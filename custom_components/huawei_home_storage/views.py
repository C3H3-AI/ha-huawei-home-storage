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
                    "counts": data.get("counts") or {},
                    "disk": data.get("disk") or {},
                    "user_data": data.get("user_data") or {},
                    # 面板展示：USB 接入与设备端用户
                    "usb": data.get("usb") or {},
                    "device_users": data.get("device_users") or [],
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
                }
            )
        return web.json_response({"entries": payload})


def async_register_views(hass: HomeAssistant) -> None:
    if hass.data.get(VIEWS_FLAG):
        return
    hass.http.register_view(HuaweiStorageImageView())
    hass.http.register_view(HuaweiStorageAccountImageView())
    hass.http.register_view(HuaweiStorageStatusView())
    hass.data[VIEWS_FLAG] = True


def async_unregister_views(hass: HomeAssistant) -> None:
    hass.data[VIEWS_FLAG] = False
