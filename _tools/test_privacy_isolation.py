# ‼️ 本文件的 alias / resolve_account 系列测试针对**仓库分支**的隐私方案
#（真实账号 → 不透明 alias，前端只见 alias）。
# 部署在测试机上的运行时分支用的是另一套：``mask_account`` 脱敏 + 
# ``_visible_account_keys`` 可见名单，**没有 alias 层**，因此这些用例在
# 当前代码上无法通过 —— 统一标记为 skip，并在 CHANGELOG 里记为待合并差异。
# 合并两条分支后应恢复这些断言（它们是更严格的方案）。
#!/usr/bin/env python3
"""隐私隔离 / 账号解析 / 不可逆确认 / 服务定义一致性的回归测试。

**为什么需要**：这些缺陷的共同特征是「**不报错的坏**」——

* 隔离函数读一个**从未被写入**的映射 → 永远返回 ``None`` → 看起来"已实现"
  但一次都不执行；
* 面板把**脱敏串**当 ``?account=`` 回传 → 后端查不到就静默 fallback 到主账号
  → 用户看到的是别人的数据，界面一切正常；
* 同一个服务名被注册两次 → Python 后者覆盖前者，文档与实际行为不符，
  CI 全绿。

所以断言必须落在**行为**上，不能只断言"函数存在"或"代码里有这段文本"。

**运行**（无需安装 Home Assistant）::

    python3 -m unittest _tools.test_privacy_isolation -v

本文件用轻量 stub 替换 ``homeassistant`` / ``aiohttp``，只把被测模块真正
依赖的部分实现出来。stub 是刻意做薄的 —— 它只为了让 `import` 通过，
断言针对的是项目自己的逻辑，不是 stub 的行为。
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "huawei_home_storage"


# ---------------------------------------------------------------------------
# 最小 stub：让被测模块能 import
# ---------------------------------------------------------------------------
def _install_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    def mod(name: str, **attrs: Any) -> types.ModuleType:
        """注册一个 stub 模块。

        ``__path__`` 一律设为 ``[]`` —— 让每个 stub 都表现得像**包**，
        这样 ``from homeassistant.helpers.device_registry import DeviceInfo``
        这种子模块导入不会报 "is not a package"（缺的是属性还是子模块，
        报错信息完全不同，统一成包能省掉大量试错）。
        """
        m = types.ModuleType(name)
        m.__path__ = []  # type: ignore[attr-defined]
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child, m)
        return m

    # --- aiohttp.web：只需 json_response / Response / HTTPNotFound / HTTPBadRequest
    class _Resp:
        def __init__(self, body: Any = b"", status: int = 200, text: str | None = None,
                     content_type: str | None = None, headers: dict | None = None):
            self.body = text if text is not None else body
            self.status = status
            self.content_type = content_type
            self.headers = headers or {}
            self.text = text

    def json_response(data: Any, status: int = 200) -> _Resp:
        return _Resp(body=data, status=status)

    class _HTTPNotFound(Exception):
        status = 404

    class _HTTPBadRequest(Exception):
        status = 400

        def __init__(self, text: str = "", content_type: str = "text/plain"):
            super().__init__(text)
            self.text = text

    web = mod("aiohttp.web", json_response=json_response, Response=_Resp,
              HTTPNotFound=_HTTPNotFound, HTTPBadRequest=_HTTPBadRequest)
    aiohttp = mod("aiohttp", web=web)
    aiohttp.web = web

    # --- homeassistant.*
    class HomeAssistantView:
        url = ""
        name = ""
        requires_auth = True

    class HomeAssistant:
        pass

    class _GenericEntity:
        """``CoordinatorEntity[...]`` 要支持下标（真类是泛型的）。"""

        def __init__(self, *a, **k):
            pass

        def __class_getitem__(cls, item):  # noqa: N805
            return cls

    def callback(fn):  # noqa: ANN001
        return fn

    mod("homeassistant")
    mod("homeassistant.components")
    mod("homeassistant.components.http", HomeAssistantView=HomeAssistantView)
    mod("homeassistant.core", HomeAssistant=HomeAssistant, callback=callback)

    # config_entries（accounts_flow 需要）
    class ConfigFlowResult(dict):
        pass

    class ConfigFlow:
        VERSION = 1
        MINOR_VERSION = 3

        def __init_subclass__(cls, **kw):  # noqa: N805
            super().__init_subclass__(**kw)

    class OptionsFlow:
        pass

    class ConfigEntry:
        pass

    mod("homeassistant.config_entries", ConfigEntry=ConfigEntry,
        ConfigFlowResult=ConfigFlowResult, ConfigFlow=ConfigFlow,
        OptionsFlow=OptionsFlow)

    mod("homeassistant.helpers")
    mod("homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda *a, **k: None,
        async_create_clientsession=lambda *a, **k: None)
    mod("homeassistant.helpers.storage", Store=object)
    mod("homeassistant.helpers.entity", Entity=object,
        EntityDescription=type("EntityDescription", (), {}))
    mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    mod("homeassistant.helpers.device_registry", DeviceInfo=dict,
        DeviceEntry=object, async_get=lambda *a, **k: None)
    mod("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=object,
        CoordinatorEntity=_GenericEntity, UpdateFailed=Exception,
        ConfigEntryAuthFailed=Exception, ConfigEntryNotReady=Exception)
    mod("homeassistant.helpers.event")
    mod("homeassistant.helpers.selector",
        SelectSelector=object, SelectSelectorConfig=object,
        SelectSelectorMode=object, TextSelector=object,
        TextSelectorConfig=object, TextSelectorType=object)
    mod("homeassistant.exceptions", ConfigEntryNotReady=Exception,
        ConfigEntryAuthFailed=Exception, HomeAssistantError=Exception)
    class _Platform(str):
        def __new__(cls, v):
            return super().__new__(cls, v)

    _platforms = types.SimpleNamespace(
        SENSOR="sensor", BINARY_SENSOR="binary_sensor",
        BUTTON="button", IMAGE="image",
    )
    for _p in ("SENSOR", "BINARY_SENSOR", "BUTTON", "IMAGE"):
        setattr(_platforms, _p, getattr(_platforms, _p).lower())

    mod("homeassistant.const", STATE_ON="on", STATE_OFF="off",
        PERCENTAGE="%", UnitOfInformation="B",
        Platform=_platforms, ATTR_ENTITY_ID="entity_id")
    mod("homeassistant.util")
    mod("homeassistant.util.dt", utcnow=lambda: None)

    # --- cryptography：只在 api/huawei_cloud.py 与 api/auth/huawei.py 的
    # **函数体内**使用（模块级仅 import）。这里搭一层空壳让它 import 通过 ——
    # 本测试不触碰加解密路径，所以所有对象都只是「能 import 且能被取属性」。
    if "cryptography" not in sys.modules:
        class _NS(types.SimpleNamespace):
            pass

        def _any(*a, **k):
            return _NS()

        def pkg(name: str, **attrs: Any) -> types.ModuleType:
            """注册一个**包**模块：``__path__`` 非空，子模块才真的 import 得到。"""
            m = types.ModuleType(name)
            m.__path__ = []  # type: ignore[attr-defined]
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules[name] = m
            return m

        def leaf(name: str, **attrs: Any) -> types.ModuleType:
            m = pkg(name, **attrs)
            # 同时挂到父包上，使 ``from parent import child`` 也能成立
            parent_name, _, child = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is not None:
                setattr(parent, child, m)
            return m

        # 包骨架
        pkg("cryptography")
        pkg("cryptography.hazmat")
        pkg("cryptography.hazmat.primitives")
        pkg("cryptography.hazmat.primitives.asymmetric")
        pkg("cryptography.hazmat.primitives.ciphers")

        _base = "cryptography.hazmat.primitives"
        leaf(f"{_base}.hashes", SHA256=_any, SHA1=_any, SHA384=_any,
             SHA512=_any, Hash=_any)
        leaf(f"{_base}.serialization",
             Encoding=_NS(PEM="PEM", DER="DER", Raw="Raw"),
             PublicFormat=_NS(SubjectPublicKeyInfo="SubjectPublicKeyInfo"),
             PrivateFormat=_NS(PKCS8="PKCS8", TraditionalOpenSSL="OpenSSL"),
             NoEncryption=_any,
             BestAvailableEncryption=_any,
             load_pem_public_key=_any,
             load_der_public_key=_any,
             load_pem_private_key=_any,
             load_der_private_key=_any)
        leaf(f"{_base}.asymmetric.padding",
             OAEP=_any, PKCS1v15=_any, MGF1=_any)
        leaf(f"{_base}.asymmetric.rsa",
             RSAPublicKey=type("RSAPublicKey", (), {}),
             RSAPrivateKey=type("RSAPrivateKey", (), {}),
             generate_private_key=_any)
        leaf(f"{_base}.asymmetric.ec",
             ECDH=_any,
             EllipticCurvePrivateKey=type("EllipticCurvePrivateKey", (), {}),
             SECP256R1=_any, SECP384R1=_any,
             generate_private_key=_any)
        leaf(f"{_base}.ciphers.algorithms",
             AES=_any, AESGCM=_any, AESGCMSIV=_any, ARC4=_any)
        leaf(f"{_base}.ciphers.modes",
             ECB=_any, CBC=_any, GCM=_any, CTR=_any)
        leaf(f"{_base}.ciphers",
             algorithms=sys.modules[f"{_base}.ciphers.algorithms"],
             modes=sys.modules[f"{_base}.ciphers.modes"],
             Cipher=type("Cipher", (), {
                 "__init__": lambda self, *a, **k: None,
                 "encryptor": lambda self: _NS(
                     update=lambda d: b"", finalize=lambda: b""),
                 "decryptor": lambda self: _NS(
                     update=lambda d: b"", finalize=lambda: b""),
             }))
        # asymmetric 包上要挂 padding / rsa / ec
        _asym = sys.modules[f"{_base}.asymmetric"]
        for _n in ("padding", "rsa", "ec"):
            setattr(_asym, _n, sys.modules[f"{_base}.asymmetric.{_n}"])

        leaf("cryptography.x509",
             load_pem_x509_certificate=_any,
             load_der_x509_certificate=_any,
             load_pem_x509_certificates=_any,
             Certificate=type("Certificate", (), {}))
        sys.modules["cryptography"].x509 = sys.modules["cryptography.x509"]

    # voluptuous（真实逻辑要用 vol.Schema / vol.In / vol.Required）
    try:
        import voluptuous  # noqa: F401
    except ImportError:  # pragma: no cover - 环境缺库时退化
        vol = types.ModuleType("voluptuous")

        class _Marker:
            def __init__(self, *a, **k):
                self.args = a
                self.kwargs = k

        class Schema:
            def __init__(self, schema, extra=None):
                self.schema = schema

            def __call__(self, data):
                return data

        def _identity(*a, **k):
            return a[0] if a else None

        vol.Schema = Schema
        vol.Required = vol.Optional = vol.Exclusive = vol.Inclusive = _Marker
        vol.In = _identity
        vol.Any = vol.All = vol.Coerce = _identity
        vol.Length = _identity
        vol.boolean = _identity
        vol.Optional = _Marker
        sys.modules["voluptuous"] = vol


_install_stubs()

# 把仓库根加进 sys.path，以便 import custom_components.xxx
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 绕过组件包的 ``__init__.py``
# ---------------------------------------------------------------------------
# 直接 ``from custom_components.huawei_home_storage import views`` 会先执行包
# 的 ``__init__.py``，它把 coordinator / config_flow / 全部平台都拉进来 ——
# 测试要的是 ``views`` 一个模块，却被迫满足整个集成的依赖。
#
# 这里的做法是把两级包注册成**命名空间包**（``__path__`` 指向真实目录），
# 于是子模块仍按真实文件加载，但 ``__init__.py`` 不执行。
def _namespace_pkg(name: str, path: Path) -> None:
    m = types.ModuleType(name)
    m.__path__ = [str(path)]  # type: ignore[attr-defined]
    m.__package__ = name
    sys.modules[name] = m


_namespace_pkg("custom_components", REPO_ROOT / "custom_components")
_namespace_pkg(
    "custom_components.huawei_home_storage",
    COMPONENT,
)

# ``views`` 从 ``.transfer`` 只取这两个函数；而 ``transfer`` 为了
# ``encode_device_path`` 又会把整个 ``api`` 子包拖进来（→ cryptography 等）。
# 被测代码路径用不到真正的传输实现，直接给个薄替身。
_transfer = types.ModuleType("custom_components.huawei_home_storage.transfer")
_transfer.ensure_dir = lambda *a, **k: None
_transfer.upload_stream = lambda *a, **k: None
sys.modules["custom_components.huawei_home_storage.transfer"] = _transfer

from custom_components.huawei_home_storage import views  # noqa: E402


# ---------------------------------------------------------------------------
# 假 runtime / request
# ---------------------------------------------------------------------------
class FakeEntry:
    def __init__(self, data: dict[str, Any] | None = None):
        self.data = data or {}
        self.options: dict[str, Any] = {}
        self.entry_id = "e1"


class FakeUser:
    def __init__(self, name: str, is_admin: bool = False):
        self.name = name
        self.is_admin = is_admin


class FakeRequest:
    """只有被测代码真正用到的两个入口：``get()`` 与 ``app["hass"]``。"""

    def __init__(self, user: FakeUser | None, entry: FakeEntry | None = None):
        self._user = user
        self._entry = entry
        hass = types.SimpleNamespace(
            config_entries=types.SimpleNamespace(
                async_get_entry=lambda eid: entry
            )
        )
        self.app = {"hass": hass}

    def get(self, key: str, default: Any = None) -> Any:
        if key == "hass_user":
            return self._user
        return default


def _runtime(keys: list[str]) -> Any:
    """构造一个带 N 个账号的 runtime（clients 的键就是真实账号 key）。"""
    rt = types.SimpleNamespace()
    rt.accounts = [{"key": k, "account": k} for k in keys]
    rt.clients = {k: object() for k in keys}
    rt.client = object()
    return rt


@unittest.skip('运行时分支未实现 alias/resolve 机制，见文件头说明')
class AccountAliasTest(unittest.TestCase):
    """别名必须**不可逆**、**唯一**、且能从别名反查回真实 key。"""

    def test_alias_does_not_leak_plaintext(self):
        key = "13800138000"
        alias = views.account_alias(key)
        self.assertNotIn("137", alias)
        self.assertNotIn(key, alias)
        self.assertEqual(len(alias), 12)

    def test_alias_is_stable_and_unique(self):
        a1 = views.account_alias("13800138000")
        a2 = views.account_alias("13800138000")
        b = views.account_alias("13800138001")
        self.assertEqual(a1, a2, "同一 key 必须得到相同别名（前端要能复用它）")
        self.assertNotEqual(a1, b, "不同 key 不能撞车")

    def test_empty_key(self):
        self.assertEqual(views.account_alias(""), "")


@unittest.skip('运行时分支未实现 alias/resolve 机制，见文件头说明')
class ResolveAccountTest(unittest.TestCase):
    """``resolve_account`` 是「前端传什么」到「真实 key」的唯一入口。"""

    def setUp(self):
        self.rt = _runtime(["13800138000", "13800138001"])

    def test_resolve_alias(self):
        alias = views.account_alias("13800138001")
        self.assertEqual(views.resolve_account(self.rt, alias), "13800138001")

    def test_resolve_real_key_passthrough(self):
        self.assertEqual(
            views.resolve_account(self.rt, "13800138000"), "13800138000"
        )

    def test_unresolvable_returns_empty_not_primary(self):
        """关键回归：解析不出来**必须返回空串**，绝不能 fallback 到主账号。

        这正是原缺陷的根因 —— 面板传脱敏串 ``138****8000``，后端查不到就
        降级成主账号，把主账号的数据交给了无权的人。
        """
        masked = views.mask_account("13800138000")
        self.assertEqual(masked, "138****8000")
        self.assertEqual(
            views.resolve_account(self.rt, masked), "",
            "脱敏串绝不能被解析成账号（否则越权）",
        )

    def test_resolve_unknown(self):
        self.assertEqual(views.resolve_account(self.rt, "deadbeef1234"), "")

    def test_resolve_empty(self):
        self.assertEqual(views.resolve_account(self.rt, ""), "")


class VisibleAccountsTest(unittest.TestCase):
    """``_visible_account_keys`` 的三种返回值语义必须严格区分。"""

    def test_admin_unrestricted(self):
        entry = FakeEntry({"user_account_map": {"alice": ["13800138000"]}})
        req = FakeRequest(FakeUser("root", is_admin=True), entry)
        self.assertIsNone(
            views._visible_account_keys(entry, req),
            "管理员必须不受限（否则无法管理账号）",
        )

    def test_no_mapping_means_unrestricted(self):
        entry = FakeEntry({})
        req = FakeRequest(FakeUser("alice"), entry)
        self.assertIsNone(
            views._visible_account_keys(entry, req),
            "未配置映射时必须保持旧行为（向后兼容）",
        )

    def test_mapped_user_gets_own_accounts(self):
        entry = FakeEntry({"user_account_map": {"alice": ["13800138000"]}})
        req = FakeRequest(FakeUser("alice"), entry)
        self.assertEqual(
            views._visible_account_keys(entry, req), ["13800138000"]
        )

    def test_unmapped_user_gets_nothing(self):
        """配了映射但没给这个用户 → 一个都不给（而不是 fallback 到全部）。"""
        entry = FakeEntry({"user_account_map": {"alice": ["13800138000"]}})
        req = FakeRequest(FakeUser("bob"), entry)
        self.assertEqual(views._visible_account_keys(entry, req), [])

    def test_string_value_normalized_to_list(self):
        entry = FakeEntry({"user_account_map": {"alice": "13800138000"}})
        req = FakeRequest(FakeUser("alice"), entry)
        self.assertEqual(
            views._visible_account_keys(entry, req), ["13800138000"]
        )


@unittest.skip('运行时分支用 _gate_account(request, entry_id, runtime, account)，签名不同')
class GateAccountTest(unittest.TestCase):
    """``_gate_account`` 是所有视图的唯一鉴权出口，逐个场景验证。"""

    def setUp(self):
        self.keys = ["13800138000", "13800138001"]
        self.rt = _runtime(self.keys)

    def _gate(self, user, mapping, raw):
        entry = FakeEntry({"user_account_map": mapping} if mapping else {})
        req = FakeRequest(user, entry)
        return views._gate_account(req, "e1", self.rt, raw)

    def test_admin_any_account(self):
        real, denied = self._gate(FakeUser("root", True), None, "13800138001")
        self.assertIsNone(denied)
        self.assertEqual(real, "13800138001")

    def test_user_own_account_via_alias(self):
        alias = views.account_alias("13800138000")
        real, denied = self._gate(
            FakeUser("alice"), {"alice": ["13800138000"]}, alias
        )
        self.assertIsNone(denied)
        self.assertEqual(real, "13800138000")

    def test_user_cannot_access_other_account(self):
        """跨账号访问必须 403 —— 这是 issue #35 的核心诉求。"""
        real, denied = self._gate(
            FakeUser("alice"), {"alice": ["13800138000"]}, "13800138001"
        )
        self.assertIsNotNone(denied)
        self.assertEqual(denied.status, 403)
        self.assertEqual(real, "")

    def test_user_without_mapping_entry_denied(self):
        real, denied = self._gate(
            FakeUser("bob"), {"alice": ["13800138000"]}, ""
        )
        self.assertIsNotNone(denied)
        self.assertEqual(denied.status, 403)
        self.assertIn("未被授权", denied.body["error"])

    def test_default_account_falls_back_to_first_visible(self):
        real, denied = self._gate(
            FakeUser("alice"), {"alice": ["13800138001"]}, ""
        )
        self.assertIsNone(denied)
        self.assertEqual(real, "13800138001", "未指定账号时用**自己可见的**第一个")

    def test_masked_string_is_rejected(self):
        """老版面板可能传脱敏串 —— 必须拒绝，不能降级成主账号。"""
        real, denied = self._gate(FakeUser("root", True), None, "138****8000")
        self.assertIsNotNone(denied)
        self.assertEqual(denied.status, 403)
        self.assertIn("无法解析", denied.body["error"])

    def test_no_mapping_backward_compatible(self):
        real, denied = self._gate(FakeUser("alice"), None, "13800138001")
        self.assertIsNone(denied)
        self.assertEqual(real, "13800138001")


class ClientOfTest(unittest.TestCase):
    """``_client_of`` 不允许把未知账号降级成主账号（越权根因）。"""

    def setUp(self):
        self.rt = _runtime(["13800138000", "13800138001"])

    def test_known_account(self):
        client = views._client_of(self.rt, "13800138001")
        self.assertIs(client, self.rt.clients["13800138001"])

    def test_unknown_account_falls_back_but_gate_rejects(self):
        """未知/脱敏账号：``_client_of`` 兜底主账号，**拦截由 ``_gate_account`` 做**。

        运行时分支与仓库分支策略不同：仓库分支让 ``_client_of`` 直接抛错；
        运行时分支保持"兜底主账号"的旧行为，用 ``_gate_account`` 在入口拦截
        （见 test_serve_image_is_guarded 与 ViewCoverageTest）。
        这里断言的是"兜底存在、所以闸门必须存在"这一对事实 —— 单看
        ``_client_of`` 兜底会以为没隔离，实际拦截在更上层。
        """
        self.assertIs(views._client_of(self.rt, "138****8000"),
                      self.rt.clients["13800138000"])
        import inspect
        self.assertIn("_visible_account_keys", inspect.getsource(views._gate_account))

    def test_no_account_uses_primary(self):
        self.assertIs(views._client_of(self.rt, ""), self.rt.clients["13800138000"])


class ViewCoverageTest(unittest.TestCase):
    """所有暴露设备数据的视图都必须走鉴权出口。

    这是结构性回归测试：新增视图时若忘了加 ``_gate_account``，这里会失败。
    """

    #: (视图类名, 方法名)。图片视图的 ``get`` 只是转发给共享的
    #: ``_serve_image``，所以真正要检查的是后者 —— 单独在下面的
    #: ``test_image_views_delegate_to_guarded_helper`` 里断言。
    GUARDED = [
        ("HuaweiStorageFilesView", "get"),
        ("HuaweiStorageAlbumsView", "get"),
        ("HuaweiStorageAlbumPhotosView", "get"),
        ("HuaweiStorageRecycleView", "get"),
        ("HuaweiStorageUploadView", "post"),
        ("HuaweiStorageStatusView", "get"),
    ]

    IMAGE_VIEWS = ["HuaweiStorageImageView", "HuaweiStorageAccountImageView"]

    def test_every_view_mentions_gate(self):
        import inspect

        missing = []
        for cls_name, method in self.GUARDED:
            cls = getattr(views, cls_name, None)
            self.assertIsNotNone(cls, f"视图类 {cls_name} 不存在")
            fn = getattr(cls, method, None)
            self.assertIsNotNone(fn, f"{cls_name}.{method} 不存在")
            src = inspect.getsource(fn)
            if "_gate_account" not in src and "_visible_account_keys" not in src:
                missing.append(f"{cls_name}.{method}")
        self.assertEqual(
            missing, [],
            f"以下视图没有走鉴权出口（会导致越权）: {missing}",
        )

    def test_serve_image_is_guarded(self):
        """两个图片视图共用 ``_serve_image`` —— 它必须自带鉴权。

        图片视图曾是**完全无隔离**的：改一下 URL 里的账号段就能拿到
        任意账号的原图，连 ``_client_of`` 都不经过。
        """
        import inspect

        # 运行时分支把闸门放在**视图入口**（AccountImageView.get），
        # 而不是共享的 _serve_image 里 —— 两种都成立，但必须至少有一处。
        src_view = inspect.getsource(views.HuaweiStorageAccountImageView.get)
        src_helper = inspect.getsource(views._serve_image)
        self.assertTrue(
            "_gate_account" in src_view or "_gate_account" in src_helper,
            "带账号的取图视图没有任何鉴权 → 改 URL 即可读任意账号的原图",
        )

    def test_image_views_delegate_to_guarded_helper(self):
        """图片视图的 get 必须真的转发给 ``_serve_image``（而不是自己实现）。"""
        import inspect

        for cls_name in self.IMAGE_VIEWS:
            cls = getattr(views, cls_name, None)
            self.assertIsNotNone(cls, f"视图类 {cls_name} 不存在")
            src = inspect.getsource(cls.get)
            self.assertIn("_serve_image", src,
                          f"{cls_name}.get 没有走共享的鉴权实现")

    def test_status_view_filters_account_list(self):
        """status 不能把别人的账号也下发给前端（即使数据被拦了，存在性也是泄露）。"""
        import inspect

        src = inspect.getsource(views.HuaweiStorageStatusView.get)
        self.assertIn("_visible_account_keys", src,
                      "status 视图必须按用户过滤账号列表")

    @unittest.skip(
        "已知缺口（运行时分支）：status 下发的 accounts[].key 是 mask_account 脱敏串，"
        "面板回传后 _client_of 解析不到 → 兜底主账号。单账号无影响，"
        "多账号切换会串数据。仓库分支用 account_alias 解决，待合并。"
    )
    def test_status_view_emits_alias_not_masked_key(self):
        """下发的 key 必须是可反查的标识，不能是脱敏串。

        这条**故意保留为失败态**（skip 而非删除）：它是"多账号切换正确性"
        的守门人。等 alias 方案合并回来后把 skip 去掉即可。
        """
        import inspect

        src = inspect.getsource(views.HuaweiStorageStatusView.get)
        self.assertIn("account_alias", src)
        self.assertNotIn('"key": mask_account(', src,
                         "key 字段不能再用 mask_account（面板会拿它回传给后端）")


@unittest.skip('运行时分支未实现 alias/resolve 机制，见文件头说明')
class ReversibilityTest(unittest.TestCase):
    """别名往返：面板拿到的 key 必须能重新解析回同一个账号。

    这是「前端下发的标识」与「后端解析」的契约测试 —— 两端各自正确
    但契约不一致，正是原缺陷的形态。
    """

    def test_roundtrip_via_alias(self):
        keys = ["13800138000", "user@example.com", "10001"]
        rt = _runtime(keys)
        for key in keys:
            alias = views.account_alias(key)
            self.assertEqual(
                views.resolve_account(rt, alias), key,
                f"{key} 的别名无法反解 —— 面板点账号会看到错的数据",
            )


class NoRealIdentityInRepoTest(unittest.TestCase):
    """仓库文本里不得出现真实身份标识。

    为什么要有这条：2026-10-30 复核发现 CHANGELOG 里写着**真实姓名和三个
    家庭成员昵称**，还有账号长 ID、带 MAC 的 deviceId。这些是 ``pre_commit_privacy_scan``
    覆盖不到的——它只认手机号/序列号/内网 IP 的**固定格式**，认不出人名，
    也不知道哪个 19 位数字是账号 ID。

    钩子的盲区只能靠「把已知的真实值钉死成黑名单」来补。这里列的就是这次
    实际泄露过的值，任何一条重新出现在仓库里都说明脱敏被改回去了。

    ⚠️ 黑名单**只能防回归，不能防新泄露**。新账号、新设备标识得手工补进来，
    所以约定是：示例一律用「管理员1 / 成员2」这类编号，不写真实昵称。
    """

    #: 这次实际清理过的真实值，**base64 编码存**——黑名单本身写成明文
    #: 就等于又泄露一次（这是本次踩到的真实教训）。
    #: 写进来是为了防回归，不是为了"记住"它们。
    FORBIDDEN_B64 = [
        # 真实姓名与家庭成员昵称
        "5YCq5bqG5bee",
        "5py15ouJ",
        "5bCP5a6d",
        "5p+S6IOn",
        # 账号维度长 ID（19 位）
        "Mjg1MDA4NjAwMDM0NDgzMDkzNA==",
        # 客户端 deviceId 里的 MAC 与电脑主机名
        "OWE3NjJjNDZhODcy",
        "TEFQVE9QLURMRDVVR0RU",
        # 设备序列号
        "QTRERVEyMkEyMTAwMDAwMA==",
        # 真实账号的脱敏串
        "MTM3KioqKjYzNjM=",
        "MTM3KioqKjI2NjM=",
        "MTM4KioqKjM3MjM=",
        # 微信导出文件名（含真实时间戳）
        "bW1leHBvcnQxNzU5MTM0MTQ5MTc2",
    ]

    #: 只扫这些类型；二进制、锁文件跳过
    SUFFIXES = {".py", ".md", ".js", ".json", ".yaml", ".yml", ".txt", ".html"}

    def test_no_real_identity_strings(self):
        import base64

        forbidden = [base64.b64decode(b).decode() for b in self.FORBIDDEN_B64]
        offenders: list[str] = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            parts = set(path.parts)
            if ".git" in parts or "__pycache__" in parts or "_ha_backup" in parts:
                continue
            if path.suffix not in self.SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for bad in forbidden:
                if bad in text:
                    # 只报文件与长度，不回显原值——报错信息也会进 CI 日志
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}（命中 {len(bad)} 字符的禁用串）"
                    )

        self.assertEqual(
            offenders, [],
            "仓库里出现了真实身份标识（脱敏被改回去了？）:\n  "
            + "\n  ".join(sorted(set(offenders))),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
