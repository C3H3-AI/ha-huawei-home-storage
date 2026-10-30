"""华为账号密码登录（移植自 ha-huawei-smarthome，GPL-3.0）。

本子包使「账号密码登录」完全自包含 —— 不再需要安装 huawei_smarthome 集成。
详见 :mod:`.huawei` 顶部的来源与许可声明。
"""

from .huawei import HuaweiSmartHomeAuthProvider
from .interface import ChallengeChannel, LoginChallenge, LoginStart

__all__ = [
    "ChallengeChannel",
    "HuaweiSmartHomeAuthProvider",
    "LoginChallenge",
    "LoginStart",
]
