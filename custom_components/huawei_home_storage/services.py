"""Services for Huawei Home Storage.

服务分三类：
* **只读查询**：``query_files`` / ``file_detail`` / ``search_files`` /
  ``task_status`` / ``list_recycle``
* **文件空间写入**：``create_folder`` / ``rename_path`` / ``move_paths`` /
  ``delete_paths`` / ``upload_file`` / ``cancel_upload`` / ``copy_to_album`` /
  ``recover_recycle``（删除**一律进回收站**、可逆；永久删除的端点参数没解出，
  集成不提供，回收站条目请在客户端 App 里清）
* **设备/账号运维**：``refresh_credentials`` / ``duplicate_scan`` /
  ``reboot_device`` / ``disk_sleep`` / ``usb_plug_out``

⚠️ 设备侧写入端点要的是**配置条目里的 ``device_id``**（形如 ``42e9d4b7-…``），
不是云侧 SN（``creds.cloud_dev_id``）。二者在 ``batchOperation`` /
``prepareUpload`` / ``trans/*`` 上**不可互换**（用错 → ``1101``，实测 2026-10-08）。
"""
from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)

from .const import CONF_DEVICE_ID, DOMAIN, FILE_FILES_CATEGORY
from .coordinator import HuaweiStorageData

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_CREDENTIALS = "refresh_credentials"
SERVICE_DUP_SCAN = "duplicate_scan"
SERVICE_QUERY_FILES = "query_files"
SERVICE_DELETE_MEDIA = "delete_media"
SERVICE_RECOVER_MEDIA = "recover_media"
# ---- 文件空间（NAS）读写：2026-10-08 补齐「新建目录 / 重命名」后新增 ----
SERVICE_CREATE_FOLDER = "create_folder"
SERVICE_RENAME_PATH = "rename_path"
SERVICE_MOVE_PATHS = "move_paths"
SERVICE_DELETE_PATHS = "delete_paths"
SERVICE_UPLOAD_FILE = "upload_file"
SERVICE_CANCEL_UPLOAD = "cancel_upload"
SERVICE_COPY_TO_ALBUM = "copy_to_album"
SERVICE_LIST_RECYCLE = "list_recycle"
SERVICE_RECOVER_RECYCLE = "recover_recycle"
SERVICE_FILE_DETAIL = "file_detail"
SERVICE_SEARCH_FILES = "search_files"
SERVICE_TASK_STATUS = "task_status"
# ---- 设备级运维 ----
SERVICE_REBOOT_DEVICE = "reboot_device"
SERVICE_DISK_SLEEP = "disk_sleep"
SERVICE_USB_PLUG_OUT = "usb_plug_out"

REFRESH_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})

#: 文件空间的两个**独立**空间：user = 「我的文件」，public = 「共享」
CATEGORY = vol.In(("user", "public"))
#: 默认空间与集成其它入口一致（``FILE_FILES_CATEGORY`` = user）——
#: 要写「共享」时显式传 ``category: public``
DEFAULT_CATEGORY = FILE_FILES_CATEGORY
#: 单次最多操作的条目数（防止一次服务调用把设备打爆）
MAX_BATCH = 200
#: 单个文件上限（读取/上传都用它兜底）
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


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


def _pick(
    hass: HomeAssistant, entry_id: str | None
) -> tuple[HuaweiStorageData | None, ConfigEntry | None, dict[str, Any] | None]:
    """解析出（runtime, config_entry, 错误响应）。"""
    entries: dict[str, HuaweiStorageData] = hass.data.get(DOMAIN, {}) or {}
    key = entry_id or next(iter(entries), None)
    runtime = entries.get(key) if key else None
    if runtime is None:
        return None, None, {"ok": False, "error": "没有可用的配置条目"}
    entry = hass.config_entries.async_get_entry(key) if key else None
    return runtime, entry, None


def _entry_device_id(entry: ConfigEntry | None) -> str:
    """配置条目里的 ``device_id``（设备侧写入端点要的就是它，不是云侧 SN）。"""
    if entry is None:
        return ""
    return str((entry.data or {}).get(CONF_DEVICE_ID) or "")


def _need_device_id(entry: ConfigEntry | None) -> dict[str, Any] | None:
    if not _entry_device_id(entry):
        return {"ok": False, "error": "配置条目缺少 device_id，无法执行该操作"}
    return None


def _paths(call: ServiceCall, field: str = "paths") -> list[str]:
    return [str(p) for p in call.data.get(field) or []]


async def async_register_services(hass: HomeAssistant) -> None:
    """注册服务（可重复调用）。"""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH_CREDENTIALS):
        return

    # ------------------------------------------------------------------
    # 设备 / 账号运维
    # ------------------------------------------------------------------
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

    async def _reboot_device(call: "ServiceCall") -> "ServiceResponse":
        """⚠️ 重启存储设备：会中断服务约 1-2 分钟（可恢复，但整机不可用）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        _LOGGER.warning("收到 reboot_device 服务调用：设备将重启，服务中断约 1-2 分钟")
        try:
            result = await runtime.client.async_post_device_reboot()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("重启设备失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "reboot", "result": result}

    async def _disk_sleep(call: "ServiceCall") -> "ServiceResponse":
        """磁盘休眠（可恢复；唤醒由设备自身策略决定）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        _LOGGER.warning("收到 disk_sleep 服务调用：磁盘将进入休眠")
        try:
            result = await runtime.client.async_post_disk_sleep()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("磁盘休眠失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "disk_sleep", "result": result}

    async def _usb_plug_out(call: "ServiceCall") -> "ServiceResponse":
        """弹出 USB 设备（可恢复；在用的 USB 存储会被卸载）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        _LOGGER.warning("收到 usb_plug_out 服务调用：USB 设备将被弹出")
        try:
            result = await runtime.client.async_post_usb_plug_out()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("弹出 USB 失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "usb_plug_out", "result": result}

    # ------------------------------------------------------------------
    # 只读查询
    # ------------------------------------------------------------------
    async def _query_files(call: "ServiceCall") -> "ServiceResponse":
        """查询文件/目录（只读）：recent / all / dir / photos。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        client = runtime.client
        source = call.data.get("source", "recent")
        limit = int(call.data.get("limit", 20))
        category = call.data.get("category") or DEFAULT_CATEGORY
        try:
            if source == "recent":
                raw = await client.async_get_recent_files(limit=limit)
                items = ((raw or {}).get("data") or {}).get("records") or []
            elif source == "all":
                raw = await client.async_get_all_files(limit=limit)
                items = ((raw or {}).get("data") or {}).get("files") or []
            elif source == "photos":
                raw = await client.async_get_photos_table(0)
                items = raw.get("data") if isinstance(raw, dict) else raw
                items = items if isinstance(items, list) else []
            else:
                dir_path = call.data.get("dir_path") or "/file/"
                raw = await client.async_list_files(dir_path, category=category)
                # v0.8.0 的 async_list_files 返回 {"files": [...], "count": N}
                # （旧版返回 list），两种形态都兼容。
                if isinstance(raw, dict):
                    items = raw.get("files") or []
                else:
                    items = raw if isinstance(raw, list) else []
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("查询文件失败(%s): %s", source, err)
            return {"ok": False, "error": str(err)}

        return {"ok": True, "source": source, "count": len(items),
                "items": [_brief(i) for i in items][:limit]}

    async def _file_detail(call: "ServiceCall") -> "ServiceResponse":
        """文件/目录详情（``/filesvc/detail``，参数未完全解出，容错返回）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_file_detail(
                call.data["path"], category=call.data.get("category") or DEFAULT_CATEGORY
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": call.data["path"], "detail": data}

    async def _search_files(call: "ServiceCall") -> "ServiceResponse":
        """按关键字搜索（``/filesvc/search``，参数未完全解出，容错返回）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_search_files(
                call.data["keyword"],
                category=call.data.get("category") or DEFAULT_CATEGORY,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "keyword": call.data["keyword"], "result": data}

    async def _task_status(call: "ServiceCall") -> "ServiceResponse":
        """查传输任务中心（只读）：filesvc（文件空间）/ trans（跨服务传输）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        service = call.data.get("service") or "filesvc"
        types = call.data.get("task_types")
        if not types:
            types = [400] if service == "filesvc" else [201, 300]
        try:
            tasks = await runtime.client.async_get_task_status(
                [int(t) for t in types],
                category=int(call.data.get("task_category", 2)),
                service=service,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "service": service, "count": len(tasks), "tasks": tasks}

    async def _list_recycle(call: "ServiceCall") -> "ServiceResponse":
        """列回收站（只读）——恢复要用条目里的 ``rid``。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            items = await runtime.client.async_list_recycle(
                category=call.data.get("category") or DEFAULT_CATEGORY,
                limit=int(call.data.get("limit", 100)),
                offset=int(call.data.get("offset", 0)),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "count": len(items), "items": items}

    # ------------------------------------------------------------------
    # 文件空间写入
    # ------------------------------------------------------------------
    async def _create_folder(call: "ServiceCall") -> "ServiceResponse":
        """新建目录（``/filesvc/mkdir``）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        path = call.data["path"]
        category = call.data.get("category") or DEFAULT_CATEGORY
        try:
            data = await runtime.client.async_mkdir(path, category=category)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("新建目录失败(%s): %s", path, exc)
            return {"ok": False, "path": path, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        return {
            "ok": True,
            "path": path if path.endswith("/") else path + "/",
            "category": category,
            "fid": (data or {}).get("fid"),
        }

    async def _rename_path(call: "ServiceCall") -> "ServiceResponse":
        """重命名（``/filesvc/rename``）：``old_path`` → ``new_path``。

        目录要带尾斜杠（``/file/旧名/``），文件不带。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        old_path = call.data["old_path"]
        new_path = call.data["new_path"]
        category = call.data.get("category") or DEFAULT_CATEGORY
        try:
            result = await runtime.client.async_rename(
                old_path, new_path, category=category,
                file_id=call.data.get("file_id"),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("重命名失败(%s → %s): %s", old_path, new_path, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "old_path": old_path, "new_path": new_path,
                "error": dev_err, "result": result}

    async def _move_paths(call: "ServiceCall") -> "ServiceResponse":
        """移动文件/目录到目标目录（``/trans/move``，异步任务）。"""
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        paths = _paths(call)
        dest = call.data["dest_dir"]
        category = call.data.get("category") or DEFAULT_CATEGORY
        try:
            result = await runtime.client.async_trans_move(
                paths, dest, _entry_device_id(entry),
                src_category=category,
                dst_category=call.data.get("dest_category") or category,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("移动失败(%s → %s): %s", paths, dest, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(paths), "dest_dir": dest,
                "error": dev_err, "result": result}

    async def _delete_paths(call: "ServiceCall") -> "ServiceResponse":
        """删除文件空间里的文件/目录 —— **统一进回收站**（可逆）。

        集成**不提供永久删除**：设备侧 ``type=delete`` 与
        ``/filesvc/recycleDelFiles`` 的参数都没解出（实测恒 ``1101``），
        回收站条目只能在客户端 App 里清理。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        paths = _paths(call)
        category = call.data.get("category") or DEFAULT_CATEGORY
        _LOGGER.warning("delete_paths：把 %d 项移入回收站（可用 recover_recycle 还原）",
                        len(paths))
        try:
            result = await runtime.client.async_delete_paths(
                paths, _entry_device_id(entry),
                to_recycle=True, category=category,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("删除路径失败(%s): %s", paths, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(paths), "to_recycle": True,
                "error": dev_err, "result": result}

    async def _upload_file(call: "ServiceCall") -> "ServiceResponse":
        """上传文件到设备文件空间（``prepareUpload`` + 数据通道 ``/upload``）。

        ``content``（文本）与 ``local_path``（HA 主机上的文件）二选一：
        文本走 ``content``，二进制走 ``local_path``（读权限受 HA 容器限制，
        常见可读路径是 ``/config`` 下的文件）。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        dest_path = call.data["dest_path"]
        content = call.data.get("content")
        local_path = call.data.get("local_path")
        if content is None and not local_path:
            return {"ok": False, "error": "content 与 local_path 必须提供其一"}

        payload: bytes
        if local_path:
            def _read() -> bytes:
                with open(local_path, "rb") as fh:
                    return fh.read(MAX_UPLOAD_BYTES + 1)

            try:
                payload = await hass.async_add_executor_job(_read)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"读取 {local_path} 失败: {exc}"}
            if len(payload) > MAX_UPLOAD_BYTES:
                return {"ok": False,
                        "error": f"文件超过 {MAX_UPLOAD_BYTES} 字节上限"}
        else:
            payload = str(content).encode("utf-8")

        try:
            result = await runtime.client.async_upload_file(
                dest_path, payload, _entry_device_id(entry),
                category=call.data.get("category") or DEFAULT_CATEGORY,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("上传失败(%s): %s", dest_path, exc)
            return {"ok": False, "dest_path": dest_path, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        return {"ok": True, "dest_path": dest_path, "bytes": len(payload),
                "result": result}

    async def _cancel_upload(call: "ServiceCall") -> "ServiceResponse":
        """取消进行中的上传（``/filesvc/cancelUpload``，需 ``fileId``）。"""
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        try:
            result = await runtime.client.async_cancel_upload(
                call.data["file_ids"], _entry_device_id(entry)
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "error": dev_err, "result": result}

    async def _copy_to_album(call: "ServiceCall") -> "ServiceResponse":
        """把文件空间里的照片复制进相册（``/trans/acrosscopy``，异步任务）。

        需要源文件的 ``fid``：不传 ``fids`` 时按路径逐条解析（多几次列目录）。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        paths = _paths(call)
        category = call.data.get("category") or DEFAULT_CATEGORY
        fids = call.data.get("fids") or []
        src_files: list[dict[str, Any]] = []
        try:
            for index, path in enumerate(paths):
                fid = fids[index] if index < len(fids) else None
                if fid is None:
                    entry_item = await runtime.client.async_find_entry(
                        path, category=category
                    )
                    if entry_item is None:
                        return {"ok": False, "error": f"找不到源文件: {path}"}
                    fid = entry_item.get("fid") or entry_item.get("id")
                src_files.append({"category": category, "fid": fid, "path": path})
            album_id = int(call.data["album_id"])
            result = await runtime.client.async_trans_acrosscopy(
                src_files, "filesvc",
                [{
                    "albumId": album_id,
                    "albumName": call.data.get("album_name") or "",
                    "albumType": int(call.data.get("album_type", 6)),
                    "category": call.data.get("album_category") or category,
                }],
                "gallery", _entry_device_id(entry),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("复制到相册失败(%s): %s", paths, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(src_files), "album_id": album_id,
                "error": dev_err, "result": result}

    async def _recover_recycle(call: "ServiceCall") -> "ServiceResponse":
        """从回收站恢复（``batchOperation?operation=recycle&type=recover``）。

        ``rid`` 可直接给；也可给 ``paths``/``names`` 由回收站列表里匹配。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        category = call.data.get("category") or DEFAULT_CATEGORY
        rid = call.data.get("rid")
        name = call.data.get("name") or ""
        item_type = int(call.data.get("item_type", 4))
        if rid is None:
            wanted = _paths(call) or [str(n) for n in call.data.get("names") or []]
            if not wanted:
                return {"ok": False, "error": "rid / paths / names 至少给一个"}
            try:
                items = await runtime.client.async_list_recycle(
                    category=category, limit=500
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"读取回收站失败: {exc}"}

            def _match(item: dict[str, Any]) -> bool:
                iname = str(item.get("name") or "")
                ipath = str(item.get("path") or "")
                return any(
                    w.rstrip("/") == iname or w.rstrip("/").endswith(iname)
                    or (ipath and ipath.rstrip("/") == w.rstrip("/"))
                    or (ipath and ipath.rstrip("/").endswith(w.rstrip("/")))
                    for w in wanted
                )

            hit = next((i for i in items if _match(i)), None)
            if hit is None:
                return {"ok": False, "error": f"回收站里没找到: {wanted}"}
            rid = hit.get("rid")
            name = str(hit.get("name") or name)
            item_type = int(hit.get("type") or item_type or 0)
        try:
            result = await runtime.client.async_recycle_recover(
                rid, name=name, device_id=_entry_device_id(entry),
                category=category, item_type=item_type,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("回收站恢复失败(rid=%s): %s", rid, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "rid": rid, "name": name, "error": dev_err,
                "result": result}

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------
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

    entry_field = {vol.Optional("entry_id"): str}

    hass.services.async_register(
        DOMAIN, SERVICE_DUP_SCAN, _dup_scan,
        schema=vol.Schema({
            **entry_field,
            vol.Required("act"): vol.In(("start", "stop")),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_QUERY_FILES, _query_files,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("source"): vol.In(("recent", "all", "dir", "photos")),
            vol.Optional("dir_path"): str,
            vol.Optional("category"): CATEGORY,
            vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=200)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    media_schema = vol.Schema({
        **entry_field,
        vol.Required("file_ids"): vol.All(cv.ensure_list, [str], vol.Length(min=1, max=MAX_BATCH)),
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

    path_list = vol.All(cv.ensure_list, [str], vol.Length(min=1, max=MAX_BATCH))

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_FOLDER, _create_folder,
        schema=vol.Schema({
            **entry_field,
            vol.Required("path"): str,
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RENAME_PATH, _rename_path,
        schema=vol.Schema({
            **entry_field,
            vol.Required("old_path"): str,
            vol.Required("new_path"): str,
            vol.Optional("category"): CATEGORY,
            vol.Optional("file_id"): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MOVE_PATHS, _move_paths,
        schema=vol.Schema({
            **entry_field,
            vol.Required("paths"): path_list,
            vol.Required("dest_dir"): str,
            vol.Optional("category"): CATEGORY,
            vol.Optional("dest_category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_PATHS, _delete_paths,
        schema=vol.Schema({
            **entry_field,
            vol.Required("paths"): path_list,
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPLOAD_FILE, _upload_file,
        schema=vol.Schema({
            **entry_field,
            vol.Required("dest_path"): str,
            vol.Optional("content"): cv.string,
            vol.Optional("local_path"): cv.string,
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_UPLOAD, _cancel_upload,
        schema=vol.Schema({
            **entry_field,
            vol.Required("file_ids"): vol.All(cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COPY_TO_ALBUM, _copy_to_album,
        schema=vol.Schema({
            **entry_field,
            vol.Required("paths"): path_list,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Optional("album_name"): str,
            vol.Optional("album_type", default=6): vol.Coerce(int),
            vol.Optional("album_category"): CATEGORY,
            vol.Optional("fids"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_RECYCLE, _list_recycle,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("category"): CATEGORY,
            vol.Optional("limit", default=100): vol.All(int, vol.Range(min=1, max=500)),
            vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECOVER_RECYCLE, _recover_recycle,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("rid"): vol.Coerce(int),
            vol.Optional("name"): str,
            vol.Optional("paths"): vol.All(cv.ensure_list, [str]),
            vol.Optional("names"): vol.All(cv.ensure_list, [str]),
            vol.Optional("category"): CATEGORY,
            vol.Optional("item_type", default=4): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FILE_DETAIL, _file_detail,
        schema=vol.Schema({
            **entry_field,
            vol.Required("path"): str,
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEARCH_FILES, _search_files,
        schema=vol.Schema({
            **entry_field,
            vol.Required("keyword"): str,
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TASK_STATUS, _task_status,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("service", default="filesvc"): vol.In(("filesvc", "trans")),
            vol.Optional("task_types"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
            vol.Optional("task_category", default=2): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT_DEVICE, _reboot_device,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISK_SLEEP, _disk_sleep,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_USB_PLUG_OUT, _usb_plug_out,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )


def _brief(item: Any) -> dict[str, Any]:
    """把设备返回的条目裁成常用字段（服务响应别塞整条记录）。"""
    if not isinstance(item, dict):
        return {}
    return {k: item.get(k) for k in
            ("name", "mime", "size", "mtime", "path", "type", "fid", "id",
             "fileId", "rowId", "operation", "rid", "dtime") if k in item}
