"""华为账号密码登录（不跳浏览器）。

**自包含实现**：登录流程（CAS 账号密码 + 可选挑战码 → ``service_token`` →
静默 OAuth 换 ``oauth_access_token``）已随本仓库分发（移植自
``ha-huawei-smarthome``，GPL-3.0，见 :mod:`.auth`），**不再依赖 huawei_smarthome
集成**。

2026-10-06 之前本模块通过 ``import custom_components.huawei_smarthome.*`` 复用
其实现，属于运行时硬耦合：对方未安装/改名/升级不兼容时，本集成直接
``setup_error`` 且无法自愈。移植后账号密码登录与设备码授权两条路径都完全独立。

换出的 ``oauth_access_token`` 与设备码流程拿到的 token 用途相同 —— 都用于
``smarthome.hicloud.com`` 的设备列表 / message-center / startService。
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: 保留旧名字，仅为兼容既有引用（现已无外部依赖）
SMARTHOME_DOMAIN = "huawei_smarthome"


class HuaweiAccountError(Exception):
    """账号登录相关错误。"""


def is_available() -> bool:
    """账号密码登录是否可用。

    登录实现已内置，恒为 True。保留此函数是为了兼容既有调用方
    （配置流 / __init__ 仍按它决定走账号模式还是设备码）。
    """
    return True


def _new_provider(hass: Any, identity: dict[str, Any]) -> Any:
    from .auth.huawei import HuaweiSmartHomeAuthProvider

    return HuaweiSmartHomeAuthProvider(
        device_id=str(identity["device_id"]),
        device_name=str(identity["device_name"]),
        pushtmid=str(identity["pushtmid"]),
        identity_fingerprint=str(identity["identity_fingerprint"]),
    )


async def async_current_identity(hass: Any, account: str) -> dict[str, Any]:
    """读取本集成当前为该账号持有的客户端身份（device_id / pushtmid / 指纹）。

    ⚠️ 这是**唯一权威来源**。切勿再从会话快照里的 device_id 反推身份：
    0.8.x 曾与上游 domain=huawei_smarthome 集成共用同一个身份文件，
    导致两边 device_id 完全相同、会话互相顶掉（2026-10-06 用户报告
    「huawei home smart 突然需要重新登录」）。改用独立命名空间后，
    历史条目里缓存的旧 device_id 会与新身份不一致，必须由本函数纠正。
    """
    from .storage.identity import ClientIdentityStore

    try:
        return await ClientIdentityStore(hass).async_get_or_create(account)
    except Exception as err:  # noqa: BLE001
        raise HuaweiAccountError(f"创建账号身份失败: {err}") from err


async def async_create_provider(hass: Any, account: str) -> Any:
    """按账号创建登录 provider（含设备指纹），由调用方持有。

    不放在 hass.data 里全局共享：同一账号并发添加多台设备时，
    共享状态会被后一个流程覆盖，导致前一个流程的挑战码失效。
    """
    return _new_provider(hass, await async_current_identity(hass, account))


def rebuild_session(hass: Any, stored: dict[str, Any], account: str) -> Any:
    """用持久化的字段重建会话（HA 重启后继续用，无需重新登录）。"""
    from .domain.models import AuthSession

    return AuthSession(
        account=stored.get("account") or account,
        user_id=stored.get("user_id") or "",
        service_token=stored.get("service_token") or "",
        oauth_access_token=stored.get("oauth_access_token"),
        oauth_expires_at=None,
        device_id=stored.get("device_id") or "",
        device_name=stored.get("device_name") or "huawei-smarthome",
        pushtmid=stored.get("pushtmid"),
        identity_fingerprint=stored.get("identity_fingerprint"),
    )


def session_to_dict(session: Any) -> dict[str, Any]:
    """只保留重建与续期所需的字段。"""
    return {
        "account": getattr(session, "account", None),
        "user_id": getattr(session, "user_id", None),
        "service_token": getattr(session, "service_token", None),
        "oauth_access_token": getattr(session, "oauth_access_token", None),
        "device_id": getattr(session, "device_id", None),
        "device_name": getattr(session, "device_name", None),
        "pushtmid": getattr(session, "pushtmid", None),
        "identity_fingerprint": getattr(session, "identity_fingerprint", None),
    }


def access_token_of(session: Any) -> str | None:
    """取用于 ``Authorization: Bearer`` 的 token。

    优先 ``oauth_access_token``（与本集成设备码流程拿到的 token 同一类，
    请求形状已实测可用）；退回 ``hms_access_token``。
    """
    for attr in ("oauth_access_token", "hms_access_token"):
        value = getattr(session, attr, None)
        if value:
            return str(value)
    return None


async def async_begin_login(provider: Any, account: str, password: str) -> Any:
    """开始账号密码登录。返回 ``LoginStart``（含 challenge 或 session）。"""
    try:
        return await provider.async_begin_login(account, password)
    except Exception as err:  # noqa: BLE001
        raise HuaweiAccountError(f"账号登录失败: {err}") from err


async def async_select_challenge_channel(provider: Any, channel: Any) -> Any:
    """选择验证码投递渠道并请华为下发（短信渠道会真正发短信）。"""
    if provider is None:
        raise HuaweiAccountError("没有待完成的登录挑战，请重新开始配置")
    try:
        return await provider.async_select_challenge_channel(channel)
    except Exception as err:  # noqa: BLE001
        raise HuaweiAccountError(f"验证码下发失败: {err}") from err


async def async_complete_challenge(provider: Any, code: str) -> Any:
    """提交挑战码（在另一台华为设备上查看）。"""
    if provider is None:
        raise HuaweiAccountError("没有待完成的登录挑战，请重新开始配置")
    try:
        return await provider.async_complete_challenge(code)
    except Exception as err:  # noqa: BLE001
        raise HuaweiAccountError(f"挑战码校验失败: {err}") from err


async def async_refresh_session(hass: Any, session: Any) -> Any:
    """用 service_token 静默续期 oauth_access_token。

    ⚠️ 身份必须取自 identity store（``async_current_identity``），**不能**用
    ``session.device_id``：历史条目的会话快照可能还存着 0.8.x 时代与上游
    共享的 device_id，照用会让本集成继续以「上游客户端身份」发请求，
    令两边的会话持续互相顶掉（2026-10-06 故障根因）。
    续期请求里携带的 device_id 与 session 记录的不一致是安全的——这里只
    换客户端标识，service_token 仍属同一账号。
    """
    if not is_available():
        raise HuaweiAccountError("账号登录实现不可用，请改用设备码授权")
    account = str(getattr(session, "account", "") or "")
    if not account:
        raise HuaweiAccountError("会话缺少账号信息，无法续期")
    identity = await async_current_identity(hass, account)
    provider = _new_provider(hass, identity)
    session = replace(
        session,
        device_id=str(identity["device_id"]),
        device_name=str(identity["device_name"]),
        pushtmid=str(identity["pushtmid"]),
        identity_fingerprint=str(identity["identity_fingerprint"]),
    )
    try:
        return await provider.async_refresh_oauth(session)
    except Exception as err:  # noqa: BLE001
        raise HuaweiAccountError(f"会话续期失败: {err}") from err
