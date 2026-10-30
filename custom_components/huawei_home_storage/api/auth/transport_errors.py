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

from .smarthome_errors import HuaweiSmartHomeError


class SmartHomeApiError(HuaweiSmartHomeError):
    """Base error for SmartHome HTTP operations."""


class AuthExpiredError(SmartHomeApiError):
    """The HMS-lite session is expired or invalid."""


class PermissionDeniedError(SmartHomeApiError):
    """The account cannot access the requested resource."""


class RateLimitedError(SmartHomeApiError):
    """The remote service rate-limited a request."""


class InvalidResponseError(SmartHomeApiError):
    """The remote response is not a supported schema."""


class TransientNetworkError(SmartHomeApiError):
    """The request failed due to a retryable network condition."""


class RemoteOperationError(SmartHomeApiError):
    """The remote service returned an operation error."""
