"""华为账号密码登录实现（移植自 ha-huawei-smarthome）。

来源  : https://github.com/xiasi0/ha-huawei-smarthome
commit: 04fd6e8115c3d7bb30e5866b138b30fba7379b36 (2026-10-05)
作者  : xiasi0
许可  : GPL-3.0（经原作者同意移植；本仓库整体采用 GPL-3.0）

移植说明（2026-10-06）
----------------------
原先本集成通过 ``import custom_components.huawei_smarthome.*`` 复用登录实现，
属于运行时硬耦合：对方未安装 / 改名 / 升级不兼容时本集成直接 setup_error
且无法自愈。经原作者同意后把登录实现复制入本仓库，使「账号密码登录」成为
**完全自包含**能力，不再依赖任何外部集成。

相对上游只改了导入路径（``..api.transport`` → ``.transport``、
``..const`` → ``.._smarthome_const``、``..errors`` → ``.smarthome_errors``），
登录逻辑本身未作任何修改。同步上游时请对照上述 commit 取最新文件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .transport_errors import TransientNetworkError


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Minimal HTTP response used by protocol adapters."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class AsyncHttpTransport(Protocol):
    """HTTP transport port."""

    async def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout: float = 20.0,
    ) -> HttpResponse:
        """Send one HTTP request."""


class AiohttpHttpTransport:
    """Use Home Assistant's shared aiohttp client session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout: float = 20.0,
    ) -> HttpResponse:
        """Send a non-blocking HTTP request."""

        try:
            import aiohttp
        except ImportError as error:  # pragma: no cover - supplied by HA
            raise TransientNetworkError("aiohttp is unavailable") from error
        try:
            async with self._session.request(
                method,
                url,
                headers=dict(headers),
                data=body,
                timeout=timeout,
            ) as response:
                return HttpResponse(
                    status=response.status,
                    headers={str(k): str(v) for k, v in response.headers.items()},
                    body=await response.read(),
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
            raise TransientNetworkError("SmartHome HTTP transport failed") from error


class UrllibHttpTransport:
    """Standard-library transport for standalone tests."""

    async def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout: float = 20.0,
    ) -> HttpResponse:
        """Run blocking urllib work off the event loop."""

        return await asyncio.to_thread(
            self._request_sync,
            method,
            url,
            dict(headers),
            body,
            timeout,
        )

    @staticmethod
    def _request_sync(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> HttpResponse:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    status=response.status,
                    headers={str(k): str(v) for k, v in response.headers.items()},
                    body=response.read(),
                )
        except HTTPError as error:
            return HttpResponse(
                status=error.code,
                headers={str(k): str(v) for k, v in error.headers.items()},
                body=error.read(),
            )
        except (URLError, TimeoutError, OSError) as error:
            raise TransientNetworkError("SmartHome HTTP transport failed") from error
