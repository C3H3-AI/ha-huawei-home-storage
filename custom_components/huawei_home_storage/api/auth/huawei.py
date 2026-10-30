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
import base64
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import time
import uuid
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .transport import HttpResponse
from .._smarthome_const import (
    ACCOUNT_BASE_URL,
    HMS_LITE_TOKEN_PATH,
    OAUTH_BASE_URL,
    SMART_HOME_ACCOUNT_CLIENT_VERSION,
    SMART_HOME_ACCOUNT_USER_AGENT,
    SMART_HOME_ACCOUNT_VERSION,
    SMART_HOME_APP_ID,
    SMART_HOME_BASE_URL,
    SMART_HOME_IOS_APP_ID,
    SMART_HOME_OAUTH_CLIENT_ID,
    SMART_HOME_USER_AGENT,
)
from .smarthome_errors import (
    AuthenticationError,
    InvalidCredentialsError,
    TransientAuthenticationError,
)
from ..domain.models import AuthSession
from .interface import (
    ChallengeChannel,
    LoginChallenge,
    LoginStart,
    channel_kind,
)

_LOGGER = logging.getLogger(__name__)

SCOPE_FOR_CODE = (
    "openid https://www.huawei.com/auth/account/accountlist "
    "https://www.huawei.com/auth/account/birthday "
    "https://www.huawei.com/auth/account/base.profile"
)
SCOPE_FOR_SESSION = (
    "openid https://www.huawei.com/auth/account/mobile.number email "
    "https://www.huawei.com/auth/account/accountlist "
    "https://www.huawei.com/auth/account/base.profile"
)

# The account web tier (CAS) is the only component in the Huawei stack that can
# dispatch a verification code: the app-side loginV3 endpoint has no send action,
# and its authCode is rejected because it was bound to the CAS web session.
CAS_BASE_URL = "https://id1.cloud.huawei.com"
CAS_LOGIN_PAGE = f"{CAS_BASE_URL}/CAS/portal/login.html"
CAS_AJAX_PATH = "/CAS/IDM_W/ajaxHandler"
CAS_CVERSION_BASE = "UP_CAS_6.26.2.100"
CAS_CVERSION_FALLBACK = f"{CAS_CVERSION_BASE}_blue"
CAS_BASE_SWITCH_ACTION = "common/getBaseSwitchInfo"
CAS_SERVICE = f"{CAS_BASE_URL}/AMW/portal/userCenter/index.html"
CAS_REQUEST_CLIENT_TYPE = "7"
CAS_LOGIN_CHANNEL = "7000000"
CAS_LANGUAGE = "zh-cn"
CAS_SITE_ID = "1"
CAS_PAGE_INFO_ACTION = "login/getPageInfo"
CAS_PAGE_NAME = "login"
# The web tier wants the account identifier type here (2 = phone number). The
# challenge's channel code uses 2 or 6 for the same SMS channel, and passing the
# channel code through makes the tier answer 70001201 UserAccount not match UserID!
CAS_ACCOUNT_TYPE_PHONE = "2"
CAS_SMS_OPER_TYPE = "8"
CAS_SMS_REQUEST_TYPE = "6"

# Several Set-Cookie headers are folded into one value with this separator,
# because HttpResponse.headers is a flat mapping.
SET_COOKIE_SEPARATOR = "\n"


@dataclass(frozen=True, slots=True)
class _PendingLogin:
    account: str
    encrypted_password: str
    challenge_name: str
    challenge_type: str
    channels: tuple[ChallengeChannel, ...] = ()


class HuaweiSmartHomeAuthProvider:
    """Interactive provider for the verified SmartHome login sequence."""

    def __init__(
        self,
        *,
        device_id: str,
        device_name: str,
        pushtmid: str | None = None,
        identity_fingerprint: str | None = None,
        timeout: float = 20.0,
        transport: Any | None = None,
    ) -> None:
        if not device_id:
            raise ValueError("device_id is required")
        self.device_id = device_id
        self.device_name = device_name or "huawei-smarthome"
        self.pushtmid = pushtmid
        self.identity_fingerprint = identity_fingerprint
        self.timeout = timeout
        self._transport = transport or _urllib_transport
        self._cookies: dict[str, str] = {}
        self._cas_cookies: dict[str, str] = {}
        self._cas_tokens: dict[str, str] = {}
        self._cas_version = CAS_CVERSION_FALLBACK
        self._cas_session_ready = False
        self._pending: _PendingLogin | None = None

    async def async_begin_login(self, account: str, password: str) -> LoginStart:
        """Start login and return either a session or a device challenge."""

        account = account.strip()
        if not account or not password:
            raise InvalidCredentialsError("account and password are required")
        return await asyncio.to_thread(self._begin_login, account, password)

    async def async_select_challenge_channel(
        self,
        channel: ChallengeChannel,
    ) -> LoginChallenge:
        """Dispatch the code for the chosen channel and describe the next step."""

        pending = self._pending
        if pending is None:
            raise InvalidCredentialsError("no pending Huawei SmartHome challenge")
        return await asyncio.to_thread(self._select_challenge_channel, channel)

    async def async_complete_challenge(self, code: str) -> AuthSession:
        """Submit a pending challenge code."""

        if not code.strip():
            raise InvalidCredentialsError("challenge code is required")
        session = await asyncio.to_thread(self._complete_challenge, code.strip())
        self._pending = None
        return session

    async def async_refresh_oauth(self, session: AuthSession) -> AuthSession:
        """Refresh the OAuth session access token using the service token."""

        return await asyncio.to_thread(self._refresh_oauth, session)

    async def async_refresh_hms_lite(self, session: AuthSession) -> AuthSession:
        """Reissue HMS-lite credentials through a silent OAuth code."""

        return await asyncio.to_thread(self._refresh_hms_lite, session)

    def _refresh_oauth(self, session: AuthSession) -> AuthSession:
        if not session.service_token:
            raise AuthenticationError("Huawei SmartHome service token is unavailable")
        response = self._oauth_request(
            need_code=False,
            scope=SCOPE_FOR_SESSION,
            service_token=session.service_token,
        )
        if response.status == 429 or response.status >= 500:
            raise TransientAuthenticationError(
                "Huawei SmartHome OAuth session refresh is temporarily unavailable"
            )
        payload = _json_object(response.body)
        access_token = _find_string(payload, "access_token")
        expires_at = _expires_at(payload.get("expire_in"))
        if response.status >= 400 or not access_token or expires_at is None:
            raise AuthenticationError("Huawei SmartHome OAuth session refresh failed")
        return replace(
            session,
            oauth_access_token=access_token,
            oauth_expires_at=expires_at,
            generation=session.generation + 1,
        )

    def _refresh_hms_lite(self, session: AuthSession) -> AuthSession:
        if not session.service_token:
            raise AuthenticationError("Huawei SmartHome service token is unavailable")
        code = self._obtain_silent_code(session.service_token)
        access_token, refresh_token, expires_at = self._exchange_hms_lite_code(
            session.user_id,
            code,
        )
        return replace(
            session,
            hms_access_token=access_token,
            hms_refresh_token=refresh_token or session.hms_refresh_token,
            hms_expires_at=expires_at,
        )

    def _begin_login(self, account: str, password: str) -> LoginStart:
        self._cookies.clear()
        self._cas_cookies.clear()
        self._cas_tokens.clear()
        self._cas_version = CAS_CVERSION_FALLBACK
        self._cas_session_ready = False
        self._pending = None
        public_key = self._fetch_rsa_public_key()
        encrypted_password = _encrypt_password(password, public_key)
        response = self._login_request(
            account,
            encrypted_password,
            challenge=None,
            retry=False,
        )
        fields = _parse_form(response.body)
        result_code = _first(fields, "resultCode")
        if response.status < 400 and result_code == "0":
            return LoginStart(session=self._finish_login(account, fields))
        channels = _extract_channels(fields)
        if not channels:
            _LOGGER.warning(
                "Huawei SmartHome login rejected without a challenge: "
                "status=%s resultCode=%s",
                response.status,
                result_code,
            )
            raise InvalidCredentialsError("Huawei SmartHome account login rejected")
        selected = _default_channel(channels)

        self._pending = _PendingLogin(
            account=account,
            encrypted_password=encrypted_password,
            challenge_name=selected.name,
            challenge_type=selected.account_type,
            channels=channels,
        )
        return LoginStart(
            challenge=LoginChallenge(
                prompt=_channel_prompt(selected),
                challenge_name=selected.name,
                challenge_type=selected.account_type,
                channels=channels,
            )
        )

    def _select_challenge_channel(self, channel: ChallengeChannel) -> LoginChallenge:
        """Dispatch the code for one channel and describe what the user must do."""

        pending = self._pending
        if pending is None:
            raise InvalidCredentialsError("no pending Huawei SmartHome challenge")
        matched = [item for item in pending.channels if item.key == channel.key]
        selected = matched[0] if matched else channel
        if selected.is_sms and not selected.sent:
            self._dispatch_web_sms_code(selected, pending.account)
            selected = replace(selected, sent=True)
        self._pending = replace(
            pending,
            challenge_name=selected.name,
            challenge_type=selected.account_type,
        )
        return LoginChallenge(
            prompt=_channel_prompt(selected),
            challenge_name=selected.name,
            challenge_type=selected.account_type,
            channels=pending.channels,
        )

    def _dispatch_web_sms_code(
        self,
        channel: ChallengeChannel,
        account: str,
    ) -> None:
        """Ask the Huawei account web tier to send the SMS code.

        The app-side loginV3 endpoint exposes no send action, so the only way to
        make Huawei send anything is the account web tier (CAS) ajax gateway.
        """

        self._cas_open_session()
        # The page token stays valid for the whole session. Re-fetching it between
        # attempts drops the loginFlowContext the web tier resolves the account
        # from, after which every later attempt answers "Can't get user
        # information from loginFlowContext session".
        self._refresh_cas_tokens()
        self._cas_ajax(
            "chkRisk",
            {
                "userAccount": account,
                "service": CAS_SERVICE,
                "operType": "11",
                "registerCountry": "cn",
                "lowLogin": "",
                "ext_clientInfo": "",
            },
        )

        candidates = _sms_phone_candidates(channel.name, account)
        last_error = "unknown error"
        for phone in candidates:
            response = self._cas_ajax(
                "getSMSCodeV3",
                {
                    "userAccount": account,
                    "accountType": CAS_ACCOUNT_TYPE_PHONE,
                    "mobilePhone": phone,
                    "operType": CAS_SMS_OPER_TYPE,
                    "smsReqType": CAS_SMS_REQUEST_TYPE,
                    "siteID": CAS_SITE_ID,
                },
            )
            payload = _json_object_or_none(response.body)
            if not _cas_call_failed(response.status, payload):
                return
            last_error = _cas_error_text(payload, response.status)
            if not _cas_failure_is_explicit(payload):
                raise AuthenticationError(last_error)
        raise AuthenticationError(last_error)

    def _cas_open_session(self) -> None:
        """Prime the CAS web session so the dispatch call carries a JSESSIONID."""

        if self._cas_session_ready:
            return
        self._request(
            "GET",
            CAS_LOGIN_PAGE,
            {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": SMART_HOME_ACCOUNT_USER_AGENT,
            },
            None,
            cookies=self._cas_cookies,
        )
        self._cas_session_ready = True
        self._cas_sync_version()

    def _cas_sync_version(self) -> None:
        """Adopt the web tier's current asset version.

        Huawei bumps this string with every web release and rejects ajax calls
        that carry a stale one, so it is read at runtime and only falls back to
        the bundled constant when the probe fails.
        """

        response = self._cas_ajax(
            CAS_BASE_SWITCH_ACTION,
            {},
            with_tokens=False,
            version=CAS_CVERSION_BASE,
        )
        payload = _json_object_or_none(response.body)
        version = payload.get("cookieVersion") if payload else None
        if isinstance(version, str) and version:
            self._cas_version = version

    def _refresh_cas_tokens(self) -> None:
        """Fetch the page token pair the ajax gateway demands.

        Without pageToken/pageTokenKey every action answers 10000004
        "Illegal Operation", which is what made the first dispatch attempt fail.
        """

        response = self._cas_ajax(
            CAS_PAGE_INFO_ACTION,
            {"pageName": CAS_PAGE_NAME},
            with_tokens=False,
        )
        payload = _json_object_or_none(response.body)
        token = payload.get("pageToken") if payload else None
        token_key = payload.get("pageTokenKey") if payload else None
        if not isinstance(token, str) or not isinstance(token_key, str):
            raise AuthenticationError(
                "Huawei SmartHome account web page token is unavailable"
            )
        self._cas_tokens = {"pageToken": token, "pageTokenKey": token_key}

    def _cas_ajax(
        self,
        action: str,
        values: Mapping[str, str],
        *,
        with_tokens: bool = True,
        version: str | None = None,
    ) -> HttpResponse:
        """POST one action to the account web tier ajax gateway."""

        query = urlencode(
            {
                "reflushCode": f"{time.time()}",
                "cVersion": version or self._cas_version,
            }
        )
        params: list[tuple[str, str]] = [
            ("reqClientType", CAS_REQUEST_CLIENT_TYPE),
            ("loginChannel", CAS_LOGIN_CHANNEL),
            ("lang", CAS_LANGUAGE),
            ("languageCode", CAS_LANGUAGE),
        ]
        if with_tokens:
            params.extend(self._cas_tokens.items())
        params.extend(values.items())
        return self._request(
            "POST",
            f"{CAS_BASE_URL}{CAS_AJAX_PATH}/{action}?{query}",
            {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": CAS_BASE_URL,
                "Referer": CAS_LOGIN_PAGE,
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": SMART_HOME_ACCOUNT_USER_AGENT,
            },
            urlencode(params).encode("utf-8"),
            cookies=self._cas_cookies,
        )

    def _complete_challenge(self, code: str) -> AuthSession:
        pending = self._pending
        if pending is None:
            raise InvalidCredentialsError("no pending Huawei SmartHome challenge")
        response = self._login_request(
            pending.account,
            pending.encrypted_password,
            challenge=(code, pending.challenge_name, pending.challenge_type),
            retry=True,
        )
        fields = _parse_form(response.body)
        if response.status >= 400 or _first(fields, "resultCode") != "0":
            _LOGGER.warning(
                "Huawei SmartHome challenge rejected: status=%s resultCode=%s",
                response.status,
                _first(fields, "resultCode"),
            )
            raise InvalidCredentialsError("Huawei SmartHome challenge rejected")
        return self._finish_login(pending.account, fields)

    def _finish_login(
        self,
        account: str,
        fields: Mapping[str, list[str]],
    ) -> AuthSession:
        service_token = _first(fields, "TGC")
        user_id = _first(fields, "userID")
        if not service_token or not user_id:
            raise AuthenticationError("login response did not contain a session")

        st_response = self._post_account_form(
            "/AccountServer/IUserInfoMng/stAuth",
            {
                "ver": SMART_HOME_ACCOUNT_VERSION,
                "st": service_token,
                "app": SMART_HOME_APP_ID,
                "agr": "1",
                "chg": "0",
                "clT": "54",
                "cn": "54000000",
                "dS": "0",
                "dvID": self.device_id,
                "dvT": "6",
                "gAc": "0",
                "tmT": "iPhone",
            },
        )
        st_fields = _parse_form(st_response.body)
        if st_response.status >= 400 or _first(st_fields, "resultCode") not in (
            None,
            "",
            "0",
        ):
            raise AuthenticationError("stAuth session validation failed")

        self._post_user_info(user_id)
        code = self._obtain_silent_code(service_token)

        session_response = self._oauth_request(
            need_code=False,
            scope=SCOPE_FOR_SESSION,
            service_token=service_token,
        )
        session_payload = _json_object(session_response.body)
        oauth_access_token = _find_string(session_payload, "access_token")
        if session_response.status >= 400 or not oauth_access_token:
            raise AuthenticationError("OAuth session exchange failed")

        hms_access_token, hms_refresh_token, hms_expires_at = (
            self._exchange_hms_lite_code(user_id, code)
        )
        return AuthSession(
            account=account,
            user_id=user_id,
            service_token=service_token,
            hms_access_token=hms_access_token,
            hms_refresh_token=(
                hms_refresh_token if isinstance(hms_refresh_token, str) else None
            ),
            hms_expires_at=hms_expires_at,
            oauth_access_token=oauth_access_token,
            oauth_expires_at=_expires_at(session_payload.get("expire_in")),
            device_id=self.device_id,
            device_name=self.device_name,
            pushtmid=self.pushtmid,
            identity_fingerprint=self.identity_fingerprint,
            app_id=SMART_HOME_IOS_APP_ID,
            base_url=SMART_HOME_BASE_URL,
            home_zone=_first(st_fields, "homeZone"),
            oauth_domain=_first(st_fields, "oauthDomain"),
            site_domain=_first(st_fields, "siteDomain"),
        )

    def _obtain_silent_code(self, service_token: str) -> str:
        response = self._oauth_request(
            need_code=True,
            scope=SCOPE_FOR_CODE,
            service_token=service_token,
        )
        if response.status == 429 or response.status >= 500:
            raise TransientAuthenticationError(
                "Huawei SmartHome OAuth code request is temporarily unavailable"
            )
        payload = _json_object(response.body)
        code = _find_string(payload, "code")
        if response.status >= 400 or not code:
            raise AuthenticationError("OAuth code exchange failed")
        return code

    def _exchange_hms_lite_code(
        self,
        user_id: str,
        code: str,
    ) -> tuple[str, str | None, datetime | None]:
        response = self._request(
            "POST",
            f"{SMART_HOME_BASE_URL}{HMS_LITE_TOKEN_PATH}",
            {
                "Accept": "*/*",
                "Accept-Language": "zh-Hans-CN;q=1",
                "Authorization": "Bearer (null)",
                "Content-Type": "application/json;charset=UTF-8",
                "X-AppId": SMART_HOME_IOS_APP_ID,
                "X-Huid": user_id,
                "X-RequestId": str(uuid.uuid4()).upper(),
                "User-Agent": SMART_HOME_USER_AGENT,
            },
            json.dumps(
                {
                    "appId": SMART_HOME_OAUTH_CLIENT_ID,
                    "code": quote(code, safe=""),
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            send_cookies=False,
        )
        if response.status == 429 or response.status >= 500:
            raise TransientAuthenticationError(
                "Huawei SmartHome HMS-lite token exchange is temporarily unavailable"
            )
        payload = _json_object(response.body)
        access_token = payload.get("access_token")
        if response.status >= 400 or not isinstance(access_token, str):
            raise AuthenticationError("HMS-lite token exchange failed")
        refresh_token = payload.get("refresh_token")
        return (
            access_token,
            refresh_token if isinstance(refresh_token, str) else None,
            _expires_at(payload.get("expires_in")),
        )

    def _fetch_rsa_public_key(self) -> str:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<GetResourceReq>"
            f"<version>{SMART_HOME_ACCOUNT_VERSION}</version>"
            "<resourceID>upLogin</resourceID>"
            "<reqClientType>54</reqClientType>"
            "<languageCode>zh-Hans-CN</languageCode>"
            "</GetResourceReq>"
        ).encode("utf-8")
        response = self._post_account(
            "/AccountServer/IUserInfoMng/getResource",
            body,
            "text/xml; charset=utf-8",
        )
        key = _public_key_from_response(response.body)
        if response.status >= 400 or not key:
            raise AuthenticationError("RSA resource lookup failed")
        return key

    def _login_request(
        self,
        account: str,
        encrypted_password: str,
        *,
        challenge: tuple[str, str, str] | None,
        retry: bool,
    ) -> HttpResponse:
        params: list[tuple[str, str]] = [
            ("ver", SMART_HOME_ACCOUNT_VERSION),
            ("acT", _account_type_code(account)),
            ("ac", account),
            ("pw", encrypted_password),
            ("dvT", "6"),
            ("dvID", self.device_id),
            ("tmT", "iPhone"),
            ("clT", "54"),
            ("cn", "54000000"),
            ("os", "iOS15.8.8"),
            ("app", SMART_HOME_APP_ID),
            ("dvN", self.device_name),
            ("uuid", self.device_id),
        ]
        if challenge:
            code, name, account_type = challenge
            if code is not None:
                params.append(("vCode", code))
            params.extend([("vAcT", account_type), ("vAc", name)])
        params.extend(
            [
                ("lang", "zh-Hans-CN"),
                ("dS", "0"),
                ("mA", "1" if retry else "0"),
                ("deviceInfo", json.dumps(self._device_info(), separators=(",", ":"))),
            ]
        )
        return self._post_account(
            "/AccountServer/IDM/loginV3",
            urlencode(params).encode("utf-8"),
            "application/x-www-form-urlencoded; charset=UTF-8",
        )

    def _post_user_info(self, user_id: str) -> None:
        root = ElementTree.Element("GetUserInfoReq")
        for name, value in (
            ("version", SMART_HOME_ACCOUNT_VERSION),
            ("userID", user_id),
            ("reqClientType", "54"),
            ("queryRangeFlag", "00100000"),
            ("cliDataVersion", f"{int(time.time() * 1000)}_rp"),
            ("cliDataRangeFlag", "11110010"),
        ):
            ElementTree.SubElement(root, name).text = value
        info = ElementTree.SubElement(root, "deviceInfo")
        for name, value in self._device_info().items():
            ElementTree.SubElement(info, name).text = str(value)
        response = self._post_account(
            "/AccountServer/IUserInfoMng/getUserInfo",
            ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
            "text/xml; charset=utf-8",
        )
        if response.status >= 400:
            raise AuthenticationError("user information lookup failed")

    def _oauth_request(
        self,
        *,
        need_code: bool,
        scope: str,
        service_token: str,
    ) -> HttpResponse:
        body = urlencode(
            [
                ("grant_type", "service_token"),
                ("scope", scope),
                ("service_token", service_token),
                ("device_type", "6"),
                ("package_name", SMART_HOME_APP_ID),
                ("siteId", "1"),
                ("device_id", self.device_id),
                ("need_code", "true" if need_code else "false"),
                ("uuid", self.device_id),
            ]
        ).encode("utf-8")
        query = urlencode(
            {
                "client_id": SMART_HOME_OAUTH_CLIENT_ID,
                "Version": SMART_HOME_ACCOUNT_VERSION,
                "cVersion": SMART_HOME_ACCOUNT_CLIENT_VERSION,
                "srcAppName": SMART_HOME_APP_ID,
            }
        )
        return self._request(
            "POST",
            f"{OAUTH_BASE_URL}/oauth2/v3/silent_token?{query}",
            {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "terminal-type": "iPhone",
                "User-Agent": SMART_HOME_ACCOUNT_USER_AGENT,
            },
            body,
            send_cookies=False,
        )

    def _post_account_form(
        self,
        path: str,
        values: Mapping[str, str],
    ) -> HttpResponse:
        return self._post_account(
            path,
            urlencode(values).encode("utf-8"),
            "application/x-www-form-urlencoded; charset=UTF-8",
        )

    def _post_account(self, path: str, body: bytes, content_type: str) -> HttpResponse:
        query = urlencode(
            {
                "Version": SMART_HOME_ACCOUNT_VERSION,
                "cVersion": SMART_HOME_ACCOUNT_CLIENT_VERSION,
                "ctrID": uuid.uuid4().hex,
                "srcAppName": SMART_HOME_APP_ID,
            }
        )
        url = f"{ACCOUNT_BASE_URL}{path}?{query}"
        return self._request(
            "POST",
            url,
            {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                "Authorization": str(int(time.time() * 1000)),
                "Content-Type": content_type,
                "SOAPAction": url,
                "User-Agent": SMART_HOME_ACCOUNT_USER_AGENT,
            },
            body,
        )

    def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        send_cookies: bool = True,
        cookies: dict[str, str] | None = None,
    ) -> HttpResponse:
        jar = self._cookies if cookies is None else cookies
        request_headers = dict(headers)
        if send_cookies and jar:
            request_headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in jar.items()
            )
        try:
            result = self._transport(
                method,
                url,
                request_headers,
                body,
                self.timeout,
            )
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise TransientAuthenticationError(
                "Huawei SmartHome authentication transport failed"
            ) from error
        if not isinstance(result, HttpResponse):
            raise AuthenticationError("authentication transport returned an invalid response")
        for value in _set_cookie_values(result.headers):
            pair = value.split(";", 1)[0]
            cookie_name, separator, cookie_value = pair.partition("=")
            if separator and cookie_name and cookie_value:
                jar[cookie_name.strip()] = cookie_value
        return result

    def _device_info(self) -> dict[str, str | int]:
        return {
            "terminalCategory": 9,
            "deviceType": 6,
            "deviceID": self.device_id,
            "terminalType": "iPhone",
            "deviceAliasName": self.device_name,
            "uuid": self.device_id,
        }


def _urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> HttpResponse:
    """Perform one synchronous request for the worker thread."""

    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status=response.status,
                headers=_collect_headers(response.headers),
                body=response.read(),
            )
    except HTTPError as error:
        return HttpResponse(
            status=error.code,
            headers=_collect_headers(error.headers),
            body=error.read(),
        )


def _collect_headers(headers: Any) -> dict[str, str]:
    """Flatten response headers while keeping every Set-Cookie the server sent.

    A plain dict comprehension lets a later Set-Cookie overwrite an earlier one,
    which silently drops the JSESSIONID that the account web session depends on.
    """

    collected: dict[str, str] = {}
    for name, value in headers.items():
        key = str(name)
        if key.lower() != "set-cookie":
            collected[key] = str(value)
            continue
        existing = collected.get(key)
        collected[key] = (
            f"{existing}{SET_COOKIE_SEPARATOR}{value}" if existing else str(value)
        )
    return collected


def _set_cookie_values(headers: Mapping[str, str]) -> list[str]:
    """Read every Set-Cookie value out of flattened response headers."""

    values: list[str] = []
    for name, value in headers.items():
        if name.lower() != "set-cookie":
            continue
        values.extend(part for part in value.split(SET_COOKIE_SEPARATOR) if part)
    return values


def _first(fields: Mapping[str, list[str]], key: str) -> str | None:
    values = fields.get(key)
    return values[0] if values else None


def _parse_form(body: bytes) -> dict[str, list[str]]:
    return parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)


def _extract_channels(
    fields: Mapping[str, list[str]],
) -> tuple[ChallengeChannel, ...]:
    """Read every verification channel Huawei offered for this login."""

    raw = _first(fields, "errorDesc")
    if not raw:
        return ()
    try:
        details = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    items = details.get("authCodeSentList") if isinstance(details, dict) else None
    if not isinstance(items, list):
        return ()
    channels: list[ChallengeChannel] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        account_type = item.get("accountType")
        if not isinstance(name, str) or account_type is None:
            continue
        channels.append(
            ChallengeChannel(
                name=name,
                account_type=str(account_type),
                kind=channel_kind(account_type),
                sent=str(item.get("sent")) == "1",
            )
        )
    return tuple(channels)


def _default_channel(
    channels: tuple[ChallengeChannel, ...],
) -> ChallengeChannel:
    """Pick the channel to preselect: already sent, then SMS, then the first."""

    for channel in channels:
        if channel.sent:
            return channel
    for channel in channels:
        if channel.is_sms:
            return channel
    return channels[0]


def _channel_prompt(channel: ChallengeChannel) -> str:
    """Describe the selected channel in the terms the user needs."""

    label = f"{channel.name}(类型 {channel.account_type})"
    if channel.sent:
        return f"验证码已发送至 {label},请到该渠道查看后尽快输入"
    if channel.is_sms:
        return f"验证码将发送至 {label}"
    return f"请在已登录的华为设备(通道 {label})上查看挑战码"


def _sms_phone_candidates(masked: str, account: str) -> list[str]:
    """Phone spellings to offer the web tier, most likely first.

    The challenge only exposes a masked number, and Huawei's own login page
    submits the country-prefixed form, so that is kept as the fallback. The list
    stays deliberately short: the web tier rate limits repeated dispatch
    requests inside a single login flow.
    """

    candidates = [masked]
    digits = re.sub(r"\D", "", account)
    if digits:
        candidates.append(f"0086{digits}")
    ordered: list[str] = []
    for value in candidates:
        if value and value not in ordered:
            ordered.append(value)
    return ordered


def _account_type_code(account: str) -> str:
    """Map a Huawei account identifier to the acT code the API expects."""

    text = re.sub(r"[\s-]", "", account.strip())
    if "@" in text:
        return "1"
    if re.fullmatch(r"\+?\d{5,20}", text):
        return "2"
    return "0"


def _json_object_or_none(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _cas_call_failed(status: int, payload: Mapping[str, Any] | None) -> bool:
    """Decide whether a CAS call failed or returned an unknown response."""

    if not 200 <= status < 300:
        return True
    if not isinstance(payload, Mapping):
        return True

    error_code = payload.get("errorCode")
    if error_code is not None and not _cas_success_code(error_code):
        return True

    success = payload.get("isSuccess")
    if success is not None:
        return not _cas_success_value(success)

    result_code = payload.get("resultCode")
    if result_code is not None:
        return not _cas_success_code(result_code)
    return error_code is None


def _cas_success_value(value: Any) -> bool:
    """Return whether a CAS success flag explicitly represents success."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in {"1", "true", "ok", "success"}


def _cas_success_code(value: Any) -> bool:
    """Return whether a CAS result/error code explicitly represents success."""

    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value in {0, 200}
    return str(value).strip().lower() in {"0", "200", "ok", "success"}


def _cas_failure_is_explicit(payload: Mapping[str, Any] | None) -> bool:
    """Return whether a failed CAS response provides a retryable status."""

    if not isinstance(payload, Mapping):
        return False
    return any(
        payload.get(key) is not None
        for key in ("isSuccess", "resultCode", "errorCode")
    )


def _cas_error_text(payload: Mapping[str, Any] | None, status: int) -> str:
    if payload is None:
        return f"HTTP {status}"
    code = payload.get("errorCode")
    desc = payload.get("errorDesc")
    if code or desc:
        return f"{code} {desc}".strip()
    return f"HTTP {status}"


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthenticationError("Huawei SmartHome response is not JSON") from error
    if not isinstance(value, dict):
        raise AuthenticationError("Huawei SmartHome response is not an object")
    return value


def _find_string(value: Any, wanted: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(wanted)
        if isinstance(candidate, str) and candidate:
            return candidate
        for child in value.values():
            found = _find_string(child, wanted)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_string(child, wanted)
            if found:
                return found
    return None


def _expires_at(value: Any) -> datetime | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _encrypt_password(password: str, public_key_pem: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise AuthenticationError("RSA resource did not contain an RSA public key")
    encrypted = public_key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return encrypted.hex().upper()


def _public_key_from_response(body: bytes) -> str | None:
    try:
        value = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    if value is not None:
        found = _find_public_key(value)
        if found:
            return found
    try:
        root = ElementTree.fromstring(body.decode("utf-8"))
    except (UnicodeDecodeError, ElementTree.ParseError):
        return None
    for element in root.iter():
        text = (element.text or "").strip()
        if not text:
            continue
        found = _normalize_public_key(text)
        if found:
            return found
        try:
            nested = json.loads(text)
        except json.JSONDecodeError:
            continue
        found = _find_public_key(nested)
        if found:
            return found
    return None


def _find_public_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower().replace("_", "-")
            if isinstance(child, str) and any(
                marker in lowered
                for marker in ("public-key", "publickey", "rsapublic", "rsa-key")
            ):
                found = _normalize_public_key(child)
                if found:
                    return found
            found = _find_public_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_public_key(child)
            if found:
                return found
    return None


def _normalize_public_key(value: str) -> str | None:
    text = value.strip()
    if "BEGIN PUBLIC KEY" in text or "BEGIN RSA PUBLIC KEY" in text:
        return text
    compact = re.sub(r"\s+", "", text)
    try:
        der = base64.b64decode(compact, validate=True)
        public_key = serialization.load_der_public_key(der)
    except (ValueError, TypeError, UnicodeEncodeError):
        return None
    if not isinstance(public_key, rsa.RSAPublicKey):
        return None
    return public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
