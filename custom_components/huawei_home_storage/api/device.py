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
    API_PREPARE_UPLOAD,
    API_CANCEL_UPLOAD,
    API_BATCH_OPERATION,
    API_ALL_FILES,
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

    async def async_get_album_cfg(self, album_id: int, album_type: int) -> dict[str, Any]:
        """相册详情：只含元数据 + coverInfo，**不含成员列表**。"""
        data = await self._request(
            API_ALBUM_CFG, {"albumId": album_id, "albumType": album_type}
        )
        return data.get("data") or {}

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

    async def async_get_recycle_files(self) -> dict[str, Any]:
        data = await self._request(API_RECYCLE, {"category": "user", "limit": 1, "offset": 0})
        return data.get("data") or {}

    async def async_get_usb_status(self) -> dict[str, Any]:
        data = await self._request(API_USB_STATUS)
        return data.get("data") or {}

    # ------------------------------------------------------------------
    # 上传（/filesvc/prepareUpload，见 docs/huawei-storage-upload-protocol.md）
    # ------------------------------------------------------------------
    async def async_prepare_upload(
        self, dest_path: str, file_size: int, src_path: str | None = None
    ) -> dict[str, Any]:
        """上传第一步：向设备申请文件占位，拿 ``fileId`` + ``sessionId``。

        实测（2026-10-08，AS6020-02）：::

            POST /filesvc/prepareUpload?clientType=3&deviceId=<devId>
            {"deviceId":..., "uploadType":1,
             "files":[{"path":"/file/x.txt","fileSize":11,"srcPath":"/file/x.txt"}]}
            -> {"code":0,"data":{"fileList":[{"fileId":...,"sessionId":...,
                "offset":0,"path":...,"srcPath":...,"status":0,"taskId":0}]}}

        返回 ``data.fileList[0]``；失败（无 fileList/sessionId）时抛
        :class:`RuntimeError`。后续字节流与完成通知见协议文档第 1 节，
        尚未落地（设备对第三方身份仍返回 ``1004``，见文档「未完成」）。
        """
        src = src_path or dest_path
        creds = await self.async_ensure_credentials()
        data = await self._request(
            API_PREPARE_UPLOAD,
            method="POST",
            json_body={
                "deviceId": creds.cloud_dev_id,
                "uploadType": 1,
                "files": [{"path": dest_path, "fileSize": file_size, "srcPath": src}],
            },
        )
        items = ((data.get("data") or {}).get("fileList") or [])
        if not items or not items[0].get("sessionId"):
            raise RuntimeError(f"prepareUpload 未返回会话: {data}")
        return items[0]

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
        * ``operation=remove`` 决定了动作，``type`` 决定去向：
          ``recycle``（进回收站，可逆）/ ``delete``（彻底删）
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

        ⚠️ 四个易错点（实测，错一个就 ``prog=-1`` 失败）：
        * ``operation`` 是 **``recycle``**（不是 ``remove``）
        * ``type`` 是 **``recover``**
        * ``rid`` 必须是**数组**
        * tasks 内的 ``type`` 用 **4**（目录）/ 0（文件）

        ``rid`` 来自 :meth:`async_list_recycle`（必须用 GET 取）。
        恢复是异步任务，用 :meth:`async_get_task_status` 查 ``progress`` 确认。
        """
        body = {"tasks": [{
            "clientType": DEVICE_CLIENT_TYPE,
            "deviceId": device_id,
            "name": name,
            "rid": [rid],
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

    async def async_all_files(
        self, category: str = "public", offset: int = 0, limit: int = FILES_PAGE_SIZE
    ) -> dict[str, Any]:
        """全文件视图（``/filesvc/allFiles``，端点实测存在）。

        与 :meth:`async_list_files` 的差别：后者按目录逐层浏览（需 ``Dest-File``），
        前者是扁平的全量视图。
        """
        data = await self._request(
            API_ALL_FILES,
            {"category": category, "limit": limit, "offset": offset},
            extra_headers={"Dest-File": encode_device_path(FILE_ROOT_PATH)},
        )
        inner = data.get("data") or {}
        return {"files": inner.get("files") or [], "count": inner.get("count")}

    async def async_file_detail(self, path: str, category: str = "public") -> dict[str, Any]:
        """文件/目录详情（``/filesvc/detail``）。

        ⚠️ 参数尚未完全解出（实测 2026-10-08）：
        * ``{"path": ...}`` → ``code -2``（字段形态对，但值需为**有效**路径）
        * ``fid`` / ``id`` / ``fids`` → ``1101``（缺字段）
        保留方法以便后续补参数；调用方应容错。
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

        ⚠️ HANDOFF §1.6 记录该端点返回 ``1003``；本次实测返回 ``1101``
        （缺必填字段），说明**它仍在但需要更多参数**，未完整解出。
        保留方法以便后续补参数，调用方应容错处理。
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

        ``service`` 取 ``filesvc``（文件空间，``taskType`` 400 段）或
        ``trans``（跨服务传输，含 201/300 段）。返回任务列表，每项含
        ``originObjectName``（源名）、``destination``（目标目录）、
        ``objectType``（0 文件 / 1 目录 / 2 相册对象）、``progress``、
        ``transId``。实测 2026-10-08。
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
