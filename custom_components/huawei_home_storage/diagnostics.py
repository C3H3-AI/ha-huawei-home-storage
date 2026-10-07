"""Diagnostics support for Huawei Home Storage.

定位问题的第一现场。2026-10-05 的「第二个账号 heartBeat 恒 401」就是靠
``tunnel`` 这一段发现的：设备按 client 会话分配**独立隧道端口**（第一个账号
8471/8472，第二个账号 8431/8432），而集成当时硬编码了 8471。有了这里的
``https_url`` / ``data_https_url``，看一眼就能定位。
"""
from __future__ import annotations

import re
import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT,
    CONF_ACCOUNTS,
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
    DOMAIN,
    SCAN_INTERVAL_FAST_MINUTES,
    SCAN_INTERVAL_SLOW_MINUTES,
)

TO_REDACT = {
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SMART_SESSION,
    "token",
    "session",
    "dataToken",
    "dataSession",
    "service_token",
    "oauth_access_token",
    "pushtmid",
    "identity_fingerprint",
    "user_id",
    CONF_UID,
    CONF_DEVICE_ID,
}


def _mask(value: str | None) -> str:
    """账号类字符串脱敏：保留前 3 后 4 位。

    ⚠️ 短值也必须打码。早先的实现是 ``value if len(value) <= 7 else ...``，
    对 ≤7 字符的值**原样返回** —— 短邮箱/短账号等于完全没脱敏。
    """
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 7:
        return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
    return f"{value[:3]}****{value[-4:]}"


def _mask_account_fields(data: dict[str, Any]) -> dict[str, Any]:
    """把 ``entry.data`` 里的账号类字段统一打码（保留可读的掩码形式）。

    **为什么不能只靠 TO_REDACT**：白名单是按**字段名**匹配的，只能挡住已经
    想到的字段。实测就漏了 ``accounts[*].key`` / ``accounts[*].account``，
    于是 3 个账号手机号原样进了诊断包（而同一格里的 password/uid 都脱敏了）。

    这里按**语义**处理 account / accounts[*] 两组字段，账号用手机号还是邮箱
    登录都会被打码，且保留 ``137****6363`` 这种可读形式（便于判断"是哪个账号
    出问题"），而不是一律变成 ``**REDACTED**`` 失去排查价值。
    """
    out = dict(data)
    if out.get(CONF_ACCOUNT):
        out[CONF_ACCOUNT] = _mask(str(out[CONF_ACCOUNT]))
    accounts = out.get(CONF_ACCOUNTS)
    if isinstance(accounts, list):
        cleaned = []
        for item in accounts:
            if not isinstance(item, dict):
                cleaned.append(item)
                continue
            item = dict(item)
            for field in ("key", CONF_ACCOUNT):
                if item.get(field):
                    item[field] = _mask(str(item[field]))
            cleaned.append(item)
        out[CONF_ACCOUNTS] = cleaned
    return out


_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")


def _scrub_phones(obj: Any) -> Any:
    """按**值特征**兜底：递归把任何 11 位手机号打码。

    TO_REDACT（字段名）和 _mask_account_fields（语义）都是"已知位置"的防守。
    这一层不看字段名、只看内容，将来新增字段忘了加白名单也不会漏手机号。
    """
    if isinstance(obj, dict):
        return {k: _scrub_phones(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_phones(v) for v in obj]
    if isinstance(obj, str):
        return _PHONE_RE.sub(lambda m: _mask(m.group(1)), obj)
    return obj


def _tunnel(url: str | None) -> str:
    """隧道地址：只保留 host 与端口（端口是关键信息，IP 属于用户内网可保留）。"""
    if not url:
        return ""
    return url.split("//", 1)[-1].rstrip("/")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Any
) -> dict[str, Any]:
    """返回配置条目诊断信息。

    运行期数据取自 ``entry.runtime_data``（HA 官方推荐）；退化时回退到
    ``hass.data``——诊断端点在不同 HA 版本下拿到的 hass 引用不一定与
    运行时一致，``runtime_data`` 更可靠。
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None or not hasattr(runtime, "fast"):
        runtime = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if runtime is None or not hasattr(runtime, "fast"):
        return {"error": "条目尚未加载", "entry_id": entry.entry_id}

    client = runtime.client
    creds = client.credentials

    fast_data = dict(runtime.fast.data or {})
    album_data = dict(runtime.albums.data or {})
    disk = fast_data.get("disk") or {}

    # 多账号：各自的隧道与相册统计（排查「哪个账号出问题」的第一现场）
    accounts: list[dict[str, Any]] = []
    for account in getattr(runtime, "accounts", None) or []:
        key = str(account.get("key") or account.get("account") or "")
        client = (getattr(runtime, "clients", None) or {}).get(key)
        acc_creds = client.credentials if client else None
        coord = (getattr(runtime, "album_coordinators", None) or {}).get(key)
        accounts.append(
            {
                # key 是账号手机号，导出前必须打码。
                # 注意：上面查 runtime.clients/album_coordinators 用的是**未打码**的
                # key，只有这里的输出才打码 —— 打码后的值查不到任何东西。
                "key": _mask(key),
                "account": _mask(account.get("account")),
                "device_user": account.get("user") or "",
                "tunnel": _tunnel(acc_creds.https_url if acc_creds else None),
                "data_tunnel": _tunnel(acc_creds.data_https_url if acc_creds else None),
                "albums_last_update_success": (
                    coord.last_update_success if coord else None
                ),
                "albums_error": (
                    getattr(coord, "last_error", None) if coord else None
                ),
                "albums_counts": (
                    (coord.data or {}).get("counts", {}) if coord else {}
                ),
            }
        )
    payload = {
        # 条目本身（脱敏）
        "entry": async_redact_data(
            {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "version": entry.version,
                # 先按语义打码 account/accounts[*]，再过白名单
                "data": _mask_account_fields(
                    async_redact_data(dict(entry.data), TO_REDACT)
                ),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        # ★ 隧道与会话：排查 401 / 端口冲突的第一现场
        "tunnel": {
            "https_url": _tunnel(creds.https_url if creds else None),
            "data_https_url": _tunnel(creds.data_https_url if creds else None),
            "control_port_used": (client._control_url or "").split(":")[-1] or None,  # noqa: SLF001
            "data_port_used": (client._data_url or "").split(":")[-1] or None,  # noqa: SLF001
            "has_credentials": creds is not None,
            "credentials_obtained_at": (
                round(time_delta(creds.obtained_at), 0) if creds else None
            ),
        },
        "identity": {
            "dev_mac": entry.data.get(CONF_DEV_MAC),
            "product": entry.data.get(CONF_PRODUCT),
            "device_mac": entry.data.get(CONF_DEVICE_MAC),
            "device_sn": entry.data.get(CONF_DEVICE_SN),
            "device_model": entry.data.get(CONF_DEVICE_MODEL),
            "host": entry.data.get(CONF_HOST),
            "login_method": entry.data.get(CONF_LOGIN_METHOD),
            "account": _mask(entry.data.get(CONF_ACCOUNT)),
        },
        "coordinators": {
            "fast": {
                "last_update_success": runtime.fast.last_update_success,
                "update_interval_minutes": SCAN_INTERVAL_FAST_MINUTES,
                "last_exception": str(runtime.fast.last_exception),
            },
            "albums": {
                "last_update_success": runtime.albums.last_update_success,
                "update_interval_minutes": SCAN_INTERVAL_SLOW_MINUTES,
                "last_exception": str(runtime.albums.last_exception),
            },
        },
        # 设备状态快照
        "device": {
            "online": fast_data.get("online"),
            "disk": {
                "slots": [
                    {
                        "slot": s.get("slot"),
                        "isExist": s.get("isExist"),
                        "sn": s.get("sn"),
                        "totalSize_mb": s.get("totalSize"),
                        "usedSize_mb": s.get("usedSize"),
                        "availableState": s.get("availableState"),
                    }
                    for s in disk.get("diskChangeInfo") or []
                ],
            },
            "user_data_mb": fast_data.get("user_data"),
            "usb": {
                "status": (fast_data.get("usb") or {}).get("status"),
                "devices": len((fast_data.get("usb") or {}).get("info") or []),
            },
            "device_users": [
                # 不导出头像 URL（含用户标识的签名链接）
                {
                    "nick": u.get("nick"),
                    "level": u.get("level"),
                    "state": u.get("state"),
                    "usage_mb": u.get("usage"),
                }
                for u in (fast_data.get("device_users") or [])
            ],
        },
        # 相册统计
        "albums": {
            "counts": album_data.get("counts"),
            "total": len(album_data.get("albums", {}).get(0, [])),
        },
        "accounts": accounts,
    }
    # ★ 最后一道：按值特征兜底，扫掉任何残留的 11 位手机号。
    # 不看字段名，所以将来新增字段忘记加白名单也不会漏 ——
    # 按字段名枚举的防线天然有遗漏，必须有一层按内容兜底。
    return _scrub_phones(payload)


def time_delta(timestamp: float | None) -> float:
    """凭据获取至今的秒数。"""
    return time.time() - timestamp if timestamp else 0.0
