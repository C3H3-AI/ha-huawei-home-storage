"""Services for Huawei Home Storage."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)

from .const import DOMAIN
from .coordinator import HuaweiStorageData

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_CREDENTIALS = "refresh_credentials"

REFRESH_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})


def _resolve(hass: HomeAssistant, entry_id: str | None) -> HuaweiStorageData | None:
    entries: dict[str, HuaweiStorageData] = hass.data.get(DOMAIN, {}) or {}
    if entry_id:
        return entries.get(entry_id)
    return next(iter(entries.values()), None)


async def async_register_services(hass: HomeAssistant) -> None:
    """注册服务（可重复调用）。"""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH_CREDENTIALS):
        return

    async def _refresh_credentials(call: ServiceCall) -> ServiceResponse:
        """强制重新走一遍云 startService，换取新的设备会话凭据。"""
        runtime = _resolve(hass, call.data.get("entry_id"))
        if runtime is None:
            return {"ok": False, "error": "没有可用的配置条目"}
        try:
            await runtime.client.async_refresh_credentials()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("刷新设备凭据失败: %s", err)
            return {"ok": False, "error": str(err)}
        # 凭据换了，两个协调器都要重新拉一次
        await runtime.fast.async_request_refresh()
        await runtime.albums.async_request_refresh()
        creds = runtime.client.credentials
        result: dict[str, Any] = {"ok": True}
        if creds is not None:
            result.update(creds.to_dict())
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_CREDENTIALS,
        _refresh_credentials,
        schema=REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
