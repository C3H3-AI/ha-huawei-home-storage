"""Services for Huawei Home Storage.

服务分三类：
* **只读查询**：``query_files`` / ``file_detail`` / ``search_files`` /
  ``task_status`` / ``list_recycle`` / ``photo_info``
* **文件空间写入**：``create_folder`` / ``rename_path`` / ``move_paths`` /
  ``copy_paths`` / ``delete_paths`` / ``upload_file`` / ``download_file`` /
  ``cancel_upload`` / ``copy_to_album`` / ``recover_recycle``（删除**一律进
  回收站**、可逆；永久删除的端点参数没解出，集成不提供，回收站条目请在客户端 App 里清）
* **设备/账号运维**：``refresh_credentials`` / ``duplicate_scan`` /
  ``reboot_device`` / ``disk_sleep`` / ``usb_plug_out``

⚠️ 设备侧写入端点要的是**配置条目里的 ``device_id``**（形如 ``42e9d4b7-…``），
不是云侧 SN（``creds.cloud_dev_id``）。二者在 ``batchOperation`` /
``prepareUpload`` / ``trans/*`` 上**不可互换**（用错 → ``1101``，实测 2026-10-08）。
"""
from __future__ import annotations

import logging
import time as _time
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

from .const import (
    ALBUM_PAGE_SIZE,
    ALBUM_TYPE_USER,
    CONF_DEVICE_ID,
    DOMAIN,
    FILE_FILES_CATEGORY,
    TASK_TYPES_DEFAULT,
)
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
SERVICE_COPY_PATHS = "copy_paths"
SERVICE_DELETE_PATHS = "delete_paths"
SERVICE_UPLOAD_FILE = "upload_file"
SERVICE_DOWNLOAD_FILE = "download_file"
SERVICE_CANCEL_UPLOAD = "cancel_upload"
SERVICE_COPY_TO_ALBUM = "copy_to_album"
SERVICE_LIST_RECYCLE = "list_recycle"
SERVICE_RECOVER_RECYCLE = "recover_recycle"
SERVICE_DELETE_RECYCLE_ITEMS = "permanent_delete_recycle_items"
SERVICE_EMPTY_RECYCLE = "empty_recycle"
SERVICE_FILE_DETAIL = "file_detail"
SERVICE_SEARCH_FILES = "search_files"
SERVICE_PHOTO_INFO = "photo_info"
SERVICE_TASK_STATUS = "task_status"
SERVICE_CLEAN_TASK_RECORDS = "clean_task_records"
# 重试失败的传输任务（POST /{business}/retryTask）
SERVICE_RETRY_TASK = "retry_task"
# 动态 / 时光轴 / 回忆（GET /gallery/getDynamicInfo）
SERVICE_DYNAMIC_INFO = "dynamic_info"
# acelite 轻应用（插件）市场：只读三件套
SERVICE_PLUGIN_MARKET = "plugin_market"
SERVICE_PLUGIN_ALL = "plugin_all"
SERVICE_PLUGIN_XUNLEI = "plugin_xunlei"
SERVICE_PLUGIN_INSTALL = "plugin_install"
SERVICE_PLUGIN_UNINSTALL = "plugin_uninstall"
SERVICE_ADD_TO_ALBUM = "add_to_album"
# 上传照片**进相册**（走 /gallery/prepareUpload 拿相册域 fileId，
# 而非 /filesvc 的文件域）—— 见 transfer.upload_stream(service_type=...)。
# 全量照片表（面板批量加载用）
SERVICE_PHOTOS_TABLE_FULL = "photos_table_full"
SERVICE_SHARE_TO_PERSON = "share_to_person"
#: 按文件分享（与 ``share_to_person`` 是不同端点语义，2026-10-29 从重名中拆出）
SERVICE_SHARE_FILES_TO_PERSON = "share_files_to_person"
SERVICE_ALBUM_INFO = "album_info"
SERVICE_ALBUM_CHANGES = "album_changes"
SERVICE_GET_TASK = "get_task"
# ---- 浏览 / 诊断类（此前只有设备方法、没有服务出口）----
SERVICE_LIST_ALBUMS = "list_albums"
SERVICE_ALBUM_PHOTOS = "album_photos"
SERVICE_LIST_TRASH = "list_trash"
SERVICE_DUPLICATE_SCAN = "duplicate_scan_result"
SERVICE_DEVICE_DIAGNOSTICS = "device_diagnostics"
# ---- 设备级运维 ----
SERVICE_REBOOT_DEVICE = "reboot_device"
SERVICE_SHUTDOWN_DEVICE = "shutdown_device"
SERVICE_DISK_SLEEP = "disk_sleep"
SERVICE_DISK_INFO = "disk_info"
SERVICE_USB_PLUG_OUT = "usb_plug_out"
SERVICE_RAID_STATUS = "raid_status"
# ---- 相册 CRUD ----
SERVICE_ADD_ALBUM = "add_album"
SERVICE_DEL_ALBUM = "del_album"
SERVICE_SEARCH_ALBUM_PHOTOS = "search_album_photos"
SERVICE_RENAME_MEDIA = "rename_media"
SERVICE_REMOVE_ALBUM_MEMBERS = "remove_album_members"
SERVICE_HIDE_ALBUMS = "hide_albums"
SERVICE_LIST_ALL_ALBUMS = "list_all_albums"
SERVICE_MERGE_FACE_ALBUMS = "merge_face_albums"
# 相册属性修改（POST /gallery/albumCfg）：重命名 / 设封面
SERVICE_ALBUM_RENAME = "album_rename"
SERVICE_ALBUM_SET_COVER = "album_set_cover"
# ---- 辅助查询 ----
SERVICE_RECENT_FILES = "recent_files"
SERVICE_INSTALLED_PLUGINS = "installed_plugins"
SERVICE_ALL_TRANS_TASKS = "all_trans_tasks"
# 设备家庭成员（/account/userManageInfo）：给「共享给家人」挑 ownerId 用
SERVICE_DEVICE_USERS = "device_users"

REFRESH_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})

# ⚠️ 不可逆/高风险服务的确认词：调用方必须**显式**传对才执行。
#
# 起因（2026-10-17 实测）：``shutdown_device`` 此前**空 payload 就能触发**，
# 而它是「设备彻底断电、需物理按键重启」的不可逆操作 —— 一次误调用
# （批量探测 50 个服务时）真的把设备关机了，用户只能物理开机。
#
# 所以这些服务加一道**显式确认**：schema 层用 ``vol.In([word])`` 让值必须
# 完全等于确认词（大小写敏感），处理函数再校验一次（防绕过 schema 的内部调用）。
#
# ⚠️ 这是**破坏性变更**：已有自动化若调用这些服务需要补上 confirm 字段。
# 权衡：误关机的代价（设备断电 + 跑过去按物理键）远大于改一次自动化。
CONFIRM_SHUTDOWN = "SHUTDOWN"
CONFIRM_REBOOT = "REBOOT"
CONFIRM_EMPTY_RECYCLE = "EMPTY_RECYCLE"
CONFIRM_PERMANENT_DELETE = "PERMANENT_DELETE"
#: 删除相册（2026-10-29 补）：``/gallery/delAlbum`` 删的是**相册本身**，
#: 不是把照片挪进回收站 —— 照片会从所有视图里消失，且没有 undo。
#: 此前只有上面四个不可逆服务有 confirm，``del_album`` 被漏掉了，
#: 一句 ``service: huawei_home_storage.del_album`` + 一个 album_id 就能清掉
#: 整本共享相册（家庭成员共同维护的那种）。
CONFIRM_DELETE_ALBUM = "DELETE_ALBUM"
#: 合并人脸相册（2026-10-29 补）：``/gallery/mergeFaceAlbums`` 把 source
#: 相册**并进** target，源相册随之消失。人脸聚类结果一旦合起来就拆不回去
#: （设备没有"拆分相册"接口），所以这是不可逆的。此前同样没有确认门槛。
CONFIRM_MERGE_FACE_ALBUMS = "MERGE_FACE_ALBUMS"


def _confirm_field(word: str) -> dict:
    """必填确认字段（schema 用）：值必须完全等于给定词。"""
    return {vol.Required("confirm"): vol.In([word])}


def _reject_unconfirmed(call: "ServiceCall", word: str) -> ServiceResponse | None:
    """未确认则返回错误响应；已确认返回 ``None``（调用方继续）。"""
    if str(call.data.get("confirm") or "") != word:
        return {
            "ok": False,
            "error": (
                f"该操作不可逆，必须显式传 confirm: \"{word}\" 才会执行"
                f"（当前值: {str(call.data.get('confirm') or '')!r}）"
            ),
        }
    return None

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


def _client_for(runtime: Any, call: "ServiceCall") -> Any:
    """按 ``call.data["account"]`` 取对应账号的设备客户端；缺省用主账号。

    ⚠️ 为什么要有这个（2026-10-29）：**服务层一直是"只操作主账号"的** ——
    ``runtime.client`` 固定指向主账号（``HuaweiStorageData`` 构造时
    ``is_primary=True``）。多账号支持此前只做在**视图**里（``_client_of``）。

    这本身是个已知限制，但「相册上传照片」是**视图写 + 服务读**的组合流程，
    于是变成了硬故障：

        1. 上传走视图 → ``_client_of(runtime, account)`` → 正确进了账号 B
        2. 紧接着 ``copy_to_album`` 走服务 → ``runtime.client`` 是**主账号**
        3. 主账号里当然找不到刚传进 B 的文件 → 「找不到源文件」

    用户看到的是"上传成功但加入相册失败"，而文件明明就在那儿。所以相册
    这几个服务必须支持 ``account``。

    ⚠️ 传了 ``account`` 但不认识时**报错**，不 fallback 到主账号 ——
    与视图层 ``_client_of`` 同一原则（fallback 正是越权来源）。
    """
    account = str(call.data.get("account") or "")
    if not account:
        return runtime.client
    from .views import resolve_account  # noqa: PLC0415（services↔views 互相引用，放函数内避免循环导入）

    key = resolve_account(runtime, account)
    clients = getattr(runtime, "clients", None) or {}
    if not key or key not in clients:
        raise ValueError(f"账号不存在或无权访问: {account}")
    return clients[key]


#: 相册类服务都要在 schema 里声明它（见 ``_client_for`` 的说明）
ACCOUNT_FIELD: dict[Any, Any] = {vol.Optional("account"): str}


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
        if (blocked := _reject_unconfirmed(call, CONFIRM_REBOOT)) is not None:
            return blocked
        _LOGGER.warning("收到 reboot_device 服务调用：设备将重启，服务中断约 1-2 分钟")
        try:
            result = await runtime.client.async_post_device_reboot()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("重启设备失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "reboot", "result": result}

    async def _shutdown_device(call: "ServiceCall") -> "ServiceResponse":
        """⚠️ **关机**（不可逆）：设备彻底断电，需物理按键重启。

        ⚠️ 逆向推断实现，未实机验证；如果返回 1101 请反馈抓包。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (blocked := _reject_unconfirmed(call, CONFIRM_SHUTDOWN)) is not None:
            return blocked
        _LOGGER.warning("收到 shutdown_device 服务调用：设备将**彻底关机**，需物理重启（不可逆）")
        try:
            result = await runtime.client.async_post_device_shutdown()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("关机失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "shutdown", "result": result}

    async def _disk_info(call: "ServiceCall") -> "ServiceResponse":
        """磁盘诊断：**基础状态 + SMART 健康**。

        两个端点都跑一遍，合在一个响应里方便看。非 RAID 设备会跳过 RAID 查询。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        # ⚠️ 此前这里写死 ``{"ok": True}``，于是**两个子端点都失败时也报成功**
        # （实测本机：basic/smart 都返回 code=1，服务仍 ok=True）——调用方
        # 无法用 ok 判断成败，会误以为拿到了磁盘健康数据。改成按实际结果定。
        result: dict[str, Any] = {}
        ok = False
        try:
            result["basic"] = await runtime.client.async_get_disk_basic_info()
            ok = True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("diskBasicInfo 失败(可能未实现): %s", exc)
            result["basic_error"] = str(exc)
        try:
            result["smart"] = await runtime.client.async_get_disk_smart_info()
            ok = True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("diskSmartInfo 失败(可能未实现): %s", exc)
            result["smart_error"] = str(exc)
        result["ok"] = ok
        if not ok:
            result["error"] = "磁盘诊断两个端点均不可用（设备可能未实现该接口）"
        return result

    async def _raid_status(call: "ServiceCall") -> "ServiceResponse":
        """RAID 阵列状态。非 RAID 设备会返回 error（RAID 不是标配）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            result = await runtime.client.async_get_raid_status()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("RAID 查询失败(非 RAID 设备或未实现): %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "raid": result}

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
        """按关键字搜索文件空间（``/filesvc/search``，**实测可用**）。

        参数是穷举试出来的：关键字字段 ``query`` + 分页 ``limit``（不是 num）；
        两者与 ``offset`` 一起才通过，多带 ``category`` 等反而会报错。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_search_files(
                call.data["keyword"],
                category=call.data.get("category") or DEFAULT_CATEGORY,
                limit=int(call.data.get("limit") or 20),
                offset=int(call.data.get("offset") or 0),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        files = data.get("files") or []
        return {"ok": True, "keyword": call.data["keyword"],
                "count": data.get("count", len(files)), "items": files,
                "result": data}

    async def _task_status(call: "ServiceCall") -> "ServiceResponse":
        """查传输任务中心（只读）：filesvc（文件空间）/ trans（跨服务传输）。

        ``all_tasks: true`` 时走 ``/trans/getAllTask``（不带 taskTypes 筛选）。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if call.data.get("all_tasks"):
            try:
                tasks = await runtime.client.async_get_all_trans_tasks()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "service": "trans/all", "count": len(tasks),
                    "tasks": tasks}
        service = call.data.get("service") or "filesvc"
        types = call.data.get("task_types")
        if not types:
            # 抓包实据：客户端传的是整段，只传 [400] 拿不到完整历史
            types = TASK_TYPES_DEFAULT.get(service) or TASK_TYPES_DEFAULT["filesvc"]
        try:
            tasks = await runtime.client.async_get_task_status(
                [int(t) for t in types],
                category=int(call.data.get("task_category", 2)),
                service=service,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "service": service, "count": len(tasks), "tasks": tasks}

    async def _clean_task_records(call: "ServiceCall") -> "ServiceResponse":
        """清除任务中心的历史记录（只影响任务列表显示，不碰任何文件）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        ids = [int(i) for i in call.data["task_ids"]]
        _LOGGER.warning("清除任务中心历史记录 %d 条（不影响文件）", len(ids))
        try:
            result = await runtime.client.async_clean_task_records(
                ids, category=call.data.get("category") or DEFAULT_CATEGORY
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("清除任务记录失败(%s): %s", ids, exc)
            return {"ok": False, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        failed = (result.get("data") or {}).get("errorIdList") or []
        return {"ok": ok and not failed, "count": len(ids),
                "failed_ids": failed, "error": dev_err, "result": result}

    async def _retry_task(call: "ServiceCall") -> "ServiceResponse":
        """重试失败的传输任务（``POST /{business}/retryTask``）。

        报文格式取自插件反编译（``TaskRetryRequestBean``）：

            {"business": "filesvc", "taskId": 123, "taskType": 400}

        ``business`` 是任务所属域：``filesvc`` / ``gallery`` / ``trans`` /
        ``safebox``（``task_status`` 的 ``service`` 就是同一组取值）。
        ``taskId`` 与 ``taskType`` 从 ``task_status`` 返回的列表里取。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        task_id = int(call.data["task_id"])
        task_type = int(call.data["task_type"])
        business = str(call.data.get("business") or "filesvc").strip() or "filesvc"
        # 先从任务中心查同一条任务的 transId：App 在部分任务类型上会带上它，
        # 带上更接近真实报文；查不到就退回最简报文（已被设备接受）。
        trans_id = call.data.get("trans_id")
        if not trans_id:
            try:
                types = TASK_TYPES_DEFAULT.get(business) or TASK_TYPES_DEFAULT["filesvc"]
                tasks = await runtime.client.async_get_task_status(
                    [int(t) for t in types], service=business
                )
                for item in tasks:
                    if int(item.get("taskId", -1)) == task_id:
                        trans_id = item.get("transId")
                        break
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("查任务 transId 失败（继续用最简报文）: %s", exc)
        _LOGGER.warning(
            "重试任务 taskId=%s taskType=%s business=%s transId=%s",
            task_id,
            task_type,
            business,
            trans_id or "-",
        )
        try:
            result = await runtime.client.async_retry_task(
                task_id, task_type, business=business, trans_id=trans_id
            )
        except Exception as exc:  # noqa: BLE001
            # 设备对非 0 业务码是**抛异常**（见 api/device.py 的 _request），
            # 所以这里要自己把上下文补齐，别只回一句 error。
            _LOGGER.error("重试任务失败(taskId=%s): %s", task_id, exc)
            return {
                "ok": False,
                "task_id": task_id,
                "task_type": task_type,
                "business": business,
                "trans_id": trans_id,
                "error": str(exc),
            }
        ok, dev_err = _device_ok(result)
        return {
            "ok": ok,
            "task_id": task_id,
            "task_type": task_type,
            "business": business,
            "trans_id": trans_id,
            "error": dev_err,
            "result": result,
        }

    async def _plugin_install(call: "ServiceCall") -> "ServiceResponse":
        """安装市场里的插件（``POST /acelite/hap_add``）。

        只需给 ``app_id``（从 plugin_market 拿），其余字段自动补齐。
        也可直接给 ``plugin``（完整的 marketplace 项）跳过查询。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        app_id = str(call.data.get("app_id") or "").strip()
        download_url = str(call.data.get("download_url") or "").strip()

        # 自定义来源：直接给 download_url + pkg_name 即可（绕过市场查询）。
        # 用于验证「设备是否接受非官方来源的包」。
        if download_url:
            pkg_name = str(call.data.get("pkg_name") or "").strip()
            if not pkg_name:
                return {"ok": False, "error": "自定义来源需要同时提供 pkg_name"}
            plugin = {
                "appId": app_id or f"C{abs(hash(pkg_name)) % 10**18:018d}",
                "name": str(call.data.get("name") or pkg_name),
                "pkgName": pkg_name,
                "downloadURL": download_url,
                "iconURL": str(call.data.get("icon_url") or ""),
                "uiURL": str(call.data.get("ui_url") or ""),
                "versionCode": int(call.data.get("version_code") or 1),
                "versionName": str(call.data.get("version_name") or "0.0.1"),
            }
            _LOGGER.warning("按自定义来源安装: %s <- %s", pkg_name, download_url)
            try:
                result = await runtime.client.async_install_plugin(plugin)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "source": "custom", "pkg_name": pkg_name,
                        "download_url": download_url, "error": str(exc)}
            return {"ok": True, "source": "custom", "pkg_name": pkg_name,
                    "download_url": download_url, "plugin": plugin, "result": result}

        if not app_id:
            return {"ok": False,
                    "error": "需要 app_id（见 plugin_market），或给 download_url + pkg_name 走自定义来源"}
        _LOGGER.warning("开始安装插件 appId=%s", app_id)
        try:
            result = await runtime.client.async_install_plugin_by_id(app_id)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("安装插件失败(%s): %s", app_id, exc)
            return {"ok": False, "app_id": app_id, "error": str(exc)}
        return {"ok": True, "app_id": app_id, "result": result}

    async def _plugin_uninstall(call: "ServiceCall") -> "ServiceResponse":
        """卸载 / 取消 / 暂停插件（``hap_delete`` / ``hap_cancel`` / ``hap_pause``）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        app_id = str(call.data.get("app_id") or "").strip()
        pkg_name = str(call.data.get("pkg_name") or "").strip()
        action = str(call.data.get("action") or "delete")
        if not app_id or not pkg_name:
            return {"ok": False, "error": "需要 app_id 与 pkg_name（见 plugin_all 的 installedHap）"}
        _LOGGER.warning("插件操作 %s: %s (%s)", action, pkg_name, app_id)
        try:
            result = await runtime.client.async_uninstall_plugin(
                app_id, pkg_name, action=action
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "app_id": app_id, "action": action, "error": str(exc)}
        return {"ok": True, "app_id": app_id, "action": action, "result": result}

    async def _plugin_market(call: "ServiceCall") -> "ServiceResponse":
        """应用市场可安装插件（``GET /acelite/market_infos``，只读）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_get_plugin_market()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        count = len(data) if isinstance(data, (list, dict)) else 0
        return {"ok": True, "count": count, "data": data}

    async def _plugin_all(call: "ServiceCall") -> "ServiceResponse":
        """市场 + 已安装合并视图（``GET /acelite/all_infos``，只读）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_get_plugin_all()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        count = len(data) if isinstance(data, (list, dict)) else 0
        return {"ok": True, "count": count, "data": data}

    async def _plugin_xunlei(call: "ServiceCall") -> "ServiceResponse":
        """迅雷插件信息（``GET /acelite/xunlei_infos``，只读）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_get_plugin_xunlei()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "data": data}

    async def _dynamic_info(call: "ServiceCall") -> "ServiceResponse":
        """动态 / 时光轴 / 回忆（``GET /gallery/getDynamicInfo``）。

        ``data_type`` 是动态类型枚举，插件里由
        ``AlbumDynamicApi$Param.setDataType()`` 决定；这里默认 0，
        并支持 ``probe: true`` 一次性把 0~9 都试一遍，方便在真机上
        摸清哪个值有数据（只读，安全）。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        owner_id = int(call.data.get("owner_id") or 0)

        if call.data.get("probe"):
            results: dict[str, Any] = {}
            for dt in range(0, 10):
                try:
                    data = await runtime.client.async_get_dynamic_info(
                        owner_id=owner_id, data_type=dt
                    )
                    size = len(data) if isinstance(data, (list, dict)) else 0
                    results[str(dt)] = {"ok": True, "size": size,
                                        "sample": str(data)[:200]}
                except Exception as exc:  # noqa: BLE001
                    results[str(dt)] = {"ok": False, "error": str(exc)[:120]}
            return {"ok": True, "probe": True, "owner_id": owner_id,
                    "results": results}

        data_type = int(call.data.get("data_type") or 0)
        try:
            data = await runtime.client.async_get_dynamic_info(
                owner_id=owner_id, data_type=data_type
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("动态信息拉取失败(dataType=%s): %s", data_type, exc)
            return {"ok": False, "data_type": data_type, "error": str(exc)}
        count = len(data) if isinstance(data, (list, dict)) else 0
        return {"ok": True, "data_type": data_type, "owner_id": owner_id,
                "count": count, "data": data}

    async def _add_to_album(call: "ServiceCall") -> "ServiceResponse":
        """把**已有的照片**加进相册（``/gallery/addAlbumMemb``）。

        加的是**相册域的 fileId**（不是文件空间的 fid）：从相册浏览或
        ``query_files source=photos`` 里取。重复添加返回 suc（幂等），
        所以以 ``failIds`` 为空为准。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        ids = [int(i) for i in call.data["file_ids"]]
        album_id = int(call.data["album_id"])
        _LOGGER.warning("把 %d 张照片加入相册 %s", len(ids), album_id)
        try:
            result = await _client_for(runtime, call).async_add_album_members(
                album_id, ids,
                album_name=call.data.get("album_name") or "",
                album_type=int(call.data.get("album_type") or 6),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("加入相册失败(%s): %s", album_id, exc)
            return {"ok": False, "album_id": album_id, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        failed = result.get("failIds") or []
        suc = result.get("sucIds") or []
        return {"ok": ok and not failed, "album_id": album_id,
                "added": len(suc), "failed_ids": failed,
                "error": dev_err, "result": result}

    async def _album_info(call: "ServiceCall") -> "ServiceResponse":
        """单个相册的元数据 + **封面原图路径**（相册列表里 coverInfo 为空时的兜底）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            data = await runtime.client.async_get_album_cfg(
                int(call.data["album_id"]),
                int(call.data.get("album_type") or 6),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        cover = (data.get("coverInfo") or [{}])[0] if data.get("coverInfo") else {}
        return {"ok": True, "album_id": call.data["album_id"],
                "name": data.get("albumName"),
                "cover_original": cover.get("hdcFilePath"),
                "cover_large": cover.get("lcdFilePath"),
                "result": data}

    async def _album_changes(call: "ServiceCall") -> "ServiceResponse":
        """相册增量表：哪些相册有变动（只读）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            items = await runtime.client.async_get_album_inc(
                int(call.data.get("pre_id") or 0),
                int(call.data.get("num") or 500),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "count": len(items), "items": items}

    async def _share_to_person(call: "ServiceCall") -> "ServiceResponse":
        """把照片共享到人物相册（``ownerId`` 从设备用户列表取）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        ids = [int(i) for i in call.data["file_ids"]]
        _LOGGER.warning("共享 %d 张照片到人物 ownerId=%s", len(ids),
                        call.data.get("owner_id"))
        try:
            result = await _client_for(runtime, call).async_add_share_to_person(
                int(call.data["album_id"]), ids,
                int(call.data["owner_id"]),
                album_name=call.data.get("album_name") or "",
                album_type=int(call.data.get("album_type") or 6),
                file_names=call.data.get("file_names"),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("共享到人物失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(ids), "error": dev_err, "result": result}

    async def _list_albums(call: "ServiceCall") -> "ServiceResponse":
        """列相册。⚠️ ``album_type=0`` **不含 type=6**（用户/共享相册），要取全就传 6 或 -1。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        atype = int(call.data.get("album_type", 0))
        try:
            items = await runtime.client.async_get_album_list(atype)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "album_type": atype, "count": len(items), "items": items}

    async def _add_album(call: "ServiceCall") -> "ServiceResponse":
        """创建相册（逆向推断实现，未实机验证；body={albumName, albumType}）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        name = str(call.data.get("name", "") or "").strip()
        if not name:
            return {"ok": False, "error": "name 必填"}
        album_type = int(call.data.get("album_type", 0))
        try:
            result = await _client_for(runtime, call).async_add_album(
                name=name, album_type=album_type
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("创建相册失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "name": name, "error": dev_err, "result": result}

    async def _del_album(call: "ServiceCall") -> "ServiceResponse":
        """**删除相册**（⚠️ 不可逆；逆向推断实现，未实机验证）。

        ⚠️ 必须 ``confirm: "DELETE_ALBUM"``（2026-10-29 补）：此前没有任何
        确认门槛，与其他四个不可逆服务（关机/重启/清空回收站/永久删除）的
        防护不一致。删相册比删文件更狠 —— 文件删了还在回收站，相册删了
        整本索引就没了，成员共享的那些照片也一起从相册视图消失。
        """
        if (blocked := _reject_unconfirmed(call, CONFIRM_DELETE_ALBUM)) is not None:
            return blocked
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        album_id = int(call.data.get("album_id", 0))
        if not album_id:
            return {"ok": False, "error": "album_id 必填"}
        album_type = int(call.data.get("album_type", 0))
        try:
            result = await _client_for(runtime, call).async_del_album(
                album_id=album_id, album_type=album_type
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("删除相册失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "album_id": album_id,
                "error": dev_err, "result": result}

    async def _search_album_photos(call: "ServiceCall") -> "ServiceResponse":
        """**相册内照片搜索**（关键词，逆向推断，未实机验证）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        keyword = str(call.data.get("keyword", "")).strip()
        if not keyword:
            return {"ok": False, "error": "keyword 必填"}
        album_type = int(call.data.get("album_type", 0))
        num = int(call.data.get("num", 100))
        page = int(call.data.get("page", 1))
        try:
            result = await runtime.client.async_album_search(
                keyword=keyword, album_type=album_type, num=num, page=page,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("相册搜索失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "keyword": keyword,
                "result": result}

    async def _rename_media(call: "ServiceCall") -> "ServiceResponse":
        """**重命名照片/视频**（modifyFileAttr，逆向推断，未实机验证）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        file_ids = call.data.get("file_ids") or call.data.get("file_id")
        if not file_ids:
            return {"ok": False, "error": "file_id(s) 必填"}
        if isinstance(file_ids, (int, str)):
            file_ids = [file_ids]
        new_name = call.data.get("new_name")
        if not new_name:
            return {"ok": False, "error": "new_name 必填"}
        try:
            result = await runtime.client.async_modify_file_attr(
                file_ids=[int(i) for i in file_ids], new_name=new_name,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("重命名失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "new_name": new_name, "result": result}

    async def _remove_album_members(call: "ServiceCall") -> "ServiceResponse":
        """**把照片移出相册**（对称于 add_album_members）。

        ⚠️ 2026-10-30 真机：只给 ``{albumId, albumType, membs}`` 会返回
        ``30110``；已按 ``addAlbumMemb`` 的成功形态补上
        ``clientType`` / ``deviceId`` / ``albumName`` / ``addTime``。

        语义：**解除关联，不删原图**。照片仍留在「照片」总相册和文件空间里。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        album_id = int(call.data.get("album_id", 0))
        if not album_id:
            return {"ok": False, "error": "album_id 必填"}
        album_type = int(call.data.get("album_type", 0))
        file_ids = call.data.get("file_ids") or call.data.get("file_id")
        if not file_ids:
            return {"ok": False, "error": "file_id(s) 必填"}
        if isinstance(file_ids, (int, str)):
            file_ids = [file_ids]
        try:
            # ⚠️ 必须 `_client_for(runtime, call)`：schema 已声明 account，
            # 用 `runtime.client` 会把「从账号 B 的相册移出照片」打到主账号的
            # 同名相册上 —— 参数收了却不用，比报错更危险（静默动错账号）。
            result = await _client_for(runtime, call).async_del_album_memb(
                album_id=album_id, album_type=album_type,
                file_ids=[int(i) for i in file_ids],
                album_name=str(call.data.get("album_name") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("移除相册照片失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "removed_count": len(file_ids),
                "error": dev_err, "result": result}

    async def _hide_albums(call: "ServiceCall") -> "ServiceResponse":
        """**隐藏/显示相册**（modifyAlbumsHiddenStatus，逆向推断，未实机验证）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        album_ids = call.data.get("album_ids") or call.data.get("album_id")
        if not album_ids:
            return {"ok": False, "error": "album_id(s) 必填"}
        if isinstance(album_ids, (int, str)):
            album_ids = [album_ids]
        album_type = int(call.data.get("album_type", 0))
        hidden = bool(call.data.get("hidden", True))
        try:
            result = await runtime.client.async_hide_albums(
                album_ids=[int(i) for i in album_ids],
                album_type=album_type, hidden=hidden,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("隐藏相册失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "hidden": hidden,
                "album_ids": [int(i) for i in album_ids],
                "result": result}

    async def _album_rename(call: "ServiceCall") -> "ServiceResponse":
        """**相册重命名**（``POST /gallery/albumCfg``）。

        ✅ 真机实据（2026-10-30，官方客户端抓包 + 设备侧确认）：
        ``{albumId:29, albumName:"345234", albumType:6, clientType:3,
        deviceId:"...", modifyTime:0, toShareAlbum:0}`` → 列表里名字已变。

        与 ``rename_path``（改文件/目录名）、``rename_media``（改单张照片名）
        是三件事：相册在设备上是**独立的集合对象**，走相册域的 albumCfg。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        album_id = int(call.data.get("album_id") or 0)
        new_name = str(call.data.get("new_name") or "").strip()
        if not album_id:
            return {"ok": False, "error": "album_id 必填"}
        if not new_name:
            return {"ok": False, "error": "new_name 不能为空"}
        album_type = int(call.data.get("album_type") or ALBUM_TYPE_USER)
        try:
            result = await _client_for(runtime, call).async_modify_album(
                album_id=album_id, album_name=new_name, album_type=album_type,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("相册重命名失败(%s): %s", album_id, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "album_id": album_id, "album_name": new_name,
                "error": dev_err, "result": result}

    async def _album_set_cover(call: "ServiceCall") -> "ServiceResponse":
        """**设置相册封面**（``POST /gallery/albumCfg`` + ``coverId``）。

        ✅ 真机实据（2026-10-30 09:12，官方客户端「设为封面」）::

            {"albumId":29,"albumType":6,"clientType":3,
             "coverId":281474976736133,"deviceId":"...","modifyTime":0,
             "toShareAlbum":0}

        ⚠️ **不能带 ``albumName``**：改名和设封面是同一个端点但两套 body，
        混着传（albumName + coverId）设备返回 ``30111``。之前按"字段缺了"
        的思路反查相册名补进去，反而是错的 —— 这是"多送字段"，不是"少送"。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        album_id = int(call.data.get("album_id") or 0)
        cover_id = call.data.get("cover_id")
        if not album_id:
            return {"ok": False, "error": "album_id 必填"}
        if cover_id is None:
            return {"ok": False, "error": "cover_id 必填（相册域 fileId）"}
        album_type = int(call.data.get("album_type") or ALBUM_TYPE_USER)
        client = _client_for(runtime, call)
        try:
            result = await client.async_modify_album(
                album_id=album_id, album_type=album_type, cover_id=int(cover_id),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("设置相册封面失败(%s): %s", album_id, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "album_id": album_id, "cover_id": int(cover_id),
                "error": dev_err, "result": result}

    async def _list_all_albums(call: "ServiceCall") -> "ServiceResponse":
        """**列出全部相册**（含隐藏/系统/推荐，比 list_albums 全。逆向推断，未实机验证）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            albums = await runtime.client.async_get_all_album_list()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("列出全部相册失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "album_count": len(albums), "albums": albums}

    async def _device_users(call: "ServiceCall") -> "ServiceResponse":
        """**设备家庭成员列表**（``/account/userManageInfo``）。

        返回数组，每项含 ``level``（1=管理员 / 2=成员）、``nick``、``usage``
        （已用 MB）、``state``。``share_to_person`` 需要的就是这里的
        ``ownerId``（与相册 ``ownerId`` 同源）。

        ✅ 实测可用（2026-10-30）：返回 2 个成员（10001 管理员 / 10002 成员）。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            users = await _client_for(runtime, call).async_get_device_users()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("列家庭成员失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        brief = [
            {
                "userId": u.get("ownerId") or u.get("userId") or u.get("id"),
                "nick": u.get("nick") or u.get("nickName") or "",
                "level": u.get("level"),
                "usage": u.get("usage"),
            }
            for u in users or []
        ]
        return {"ok": True, "count": len(brief), "users": brief}

    async def _share_files_to_person(call: "ServiceCall") -> "ServiceResponse":
        """**按文件**分享给指定设备用户（shareToPerson，sync 版）。

        ⚠️ 与 ``_share_to_person``（按相册）是**两个不同端点语义**。
        2026-10-29 修：本函数此前与 ``_share_to_person`` **同名** ``_share_to_person``，
        Python 中后定义覆盖先定义，导致：

        * 注册表里两份 schema 争抢同一个服务名 ``share_to_person``，
          最终生效的是**本函数 + 本函数的 schema**；
        * 而 ``services.yaml`` 文档写的是 ``album_id``/``owner_id`` ——
          **文档与实际行为不符**，按文档调用必然报「receiver_user_id 必填」。

        现改为独立服务名 ``share_files_to_person``，两者各归其位。
        (逆向推断，未实机验证)
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        file_ids = call.data.get("file_ids") or call.data.get("file_id")
        if not file_ids:
            return {"ok": False, "error": "file_id(s) 必填"}
        if isinstance(file_ids, (int, str)):
            file_ids = [file_ids]
        receiver_ids = call.data.get("receiver_user_ids") or call.data.get("receiver_user_id")
        if not receiver_ids:
            return {"ok": False, "error": "receiver_user_id(s) 必填"}
        if isinstance(receiver_ids, str):
            receiver_ids = [receiver_ids]
        auto_expire_days = int(call.data.get("auto_expire_days", 0))
        try:
            result = await runtime.client.async_share_to_person(
                file_ids=[int(i) for i in file_ids],
                receiver_user_ids=receiver_ids,
                auto_expire_days=auto_expire_days,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("分享失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "receiver_count": len(receiver_ids),
                "file_count": len(file_ids), "result": result}

    async def _merge_face_albums(call: "ServiceCall") -> "ServiceResponse":
        """**合并人脸相册**（mergeFaceAlbums，有人脸相册的用户才需要。逆向推断，未实机验证）。

        ⚠️ 不可逆，必须 ``confirm: "MERGE_FACE_ALBUMS"``（2026-10-29 补）：
        源相册被并进目标相册后就没了，设备不提供拆分接口。把两个人的脸
        合到一起之后，只能靠手工重建相册才能分开。
        """
        if (blocked := _reject_unconfirmed(call, CONFIRM_MERGE_FACE_ALBUMS)) is not None:
            return blocked
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        target_id = int(call.data.get("target_album_id", 0))
        if not target_id:
            return {"ok": False, "error": "target_album_id 必填"}
        source_ids = call.data.get("source_album_ids") or call.data.get("source_album_id")
        if not source_ids:
            return {"ok": False, "error": "source_album_id(s) 必填"}
        if isinstance(source_ids, (int, str)):
            source_ids = [source_ids]
        try:
            result = await runtime.client.async_merge_face_albums(
                target_id=target_id,
                source_ids=[int(i) for i in source_ids],
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("合并人脸相册失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "target_album_id": target_id,
                "merged_count": len(source_ids), "result": result}

    async def _recent_files(call: "ServiceCall") -> "ServiceResponse":
        """**最近文件**（设备侧最近访问/修改的文件列表）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        limit = int(call.data.get("limit", 50))
        try:
            result = await runtime.client.async_get_recent_files(limit=limit)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("最近文件查询失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        files = result.get("data") if isinstance(result, dict) else None
        if not isinstance(files, list):
            files = []
        return {"ok": True, "count": len(files), "files": files}

    async def _installed_plugins(call: "ServiceCall") -> "ServiceResponse":
        """**已装插件列表**（acelite 接口）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            result = await runtime.client.async_get_installed_plugins()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("已装插件查询失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": result}

    async def _all_trans_tasks(call: "ServiceCall") -> "ServiceResponse":
        """**全量传输任务列表**（trans 域，含 move/copy/upload 等）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            tasks = await runtime.client.async_get_all_trans_tasks()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("传输任务查询失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "task_count": len(tasks), "tasks": tasks}

    async def _album_photos(call: "ServiceCall") -> "ServiceResponse":
        """列相册内的照片（``getAlbumInfo``，含路径与缩略图）。支持游标分页。"""
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        try:
            res = await runtime.client.async_get_album_photos(
                int(call.data["album_id"]),
                int(call.data.get("album_type") or 6),
                device_id=_entry_device_id(entry),
                last_cre_time=int(call.data.get("last_cre_time") or 0),
                last_row_id=int(call.data.get("last_row_id") or 0),
                num=int(call.data.get("num") or ALBUM_PAGE_SIZE),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        photos = res.get("photos") or []
        return {"ok": True, "count": len(photos), "items": photos,
                "lastCreTime": res.get("lastCreTime"),
                "lastRowId": res.get("lastRowId")}

    async def _list_trash(call: "ServiceCall") -> "ServiceResponse":
        """回收站查询（``queryBin``，返回**完整元数据**含 assets / 原图路径）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            res = await runtime.client.async_query_bin(
                int(call.data.get("offset") or 0),
                int(call.data.get("num") or 100),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        # ⚠️ 该接口直接返回**列表**（不是 dict），与媒体源 _browse_trash 的取法一致
        items = [x for x in (res or []) if isinstance(x, dict)]
        return {"ok": True, "count": len(items), "items": items}

    async def _duplicate_scan_result(call: "ServiceCall") -> "ServiceResponse":
        """查询重复照片扫描结果（只读，需先跑 ``duplicate_scan`` 的 start）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            res = await runtime.client.async_query_duplicate_scan(
                int(call.data.get("task_id") or 0),
                int(call.data.get("offset") or 0),
                int(call.data.get("limit") or 20),
                int(call.data.get("filter") or 0),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": res}

    async def _device_diagnostics(call: "ServiceCall") -> "ServiceResponse":
        """设备诊断快照：错误码 / 维修模式 / Samba 共享状态（排障用）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        client = runtime.client
        out: dict[str, Any] = {}
        for key, getter in (
            ("dev_err_code", client.async_get_dev_err_code),
            ("repair_mode", client.async_get_repair_mode),
            ("samba_public", client.async_get_samba_public),
            ("samba_user", client.async_get_samba_user),
        ):
            try:
                out[key] = await getter()
            except Exception as exc:  # noqa: BLE001  单项失败不影响其它
                out[key] = {"error": str(exc)}
        return {"ok": True, "result": out}

    async def _get_task(call: "ServiceCall") -> "ServiceResponse":
        """按 taskId 查单个任务详情（``/<service>/getTaskStatus``）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        try:
            result = await runtime.client.async_get_single_task(
                int(call.data["task_id"]),
                category=call.data.get("category") or DEFAULT_CATEGORY,
                service=call.data.get("service") or "filesvc",
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        ok, dev_err = _device_ok(result)
        tasks = (result.get("data") or {}).get("tasks") or []
        return {"ok": ok, "count": len(tasks), "tasks": tasks,
                "error": dev_err, "result": result}

    async def _photo_info(call: "ServiceCall") -> "ServiceResponse":
        """把相册照片的 ``fileId`` 换成完整元数据（含 ``hdcFilePath`` 原图路径）。"""
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        ids = [int(i) for i in call.data["file_ids"]]
        try:
            items = await runtime.client.async_get_photos_info(ids)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("取照片元数据失败(%s): %s", ids, exc)
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "count": len(items), "items": items}

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

    async def _resolve_recycle_rids(
        hass: HomeAssistant, data: dict[str, Any], category: str
    ) -> list[int]:
        """从 call.data 里解析出回收站条目 rid 列表（三个回收站服务共用）。

        接受三种输入：
        * ``rids`` / ``rid``（int 或 str 或 list）—— 直接用
        * ``paths`` / ``names`` —— 从回收站列表里按 name / path 匹配
        * 都没给 —— 自动调 ``async_list_recycle`` 取第一条（
          ``recycleDelFiles`` 的 action=clear 只需要任意 1 个 rid，
          App UI 上也是取第一条就 break）
        """
        # 优先用直接给的 rid / rids
        raw = data.get("rids") or data.get("rid")
        if raw is not None:
            items = raw if isinstance(raw, list) else [raw]
            return [int(r) for r in items if r not in (None, "")]
        # 按 paths / names 匹配
        wanted = _paths(data) or [
            str(n) for n in (data.get("names") or [])
        ]
        # 用闭包里已有的 _pick / runtime，懒加载避免循环导入
        runtime, _, err = _pick(hass, data.get("entry_id"))
        if err:
            return []
        try:
            items = await runtime.client.async_list_recycle(
                # recycleDelFiles category 口径：空串=我的文件，public=共享；
                # batchOperation 用 user，这里把 user 映射成空串
                category=("" if category == "user" else category),
                limit=500,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("读取回收站失败: %s", exc)
            return []
        if not wanted:
            # 没给匹配条件 → 自动取第一条（给 empty_recycle / clear 用）
            first = items[0] if items else None
            if first and first.get("rid") is not None:
                return [int(first["rid"])]
            return []

        def _match(item: dict[str, Any]) -> bool:
            iname = str(item.get("name") or "")
            ipath = str(item.get("path") or "")
            return any(
                w.rstrip("/") == iname or w.rstrip("/").endswith(iname)
                or (ipath and ipath.rstrip("/") == w.rstrip("/"))
                or (ipath and ipath.rstrip("/").endswith(w.rstrip("/")))
                for w in wanted
            )

        hits = [i for i in items if _match(i)]
        return [int(i.get("rid")) for i in hits if i.get("rid") is not None]

    async def _delete_recycle_items(call: "ServiceCall") -> "ServiceResponse":
        """永久删除回收站里的条目（``recycleDelFiles?action=remove``）。

        ⚠️ **不可逆**：删完回收站就没了，进文件空间恢复不了。

        逆向自智慧生活 App 插件 ``517616675.jar``（2026-10-13）：
        body ``{"action":"remove","files":[rid1, rid2, ...]}``。

        ``rids`` 可直接给（数字或字符串都转 int）；也可给 ``paths`` /
        ``names``，由回收站列表里自动匹配。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (blocked := _reject_unconfirmed(call, CONFIRM_PERMANENT_DELETE)) is not None:
            return blocked
        cat = call.data.get("category") or DEFAULT_CATEGORY
        rids = await _resolve_recycle_rids(hass, call.data, cat)
        if not rids:
            return {"ok": False, "error": "没解析到任何 rid"}
        _LOGGER.warning("permanent_delete_recycle_items：%d 条回收站条目永久删除",
                        len(rids))
        try:
            result = await runtime.client.async_recycle_operate(
                action="remove", rids=rids, category=cat,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("永久删除回收站条目失败(rids=%s): %s", rids, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(rids),
                "error": dev_err, "result": result}

    async def _empty_recycle(call: "ServiceCall") -> "ServiceResponse":
        """清空整个回收站（``recycleDelFiles?action=clear``）。

        ⚠️ **不可逆**：删完回收站就没了，所有条目都永久消失。

        逆向自智慧生活 App 插件 ``517616675.jar``（2026-10-13）：
        body ``{"action":"clear","files":[任意1个rid]}``——App UI 上只取
        回收站列表第一条的 rid 就 break 了，所以这里也只取第一条。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (blocked := _reject_unconfirmed(call, CONFIRM_EMPTY_RECYCLE)) is not None:
            return blocked
        cat = call.data.get("category") or DEFAULT_CATEGORY
        _LOGGER.warning("empty_recycle：清空整个回收站（所有条目永久删除，不可逆）")
        # clear 需要至少 1 个 rid（App UI 上是取列表第一条）
        rids = await _resolve_recycle_rids(hass, call.data, cat)
        if not rids:
            return {"ok": False, "error":
                    "clear 需要至少 1 个 rid（随便哪个都行），但回收站为空或没给 rid"}
        try:
            result = await runtime.client.async_recycle_operate(
                action="clear", rids=[rids[0]], category=cat,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("清空回收站失败: %s", exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "action": "clear",
                "error": dev_err, "result": result}

    # ------------------------------------------------------------------
    # 文件空间写入
    # ------------------------------------------------------------------
    def _safe_device_path(raw: object) -> tuple[str, str | None]:
        """校验设备内路径，返回 (规范化路径, 错误信息)。

        服务的路径来自自动化/脚本输入，这里挡掉两类问题：
          * 越界：含 ``..`` 段（如 ``/file/../../etc``）
          * 越界：不是 ``/file/`` 起头（设备只认这个文件空间根）
        """
        text = str(raw or "").strip()
        if not text:
            return "", "路径不能为空"
        if ".." in text.split("/"):
            return "", f"路径不允许包含 '..'：{text}"
        if not text.startswith("/file/"):
            return "", f"路径必须以 /file/ 开头：{text}"
        norm = "/" + "/".join(x for x in text.split("/") if x)
        if text.endswith("/"):
            norm += "/"
        return norm, None

    def _allowed_upload_dir(hass: Any) -> str:
        """``upload_file`` 的 ``local_path`` 允许读取的根目录。

        ⚠️ 安全：``local_path`` 由调用者给，不限制就能读容器内**任意文件** ——
        包括 ``secrets.yaml``、``.storage``（含令牌与凭据），等于把读文件的
        口子开给任何一条自动化。这里限定在 HA 配置目录下的 ``uploads`` 子目录。
        """
        import os as _os  # noqa: PLC0415

        return _os.path.realpath(hass.config.path("uploads"))

    async def _create_folder(call: "ServiceCall") -> "ServiceResponse":
        """新建目录（``/filesvc/mkdir``）—— 支持一次给多个路径（逐个建，部分失败也如实回报）。

        ⚠️ 设备侧 ``/filesvc/createDirs``（批量建目录）**参数没解出**：
        `{paths:[..]}`、`{dirs:[..]}`、`{path:[..],redundancy:0}`、`tasks[]`
        四种形态实测全部 ``1101``，所以批量只能在这里循环调 mkdir。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        paths = [str(p) for p in (call.data.get("paths") or [])]
        if call.data.get("path"):
            paths.append(str(call.data["path"]))
        if not paths:
            return {"ok": False, "error": "path 与 paths 至少给一个"}
        category = call.data.get("category") or DEFAULT_CATEGORY
        created: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for raw in paths:
            norm, bad = _safe_device_path(raw)
            if bad:
                failed.append({"path": str(raw), "error": bad})
                continue
            try:
                data = await runtime.client.async_mkdir(norm, category=category)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("新建目录失败(%s): %s", norm, exc)
                failed.append({"path": norm, "error": str(exc)})
                continue
            created.append({
                "path": norm,
                "fid": (data or {}).get("fid"),
            })
        await runtime.fast.async_request_refresh()
        return {"ok": not failed, "created": created, "failed": failed}

    async def _rename_path(call: "ServiceCall") -> "ServiceResponse":
        """重命名（``/filesvc/rename``）：``old_path`` → ``new_path``。

        目录要带尾斜杠（``/file/旧名/``），文件不带。
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        old_path, bad1 = _safe_device_path(call.data["old_path"])
        new_path, bad2 = _safe_device_path(call.data["new_path"])
        if bad1:
            return {"ok": False, "error": bad1}
        if bad2:
            return {"ok": False, "error": bad2}
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

    async def _copy_paths(call: "ServiceCall") -> "ServiceResponse":
        """同空间复制文件/目录（``/trans/copy``，异步任务；目标目录需已存在）。"""
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        paths = _paths(call)
        dest = call.data["dest_dir"]
        category = call.data.get("category") or DEFAULT_CATEGORY
        try:
            result = await runtime.client.async_trans_copy(
                paths, dest, _entry_device_id(entry),
                src_category=category,
                dst_category=call.data.get("dest_category") or category,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("复制失败(%s → %s): %s", paths, dest, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(paths), "dest_dir": dest,
                "error": dev_err, "result": result}

    async def _delete_paths(call: "ServiceCall") -> "ServiceResponse":
        """删除文件空间里的文件/目录。

        * ``skip_recycle=False``（默认）→ **进回收站**（可逆，用 recover_recycle 还原）
        * ``skip_recycle=True`` → **永久删除**（逆向实据：batchOperation body 加 operationType=force，2026-10-13）
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        paths = _paths(call)
        category = call.data.get("category") or DEFAULT_CATEGORY
        skip = bool(call.data.get("skip_recycle"))
        # ⚠️ ``skip_recycle=True`` 是**永久删除**，与 empty_recycle /
        # permanent_delete_recycle_items 同级不可逆，必须同样要确认
        # （2026-10-29 补：此前只有另外两个要确认，这条漏了，防护不一致）。
        if skip and (blocked := _reject_unconfirmed(
            call, CONFIRM_PERMANENT_DELETE
        )) is not None:
            return blocked
        _LOGGER.warning("delete_paths：%d 项 %s",
                        len(paths),
                        "直接永久删除（skip_recycle=True）" if skip
                        else "移入回收站（可用 recover_recycle 还原）")
        try:
            result = await runtime.client.async_delete_paths(
                paths, _entry_device_id(entry),
                to_recycle=not skip, category=category,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("删除路径失败(%s): %s", paths, exc)
            return {"ok": False, "error": str(exc)}
        await runtime.fast.async_request_refresh()
        ok, dev_err = _device_ok(result)
        return {"ok": ok, "count": len(paths),
                "to_recycle": not skip,
                "error": dev_err, "result": result}

    async def _photos_table_full(call: "ServiceCall") -> "ServiceResponse":
        """全量照片表（``/gallery/getFullPhotosInfoTable``）。

        面板首次加载 / 本地缓存重建用：一次拉一页（默认 500 条），而不是
        逐张 ``album_photos`` 往返（2.5 万张不可行）。

        ``row_id`` 传上一次返回的 ``lastRowId`` 翻下一页；到 0 条即到底。

        ⚠️ **实测本机返回 code=30102**（端点确认存在，但设备侧有额外要求；
        ``clientType``/``deviceId``/``num`` 都试过仍 30102）。所以本服务目前
        在多数机型上会直接返回 ok=False —— 保留它是为了记录该能力，待抓包
        补齐参数后即可用。**不声称可用。**
        """
        runtime, _, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        row_id = int(call.data.get("row_id") or 0)
        num = int(call.data.get("num") or 500)
        try:
            res = await runtime.client.async_get_photos_table_full(row_id, num)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "row_id": row_id}
        return {"ok": True, **res, "row_id": row_id}

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
            # ⚠️ 安全：限定可读目录，避免读到 secrets.yaml / .storage 里的令牌
            import os as _os  # noqa: PLC0415

            root = _allowed_upload_dir(hass)
            real = _os.path.realpath(local_path)
            if not (real == root or real.startswith(root + _os.sep)):
                return {
                    "ok": False,
                    "error": f"local_path 只允许读取 {root} 下的文件（防止读到敏感配置）",
                }

            def _read() -> bytes:
                with open(real, "rb") as fh:
                    return fh.read(MAX_UPLOAD_BYTES + 1)

            try:
                payload = await hass.async_add_executor_job(_read)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"读取失败: {exc}"}
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

    async def _download_file(call: "ServiceCall") -> "ServiceResponse":
        """从设备文件空间下载文件到 HA 主机（流式落盘，内存 ≈ 一个分块）。

        与 ``upload_file`` 对称：``local_path`` 限定在 ``uploads`` 目录下
        （防止写到任意路径覆盖 ``secrets.yaml`` / ``.storage``），父目录
        不存在时自动创建；``local_path`` 给目录时自动取设备路径的文件名。
        失败时清掉半截文件，不留误导性残留。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        norm, perr = _safe_device_path(str(call.data["path"]))
        if perr:
            return {"ok": False, "error": perr}
        if norm.endswith("/"):
            return {"ok": False, "error": "path 必须是文件，不能是目录"}

        import os as _os  # noqa: PLC0415

        from .transfer import download_stream  # noqa: PLC0415

        root = _allowed_upload_dir(hass)
        dest = str(call.data["local_path"])
        # 给目录（带尾斜杠或已存在）时，取设备路径的基名作为文件名
        if dest.rstrip("/\\").endswith(("/", "\\")) or _os.path.isdir(dest):
            name = _os.path.basename(norm.rstrip("/")) or "download.bin"
            dest = _os.path.join(dest, name)
        real = _os.path.realpath(dest)
        if not (real == root or real.startswith(root + _os.sep)):
            return {
                "ok": False,
                "error": f"local_path 只允许写入 {root} 下的文件（防止覆盖敏感配置）",
            }

        def _prepare() -> None:
            _os.makedirs(_os.path.dirname(real), exist_ok=True)

        try:
            await hass.async_add_executor_job(_prepare)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"创建目录失败: {exc}"}

        category = call.data.get("category") or DEFAULT_CATEGORY
        total = 0
        try:
            fh = await hass.async_add_executor_job(open, real, "wb")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"打开目标文件失败: {exc}"}
        try:
            async for block in download_stream(
                runtime.client, norm, category=category
            ):
                await hass.async_add_executor_job(fh.write, block)
                total += len(block)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("下载失败(%s): %s", norm, exc)
            await hass.async_add_executor_job(fh.close)
            try:
                await hass.async_add_executor_job(_os.remove, real)
            except OSError:
                pass
            return {"ok": False, "path": norm, "error": str(exc)}
        await hass.async_add_executor_job(fh.close)
        return {"ok": True, "path": norm, "local_path": real, "bytes": total}

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

        ✅ **真机实测可用**（2026-10-29，AS6020）：临时相册 0 张 → 调用 →
        3 秒内变 1 张，且照片拿到的是**相册域 fileId**（``281474976755904``），
        正是 ``add_to_album`` 唯一认的那种 id。这打通了
        「上传到文件空间 → 收进相册」整条链路。

        🚨 但它曾经**假成功**，教训值得留着：

            返回:     {"ok":true,"code":0,"data":{"tasks":[{"transId":"..."}]}}
            trans 域: taskType=201 progress=100 errorInfo.detail=[]
            相册:     15 张 → 15 张（等 30s 不变）
            文件空间: 没多出副本

        任务"跑完了"，数据凭空消失。成因是 ``dest.dirs`` 里**少了一个
        ``addTime`` 字段** —— 见下方构造处的长注释。设备对它做的是"字段
        存在性"校验（反方向抓包里该值是 ``0`` 也能过），缺了不报错、只是
        什么都不做。

        由此得出一条通用判断：**``code=0`` 和 ``progress=100`` 都不是成功
        的证据**。异步任务类接口必须回查目标数据本身（这里就是数一遍目标
        相册的照片），否则假成功会被当成功能上线。

        源文件的 ``fid`` 不传时按路径逐条列目录解析（多几次往返）；
        设备对 filesvc 文件返回的 ``fid`` 常常是 ``null``，此时退回 ``id``
        （实测两者量级相同，都能被 acrosscopy 接受）。

        ⚠️ 必须用 ``_client_for(runtime, call)``（2026-10-29 修）：
        这个服务是「相册上传照片」两步流程的第二步，前一步上传走**视图**
        已经按 account 路由到正确账号了。这里若还用 ``runtime.client``
        （固定主账号），就会去主账号里找刚传进别的账号的文件 —— 必然
        「找不到源文件」，用户看到"上传成功但加不进相册"。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        client = _client_for(runtime, call)
        paths = _paths(call)
        category = call.data.get("category") or DEFAULT_CATEGORY
        fids = call.data.get("fids") or []
        src_files: list[dict[str, Any]] = []
        try:
            for index, path in enumerate(paths):
                fid = fids[index] if index < len(fids) else None
                if fid is None:
                    entry_item = await client.async_find_entry(
                        path, category=category
                    )
                    if entry_item is None:
                        return {"ok": False, "error": f"找不到源文件: {path}"}
                    fid = entry_item.get("fid") or entry_item.get("id")
                src_files.append({"category": category, "fid": fid, "path": path})
            album_id = int(call.data["album_id"])
            result = await client.async_trans_acrosscopy(
                src_files, "filesvc",
                [{
                    "albumId": album_id,
                    "albumName": call.data.get("album_name") or "",
                    "albumType": int(call.data.get("album_type", 6)),
                    "category": call.data.get("album_category") or category,
                    # ⚠️ addTime 是**必填**，缺了任务会"假成功"（2026-10-29 真机证实）。
                    #
                    # 这一条是拿抓包报文逐字段对比挖出来的（``capture.jsonl``
                    # 的 /trans/acrosscopy 真实请求）：
                    #
                    #   抓包 dest.dirs: {addTime:1791391599804, albumId, albumName,
                    #                    albumType, category}
                    #   我们原先:       {albumId, albumName, albumType, category}
                    #
                    # 缺这一个字段的表现极具欺骗性：设备返回 code 0、传输任务
                    # taskType=201 progress=100 errorInfo.detail=[]，但目标相册
                    # 一张都不多、源空间也没有副本 —— 数据被静默丢弃。
                    # 反方向的 gallery→filesvc 抓包里 addTime 是 0，说明**字段
                    # 必须存在、值可以为 0**，这是"字段存在性校验"而非取值校验。
                    #
                    # 补上后真机验证：临时相册 0 张 → 复制 → 3 秒内变 1 张，
                    # 且拿到的是**相册域 fileId**（281474976755904）。
                    "addTime": int(_time.time() * 1000),
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

        ``rids`` 可直接给；也可给 ``paths``/``names`` 由回收站列表里匹配。
        """
        runtime, entry, err = _pick(hass, call.data.get("entry_id"))
        if err:
            return err
        if (bad := _need_device_id(entry)) is not None:
            return bad
        category = call.data.get("category") or DEFAULT_CATEGORY
        rids = await _resolve_recycle_rids(hass, call.data, category)
        if not rids:
            return {"ok": False, "error": "没解析到任何 rid（给 rids / rid / paths / names 其中之一）"}
        # 只恢复第一个（现有 batchOperation 只支持单条 recover；
        # 要批量的话可以循环调用）
        rid = rids[0]
        # 查 name / item_type（从回收站列表里取，或者直接用默认值）
        name = call.data.get("name") or ""
        item_type = int(call.data.get("item_type", 4))
        if not name or item_type == 4:
            try:
                items = await runtime.client.async_list_recycle(
                    category=category, limit=500,
                )
                hit = next((i for i in items if int(i.get("rid", -1)) == rid), None)
                if hit:
                    name = str(hit.get("name") or name)
                    item_type = int(hit.get("type") or item_type or 0)
            except Exception:  # noqa: BLE001
                pass
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
            vol.Optional("path"): str,
            vol.Optional("paths"): vol.All(cv.ensure_list, [str], vol.Length(max=MAX_BATCH)),
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
        DOMAIN, SERVICE_COPY_PATHS, _copy_paths,
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
            vol.Optional("skip_recycle", default=False): cv.boolean,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PHOTOS_TABLE_FULL, _photos_table_full,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("row_id"): vol.Coerce(int),
            vol.Optional("num"): vol.Coerce(int),
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
        DOMAIN, SERVICE_DOWNLOAD_FILE, _download_file,
        schema=vol.Schema({
            **entry_field,
            vol.Required("path"): str,
            vol.Required("local_path"): cv.string,
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
            **ACCOUNT_FIELD,
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
        DOMAIN, SERVICE_DELETE_RECYCLE_ITEMS, _delete_recycle_items,
        schema=vol.Schema({
            **entry_field,
            **_confirm_field(CONFIRM_PERMANENT_DELETE),
            vol.Optional("rids"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
            vol.Optional("rid"): vol.Coerce(int),
            vol.Optional("paths"): vol.All(cv.ensure_list, [str]),
            vol.Optional("names"): vol.All(cv.ensure_list, [str]),
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EMPTY_RECYCLE, _empty_recycle,
        schema=vol.Schema({
            **entry_field,
            **_confirm_field(CONFIRM_EMPTY_RECYCLE),
            vol.Optional("category"): CATEGORY,
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
            vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=200)),
            vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TASK_STATUS, _task_status,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("service", default="filesvc"): vol.In(("filesvc", "trans", "gallery")),
            vol.Optional("task_types"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
            vol.Optional("task_category", default=2): vol.Coerce(int),
            vol.Optional("all_tasks", default=False): cv.boolean,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PLUGIN_INSTALL, _plugin_install,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("app_id"): cv.string,
            vol.Optional("download_url"): cv.string,
            vol.Optional("pkg_name"): cv.string,
            vol.Optional("name"): cv.string,
            vol.Optional("icon_url"): cv.string,
            vol.Optional("ui_url"): cv.string,
            vol.Optional("version_code"): vol.Coerce(int),
            vol.Optional("version_name"): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PLUGIN_UNINSTALL, _plugin_uninstall,
        schema=vol.Schema({
            **entry_field,
            vol.Required("app_id"): cv.string,
            vol.Required("pkg_name"): cv.string,
            vol.Optional("action", default="delete"): vol.In(["delete","cancel","pause"]),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    for _svc, _func in (
        (SERVICE_PLUGIN_MARKET, _plugin_market),
        (SERVICE_PLUGIN_ALL, _plugin_all),
        (SERVICE_PLUGIN_XUNLEI, _plugin_xunlei),
    ):
        hass.services.async_register(
            DOMAIN, _svc, _func,
            schema=vol.Schema({**entry_field}),
            supports_response=SupportsResponse.ONLY,
        )
    hass.services.async_register(
        DOMAIN, SERVICE_DYNAMIC_INFO, _dynamic_info,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("owner_id", default=0): vol.Coerce(int),
            vol.Optional("data_type", default=0): vol.Coerce(int),
            vol.Optional("probe", default=False): cv.boolean,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RETRY_TASK, _retry_task,
        schema=vol.Schema({
            **entry_field,
            vol.Required("task_id"): vol.Coerce(int),
            vol.Required("task_type"): vol.Coerce(int),
            vol.Optional("business", default="filesvc"): cv.string,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAN_TASK_RECORDS, _clean_task_records,
        schema=vol.Schema({
            **entry_field,
            vol.Required("task_ids"): vol.All(
                cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1, max=MAX_BATCH)
            ),
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_ALBUMS, _list_albums,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("album_type", default=0): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_ALBUM, _add_album,
        schema=vol.Schema({
            **entry_field,
            vol.Required("name"): str,
            vol.Optional("album_type", default=0): vol.Coerce(int),
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DEL_ALBUM, _del_album,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Optional("album_type", default=0): vol.Coerce(int),
            **_confirm_field(CONFIRM_DELETE_ALBUM),
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEARCH_ALBUM_PHOTOS, _search_album_photos,
        schema=vol.Schema({
            **entry_field,
            vol.Required("keyword"): str,
            vol.Optional("album_type", default=0): vol.Coerce(int),
            vol.Optional("num", default=100): vol.Coerce(int),
            vol.Optional("page", default=1): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RENAME_MEDIA, _rename_media,
        schema=vol.Schema({
            **entry_field,
            vol.Exclusive("file_id", "target"): vol.Any(int, str),
            vol.Exclusive("file_ids", "target"): [vol.Any(int, str)],
            vol.Required("new_name"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_ALBUM_MEMBERS, _remove_album_members,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            # 与 add_to_album 保持一致：面板里操作的相册都是 type=6，
            # 之前默认 0 会导致「移出」跑去 type=0 里找同 id 的相册。
            vol.Optional("album_type", default=6): vol.Coerce(int),
            vol.Exclusive("file_id", "target"): vol.Any(int, str),
            vol.Exclusive("file_ids", "target"): [vol.Any(int, str)],
            vol.Optional("album_name"): str,
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_HIDE_ALBUMS, _hide_albums,
        schema=vol.Schema({
            **entry_field,
            vol.Exclusive("album_id", "target"): vol.Any(int, str),
            vol.Exclusive("album_ids", "target"): [vol.Any(int, str)],
            vol.Optional("album_type", default=0): vol.Coerce(int),
            vol.Optional("hidden", default=True): bool,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_ALL_ALBUMS, _list_all_albums,
        schema=vol.Schema({**entry_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALBUM_RENAME, _album_rename,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Required("new_name"): cv.string,
            vol.Optional("album_type", default=ALBUM_TYPE_USER): vol.Coerce(int),
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALBUM_SET_COVER, _album_set_cover,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Required("cover_id"): vol.Coerce(int),
            vol.Optional("album_type", default=ALBUM_TYPE_USER): vol.Coerce(int),
            # ⚠️ 不要再加 album_name：设封面带 albumName 会返回 30111（多送字段）
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SHARE_FILES_TO_PERSON, _share_files_to_person,
        schema=vol.Schema({
            **entry_field,
            vol.Exclusive("file_id", "target"): vol.Any(int, str),
            vol.Exclusive("file_ids", "target"): [vol.Any(int, str)],
            vol.Exclusive("receiver_user_id", "rx"): str,
            vol.Exclusive("receiver_user_ids", "rx"): [str],
            vol.Optional("auto_expire_days", default=0): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MERGE_FACE_ALBUMS, _merge_face_albums,
        schema=vol.Schema({
            **entry_field,
            vol.Required("target_album_id"): vol.Coerce(int),
            vol.Exclusive("source_album_id", "src"): vol.Any(int, str),
            vol.Exclusive("source_album_ids", "src"): [vol.Any(int, str)],
            **_confirm_field(CONFIRM_MERGE_FACE_ALBUMS),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECENT_FILES, _recent_files,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("limit", default=50): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_INSTALLED_PLUGINS, _installed_plugins,
        schema=vol.Schema({**entry_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALL_TRANS_TASKS, _all_trans_tasks,
        schema=vol.Schema({**entry_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DEVICE_USERS, _device_users,
        schema=vol.Schema({**entry_field}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALBUM_PHOTOS, _album_photos,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Optional("album_type", default=6): vol.Coerce(int),
            vol.Optional("num", default=ALBUM_PAGE_SIZE): vol.All(
                int, vol.Range(min=1, max=500)),
            vol.Optional("last_cre_time", default=0): vol.Coerce(int),
            vol.Optional("last_row_id", default=0): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_TRASH, _list_trash,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("num", default=100): vol.All(int, vol.Range(min=1, max=500)),
            vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DUPLICATE_SCAN, _duplicate_scan_result,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("task_id", default=0): vol.Coerce(int),
            vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
            vol.Optional("limit", default=20): vol.All(int, vol.Range(min=1, max=200)),
            vol.Optional("filter", default=0): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DEVICE_DIAGNOSTICS, _device_diagnostics,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_TASK, _get_task,
        schema=vol.Schema({
            **entry_field,
            vol.Required("task_id"): vol.Coerce(int),
            vol.Optional("service", default="filesvc"): vol.In(("filesvc", "trans")),
            vol.Optional("category"): CATEGORY,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALBUM_INFO, _album_info,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Optional("album_type", default=6): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ALBUM_CHANGES, _album_changes,
        schema=vol.Schema({
            **entry_field,
            vol.Optional("pre_id", default=0): vol.Coerce(int),
            vol.Optional("num", default=500): vol.All(int, vol.Range(min=1, max=500)),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SHARE_TO_PERSON, _share_to_person,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Required("owner_id"): vol.Coerce(int),
            vol.Required("file_ids"): vol.All(
                cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1, max=MAX_BATCH)
            ),
            vol.Optional("album_name"): str,
            vol.Optional("album_type", default=6): vol.Coerce(int),
            vol.Optional("file_names"): vol.All(cv.ensure_list, [str]),
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_TO_ALBUM, _add_to_album,
        schema=vol.Schema({
            **entry_field,
            vol.Required("album_id"): vol.Coerce(int),
            vol.Required("file_ids"): vol.All(
                cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1, max=MAX_BATCH)
            ),
            vol.Optional("album_name"): str,
            vol.Optional("album_type", default=6): vol.Coerce(int),
            **ACCOUNT_FIELD,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PHOTO_INFO, _photo_info,
        schema=vol.Schema({
            **entry_field,
            vol.Required("file_ids"): vol.All(
                cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1, max=MAX_BATCH)
            ),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT_DEVICE, _reboot_device,
        schema=vol.Schema({**entry_field, **_confirm_field(CONFIRM_REBOOT)}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SHUTDOWN_DEVICE, _shutdown_device,
        schema=vol.Schema({**entry_field, **_confirm_field(CONFIRM_SHUTDOWN)}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISK_SLEEP, _disk_sleep,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISK_INFO, _disk_info,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_USB_PLUG_OUT, _usb_plug_out,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RAID_STATUS, _raid_status,
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
