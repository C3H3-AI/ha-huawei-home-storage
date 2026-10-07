"""侧边栏面板：在 HA 中展示家庭存储状态并快捷刷新凭据。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend, panel_custom
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

import json as _json
try:
    version = _json.loads(
        (Path(__file__).parent / "manifest.json").read_text()
    ).get("version", "0")
except Exception:  # noqa: BLE001
    version = "0"

PANEL_URL_PATH = "huawei-storage"
PANEL_TITLE = "家庭存储"
PANEL_ICON = "mdi:nas"
PANEL_WEBCOMPONENT = "huawei-storage-panel"
STATIC_URL = f"/{DOMAIN}"
# 带集成版本号做缓存穿透：升级面板代码后浏览器不会用旧缓存
PANEL_MODULE_URL = f"{STATIC_URL}/huawei-storage-panel.js?v={version}"
WWW_DIR = Path(__file__).parent / "www"
PANEL_FLAG = f"{DOMAIN}_panel_registered"


async def _get_translations(hass: HomeAssistant) -> dict[str, str]:
    """收集面板文案，供前端 ``localize`` 使用。

    panel_custom 会把返回的 dict 作为 ``localize`` 回调交给 Web Component，
    键名与前端 ``_t()`` 里的 ``component.huawei_home_storage.panel.*`` 对应。
    """
    keys = [
        f"component.{DOMAIN}.common.{key}"
        for key in (
            "title",
            "empty",
            "refresh",
            "refreshing",
            "open_media",
            "photos",
            "videos",
            "user_albums",
            "face_albums",
            "scene_albums",
            "place_albums",
            "trash",
            "disk_total",
            "disk_used",
            "disk_free",
            "disk_usage",
            "usb",
            "users",
            "model",
            "serial",
            "mac",
            "lan",
            "tunnel",
            "account_login",
            "device_code_login",
            "session_at",
        )
    ]
    try:
        return dict(await async_get_translations(hass, "zh-Hans", "entity", keys))
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("面板翻译获取失败，使用内置文案: %s", err)
        return {}


async def async_register_panel(hass: HomeAssistant) -> None:
    """注册静态目录与侧边栏面板（幂等）。"""
    if hass.data.get(PANEL_FLAG):
        return
    if "frontend" not in hass.config.components:
        _LOGGER.debug("未启用 frontend，跳过侧边栏面板注册")
        return

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(WWW_DIR), False)]
        )
    except ImportError:  # 兼容旧版 HA
        hass.http.register_static_path(STATIC_URL, str(WWW_DIR), False)
    except RuntimeError:
        _LOGGER.debug("静态目录 %s 已注册", STATIC_URL)

    try:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name=PANEL_WEBCOMPONENT,
            frontend_url_path=PANEL_URL_PATH,
            module_url=PANEL_MODULE_URL,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            config={},
            require_admin=False,
            embed_iframe=False,
        )
    except ValueError:
        _LOGGER.debug("面板 %s 已存在", PANEL_URL_PATH)

    hass.data[PANEL_FLAG] = True


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """从侧边栏移除面板。"""
    if not hass.data.get(PANEL_FLAG):
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[PANEL_FLAG] = False
