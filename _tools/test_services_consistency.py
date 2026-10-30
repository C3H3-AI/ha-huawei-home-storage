#!/usr/bin/env python3
"""服务定义三处一致性 + 不可逆操作确认机制的回归测试。

**为什么需要**：这类缺陷同样「不报错」——

* 同一个服务名被注册两次（``share_to_person``），Python 后者静默覆盖前者，
  注册表里只有一个、CI 全绿，但 ``services.yaml`` 按旧签名写的文档必然报错；
* ``services.yaml`` 声明了 ``confirm``、``services.py`` 没校验（或反过来）——
  文档说"要确认"，实际直接执行，用户以为有护栏；
* 服务在 ``services.py`` 注册了却没有翻译，前端显示成裸服务名。

三处定义（代码常量 / yaml 文档 / 翻译文案）任何一处漏掉，用户看到的行为
都和文档不符。所以这里做**交叉断言**，而不是分别检查各自"看起来对"。

**运行**（无需安装 Home Assistant）::

    python3 _tools/test_services_consistency.py
"""
from __future__ import annotations

import re
import sys
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "huawei_home_storage"
SERVICES_PY = COMPONENT / "services.py"
SERVICES_YAML = COMPONENT / "services.yaml"
STRINGS_JSON = COMPONENT / "strings.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 静态读取（不 import services.py —— 它依赖整个集成）
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def registered_service_names() -> list[str]:
    """从 ``services.py`` 里抽取真正注册的服务名（用 AST，不靠正则猜）。

    必须覆盖两种注册方式，否则会漏掉 **循环注册** 的那批服务（plugin_*
    就是这样注册的，正则表达式完全看不见）：

    1. ``hass.services.async_register(DOMAIN, SERVICE_X, ...)``
    2. ``for _svc, _func in ((SERVICE_X, f), ...): async_register(DOMAIN, _svc, ...)``

    常量名会被解析回字符串值 —— 这样"常量重复定义"也能一并暴露。
    """
    import ast

    src = _read(SERVICES_PY)
    tree = ast.parse(src)

    # 常量表（同名后定义覆盖前定义，正是缺陷形态；重复由另一个测试负责）
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            val = node.value
            if (
                isinstance(tgt, ast.Name)
                and tgt.id.startswith("SERVICE_")
                and isinstance(val, ast.Constant)
                and isinstance(val.value, str)
            ):
                consts[tgt.id] = val.value

    def resolve(node: ast.AST) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id, f"<未解析:{node.id}>")
        return "<动态>"

    names: list[str] = []

    def has_register(node: ast.AST) -> bool:
        """节点子树里是否有 ``async_register`` 调用。"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "async_register":
                    return True
        return False

    def walk(node: ast.AST) -> None:
        # 方式 1：直接调用
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "async_register" and len(node.args) >= 2:
                names.append(resolve(node.args[1]))
        # 方式 2：``for X in ((SERVICE_A, f), ...): async_register(DOMAIN, X, ...)``
        #   只认「循环体里真的注册」的那种 —— 有些 for 循环遍历
        #   ``(name, client_method)`` 做**动态分发**（dev_err_code / repair_mode
        #   等），它们不是服务名，误收会让一致性检查凭空多出一堆"未文档化服务"。
        if (
            isinstance(node, ast.For)
            and isinstance(node.iter, (ast.Tuple, ast.List))
            and has_register(node)
        ):
            for elt in node.iter.elts:
                if isinstance(elt, (ast.Tuple, ast.List)) and elt.elts:
                    names.append(resolve(elt.elts[0]))
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return [n for n in names if not n.startswith("<")]


def duplicate_constants() -> dict[str, list[str]]:
    """找出被**重复赋值**的 ``SERVICE_*`` 常量名（后者覆盖前者）。"""
    src = _read(SERVICES_PY)
    seen: dict[str, list[str]] = {}
    for m in re.finditer(
        r'^(SERVICE_[A-Z0-9_]+)\s*=\s*"([^"]+)"', src, re.MULTILINE
    ):
        seen.setdefault(m.group(1), []).append(m.group(2))
    return {k: v for k, v in seen.items() if len(v) > 1}


def _yaml_service_blocks() -> dict[str, dict[str, Any]]:
    """极简 YAML 服务块解析（不依赖 pyyaml）。

    只需要回答两件事：**顶格的服务名有哪些**，以及**每个服务块里出现了
    哪些字段名**。项目里 yaml 的结构是规整的：

        service_name:
          fields:
            field_name:
              ...
    """
    blocks: dict[str, dict[str, Any]] = {}
    current: str | None = None
    in_fields = False
    for raw in _read(SERVICES_YAML).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()

        if indent == 0 and stripped.endswith(":"):
            current = stripped[:-1].strip()
            blocks[current] = {"fields": [], "desc": ""}
            in_fields = False
            continue
        if current is None:
            continue
        if indent == 2 and stripped == "fields:":
            in_fields = True
            continue
        if indent == 2 and not stripped.startswith("fields:"):
            in_fields = False
        if indent == 2 and stripped.startswith("description:"):
            blocks[current]["desc"] = stripped
        if in_fields and indent == 4 and stripped.endswith(":"):
            blocks[current]["fields"].append(stripped[:-1].strip())
    return blocks


def _strings_services() -> dict[str, Any]:
    import json

    data = json.loads(_read(STRINGS_JSON))
    return (data.get("services") or {})


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
class ServiceRegistrationTest(unittest.TestCase):
    """注册表里不能有重名 —— 重名等于「后一个静默吃掉前一个」。"""

    def test_no_duplicate_registration(self):
        names = registered_service_names()
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(
            dupes, [],
            f"以下服务被注册了多次（后者会覆盖前者，文档与行为不符）: {dupes}",
        )

    def test_no_duplicate_constants(self):
        dupes = duplicate_constants()
        self.assertEqual(
            dupes, {},
            f"以下 SERVICE_* 常量被重复赋值（前者形同虚设）: {dupes}",
        )

    def test_share_files_to_person_is_registered(self):
        """``share_to_person`` 拆成两个后，新名字必须真的在注册表里。"""
        self.assertIn(
            "share_files_to_person", registered_service_names(),
            "按文件分享的服务没有注册（原缺陷：与按相册的同名，被覆盖）",
        )

    def test_share_to_person_registered_exactly_once(self):
        names = registered_service_names()
        self.assertEqual(
            names.count("share_to_person"), 1,
            "share_to_person 必须恰好注册一次",
        )


class YamlMatchesCodeTest(unittest.TestCase):
    """``services.yaml`` 与代码注册的服务必须**双向**一致。"""

    def setUp(self):
        self.code = set(registered_service_names())
        self.yaml = set(_yaml_service_blocks())

    def test_every_registered_service_is_documented(self):
        missing = sorted(self.code - self.yaml)
        self.assertEqual(
            missing, [],
            f"这些服务已注册但没有写进 services.yaml（前端看不到参数）: {missing}",
        )

    def test_every_documented_service_is_registered(self):
        ghost = sorted(self.yaml - self.code)
        self.assertEqual(
            ghost, [],
            f"services.yaml 里这些服务根本不存在（调用必然报错）: {ghost}",
        )


class ConfirmMechanismTest(unittest.TestCase):
    """不可逆操作必须在**两层**都有确认：schema 与处理函数。"""

    #: (服务名, 确认词)。新增不可逆服务时请加进这里。
    #:
    #: ⚠️ 这是**手写清单**，天然会漏 —— ``del_album`` 就漏了很久（删除相册
    #: 不可逆，却一个 confirm 都没有，与其他四个不一致）。所以下面额外有
    #: ``test_no_irreversible_service_missing_confirm``：按服务名语义自动
    #: 扫一遍，凡是"听起来会删东西"的服务，要么在清单里，要么必须在
    #: ``KNOWN_REVERSIBLE`` 里**显式声明为什么可逆**。手写清单只能兜已知的，
    #: 自动扫描才能兜住"以后新加的"。
    IRREVERSIBLE = [
        ("shutdown_device", "SHUTDOWN"),
        ("reboot_device", "REBOOT"),
        ("empty_recycle", "EMPTY_RECYCLE"),
        ("permanent_delete_recycle_items", "PERMANENT_DELETE"),
        ("del_album", "DELETE_ALBUM"),
        ("merge_face_albums", "MERGE_FACE_ALBUMS"),
    ]

    #: 名字像"删除"但**确实可逆**的服务，必须在这里说明理由。
    #: 每加一条都要写清楚"为什么不需要 confirm"——否则就是在给漏网之鱼开后门。
    KNOWN_REVERSIBLE = {
        "delete_paths": "默认进回收站（可逆）；仅 skip_recycle=true 才需 confirm，"
                        "由 test_delete_paths_confirm_only_for_permanent 单独覆盖",
        "delete_media": "相册照片删除走 /gallery/deleteMedia，实测进最近删除，可恢复",
        "hide_albums": "是**开关**不是删除：同一接口传 hidden=False 即恢复显示"
                       "（/gallery/modifyAlbumsHiddenStatus），照片与相册都不受影响",
        "remove_album_members": "只是把成员移出相册，相册与照片仍在，随时可重新加入",
        "plugin_uninstall": "卸载插件可随时重装（plugin_install / plugin_market 都在），"
                            "设备数据不受影响",
        "clean_task_records": "只清传输任务中心的历史记录，不碰文件本身",
        "cancel_upload": "取消的是**进行中**的上传，重新发起即可，无数据损失",
    }

    def test_schema_requires_confirm(self):
        src = _read(SERVICES_PY)
        for service, word in self.IRREVERSIBLE:
            self.assertIn(
                f"_confirm_field(CONFIRM_{word})", src,
                f"{service} 的 schema 没有要求 confirm={word}",
            )

    def test_handler_rechecks_confirm(self):
        """处理函数要再校验一次 —— schema 可以被 ``async_call`` 内部调用绕过。

        只看有没有出现 ``_reject_unconfirmed(call, CONFIRM_X)``，不定位到具体
        函数：函数被重命名时这条断言不会误报，但**删掉**任何一处都会。
        """
        src = _read(SERVICES_PY)
        for service, word in self.IRREVERSIBLE:
            self.assertIn(
                f"_reject_unconfirmed(call, CONFIRM_{word})", src,
                f"{service} 的处理函数没有二次校验 confirm",
            )

    def test_yaml_exposes_confirm_field(self):
        blocks = _yaml_service_blocks()
        for service, _word in self.IRREVERSIBLE:
            self.assertIn(service, blocks, f"{service} 不在 services.yaml")
            self.assertIn(
                "confirm", blocks[service]["fields"],
                f"{service} 的 yaml 没声明 confirm 字段（用户不知道要传）",
            )

    def test_strings_expose_confirm_field(self):
        strings = _strings_services()
        for service, _word in self.IRREVERSIBLE:
            entry = strings.get(service) or {}
            fields = entry.get("fields") or {}
            self.assertIn(
                "confirm", fields,
                f"{service} 的翻译里没有 confirm 字段说明",
            )

    def test_no_irreversible_service_missing_confirm(self):
        """按**语义**自动扫一遍，揪出手写清单漏掉的不可逆服务。

        ``IRREVERSIBLE`` 是人肉维护的，新增服务时忘了登记就永远查不出来 ——
        ``del_album``（删除相册，不可逆）就这么漏了很久：其他四个不可逆服务
        都有 confirm，只有它裸奔，一句 service 调用就能清掉整本共享相册。

        所以这里反向做：把所有**名字听起来会破坏数据**的服务找出来，要求
        每一个都被显式归类 —— 要么在 ``IRREVERSIBLE``（有 confirm），要么在
        ``KNOWN_REVERSIBLE`` 里写清楚**为什么可逆**。漏归类即失败。

        这不是在挑刺：每一条都要有人真的想过"这玩意删了还能不能救回来"。
        """
        # 毁灭性语义关键词。宁可误报（逼人写一句理由），不可漏报。
        DESTRUCTIVE = (
            "del", "delete", "remove", "clear", "empty", "permanent",
            "shutdown", "reboot", "uninstall", "hide", "merge",
        )
        src = _read(SERVICES_PY)
        all_svc = set(re.findall(r'^SERVICE_[A-Z_0-9]+\s*=\s*"([a-z_0-9]+)"', src, re.M))

        suspects = sorted(
            n for n in all_svc if any(k in n for k in DESTRUCTIVE)
        )
        self.assertTrue(suspects, "一个可疑服务都没扫到，规则或抽取坏了")

        claimed = {s for s, _w in self.IRREVERSIBLE} | set(self.KNOWN_REVERSIBLE)
        unclassified = [n for n in suspects if n not in claimed]
        self.assertEqual(
            unclassified,
            [],
            "这些服务的名字听起来会破坏数据，但既没加进 IRREVERSIBLE"
            "（要求 confirm），也没加进 KNOWN_REVERSIBLE（说明为何可逆）。"
            "请逐个判断后归类，不要直接放进 KNOWN_REVERSIBLE 了事：\n"
            f"  {unclassified}",
        )

    def test_known_reversible_is_not_stale(self):
        """``KNOWN_REVERSIBLE`` 里不能留着已经不存在的服务名。

        否则清单会越积越脏，后人看到一堆对不上号的条目就不敢动它了。
        """
        src = _read(SERVICES_PY)
        all_svc = set(re.findall(r'^SERVICE_[A-Z_0-9]+\s*=\s*"([a-z_0-9]+)"', src, re.M))
        stale = sorted(set(self.KNOWN_REVERSIBLE) - all_svc)
        self.assertEqual(stale, [], f"KNOWN_REVERSIBLE 里有已不存在的服务：{stale}")

    def test_irreversible_list_matches_reality(self):
        """``IRREVERSIBLE`` 里的服务必须真的存在（防改名后清单失效）。"""
        src = _read(SERVICES_PY)
        all_svc = set(re.findall(r'^SERVICE_[A-Z_0-9]+\s*=\s*"([a-z_0-9]+)"', src, re.M))
        missing = sorted({s for s, _w in self.IRREVERSIBLE} - all_svc)
        self.assertEqual(missing, [], f"IRREVERSIBLE 里有不存在的服务：{missing}")

    def test_delete_paths_confirm_only_for_permanent(self):
        """``delete_paths`` 的 confirm 是**条件性**的。

        默认走回收站（可恢复）不该强制确认；只有 ``skip_recycle=true``        （永久删除）才要 —— 原缺陷正是一刀切都不校验。
        """
        src = _read(SERVICES_PY)
        self.assertIn(
            "_reject_unconfirmed(\n            call, CONFIRM_PERMANENT_DELETE",
            src,
            "delete_paths 的 skip_recycle 永久删除分支缺少确认校验",
        )


class RejectUnconfirmedBehaviourTest(unittest.TestCase):
    """``_reject_unconfirmed`` 的**运行时**行为（不是文本断言）。"""

    @classmethod
    def setUpClass(cls):
        """直接按文件加载 services 模块的确认函数，不执行整个模块。"""
        import ast
        import textwrap

        src = _read(SERVICES_PY)
        tree = ast.parse(src)
        wanted = {"_reject_unconfirmed"}
        chunks: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name) and tgt.id.startswith(
                    ("CONFIRM_", "SERVICE_")
                ):
                    chunks.append(ast.get_source_segment(src, node) or "")
            elif isinstance(node, ast.FunctionDef) and node.name in wanted:
                chunks.append(ast.get_source_segment(src, node) or "")

        ns: dict[str, Any] = {"__name__": "svc_stub"}
        exec(  # noqa: S102 - 只执行本仓库自己的常量与纯函数
            textwrap.dedent("\n\n".join(chunks)), ns
        )
        cls.ns = ns

    def _call(self, data: dict[str, Any]) -> Any:
        call = types.SimpleNamespace(data=data)
        return self.ns["_reject_unconfirmed"](call, "SHUTDOWN")

    def test_missing_confirm_is_rejected(self):
        result = self._call({})
        self.assertIsNotNone(result, "没传 confirm 却放行了")
        self.assertFalse(result["ok"])
        self.assertIn("不可逆", result["error"])

    def test_wrong_confirm_is_rejected(self):
        self.assertIsNotNone(self._call({"confirm": "shutdown"}))  # 大小写敏感
        self.assertIsNotNone(self._call({"confirm": "SHUTDOWN "}))  # 尾空格
        self.assertIsNotNone(self._call({"confirm": True}))

    def test_correct_confirm_passes(self):
        self.assertIsNone(self._call({"confirm": "SHUTDOWN"}))


class TranslationCoverageTest(unittest.TestCase):
    """每个服务都要有翻译，否则前端显示裸服务名。"""

    def test_all_services_translated(self):
        code = set(registered_service_names())
        translated = set(_strings_services())
        missing = sorted(code - translated)
        self.assertEqual(
            missing, [],
            f"这些服务缺翻译（UI 里会显示成服务 ID）: {missing}",
        )

    def test_translations_match_strings_json(self):
        """``translations/*.json`` 的 services 段必须与 ``strings.json`` 同键。

        HA 运行时读的是 translations，strings.json 只是开发时的源 ——
        两者键不一致意味着「翻译存在但没生效」。
        """
        import json

        strings_services = set(_strings_services())
        problems: list[str] = []
        for path in sorted((COMPONENT / "translations").glob("*.json")):
            data = json.loads(_read(path))
            keys = set(data.get("services") or {})
            missing = strings_services - keys
            if missing:
                problems.append(f"{path.name} 缺 {sorted(missing)}")
        self.assertEqual(problems, [], "翻译文件与 strings.json 不同步: "
                         + "; ".join(problems))

    def test_no_dead_locale_files(self):
        """``zh.json`` 不是 HA 识别的 locale（HA 用 ``zh-Hans``/``zh-Hant``）。"""
        dead = (COMPONENT / "translations" / "zh.json")
        self.assertFalse(
            dead.exists(),
            "translations/zh.json 是死文件（HA 不加载 zh，只加载 zh-Hans）",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
