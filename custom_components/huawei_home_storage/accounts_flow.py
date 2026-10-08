"""重新配置流：在一个设备条目下管理多个华为账号。

HA 里「一台设备 = 一个配置条目」，账号是它的分支。本流负责：

* 添加账号 —— 走登录流程（挑战码在需要时出现），成功后并入 ``accounts`` 列表
* 移除账号 —— 从列表删除；至少保留一个
* 重新登录某个账号 —— 单独更新该账号的凭据

每个账号独立持有：``dev_mac``（设备按 client 标识维持会话，相同标识会互相
顶掉）、云端 token、以及由设备分配的**独立隧道端口**。
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import HuaweiAccountError, huawei_account
from .api.device import derive_dev_mac
from .challenge_flow import _channel_schema, _selectable_channels
from .const import (
    CONF_ACCOUNT,
    CONF_ACCOUNTS,
    CONF_CHALLENGE_CHANNEL,
    CONF_DEV_MAC,
    CONF_LOGIN_METHOD,
    CONF_PASSWORD,
    CONF_UID,
    CONF_USER,
    LOGIN_METHOD_ACCOUNT,
)

_LOGGER = logging.getLogger(__name__)

MAX_ACCOUNTS = 8


def _mask(value: str) -> str:
    return value if len(value) <= 7 else f"{value[:3]}****{value[-4:]}"


async def build_account_entry(
    hass: Any, entry: Any, account: str, password: str, session: Any
) -> dict[str, Any] | None:
    """登录成功后构造一条账号记录（配置流与面板登录共用）。

    抽成独立函数是为了让【HA 配置流添加账号】与【面板内登录】走**同一段**逻辑，
    避免两边行为漂移（曾出现配置流可用、另一处静默失败的情况）。
    """
    from .api import HuaweiCloudClient
    from .api.huawei_account import access_token_of, session_to_dict

    device_id = entry.data.get("device_id", "")
    uid = str(getattr(session, "user_id", "") or "")
    dev_mac = derive_dev_mac(f"{device_id}|{account}")
    try:
        # ⚠️ 必须给真实 session（async_fetch_device_credentials 内部要 post），
        # 否则抛 'NoneType' has no attribute 'post'（2026-10-06 实测）。
        session_http = async_get_clientsession(hass, verify_ssl=False)
        client = HuaweiCloudClient(session_http, access_token=access_token_of(session))
        creds = await client.async_fetch_device_credentials(
            device_id, uid, dev_mac, entry.data.get("product") or "home-assistant"
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("新增账号获取设备凭据失败: %s: %s", type(err).__name__, err)
        return None

    return {
        "key": account,
        "account": account,
        "password": password,
        "smart_session": session_to_dict(session),
        "dev_mac": dev_mac,
        "uid": uid,
        "user": creds.user,
    }



def _accounts_label(accounts: list[dict[str, Any]]) -> str:
    """账号列表的可读摘要（界面占位符 ``{accounts}``）。"""
    return "、".join(_mask(a.get("account", "")) for a in accounts) or "（无）"


def _entry_accounts(entry: ConfigEntry) -> list[dict[str, Any]]:
    """读取条目里的账号列表（兼容旧的单账号结构）。"""
    accounts = entry.data.get(CONF_ACCOUNTS)
    if accounts:
        return [dict(a) for a in accounts]
    # 旧结构：单账号字段在顶层
    if entry.data.get(CONF_ACCOUNT):
        return [
            {
                "key": entry.data.get(CONF_ACCOUNT),
                "account": entry.data.get(CONF_ACCOUNT),
                "password": entry.data.get(CONF_PASSWORD, ""),
                "smart_session": entry.data.get("smart_session") or {},
                "dev_mac": entry.data.get(CONF_DEV_MAC, ""),
                "uid": entry.data.get(CONF_UID, ""),
                "user": entry.data.get(CONF_USER, ""),
            }
        ]
    return []


def _write_accounts(entry: ConfigEntry, accounts: list[dict[str, Any]]) -> dict[str, Any]:
    """把账号列表写回条目，顶层同步主账号（兼容旧读取路径）。"""
    data = {**entry.data, CONF_ACCOUNTS: accounts}
    if accounts:
        primary = accounts[0]
        data.update(
            {
                CONF_LOGIN_METHOD: LOGIN_METHOD_ACCOUNT,
                CONF_ACCOUNT: primary.get("account", ""),
                CONF_PASSWORD: primary.get("password", ""),
                CONF_DEV_MAC: primary.get("dev_mac", ""),
                CONF_UID: primary.get("uid", ""),
                CONF_USER: primary.get("user", ""),
                "smart_session": primary.get("smart_session") or {},
            }
        )
    return data


class _AccountStepsMixin:
    """账号管理（添加 / 移除 / 重新登录）步骤，供两个流复用。

    ⚠️ 2026-10-06 踩坑（P0，用户可见故障：点「添加集成」报 ``not_implemented``）：
    ``ConfigFlow.__init_subclass__`` 对 ``domain=DOMAIN`` 的类执行
    ``HANDLERS.register(domain)(cls)``，**后注册者覆盖先注册者**。本模块此前用
    ``class HuaweiHomeStorageReconfigureFlow(ConfigFlow, domain=DOMAIN)`` 定义了
    第二个同 domain 的 flow 类，导入顺序上它**覆盖**了 ``config_flow.py`` 里真正的
    ``HuaweiHomeStorageConfigFlow``。而本类没有 ``async_step_user``，HA 于是落到
    基类默认实现::

        class ConfigFlow:
            async def async_step_user(self, user_input=None):
                return self.async_abort(reason="not_implemented")

    → 用户点「添加集成」必然得到 ``{"type":"abort","reason":"not_implemented"}``。

    同时 HA 的 ``supports_reconfigure`` 与 reconfigure 流实例化都只看
    ``HANDLERS.get(entry.domain)`` 这一个类，所以**两个类必须合一**：
    ``config_flow.py`` 的 ``HuaweiHomeStorageConfigFlow`` 继承本 mixin，
    使同一个注册类同时具备 ``async_step_user`` 与 ``async_step_reconfigure``。

    ⚠️ 2026-10-06 第二个踩坑（P1，用户可见故障：加账号要验证码时流程跑飞）：
    mixin 之前把验证码步骤命名为 ``async_step_challenge``，而
    ``HuaweiHomeStorageConfigFlow`` 自己也有 ``async_step_challenge``（设备码授权用）。
    MRO 上子类自己的方法优先，于是「添加账号 → 需要验证码」会跑到**设备码**那条
    分支（``async_step_device``），最后变成新建条目而不是把账号并入原条目。
    所以本 mixin 的验证码步骤必须用**不冲突**的名字：``async_step_acct_challenge``。

    ⚠️ 2026-10-06 第三个踩坑：``async_show_form`` / ``async_show_menu`` 的 ``step_id``
    必须与方法名一致（HA 用 ``next_step_id`` 去调 ``async_step_<id>``），
    否则报 ``Handler ... doesn't support step <id>``；且翻译键也要与 ``step_id``
    同名，否则界面显示不出标题与选项文字。
    """

    #: 由主配置流在 mixin 上复用的类型标注（避免 mixin 依赖 config_flow）
    _accounts: list[dict[str, Any]]
    _entry: ConfigEntry | None
    _pending: dict[str, Any] | None
    _provider: Any
    _challenge_prompt: str
    #: 当前待完成的 LoginChallenge（含可选的验证码投递渠道）
    _challenge: Any
    #: 非空表示当前验证码流程属于「重新登录既有账号」（key 为该账号），
    #: 完成时**更新**而不是追加，避免产生重复账号。
    _relogin_key: Any

    #: 菜单步骤的 step_id（HA 里 OptionsFlow 入口固定是 ``init``，
    #: 而 ConfigFlow 的 reconfigure 用 ``menu``）
    _MENU_STEP: str = "menu"

    def _init_account_state(self) -> None:
        """初始化账号管理相关状态（由各流的 __init__ 调用）。"""
        self._accounts = []
        self._entry = None
        self._pending = None
        self._provider = None
        self._challenge_prompt = ""
        self._challenge = None
        self._relogin_key = None

    # ------------------------------------------------------------------
    def _menu_options(self) -> list[str]:
        """账号管理菜单项（键名即后续步骤名）。"""
        options = ["add_account"] if len(self._accounts) < MAX_ACCOUNTS else []
        options.append("relogin")
        if len(self._accounts) > 1:
            options.append("remove_account")
        return options

    def _extra_menu_options(self) -> list[str]:
        """子类追加的菜单项（OptionsFlow 用来加「设备 IP」）。"""
        return []

    def _show_menu(self) -> ConfigFlowResult:
        """显示账号管理菜单。

        ``step_id`` 必须等于当前方法名（``_MENU_STEP``），否则 HA 找不到下一步。
        ConfigFlow 的 reconfigure 入口方法叫 ``async_step_menu`` → ``"menu"``；
        OptionsFlow 的入口方法固定是 ``async_step_init`` → ``"init"``。
        """
        # 菜单是流程中枢：清掉上一轮遗留的「待完成登录」状态，
        # 避免上一次 relogin 的 _relogin_key 污染后续的「添加账号」。
        self._pending = None
        self._relogin_key = None
        self._provider = None
        self._challenge_prompt = ""
        self._challenge = None
        return self.async_show_menu(
            step_id=self._MENU_STEP,
            menu_options=self._menu_options() + self._extra_menu_options(),
            description_placeholders={
                "accounts": str(len(self._accounts)),
                "list": _accounts_label(self._accounts),
            },
        )

    # ------------------------------------------------------------------
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """账号列表管理入口（⋮ →「重新配置」）。"""
        self._entry = self._get_reconfigure_entry()
        self._accounts = _entry_accounts(self._entry)
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """账号管理菜单（ConfigFlow / reconfigure 入口）。"""
        return self._show_menu()

    def _save_accounts(self, accounts: list[dict[str, Any]]) -> ConfigFlowResult:
        """把账号列表写回条目并结束流程。

        ConfigFlow 与 OptionsFlow 的收尾方式不同：

        * ``ConfigFlow``（reconfigure）用 ``async_update_reload_and_abort``
        * ``OptionsFlow`` **没有** ``async_update_reload_and_abort``（HA 2026.9.4
          实测），只能自己调 ``hass.config_entries.async_update_entry``。
          该调用在 data 变化时会触发条目的 update listener
          （``__init__._async_update_listener`` → ``async_reload``），
          所以条目照常重载；随后用 ``async_create_entry`` 以当前 options 收尾，
          避免把 options 清空。
        """
        assert self._entry is not None
        self._accounts = accounts
        data = _write_accounts(self._entry, accounts)
        if isinstance(self, OptionsFlow):
            self.hass.config_entries.async_update_entry(self._entry, data=data)
            return self.async_create_entry(data=dict(self._entry.options))
        return self.async_update_reload_and_abort(self._entry, data=data)

    # ------------------------------------------------------------------
    async def async_step_add_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if not huawei_account.is_available():
            return self.async_abort(reason="smarthome_unavailable")

        if len(self._accounts) >= MAX_ACCOUNTS:
            return self.async_abort(reason="too_many_accounts")

        if user_input is not None:
            account = str(user_input.get(CONF_ACCOUNT, "")).strip()
            password = str(user_input.get(CONF_PASSWORD, ""))
            if any(a.get("account") == account for a in self._accounts):
                errors["base"] = "account_exists"
            else:
                try:
                    provider = await huawei_account.async_create_provider(
                        self.hass, account
                    )
                    result = await huawei_account.async_begin_login(
                        provider, account, password
                    )
                except HuaweiAccountError:
                    errors["base"] = "invalid_auth"
                else:
                    self._pending = {
                        "key": account,
                        "account": account,
                        "password": password,
                    }
                    self._provider = provider
                    if getattr(result, "challenge", None) is not None:
                        self._challenge = result.challenge
                        self._challenge_prompt = result.challenge.prompt
                        return await self.async_step_acct_challenge_channel()
                    if getattr(result, "session", None) is not None:
                        return await self._finish_add_account(result.session)
                    return self.async_abort(reason="auth_failed")

        return self.async_show_form(
            step_id="add_account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_acct_challenge_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """让用户选择验证码投递渠道（短信 / 已登录设备推送）。

        ⚠️ 与 ``async_step_acct_challenge`` 同理，名字**不能**叫
        ``async_step_challenge_channel``：``HuaweiHomeStorageConfigFlow``
        自己有同名方法（user 流的渠道选择），MRO 上子类优先会把「添加账号」
        的渠道选择路由到 user 流去。
        """
        channels = _selectable_channels(self._challenge)
        if not channels:
            return await self.async_step_acct_challenge()
        if user_input is None and len(channels) == 1:
            return await self._async_dispatch_acct_channel(channels[0])
        if user_input is not None:
            wanted = str(user_input.get(CONF_CHALLENGE_CHANNEL, ""))
            chosen = next((item for item in channels if item.key == wanted), None)
            if chosen is None:
                return self.async_show_form(
                    step_id="acct_challenge_channel",
                    data_schema=_channel_schema(channels),
                    errors={"base": "code_dispatch_failed"},
                )
            return await self._async_dispatch_acct_channel(chosen)
        return self.async_show_form(
            step_id="acct_challenge_channel",
            data_schema=_channel_schema(channels),
        )

    async def _async_dispatch_acct_channel(self, channel: Any) -> ConfigFlowResult:
        """请华为按所选渠道下发验证码（短信渠道会真正发短信）。"""
        try:
            self._challenge = await huawei_account.async_select_challenge_channel(
                self._provider, channel
            )
        except HuaweiAccountError as err:
            _LOGGER.warning("验证码下发失败: %s", err)
            return self.async_show_form(
                step_id="acct_challenge_channel",
                data_schema=_channel_schema(_selectable_channels(self._challenge)),
                errors={"base": "code_dispatch_failed"},
            )
        self._challenge_prompt = self._challenge.prompt
        return await self.async_step_acct_challenge()

    async def async_step_acct_challenge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """账号登录的验证码步骤。

        ⚠️ 名字**不能**叫 ``async_step_challenge``：``HuaweiHomeStorageConfigFlow``
        自己有同名方法用于设备码授权，MRO 上子类优先，会把「添加账号」的验证码
        路由到设备码分支去（2026-10-06 发现）。
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input.get("challenge_code", "")).strip()
            try:
                result = await huawei_account.async_complete_challenge(
                    self._provider, code
                )
            except HuaweiAccountError:
                errors["base"] = "invalid_challenge"
            else:
                if getattr(result, "session", None) is not None:
                    return await self._finish_add_account(result.session)
                return self.async_abort(reason="auth_failed")

        return self.async_show_form(
            step_id="acct_challenge",
            data_schema=vol.Schema(
                {vol.Required("challenge_code"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                )}
            ),
            description_placeholders={"prompt": self._challenge_prompt},
            errors=errors,
        )

    async def _finish_add_account(self, session: Any) -> ConfigFlowResult:
        """登录成功：取设备凭据并写入账号列表。"""
        assert self._entry is not None and self._pending is not None
        account = self._pending["account"]
        device_id = self._entry.data.get("device_id", "")
        uid = str(getattr(session, "user_id", "") or "")

        from .api import HuaweiCloudClient
        from .api.huawei_account import access_token_of

        dev_mac = derive_dev_mac(f"{device_id}|{account}")
        try:
            # ⚠️ 2026-10-06 实测故障（用户报「添加账号，无法连接华为云或设备凭据」）：
            # 这里原本写的是 ``HuaweiCloudClient(session=None, ...)``，
            # 而 ``async_fetch_device_credentials`` 内部要走
            # ``async_cloud_login()`` → ``self._session.post(...)``，
            # 于是抛 ``'NoneType' object has no attribute 'post'``，
            # 被下面的 except 吞掉后统一报成 abort ``cannot_connect``，
            # 用户看到的就是「无法连接华为云或设备凭据」——真实原因是**没传 session**，
            # 与网络无关。必须给一个真实的 aiohttp session。
            # 用 async_get_clientsession：按 (verify_ssl) 缓存在 hass.data 并由 HA
            # 统一关闭；async_create_clientsession 每次调用都会新建一个 session，
            # 在配置流里反复添加账号会泄漏连接池。
            session_http = async_get_clientsession(self.hass, verify_ssl=False)
            client = HuaweiCloudClient(
                session_http, access_token=access_token_of(session)
            )
            creds = await client.async_fetch_device_credentials(
                device_id, uid, dev_mac, self._entry.data.get("product") or "home-assistant"
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "新增账号获取设备凭据失败: %s: %s", type(err).__name__, err
            )
            return self.async_abort(reason="cannot_connect")

        from .api.huawei_account import session_to_dict

        new_account = {
            "key": account,
            "account": account,
            "password": self._pending["password"],
            "smart_session": session_to_dict(session),
            "dev_mac": dev_mac,
            "uid": uid,
            "user": creds.user,
        }
        # 管理员（设备 userManageInfo level==1）排前面：它提供设备级数据
        if self._relogin_key is not None:
            # 验证码属于「重新登录既有账号」：就地更新，绝不追加，
            # 否则同一账号会出现两条（2026-10-06 发现）。
            for idx, item in enumerate(self._accounts):
                if item.get("key") == self._relogin_key:
                    self._accounts[idx] = {**item, **new_account}
                    _LOGGER.info("账号 %s 验证码登录成功，已就地更新凭据", _mask(account))
                    return self._save_accounts(list(self._accounts))
            _LOGGER.warning("重新登录目标账号 %s 已不存在，转为新增", _mask(account))

        accounts = self._accounts + [new_account]
        return self._save_accounts(accounts)

    # ------------------------------------------------------------------
    async def async_step_remove_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """移除一个账号（保留管理员账号，至少留一个）。

        ⚠️ 2026-10-06 修复的 P1：下拉框选项用的是**打码值** ``_mask(account)``
        （如 ``137****2663``），而本方法此前直接拿提交值去比 ``a["account"]``
        （真实值 ``138****3723`` 这类完整号码）→ 过滤结果恒等于原列表 → 永远走
        ``abort("cannot_remove_last")``，用户看到误导性提示且「移除账号」完全不可用。
        正确做法与 ``async_step_relogin`` 一致：用打码值**反查**真实账号。
        """
        if user_input is not None:
            target = str(user_input.get(CONF_ACCOUNT, ""))
            # 只在可选范围（非管理员账号）内反查，与下方下拉框的 self._accounts[1:] 保持一致，
            # 避免构造请求移除管理员账号（管理员账号提供设备属性）。
            removable = self._accounts[1:]
            victim = next(
                (a for a in removable if _mask(a.get("account", "")) == target),
                None,
            )
            if victim is None:
                return self.async_abort(reason="account_not_found")
            accounts = [a for a in self._accounts if a is not victim]
            if len(accounts) < 1:
                return self.async_abort(reason="cannot_remove_last")
            return self._save_accounts(accounts)

        return self.async_show_form(
            step_id="remove_account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                _mask(a.get("account", ""))
                                for a in self._accounts[1:]
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_ACCOUNT,
                        )
                    )
                }
            ),
        )

    async def async_step_relogin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """重新登录指定账号（更新其凭据，不影响其它账号）。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            target = str(user_input.get(CONF_ACCOUNT, ""))
            password = str(user_input.get(CONF_PASSWORD, ""))
            account = next(
                (a for a in self._accounts if _mask(a.get("account", "")) == target),
                None,
            )
            if account is None:
                return self.async_abort(reason="account_not_found")
            try:
                provider = await huawei_account.async_create_provider(
                    self.hass, account["account"]
                )
                result = await huawei_account.async_begin_login(
                    provider, account["account"], password
                )
            except HuaweiAccountError:
                errors["base"] = "invalid_auth"
            else:
                if getattr(result, "session", None) is not None:
                    from .api.huawei_account import session_to_dict

                    account["smart_session"] = session_to_dict(result.session)
                    account["password"] = password
                    return self._save_accounts(list(self._accounts))
                # ⚠️ 需要验证码时，必须让验证码步骤知道这是「重新登录既有账号」，
                # 否则 _finish_add_account 会**再追加一个同账号**（重复账号）。
                self._relogin_key = account.get("key") or account.get("account")
                self._pending = {
                    "key": account.get("key"),
                    "account": account["account"],
                    "password": password,
                }
                self._provider = provider
                self._challenge = result.challenge
                self._challenge_prompt = result.challenge.prompt
                return await self.async_step_acct_challenge_channel()

        return self.async_show_form(
            step_id="relogin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                _mask(a.get("account", ""))
                                for a in self._accounts
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_ACCOUNT,
                        )
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )


class HuaweiHomeStorageAccountsFlow(_AccountStepsMixin, OptionsFlow):
    """选项流 = 集成页「配置」按钮：账号管理 + 设备 IP（排障）。

    ⚠️ 2026-10-06 用户反馈「你说的设置里面添加账号，我没找到」的根因：
    本类此前**只有**一个设备 IP 输入框，而界面提示却写着「账号增删请点集成页的
    「配置」按钮」——文字与实际行为不符。账号菜单其实藏在 ⋮ →「重新配置」
    （``async_step_reconfigure``）里，用户按提示点「配置」自然找不到。
    现在把账号菜单并入本流，两个入口都能管账号。

    ⚠️ OptionsFlow 的三条硬约束（HA 2026.9.4 实测）：

    1. 入口方法**固定**是 ``async_step_init``，所以 ``_MENU_STEP`` 必须是 ``"init"``。
    2. ``OptionsFlow`` **没有** ``async_update_reload_and_abort``（只有 ConfigFlow 有），
       不能照抄 reconfigure 的收尾写法。
    3. ``async_create_entry`` 只写 ``entry.options``，**永远写不到 ``entry.data``**，
       而账号存在 ``entry.data[CONF_ACCOUNTS]``。所以必须自己调
       ``hass.config_entries.async_update_entry``（见 ``_save_accounts``）。

    ⚠️ 同理，``__init__`` 里不能碰 ``self.config_entry``：该属性在初始化阶段
    hass 为 None，会抛 ``ValueError("The config entry is not available during
    initialisation")``。HA 通过 ``async_get_options_flow(entry)`` 把条目传进来，
    所以这里沿用构造参数保存。
    """

    #: OptionsFlow 的入口方法叫 async_step_init，菜单 step_id 必须与之一致
    _MENU_STEP = "init"

    def __init__(self, entry: ConfigEntry) -> None:
        self._init_account_state()
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """账号管理菜单（「配置」按钮的直接落地页）。"""
        self._accounts = _entry_accounts(self._entry)
        return self._show_menu()

    def _extra_menu_options(self) -> list[str]:
        return ["host"]

    # ------------------------------------------------------------------
    async def async_step_host(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """设备 IP 覆盖（自动获取失败时排障用）。

        ⚠️ 必须写进 ``entry.data``：``__init__.py`` 构建客户端时读的是
        ``entry.data.get(CONF_HOST)``。此前本流用 ``async_create_entry`` 收尾，
        只落到 ``entry.options``，而集成从不读 options → 这个输入框**完全无效**。
        """
        from .const import CONF_HOST

        if user_input is not None:
            host = str(user_input.get(CONF_HOST, "")).strip()
            self.hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, CONF_HOST: host}
            )
            _LOGGER.info(
                "设备 IP 覆盖已保存：%s（条目 %s）", host or "（清空，回退自动获取）",
                self._entry.entry_id,
            )
            return self.async_create_entry(data=dict(self._entry.options))

        return self.async_show_form(
            step_id="host",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HOST, default=self._entry.data.get(CONF_HOST, "")
                    ): str
                }
            ),
            description_placeholders={
                "accounts": _accounts_label(self._accounts),
            },
        )
