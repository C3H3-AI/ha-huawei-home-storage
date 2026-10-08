"""设备文件传输：流式上传 / 下载 / 建目录。

**为什么单独一个模块**：面板上传的文件可能很大，而 ``api/device.py`` 的
``async_upload_file`` 签名是 ``payload: bytes``（整份进内存）——
拿它传大文件会把 HA 的内存吃满。

所以这里只放**传输原语**，供需要流式处理的功能复用
（当前是面板的上传视图 ``views.py``）。

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

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp

from .api.device import encode_device_path
from .const import API_PREPARE_UPLOAD, DEVICE_CLIENT_TYPE

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
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("建目录失败 %s: %s", path, err)
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
) -> dict[str, Any]:
    """把字节流分块上传到设备（内存占用 ≈ 一个 chunk）。

    ``total_size`` 必须准确（``prepareUpload`` 要声明大小）；调用方从
    ``Content-Length`` 或备份元数据里拿。
    """
    await client.async_ensure_credentials()
    fname = dest_path.rstrip("/").rsplit("/", 1)[-1]
    src_path = f"/win/C/tmp/{fname}"
    view_path = f"Pictures/MemoSpace/{fname}"

    # ① prepareUpload：声明总大小，拿 fileId / sessionId
    prep = await client._request(  # noqa: SLF001（同包内复用）
        API_PREPARE_UPLOAD,
        method="POST",
        params={"category": category},
        json_body={
            "deviceId": device_id,
            "uploadType": 1,
            "files": [
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
            ],
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
            "ctime": str(start),
            "deviceId": device_id,
            "fileId": file_id,
            "fileVer": "",
            "mediaType": "0",
            "mtime": str(start),
            "orientation": "0",
            "service": "filesvc",
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
            "Content-Disposition": f'attachment;filename="{fname}"',
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

    if sent != total_size:
        _LOGGER.warning(
            "上传字节数与声明不一致：实发 %s / 声明 %s（%s）", sent, total_size, dest_path
        )
    return last or {"code": 0, "data": {"path": dest_path}}
