"""Services for Huawei Home Storage."""
from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
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
SERVICE_DUP_SCAN = "duplicate_scan"
SERVICE_QUERY_FILES = "query_files"
SERVICE_DELETE_MEDIA = "delete_media"
SERVICE_RECOVER_MEDIA = "recover_media"

REFRESH_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})


def _device_ok(result: Any) -> tuple[bool, str | None]:
    """校验设备是否真的执行了（不能只看请求没抛异常）。

    设备用 ``code`` 表示真实结果：0/缺失 = 成功；非 0 = 未执行
    （如 16106 会话失效/服务未就绪）。见逆向笔记 9.3。
    """
    code = result.get("code") if isinstance(result, dict) else None
    if code in (0, None):
        return True, None
    return False, f"设备返回 code={code}（未执行）"


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

    async def _dup_scan(call: "ServiceCall") -> "ServiceResponse":
        """启动/停止重复照片扫描（实测 stop 返回 des:suc）。"""
        runtime = _resolve(hass, call.data.get("entry_id"))
        if runtime is None:
            return {"ok": False, "error": "没有可用的配置条目"}
        act = call.data["act"]
        try:
            result = await runtime.client.async_ctrl_duplicate_scan(act)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("重复照片扫描(%s)失败: %s", act, err)
            return {"ok": False, "error": str(err)}
        await runtime.albums.async_request_refresh()
        ok, err = _device_ok(result)
        if not ok:
            return {"ok": False, "act": act, "error": err, "result": result}
        return {"ok": True, "act": act, "result": result}

    async def _query_files(call: "ServiceCall") -> "ServiceResponse":
        """查询文件/目录（只读）：recent / all / dir。"""
        runtime = _resolve(hass, call.data.get("entry_id"))
        if runtime is None:
            return {"ok": False, "error": "没有可用的配置条目"}
        client = runtime.client
        source = call.data.get("source", "recent")
        limit = int(call.data.get("limit", 20))
        try:
            if source == "recent":
                raw = await client.async_get_recent_files(limit=limit)
                items = ((raw or {}).get("data") or {}).get("records") or []
            elif source == "all":
                raw = await client.async_get_all_files(limit=limit)
                items = ((raw or {}).get("data") or {}).get("files") or []
            else:
                dir_path = call.data.get("dir_path") or "/file/"
                items = await client.async_list_files(dir_path)
                items = items if isinstance(items, list) else []
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("查询文件失败(%s): %s", source, err)
            return {"ok": False, "error": str(err)}

        def _brief(item: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(item, dict):
                return {}
            return {k: item.get(k) for k in
                    ("name", "mime", "size", "mtime", "path", "type", "fid", "id") if k in item}

        return {"ok": True, "source": source, "count": len(items),
                "items": [_brief(i) for i in items][:limit]}

    async def _delete_media(call: "ServiceCall") -> "ServiceResponse":
        """移入回收站（可逆；绝不调用 cleanBin 永久删除）。"""
        runtime = _resolve(hass, call.data.get("entry_id"))
        if runtime is None:
            return {"ok": False, "error": "没有可用的配置条目"}
        file_ids = call.data["file_ids"]
        _LOGGER.warning("移入回收站 %d 个媒体（可用 recover_media 恢复）", len(file_ids))
        try:
            result = await runtime.client.async_delete_media(file_ids)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("移入回收站失败: %s", err)
            return {"ok": False, "error": str(err)}
        await runtime.albums.async_request_refresh()
        ok, err = _device_ok(result)
        if not ok:
            return {"ok": False, "count": len(file_ids), "error": err, "result": result}
        return {"ok": True, "count": len(file_ids), "result": result}

    async def _recover_media(call: "ServiceCall") -> "ServiceResponse":
        """从回收站恢复。"""
        runtime = _resolve(hass, call.data.get("entry_id"))
        if runtime is None:
            return {"ok": False, "error": "没有可用的配置条目"}
        file_ids = call.data["file_ids"]
        try:
            result = await runtime.client.async_recover_media(file_ids)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("恢复媒体失败: %s", err)
            return {"ok": False, "error": str(err)}
        await runtime.albums.async_request_refresh()
        ok, err = _device_ok(result)
        if not ok:
            return {"ok": False, "count": len(file_ids), "error": err, "result": result}
        return {"ok": True, "count": len(file_ids), "result": result}

    hass.services.async_register(
        DOMAIN, SERVICE_DUP_SCAN, _dup_scan,
        schema=vol.Schema({
            vol.Optional("entry_id"): str,
            vol.Required("act"): vol.In(("start", "stop")),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_QUERY_FILES, _query_files,
        schema=vol.Schema({
            vol.Optional("entry_id"): str,
            vol.Optional("source"): vol.In(("recent", "all", "dir")),
            vol.Optional("dir_path"): str,
            vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=200)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    media_schema = vol.Schema({
        vol.Optional("entry_id"): str,
        vol.Required("file_ids"): vol.All(cv.ensure_list, [str], vol.Length(min=1, max=200)),
    })
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_MEDIA, _delete_media,
        schema=media_schema, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECOVER_MEDIA, _recover_media,
        schema=media_schema, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_CREDENTIALS,
        _refresh_credentials,
        schema=REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
