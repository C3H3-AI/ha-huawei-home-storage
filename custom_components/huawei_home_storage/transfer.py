"""设备文件传输：流式上传 / 下载 / 建目录。

**为什么单独一个模块**：面板上传的文件可能很大，而 ``api/device.py`` 的
``async_upload_file`` 签名是 ``payload: bytes``（整份进内存）——
拿它传大文件会把 HA 的内存吃满。

所以这里只放**传输原语**，供需要流式处理的功能复用：
  * 上传：面板上传视图（``views.py``）、HA 备份代理（``backup.py``）
  * 下载：HA 备份代理（恢复时读取设备上的 tar）

这样也避免改动 ``api/device.py`` —— 上游正在频繁改那个文件，
少一处交集就少一处冲突。

实测依据（2026-10-08，AS6020-02 / 6.1.0.7）：
  * ``prepareUpload`` 返回 ``{fileId, sessionId, offset, ...}``，
    声明总大小后可**分多次** POST ``<数据通道>/upload``
  * 每块带 ``Content-Range: bytes <start>-<end>/<total>``：
    中间块返回 ``HTTP 201``（回显区间），**最后一块**返回
    ``{"code":0,"data":{"path":...}}``
  * 两块 20480B 拼成 40960B 落盘，大小精确
  * **目标目录必须已存在**，否则连接被直接断开（不是报错，是断开）
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from urllib.parse import quote as _urllib_quote
from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp

from .api.device import encode_device_path
from .const import (
    API_GALLERY_PREPARE_UPLOAD,
    API_PREPARE_UPLOAD,
    DATA_DOWNLOAD_PATH,
    DEVICE_CLIENT_TYPE,
)

_LOGGER = logging.getLogger(__name__)

# 分块大小。8 MiB 在设备侧表现稳定，且进度回调粒度足够细。
CHUNK_SIZE = 8 * 1024 * 1024


class TransferError(Exception):
    """上传/下载失败。"""


async def ensure_dir(client: Any, dir_path: str, category: str = "user") -> bool:
    """确保目录存在（不存在则建）。返回是否可用。

    先列一次父目录判断，避免每次都发 mkdir（重名 mkdir 会报错）。
    """
    path = dir_path if dir_path.endswith("/") else dir_path + "/"
    parent = path.rstrip("/").rsplit("/", 1)[0] + "/"
    name = path.rstrip("/").rsplit("/", 1)[-1]
    try:
        listing = await client.async_list_files(parent, category=category)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("列目录失败 %s: %s", parent, err)
        return False
    for item in listing.get("files") or []:
        if item.get("name") == name and item.get("type") != 8:
            return True
    try:
        await client.async_mkdir(path.rstrip("/"), category=category)
    except Exception as err:  # noqa: BLE001
        # mkdir 本身失败也继续往下轮询：可能是"父目录刚建、还没被索引"导致的
        # 瞬时失败，轮询能看到就当成功。
        _LOGGER.debug("建目录失败 %s: %s", path, err)

    # ⚠️ mkdir 在设备上是**异步任务**，要过一会儿目录才会被索引出来。
    # 这期间往该目录上传，设备**直接断开连接**（不是返回错误码，是断连），
    # 客户端看到的是 "Remote end closed connection without response" ——
    # 面板上表现为「新建文件夹 → 立刻上传」必失败，而且换文件名、重试都没用，
    # 只有等几秒再传才行（用户根本不会这么想）。
    #
    # 所以建完必须**等它真的能在父目录里列出来**再返回。
    for _ in range(12):  # 最多约 6s
        await asyncio.sleep(0.5)
        try:
            listing = await client.async_list_files(parent, category=category)
        except Exception:  # noqa: BLE001
            continue
        for item in listing.get("files") or []:
            if item.get("name") == name and item.get("type") != 8:
                return True
    _LOGGER.debug("目录建好但一直没出现在列表里: %s", path)
    return False


async def upload_stream(
    client: Any,
    dest_path: str,
    total_size: int,
    chunks: AsyncIterator[bytes],
    *,
    device_id: str,
    category: str = "user",
    chunk_size: int = CHUNK_SIZE,
    on_progress: Callable[[int], None] | None = None,
    service_type: str = "filesvc",
    file_bytes: bytes | None = None,
    mtime_ms: int | None = None,
) -> dict[str, Any]:
    """把字节流分块上传到设备（内存占用 ≈ 一个 chunk）。

    ``total_size`` 必须准确（``prepareUpload`` 要声明大小）；调用方从
    ``Content-Length`` 或备份元数据里拿。

    ⚠️ **相册域（``service_type="gallery"``）至今没跑通**：真机 ``30104``，
    抓包里官方 Windows 客户端连发 19 次 ``/gallery/prepareUpload``、0 条响应
    （自己也在重试）。所以这条分支是**保留事实**而非可用功能 —— 别看到
    ``gallery`` 就以为"上传照片进相册"能用。当前可行的进相册路径是：
    先传到文件空间，再 ``copy_to_album``（``/trans/acrosscopy``）。

    ``service_type`` 决定走哪套 prepareUpload（插件反编译：
    ``TransmissionApi.filePrepareUpload`` → ``/filesvc/prepareUpload``，
    ``galleryPrepareUpload`` → ``/gallery/prepareUpload``）：

    * ``filesvc``：文件空间，``files`` 元素用
      ``srcPath``/``path(完整目标路径)``/``sessionId``/``taskId``
    * ``gallery``：相册域，**同样是 ``files``**，但 ``path`` 传空串、且
      **没有 hash/fileVer 字段**（抓包实测，见下）

    ⚠️ 这两段原来是按插件反编译写的（gallery 用 ``fileSrcPath``/``hdcPath``/
    ``fileHash``，还要求真实 MD5）。抓包证明那是错的，照它写会固定回 ``1101``。
    教训：**反编译能看出类结构，看不出运行时到底序列化了哪些字段**。

    另外：``/gallery/addAlbumMemb`` 只认相册域 fileId（文件域的会被 30101 拒）。
    但"把照片放进相册"目前走的是 ``copy_to_album``（跨域复制），不需要这个 id。
    """
    if total_size is None or total_size <= 0:
        raise TransferError(f"上传大小无效（{total_size}）：{dest_path}")
    # ⚠️ 数据通道凭据短时效（见 api/device.py async_upload_file 的注释），
    # 分块上传可能持续数分钟 —— 开头保证一次新鲜凭据。
    # 必须用**节流版**：面板一次选多张照片会连着调这里，无脑强刷会在
    # 第 4~5 个文件时被设备限流（返回空 data），于是"多选上传必挂"。
    await client.async_ensure_fresh_credentials()
    fname = dest_path.rstrip("/").rsplit("/", 1)[-1]
    src_path = f"/win/C/tmp/{fname}"
    view_path = f"Pictures/MemoSpace/{fname}"

    # ① prepareUpload：声明总大小，拿 fileId / sessionId
    #
    # ⚠️ 两套报文结构完全不同（插件反编译 TransmissionApi：
    #   filePrepareUpload    → /filesvc/prepareUpload → FilePrepareUploadRequestBean
    #   galleryPrepareUpload → /gallery/prepareUpload → GalleryPrepareUploadRequestBean
    #                                                   .$GalleryRequestBean）
    # 相册域的 files 元素是 fileHash/fileSrcPath/hdcPath，没有 path/sessionId/taskId，
    # 且 fileHash 必须是真实文件 MD5 —— 所以相册域上传必须传 file_bytes。
    if service_type == "gallery":
        # 相册域 prepareUpload 的**真实**报文（抓包，非反编译推断）：
        # _frida/capture_all_1791417873.jsonl:24953 —— 官方 Windows 客户端
        #   POST /gallery/prepareUpload
        #   {"deviceId":...,"uploadType":1,"files":[{"viewPath":...,"srcPath":...,
        #     "path":"",                 <-- 空串，路径由设备分配
        #     "sessionId":"","fileId":0,"fileSize":116316,
        #     "orientation":0,"taskId":195}]}
        # 键名是 files（不是 dataList）、**没有 hash**、也没有 fileVer。
        # ⚠️ 但这条路径至今没成功过：抓包里官方客户端连发 19 次同样请求、
        #    0 条响应 —— 连官方 PC 端自己都在失败重试。别当成"只差一个字段"。
        prep_path = API_GALLERY_PREPARE_UPLOAD
        prep_key = "files"
        prep_items = [
            {
                "viewPath": view_path,
                "srcPath": src_path,
                "path": "",
                "sessionId": "",
                "fileId": 0,
                "fileSize": total_size,
                "orientation": 0,
                "taskId": 0,
            }
        ]
    else:
        prep_path = API_PREPARE_UPLOAD
        prep_files = [
            {
                "viewPath": view_path,
                "srcPath": src_path,
                "path": dest_path,
                "sessionId": "",
                "fileId": 0,
                "fileSize": total_size,
                "orientation": 0,
                "taskId": 0,
            }
        ]
    prep = await client._request(  # noqa: SLF001（同包内复用）
        prep_path,
        method="POST",
        params={"category": category},
        json_body={
            "deviceId": device_id,
            "uploadType": 1,
            "files": prep_files,
        },
    )
    items = (prep.get("data") or {}).get("fileList") or []
    if not items:
        raise TransferError(f"prepareUpload 未返回 fileList: {str(prep)[:160]}")
    file_id = str(items[0].get("fileId"))
    session_id = str(items[0].get("sessionId"))

    durl = client._data_base()  # noqa: SLF001
    base_headers = client._data_headers()  # noqa: SLF001
    dest_encoded = encode_device_path(dest_path)

    # ⚠️ 文件名必须百分号编码（2026-10-29 修）：
    # ``Content-Disposition`` 是 HTTP 头，规范上只允许 ASCII（latin-1 编码）。
    # 直接塞中文会抛 ``UnicodeEncodeError``，或者发出乱码被设备拒收 ——
    # 而**用户遇到的第一个文件通常就是中文名**（"照片.jpg"），于是"上传
    # 完全不能用"，且错误信息与文件名毫无关系，极难定位。
    # 同一份报文在 ``api/device.py::async_upload_file`` 里早就编码了，
    # 这里是漏改的第二处实现。
    fname_quoted = _urllib_quote(fname)

    # ⚠️ 时间戳必须是**真实 Unix 毫秒**（2026-10-29 修）。
    # 原来传的是 ``start`` —— 那是**分块在文件里的字节偏移**，量级几百/几千，
    # 而真实时间戳是 1.7e12。后果：照片在设备上显示成 1970 年，排序永远沉底，
    # 但接口全部 code 0、没有任何报错。
    now_ms = int(mtime_ms if mtime_ms is not None else time.time() * 1000)

    sent = 0
    buf = bytearray()
    last: dict[str, Any] = {}

    async def _send(chunk: bytes, start: int) -> dict[str, Any]:
        """发一块。start 为该块在文件中的起始偏移。"""
        end = start + len(chunk) - 1
        # 17 个 query 参数一个都不能少（缺则 openresty 直接 500）
        query = {
            "category": category,
            "clientType": str(DEVICE_CLIENT_TYPE),
            "comment": "",
            "ctime": str(now_ms),
            "deviceId": device_id,
            "fileId": file_id,
            "fileVer": "",
            "mediaType": "0",
            "mtime": str(now_ms),
            "orientation": "0",
            "service": service_type,
            "size": str(total_size),
            "sourceAlbum": "0",
            "srcPath": src_path,
            "takenTime": "0",
            "uploadType": "1",
            "usb": "false",
            "viewPath": view_path,
        }
        headers = {
            **base_headers,
            "Content-Disposition": f'attachment;filename="{fname_quoted}"',
            "Content-Type": "application/octet-stream",
            "Dest-File": dest_encoded,
            "X-Session-ID": session_id,
            "Content-Range": f"bytes {start}-{end}/{total_size}",
            # ⚠️ 必需：去掉即 500（实测）
            "Expect": "100-continue",
        }
        # 大块给足超时；小块至少 120s
        timeout = aiohttp.ClientTimeout(total=max(300, len(chunk) // 2000))
        async with client._session.post(  # noqa: SLF001
            f"{durl}/upload", params=query, headers=headers, data=chunk, timeout=timeout
        ) as resp:
            text = await resp.text()
        if resp.status not in (200, 201):
            raise TransferError(f"上传分块失败 HTTP {resp.status}: {text[:140]}")
        if resp.status == 200:
            import json as _json  # noqa: PLC0415

            try:
                parsed = _json.loads(text)
            except ValueError:
                parsed = {}
            code = str(parsed.get("code"))
            if code not in ("0", "None"):
                raise TransferError(f"上传被拒 code={code}: {text[:140]}")
            return parsed
        return {}

    async for piece in chunks:
        buf += piece
        while len(buf) >= chunk_size:
            block = bytes(buf[:chunk_size])
            del buf[:chunk_size]
            last = await _send(block, sent)
            sent += len(block)
            if on_progress:
                on_progress(sent)

    if buf:  # 收尾块
        last = await _send(bytes(buf), sent)
        sent += len(buf)
        if on_progress:
            on_progress(sent)

    # ⚠️ 声明大小与实发不符 = 设备在等更多字节，文件是不完整的。
    # 之前只 warning 并返回成功，会让一个残缺的备份被当成成功的备份
    # （恢复时才发现打不开）。这里必须失败，让 HA 重试或报错。
    if sent != total_size:
        raise TransferError(
            "上传字节数与声明不一致：实发 %s / 声明 %s（%s）—— 文件不完整，已中止"
            % (sent, total_size, dest_path)
        )
    if total_size > 0 and not last:
        # 有数据但没拿到设备的收尾确认，同样视为未真正完成
        raise TransferError(
            "设备未返回上传完成确认（%s，%s 字节）" % (dest_path, total_size)
        )
    result = last or {"code": 0, "data": {"path": dest_path}}
    # ⚠️ prepareUpload 给的 fileId 是**相册域**的，回传它，
    # 调用方才能"上传后直接加入相册"（此前丢弃导致这条路走不通）。
    if isinstance(result, dict):
        result.setdefault("fileId", file_id)
        if isinstance(result.get("data"), dict):
            result["data"].setdefault("fileId", file_id)
    return result


async def download_stream(
    client: Any,
    device_path: str,
    *,
    category: str = "user",
    chunk_size: int = 256 * 1024,
) -> AsyncIterator[bytes]:
    """流式下载设备文件（供备份恢复用，内存占用 ≈ 一个 chunk）。"""
    await client.async_ensure_credentials()
    query = f"type=download&fileVer=&category={category}&service=filesvc&usb=false"
    url = f"{client._data_base()}{DATA_DOWNLOAD_PATH}{encode_device_path(device_path)}?{query}"  # noqa: SLF001
    timeout = aiohttp.ClientTimeout(total=None, sock_read=120)
    async with client._session.get(  # noqa: SLF001
        url, headers=client._data_headers(), timeout=timeout  # noqa: SLF001
    ) as resp:
        if resp.status != 200:
            raise TransferError(f"下载失败 HTTP {resp.status}（{device_path}）")
        async for block in resp.content.iter_chunked(chunk_size):
            yield block
