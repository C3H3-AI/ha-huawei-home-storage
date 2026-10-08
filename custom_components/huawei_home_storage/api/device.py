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
import random
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from ..const import (
    API_ALBUM_LIST,
    API_DISK_CHANGE,
    API_FILES,
    API_HEARTBEAT,
    API_PHOTOS_INC,
    API_QUERY_BIN,
    API_RECYCLE,
    API_USB_STATUS,
    API_PREPARE_UPLOAD,
    API_CANCEL_UPLOAD,
    API_BATCH_OPERATION,
    API_MKDIR,
    API_RENAME,
    API_FILE_DETAIL,
    API_FILE_SEARCH,
    API_TRANS_MOVE,
    API_TRANS_COPY,
    API_TRANS_ACROSSCOPY,
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
    ALBUM_PAGE_SIZE,
    ALBUM_TYPE_ALL,
    ALBUM_TYPE_USER,
    REQUEST_TIMEOUT,
)
from .huawei_cloud import DeviceCredentials, HuaweiCloudAuthError, HuaweiCloudError

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
            except HuaweiCloudAuthError as err:
                # 凭据/授权真的失效（refresh_token 过期、缺 token）：
                # 只有这种情况才该让 HA 弹重新认证。
                raise HuaweiDeviceAuthError(f"获取设备凭据失败: {err}") from err
            except HuaweiCloudError as err:
                # 其它云侧故障（MQTT 超时、链路被截断、响应非 JSON 等）都是
                # **瞬时/设备侧**问题，不是凭据失效。
                #
                # ⚠️ 这里曾把所有 HuaweiCloudError 都归为 AuthError，后果是：
                # 一次 MQTT 超时就会变成 ConfigEntryAuthFailed → HA 弹出
                # 「重新认证」，要求用户重输账号密码，而其实下一轮轮询就自愈了。
                # 归为 DeviceError 后会走 UpdateFailed → 协调器优雅降级 + 下轮重试。
                raise HuaweiDeviceError(f"获取设备凭据失败（可重试）: {err}") from err
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

    async def async_upload_file(
        self,
        dest_path: str,
        payload: bytes,
        device_id: str,
        category: str = "public",
        src_path: str = "",
        view_path: str = "",
        mtime_ms: int | None = None,
    ) -> dict[str, Any]:
        """上传文件到设备（**端到端打通**，2026-10-08 实测落盘）。

        两段式，全部照抓包报文复现（外网/局域网一致）::

            ① POST /filesvc/prepareUpload?category=public
               {"deviceId":..,"uploadType":1,"files":[{viewPath,srcPath,
                 path,sessionId:"",fileId:0,fileSize,orientation:0,taskId:0}]}
               → {fileList:[{fileId, sessionId, offset, path, ...}]}

            ② POST <数据通道>/upload?<17 个 query 参数>
               头: Content-Disposition / Content-Type / Dest-File /
                   X-Session-ID / Expect: 100-continue（**必需**，缺则 500）
               body: 文件原始字节

        ⚠️ 关键点（缺一个就 500/52015）：
        * query 必须带 **mediaType/mtime/orientation/service/size/
          sourceAlbum/srcPath/takenTime/uploadType/usb/viewPath** ——
          抓包里共 17 个参数，缺一个就 500（openresty 层拒绝）
        * **``Expect: 100-continue`` 必需**（实测去掉 → 500）
        * ``service=filesvc`` 也要在 query 里（prepare 不用，upload 要）
        * ``Dest-File`` / ``Content-Disposition`` 的文件名用**全字节百分号编码**
        * 成功返回 ``{"code":0,"data":{"path":"/file/test/xxx"}}``
        """
        import time as _time
        import urllib.parse as _up

        await self.async_ensure_credentials()
        durl = self._data_base()
        dh = self._data_headers()
        fname = dest_path.rstrip("/").rsplit("/", 1)[-1]
        now = mtime_ms or int(_time.time() * 1000)
        src = src_path or f"/win/C/tmp/{fname}"
        view = view_path or f"Pictures/MemoSpace/{fname}"

        # ① prepareUpload
        prep = await self._request(
            API_PREPARE_UPLOAD,
            method="POST",
            params={"category": category},
            json_body={"deviceId": device_id, "uploadType": 1,
                       "files": [{"viewPath": view, "srcPath": src,
                                  "path": dest_path, "sessionId": "",
                                  "fileId": 0, "fileSize": len(payload),
                                  "orientation": 0, "taskId": 0}]},
        )
        items = (prep.get("data") or {}).get("fileList") or []
        if not items:
            raise HuaweiDeviceError(f"prepareUpload 无 fileList: {prep}")
        fid = str(items[0].get("fileId"))
        sid = str(items[0].get("sessionId"))

        # ② POST /upload（数据通道，17 参数 + Expect: 100-continue）
        q = {
            "category": category, "clientType": str(DEVICE_CLIENT_TYPE),
            "comment": "", "ctime": str(now), "deviceId": device_id,
            "fileId": fid, "fileVer": "", "mediaType": "0", "mtime": str(now),
            "orientation": "0", "service": "filesvc", "size": str(len(payload)),
            "sourceAlbum": "0", "srcPath": src, "takenTime": "0",
            "uploadType": "1", "usb": "false", "viewPath": view,
        }
        h = {**dh,
             "Content-Disposition": f'attachment;filename="{_up.quote(fname)}"',
             "Content-Type": "application/octet-stream",
             "Dest-File": encode_device_path(dest_path),
             "X-Session-ID": sid,
             "Expect": "100-continue"}
        async with self._session.post(
            f"{durl}/upload", params=q, headers=h, data=payload,
            timeout=aiohttp.ClientTimeout(total=max(120, len(payload) // 10000)),
        ) as resp:
            text = await resp.text()
        try:
            j = json.loads(text)
        except ValueError:
            raise HuaweiDeviceError(f"/upload 非 JSON 响应: HTTP {resp.status} {text[:120]}")
        # 成功：{"code":0,"data":{"path":...}}。注意 code 可能是 str/int。
        if str(j.get("code")) != "0":
            raise HuaweiDeviceError(f"/upload 失败: {text[:200]}")
        return j

    async def async_get_album_photos(
        self,
        album_id: int,
        album_type: int,
        device_id: str,
        last_cre_time: int = 0,
        last_row_id: int = 0,
        num: int = ALBUM_PAGE_SIZE,
    ) -> dict[str, Any]:
        """取相册内的照片（``/gallery/getAlbumInfo``）——**列全部照片的正解**。

        抓包实据（出现 1220 次，客户端浏览相册照片的主接口）::

            GET /gallery/getAlbumInfo
                ?albumId=16&albumType=6&clientType=3&dataType=1
                &deviceId=<devId>&lastCreTime=0&lastRowId=0&num=500

        ⚠️ 「所有照片」(albumId=1) 传它的 albumType=1 会 ``30109``，
        实测改用 ``albumType=2`` 才有数据——本方法已内置该回退。
        """
        req = {
            "albumId": album_id,
            "albumType": album_type,
            "clientType": DEVICE_CLIENT_TYPE,
            "dataType": 1,
            "deviceId": device_id,
            "lastCreTime": last_cre_time,
            "lastRowId": last_row_id,
            "num": num,
        }
        try:
            data = await self._request("/gallery/getAlbumInfo", req)
        except HuaweiDeviceError as err:
            # 「所有照片」等特殊相册：albumType=1 → 30109，改用 2 重试。
            # _request 对非 0 code 直接抛异常，所以在这里捕获判断。
            if "30109" not in str(err):
                raise
            data = await self._request(
                "/gallery/getAlbumInfo", {**req, "albumType": 2}
            )
        photos = data.get("data") or []
        if not isinstance(photos, list):
            photos = []
        next_cre, next_row = last_cre_time, last_row_id
        if photos:
            ts = [int(p.get("createTime") or 0) for p in photos]
            mx = max(ts) if ts else 0
            if mx:
                next_cre = mx
            rid = [int(p.get("rowId") or 0) for p in photos]
            mrow = max(rid) if rid else 0
            if mrow:
                next_row = mrow
        return {"photos": photos, "lastCreTime": next_cre, "lastRowId": next_row}

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

    async def _media_body(self, file_ids: list[str] | list[int]) -> dict[str, Any]:
        """构造 delFile/recoverFile 的 body。

        ⚠️ 实测（2026-10-06，AS6020-02）：这三个字段缺一不可，否则返回
        ``30102``（``delFile``/``recoverFile`` 都是）：
          * ``clientType`` = **会话的 clientType**（``DEVICE_CLIENT_TYPE``）。
            用手机端的 ``1`` 会被拒；必须与 query 参数里的 clientType 一致。
          * ``deviceId`` = ``creds.cloud_dev_id``（设备 SN，如
            ``SN-REDACTED``）。不是客户端安装标识。
          * ``userId`` = ``"1"``。
        成员字段名是 ``fileId``（``DeleteMediaInfoBean$MemberBean``），
        且必须是 **gallery 域**的 fileId（``getIncPhotosInfoTable`` 里的
        ``fileId``），不是 ``filesvc`` 的 ``fid``。
        """
        creds = await self.async_ensure_credentials()
        return {
            "membs": [{"fileId": int(fid)} for fid in file_ids],
            "clientType": DEVICE_CLIENT_TYPE,
            "deviceId": creds.cloud_dev_id,
            "userId": "1",
            "empty": 0,
        }

    async def async_delete_media(self, file_ids: list[str]) -> dict[str, Any]:
        """把照片/视频移入回收站（**可逆**，不是永久删除）。

        参数 ``membs`` 为文件 id 列表。删完可在「最近删除」里用
        :meth:`async_recover_media` 恢复。集成**永不**调用 cleanBin。
        """
        return await self._request(
            API_DEL_MEDIA,
            method="POST",
            json_body=await self._media_body(file_ids),
        )

    async def async_recover_media(self, file_ids: list[str]) -> dict[str, Any]:
        """从回收站恢复照片/视频。"""
        return await self._request(
            API_RECOVER_MEDIA,
            method="POST",
            json_body=await self._media_body(file_ids),
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

    async def async_get_usb_status(self) -> dict[str, Any]:
        data = await self._request(API_USB_STATUS)
        return data.get("data") or {}

    async def async_mkdir(
        self, path: str, category: str = FILE_FILES_CATEGORY
    ) -> dict[str, Any]:
        """新建目录（``/filesvc/mkdir``，抓包实据 + 基线实测 ``code 0``）。

        实据::

            POST /filesvc/mkdir?category=public
            {"path":"/file/新建文件夹/","redundancy":0}
            -> {"code":0,"data":{"fid":288511851128439709,...}}

        要点（照抓包形态，缺一个就可能被拒）：
        * ``path`` 是**设备路径**（``/file/...``），本方法会补上**尾斜杠**
        * body 是**扁平**的（不是 ``tasks[]`` 数组），且**不要**带 ``Dest-File``
          头 —— mkdir 的成功形态没有这个头
        * ``redundancy=0``：重名直接报错，不自动改名
        * 返回 ``data.fid``（约 2.9e17 的句柄）用于删除；**不要**拿列表里的
          ``id`` 去删 —— 实测两者不是一回事
        """
        path = path if path.endswith("/") else path + "/"
        data = await self._request(
            API_MKDIR,
            method="POST",
            params={"category": category},
            json_body={"path": path, "redundancy": 0},
        )
        return data.get("data") or {}

    async def async_find_entry(
        self, path: str, category: str = FILE_FILES_CATEGORY
    ) -> dict[str, Any] | None:
        """按路径在**父目录列表**里找出该条目（返回原始条目，含 ``fid`` / ``id``）。

        目录条目的 ``path`` 字段常为空，所以只能列父目录再按名字匹配。
        找不到时返回 ``None``。重命名要用 ``id``、跨服务复制要用 ``fid``，
        两者都在返回的条目里。
        """
        clean = path.rstrip("/")
        parent, _, name = clean.rpartition("/")
        parent = (parent or "") + "/"
        listing = await self.async_list_files(parent, category=category)
        for item in listing.get("files") or []:
            if str(item.get("name")) == name:
                return item
        return None

    async def async_resolve_id(
        self, path: str, category: str = FILE_FILES_CATEGORY
    ) -> int | None:
        """按路径解析 filesvc ``id``（重命名要用，见 :meth:`async_rename`）。"""
        item = await self.async_find_entry(path, category=category)
        if not item:
            return None
        value = item.get("id")
        if value is None:
            value = item.get("fid")
        return int(value) if value is not None else None

    async def async_rename(
        self,
        old_path: str,
        new_path: str,
        category: str = FILE_FILES_CATEGORY,
        file_id: int | str | None = None,
    ) -> dict[str, Any]:
        """重命名（``/filesvc/rename``，抓包实据 + 实测 ``code 0``）。

        实据::

            POST /filesvc/rename?category=public&id=209104
            {"newpath":"/file/测试/","oldpath":"/file/新建文件夹/"}
            -> {"code":0}

        ⚠️ 两点：
        * query 必须带 **``id``**（该条目的 filesvc ``id``）。不传时用
          :meth:`async_resolve_id` 列父目录按名字解析（多一次请求）
        * 路径**按调用方给的形态原样传**：目录带尾斜杠（``/file/旧名/``），
          文件不带。本方法不做补斜杠，避免把文件名改坏
        """
        if file_id is None:
            file_id = await self.async_resolve_id(old_path, category=category)
        if file_id is None:
            raise HuaweiDeviceError(f"找不到路径对应的 id，无法重命名: {old_path}")
        return await self._request(
            API_RENAME,
            method="POST",
            params={"category": category, "id": str(file_id)},
            json_body={"newpath": new_path, "oldpath": old_path},
        )

    async def async_delete_paths(
        self,
        paths: list[str],
        device_id: str,
        to_recycle: bool = True,
        category: str = "user",
    ) -> dict[str, Any]:
        """删除文件空间里的路径（**实测可用**，2026-10-08）。

        抓包实据（用户真实删除，``capture.jsonl`` L118）::

            POST /filesvc/batchOperation?category=user&operation=remove&type=recycle
            {"tasks":[{"clientType":3,"deviceId":"9a762c46a872-LAPTOP-DLD5UGDT",
                       "name":"","srcPath":["/file/测试/屏幕截图 ....png"],
                       "subTaskId":1,"transId":"244833947285","type":0}]}
            -> {"code":0,"data":{"tasks":[{"taskId":6,"transId":"..."}]}}

        要点（此前一直失败的根因）：
        * 端点不是 ``/filesvc/remove``（该端点恒 1101），而是 **``batchOperation``**
        * ``operation=remove`` 决定了动作，``type=recycle`` 决定去向（**进回收站**）
        * ⚠️ ``to_recycle=False``（query 用 ``type=delete``）**实测恒 1101，未解出**：
          2026-10-08 试过 ``operation=delete`` / ``clean`` / 带 ``redundancy``
          以及 ``/filesvc/recycleDelFiles`` 的多种 body 形态，全部 1101。
          因此**永久删除目前做不到**，回收站条目只能在客户端 App 里清
        * 参数嵌在 **``tasks[]`` 数组**里，不是扁平 body
        * ``srcPath`` 是**数组**，目录路径需带尾斜杠
        * ⚠️ body 里的 ``deviceId`` 必须是**配置条目的 device_id**
          （``entry.data["device_id"]``，形如 ``42e9d4b7-...``）；
          用 ``creds.cloud_dev_id``（设备 SN）会被拒 ``1101``——
          这两者在此端点上**不可互换**（实测 2026-10-08）

        返回 ``{"code":0,"data":{"tasks":[{"taskId":..,"transId":".."}]}}``。
        删除为**异步任务**：返回成功不代表立即生效，用
        :meth:`async_get_task_status` 查 ``progress`` 确认落地。
        """
        creds = await self.async_ensure_credentials()
        body = {
            "tasks": [{
                "clientType": DEVICE_CLIENT_TYPE,
                "deviceId": device_id,
                "name": "",
                "srcPath": list(paths),
                "subTaskId": 1,
                # ⚠️ transId 必须是 **12 位数字**：实测 9 位会被拒 1101，
                # 12 位才返回 code 0（抓包原值为 12 位）。
                "transId": str(random.randint(10**11, 10**12 - 1)),
                "type": 0,
            }]
        }
        return await self._request(
            API_BATCH_OPERATION,
            method="POST",
            params={"category": category, "operation": "remove",
                    "type": "recycle" if to_recycle else "delete"},
            json_body=body,
        )

    async def async_get_photos_info(
        self, file_ids: list[int] | list[str]
    ) -> list[dict[str, Any]]:
        """把 fileId 换成**完整元数据**（``/gallery/getSelectedPhotosInfo``）。

        实测（2026-10-08）返回每项的：``hdcFilePath``（原图）、
        ``lcdFilePath``（大图）、``assets[].path``（``thumb``/``lcd``）、
        ``city````createTime````favorite````hash`` 等。
        这是**相册成员唯一能拿到图片路径的途径**。

        ⚠️ 只有**有效** fileId 才有返回；从 ``getIncPhotosInfoTable``
        取到的删除残留（``operation=2``）会返回空数组。
        """
        data = await self._request(
            "/gallery/getSelectedPhotosInfo",
            method="POST",
            json_body={"clientType": DEVICE_CLIENT_TYPE,
                       "fileIds": [{"fileId": f} for f in file_ids]},
        )
        d = data.get("data") or []
        return d if isinstance(d, list) else []

    async def async_add_album_members(
        self,
        album_id: int,
        file_ids: list[int] | list[str],
        album_name: str = "",
        album_type: int = ALBUM_TYPE_USER,
    ) -> dict[str, Any]:
        """把**已有的照片**加进相册（``/gallery/addAlbumMemb``，实测 ``code 0``）。

        抓包实据（2026-10-09 从 `capture_all_1791417873.jsonl` 挖出）::

            POST /gallery/addAlbumMemb
            {"clientType":3,"deviceId":"9a762c46a872-...","albumId":13,
             "albumName":"新建相册","albumType":6,
             "membs":[{"fileId":281474976755920}],
             "addTime":1791412165000}
            -> {"code":0,"des":"suc","failIds":[],
                "sucIds":[{"fileId":281474976755920}]}

        要点：
        * 加的是**相册域（gallery）的 fileId**，不是文件空间的 ``fid``
          —— 从 :meth:`async_get_album_photos` 或照片增量表取
        * 返回 ``sucIds``（成功）/ ``failIds``（失败）数组。重复添加同一张
          也返回 suc（幂等），所以 ``failIds`` 为空才算真的都进去了
        * ``albumType`` 默认 6（用户/共享相册）
        * ⚠️ ``albumName`` **是必填**：不传会返回 ``30101``（实测 2026-10-09）。
          留空时本方法会自动查相册列表补全（type=6 优先，再查 type=0）
        """
        creds = await self.async_ensure_credentials()
        if not album_name:
            album_name = await self._album_name_by_id(int(album_id))
        return await self._request(
            "/gallery/addAlbumMemb",
            method="POST",
            json_body={
                "clientType": DEVICE_CLIENT_TYPE,
                "deviceId": creds.cloud_dev_id,
                "albumId": int(album_id),
                "albumName": album_name,
                "albumType": int(album_type),
                "membs": [{"fileId": int(f)} for f in file_ids],
                "addTime": int(asyncio.get_event_loop().time() * 1000),
            },
        )

    async def _album_name_by_id(self, album_id: int) -> str:
        """按 albumId 反查相册名（``addAlbumMemb`` 的 albumName 是必填）。

        ⚠️ ``albumType=0`` 的返回**不含 type=6**，所以两个都要查（已知结论）。
        """
        for a_type in (ALBUM_TYPE_USER, ALBUM_TYPE_ALL):
            try:
                albums = await self.async_get_album_list(a_type)
            except Exception:  # noqa: BLE001
                continue
            for a in albums or []:
                try:
                    if int(a.get("albumId")) == int(album_id):
                        return str(a.get("albumName") or "")
                except (TypeError, ValueError):
                    continue
        return ""

    async def async_get_single_task(
        self, task_id: int, category: str = "user", service: str = "filesvc"
    ) -> dict[str, Any]:
        """查**单个**任务详情（``/<service>/getTaskStatus``，实测 ``code 0``）。

        抓包实据（2026-10-09）：body 只有 ``{"category":"user","taskId":18}``。
        与 :meth:`async_get_task_status`（批量、要 taskTypes）互补：这个按
        ``taskId`` 精确查一个，返回同构的 ``data.tasks[]``（通常只有一项）。
        """
        return await self._request(
            f"/{service}/getTaskStatus",
            method="POST",
            json_body={"category": category, "taskId": int(task_id)},
        )

    async def async_recycle_recover(
        self, rid: int | str, name: str = "", device_id: str = "",
        category: str = "public", item_type: int = 4
    ) -> dict[str, Any]:
        """从回收站**恢复**条目（``batchOperation`` 的 ``recycle/recover``）。

        抓包实据（用户真实还原操作，2026-10-08）::

            POST /filesvc/batchOperation?category=public
                 ?operation=recycle&type=recover
            {"tasks":[{"clientType":3,"deviceId":"9a762c46a872-LAPTOP-DLD5UGDT",
                       "name":"新建文件夹","rid":["82"],
                       "subTaskId":1,"transId":"777394318487","type":4}]}
            -> {"code":0,"data":{"tasks":[{"taskId":..,"transId":".."}]}}

        ⚠️ 四个易错点（实测，错一个就 ``1101``/``prog=-1``）：
        * ``operation`` 是 **``recycle``**（不是 ``remove``）
        * ``type`` 是 **``recover``**
        * ``rid`` 必须是**字符串的单元素数组**：``["2363"]``。
          传整数数组 ``[2363]`` 或裸字符串 ``"2363"`` 都返回 ``1101``
          （2026-10-08 实机对照实测）
        * tasks 内的 ``type`` 用 **4**（目录）/ 0（文件）

        ``rid`` 来自 :meth:`async_list_recycle`（必须用 GET 取）。
        恢复是异步任务，用 :meth:`async_get_task_status` 查 ``progress`` 确认。
        """
        body = {"tasks": [{
            "clientType": DEVICE_CLIENT_TYPE,
            "deviceId": device_id,
            "name": name,
            "rid": [str(rid)],
            "subTaskId": 1,
            "transId": str(random.randint(10**11, 10**12 - 1)),
            "type": item_type,
        }]}
        return await self._request(
            API_BATCH_OPERATION,
            method="POST",
            params={"category": category, "operation": "recycle", "type": "recover"},
            json_body=body,
        )

    async def async_list_recycle(
        self, category: str = "public", limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """列回收站条目（``/filesvc/recycleFiles``）。

        ⚠️ **必须用 GET**：实测 POST 返回 ``1004``（2026-10-08）。
        条目含 ``rid``（恢复用）、``name``、``path``、``dtime``、``type``。
        """
        data = await self._request(
            API_RECYCLE,
            {"category": category, "limit": limit, "offset": offset},
        )
        return (data.get("data") or {}).get("files") or []

    async def async_cancel_upload(
        self, fids: list[int] | list[str], device_id: str
    ) -> dict[str, Any]:
        """取消进行中的上传（``/filesvc/cancelUpload``，**实测 code 0**）。

        实测（2026-10-08）：body 用 **``fids`` 数组**（与 ``srcPath``/``sessionId``
        无效，返回 1101）::

            POST /filesvc/cancelUpload
            {"clientType":3,"deviceId":"42e9d4b7-...","fids":[<fileId>]}
            -> {"code":0}

        ``fileId`` 来自 :meth:`async_prepare_upload` 的返回值。
        """
        return await self._request(
            API_CANCEL_UPLOAD,
            method="POST",
            json_body={"clientType": DEVICE_CLIENT_TYPE, "deviceId": device_id,
                       "fids": list(fids)},
        )

    async def async_file_detail(self, path: str, category: str = "public") -> dict[str, Any]:
        """文件/目录详情（``/filesvc/detail``）。

        实测（2026-10-08）：``{"path": "/file/"}`` 正常返回
        ``{name, size, mtime, dirCount, fileCount}``；
        **路径不存在**时返回 ``code -2``，``fid`` / ``id`` 形态则 ``1101``。
        """
        data = await self._request(
            API_FILE_DETAIL,
            method="POST",
            json_body={"path": path, "category": category},
            extra_headers={"Dest-File": encode_device_path(path)},
        )
        return data.get("data") or {}

    async def async_search_files(
        self, keyword: str, category: str = "public"
    ) -> dict[str, Any]:
        """按关键字搜索（``/filesvc/search``）。

        ⚠️ 参数**尚未解出**：多次实测返回 ``1101``（缺必填字段），
        说明端点仍在但还需要别的参数。保留方法以便后续补，调用方需容错。
        """
        data = await self._request(
            API_FILE_SEARCH,
            method="POST",
            params={"category": category},
            json_body={"keyword": keyword, "clientType": DEVICE_CLIENT_TYPE},
            extra_headers={"Dest-File": encode_device_path(FILE_ROOT_PATH)},
        )
        return data.get("data") or {}

    async def async_trans_move(
        self,
        src_paths: list[str],
        dst_dir: str,
        device_id: str,
        src_category: str = "public",
        dst_category: str = "public",
    ) -> dict[str, Any]:
        """移动文件/目录（``/trans/move``）。

        抓包实据（用户真实操作，``capture.jsonl`` L239）::

            POST /trans/move?category=user
            {"tasks":[{"dCategory":"user","dPath":"/file/__probe_noop__/",
                       "dVersion":1,"deviceId":"9a762c46a872-LAPTOP-DLD5UGDT",
                       "name":"1791391583908","sCategory":"public",
                       "sPaths":["/file/新建文件夹/是否撒/"],
                       "subTaskId":1,"transId":"227734064393"}]}

        与 :meth:`async_delete_paths` 同构：参数嵌在 ``tasks[]`` 里。
        """
        body = {"tasks": [{
            "deviceId": device_id,
            "sCategory": src_category,
            "sPaths": list(src_paths),
            "dCategory": dst_category,
            "dPath": dst_dir,
            "dVersion": 1,
            "name": str(int(asyncio.get_event_loop().time() * 1000)),
            "subTaskId": 1,
            "transId": str(random.randint(10**11, 10**12 - 1)),
        }]}
        return await self._request(API_TRANS_MOVE, method="POST",
                                   params={"category": dst_category},
                                   json_body=body)

    async def async_trans_copy(
        self,
        src_paths: list[str],
        dst_dir: str,
        device_id: str,
        src_category: str = "public",
        dst_category: str = "public",
    ) -> dict[str, Any]:
        """同空间复制文件/目录（``/trans/copy``）。

        与 :meth:`async_trans_move` **同构**（2026-10-08 实机对照实测）：
        `tasks[]` 数组 + 同样的字段，扁平 body 会被拒 ``1100``::

            POST /trans/copy?category=user
            {"tasks":[{"deviceId":..,"sCategory":"user",
                       "sPaths":["/file/源/"],"dCategory":"user",
                       "dPath":"/file/目标/","dVersion":1,"name":"源",
                       "subTaskId":1,"transId":"<12 位>"}]}
            -> {"code":0,"data":{"tasks":[{"centerId":..,"id":..,"transId":..}]}}

        与 move 一样是**异步任务**：``code 0`` 只代表受理，用
        :meth:`async_get_task_status` 查进度。目标目录需**已存在**。
        """
        body = {"tasks": [{
            "deviceId": device_id,
            "sCategory": src_category,
            "sPaths": list(src_paths),
            "dCategory": dst_category,
            "dPath": dst_dir,
            "dVersion": 1,
            "name": str(int(asyncio.get_event_loop().time() * 1000)),
            "subTaskId": 1,
            "transId": str(random.randint(10**11, 10**12 - 1)),
        }]}
        return await self._request(API_TRANS_COPY, method="POST",
                                   params={"category": dst_category},
                                   json_body=body)

    async def async_trans_acrosscopy(
        self,
        src_files: list[dict[str, Any]],
        src_service: str,
        dst_dirs: list[dict[str, Any]],
        dst_service: str,
        device_id: str,
    ) -> dict[str, Any]:
        """跨服务复制（``/trans/acrosscopy``）。

        抓包实据（``capture.jsonl`` L268）—— 把文件空间的图复制进相册::

            {"clientType":3,
             "src":{"files":[{"category":"public","fid":209056,
                              "path":"/file/新建文件夹/屏幕截图 ....png"}],
                    "service":"filesvc"},
             "dest":{"dirs":[{"addTime":1791391599804,"albumId":16,
                              "albumName":"照片","albumType":6,
                              "category":"public"}],
                     "service":"gallery"},
             "deviceId":"9a762c46a872-LAPTOP-DLD5UGDT",
             "subTaskId":1,"transId":"415751786104"}
        """
        body = {
            "clientType": DEVICE_CLIENT_TYPE,
            "deviceId": device_id,
            "src": {"files": src_files, "service": src_service},
            "dest": {"dirs": dst_dirs, "service": dst_service},
            "subTaskId": 1,
            "transId": str(random.randint(10**11, 10**12 - 1)),
        }
        return await self._request(API_TRANS_ACROSSCOPY, method="POST", json_body=body)

    async def async_get_task_status(
        self, task_types: list[int], category: int = 2, service: str = "filesvc"
    ) -> list[dict[str, Any]]:
        """查传输任务中心（只读）。

        ``service`` 取 ``filesvc`` / ``trans`` / ``gallery``，端点都是
        ``/<service>/getAllTaskStatus``。每项含 ``taskId``、``originObjectName``
        （源名）、``destination``（目标目录）、``objectType``（0 文件 / 1 目录 /
        2 相册对象）、``progress``、``errorInfo``、``transId``。

        ⚠️ ``taskTypes`` **必须给全段**，否则只能拿到一小部分（实测 2026-10-09）：
        ``filesvc`` 传 ``[400]`` 只能拿到零星几条，传抓包里的 ``[400..408]``
        才返回完整的 61 条历史。默认段见 :data:`~.const.TASK_TYPES_DEFAULT`。
        """
        creds = await self.async_ensure_credentials()
        data = await self._request(
            f"/{service}/getAllTaskStatus",
            method="POST",
            json_body={
                "clientType": DEVICE_CLIENT_TYPE,
                "deviceId": creds.cloud_dev_id,
                "taskCategory": category,
                "taskTypes": task_types,
            },
        )
        return (data.get("data") or {}).get("tasks") or []

    async def async_clean_task_records(
        self, task_ids: list[int], category: str = "user"
    ) -> dict[str, Any]:
        """清除任务中心的**历史记录**（``/filesvc/cleanTaskRecord``）。

        ⚠️ 关键在字段名：抓包实据（2026-10-09 从 `capture_all_1791417873.jsonl`
        挖出真实报文）是 ``taskIdList``（**不是** ``taskIds`` / ``taskId``）——
        后两种形态实测分别返回 ``1100`` / ``1100``::

            POST /filesvc/cleanTaskRecord
            {"clientType":3,"deviceId":"9a762c46a872-LAPTOP-DLD5UGDT",
             "taskIdList":[13,14,15,16,17]}
            -> {"code":0,"data":{"errorIdList":[]}}

        ``errorIdList`` 为空 = 全部清除成功；有值则是**清除失败**的 taskId。
        只影响任务中心的显示，不碰任何文件。
        """
        creds = await self.async_ensure_credentials()
        return await self._request(
            "/filesvc/cleanTaskRecord",
            method="POST",
            params={"category": category},
            json_body={
                "clientType": DEVICE_CLIENT_TYPE,
                "deviceId": creds.cloud_dev_id,
                "taskIdList": [int(t) for t in task_ids],
            },
        )

    async def async_get_all_trans_tasks(self) -> list[dict[str, Any]]:
        """跨服务传输任务**全表**（``/trans/getAllTask``，实测 ``code 0``）。

        与 :meth:`async_get_task_status` 的区别：后者要传 ``taskTypes``
        只取指定段；这个不带筛选，返回 `trans` 域全部任务。
        实测（2026-10-08）：``{"code":0,"data":{"tasks":[]}}``；
        同一批探测里 ``/filesvc/getAllTask`` 返回**非 JSON**（不可用）。
        """
        creds = await self.async_ensure_credentials()
        data = await self._request(
            "/trans/getAllTask",
            method="POST",
            json_body={
                "clientType": DEVICE_CLIENT_TYPE,
                "deviceId": creds.cloud_dev_id,
                "taskCategory": 2,
            },
        )
        return (data.get("data") or {}).get("tasks") or []

    # ------------------------------------------------------------------
    # 文件空间（NAS 视图，/filesvc/files + Dest-File 头）
    # ------------------------------------------------------------------
    async def async_list_files(
        self,
        dir_path: str = FILE_ROOT_PATH,
        offset: int = 0,
        limit: int = FILES_PAGE_SIZE,
        category: str = FILE_FILES_CATEGORY,
    ) -> dict[str, Any]:
        """列文件空间目录。

        ⚠️ ``category`` 区分**两个独立的空间**（实测 2026-10-08）：
        ``user`` = 「我的文件」，``public`` = **「共享」**。
        用户在 PC 客户端「共享」里建的目录只在 ``public`` 下可见；
        此前硬编码 ``user`` 导致共享空间的内容**完全看不到**。

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
                "category": category,
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
    async def async_fetch_image(
        self,
        device_path: str,
        service: str = "gallery",
        category: str = "",
    ) -> bytes | None:
        """按设备路径取图（``/picture/thumb|asset|raw|hdc_1080`` 等）。

        ⚠️ ``category`` 是能否取到的**决定因素**（实测 2026-10-08）：
        * 相册域路径（``/picture/...``）→ ``category=""``（空）即可
        * **文件空间/共享空间缩略图**
          （``/file/.File_Syssvc/thumb/0001/7137.jpg``）
          → 必须 ``category="public"``；传空会 404/403 取不到图。

        ``service`` 实测对结果无影响（``gallery``/``filesvc`` 均可用）；
        ``usb`` 保持 ``false``（``true`` 会 403）。
        """
        if not device_path:
            return None
        await self.async_ensure_credentials()
        query = (
            f"type=download&fileVer=&category={category}"
            f"&service={service}&usb=false"
        )
        url = (
            f"{self._data_base()}{DATA_DOWNLOAD_PATH}"
            f"{encode_device_path(device_path)}?{query}"
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
