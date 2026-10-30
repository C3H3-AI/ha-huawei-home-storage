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

from dataclasses import dataclass
from typing import Protocol

from ..domain.models import AuthSession

CHALLENGE_KIND_DEVICE = "device"
CHALLENGE_KIND_SMS = "sms"
CHALLENGE_KIND_EMAIL = "email"

_SMS_ACCOUNT_TYPES = frozenset({"2", "6"})
_EMAIL_ACCOUNT_TYPES = frozenset({"1", "5"})
_DEVICE_ACCOUNT_TYPES = frozenset({"-1"})


@dataclass(frozen=True, slots=True)
class ChallengeChannel:
    """One verification channel offered by the Huawei challenge response."""

    name: str
    account_type: str
    kind: str
    sent: bool

    @property
    def key(self) -> str:
        """Stable identifier used as the selector value in the config flow."""

        return f"{self.kind}:{self.account_type}:{self.name}"

    @property
    def is_sms(self) -> bool:
        return self.kind == CHALLENGE_KIND_SMS


def channel_kind(account_type: object) -> str:
    """Classify an ``authCodeSentList`` entry into a delivery channel kind."""

    value = str(account_type)
    if value in _SMS_ACCOUNT_TYPES:
        return CHALLENGE_KIND_SMS
    if value in _EMAIL_ACCOUNT_TYPES:
        return CHALLENGE_KIND_EMAIL
    if value in _DEVICE_ACCOUNT_TYPES:
        return CHALLENGE_KIND_DEVICE
    return CHALLENGE_KIND_DEVICE


@dataclass(frozen=True, slots=True)
class LoginChallenge:
    """Challenge information shown to the user."""

    prompt: str
    challenge_name: str
    challenge_type: str
    channels: tuple[ChallengeChannel, ...] = ()


@dataclass(frozen=True, slots=True)
class LoginStart:
    """Result of starting an account login."""

    session: AuthSession | None = None
    challenge: LoginChallenge | None = None


class AuthProvider(Protocol):
    """Port for Huawei account authentication."""

    async def async_begin_login(self, account: str, password: str) -> LoginStart:
        """Start account/password login."""

    async def async_select_challenge_channel(
        self,
        channel: ChallengeChannel,
    ) -> LoginChallenge:
        """Choose a verification channel and dispatch its code."""

    async def async_complete_challenge(self, code: str) -> AuthSession:
        """Complete a pending device challenge."""

    async def async_refresh_oauth(self, session: AuthSession) -> AuthSession:
        """Refresh the OAuth session token with the Huawei service token."""

    async def async_refresh_hms_lite(self, session: AuthSession) -> AuthSession:
        """Reissue the HMS-lite token through the Huawei silent-auth flow."""
