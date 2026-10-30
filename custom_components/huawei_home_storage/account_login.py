"""面板内登录/添加账号（WebSocket API）。

三步流程与 HA 配置流一致，但状态放在**内存**里（不落盘），
密码只在本次登录会话中使用，成功后按现有行为写入 config entry
（与配置流一致，便于后续自动续期）。

会话用一次性 ``flow_id`` 标识，5 分钟无进展自动过期。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import decorators as _wsdec
from homeassistant.helpers import config_validation as cv

from . import api  # noqa: F401  (hass.data 里存会话)
from .api import huawei_account
from .const import DOMAIN

SESSION_TTL = 300  # 5 分钟
cmd_start = "huawei_home_storage/login_start"
cmd_channel = "huawei_home_storage/login_channel"
cmd_code = "huawei_home_storage/login_code"
_PENDING: dict[str, dict[str, Any]] = {}


def _entry(hass: HomeAssistant, entry_id: str):
    """取配置条目；未指定或找不到时取第一个。"""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if entry_id:
        for e in entries:
            if e.entry_id == entry_id:
                return e
    return entries[0]


def _purge() -> None:
    """清理过期会话。"""
    now = time.time()
    for k in [k for k, v in _PENDING.items() if now - v["ts"] > SESSION_TTL]:
        _PENDING.pop(k, None)


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """注册面板登录用的 WebSocket 命令。"""

    @websocket_api.async_response
    async def ws_login_start(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
        """第一步：账号 + 密码 → 返回 challenge 与可选渠道。"""
        entry_id = msg.get("entry_id") or ""
        account = str(msg.get("account") or "").strip()
        password = str(msg.get("password") or "")
        if not account or not password:
            connection.send_error(msg["id"], "invalid_input", "账号与密码不能为空")
            return

        entry = _entry(hass, entry_id)
        if entry is None:
            connection.send_error(msg["id"], "no_entry", "没有可添加账号的配置条目")
            return
        # 已存在同账号则拒绝（与配置流一致）
        existing = {
            str((a or {}).get("account") or (a or {}).get("key") or "")
            for a in (entry.data.get("accounts") or [])
        }
        if account in existing:
            connection.send_error(msg["id"], "account_exists", "该账号已添加")
            return

        try:
            provider = await huawei_account.async_create_provider(hass, account)
            result = await huawei_account.async_begin_login(provider, account, password)
        except Exception as err:  # noqa: BLE001
            connection.send_error(msg["id"], "login_failed", str(err)[:200])
            return

        _purge()
        flow_id = uuid.uuid4().hex
        _PENDING[flow_id] = {
            "ts": time.time(),
            "entry_id": entry.entry_id,
            "account": account,
            "password": password,
            "provider": provider,
            "challenge": getattr(result, "challenge", None),
            "session": getattr(result, "session", None),
        }

        # 无需验证码（已信任设备）→ 直接完成
        if _PENDING[flow_id]["session"] is not None:
            done = await _finish(hass, flow_id)
            if done:
                connection.send_result(msg["id"], {"done": True, "flow_id": flow_id})
                return
            connection.send_error(msg["id"], "auth_failed", "登录未完成")
            return

        challenge = _PENDING[flow_id]["challenge"]
        channels = []
        try:
            channels = [
                {"key": str(getattr(c, "key", i)), "label": str(getattr(c, "label", c))}
                for i, c in enumerate(huawei_account.selectable_channels(challenge))
            ]
        except Exception:  # noqa: BLE001
            channels = []
        connection.send_result(msg["id"], {
            "done": False,
            "flow_id": flow_id,
            "prompt": str(getattr(challenge, "prompt", "") or ""),
            "channels": channels,
        })

    @websocket_api.async_response
    async def ws_login_channel(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
        """第二步：选择验证码渠道 → 华为下发验证码（短信会真的发）。"""
        flow_id = str(msg.get("flow_id") or "")
        state = _PENDING.get(flow_id)
        if state is None:
            connection.send_error(msg["id"], "flow_expired", "会话已过期，请重新登录")
            return
        state["ts"] = time.time()
        try:
            challenge = await huawei_account.async_select_challenge_channel(
                state["provider"], msg.get("channel")
            )
            state["challenge"] = challenge
        except Exception as err:  # noqa: BLE001
            connection.send_error(msg["id"], "dispatch_failed", str(err)[:200])
            return
        connection.send_result(msg["id"], {
            "prompt": str(getattr(challenge, "prompt", "") or ""),
        })

    @websocket_api.async_response
    async def ws_login_code(hass: HomeAssistant, connection: Any, msg: dict[str, Any]) -> None:
        """第三步：提交验证码 → 完成登录并写入配置条目。"""
        flow_id = str(msg.get("flow_id") or "")
        state = _PENDING.get(flow_id)
        if state is None:
            connection.send_error(msg["id"], "flow_expired", "会话已过期，请重新登录")
            return
        state["ts"] = time.time()
        code_str = str(msg.get("code") or "").strip()
        if not code_str:
            connection.send_error(msg["id"], "invalid_code", "验证码不能为空")
            return
        try:
            result = await huawei_account.async_complete_challenge(
                state["provider"], code_str
            )
        except Exception as err:  # noqa: BLE001
            connection.send_error(msg["id"], "invalid_challenge", str(err)[:200])
            return
        session = getattr(result, "session", None)
        if session is None:
            connection.send_error(msg["id"], "auth_failed", "登录未完成")
            return
        state["session"] = session
        ok = await _finish(hass, flow_id)
        if ok:
            connection.send_result(msg["id"], {"done": True})
        else:
            connection.send_error(msg["id"], "save_failed", "保存账号失败")

    async def _finish(hass: HomeAssistant, flow_id: str) -> bool:
        """把登录结果写入配置条目（与配置流一致）。"""
        state = _PENDING.get(flow_id)
        if state is None:
            return False
        entry = _entry(hass, state["entry_id"])
        if entry is None:
            return False
        try:
            # 复用配置流的收尾逻辑，避免两处行为不一致
            from .accounts_flow import build_account_entry  # noqa: PLC0415

            new_account = await build_account_entry(
                hass, entry, state["account"], state["password"], state["session"]
            )
        except Exception:  # noqa: BLE001
            return False
        if not new_account:
            return False
        accounts = list(entry.data.get("accounts") or [])
        accounts.append(new_account)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "accounts": accounts}
        )
        # 触发条目重载，让新账号立即生效
        await hass.config_entries.async_reload(entry.entry_id)
        _PENDING.pop(flow_id, None)
        return True

    # websocket_command 接受的是 **schema 字典**（必须含 "type"），不是命令名
    for cmd_name, handler, schema in (
        ("huawei_home_storage/login_start", ws_login_start, {
            vol.Required("type"): cmd_start,
            vol.Optional("entry_id"): str,
            vol.Required("account"): str,
            vol.Required("password"): str,
        }),
        ("huawei_home_storage/login_channel", ws_login_channel, {
            vol.Required("type"): cmd_channel,
            vol.Required("flow_id"): str,
            vol.Optional("channel"): vol.Any(str, int, None),
        }),
        ("huawei_home_storage/login_code", ws_login_code, {
            vol.Required("type"): cmd_code,
            vol.Required("flow_id"): str,
            vol.Required("code"): str,
        }),
    ):
        websocket_api.async_register_command(
            hass,
            _wsdec.async_response(_wsdec.websocket_command(schema)(handler)),
        )
