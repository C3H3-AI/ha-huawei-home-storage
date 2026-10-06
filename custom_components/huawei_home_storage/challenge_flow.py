"""验证码投递渠道选择（短信 / 已登录设备推送）的共享 UI 辅助。

为什么单独一个模块
------------------
``config_flow.py`` 与 ``accounts_flow.py`` 都要用这几个辅助函数，但
``config_flow`` 在模块顶层就 ``from .accounts_flow import _AccountStepsMixin``。
若让 ``accounts_flow`` 反过来在顶层 import ``config_flow``，就会形成循环导入：
config_flow 执行到该 import 行时 ``_selectable_channels`` 尚未定义，直接
ImportError。因此把这段无状态逻辑放在独立的叶子模块里，两边都从这里取。

移植来源
--------
上游 ``ha-huawei-smarthome`` 的 ``config_flow.py``（``_selectable_channels`` /
``_channel_label`` / ``_channel_schema``，commit 04fd6e8）。上游把这几个函数
放在 config_flow 里，我们挪到本模块以适配自己的双 flow 结构，逻辑保持一致。
"""
from __future__ import annotations

import voluptuous as vol

from .api.auth.interface import (
    CHALLENGE_KIND_DEVICE,
    CHALLENGE_KIND_SMS,
    ChallengeChannel,
    LoginChallenge,
)
from .const import CONF_CHALLENGE_CHANNEL

#: 可供用户选择的验证码投递渠道。
#: 只列「短信」与「已登录设备」两类，邮件渠道不让用户选（与上游
#: ``_SELECTABLE_CHALLENGE_KINDS`` 一致），避免出现选了也没用的选项。
_SELECTABLE_CHALLENGE_KINDS = (CHALLENGE_KIND_DEVICE, CHALLENGE_KIND_SMS)


def _selectable_channels(
    challenge: LoginChallenge | None,
) -> tuple[ChallengeChannel, ...]:
    """列出用户真正可选的验证码渠道。"""
    if challenge is None:
        return ()
    return tuple(
        channel
        for channel in challenge.channels
        if channel.kind in _SELECTABLE_CHALLENGE_KINDS
    )


def _channel_label(channel: ChallengeChannel) -> str:
    """给渠道一个人话标签。"""
    if channel.is_sms:
        return f"短信验证码 → {channel.name}"
    return f"已登录设备推送 → {channel.name}"


def _channel_schema(channels: tuple[ChallengeChannel, ...]) -> vol.Schema:
    """构建验证码渠道选择器。"""
    options = {channel.key: _channel_label(channel) for channel in channels}
    return vol.Schema({vol.Required(CONF_CHALLENGE_CHANNEL): vol.In(options)})