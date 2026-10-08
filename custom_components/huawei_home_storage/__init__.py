"""Huawei Home Storage integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .api import (
    DeviceCredentials,
    HuaweiAccountError,
    HuaweiCloudAuthError,
    HuaweiCloudClient,
    HuaweiDeviceAuthError,
    HuaweiDeviceClient,
    derive_dev_mac,
    huawei_account,
)
from .const import (
    CONF_ACCOUNT,
    CONF_ACCOUNTS,
    CONF_DEV_MAC,
    CONF_DEVICE_ID,
    ENTRY_VERSION,
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
    PLATFORMS,
)
from .coordinator import (
    HuaweiAlbumCoordinator,
    HuaweiFastCoordinator,
    HuaweiInfoCoordinator,
    HuaweiStorageData,
)
from .entity import _account_key, find_main_device, main_device_identifier, main_device_info
from .account_login import async_register_websocket
from .panel import async_register_panel, async_unregister_panel
from .services import async_register_services
from .views import async_register_views, async_unregister_views

_LOGGER = logging.getLogger(__name__)

TOKEN_STORE_VERSION = 1
TOKEN_STORE_KEY = "refresh_token"

HuaweiConfigEntry = ConfigEntry  # 运行期实际携带 HuaweiStorageData（runtime_data）


def _account_token_provider(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: Store,
    stored: dict[str, Any],
    account: dict[str, Any] | None = None,
) -> Any:
    """账号密码模式：优先静默续期，失败则用账号密码重新登录。

    ``account`` 为空时按旧结构（单账号，字段在 entry.data 顶层）取；
    单条目多账号模式下传入对应的账号 dict。
    """
    if account:
        account_name = str(account.get("account") or "")
        password = str(account.get("password") or "")
        initial_session = account.get("smart_session") or stored.get(CONF_SMART_SESSION) or {}
    else:
        account_name = str(entry.data.get(CONF_ACCOUNT) or "")
        password = str(entry.data.get(CONF_PASSWORD) or "")
        initial_session = stored.get(CONF_SMART_SESSION) or entry.data.get(CONF_SMART_SESSION) or {}

    state: dict[str, Any] = {
        "session": huawei_account.rebuild_session(hass, initial_session, account_name)
    }

    async def provider() -> str:
        session = state["session"]
        try:
            session = await huawei_account.async_refresh_session(hass, session)
        except HuaweiAccountError as err:
            _LOGGER.debug("云端会话续期失败，改用账号密码重新登录: %s", err)
            try:
                login_provider = await huawei_account.async_create_provider(hass, account_name)
                result = await huawei_account.async_begin_login(
                    login_provider, account_name, password
                )
            except HuaweiAccountError as login_err:
                raise HuaweiCloudAuthError(f"华为账号登录失败: {login_err}") from login_err
            if getattr(result, "challenge", None) is not None:
                raise HuaweiCloudAuthError("华为账号需要验证码验证，请重新配置该集成")
            if getattr(result, "session", None) is None:
                raise HuaweiCloudAuthError("华为账号登录未返回会话，请重新配置该集成")
            session = result.session

        state["session"] = session
        token = huawei_account.access_token_of(session)
        if not token:
            raise HuaweiCloudAuthError("未能取得华为云端访问令牌")
        data = await store.async_load() or {}
        snap = huawei_account.session_to_dict(session)
        data[CONF_SMART_SESSION] = snap
        await store.async_save(data)
        if account is not None and entry is not None:
            # 同步回条目里的账号快照：否则每次重启都会拿 3 小时前的旧 token，
            # 导致 message-center 报 200201 Token is expired
            # （2026-10-06 排查相册 16106 时踩过：探针读 .storage 里的旧快照，
            #   误判成设备相册服务故障）
            account["smart_session"] = snap
            accounts_now = list(entry.data.get(CONF_ACCOUNTS) or [])
            for idx, item in enumerate(accounts_now):
                if _account_key(item) == _account_key(account):
                    accounts_now[idx] = dict(item, smart_session=snap)
                    break
            else:
                accounts_now.append(dict(account))
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_ACCOUNTS: accounts_now}
            )
        return token

    return provider


def _migrate_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """旧版本唯一标识是裸 devId；新版为「设备 + 账号」。

    不迁移的话，同一台设备 + 同一账号会被允许重复添加。
    """
    current = entry.unique_id or ""
    if not current or "|" in current:
        return
    key = entry.data.get(CONF_ACCOUNT) or entry.data.get(CONF_UID) or "device_code"
    hass.config_entries.async_update_entry(entry, unique_id=f"{current}|{key}")
    _LOGGER.info("唯一标识已迁移为「设备 + 账号」形式")


async def async_migrate_entry(hass: HomeAssistant, entry: HuaweiConfigEntry) -> bool:
    """条目结构迁移：单账号字段 → ``accounts`` 列表。

    v0.6.x 起一个条目管理多个账号（``data["accounts"]``），此前账号信息散在
    顶层字段。没有这一步 HA 会把条目标成 ``migration_error`` 而拒绝加载。

    ⚠️ 2026-10-06 踩过的坑：条目 version 会被各种路径抬高，一旦**超过** HA 认为的
    集成版本（manifest 无 ``version`` 字段时恒为 1），HA 直接拒绝加载并报::

        Config entry ... has version 3 which is higher than the current version 1

    此时本函数根本不会被调用（HA 在调用前就拒绝），表现为条目 data 读不出来、
    配置流没有入口。所以这里不信任条目的 version 字段，一律按**数据结构**
    判断是否需要迁移，并把 version 归一到本集成当前支持的版本。
    """
    _LOGGER.info(
        "async_migrate_entry: version=%s data键=%s accounts=%s",
        entry.version,
        sorted(entry.data),
        len(entry.data.get(CONF_ACCOUNTS) or []),
    )
    if entry.data.get(CONF_ACCOUNTS):
        # 已是新结构；顺带把顶层主账号字段补齐（兼容旧读取路径）
        if entry.version != ENTRY_VERSION:
            hass.config_entries.async_update_entry(
                entry,
                data=_write_accounts_compat(entry, entry.data[CONF_ACCOUNTS]),
                version=ENTRY_VERSION,
            )
        return True

    account = entry.data.get(CONF_ACCOUNT)
    if not account:
        # 设备码模式：没有账号概念，直接放行
        if entry.version != ENTRY_VERSION:
            hass.config_entries.async_update_entry(entry, version=ENTRY_VERSION)
        return True

    accounts = [
        {
            "key": account,
            "account": account,
            "password": entry.data.get(CONF_PASSWORD, ""),
            "smart_session": entry.data.get(CONF_SMART_SESSION) or {},
            "dev_mac": entry.data.get(CONF_DEV_MAC, ""),
            "uid": entry.data.get(CONF_UID, ""),
            "user": entry.data.get(CONF_USER, ""),
        }
    ]
    _LOGGER.info("迁移为单条目多账号结构，账号数=%d", len(accounts))
    hass.config_entries.async_update_entry(
        entry, data=_write_accounts_compat(entry, accounts), version=ENTRY_VERSION
    )
    return True


def _mask_account(value: Any) -> str:
    """账号中间打码（仅用于日志）。"""
    text = str(value or "")
    if len(text) <= 6:
        return text
    return f"{text[:3]}****{text[-4:]}"


def _accounts_from_flat_data(entry: HuaweiConfigEntry) -> list[dict[str, Any]]:
    """从顶层扁平字段还原出 ``accounts`` 列表（账号密码模式）。

    ⚠️ 2026-10-06 修复的 P0：``config_flow._async_finish`` 曾只写顶层扁平字段
    （``account``/``password``/``smart_session``…）而**不写 ``accounts``**，
    于是新建条目 ``accounts`` 为空 → ``async_setup_entry`` 里
    ``primary = accounts[0] if accounts else None`` 得到 ``None`` →
    ``_build_client`` 走设备码分支去用 ``refresh_token``，而账号密码模式从不写该字段
    → 云侧报「缺少 refresh_token」，条目停在 ``setup_retry``，添加账号必然失败。

    这个函数让**已经写坏的旧条目**在 setup 时自动恢复，不必让用户删掉重加。
    设备码模式（无 ``account``）返回空列表，交由原逻辑处理。
    """
    account = entry.data.get(CONF_ACCOUNT)
    if not account:
        return []
    if entry.data.get(CONF_LOGIN_METHOD) not in (None, LOGIN_METHOD_ACCOUNT):
        return []
    return [
        {
            "key": account,
            "account": account,
            "password": entry.data.get(CONF_PASSWORD, "") or "",
            "smart_session": entry.data.get(CONF_SMART_SESSION) or {},
            "dev_mac": entry.data.get(CONF_DEV_MAC, "") or "",
            "uid": entry.data.get(CONF_UID, "") or "",
            "user": entry.data.get(CONF_USER, "") or "",
        }
    ]


def _write_accounts_compat(
    entry: HuaweiConfigEntry, accounts: list[dict[str, Any]]
) -> dict[str, Any]:
    """账号列表 + 顶层同步主账号（兼容旧的单账号读取路径）。"""
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
                CONF_SMART_SESSION: primary.get("smart_session") or {},
            }
        )
    return data


def _build_client(
    hass: HomeAssistant,
    entry: HuaweiConfigEntry,
    session: Any,
    account: dict[str, Any] | None,
    store: Store,
    stored: dict[str, Any] | None = None,
) -> HuaweiDeviceClient:
    """为一个账号构建设备客户端。

    单条目模式下每个账号有自己的登录态、``dev_mac``（设备按 client 标识维持
    会话，相同标识会互相顶掉）与隧道端口，因此**每个账号一个独立 client**。
    """
    cloud_dev_id = entry.data[CONF_DEVICE_ID]
    product = entry.data.get(CONF_PRODUCT) or DEFAULT_PRODUCT

    if account is None:
        # 设备码模式（单账号）
        saved = (stored or {}).get(TOKEN_STORE_KEY) or entry.data.get(CONF_REFRESH_TOKEN, "")
        cloud = HuaweiCloudClient(session, refresh_token=saved)
        uid = entry.data.get(CONF_UID)
        dev_mac = entry.data.get(CONF_DEV_MAC) or derive_dev_mac(cloud_dev_id)
    else:
        key = _account_key(account)
        acct_store: Store = Store(
            hass, TOKEN_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.{key}"
        )
        stored_acc = hass.data.get(f"{DOMAIN}.{entry.entry_id}.{key}") or {}
        cloud = HuaweiCloudClient(
            session,
            token_provider=_account_token_provider(
                hass, entry, acct_store, stored_acc, account
            ),
        )
        uid = account.get("uid")
        dev_mac = account.get("dev_mac") or derive_dev_mac(f"{cloud_dev_id}|{key}")

    cloud.set_executor(lambda func, *args: hass.async_add_executor_job(func, *args))

    async def provide_credentials() -> DeviceCredentials:
        """完整云链路：取云端令牌 → MQTT startService → 解密设备凭据。"""
        if not uid:
            raise HuaweiDeviceAuthError("配置缺少账号 uid，请重新配置该集成")
        creds = await cloud.async_fetch_device_credentials(
            cloud_dev_id, uid, dev_mac, product
        )
        # 设备码模式下 refresh_token 可能被轮换，持久化新值
        if cloud.refresh_token and cloud.refresh_token != (
            (stored or {}).get(TOKEN_STORE_KEY) or entry.data.get(CONF_REFRESH_TOKEN, "")
        ):
            data = await store.async_load() or {}
            data[TOKEN_STORE_KEY] = cloud.refresh_token
            await store.async_save(data)
        return creds

    return HuaweiDeviceClient(
        session=session,
        host=entry.data.get(CONF_HOST, ""),
        creds_provider=provide_credentials,
    )


def _notify_backup_agents(hass: HomeAssistant) -> None:
    """通知 HA 重新收集备份目标（backup 平台监听器）。"""
    try:
        from .backup import async_notify_backup_agents_changed  # noqa: PLC0415

        async_notify_backup_agents_changed(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("通知备份目标变更失败（不影响集成）", exc_info=True)


async def async_setup_entry(hass: HomeAssistant, entry: HuaweiConfigEntry) -> bool:
    """Set up Huawei Home Storage from a config entry."""
    _migrate_unique_id(hass, entry)
    session = async_create_clientsession(hass, verify_ssl=False)
    store: Store = Store(hass, TOKEN_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    await store.async_load()

    accounts: list[dict[str, Any]] = list(entry.data.get(CONF_ACCOUNTS) or [])
    if not accounts:
        # 自愈：旧版本 config_flow 只写顶层扁平字段、漏写 accounts 的条目。
        healed = _accounts_from_flat_data(entry)
        if healed:
            _LOGGER.warning(
                "条目 %s 缺少 accounts（旧版配置流写入缺陷），已从顶层字段自动补全：%s",
                entry.entry_id,
                _mask_account(healed[0].get("account", "")),
            )
            accounts = healed
            hass.config_entries.async_update_entry(
                entry, data=_write_accounts_compat(entry, accounts)
            )
    method = entry.data.get(CONF_LOGIN_METHOD) or "device_code"
    if method == LOGIN_METHOD_ACCOUNT and not huawei_account.is_available():
        # 登录实现已随本仓库分发（移植自 ha-huawei-smarthome，GPL-3.0），
        # 正常情况恒可用；这里兜底防止移植代码被误删/损坏。
        raise ConfigEntryNotReady(
            "账号登录模块不可用，请删除该条目后用「设备码授权」重新添加"
        )

    # 首个账号作为「主账号」：设备级数据（在线/磁盘/USB/文件浏览）都用它。
    # 管理员账号权限更大（可见完整目录），配置流会把它排在第一位。
    primary = accounts[0] if accounts else None
    client = _build_client(hass, entry, session, primary, store, await store.async_load())

    fast = HuaweiFastCoordinator(hass, entry, client)
    albums = HuaweiAlbumCoordinator(hass, entry, client)
    info = HuaweiInfoCoordinator(hass, entry, client)
    runtime = HuaweiStorageData(
        client=client,
        fast=fast,
        albums=albums,
        title=entry.title,
        is_primary=True,
       info=info,
    )
    runtime.accounts = list(accounts)
    # 主账号的协调器也用**真实账号 key** 索引，避免出现 "" 这个特殊键
    # 导致诊断/实体/媒体源按 key 查不到（曾导致主账号隧道与相册显示为空）。
    primary_key = _account_key(primary) if primary else ""
    runtime.clients = {primary_key: client} if primary_key else {}
    runtime.album_coordinators = {primary_key: albums} if primary_key else {}

    # 其余账号：各自独立客户端（dev_mac / 隧道端口都不同）+ 独立相册协调器
    for account in accounts[1:]:
        key = _account_key(account)
        acc_client = _build_client(hass, entry, session, account, store)
        runtime.clients[key] = acc_client
        runtime.album_coordinators[key] = HuaweiAlbumCoordinator(
            hass, entry, acc_client
        )

    # runtime_data 是官方推荐（类型化 + 随条目释放）；hass.data 保留一份以兼容
    # 媒体源/视图/面板在条目卸载顺序上的访问。
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    # 先把 UI 与接口注册好：首次云端刷新（MQTT startService 等）可能偏慢，
    # 若排在后面，面板与状态接口会长时间不可用。
    async_register_views(hass)
    async_register_websocket(hass)
    await async_register_panel(hass)
    await async_register_services(hass)

    # 快协调器首次刷新会建立设备会话，随后各账号的相册协调器复用各自会话。
    # 快协调器失败 = 设备真的连不上，整个条目应当重试。
    await fast.async_config_entry_first_refresh()

    # 低频信息协调器（固件/硬件/Samba/网络/健康/统计）：失败不影响核心功能。
    if info is not None:
        try:
            await info.async_config_entry_first_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("设备信息拉取失败（不影响其它功能）: %s", err)

    # 各账号的相册协调器：彼此独立，任何一个失败都不影响其它账号，
    # 也不影响设备级实体（磁盘/在线/USB/文件空间）。
    for key, coord in runtime.album_coordinators.items():
        try:
            await coord.async_config_entry_first_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("账号 %s 相册统计拉取失败（不影响其它功能）: %s", key, err)

    # 主设备（按序列号）必须先于账号子设备注册，账号/盘位实体才能挂上去
    runtime.main_device_id = _async_register_main_device(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 清理「已移除账号」遗留的设备节点（必须在平台转发之后，实体已注册完）。
    _prune_stale_account_devices(hass, entry, accounts)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # 备份目标新增一个 → 让 HA 重新收集（实现 backup 平台监听器时才有效）
    _notify_backup_agents(hass)

    return True


@callback
def _prune_stale_account_devices(
    hass: HomeAssistant, entry: HuaweiConfigEntry, accounts: list[dict[str, Any]]
) -> None:
    """删除不再属于本条目任何账号的子设备节点（连带其实体）。

    ⚠️ 用户 2026-10-06 报「删除账号设备不会移除」的根因：
    移除账号只改了 ``entry.data["accounts"]``，但设备注册表里的
    ``<主标识>@<账号key>`` 节点是**上次 setup 时注册的**，HA 不会自动回收——
    集成必须自己声明「哪些设备还在」。

    HA 的机制（``helpers/device_registry.py`` + ``components/config/device_registry.py``）：
    只有当用户在 UI 上**手动**点删除、且集成实现了
    ``async_remove_config_entry_device`` 时才会走那条路；而账号是从配置流里
    移除的，用户根本不会走到「设备」页手动删，所以必须在这里主动清理。

    做法与 core 的 ``hyperion`` 一致：先算出「当前应该存在的 identifier 集合」，
    再把条目下不属于该集合的设备节点删掉。

    本函数同时回收**旧的盘位子设备** ``<主标识>@disk:<SN>``：
    盘位传感器已改为直接挂主设备（见 ``sensor._slot_entities``），
    这些节点不再由任何实体使用，留在注册表里就是永久僵尸。
    """
    from homeassistant.helpers import device_registry as dr

    main_id, _ = main_device_identifier(entry)

    # 应保留的账号子设备标识
    keep: set[str] = {main_id}
    for account in accounts:
        key = _account_key(account)
        if key:
            keep.add(f"{main_id}@{key}")

    registry = dr.async_get(hass)
    removed: list[str] = []

    for device_entry in dr.async_entries_for_config_entry(registry, entry.entry_id):
        ours = [
            str(item[1]) for item in device_entry.identifiers if item[0] == DOMAIN
        ]
        if not ours:
            # 不是本集成的设备（同条目下可能挂别的集成），不碰
            continue
        # 只保留「主设备」与「在册账号子设备」；``@disk:`` 节点已废弃，一并回收。
        if any(ident in keep for ident in ours):
            continue
        registry.async_remove_device(device_entry.id)
        removed.append(device_entry.name or device_entry.id)

    if removed:
        _LOGGER.info(
            "已清理 %d 个不再对应任何账号/盘位的设备节点：%s",
            len(removed),
            "、".join(removed),
        )


def _is_primary_entry(hass: HomeAssistant, entry: HuaweiConfigEntry) -> bool:
    """本条目是否是该物理设备的**主条目**（entry_id 最小者）。

    仅用于诊断与将来「账号级 vs 设备级」的分流判断；**实体去重本身不依赖它**
    —— 设备级实体的 unique_id 挂在物理设备序列号上，HA 注册表天然去重。
    """
    identifier, _ = main_device_identifier(entry)
    siblings = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.domain == DOMAIN
        and main_device_identifier(e)[0] == identifier
        and not e.disabled_by
    ]
    return not siblings or entry.entry_id == min(e.entry_id for e in siblings)


def _async_register_main_device(hass: HomeAssistant, entry: HuaweiConfigEntry) -> str | None:
    """注册「以物理设备为条目」的主设备节点，返回其 device_id。

    同一台设备被多个华为账号接入时，第二个配置条目**复用**已存在的主设备
    （HA 的 ``async_get_or_create`` 会因 config_entry_id 不同而新建一条重复
    设备），这里显式查一次并复用。
    """
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    identifier, _ = main_device_identifier(entry)

    # 跨条目查已有主设备（同一物理设备被多账号接入时复用，避免 HA 因
    # config_entry_id 不同而新建重复设备）。用 entity.find_main_device 统一
    # 走新 API，避免 async_get_device 的弃用警告（2027.8.0 移除）。
    existing = find_main_device(registry, identifier)
    if existing is not None:
        _LOGGER.debug("复用已有主设备: %s（%s）", existing.name, existing.id)
        return existing.id

    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **main_device_info(entry),
    )
    _LOGGER.debug("主设备已注册: %s（%s）", device.name, device.identifiers)
    return device.id


async def async_unload_entry(hass: HomeAssistant, entry: HuaweiConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            async_unregister_views(hass)
            await async_unregister_panel(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: HuaweiConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: HuaweiConfigEntry,
    device_entry: Any,
) -> bool:
    """支持在集成里删除设备（HA 要求集成显式声明）。

    没有这个回调时，用户在「设备与服务 → 设备」里删除家庭存储会报
    ``Config entry does not support device removal``，也会导致上一版遗留的
    重复/过期设备节点无法清理。

    本集成创建的设备节点只有两类（identifier 全部以主标识为前缀）：
    主设备、``<主标识>@<账号>``，所以按前缀判定归属。

    （盘位曾各自建 ``<主标识>@disk:<硬盘SN>`` 节点，现已改为传感器直接挂主设备；
    这些旧节点会在 setup 时由 ``_prune_stale_account_devices`` 回收，
    这里仍按 ``@`` 前缀放行以便用户手动清理残留。）
    """
    domain, identifier = next(iter(device_entry.identifiers), (None, None))
    if domain != DOMAIN:
        return False

    main_id, _ = main_device_identifier(entry)
    owned = identifier == main_id or str(identifier).startswith(f"{main_id}@")
    if owned:
        return True
    _LOGGER.debug("设备 %s 不属于当前配置条目 %s，忽略删除", identifier, entry.entry_id)
    return False
