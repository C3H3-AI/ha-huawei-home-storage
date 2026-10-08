"""把 Home Assistant 备份存到华为家庭存储。

**要解决的问题**：纯 Core / Container 安装（没有 Supervisor）时，HA 只能把备份
存在本地磁盘；想存到 NAS 通常得装 Samba 或额外插件。本模块让家庭存储直接成为
一个**备份目标**（设置 → 系统 → 备份 里可选中它）。

实现方式：HA 的 ``backup`` 集成会扫描各集成的 ``backup`` 平台，只要模块里有
``async_get_backup_agents(hass)`` 就把它注册为备份目标
（``components/backup/manager.py`` 的发现逻辑）。

设计要点：

* **流式上传**：HA 通过 ``open_stream()`` 给的是异步字节流，备份动辄几百 MB。
  这里用 ``transfer.upload_stream`` 分块转发，内存占用只有一个 chunk。
  总大小取自 ``AgentBackup.size``（HA 已算好），因此不需要先落盘。
* **元数据边车**：设备上只存 tar 是不够的 —— ``async_list_backups`` 必须还原
  ``AgentBackup``（名称/日期/包含项/大小等）。逐个把 tar 拉下来解析代价太大，
  所以上传时**同时写一个 ``<备份名>.ha-backup.json``**，列举时只读边车。
* **删除进回收站**：设备侧只提供移入回收站（可逆），所以这里也是
  ``async_delete_paths``；彻底清空请在设备/App 的回收站里做。
* **短缓存**：列举一次备份要逐个读边车（N 次设备请求），而 HA 在
  列举/详情/下载前会反复调用，所以缓存 30s，并在上传/删除后立即失效。
* **监听器**：实现 ``async_register_backup_agents_listener``，这样增删配置条目
  （多设备/多账号）时备份目标会即时刷新，而不必重启 HA。

设计对齐了 HA Core 官方 ``synology_dsm/backup.py`` 与社区的
``ha-china/ha_quarkcloud`` 两套实现：``backup_id`` 一律取
``AgentBackup.backup_id``（**不是文件名**），文件名与 id 的映射只存于边车。
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
import time
from typing import Any, override

from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupAgentError,
    BackupNotFound,
    OnProgressCallback,
    suggested_filename,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.json import json_dumps

from .const import (
    DATA_BACKUP_AGENT_LISTENERS,
    BACKUP_META_SUFFIX,
    CONF_BACKUP_DIR,
    CONF_BACKUP_SPACE,
    DEFAULT_BACKUP_DIR,
    DOMAIN,
)
from .transfer import TransferError, download_stream, ensure_dir, upload_stream

_LOGGER = logging.getLogger(__name__)


async def async_get_backup_agents(
    hass: HomeAssistant, **kwargs: Any
) -> list[BackupAgent]:
    """HA 备份管理器通过这个函数发现备份目标。"""
    agents: list[BackupAgent] = []
    for entry_id, runtime in (hass.data.get(DOMAIN) or {}).items():
        if getattr(runtime, "client", None) is None:
            continue
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            continue
        try:
            agents.append(HuaweiStorageBackupAgent(hass, entry_id, entry, runtime))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("家庭存储备份目标初始化失败（%s）：%s", entry_id, err)
    return agents


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant,
    *,
    listener: Callable[[], None],
    **kwargs: Any,
) -> Callable[[], None]:
    """注册监听器：条目增删时让 HA 重新收集备份目标。

    参照 ``synology_dsm/backup.py`` 与 ``ha_quarkcloud/backup.py``。
    不实现这个可选接口时，HA 只在启动时收集一次 —— 用户新加一台设备
    或一个账号后，备份目标要重启 HA 才会出现。
    """
    hass.data.setdefault(DATA_BACKUP_AGENT_LISTENERS, []).append(listener)

    @callback
    def remove_listener() -> None:
        listeners = hass.data.get(DATA_BACKUP_AGENT_LISTENERS) or []
        if listener in listeners:
            listeners.remove(listener)
        if not listeners:
            hass.data.pop(DATA_BACKUP_AGENT_LISTENERS, None)

    return remove_listener


@callback
def async_notify_backup_agents_changed(hass: HomeAssistant) -> None:
    """条目增删后由 ``__init__`` 调用，通知 HA 重新收集目标。"""
    for listener in list(hass.data.get(DATA_BACKUP_AGENT_LISTENERS) or []):
        try:
            listener()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("备份目标监听器回调失败：%s", err)


class HuaweiStorageBackupAgent(BackupAgent):
    """把备份写进设备文件空间的一个目录。"""

    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, entry_id: str, entry: Any, runtime: Any) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._entry = entry
        self._runtime = runtime
        # 名字要能与「本地」区分。runtime.title 本身就是「家庭存储」，
        # 直接拼会出现「家庭存储（家庭存储）」——优先用设备型号。
        model = str((dict(getattr(entry, "data", {}) or {})).get("device_model") or "")
        self.name = f"家庭存储（{model}）" if model else "华为家庭存储"
        self.unique_id = entry_id
        # 列举缓存：一次列举 = 1 次列目录 + N 次读边车（都是设备请求），
        # 而 HA 会反复列举，所以缓存一小段时间，写操作后立刻失效。
        self._cache: list[tuple[str, AgentBackup]] = []
        self._cache_expire = 0.0
        self._cache_ttl = 30.0

    # ---------------- 内部 ----------------

    @property
    def _opts(self) -> dict[str, Any]:
        """配置项：备份目录与空间。默认 ``/file/HomeAssistant/`` + 我的文件。"""
        data = dict(getattr(self._entry, "data", {}) or {})
        data.update(getattr(self._entry, "options", {}) or {})
        return data

    @property
    def _dir(self) -> str:
        d = str(self._opts.get(CONF_BACKUP_DIR) or DEFAULT_BACKUP_DIR)
        return d if d.endswith("/") else d + "/"

    @property
    def _category(self) -> str:
        sp = str(self._opts.get(CONF_BACKUP_SPACE) or "user")
        return "public" if sp == "public" else "user"

    def _client(self) -> Any:
        client = getattr(self._runtime, "client", None)
        if client is None:
            raise BackupAgentError("家庭存储未就绪")
        return client

    def _device_id(self) -> str:
        return str(self._opts.get("device_id") or "")

    def _tar_path(self, backup_id: str) -> str:
        return self._dir + backup_id

    def _meta_path(self, backup_id: str) -> str:
        return self._dir + backup_id + BACKUP_META_SUFFIX

    async def _read_meta(self, client: Any, backup_id: str) -> AgentBackup | None:
        """读边车元数据（小文件，走既有的整块取文件接口即可）。"""
        raw = await client.async_fetch_image(
            self._meta_path(backup_id), service="filesvc", category=self._category
        )
        if not raw:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            _LOGGER.warning("备份元数据损坏 %s：%s", backup_id, err)
            return None
        if not isinstance(payload, dict):
            return None
        # 兼容两种格式：官方参考（synology_dsm / ha_quarkcloud）写的是
        # AgentBackup 的**扁平** dict；本集成早期版本误包了一层 "backup"。
        # 设备上可能同时存在两种，都要能读。
        data = payload.get("backup")
        if not isinstance(data, dict):
            data = payload
        try:
            return AgentBackup.from_dict(data)
        except (KeyError, TypeError) as err:
            _LOGGER.warning("备份元数据字段缺失 %s：%s", backup_id, err)
            return None

    def _invalidate(self) -> None:
        self._cache_expire = 0.0

    async def _listed(self) -> list[tuple[str, AgentBackup]]:
        """列出目录里所有带边车的备份 → [(文件名, AgentBackup)]（带短缓存）。"""
        if self._cache and time.monotonic() < self._cache_expire:
            return self._cache
        client = self._client()
        try:
            listing = await client.async_list_files(self._dir, category=self._category)
        except Exception as err:  # noqa: BLE001
            raise BackupAgentError(f"无法读取备份目录 {self._dir}：{err}") from err
        out: list[tuple[str, AgentBackup]] = []
        for item in listing.get("files") or []:
            name = str(item.get("name") or "")
            if not name.endswith(BACKUP_META_SUFFIX):
                continue
            base = name[: -len(BACKUP_META_SUFFIX)]
            backup = await self._read_meta(client, base)
            if backup is not None:
                # ⚠️ 存**基名**（tar 的名字），不是边车名 —— _tar_path/_meta_path
                # 都从基名派生。存成边车名会让下载把一个几百字节的 json 当备份。
                out.append((base, backup))
        self._cache = out
        self._cache_expire = time.monotonic() + self._cache_ttl
        return out

    async def _resolve(self, backup_id: str) -> tuple[str, AgentBackup]:
        """``backup_id`` → (文件名, AgentBackup)。

        ⚠️ HA 传给 agent 的 ``backup_id`` 是**它自己分配的 id**
        （如 ``67980322``），**不是**设备上的文件名。文件名由
        ``suggested_filename()`` 生成（如 ``名称_日期.tar``），两者的对应
        关系只存在于边车元数据里。

        最初这里直接拿 ``backup_id`` 去比文件名，导致 HA 的下载/恢复请求
        一律 404（实测）。
        """
        for filename, backup in await self._listed():
            if backup.backup_id == backup_id:
                return filename, backup
        raise BackupNotFound(backup_id)

    # ---------------- BackupAgent 接口 ----------------

    @override
    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        on_progress: OnProgressCallback,
        **kwargs: Any,
    ) -> None:
        """把备份流写到设备。

        ``backup.size`` 已由 HA 算好，所以可以直接 ``prepareUpload`` 声明大小，
        然后边收边发 —— 不需要先落盘，也不需要整份进内存。
        """
        client = self._client()
        filename = suggested_filename(backup)
        if not await ensure_dir(client, self._dir, self._category):
            raise BackupAgentError(
                f"备份目录不可用：{self._dir}（请先在 App/PC 端确认该目录存在，"
                f"或改成已有目录）"
            )
        stream = await open_stream()

        def report(uploaded: int) -> None:
            on_progress(bytes_uploaded=uploaded)

        try:
            await upload_stream(
                client,
                self._tar_path(filename),
                backup.size,
                stream,
                device_id=self._device_id(),
                category=self._category,
                on_progress=report,
            )
        except TransferError as err:
            raise BackupAgentError(f"备份上传失败：{err}") from err

        # 边车元数据：让 async_list_backups 不必下载整个 tar
        meta = json_dumps(backup.as_dict()).encode("utf-8")
        try:
            await client.async_upload_file(
                self._meta_path(filename),
                meta,
                device_id=self._device_id(),
                category=self._category,
            )
        except Exception as err:  # noqa: BLE001
            # 边车写失败不影响备份本体；下次列举时该备份会不显示，记警告即可
            _LOGGER.warning("备份元数据写入失败（%s）：%s", filename, err)
        self._invalidate()

    @override
    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        return [backup for _, backup in await self._listed()]

    @override
    async def async_get_backup(self, backup_id: str, **kwargs: Any) -> AgentBackup:
        return (await self._resolve(backup_id))[1]

    @override
    async def async_download_backup(
        self, backup_id: str, **kwargs: Any
    ) -> AsyncIterator[bytes]:
        client = self._client()
        filename, _ = await self._resolve(backup_id)
        return download_stream(
            client, self._tar_path(filename), category=self._category
        )

    @override
    async def async_delete_backup(self, backup_id: str, **kwargs: Any) -> None:
        """删除备份（设备侧一律移入回收站，可逆）。"""
        client = self._client()
        filename, _ = await self._resolve(backup_id)
        paths = [self._tar_path(filename), self._meta_path(filename)]
        try:
            await client.async_delete_paths(
                paths, device_id=self._device_id(), to_recycle=True, category=self._category
            )
        except Exception as err:  # noqa: BLE001
            raise BackupAgentError(f"删除备份失败：{err}") from err
        self._invalidate()
