"""华为账号云侧客户端。

职责（全部为纯 Python 复现，无需 PC 客户端）：
  1. OAuth 2.0 设备码流程（首次授权）与 refresh_token 续期；
  2. smarthome 云：message-center 登录、枚举设备（prodId == KX01）；
  3. MQTT startService + ECDH/AES 解密，取回设备本地会话凭据。

解密细节（已实测）：
  AES-256 key = 本端一次性 EC 私钥与证书链**第一张叶子证书**公钥做 ECDH 的共享密钥 X（原始 32B，无 HKDF）；
  ``encrypted`` hex 布局 = nonce(12) ‖ ciphertext ‖ tag(16)；
  明文 = ciphertext XOR AES-256-CTR 密钥流（J0 = nonce‖00000001，从 J0+1 起，无 AAD/tag 校验）。
"""
from __future__ import annotations

import asyncio
import base64
import functools
import json
import logging
import os
import ssl
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:  # paho-mqtt 随 HA Core 一起提供
    import paho.mqtt.client as mqtt

    try:
        from paho.mqtt.enums import CallbackAPIVersion

        _PAHO_KWARGS: dict[str, Any] = {
            "callback_api_version": CallbackAPIVersion.VERSION1
        }
    except Exception:  # paho-mqtt 1.x
        _PAHO_KWARGS = {}
    _PAHO_AVAILABLE = True
except Exception:  # pragma: no cover
    mqtt = None  # type: ignore[assignment]
    _PAHO_KWARGS = {}
    _PAHO_AVAILABLE = False

from ..const import (
    API_CLOUD_DEVICES,
    API_CLOUD_LOGIN,
    CLOUD_APP,
    CLOUD_CURVE,
    CLOUD_PROD_ID,
    MQTT_CMD_TOPIC,
    MQTT_DEFAULT_TOPIC,
    MQTT_HOST,
    MQTT_PORT,
    MQTT_TIMEOUT,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_DEVICE_CODE_URL,
    OAUTH_SCOPE,
    OAUTH_TOKEN_URL,
    OAUTH_UA,
    REQUEST_TIMEOUT,
    SMARTHOME_BASE,
)

_LOGGER = logging.getLogger(__name__)

Executor = Callable[[Callable[..., Any], Any], Awaitable[Any]]

# 华为在「用户尚未授权」时返回的是 HTTP 400 +
# {"error":1101,"sub_error":20411,"error_description":"user code not scan"}，
# 既不是标准 OAuth 的 authorization_pending，也不是真失败 —— 必须当作「继续等待」。
PENDING_ERRORS = {"authorization_pending", "slow_down", "authorization_waiting"}
PENDING_SUB_ERRORS = {20411}


def _is_authorization_pending(payload: Mapping[str, Any]) -> bool:
    """判断轮询响应是否只是「用户还没完成授权」。"""
    if str(payload.get("error") or "").lower() in PENDING_ERRORS:
        return True
    if payload.get("sub_error") in PENDING_SUB_ERRORS:
        return True
    desc = str(payload.get("error_description") or "").lower()
    return "not scan" in desc or "pending" in desc


class HuaweiCloudError(Exception):
    """云侧通用错误。"""


class HuaweiCloudAuthError(HuaweiCloudError):
    """refresh_token 失效，需要重新走设备码授权。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class DeviceCredentials:
    """设备本地会话凭据（由云侧 startService 下发）。"""

    __slots__ = (
        "token",
        "session",
        "data_token",
        "data_session",
        "https_url",
        "data_https_url",
        "cloud_dev_id",
        "user",
        "raw",
        "obtained_at",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        self.token: str = data.get("token") or ""
        self.session: str = data.get("session") or ""
        self.data_token: str = data.get("dataToken") or ""
        self.data_session: str = data.get("dataSession") or ""
        self.https_url: str = (data.get("httpsUrl") or "").rstrip("/")
        self.data_https_url: str = (data.get("dataHttpsUrl") or "").rstrip("/")
        self.cloud_dev_id: str = data.get("devId") or ""
        self.user: str = data.get("user") or ""
        self.raw: dict[str, Any] = data
        self.obtained_at: float = time.time()

    @property
    def is_complete(self) -> bool:
        return bool(self.token and self.session)

    def to_dict(self) -> dict[str, Any]:
        """仅保留非敏感字段，供持久化/诊断用。"""
        return {
            "cloud_dev_id": self.cloud_dev_id,
            "user": self.user,
            "https_url": self.https_url,
            "data_https_url": self.data_https_url,
            "obtained_at": self.obtained_at,
        }


# ---------------------------------------------------------------------------
# 纯函数：JWT / 加解密
# ---------------------------------------------------------------------------
def decode_uid(id_token: str) -> str | None:
    """从 id_token(JWT) 的 payload 中取 uid。"""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("uid")
    except Exception:  # noqa: BLE001
        _LOGGER.debug("无法解析 id_token 中的 uid")
        return None


def _aes_ctr_keystream_xor(key: bytes, blob: bytes) -> bytes:
    """nonce(12) ‖ ct ‖ tag(16)，明文 = ct XOR CTR 密钥流。"""
    nonce, rest = blob[:12], blob[12:]
    body_ct = rest[:-16]

    def _block(block_in: bytes) -> bytes:
        enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        return enc.update(block_in) + enc.finalize()

    counter = int.from_bytes(nonce + b"\x00\x00\x00\x01", "big")
    keystream = b""
    while len(keystream) < len(body_ct):
        counter += 1
        keystream += _block((counter & ((1 << 128) - 1)).to_bytes(16, "big"))
    return bytes(a ^ b for a, b in zip(body_ct, keystream))


def decrypt_credentials(
    private_key: ec.EllipticCurvePrivateKey, chain_pem: str, encrypted_hex: str
) -> dict[str, Any]:
    """用本端私钥 + 叶子证书公钥 ECDH，解出 startService 下发的凭据 JSON。"""
    leaf = x509.load_pem_x509_certificate(chain_pem.encode())
    key = private_key.exchange(ec.ECDH(), leaf.public_key())
    plain = _aes_ctr_keystream_xor(key, bytes.fromhex(encrypted_hex))
    text = plain.decode("utf-8", "replace")
    start = text.find("{")
    if start < 0:
        raise HuaweiCloudError(f"解密结果不是 JSON: {text[:120]!r}")
    try:
        creds, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as err:
        # 明文里确实有 '{' 但后续不是合法 JSON：解出的密钥不对（ECDH/AES 状态
        # 不匹配）或设备返回被截断。属**瞬时 / 设备侧**故障，不是凭据失效。
        #
        # 这里必须显式包装：JSONDecodeError 不是 HuaweiCloudError，
        # 会逃出 device.py 的 `except HuaweiCloudError` 分类，冒泡到
        # DataUpdateCoordinator 变成 "Unexpected error fetching ..."，
        # 绕过各协调器自己的降级分支（实测：相册协调器整条硬失败）。
        #
        # 刻意不记录明文内容（可能含下发的凭据），只记长度。
        raise HuaweiCloudError(
            f"解密结果 JSON 解析失败（明文 {len(text)} 字节，未记录内容）: {err}"
        ) from err
    return creds


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


# ---------------------------------------------------------------------------
# 阻塞段：MQTT startService + ECDH 解密
# ---------------------------------------------------------------------------
def start_service_blocking(
    *,
    access_token: str,
    uid: str,
    mqtt_client_id: str | None,
    mqtt_topic: str,
    cloud_dev_id: str,
    dev_mac: str,
    product: str,
    timeout: int = MQTT_TIMEOUT,
) -> dict[str, Any]:
    """发布 startService 指令，等待设备推送加密凭据并解密。"""
    if not _PAHO_AVAILABLE:
        raise HuaweiCloudError("缺少 paho-mqtt 依赖")

    private_key = ec.generate_private_key(ec.SECP256R1())
    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    payload = {
        "body": {
            "app": CLOUD_APP,
            "curve": CLOUD_CURVE,
            "device": dev_mac,
            "filter": "",
            "keyid": "memospace_" + os.urandom(32).hex(),
            "matchId": uuid.uuid4().hex.upper() + str(int(time.time())),
            "product": product,
            "pubKey": pub_pem,
            "reserved": "",
        },
        "header": {
            "accessToken": access_token,
            "from": f"/users/{uid}",
            "method": "POST",
            "mode": "ACK",
            "requestId": str(uuid.uuid4()).upper(),
            "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
            "to": f"/devices/{cloud_dev_id}/services/startService",
        },
    }

    result: dict[str, Any] = {}
    done = threading.Event()
    # 诊断计数（不改变任何行为）：本轮收到的候选消息数、以及各条的 keyid 是否
    # 与我们本次发出的匹配。用于事后判定"拿错消息/私钥配对错乱"这类偶发失败
    # 的根因——**只记条数与布尔判定，不记录任何消息内容或凭据**。
    diag = {"candidates": 0, "keyid_match": 0, "payloads_parsed": 0}
    my_keyid = (payload.get("body") or {}).get("keyid") or ""

    def _on_connect(client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            client.subscribe(mqtt_topic, qos=1)

    def _on_message(client, userdata, msg):  # noqa: ANN001
        try:
            body = json.loads(msg.payload.decode("utf-8", "replace")).get("body", {})
        except Exception:  # noqa: BLE001
            return
        diag["payloads_parsed"] += 1
        if isinstance(body, dict) and body.get("devId") == cloud_dev_id and "services" in body:
            diag["candidates"] += 1
            if my_keyid and body.get("keyid") == my_keyid:
                diag["keyid_match"] += 1
            result["data"] = body
            done.set()

    client = mqtt.Client(client_id=mqtt_client_id, **_PAHO_KWARGS)
    client.username_pw_set(uid, access_token)
    client.tls_set_context(_ssl_context())
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    try:
        for _ in range(50):
            if client.is_connected():
                break
            time.sleep(0.2)
        client.publish(MQTT_CMD_TOPIC, json.dumps(payload), qos=1)
        if not done.wait(timeout):
            raise HuaweiCloudError(
                f"MQTT 未收到设备响应（超时）｜诊断: {diag}"
            )
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    body = result["data"]
    services = body.get("services") or []
    svc = next((s for s in services if s.get("sid") == "startService"), None)
    info = (svc or {}).get("data") or {}
    chain, encrypted = info.get("chain"), info.get("encrypted")
    if not chain or not encrypted:
        raise HuaweiCloudError(
            f"设备返回缺少 chain/encrypted｜诊断: {diag}"
        )
    try:
        return decrypt_credentials(private_key, chain, encrypted)
    except HuaweiCloudError as err:
        # 把本轮 MQTT 诊断带进错误：candidates>1 或 keyid_match=0 → 说明
        # "多响应/私钥配对错乱"；否则更可能是设备侧下发的密文异常。
        raise HuaweiCloudError(f"{err}｜诊断: {diag}") from err


# ---------------------------------------------------------------------------
# 异步客户端
# ---------------------------------------------------------------------------
class HuaweiCloudClient:
    """华为账号云侧客户端（设备码 → 凭据下发）。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str | None = None,
        access_token: str | None = None,
        executor: Executor | None = None,
        token_provider: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._session = session
        self.refresh_token = refresh_token
        self.access_token = access_token
        self._executor = executor
        self._token_provider = token_provider
        self._lock = asyncio.Lock()

    # -- 会话生命周期 ------------------------------------------------------
    def set_executor(self, executor: Executor) -> None:
        self._executor = executor

    async def _run_blocking(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        # hass.async_add_executor_job 只接受位置参数，含 kwargs 时用 partial 包一层
        if kwargs:
            func = functools.partial(func, *args, **kwargs)
            args = ()
        if self._executor is not None:
            return await self._executor(func, *args)
        return await asyncio.get_running_loop().run_in_executor(None, func, *args)

    # -- 静态：设备码流程（config flow 用） --------------------------------
    @staticmethod
    async def async_request_device_code(session: aiohttp.ClientSession) -> dict[str, Any]:
        """申请设备码，返回 device_code / user_code / verification_url 等。"""
        data = {"client_id": OAUTH_CLIENT_ID, "scope": OAUTH_SCOPE}
        try:
            async with session.post(
                OAUTH_DEVICE_CODE_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": OAUTH_UA,
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HuaweiCloudError(f"申请设备码失败: {err}") from err
        if "device_code" not in payload:
            raise HuaweiCloudError(f"申请设备码被拒: {payload}")
        return payload

    @staticmethod
    async def async_poll_device_code(
        session: aiohttp.ClientSession, device_code: str
    ) -> dict[str, Any] | None:
        """轮询换取 token；仍在等待用户授权时返回 None。"""
        data = {
            "grant_type": "device_code",
            "code": device_code,
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
        }
        try:
            async with session.post(
                OAUTH_TOKEN_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": OAUTH_UA,
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                payload = await resp.json(content_type=None)
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HuaweiCloudError(f"轮询设备码失败: {err}") from err

        if status == 200 and payload.get("access_token"):
            return payload
        if _is_authorization_pending(payload):
            return None
        raise HuaweiCloudError(
            "设备码轮询被拒: " + str(payload.get("error_description") or payload)[:160]
        )

    # -- access_token 续期 -------------------------------------------------
    async def async_ensure_access_token(self) -> str:
        """返回可用的 access_token。

        两种来源：
          - 账号密码模式：由 ``token_provider`` 提供（本集成自带的账号登录）
          - 设备码模式：用 ``refresh_token`` 续期
        """
        if self._token_provider is not None:
            self.access_token = await self._token_provider()
            return self.access_token

        async with self._lock:
            if self.access_token:
                return self.access_token
            if not self.refresh_token:
                raise HuaweiCloudAuthError("缺少 refresh_token")
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
            }
            try:
                async with self._session.post(
                    OAUTH_TOKEN_URL,
                    data=data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": OAUTH_UA,
                    },
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    payload = await resp.json(content_type=None)
                    status = resp.status
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise HuaweiCloudError(f"刷新 access_token 失败: {err}") from err

            if status != 200 or not payload.get("access_token"):
                raise HuaweiCloudAuthError(
                    "refresh_token 已失效，请重新授权: "
                    + str(payload.get("error_description") or payload)[:160]
                )
            self.access_token = payload["access_token"]
            # 华为可能轮换 refresh_token；未返回则沿用旧值
            if payload.get("refresh_token"):
                self.refresh_token = payload["refresh_token"]
            return self.access_token

    def invalidate_access_token(self) -> None:
        self.access_token = None

    # -- smarthome 云 ------------------------------------------------------
    def _cloud_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Content-Type": "application/json;Charset=UTF-8",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": OAUTH_UA,
        }

    async def async_cloud_login(self) -> dict[str, Any]:
        """message-center 登录，拿到 MQTT topic / clientId。"""
        access_token = await self.async_ensure_access_token()
        payload = {
            "deviceInfo": {
                "deviceAliasName": "ha_home_storage",
                "deviceID": CLOUD_APP,
                "deviceType": CLOUD_APP,
                "terminalType": "device",
            },
            "language": "ZH",
        }
        try:
            async with self._session.post(
                SMARTHOME_BASE + API_CLOUD_LOGIN,
                json=payload,
                headers=self._cloud_headers(access_token),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HuaweiCloudError(f"message-center 登录失败: {err}") from err
        if "mqttTopic" not in data and "mqttClientId" not in data:
            raise HuaweiCloudError(f"message-center 登录返回异常: {str(data)[:200]}")
        return data

    async def async_list_devices(self) -> list[dict[str, Any]]:
        """列出云侧设备。"""
        access_token = await self.async_ensure_access_token()
        try:
            async with self._session.get(
                SMARTHOME_BASE + API_CLOUD_DEVICES,
                headers=self._cloud_headers(access_token),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HuaweiCloudError(f"获取云设备列表失败: {err}") from err
        if isinstance(data, dict) and data.get("errorCode"):
            raise HuaweiCloudError(f"获取云设备列表失败: {str(data)[:200]}")
        return data if isinstance(data, list) else []

    async def async_get_storage_device(self) -> dict[str, Any]:
        """定位家庭存储设备（prodId == KX01）。"""
        devices = await self.async_list_devices()
        storage = [
            d for d in devices if (d.get("devInfo") or {}).get("prodId") == CLOUD_PROD_ID
        ]
        if not storage:
            raise HuaweiCloudError(
                f"账号下未找到家庭存储设备（prodId={CLOUD_PROD_ID}）"
            )
        return storage[0]

    # -- 主流程：取设备凭据 ------------------------------------------------
    async def async_fetch_device_credentials(
        self,
        cloud_dev_id: str,
        uid: str,
        dev_mac: str,
        product: str,
    ) -> DeviceCredentials:
        """完整链路：登录 → MQTT startService → ECDH 解密 → 设备凭据。"""
        login = await self.async_cloud_login()
        topic = login.get("mqttTopic") or MQTT_DEFAULT_TOPIC
        client_id = login.get("mqttClientId")
        access_token = self.access_token or ""

        data = await self._run_blocking(
            start_service_blocking,
            access_token=access_token,
            uid=uid,
            mqtt_client_id=client_id,
            mqtt_topic=topic,
            cloud_dev_id=cloud_dev_id,
            dev_mac=dev_mac,
            product=product,
        )
        creds = DeviceCredentials(data)
        if not creds.is_complete:
            raise HuaweiCloudError(f"下发的凭据不完整: {sorted(data.keys())}")
        _LOGGER.debug(
            "已获取设备凭据: devId=%s user=%s", creds.cloud_dev_id, creds.user
        )
        return creds
