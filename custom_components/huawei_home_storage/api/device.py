"""设备本地 API 客户端（HTTPS 控制通道 + 数据/图片通道）。

凭据由云侧 ``startService`` 下发（见 :mod:`huawei_cloud`），会话级：
控制通道用 ``Token`` + ``Cookie: ID=<session>``；数据通道用另一套
``dataToken`` / ``dataSession``。凭据 TTL 很短且每次 startService 会作废旧会话，
因此 401 时自动重新走一次云流程。

⚠️ 端口是**按 client 会话分配的隧道端口**（首个账号 8471/8472，第二个账号
可能是 8431/8432）：凭据里的 ``httpsUrl`` / ``dataHttpsUrl`` 为权威地址，
整条使用；8471/8472 仅作无凭据时的回退。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from ..const import (
    API_ALBUM_CFG,
    API_ALBUM_LIST,
    API_ALBUM_MEMBERS,
    API_DISK_CHANGE,
    API_FILES,
    API_HEARTBEAT,
    API_PHOTOS_INC,
    API_QUERY_BIN,
    API_RECYCLE,
    API_USB_STATUS,
    API_USER_DATA,
    API_ONLINE_STATE,
    API_DEVICE_INFO,
    API_DEVICE_STATUS,
    API_SAMBA_PUBLIC,
    API_SAMBA_USER,
    API_AUTO_UPGRADE,
    API_WAN_INFO,
    API_OPERATION_DEVICE,
    API_DEV_ERR_CODE,
    API_REPAIR_MODE_CHECK,
    API_FILES_RECENT,
    API_FILES_ALL,
    API_PLUGIN_INSTALLED,
    API_DUP_QUERY,
    API_DUP_CTRL,
    DUP_ACT_START,
    DUP_ACT_STOP,
    API_DEL_MEDIA,
    API_RECOVER_MEDIA,
    API_DEVICE_REBOOT,
    API_DISK_SLEEP,
    API_USB_PLUG_OUT,
    API_USER_MANAGE,
    DATA_DOWNLOAD_PATH,
    DATA_DOWNLOAD_QUERY,
    DATA_PORT,
    DATA_UA,
    DEVICE_CLIENT_TYPE,
    DEVICE_PORT,
    DEVICE_UA,
    FILE_FILES_CATEGORY,
    FILE_FILES_DIR_TYPE,
    FILE_FILES_SORT,
    FILE_ROOT_PATH,
    FILES_PAGE_SIZE,
    REQUEST_TIMEOUT,
)
from .huawei_cloud import DeviceCredentials, HuaweiCloudError

_LOGGER = logging.getLogger(__name__)

CredsProvider = Callable[[], Awaitable[DeviceCredentials]]


class HuaweiDeviceError(Exception):
    """设备 API 通用错误。"""


class HuaweiDeviceAuthError(HuaweiDeviceError):
    """设备拒绝会话凭据（401）。"""


def encode_device_path(path: str) -> str:
    """设备路径 → 全字节百分号编码（8472 的 ``/download`` 需要）。"""
    return "".join("%%%02X" % b for b in path.encode())


def derive_dev_mac(seed: str) -> str:
    """由稳定种子派生一个本地管理的伪 MAC（12 位十六进制，小写）。

    ``dev_mac`` 只是本集成向设备自称的客户端标识，无需真实网卡地址；
    用云侧 devId 作种子可保证同一设备重复添加时得到同一个值。
    """
    digest = hashlib.sha256(f"huawei_home_storage:{seed}".encode()).hexdigest()
    first = (int(digest[:2], 16) | 0x02) & 0xFE  # 本地管理地址 + 单播
    return f"{first:02x}{digest[2:12]}"


def _is_stale_session_code(value: Any) -> bool:
    """业务错误码是否代表**会话失效**（而非服务故障）。

    实测（2026-10-06）：同一设备被 PC 客户端与本集成用相同 client 标识时，
    后者的 startService 会顶掉前者；被顶掉的会话调业务接口就会拿到
    16106 / 12009，而 heartBeat / diskChange 等仍正常。重取凭据即可恢复。
    """
    try:
        return int(value) in STALE_SESSION_CODES
    except (TypeError, ValueError):
        return False


#: 表示「会话已被顶掉/失效」的业务错误码 → 需要重取凭据后重试
STALE_SESSION_CODES = frozenset({16106, 12009})


def _is_connect_error(err: BaseException) -> bool:
    """判断是否为「连不上」类错误（隧道端口失效 / 设备离线）。

    这类错误重试同一个地址没有意义，必须重新 startService 换隧道；
    而 TLS 握手类错误重取凭据也解决不了，直接抛出更清晰。
    """
    if isinstance(err, asyncio.TimeoutError):
        return True
    text = str(err).lower()
    markers = (
        "cannot connect to host",
        "connection refused",
        "name or service not known",
        "network is unreachable",
        "host is down",
        "failed to establish",
        "econnrefused",
        "econnreset",
        "epipe",
        "timed out",
        "timeout",
    )
    return any(m in text for m in markers)


class HuaweiDeviceClient:
    """与存储设备的本地 API 交互。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        creds_provider: CredsProvider,
        control_port: int = DEVICE_PORT,
        data_port: int = DATA_PORT,
    ) -> None:
        self._session = session
        self.host = host
        self._control_port = control_port
        self._data_port = data_port
        self._creds_provider = creds_provider
        self._creds: DeviceCredentials | None = None
        self._lock = asyncio.Lock()
        # 设备按 client 会话分配**隧道端口**：首个账号是 8471/8472，第二个账号
        # 可能是 8431/8432。凭据里的 httpsUrl / dataHttpsUrl 是权威地址，
        # 拿到后整条使用；8471/8472 仅作无凭据时的回退。
        self._control_url: str | None = None
        self._data_url: str | None = None

    # ------------------------------------------------------------------
    # 凭据
    # ------------------------------------------------------------------
    @property
    def credentials(self) -> DeviceCredentials | None:
        return self._creds

    @property
    def user(self) -> str:
        return self._creds.user if self._creds else ""

    async def async_refresh_credentials(self) -> DeviceCredentials:
        """向云侧换取全新设备凭据。"""
        async with self._lock:
            try:
                creds = await self._creds_provider()
            except HuaweiCloudError as err:
                raise HuaweiDeviceAuthError(f"获取设备凭据失败: {err}") from err
            # httpsUrl 形如 https://<host>:<port>/，端口是**本会话专属隧道**，
            # 必须整条采用（每个账号的端口不同，8471 只是第一个账号的默认值）
            if creds.https_url:
                host = creds.https_url.split("//", 1)[-1].split(":")[0]
                if host:
                    self.host = host
                self._control_url = creds.https_url.rstrip("/")
            if creds.data_https_url:
                self._data_url = creds.data_https_url.rstrip("/")
            self._creds = creds
            return creds

    async def async_ensure_credentials(self) -> DeviceCredentials:
        if self._creds is None:
            await self.async_refresh_credentials()
        assert self._creds is not None
        return self._creds

    def _control_base(self) -> str:
        if self._control_url:
            return self._control_url
        return f"https://{self.host}:{self._control_port}"

    def _data_base(self) -> str:
        if self._data_url:
            return self._data_url
        return f"https://{self.host}:{self._data_port}"

    def _control_headers(self) -> dict[str, str]:
        assert self._creds is not None
        return {
            "User-Agent": DEVICE_UA,
            "Accept": "*/*",
            "Token": self._creds.token,
            "Cookie": f"ID={self._creds.session}",
        }

    def _data_headers(self) -> dict[str, str]:
        assert self._creds is not None
        token = self._creds.data_token or self._creds.token
        session = self._creds.data_session or self._creds.session
        return {
            "User-Agent": DATA_UA,
            "Accept": "*/*",
            "Token": token,
            "Cookie": f"ID={session}",
        }

    @staticmethod
    def _common_params(device_id: str) -> dict[str, str]:
        return {"clientType": str(DEVICE_CLIENT_TYPE), "deviceId": device_id}

    # ------------------------------------------------------------------
    # 低层请求
    # ------------------------------------------------------------------
    async def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        creds = await self.async_ensure_credentials()
        merged = {**self._common_params(creds.cloud_dev_id), **(params or {})}
        url = f"{self._control_base()}{path}"
        headers = {**self._control_headers(), **(extra_headers or {})}
        try:
            async with self._session.request(
                method,
                url,
                params=merged,
                headers=headers,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                status = resp.status
                text = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            # 连接不上 = 隧道端口已被设备回收（设备按 client 会话分配端口，
            # 端口不固定；PC 客户端或设备重启后旧端口即失效）。
            # 此时必须重新 startService 拿新隧道，重试一次。
            if retry_auth and _is_connect_error(err):
                _LOGGER.debug("%s 连接失败（隧道可能已失效），重取凭据后重试: %s", path, err)
                await self.async_refresh_credentials()
                return await self._request(
                    path,
                    params,
                    method=method,
                    json_body=json_body,
                    extra_headers=extra_headers,
                    retry_auth=False,
                )
            raise HuaweiDeviceError(f"请求 {path} 失败: {err}") from err

        if status == 401:
            if retry_auth:
                await self.async_refresh_credentials()
                return await self._request(
                    path,
                    params,
                    method=method,
                    json_body=json_body,
                    extra_headers=extra_headers,
                    retry_auth=False,
                )
            raise HuaweiDeviceAuthError(f"{path} 拒绝会话凭据 (401)")
        if status != 200:
            raise HuaweiDeviceError(f"{path} 返回 HTTP {status}")

        try:
            payload = json.loads(text)
        except ValueError as err:
            raise HuaweiDeviceError(f"{path} 返回非 JSON") from err

        # 业务错误码：设备对不同服务用不同字段（code / errorCode），
        # 非 0 表示该服务拒绝或不可用。**必须显式抛出**，否则上层会把
        # 「设备返回错误」当成「数据为空」，故障被静默吞掉。
        #
        # 其中 16106 / 12009 是**会话失效**的表现（不是相册服务故障）：
        # 设备按 client 标识维持会话，同一标识被别的客户端 startService 顶掉后，
        # 旧会话调业务接口就会拿到这两个码。此时应重取凭据再试一次。
        if isinstance(payload, dict):
            for field in ("code", "errorCode"):
                if field in payload:
                    value = payload.get(field)
                    if value not in (0, "0", None):
                        if _is_stale_session_code(value) and retry_auth:
                            _LOGGER.debug(
                                "%s 返回 %s（会话失效），重取凭据后重试", path, value
                            )
                            await self.async_refresh_credentials()
                            return await self._request(
                                path,
                                params,
                                method=method,
                                json_body=json_body,
                                extra_headers=extra_headers,
                                retry_auth=False,
                            )
                        raise HuaweiDeviceError(
                            f"{path} 返回错误 {field}={value}"
                            f"（{str(payload.get('error_desc') or payload.get('errorMsg') or '')[:80]}）"
                        )
                    break
        return payload

    # ------------------------------------------------------------------
    # 高层：相册 / 照片
    # ------------------------------------------------------------------
    async def async_heartbeat(self) -> bool:
        data = await self._request(API_HEARTBEAT)
        return data.get("code", 0) == 0

    async def async_get_album_list(self, album_type: int = 0) -> list[dict[str, Any]]:
        """``albumType=0`` 返回全部相册（含系统/人脸/地点/场景/最近删除）。"""
        data = await self._request(API_ALBUM_LIST, {"albumType": album_type})
        return data.get("albumlist") or []

    async def async_get_album_cfg(self, album_id: int, album_type: int) -> dict[str, Any]:
        """相册详情：只含元数据 + coverInfo，**不含成员列表**。"""
        data = await self._request(
            API_ALBUM_CFG, {"albumId": album_id, "albumType": album_type}
        )
        return data.get("data") or {}

    async def async_get_album_members(
        self, album_type: int, pre_id: int = 0, num: int = 500
    ) -> list[dict[str, Any]]:
        """相册成员增量表：仅 ``{albumId, albumType, fileId, optType, optTime}``，无路径。"""
        data = await self._request(
            API_ALBUM_MEMBERS,
            {"albumType": album_type, "preId": pre_id, "num": num},
        )
        return data.get("data") or []

    async def async_get_photos_table(self, pre_row_id: int = 0) -> dict[str, Any]:
        """照片增量表：``{deviceId, fileId, operation, rowId}``，固定 500 条/页。"""
        return await self._request(API_PHOTOS_INC, {"preRowId": pre_row_id})

    async def async_query_bin(
        self, offset: int = 0, num: int = 100
    ) -> list[dict[str, Any]]:
        """回收站查询：返回**完整元数据**（含 assets/hdcFilePath/thumbFilePath）。"""
        data = await self._request(
            API_QUERY_BIN,
            method="POST",
            json_body={"offset": offset, "num": num},
        )
        return data.get("data") or []

    # ------------------------------------------------------------------
    # 高层：存储 / 系统
    # ------------------------------------------------------------------
    async def async_get_disk_info(self) -> dict[str, Any]:
        return await self._request(API_DISK_CHANGE)

    async def async_get_user_data(self) -> dict[str, Any]:
        """账号级容量统计（单位 MB）。"""
        return await self._request(API_USER_DATA)



    async def async_get_online_state(self) -> dict[str, Any]:
        """设备升级/固件状态。

        实测返回（AS6020-02）：
        ``{"SN": "SN-REDACTED", "Version": "6.1.0.7",
           "UpdateState": 17, "CurrentUpgradeTime": "2026-09-10 04:24:59",
           "IsSupportOnlineUpg": 4, ...}``
        """
        return await self._request(API_ONLINE_STATE)

    async def async_get_device_info(self) -> dict[str, Any]:
        """设备硬件/固件信息。

        实测返回（AS6020-02）：
        ``{"body": {"DeviceName": "AS6020-02", "CpuName": "realtek rtl1619b",
           "CpuCores": 4, "Frequency": 1800000,
           "SerialNumber": "SN-REDACTED", "SoftwareVersion": "6.1.0.7"},
           "code": 0}``
        注意payload在 ``body`` 下。
        """
        return await self._request(API_DEVICE_INFO)

    async def async_get_device_status(self) -> dict[str, Any]:
        """运行态指标（CPU 使用率 / 温度 / 内存）。

        实测返回（AS6020-02）：
        ``{"code": 0, "body": {"MemFree": 1417976, "MemTotal": 4000000,
           "Cpuusage": 1, "Cputemp": 44}}``
        注意 payload 在 ``body`` 下；CPU 使用率是百分比整数，温度单位摄氏度。
        """
        return await self._request(API_DEVICE_STATUS)

    async def async_get_samba_public(self) -> dict[str, Any]:
        """公共 Samba 共享状态。

        实测：``{"Smb1Enable": true, "AnonymousEnable": true,
        "Path": "Network_Share_Resource", "AudioShare": true, "version": "1"}``
        """
        return await self._request(API_SAMBA_PUBLIC)

    async def async_get_samba_user(self) -> dict[str, Any]:
        """用户 Samba 配置。

        实测：``{"Enable": true, "AnonymousEnable": 1, "Path": "My_Document"}``
        """
        return await self._request(API_SAMBA_USER)

    async def async_get_auto_upgrade(self) -> dict[str, Any]:
        """自动升级配置。

        实测：``{"Enable": true, "StartTime": "03:00", "EndTime": "05:00",
        "LatestHotaTime": "2026-09-10 04:24:35"}``
        """
        return await self._request(API_AUTO_UPGRADE)

    async def async_get_wan_info(self) -> dict[str, Any]:
        """网络/WAN 信息（payload 在 ``body`` 下）。

        实测含 ``IPv4Addr`` / ``IPv6Addr1`` / ``IPv6Gateway`` 等。
        """
        return await self._request(API_WAN_INFO)

    async def async_get_operation_devices(self) -> dict[str, Any]:
        """访问过设备的客户端列表。

        实测：``{"operationDevice": [{"deviceId": "...",
        "deviceName": "HUAWEI Pura 70 Ultra"}, ...]}``
        """
        return await self._request(API_OPERATION_DEVICE)

    async def async_get_dev_err_code(self) -> dict[str, Any]:
        """设备错误码。实测：``{"code": 0, "data": {"devErr": 0, "errorCode": 0}}``"""
        return await self._request(API_DEV_ERR_CODE)

    async def async_get_repair_mode(self) -> dict[str, Any]:
        """维修模式。实测：``{"code": 0, "data": {"mode": 0}}``"""
        return await self._request(API_REPAIR_MODE_CHECK)

    async def async_get_recent_files(
        self, offset: int = 0, limit: int = 20
    ) -> dict[str, Any]:
        """最近文件记录。

        实测：``{"data": {"hasMore": true, "offset": 10, "records": [
        {"name": "20131213212803739.JPG", "mime": "image/jpeg",
         "mtime": 1386987493000, "action": 4, ...}]}}``
        """
        return await self._request(API_FILES_RECENT, {"offset": offset, "limit": limit})

    async def async_get_all_files(
        self, offset: int = 0, limit: int = 20
    ) -> dict[str, Any]:
        """全部文件视图。实测：``{"data": {"files": [], "hasMore": false}}``"""
        return await self._request(API_FILES_ALL, {"offset": offset, "limit": limit})

    async def async_get_installed_plugins(self) -> dict[str, Any]:
        """已安装的设备插件。

        实测：``{"code": 0, "data": {"hapInfos": [{"appId": "...",
        "name": "...", "installTime": "2022-11-29 23:23:58", ...}]}}``
        """
        return await self._request(API_PLUGIN_INSTALLED)

    async def async_query_duplicate_scan(
        self, task_id: int = 0, offset: int = 0, limit: int = 20, filter_: int = 0
    ) -> dict[str, Any]:
        """查询重复照片扫描结果（POST，只读）。

        实测：``{"code": 0, "data": {"fileInfo": [], "scanCount": 0,
        "scanTotal": 0, "scanTaskStatus": 0, "mergeCount": 0,
        "mergeTaskStatus": 0, "lastMergeTime": 0, ...}}``
        """
        return await self._request(
            API_DUP_QUERY,
            json_body={
                "taskId": task_id,
                "offset": offset,
                "limit": limit,
                "filter": filter_,
            },
            method="POST",
        )

    async def async_ctrl_duplicate_scan(self, act: str, task_id: int = 0) -> dict[str, Any]:
        """启动/停止重复照片扫描（POST）。

        ``act`` 取 ``DUP_ACT_START`` / ``DUP_ACT_STOP``。
        实测 stop：``{"code": 0, "data": {"code": 0, "taskId": 0}, "des": "suc"}``
        """
        return await self._request(
            API_DUP_CTRL,
            json_body={"actType": act, "taskId": task_id},
            method="POST",
        )

    async def async_delete_media(self, file_ids: list[str]) -> dict[str, Any]:
        """把照片/视频移入回收站（**可逆**，不是永久删除）。

        参数 ``membs`` 为文件 id 列表。删完可在「最近删除」里用
        :meth:`async_recover_media` 恢复。集成**永不**调用 cleanBin。
        """
        return await self._request(
            API_DEL_MEDIA,
            method="POST",
            json_body={
                "membs": [{"id": fid} for fid in file_ids],
                "clientType": 1,
                "userId": "1",
                "empty": 0,
            },
        )

    async def async_recover_media(self, file_ids: list[str]) -> dict[str, Any]:
        """从回收站恢复照片/视频。"""
        return await self._request(
            API_RECOVER_MEDIA,
            method="POST",
            json_body={
                "membs": [{"id": fid} for fid in file_ids],
                "clientType": 1,
                "userId": "1",
                "empty": 0,
            },
        )

    async def async_post_device_reboot(self) -> dict[str, Any]:
        """重启设备（POST）。

        可恢复，但会中断服务约 1-2 分钟，期间设备不可用。
        仅由用户显式点击按钮触发，集成绝不自动重启。
        """
        return await self._request(API_DEVICE_REBOOT, method="POST")

    async def async_post_disk_sleep(self) -> dict[str, Any]:
        """磁盘休眠（POST）。会暂停磁盘，属可恢复操作。"""
        return await self._request(API_DISK_SLEEP, method="POST")

    async def async_post_usb_plug_out(self) -> dict[str, Any]:
        """弹出 USB 设备（POST）。可恢复操作。"""
        return await self._request(API_USB_PLUG_OUT, method="POST")

    async def async_get_device_users(self) -> list[dict[str, Any]]:
        """设备上的全部用户（管理员 + 家庭成员）。

        ``/account/userManageInfo`` 返回**数组**而非对象，每项含
        ``level``（1=管理员 / 2=成员）、``nick``、``usage``（MB）、``state``。
        与「当前配置条目用的账号」无关，是设备侧的完整用户列表。
        """
        data = await self._request(API_USER_MANAGE)
        return data if isinstance(data, list) else []

    async def async_get_recycle_files(self) -> dict[str, Any]:
        data = await self._request(API_RECYCLE, {"category": "user", "limit": 1, "offset": 0})
        return data.get("data") or {}

    async def async_get_usb_status(self) -> dict[str, Any]:
        data = await self._request(API_USB_STATUS)
        return data.get("data") or {}

    # ------------------------------------------------------------------
    # 文件空间（NAS 视图，/filesvc/files + Dest-File 头）
    # ------------------------------------------------------------------
    async def async_list_files(
        self, dir_path: str = FILE_ROOT_PATH, offset: int = 0, limit: int = FILES_PAGE_SIZE
    ) -> dict[str, Any]:
        """列文件空间目录。

        ``dir_path`` 为设备目录路径（含尾斜杠，如 ``/file/``）。必须携带
        ``Dest-File`` 请求头（目录路径的全字节百分号编码），缺省时设备返回
        ``{"code": 1101}``。返回 ``{"files": [...], "count": N}``：
        目录条目 ``type`` 2/4/6，文件条目 ``type=8`` 带 ``thumb``；
        目录条目的 ``path`` 常为空，需调用方自行拼接完整路径。
        """
        dir_path = dir_path if dir_path.endswith("/") else dir_path + "/"
        data = await self._request(
            API_FILES,
            {
                "category": FILE_FILES_CATEGORY,
                "dirType": FILE_FILES_DIR_TYPE,
                "limit": limit,
                "offset": offset,
                "sortType": FILE_FILES_SORT,
            },
            extra_headers={"Dest-File": encode_device_path(dir_path)},
        )
        inner = data.get("data") or {}
        files = inner.get("files") or []
        count = inner.get("count")
        if count is None:
            count = inner.get("total")
        return {"files": files, "count": int(count) if count is not None else None}

    # ------------------------------------------------------------------
    # 图片（8472 数据通道）
    # ------------------------------------------------------------------
    async def async_fetch_image(self, device_path: str) -> bytes | None:
        """按设备路径取图（``/picture/thumb|asset|raw|hdc_1080`` 等）。"""
        if not device_path:
            return None
        await self.async_ensure_credentials()
        url = (
            f"{self._data_base()}{DATA_DOWNLOAD_PATH}"
            f"{encode_device_path(device_path)}?{DATA_DOWNLOAD_QUERY}"
        )
        for attempt in range(2):
            try:
                async with self._session.get(
                    url,
                    headers=self._data_headers(),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        await self.async_refresh_credentials()
                        continue
                    if resp.status != 200:
                        _LOGGER.debug("取图失败 %s -> HTTP %s", device_path, resp.status)
                        return None
                    return await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                _LOGGER.debug("取图异常 %s: %s", device_path, err)
                return None
        return None
