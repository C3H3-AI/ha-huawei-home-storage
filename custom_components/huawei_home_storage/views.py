"""受认证保护的图片代理视图。

前端浏览器无法携带设备所需的 ``Token`` / ``Cookie`` 头，因此由 HA 侧代理转发到
设备的 8472 数据通道。对外 URL 形如::

    /api/huawei_home_storage/image/<entry_id>/raw/picture/thumb/0001/18242_x.jpg

其中路径部分为设备返回的原始路径（去掉前导 ``/``）。
"""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_MAC,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_HOST,
    CONF_LOGIN_METHOD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

URL = "/api/huawei_home_storage/image/{entry_id}/{name}/{path:.*}"
URL_PREFIX = "/api/huawei_home_storage/image"
NAME = "api:huawei_home_storage:image"
STATUS_URL = "/api/huawei_home_storage/status"
STATUS_NAME = "api:huawei_home_storage:status"
CACHE_SECONDS = 3600
VIEWS_FLAG = f"{DOMAIN}_views_registered"


def build_image_url(
    entry_id: str, device_path: str, name: str = "raw", account: str = ""
) -> str:
    """构造前端可用的代理 URL。

    多账号时不同账号的**隧道端口不同**，图片必须经对应账号的会话取，
    因此账号 key 放在路径段里（``.../image/<entry>/<account>/raw/<路径>``）。
    """
    seg = f"{entry_id}/{account}" if account else entry_id
    return f"{URL_PREFIX}/{seg}/{name}/{device_path.lstrip('/')}"


def _content_type(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".heic", ".heif")):
        return "image/heic"
    if lower.endswith((".mp4", ".mov")):
        return "video/mp4"
    return "image/jpeg"


class HuaweiStorageImageView(HomeAssistantView):
    """把设备路径代理成浏览器可直接访问的 URL。"""

    url = URL
    name = NAME
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, name: str, path: str
    ) -> web.StreamResponse:
        return await _serve_image(request, entry_id, name, path, "")


class HuaweiStorageAccountImageView(HomeAssistantView):
    """按账号取图（多账号下隧道端口不同）。"""

    url = "/api/huawei_home_storage/image/{entry_id}/acct/{account}/{name}/{path:.*}"
    name = "api:huawei_home_storage:account_image"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        account: str,
        name: str,
        path: str,
    ) -> web.StreamResponse:
        return await _serve_image(request, entry_id, name, path, account)


async def _serve_image(
    request: web.Request, entry_id: str, name: str, path: str, account: str
) -> web.StreamResponse:
    """按（可选）账号取图。"""
    runtime = request.app["hass"].data.get(DOMAIN, {}).get(entry_id)
    if runtime is None:
        raise web.HTTPNotFound()
    clients = getattr(runtime, "clients", None) or {}
    client = clients.get(account) or runtime.client
    device_path = "/" + path.lstrip("/")
    # 取图的 category 由**路径**决定（实测 2026-10-08）：
    #   /picture/...                相册域     → category=""
    #   /file/.File_Syssvc/thumb/…  共享空间   → category="public"（否则 403/404）
    category = "public" if device_path.startswith("/file/") else ""
    image = await client.async_fetch_image(device_path, category=category)
    if not image:
        raise web.HTTPNotFound()
    return web.Response(
        body=image,
        content_type=_content_type(path),
        headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"},
    )


def _info(runtime: Any) -> dict[str, Any]:
    """低频信息协调器的数据；未就绪时返回空 dict。"""
    coord = getattr(runtime, "info", None)
    data = getattr(coord, "data", None) if coord is not None else None
    return data if isinstance(data, dict) else {}


def _hardware(runtime: Any) -> dict[str, Any]:
    """设备硬件与运行态。

    实测响应把数据放在 ``body`` 下，字段是驼峰：
      device_info  -> {SerialNumber, SoftwareVersion, CpuCores, CpuName, DeviceName, ...}
      device_status-> {Cpuusage, Cputemp, MemTotal, MemFree}
      online_state -> {UpgradeState, ...}（升级状态）
    """
    info = _info(runtime)
    # 注意：device_status(CPU/温度/内存) 在**快协调器**里，不在低频 info 协调器。
    fast = getattr(getattr(runtime, "fast", None), "data", None)
    fast = fast if isinstance(fast, dict) else {}
    dev = (info.get("device_info") or {}).get("body") or {}
    st = (fast.get("device_status") or {}).get("body") or (info.get("device_status") or {}).get("body") or {}
    ol = (info.get("online_state") or {}).get("body") or info.get("online_state") or {}
    mem_total, mem_free = st.get("MemTotal"), st.get("MemFree")
    used = None
    if isinstance(mem_total, (int, float)) and isinstance(mem_free, (int, float)):
        used = int(mem_total) - int(mem_free)
    return {
        "firmware": dev.get("SoftwareVersion") or "",
        "cpu_model": dev.get("CpuName") or "",
        "cpu_cores": dev.get("CpuCores"),
        "cpu_usage": st.get("Cpuusage"),
        "cpu_temperature": st.get("Cputemp"),
        # 设备上报单位是 KB（实测 MemTotal=4000000 -> 与传感器 4096000000 B 一致）
        "memory_total": _kb_to_bytes(mem_total),
        "memory_used": _kb_to_bytes(used) if used is not None else None,
        "upgrade_state": ol.get("UpgradeState") or ol.get("upgradeState"),
    }


def _kb_to_bytes(value: Any) -> int | None:
    """设备内存单位是 KB，转成字节与传感器口径一致。

    实测：``device_status`` 的 ``MemTotal=4000000``，传感器上报 4096000000 B
    （= 4000000 * 1024），所以这里是 KB -> B，不能当成 MB。
    """
    try:
        return int(value) * 1024
    except (TypeError, ValueError):
        return None


def _network(runtime: Any) -> dict[str, str]:
    wan = _info(runtime).get("wan_info") or {}
    body = wan.get("body") or wan
    return {
        "ipv4": body.get("IPv4Addr") or "",
        "ipv6": body.get("IPv6Addr2") or body.get("IPv6Addr1") or "",
    }


def _health(runtime: Any) -> dict[str, Any]:
    info = _info(runtime)
    err = (info.get("dev_err") or {}).get("data") or info.get("dev_err") or {}
    rep = (info.get("repair_mode") or {}).get("data") or info.get("repair_mode") or {}
    ops = info.get("operation_devices") or {}
    devices = ops.get("operationDevice")
    return {
        "error_code": err.get("errorCode"),
        "repair_mode": rep.get("mode"),
        "client_devices": len(devices) if isinstance(devices, list) else None,
    }


def _samba(runtime: Any) -> dict[str, bool]:
    info = _info(runtime)
    return {
        "public": bool((info.get("samba_public") or {}).get("AnonymousEnable")),
        "user": bool((info.get("samba_user") or {}).get("Enable")),
    }


def _auto_upgrade(runtime: Any) -> dict[str, Any]:
    au = _info(runtime).get("auto_upgrade") or {}
    start, end = au.get("StartTime"), au.get("EndTime")
    return {
        "enabled": bool(au.get("Enable")),
        "window": f"{start}-{end}" if start and end else "",
    }


def _buttons(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    """找出本条目的设备按钮实体 ID（按 unique_id 后缀匹配）。"""
    try:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        out: dict[str, str] = {}
        for entity in registry.entities.values():
            if entity.platform != DOMAIN or entity.domain != "button":
                continue
            uid = entity.unique_id or ""
            if uid.endswith("_disk_sleep"):
                out["sleep"] = entity.entity_id
            elif uid.endswith("_usb_plug_out") or uid.endswith("_eject_usb"):
                out["eject"] = entity.entity_id
            elif uid.endswith("_device_reboot") or uid.endswith("_reboot_device"):
                out["reboot"] = entity.entity_id
        return out
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("面板按钮实体查找失败: %s", err)
        return {}


def _counts(runtime: Any, data: dict[str, Any]) -> dict[str, Any]:
    """相册统计 + 低频信息里的文件/插件计数。

    面板要展示「已装插件 / 最近文件 / 全部文件 / 重复照片」，这些不在快协调器
    的 counts 里，需要从低频 info 协调器补进来。
    """
    counts = dict(data.get("counts") or {})
    info = _info(runtime)

    def _len(key: str, field: str) -> int | None:
        raw = info.get(key) or {}
        inner = (raw.get("data") or {}) if isinstance(raw, dict) else {}
        value = inner.get(field) if isinstance(inner, dict) else None
        return len(value) if isinstance(value, list) else None

    plugins = ((info.get("plugins") or {}).get("data") or {}).get("hapInfos")
    counts["installed_plugins"] = len(plugins) if isinstance(plugins, list) else (
        counts.get("installed_plugins") or _len("plugins", "hapInfos"))
    counts["recent_files"] = (counts.get("recent_files")
                              or _len("recent_files", "records"))
    counts["all_files"] = counts.get("all_files") or _len("all_files", "files")
    dup = info.get("dup") or {}
    if isinstance(dup, dict) and isinstance((dup.get("data") or {}), dict):
        counts.setdefault("duplicate_photos", (dup.get("data") or {}).get("dupNum"))
    return counts


def _disk(disk: dict[str, Any]) -> dict[str, Any]:
    """把设备原始的 diskChangeInfo 汇总成面板要的 total/used/free/usage/slots。

    设备单位是 MB，这里统一转字节，与传感器口径一致。
    """
    slots = [s for s in (disk.get("diskChangeInfo") or []) if s.get("isExist")]
    total = used = 0
    for s in slots:
        try:
            total += int(s.get("totalSize") or 0)
            used += int(s.get("usedSize") or 0)
        except (TypeError, ValueError):
            continue
    mb = 1024 * 1024
    total_b, used_b = total * mb, used * mb
    free_b = max(0, total_b - used_b)
    return {
        "total": total_b,
        "used": used_b,
        "free": free_b,
        "usage": round(used / total * 100, 1) if total else None,
        "slots": len(slots) or None,
    }


class HuaweiStorageStatusView(HomeAssistantView):
    """供侧边栏面板读取的汇总状态（JSON）。"""

    url = STATUS_URL
    name = STATUS_NAME
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        entries = hass.data.get(DOMAIN, {}) or {}
        payload = []
        for entry_id, runtime in entries.items():
            data = runtime.data
            creds = runtime.client.credentials
            entry = hass.config_entries.async_get_entry(entry_id)
            cfg = entry.data if entry else {}
            accounts = getattr(runtime, "accounts", None) or []
            payload.append(
                {
                    "entry_id": entry_id,
                    "title": runtime.title,
                    "online": bool(data.get("online")),
                    "counts": _counts(runtime, data),
                    "disk": _disk(data.get("disk") or {}),
                    "user_data": data.get("user_data") or {},
                    # 面板展示：USB 接入；用户**只给数量**（uid/昵称属敏感信息，不下发前端）
                    "usb": data.get("usb") or {},
                    "device_users": [{}] * len(data.get("device_users") or []),
                    "credentials": creds.to_dict() if creds else None,
                    "last_update_success": runtime.last_update_success,
                    # 多账号：每个账号的隧道与相册统计
                    "accounts": [
                        {
                            "key": a.get("key"),
                            "account": a.get("account") or "",
                            "user": a.get("user") or "",
                            "tunnel": (
                                runtime.clients.get(str(a.get("key")))
                                .credentials.https_url
                                if runtime.clients.get(str(a.get("key")))
                                and runtime.clients[str(a.get("key"))].credentials
                                else ""
                            ),
                            "counts": runtime.counts_of_account(str(a.get("key"))),
                        }
                        for a in accounts
                    ],
                    # 以下用于面板展示（MAC 不放进设备注册，避免与路由器等集成冲突）
                    "device_mac": cfg.get(CONF_DEVICE_MAC) or "",
                    "device_sn": cfg.get(CONF_DEVICE_SN) or "",
                    "device_model": cfg.get(CONF_DEVICE_MODEL) or "",
                    "login_method": cfg.get(CONF_LOGIN_METHOD) or "",
                    "account": cfg.get(CONF_ACCOUNT) or "",
                    "host": cfg.get(CONF_HOST) or "",
                    # 面板扩展：低频信息协调器的数据（固件/CPU/内存/网络/健康/Samba/插件）
                    "hardware": _hardware(runtime),
                    "network": _network(runtime),
                    "health": _health(runtime),
                    "samba": _samba(runtime),
                    "auto_upgrade": _auto_upgrade(runtime),
                    # 面板操作：本条目的设备按钮实体 ID（重启/休眠/弹出 USB）
                    "buttons": _buttons(hass, entry_id),
                }
            )
        return web.json_response({"entries": payload})


class HuaweiStorageFilesView(HomeAssistantView):
    """文件空间目录浏览（供面板照片/文件页使用）。

    GET /api/huawei_home_storage/files/<entry_id>?path=/file/xxx/
    返回 {files: [...], count: N}，文件条目含 thumb（缩略图路径）。
    """

    url = "/api/huawei_home_storage/files/{entry_id}"
    name = "api:huawei_home_storage:files"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        hass = request.app["hass"]
        runtime = hass.data.get(DOMAIN, {}).get(entry_id)
        if runtime is None:
            raise web.HTTPNotFound()
        path = request.query.get("path") or "/file/"
        try:
            result = await runtime.client.async_list_files(path)
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": str(err)}, status=502)
        files = []
        for f in result.get("files") or []:
            # 只保留浏览需要的字段；thumb 走图片代理
            entry = {
                "name": f.get("name"),
                "type": f.get("type"),          # 2/4/6=目录, 8=文件
                "mime": f.get("mime"),
                "size": f.get("size"),
                "mtime": f.get("mtime"),
                "thumb": f.get("thumb") or "",
            }
            if f.get("thumb"):
                entry["thumbUrl"] = (
                    f"/api/huawei_home_storage/image/{entry_id}/thumb/"
                    + (f["thumb"] or "").lstrip("/")
                )
            files.append(entry)
        return web.json_response({"path": path, "count": len(files), "files": files})



def async_register_views(hass: HomeAssistant) -> None:
    if hass.data.get(VIEWS_FLAG):
        return
    hass.http.register_view(HuaweiStorageImageView())
    hass.http.register_view(HuaweiStorageAccountImageView())
    hass.http.register_view(HuaweiStorageStatusView())
    hass.http.register_view(HuaweiStorageFilesView())
    hass.data[VIEWS_FLAG] = True


def async_unregister_views(hass: HomeAssistant) -> None:
    hass.data[VIEWS_FLAG] = False
