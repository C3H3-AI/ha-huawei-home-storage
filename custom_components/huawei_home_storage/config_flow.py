"""Config flow for Huawei Home Storage。

两种登录方式（优先账号密码，不跳浏览器）：
  1. **华为账号密码**：账号 + 密码（+ 可能的**短信验证码**或挑战码），
     登录实现已随本仓库自包含分发，全程留在 HA 界面内。
  2. **设备码授权**：跳浏览器确认一次，HA 不接触密码。

两种方式之后都一样：**设备 IP / MAC / 序列号 / 型号 / 名称全部自动获取，无需输入**。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .accounts_flow import _AccountStepsMixin
from .api import (
    HuaweiAccountError,
    HuaweiCloudClient,
    HuaweiCloudError,
    decode_uid,
    derive_dev_mac,
    huawei_account,
)
from .challenge_flow import (
    _channel_schema,
    _selectable_channels,
)
from .api.auth.interface import ChallengeChannel
from .const import (
    CLOUD_PROD_ID,
    CONF_ACCOUNT,
    CONF_ACCOUNTS,
    CONF_CHALLENGE_CHANNEL,
    CONF_DEV_MAC,
    CONF_DEVICE_ID,
    CONF_DEVICE_MAC,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_HOST,
    CONF_LOGIN_METHOD,
    CONF_PASSWORD,
    CONF_PRODUCT,
    CONF_REFRESH_TOKEN,
    CONF_SMART_SESSION,
    CONF_UID,
    CONF_USER,
    DEFAULT_PRODUCT,
    DOMAIN,
    LOGIN_METHOD_ACCOUNT,
    LOGIN_METHOD_DEVICE_CODE,
    OAUTH_VERIFY_URL,
)

_LOGGER = logging.getLogger(__name__)

_TEXT = TextSelectorConfig(type=TextSelectorType.TEXT)
_PASSWORD = TextSelectorConfig(type=TextSelectorType.PASSWORD)


def _host_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """仅选项流使用：手动覆盖设备 IP（排障用）。"""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Optional(CONF_HOST, default=d.get(CONF_HOST, "")): TextSelector(_TEXT),
        }
    )


class HuaweiHomeStorageConfigFlow(
    _AccountStepsMixin, config_entries.ConfigFlow, domain=DOMAIN
):
    """华为家庭存储配置向导（含账号管理 reconfigure 步骤）。

    ⚠️ ``domain=DOMAIN`` 必须只出现在本类上。HA 的
    ``ConfigFlow.__init_subclass__`` 会对每个 ``domain=DOMAIN`` 的类执行
    ``HANDLERS.register(domain)(cls)``，后注册者覆盖先注册者；而
    ``supports_reconfigure``、reconfigure 流实例化、user 流实例化
    **全都只看 HANDLERS 里的这一个类**。所以账号管理步骤必须以 mixin
    并入本类，绝不能另建一个同 domain 的 flow 类（2026-10-06 的
    ``not_implemented`` 故障就是这么来的）。
    """

    # ⚠️ 这个值决定新建条目的 version，必须等于 HA 认定的本集成 flow 版本。
    # 2026-10-06 踩坑：这里曾是 3，导致新建条目 version=3，
    # 而 HA 比较基准是 ConfigFlow 子类的 VERSION（本类即为该基准），
    # 造成「条目 version 高于集成支持版本」→ 条目落 MIGRATION_ERROR 而拒载。
    # ⚠️ 注意：这与 manifest.json 的 "version": "0.8.0"（集成自身版本号）无关，
    # 后者是字符串形式的 HACS/集成版本，绝不可拿来对齐或改成数字。
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._session = None
        self._method: str = LOGIN_METHOD_DEVICE_CODE
        self._account: str = ""
        self._password: str = ""
        self._cloud_session: Any = None          # AuthSession
        self._provider: Any = None               # 当前流程持有的登录 provider
        self._challenge: Any = None              # 当前待完成的 LoginChallenge（含可选渠道）
        self._device_code: str = ""
        self._user_code: str = ""
        self._verify_url: str = OAUTH_VERIFY_URL
        self._deadline: float = 0.0
        self._tokens: dict[str, Any] = {}
        # 账号管理（reconfigure）状态
        self._init_account_state()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _ensure_session(self) -> None:
        if self._session is None:
            self._session = async_create_clientsession(self.hass, verify_ssl=False)

    # ------------------------------------------------------------------
    # step 1：选择登录方式
    # ------------------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not huawei_account.is_available():
            # 登录实现不可用 → 只能用设备码
            self._method = LOGIN_METHOD_DEVICE_CODE
            return await self._async_device_code_begin()

        if user_input is not None:
            self._method = str(user_input[CONF_LOGIN_METHOD])
            if self._method == LOGIN_METHOD_ACCOUNT:
                return await self.async_step_account()
            return await self._async_device_code_begin()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOGIN_METHOD, default=LOGIN_METHOD_ACCOUNT
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[LOGIN_METHOD_ACCOUNT, LOGIN_METHOD_DEVICE_CODE],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_LOGIN_METHOD,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # 方式 A：华为账号密码
    # ------------------------------------------------------------------
    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            account = str(user_input[CONF_ACCOUNT]).strip()
            password = str(user_input[CONF_PASSWORD])
            try:
                provider = await huawei_account.async_create_provider(self.hass, account)
                result = await huawei_account.async_begin_login(
                    provider, account, password
                )
            except HuaweiAccountError as err:
                _LOGGER.warning("账号登录失败: %s", err)
                errors["base"] = "invalid_auth"
            else:
                self._account = account
                self._provider = provider
                if getattr(result, "challenge", None) is not None:
                    self._password = password
                    self._challenge = result.challenge
                    self._challenge_prompt = result.challenge.prompt
                    return await self.async_step_challenge_channel()
                if getattr(result, "session", None) is not None:
                    self._password = password
                    self._cloud_session = result.session
                    return await self.async_step_device()
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT): TextSelector(_TEXT),
                    vol.Required(CONF_PASSWORD): TextSelector(_PASSWORD),
                }
            ),
            errors=errors,
        )

    async def async_step_challenge_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """让用户选择验证码投递渠道（短信 / 已登录设备推送）。

        华为返回的 ``authCodeSentList`` 可能同时含短信与设备两个渠道，
        选短信时还需要向账号 Web 层请求下发（``async_select_challenge_channel``
        内部完成）。只有一个渠道时直接跳过本步，不打扰用户。
        """
        channels = _selectable_channels(self._challenge)
        if not channels:
            return await self.async_step_challenge()
        if user_input is None and len(channels) == 1:
            return await self._async_dispatch_channel(channels[0])
        if user_input is not None:
            wanted = str(user_input.get(CONF_CHALLENGE_CHANNEL, ""))
            chosen = next((item for item in channels if item.key == wanted), None)
            if chosen is None:
                return self.async_show_form(
                    step_id="challenge_channel",
                    data_schema=_channel_schema(channels),
                    errors={"base": "code_dispatch_failed"},
                )
            return await self._async_dispatch_channel(chosen)
        return self.async_show_form(
            step_id="challenge_channel",
            data_schema=_channel_schema(channels),
        )

    async def _async_dispatch_channel(self, channel: ChallengeChannel) -> FlowResult:
        """请华为按所选渠道下发验证码，成功后进入输入步骤。"""
        try:
            self._challenge = await huawei_account.async_select_challenge_channel(
                self._provider, channel
            )
        except HuaweiAccountError as err:
            _LOGGER.warning("验证码下发失败: %s", err)
            return self.async_show_form(
                step_id="challenge_channel",
                data_schema=_channel_schema(_selectable_channels(self._challenge)),
                errors={"base": "code_dispatch_failed"},
            )
        self._challenge_prompt = self._challenge.prompt
        return await self.async_step_challenge()

    async def async_step_challenge(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input["challenge_code"]).strip()
            try:
                session = await huawei_account.async_complete_challenge(
                    self._provider, code
                )
            except HuaweiAccountError as err:
                _LOGGER.warning("挑战码校验失败: %s", err)
                errors["base"] = "invalid_challenge"
            else:
                self._cloud_session = session
                return await self.async_step_device()

        return self.async_show_form(
            step_id="challenge",
            data_schema=vol.Schema({vol.Required("challenge_code"): TextSelector(_TEXT)}),
            errors=errors,
            description_placeholders={
                "prompt": getattr(self, "_challenge_prompt", "") or "请输入华为账号验证码"
            },
        )

    # ------------------------------------------------------------------
    # 方式 B：设备码授权
    # ------------------------------------------------------------------
    async def _async_device_code_begin(self) -> FlowResult:
        self._ensure_session()
        try:
            code = await HuaweiCloudClient.async_request_device_code(self._session)
        except HuaweiCloudError as err:
            _LOGGER.warning("申请设备码失败: %s", err)
            return self.async_show_form(
                step_id="retry",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )
        self._device_code = code["device_code"]
        self._user_code = code.get("user_code", "")
        self._verify_url = code.get("verification_url") or OAUTH_VERIFY_URL
        self._deadline = time.time() + int(code.get("expire_in", 1800))
        return await self.async_step_authorize()

    async def async_step_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """申请设备码失败后的重试入口。"""
        return await self._async_device_code_begin()

    async def async_step_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if time.time() > self._deadline:
                try:
                    code = await HuaweiCloudClient.async_request_device_code(self._session)
                except HuaweiCloudError:
                    errors["base"] = "cannot_connect"
                else:
                    self._device_code = code["device_code"]
                    self._user_code = code.get("user_code", "")
                    self._verify_url = code.get("verification_url") or OAUTH_VERIFY_URL
                    self._deadline = time.time() + int(code.get("expire_in", 1800))
                    errors["base"] = "code_expired"
            else:
                try:
                    tokens = await HuaweiCloudClient.async_poll_device_code(
                        self._session, self._device_code
                    )
                except HuaweiCloudError as err:
                    _LOGGER.warning("设备码轮询失败: %s", err)
                    errors["base"] = "auth_failed"
                else:
                    if tokens is None:
                        errors["base"] = "authorization_pending"
                    else:
                        self._tokens = tokens
                        return await self.async_step_device()

        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "url": f"{self._verify_url}?user_code={self._user_code}",
                "code": self._user_code,
            },
        )

    # ------------------------------------------------------------------
    # step 3：选择设备（两种方式共用）
    # ------------------------------------------------------------------
    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        client = self._cloud_client()
        try:
            devices = [
                d
                for d in await client.async_list_devices()
                if (d.get("devInfo") or {}).get("prodId") == CLOUD_PROD_ID
            ]
        except HuaweiCloudError as err:
            _LOGGER.warning("获取云设备列表失败: %s", err)
            return self.async_abort(reason="cannot_connect")

        if not devices:
            return self.async_abort(reason="no_device")

        if user_input is not None:
            device = next(
                (d for d in devices if d.get("devId") == user_input[CONF_DEVICE_ID]),
                None,
            )
            if device is None:
                return self.async_abort(reason="no_device")
            return await self._async_finish(client, device, len(devices))

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_ID, default=devices[0]["devId"]
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=d["devId"], label=_device_label(d))
                                for d in devices
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    def _cloud_client(self) -> HuaweiCloudClient:
        self._ensure_session()
        if self._method == LOGIN_METHOD_ACCOUNT:
            token = huawei_account.access_token_of(self._cloud_session)
            client = HuaweiCloudClient(self._session, access_token=token)
        else:
            client = HuaweiCloudClient(
                self._session,
                access_token=self._tokens.get("access_token"),
                refresh_token=self._tokens.get("refresh_token"),
            )
        client.set_executor(
            lambda func, *args: self.hass.async_add_executor_job(func, *args)
        )
        return client

    def _same_device_configured(self, dev_id: str) -> bool:
        """是否已存在指向同一台设备（另一个账号）的配置条目。"""
        return self._entry_for_device(dev_id) is not None

    def _entry_for_device(self, dev_id: str) -> config_entries.ConfigEntry | None:
        """找出已配置了同一台设备的条目（用于把新账号并入其中）。"""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_DEVICE_ID) == dev_id:
                return entry
        return None

    @staticmethod
    def _has_account(entry: config_entries.ConfigEntry, account_key: str) -> bool:
        """该条目里是否已有这个账号（含顶层扁平字段的旧结构）。"""
        for item in entry.data.get(CONF_ACCOUNTS) or []:
            if str(item.get("key") or item.get("account") or "") == account_key:
                return True
        return str(entry.data.get(CONF_ACCOUNT) or "") == account_key

    async def _async_finish(
        self, client: HuaweiCloudClient, device: dict[str, Any], device_count: int = 1
    ) -> FlowResult:
        """走一遍 startService 验证，并把自动获取的设备信息一并存进配置条目。"""
        dev_id = device["devId"]
        if self._method == LOGIN_METHOD_ACCOUNT:
            uid = str(getattr(self._cloud_session, "user_id", "") or "")
            account_key = self._account
        else:
            uid = decode_uid(self._tokens.get("id_token") or "") or ""
            account_key = uid or "device_code"

        # 客户端标识按「账号 + 设备」派生。设备是**按 client 标识维持会话**的：
        # 标识相同则后一次 startService 会把前一次的会话顶掉（已实测 401），
        # 标识不同则可并存（已验证 5 个）。所以同一台设备的不同账号必须用不同标识，
        # 否则两个条目会互相踢下线、陷入反复重取凭据。
        dev_mac = derive_dev_mac(f"{dev_id}|{account_key}")

        try:
            creds = await client.async_fetch_device_credentials(
                dev_id, uid, dev_mac, DEFAULT_PRODUCT
            )
        except HuaweiCloudError as err:
            _LOGGER.warning("获取设备凭据失败: %s", err)
            return self.async_abort(reason="cannot_connect")

        # reauth 流程只更新原条目，不做「已配置」拦截，也不新建
        reauth_entry = (
            self._get_reauth_entry()
            if self.source == config_entries.SOURCE_REAUTH
            else None
        )

        # 唯一标识 = 设备 + 账号。
        # ⚠️ 2026-10-06 变更（用户选定设计）：若该**设备**已有条目，则把新账号
        # **并入那个条目的 accounts**，而不是新建条目。原因：
        #   1. 设备级实体的 unique_id 由设备序列号派生（entity.main_device_identifier），
        #      两个条目指向同一台设备 → unique_id 完全相同 → HA 直接忽略第二个条目的
        #      全部设备实体（实测日志：
        #      "Platform huawei_home_storage does not generate unique IDs.
        #       ID A4DEQ22A21000000_disk_slots already exists - ignoring ..."）。
        #   2. 一条目多账号本就是本集成的设计模型（accounts 列表 + 账号子设备）。
        # 因此「添加集成」在已有同设备条目时，等价于「配置 → 添加账号」。
        existing = self._entry_for_device(dev_id) if reauth_entry is None else None
        if existing is not None:
            if self._has_account(existing, account_key):
                return self.async_abort(reason="already_configured")
            if self._method != LOGIN_METHOD_ACCOUNT:
                # 设备码模式下新账号没有可写入的凭据结构，维持原有的拦截语义
                await self.async_set_unique_id(f"{dev_id}|{account_key}")
                self._abort_if_unique_id_configured()
            else:
                merged = self._merge_account(existing, dev_id, account_key, dev_mac, uid,
                                             creds, device)
                return self.async_update_reload_and_abort(
                    existing, data={**existing.data, **merged}
                )

        if reauth_entry is None:
            await self.async_set_unique_id(f"{dev_id}|{account_key}")
            self._abort_if_unique_id_configured()

        info = device.get("devInfo") or {}
        base = device.get("devName") or info.get("deviceName") or "Huawei Home Storage"
        sn = info.get("sn") or ""
        marks: list[str] = []
        if device_count > 1 and sn:
            marks.append(sn[-4:])
        if self._same_device_configured(dev_id):
            marks.append(_mask(account_key))
        title = f"{base}（{' · '.join(marks)}）" if marks else base
        data: dict[str, Any] = {
            CONF_LOGIN_METHOD: self._method,
            CONF_HOST: _host_of(creds.https_url),
            CONF_DEVICE_ID: dev_id,
            CONF_DEVICE_MAC: info.get("mac") or "",
            CONF_DEVICE_SN: info.get("sn") or "",
            CONF_DEVICE_MODEL: info.get("hwv") or info.get("model") or "",
            CONF_DEV_MAC: dev_mac,
            CONF_PRODUCT: DEFAULT_PRODUCT,
            CONF_UID: uid,
            CONF_USER: creds.user,
        }
        if self._method == LOGIN_METHOD_ACCOUNT:
            data[CONF_ACCOUNT] = self._account
            data[CONF_PASSWORD] = self._password
            data[CONF_SMART_SESSION] = huawei_account.session_to_dict(self._cloud_session)
            # ⚠️ 2026-10-06 修复的 P0：必须同时写入多账号结构 ``accounts``。
            # 之前只写顶层扁平字段，于是新建条目的 ``accounts`` 为空 →
            # ``async_setup_entry`` 取 ``primary = accounts[0] if accounts else None``
            # 得到 None → ``_build_client`` 走设备码分支用 refresh_token，
            # 而账号密码模式从不写该字段 → 云侧报「缺少 refresh_token」，
            # 条目停在 setup_retry，用户添加账号必然失败。
            data[CONF_ACCOUNTS] = [
                {
                    "key": self._account,
                    "account": self._account,
                    "password": self._password,
                    "smart_session": data[CONF_SMART_SESSION],
                    "dev_mac": dev_mac,
                    "uid": uid,
                    "user": creds.user,
                }
            ]
        else:
            data[CONF_REFRESH_TOKEN] = self._tokens.get("refresh_token") or ""

        if reauth_entry is not None:
            return self.async_update_reload_and_abort(
                reauth_entry, data={**reauth_entry.data, **data}
            )
        return self.async_create_entry(title=title, data=data)

    def _merge_account(
        self,
        existing: config_entries.ConfigEntry,
        dev_id: str,
        account_key: str,
        dev_mac: str,
        uid: str,
        creds: Any,
        device: dict[str, Any],
    ) -> dict[str, Any]:
        """把新账号并入已有条目的 ``accounts`` 列表。

        返回**需要更新到条目上的字段**（调用方用 ``{**existing.data, **merged}`` 合并）。
        行为与「配置 → 添加账号」保持一致：保留原主账号顺序，新账号追加在后。
        """
        session = huawei_account.session_to_dict(self._cloud_session)
        new_account = {
            "key": account_key,
            "account": account_key,
            "password": self._password,
            "smart_session": session,
            "dev_mac": dev_mac,
            "uid": uid,
            "user": creds.user,
        }

        # 沿用已有 accounts；若它是旧结构（只有顶层扁平字段），先从扁平字段还原
        accounts = [dict(a) for a in (existing.data.get(CONF_ACCOUNTS) or [])]
        if not accounts and existing.data.get(CONF_ACCOUNT):
            old = existing.data
            accounts = [
                {
                    "key": old.get(CONF_ACCOUNT),
                    "account": old.get(CONF_ACCOUNT),
                    "password": old.get(CONF_PASSWORD, ""),
                    "smart_session": old.get(CONF_SMART_SESSION) or {},
                    "dev_mac": old.get(CONF_DEV_MAC, ""),
                    "uid": old.get(CONF_UID, ""),
                    "user": old.get(CONF_USER, ""),
                }
            ]

        accounts.append(new_account)
        _LOGGER.info(
            "「添加集成」检测到设备 %s 已有条目 %s，新账号 %s 并入该条目（账号数 %d）",
            dev_id,
            existing.entry_id,
            _mask(account_key),
            len(accounts),
        )

        # 顶层字段保持指向**主账号**（accounts[0]），与 _write_accounts_compat 语义一致；
        # 设备信息用新取到的凭据刷新（隧道端口会变）。
        info = device.get("devInfo") or {}
        primary = accounts[0]
        return {
            CONF_ACCOUNTS: accounts,
            CONF_LOGIN_METHOD: LOGIN_METHOD_ACCOUNT,
            CONF_ACCOUNT: primary.get("account", ""),
            CONF_PASSWORD: primary.get("password", ""),
            CONF_DEV_MAC: primary.get("dev_mac", ""),
            CONF_UID: primary.get("uid", ""),
            CONF_USER: primary.get("user", ""),
            CONF_SMART_SESSION: primary.get("smart_session") or {},
            CONF_HOST: _host_of(creds.https_url) or existing.data.get(CONF_HOST, ""),
            CONF_DEVICE_MAC: info.get("mac") or existing.data.get(CONF_DEVICE_MAC, ""),
            CONF_DEVICE_SN: info.get("sn") or existing.data.get(CONF_DEVICE_SN, ""),
            CONF_DEVICE_MODEL: (
                info.get("hwv") or info.get("model")
                or existing.data.get(CONF_DEVICE_MODEL, "")
            ),
        }

    # ------------------------------------------------------------------
    # 重新认证
    # ------------------------------------------------------------------
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """重新认证：拿到新会话后**更新原条目**，不新建。"""
        if (entry_data.get(CONF_LOGIN_METHOD) == LOGIN_METHOD_ACCOUNT
                and huawei_account.is_available() and entry_data.get(CONF_ACCOUNT)):
            self._method = LOGIN_METHOD_ACCOUNT
            self._account = str(entry_data[CONF_ACCOUNT])
            self._password = str(entry_data.get(CONF_PASSWORD) or "")
            try:
                provider = await huawei_account.async_create_provider(
                    self.hass, self._account
                )
                result = await huawei_account.async_begin_login(
                    provider, self._account, self._password
                )
            except HuaweiAccountError:
                return await self.async_step_account()
            self._provider = provider
            if getattr(result, "session", None) is not None:
                self._cloud_session = result.session
                return await self.async_step_device()
            if getattr(result, "challenge", None) is not None:
                self._challenge = result.challenge
                self._challenge_prompt = result.challenge.prompt
                return await self.async_step_challenge_channel()
            return await self.async_step_account()

        self._method = LOGIN_METHOD_DEVICE_CODE
        return await self._async_device_code_begin()

    # ------------------------------------------------------------------
    # 选项：仅用于手动覆盖设备 IP（排障）
    # ------------------------------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        from .accounts_flow import HuaweiHomeStorageAccountsFlow

        return HuaweiHomeStorageAccountsFlow(entry)


def _device_label(device: dict[str, Any]) -> str:
    info = device.get("devInfo") or {}
    name = device.get("devName") or info.get("deviceName") or device.get("devId")
    extras = " · ".join(x for x in (info.get("model"), info.get("mac")) if x)
    return f"{name}（{extras}）" if extras else str(name)


def _host_of(url: str) -> str:
    """从 https://host:8471/ 里取出 host。"""
    if not url:
        return ""
    return url.split("//", 1)[-1].split(":")[0].split("/")[0]


def _mask(value: str) -> str:
    """账号/uid 中间打码，用于条目标题。"""
    if len(value) <= 6:
        return value
    return f"{value[:3]}****{value[-4:]}"
