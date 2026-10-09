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

    CONF_BACKUP_DIR,
    CONF_BACKUP_SPACE,
    DEFAULT_BACKUP_DIR,
)

from .transfer import ensure_dir, upload_stream

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
    # 取图的 category 不能按路径硬编码。实测 2026-10-08：
    #   * 文件空间缩略图 `/file/.File_Syssvc/thumb/…`
    #     → category="" 能取到（20976B），category="public" 反而取不到
    #   * 相册域 `/picture/…` → category="" 即可
    # 此前按路径前缀一律传 "public"，导致文件空间缩略图 404。
    # 改为**按序尝试、取到即用**，不猜单一答案。
    image = None
    for category in ("", "public"):
        image = await client.async_fetch_image(device_path, category=category)
        if image:
            break
    if not image:
        raise web.HTTPNotFound()
    return web.Response(
        body=image,
        content_type=_content_type(path),
        headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"},
    )


def mask_sn(value: str | None) -> str:
    """设备序列号脱敏：保留前 4 与后 4。

    ⚠️ 序列号是仓库隐私红线，任何下发到前端/日志/诊断的输出都必须过这里。
    """
    text = str(value or "")
    if not text:
        return ""
    return text if len(text) <= 8 else text[:4] + "****" + text[-4:]


def mask_account(value: str) -> str:
    """账号脱敏：手机号保留前 3 后 4；邮箱保留首字符与域名。"""
    text = str(value or "")
    if not text:
        return "账号"
    if "@" in text:
        name, _, domain = text.partition("@")
        return (name[:1] + "***@" + domain) if domain else name[:1] + "***"
    if len(text) > 7:
        return text[:3] + "****" + text[-4:]
    return text[:1] + "***"


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
                    # ⚠️ 整个凭据对象含**设备序列号**与其它凭据字段，
                    # 实测把完整序列号 A4DEQ…0588 直接下发给了前端。
                    # 面板只需要「有没有凭据」这一点信息，这里不再下发明细。
                    "credentials": bool(creds),
                    "last_update_success": runtime.last_update_success,
                    # 多账号：每个账号的隧道与相册统计
                    "accounts": [
                        {
                            # ⚠️ 这些字段**原样下发会让手机号进日志/诊断/前端**。
                            # label 早已脱敏，但同一层的 key/account/uid 漏了 ——
                            # 实测 status 接口直接返回完整手机号 13736776363。
                            # 面板只需要一个稳定的账号标识用于切换，脱敏值同样唯一。
                            "key": mask_account(a.get("key")),
                            "account": mask_account(a.get("account")),
                            "user": a.get("user") or "",
                            "uid": mask_account(a.get("uid")),
                            # 面板用：脱敏显示名 + 是否默认账号
                            "label": mask_account(a.get("account") or a.get("user") or "账号"),
                            "is_primary": idx == 0,
                            "tunnel": (
                                runtime.clients.get(str(a.get("key")))
                                .credentials.https_url
                                if runtime.clients.get(str(a.get("key")))
                                and runtime.clients[str(a.get("key"))].credentials
                                else ""
                            ),
                            "counts": runtime.counts_of_account(str(a.get("key"))),
                        }
                        for idx, a in enumerate(accounts)
                    ],
                    # 以下用于面板展示（MAC 不放进设备注册，避免与路由器等集成冲突）
                    "device_mac": cfg.get(CONF_DEVICE_MAC) or "",
                    # ⚠️ 设备序列号属红线，面板只展示脱敏形式
                    "device_sn": mask_sn(cfg.get(CONF_DEVICE_SN)),
                    "device_model": cfg.get(CONF_DEVICE_MODEL) or "",
                    # 面板「配置」视图展示备份目标：读法与 backup.py 的 _opts 一致
                    # （data 与 options 合并、options 优先），用户在 options 里改了
                    # 备份目录后，面板能立刻看到。
                    "backup_dir": (
                        (dict(entry.options or {})).get(CONF_BACKUP_DIR)
                        or cfg.get(CONF_BACKUP_DIR)
                        or DEFAULT_BACKUP_DIR
                    ),
                    "backup_space": (
                        (dict(entry.options or {})).get(CONF_BACKUP_SPACE)
                        or cfg.get(CONF_BACKUP_SPACE)
                        or "user"
                    ),
                    "login_method": cfg.get(CONF_LOGIN_METHOD) or "",
                    "account": mask_account(cfg.get(CONF_ACCOUNT)),
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
    """文件空间目录浏览（供面板「文件」页使用）。

    GET /api/huawei_home_storage/files/<entry_id>?path=/file/xxx/&space=user|public

    ``space`` 区分两个**互相独立**的空间（实测 2026-10-08）：
    ``user`` = 「我的文件」，``public`` = 「共享」——同一路径在两个空间下
    内容不同，共享空间的目录只在 ``public`` 可见。
    """

    url = "/api/huawei_home_storage/files/{entry_id}"
    name = "api:huawei_home_storage:files"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        runtime = _runtime_of(request, entry_id)
        path = request.query.get("path") or "/file/"
        space = request.query.get("space") or "user"
        account = request.query.get("account") or ""
        client = _client_of(runtime, account)
        category = "public" if space == "public" else "user"
        try:
            result = await client.async_list_files(
                path,
                offset=int(request.query.get("offset") or 0),
                limit=int(request.query.get("limit") or 200),
                category=category,
            )
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": str(err)}, status=502)
        files = []
        for f in result.get("files") or []:
            item = {
                "name": f.get("name"),
                "type": f.get("type"),  # 2/4/6=目录, 8=文件
                "mime": f.get("mime"),
                "size": f.get("size"),
                "mtime": f.get("mtime"),
                "thumb": f.get("thumb") or "",
            }
            if f.get("thumb"):
                item["thumbUrl"] = build_image_url(
                    entry_id, f["thumb"], name="thumb", account=account
                )
            files.append(item)
        return web.json_response(
            {"path": path, "space": space, "count": len(files), "files": files}
        )


# 相册按业务含义分组（面板「相册」页按组展示）
_ALBUM_GROUPS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("smart", "智能分类", (1, 2)),
    ("face", "人物", (23,)),
    ("place", "地点", (22,)),
    ("scene", "场景", (24,)),
    ("user", "我的相册", (6,)),
)


def _runtime_of(request: web.Request, entry_id: str) -> Any:
    runtime = request.app["hass"].data.get(DOMAIN, {}).get(entry_id)
    if runtime is None:
        raise web.HTTPNotFound()
    return runtime


def _primary_key(runtime: Any) -> str:
    """主账号 key（未指定账号时的默认视角）。"""
    from .entity import _account_key  # noqa: PLC0415

    accounts = getattr(runtime, "accounts", None) or []
    return _account_key(accounts[0]) if accounts else ""


def _client_of(runtime: Any, account: str) -> Any:
    """取账号对应的设备客户端。

    设备按 client 会话分配独立隧道端口，跨账号取数会拿到别人的数据或 401，
    因此必须用**所选账号**的客户端。
    """
    clients = getattr(runtime, "clients", None) or {}
    if account and account in clients:
        return clients[account]
    primary = _primary_key(runtime)
    if primary and primary in clients:
        return clients[primary]
    return runtime.client


def _device_id_of(runtime: Any) -> str:
    """取 ``deviceId``（``getAlbumInfo`` 必需）。

    ⚠️ 用配置条目的 ``device_id``，**不是** ``cloud_dev_id``（设备 SN）——
    两者不可互换，用错会 1101/30104（实测）。
    """
    entry = getattr(runtime, "entry", None)
    data = getattr(entry, "data", None) or {}
    return str(data.get("device_id") or "")


def _album_thumb(album: dict[str, Any]) -> str:
    """相册封面缩略图路径（``coverInfo`` 里可能有 None 元素）。"""
    for item in album.get("coverInfo") or []:
        if isinstance(item, dict):
            path = item.get("thumbFilePath") or item.get("lcdFilePath")
            if path:
                return str(path)
    return ""


class HuaweiStorageAlbumsView(HomeAssistantView):
    """相册列表（真实相册，含封面缩略图）。

    GET /api/huawei_home_storage/albums/<entry_id>?account=<key>
    返回按业务分组的相册：智能分类 / 人物 / 地点 / 场景 / 我的相册。
    每个相册带 albumType / albumId / num / thumbUrl，供面板网格直接渲染。
    """

    url = "/api/huawei_home_storage/albums/{entry_id}"
    name = "api:huawei_home_storage:albums"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        runtime = _runtime_of(request, entry_id)
        account = request.query.get("account") or ""
        key = account or _primary_key(runtime)

        groups = []
        total = 0
        for group_key, title, types in _ALBUM_GROUPS:
            albums: list[dict[str, Any]] = []
            seen: set[tuple[int, int]] = set()
            for album_type in types:
                raw = (
                    runtime.albums_of_account(key, album_type)
                    if key
                    else runtime.albums_of(album_type)
                )
                for a in raw or []:
                    album_id = int(a.get("albumId") or 0)
                    a_type = int(a.get("albumType") or album_type)
                    if (a_type, album_id) in seen:
                        continue
                    seen.add((a_type, album_id))
                    thumb = _album_thumb(a)
                    albums.append(
                        {
                            "type": a_type,
                            "id": album_id,
                            "name": a.get("albumName") or "未命名相册",
                            "count": int(a.get("num") or 0),
                            "thumbUrl": (
                                build_image_url(entry_id, thumb, name="thumb", account=account)
                                if thumb
                                else ""
                            ),
                        }
                    )
            # 「我的相册」若缓存里没有，直接补取 albumType=6（失败只降级）
            if group_key == "user" and not albums:
                try:
                    res = await _client_of(runtime, account)._request(
                        "/gallery/getAlbumList", {"albumType": 6}
                    )
                    for a in res.get("albumlist") or []:
                        thumb = _album_thumb(a)
                        albums.append(
                            {
                                "type": int(a.get("albumType") or 6),
                                "id": int(a.get("albumId") or 0),
                                "name": a.get("albumName") or "未命名相册",
                                "count": int(a.get("num") or 0),
                                "thumbUrl": (
                                    build_image_url(
                                        entry_id, thumb, name="thumb", account=account
                                    )
                                    if thumb
                                    else ""
                                ),
                            }
                        )
                except Exception:  # noqa: BLE001
                    pass
            if albums:
                albums.sort(key=lambda x: -x["count"])
                total += len(albums)
                groups.append({"key": group_key, "title": title, "albums": albums})

        # 「所有照片」这类系统相册没有 coverInfo，卡片会空着。
        # 用相册内首张照片的缩略图补封面（只对缺封面的相册做，代价可控）。
        client = _client_of(runtime, account)
        for group in groups:
            for album in group["albums"]:
                if album["thumbUrl"] or not album["count"]:
                    continue
                try:
                    res = await client.async_get_album_photos(
                        album["id"],
                        album["type"],
                        device_id=_device_id_of(runtime),
                        num=1,
                    )
                    first = (res.get("photos") or [{}])[0]
                    thumb = first.get("thumbFilePath") or ""
                    if thumb:
                        album["thumbUrl"] = build_image_url(
                            entry_id, thumb, name="thumb", account=account
                        )
                except Exception:  # noqa: BLE001
                    pass

        # ⚠️ key 是账号本身（手机号），原样回给前端等于把手机号放进页面/日志
        return web.json_response(
            {"account": mask_account(key), "total": total, "groups": groups}
        )


class HuaweiStorageAlbumPhotosView(HomeAssistantView):
    """相册内照片（分页）。

    GET /api/huawei_home_storage/album/<entry_id>/<album_type>/<album_id>
        ?account=<key>&last_cre_time=&last_row_id=&num=

    上游实测：`getAlbumInfo` 八个参数缺一即 30104；返回的照片带
    ``thumbFilePath``（可取）与 ``hdcFilePath``/``lcdFilePath``（原图）。
    """

    url = "/api/huawei_home_storage/album/{entry_id}/{album_type}/{album_id}"
    name = "api:huawei_home_storage:album_photos"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        album_type: str,
        album_id: str,
    ) -> web.Response:
        runtime = _runtime_of(request, entry_id)
        account = request.query.get("account") or ""
        client = _client_of(runtime, account)
        try:
            res = await client.async_get_album_photos(
                int(album_id),
                int(album_type),
                device_id=_device_id_of(runtime),
                last_cre_time=int(request.query.get("last_cre_time") or 0),
                last_row_id=int(request.query.get("last_row_id") or 0),
                num=int(request.query.get("num") or 100),
            )
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": str(err)}, status=502)

        photos = []
        for p in res.get("photos") or []:
            name = str(p.get("fileName") or p.get("name") or p.get("fileId") or "")
            thumb = p.get("thumbFilePath") or ""
            if not thumb:
                for a in p.get("assets") or []:
                    if "thumb" in str(a.get("name", "")):
                        thumb = a.get("path") or ""
                        break
            # 原图（hdc）多为 HEIC/大图 —— 浏览器**渲染不了 HEIC**，
            # 因此浏览用 lcd（通常是 JPEG），下载才给 hdc。
            hdc = p.get("hdcFilePath") or ""
            lcd = p.get("lcdFilePath") or ""
            item = {
                "id": p.get("fileId"),
                "name": name,
                "size": p.get("fileSize") or p.get("size"),
                "mtime": p.get("mtime") or p.get("createTime"),
            }
            if thumb:
                item["thumbUrl"] = build_image_url(
                    entry_id, thumb, name="thumb", account=account
                )
            if lcd or hdc:
                item["viewUrl"] = build_image_url(
                    entry_id, lcd or hdc, name="raw", account=account
                )
            if hdc or lcd:
                item["downloadUrl"] = build_image_url(
                    entry_id, hdc or lcd, name="raw", account=account
                )
                item["downloadName"] = name
            photos.append(item)

        return web.json_response(
            {
                "count": len(photos),
                "photos": photos,
                "next": {
                    "last_cre_time": int(res.get("lastCreTime") or 0),
                    "last_row_id": int(res.get("lastRowId") or 0),
                },
            }
        )


class HuaweiStorageRecycleView(HomeAssistantView):
    """最近删除（回收站）。

    GET /api/huawei_home_storage/recycle/<entry_id>?space=user|public
    条目含 rid（恢复用）/ name / dtime / 类型。
    """

    url = "/api/huawei_home_storage/recycle/{entry_id}"
    name = "api:huawei_home_storage:recycle"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        runtime = _runtime_of(request, entry_id)
        account = request.query.get("account") or ""
        client = _client_of(runtime, account)
        try:
            items = await client.async_list_recycle(
                category=request.query.get("space") or "public",
                limit=int(request.query.get("limit") or 100),
                offset=int(request.query.get("offset") or 0),
            )
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": str(err)}, status=502)
        out = []
        for it in items or []:
            out.append(
                {
                    "rid": str(it.get("rid") or it.get("id") or ""),
                    "name": it.get("name") or it.get("fileName") or "",
                    "path": it.get("path") or "",
                    "mtime": it.get("dtime") or it.get("deleteTime") or 0,
                    "type": it.get("type"),
                }
            )
        return web.json_response({"count": len(out), "items": out})


class HuaweiStorageUploadView(HomeAssistantView):
    """浏览器上传（面板用）。

    ``POST /api/huawei_home_storage/upload/<entry_id>?path=/file/x.bin&space=user``
    body = 文件原始字节，``Content-Length`` 必需（设备侧 prepareUpload 要声明大小）。

    为什么单开一个视图：集成的 ``upload_file`` **服务**只支持文本
    （``content``）或 HA 主机上的路径（``local_path``），都承载不了
    「用户在浏览器里选的文件」。本视图边收边转发，内存占用只有一个分块。
    """

    url = "/api/huawei_home_storage/upload/{entry_id}"
    name = "api:huawei_home_storage:upload"
    requires_auth = True

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        runtime = _runtime_of(request, entry_id)
        dest = (request.query.get("path") or "").strip()
        if not dest:
            return web.json_response({"error": "缺少 path"}, status=400)
        total = request.content_length
        if not total:
            return web.json_response(
                {"error": "缺少 Content-Length，无法向设备声明文件大小"}, status=411
            )
        space = request.query.get("space") or "user"
        category = "public" if space == "public" else "user"
        client = _client_of(runtime, request.query.get("account") or "")

        # 目标目录必须已存在，否则设备会直接断开连接（实测）
        parent = dest.rstrip("/").rsplit("/", 1)[0] + "/"
        if not await ensure_dir(client, parent, category):
            return web.json_response(
                {"error": f"目标目录不可用：{parent}"}, status=502
            )
        try:
            res = await upload_stream(
                client,
                dest,
                total,
                request.content.iter_chunked(1024 * 1024),
                device_id=_device_id_of(runtime),
                category=category,
            )
        except Exception as err:  # noqa: BLE001
            return web.json_response({"error": str(err)[:200]}, status=502)
        return web.json_response({"ok": True, "path": dest, "size": total, "device": res})


def async_register_views(hass: HomeAssistant) -> None:
    if hass.data.get(VIEWS_FLAG):
        return
    hass.http.register_view(HuaweiStorageImageView())
    hass.http.register_view(HuaweiStorageAccountImageView())
    hass.http.register_view(HuaweiStorageStatusView())
    hass.http.register_view(HuaweiStorageFilesView())
    hass.http.register_view(HuaweiStorageAlbumsView())
    hass.http.register_view(HuaweiStorageAlbumPhotosView())
    hass.http.register_view(HuaweiStorageRecycleView())
    hass.http.register_view(HuaweiStorageUploadView())
    hass.data[VIEWS_FLAG] = True


def async_unregister_views(hass: HomeAssistant) -> None:
    hass.data[VIEWS_FLAG] = False
