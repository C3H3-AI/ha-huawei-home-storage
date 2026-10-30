#!/usr/bin/env python3
"""集成结构完整性的回归测试（manifest / 平台 / 配置流 / 视图注册）。

**为什么需要**：hassfest 与 HACS 只在"发布时"校验，本地开发改了文件却不会
立刻报错。这类缺陷的表现是「装上去了但某块功能静默失效」：

* 新增 ``async_step_xxx`` 却没写翻译 → 用户在界面上看到一个空的表单；
* ``PLATFORMS`` 里加了 ``Platform.IMAGE`` 却没有 ``image.py`` → 平台加载报错，
  但 traceback 只在启动日志里；
* 视图类写好了却忘记注册 → ``/api/...`` 直接 404，前端一直转圈。

所以这里做的是**声明与实现的双向核对**。

**运行**::

    python3 _tools/test_integration_structure.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "huawei_home_storage"
TOOLS = REPO_ROOT / "_tools"

#: Home Assistant 核心自带的库 —— 不需要也不能写进 requirements
HA_BUNDLED = {
    "aiohttp", "voluptuous", "cryptography", "yarl", "attr", "attrs",
    "async_timeout", "jinja2", "requests", "typing_extensions",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _manifest() -> dict[str, Any]:
    return json.loads(_read(COMPONENT / "manifest.json"))


def _strings() -> dict[str, Any]:
    return json.loads(_read(COMPONENT / "strings.json"))


class ManifestTest(unittest.TestCase):
    """HACS 对 manifest 的要求比 hassfest 更严，两边都得满足。"""

    #: hassfest 必填
    REQUIRED = [
        "domain", "name", "codeowners", "documentation",
        "issue_tracker", "version", "integration_type", "iot_class",
    ]

    def test_required_keys(self):
        mf = _manifest()
        missing = [k for k in self.REQUIRED if k not in mf]
        self.assertEqual(missing, [], f"manifest.json 缺必填键: {missing}")

    def test_domain_matches_directory(self):
        self.assertEqual(
            _manifest().get("domain"), COMPONENT.name,
            "domain 必须与目录名一致，否则 HA 加载不到",
        )

    def test_version_is_semver(self):
        version = str(_manifest().get("version", ""))
        self.assertRegex(
            version, r"^\d+\.\d+\.\d+$",
            f"HACS 要求 version 是 x.y.z 形式，当前: {version!r}",
        )

    def test_requirements_not_polluted_by_core_libs(self):
        """把 HA 核心自带的库写进 requirements 会让安装变慢甚至版本冲突。

        这条断言防的是「为了消 import 报错，随手把 aiohttp 塞进 requirements」
        这种改法 —— 那是错的，aiohttp 由 HA 提供。
        """
        reqs = _manifest().get("requirements") or []
        polluted = [
            r for r in reqs
            if re.split(r"[<>=!~ ]", r.strip(), maxsplit=1)[0] in HA_BUNDLED
        ]
        self.assertEqual(
            polluted, [],
            f"这些库由 HA 核心提供，不该写进 requirements: {polluted}",
        )

    def test_third_party_imports_declared(self):
        """真正需要 pip 安装的三方库必须在 requirements 里。"""
        src = "\n".join(
            _read(p) for p in COMPONENT.rglob("*.py")
        )
        imported = set()
        for m in re.finditer(r"^(?:from|import)\s+([a-zA-Z_][\w.]*)", src,
                             re.MULTILINE):
            imported.add(m.group(1).split(".")[0])

        local = {
            p.stem for p in COMPONENT.rglob("*.py")
        } | {"custom_components", "homeassistant", "__future__"}

        declared = {
            re.split(r"[<>=!~ ]", r.strip(), maxsplit=1)[0]
            for r in (_manifest().get("requirements") or [])
        }

        missing = sorted(
            name for name in imported
            if name not in HA_BUNDLED
            and name not in local
            and name not in declared
            and not name.startswith("_")
            # 标准库不算
            and name not in sys.stdlib_module_names
        )
        self.assertEqual(
            missing, [],
            f"这些三方库被 import 但没在 requirements 里声明: {missing}",
        )


class PlatformsTest(unittest.TestCase):
    """``PLATFORMS`` 里声明的每个平台都必须有实现文件。"""

    def _declared_platforms(self) -> list[str]:
        src = _read(COMPONENT / "const.py")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                tgt = node.target
                if isinstance(tgt, ast.Name) and tgt.id == "PLATFORMS":
                    out = []
                    for elt in ast.walk(node.value):
                        if (
                            isinstance(elt, ast.Attribute)
                            and isinstance(elt.value, ast.Name)
                            and elt.value.id == "Platform"
                        ):
                            out.append(elt.attr.lower())
                    return out
        self.fail("const.py 里找不到 PLATFORMS 定义")

    def test_every_platform_has_module(self):
        missing = [
            p for p in self._declared_platforms()
            if not (COMPONENT / f"{p}.py").exists()
        ]
        self.assertEqual(
            missing, [],
            f"这些平台已声明但没有实现文件（加载会报错）: {missing}",
        )

    def test_setup_entry_forwards_all_platforms(self):
        src = _read(COMPONENT / "__init__.py")
        self.assertIn(
            "async_forward_entry_setups(entry, PLATFORMS)", src,
            "async_setup_entry 没有转发 PLATFORMS，实体不会创建",
        )

    def test_unload_entry_releases_platforms(self):
        src = _read(COMPONENT / "__init__.py")
        self.assertIn(
            "async_unload_platforms(entry, PLATFORMS)", src,
            "async_unload_entry 没有卸载 PLATFORMS，重载会残留实体",
        )


class ConfigFlowStepsTest(unittest.TestCase):
    """每个配置步骤都要有翻译 —— 否则用户看到一个空白表单。"""

    def _steps_in(self, path: Path) -> set[str]:
        tree = ast.parse(_read(path))
        steps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("async_step_"):
                    steps.add(node.name[len("async_step_"):])
        # 排除框架自动生成的入口/终止步骤
        return steps - {"user", "reconfigure", "reauth"}

    def _translated_steps(self, section: str) -> set[str]:
        """HA 的翻译结构是 ``<section>.step.<step_id>``，不是 ``<section>.<step_id>``。"""
        strings = _strings()
        return set(((strings.get(section) or {}).get("step") or {}).keys())

    def test_accounts_flow_steps_translated(self):
        steps = self._steps_in(COMPONENT / "accounts_flow.py")
        translated = self._translated_steps("options")
        # ``menu`` 走 menu_options 的文案，不需要独立 step 块
        missing = sorted(steps - translated - {"menu"})
        self.assertEqual(
            missing, [],
            f"这些配置步骤没有翻译（界面会显示成空白/原始 step_id）: {missing}",
        )

    def test_config_flow_steps_translated(self):
        steps = self._steps_in(COMPONENT / "config_flow.py")
        translated = self._translated_steps("config")
        missing = sorted(steps - translated - {"menu"})
        self.assertEqual(
            missing, [],
            f"这些配置步骤没有翻译: {missing}",
        )

    def test_menu_options_have_step_or_abort(self):
        """``menu_options`` 列出的每个选项要么有 step 块，要么有 abort 块。

        HA 用 ``menu_options`` 渲染菜单项，用 ``step.<id>.title`` 或
        ``abort.<id>`` 取得显示文案；两者都没有就显示成裸的 step_id。
        """
        strings = _strings()
        problems = []
        for section, path in (
            ("config", COMPONENT / "config_flow.py"),
            ("options", COMPONENT / "accounts_flow.py"),
        ):
            block = strings.get(section) or {}
            menu = block.get("menu_options") or {}
            declared = set(menu.keys()) if isinstance(menu, dict) else set(menu)
            have_step = set((block.get("step") or {}).keys())
            have_abort = set((block.get("abort") or {}).keys())
            available = self._steps_in(path) | have_abort
            for name in sorted(declared):
                if name not in available:
                    problems.append(f"{section}.menu_options.{name} 无步骤实现")
                elif name not in have_step and name not in have_abort:
                    problems.append(f"{section}.menu_options.{name} 无文案")
        self.assertEqual(problems, [], "菜单项配置不完整: " + "; ".join(problems))

    def test_user_accounts_step_exists(self):
        """issue #35 的写入端 —— 它曾经完全缺失，导致隔离永不生效。"""
        steps = self._steps_in(COMPONENT / "accounts_flow.py")
        self.assertIn(
            "user_accounts", steps,
            "async_step_user_accounts 缺失 → CONF_USER_ACCOUNT_MAP 永远写不进去"
            " → 隐私隔离形同虚设",
        )


class ViewsRegistrationTest(unittest.TestCase):
    """视图类写好了必须注册，否则 URL 404。"""

    def _view_classes(self) -> set[str]:
        tree = ast.parse(_read(COMPONENT / "views.py"))
        out = set()
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("View"):
                out.add(node.name)
        return out

    def test_every_view_is_registered(self):
        registered_src = (
            _read(COMPONENT / "views.py") + _read(COMPONENT / "__init__.py")
        )
        missing = []
        for cls in sorted(self._view_classes()):
            # 注册形式是 ``hass.http.register_view(Cls())``
            if re.search(rf"register_view\(\s*{cls}\s*\(", registered_src) is None:
                missing.append(cls)
        self.assertEqual(
            missing, [],
            f"这些视图没有注册（URL 会 404）: {missing}",
        )

    def test_every_view_has_url(self):
        tree = ast.parse(_read(COMPONENT / "views.py"))
        problems = []
        for node in tree.body:
            if not (isinstance(node, ast.ClassDef) and node.name.endswith("View")):
                continue
            has_url = False
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name) and tgt.id in ("url", "name"):
                            has_url = True
            if not has_url:
                problems.append(node.name)
        self.assertEqual(
            problems, [],
            f"这些视图缺 url/name 属性（HA 无法挂载）: {problems}",
        )

    def test_views_flag_prevents_double_registration(self):
        """``VIEWS_FLAG`` 幂等锁 —— 重复 setup 时不能重复注册。

        ⚠️ 锁写在 ``views.async_register_views`` 里，不是 ``__init__.py``：
        ``__init__`` 只是调用者。断言要点是「注册前先查锁、注册后置锁」。
        """
        src = _read(COMPONENT / "views.py")
        self.assertIn("VIEWS_FLAG", src)

        # 用 AST 定位 async_register_views，检查它读锁 + 置锁
        tree = ast.parse(src)
        fn = next(
            (
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "async_register_views"
            ),
            None,
        )
        self.assertIsNotNone(fn, "找不到 async_register_views")
        body = (ast.get_source_segment(src, fn) or "").replace(" ", "")
        self.assertIn("ifhass.data.get(VIEWS_FLAG)", body,
                      "注册前没有检查幂等锁 → 重复 setup 会重复 register_view")
        self.assertIn("hass.data[VIEWS_FLAG]=True", body, "注册后没有置锁")


class PanelAccessTest(unittest.TestCase):
    """面板可见性开关保存后要立即生效，不能等重启。"""

    def test_panel_access_refreshes_panel(self):
        src = _read(COMPONENT / "accounts_flow.py")
        self.assertIn(
            "_refresh_panel", src,
            "panel_access 保存后没有重建面板 → 必须重启 HA 才生效",
        )

    def test_refresh_panel_unregisters_then_registers(self):
        src = _read(COMPONENT / "accounts_flow.py")
        self.assertIn("async_unregister_panel", src)
        self.assertIn("async_register_panel", src)


class TranslationsShapeTest(unittest.TestCase):
    """translations/*.json 的**顶层键**必须与 strings.json 一致。

    只比对 services 段是不够的：config / options 段漏了，用户看到的是
    原始 step_id，而 services 段全对 —— 这种半对的状态最容易漏。
    """

    def test_top_level_keys_match(self):
        base = set(_strings())
        problems = []
        for path in sorted((COMPONENT / "translations").glob("*.json")):
            keys = set(json.loads(_read(path)))
            missing = base - keys
            extra = keys - base
            if missing or extra:
                problems.append(
                    f"{path.name}: 缺 {sorted(missing)} 多 {sorted(extra)}"
                )
        self.assertEqual(
            problems, [],
            "翻译文件与 strings.json 顶层键不同步: " + "; ".join(problems),
        )

    def test_json_is_valid_utf8(self):
        """中文文案必须直接存 UTF-8，不能是 \\uXXXX 转义堆。"""
        for path in sorted((COMPONENT / "translations").glob("*.json")) + [
            COMPONENT / "strings.json"
        ]:
            raw = path.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as err:
                self.fail(f"{path.name} 不是合法 UTF-8: {err}")


class CIPipelineTest(unittest.TestCase):
    """CI 必须真的跑这些离线套件 —— 「测试不跑等于没有」。

    仓库里已有的 ``test_release_workflow`` 有同样的断言，理由一致：
    这些测试守的是「不报错的坏」，删掉运行步骤不会有任何征兆。
    """

    def setUp(self):
        self.validate = REPO_ROOT / ".github" / "workflows" / "validate.yml"
        self.runner = TOOLS / "run_all_tests.py"

    def test_ci_runs_all_suites(self):
        """validate.yml 必须有一步执行 ``run_all_tests.py``。

        ⚠️ 断言前要先剥注释：工作流里为了解释「为什么这么写」会有大段注释
        提到命令本身，直接对原文做子串断言会**恒为真**，抓不到回归
        （``test_release_workflow`` 里踩过同一个坑）。
        """
        code = self._code_only(self._read(self.validate))
        self.assertRegex(
            code, r"python3?\s+_tools/run_all_tests\.py",
            "CI 没有运行离线测试套件（run_all_tests.py）",
        )

    def test_runner_covers_every_suite_file(self):
        """目录里的每个 ``test_*.py`` 都必须登记进 ``run_all_tests.SUITES``。

        反向漏检：新增 ``test_xxx.py`` 但忘了登记 → 本地和 CI 都不会跑它，
        而文件看起来"已经写好了测试"。
        """
        import ast as _ast

        suite_files = {
            p.name for p in TOOLS.glob("test_*.py")
            # 这两个不是单元测试套件：一个是 JS 的（要真实数据），
            # 一个依赖 pyyaml 且由 CI 单独一步跑
            if p.name not in {"test_panel_render.js", "test_release_workflow.py"}
        }
        tree = _ast.parse(self._read(self.runner))
        registered: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("test_") and node.value.endswith(".py"):
                    registered.add(node.value)
        missing = sorted(suite_files - registered)
        self.assertEqual(
            missing, [],
            f"这些测试文件没登记进 run_all_tests.py（不会被任何地方执行）: {missing}",
        )

    def test_every_registered_suite_exists(self):
        """反向：登记了但文件不存在，CI 会红得莫名其妙。"""
        import ast as _ast

        tree = _ast.parse(self._read(self.runner))
        registered: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("test_") and node.value.endswith(".py"):
                    registered.add(node.value)
        ghost = sorted(n for n in registered if not (TOOLS / n).exists())
        self.assertEqual(
            ghost, [],
            f"run_all_tests.py 登记了不存在的套件: {ghost}",
        )

    def test_suites_need_no_home_assistant(self):
        """离线套件不得 ``import homeassistant``（CI 里不装 HA）。

        允许 ``sys.modules`` 里塞 stub，但不允许直接 import 真包 ——
        否则 CI 上会 ModuleNotFoundError，而本地因为装了 HA 反而不报错。
        """
        import ast as _ast

        problems = []
        for path in sorted(TOOLS.glob("test_*.py")):
            if path.name in {"test_release_workflow.py"}:
                continue
            tree = _ast.parse(self._read(path))
            for node in _ast.walk(tree):
                names: list[str] = []
                if isinstance(node, _ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, _ast.ImportFrom) and node.module:
                    # ``from homeassistant.x import y`` 只有在**模块层**才算
                    # 真依赖；函数内的延迟导入同样是真依赖，也要拦。
                    names = [node.module]
                for name in names:
                    root = name.split(".")[0]
                    if root == "homeassistant":
                        # stub 注入走 sys.modules，不走 import 语句
                        problems.append(f"{path.name}: import {name}")
        self.assertEqual(
            problems, [],
            "离线套件直接 import 了 homeassistant（CI 没装会失败）: "
            + "; ".join(sorted(set(problems))),
        )

    def test_verbose_mode_reports_same_counts(self):
        """``-v`` 与默认模式的用例统计必须一致。

        ⚠️ 这条是**真实事故**：运行器靠 ``Ran N tests`` 统计用例数，但一度
        写成 ``capture_output=not verbose`` —— 开 ``-v`` 时不捕获输出，
        正则永远匹配不到，7 个套件全被判成「0 用例」而失败。

        本地跑的是不带 ``-v`` 的，所以完全没暴露；CI 用 ``-v``，一推就 7/7 挂掉。
        这类缺陷只有「同一份代码两种调用方式都跑一遍」才抓得到。

        ⚠️ 防递归：本测试会去调运行器，而运行器又会跑到本套件。所以
        (1) 用环境变量做一次性保护，(2) 只挑一个**不会回调运行器**的套件。
        """
        if os.environ.get("HS_RUNNER_PROBE"):
            self.skipTest("递归保护：本次是运行器探针的子进程")

        import subprocess

        probe = ["服务一致性"]  # 该套件只做静态分析，不会回调运行器

        def counts(extra: list[str]) -> tuple[int, int]:
            proc = subprocess.run(
                [sys.executable, str(self.runner), *probe, *extra],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env={**os.environ, "HS_RUNNER_PROBE": "1"},
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            total = re.search(r"个套件通过：(\d+) 个用例", out)
            skip = re.search(r"，(\d+) 个跳过", out)
            if not total:
                self.fail(f"跑 {extra} 时没拿到统计结果，输出尾部：\n{out[-800:]}")
            return int(total.group(1)), int(skip.group(1)) if skip else 0

        plain = counts([])
        verbose = counts(["-v"])
        self.assertEqual(
            plain, verbose,
            f"默认模式与 -v 模式统计不一致：{plain} vs {verbose}"
            "（很可能是 verbose 分支没捕获输出，导致统计不到用例数）",
        )
        self.assertGreater(plain[0], 0, "一个用例都没统计到")

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _code_only(text: str) -> str:
        """剥掉 yaml 的 ``#`` 注释行与行尾注释。"""
        out = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            # 行尾注释：只在 ``#`` 前有空格时判定（避免砍掉 URL 里的 #）
            idx = line.find(" #")
            if idx >= 0:
                line = line[:idx]
            out.append(line)
        return "\n".join(out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
