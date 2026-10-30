#!/usr/bin/env python3
"""图片代理的**路由契约**测试：生成的 URL 必须能被正确的视图接住。

**为什么单独一套**：这里出过一个极隐蔽的 bug，静态检查完全看不出来 ——

    ``build_image_url(account="13800138000")`` 生成
        /image/<entry>/13800138000/thumb/x.jpg
    但注册的路由是
        /image/{entry_id}/acct/{account}/{name}/{path:.*}

少了字面量 ``acct`` 段。而单账号路由 ``/image/{entry_id}/{name}/{path:.*}``
的 ``{path:.*}`` 是**贪婪**的，于是这条 URL **不会 404**，而是被它吞掉、
解析成 ``name="13800138000"`` / ``path="thumb/thumb/x.jpg"``。

后果：多账号用户的**每一张缩略图和原图**都取不到，界面显示图裂，
而且没有任何异常日志能指向"路由写错"。

本套件按 aiohttp ``UrlDispatcher`` 的实际行为（**按注册顺序、第一个匹配胜出**）
模拟匹配，对「生成的 URL」与「注册的路由」做双向核对。

**运行**::

    python3 _tools/test_image_routes.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "huawei_home_storage"
VIEWS = COMPONENT / "views.py"
PANEL = COMPONENT / "www" / "huawei-storage-panel.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 复刻 aiohttp 的路由匹配
# ---------------------------------------------------------------------------
def route_to_regex(tpl: str) -> str:
    """把 ``/a/{x}/{y:.*}`` 这样的模板转成正则。

    与 aiohttp 的 ``UrlDispatcher`` 保持同一语义：
    * ``{name}`` 默认匹配 ``[^{}/]+``（不含斜杠）
    * ``{name:.*}`` 匹配任意（含斜杠，**贪婪**）
    """
    out: list[str] = []
    i = 0
    for m in re.finditer(r"\{([a-zA-Z_][\w]*)(?::([^}]+))?\}", tpl):
        out.append(re.escape(tpl[i:m.start()]))
        out.append(f"(?P<{m.group(1)}>{m.group(2) or '[^{}/]+'})")
        i = m.end()
    out.append(re.escape(tpl[i:]))
    return "^" + "".join(out) + "$"


class FakeDispatcher:
    """按**注册顺序**匹配，第一个命中即胜出（aiohttp 的实际行为）。"""

    def __init__(self, routes: list[tuple[str, str]]):
        # routes: [(类名, url 模板)]
        self.routes = [(name, tpl, re.compile(route_to_regex(tpl))) for name, tpl in routes]

    def resolve(self, url: str) -> tuple[str, dict[str, str]] | None:
        for name, _tpl, rx in self.routes:
            m = rx.match(url)
            if m:
                return name, m.groupdict()
        return None


# ---------------------------------------------------------------------------
# 从源码抽取真实数据（不 import —— views 依赖整个集成）
# ---------------------------------------------------------------------------
def registered_routes() -> list[tuple[str, str]]:
    """按 ``async_register_views`` 里的**实际顺序**返回 (类名, url)。

    ⚠️ 用 AST 而不是正则：``HuaweiStorageImageView`` 的类体里只有
    ``url = URL``（引用模块级常量），正则按 ``url = "..."`` 抽会漏掉它
    （写这套测试时踩过，于是"两个视图都在"的断言假失败）。
    """
    import ast

    src = _read(VIEWS)
    tree = ast.parse(src)

    # 模块级常量：URL / STATUS_URL 这类
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    consts[tgt.id] = node.value.value

    def resolve(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        return None

    # 类名 -> url
    urls: dict[str, str] = {}
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name.endswith("View")):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "url":
                        val = resolve(stmt.value)
                        if val:
                            urls[node.name] = val

    # 注册顺序
    order: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "async_register_views":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        if sub.func.attr == "register_view" and sub.args:
                            arg = sub.args[0]
                            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                                order.append(arg.func.id)
    assert order, "async_register_views 里没有 register_view 调用"

    return [(cls, urls[cls]) for cls in order if cls in urls]


def build_image_url(entry_id: str, device_path: str, name: str = "raw",
                    account: str = "") -> str:
    """复刻 ``views.build_image_url`` 的**输出格式**（含修复后的 acct 段）。

    ⚠️ 这里刻意重写一遍而不是 import：目的是让「实现」与「路由」互为对照，
    两边独立写，一旦哪边改了格式，本测试就会失败。
    """
    base = "/api/huawei_home_storage/image"
    p = device_path.lstrip("/")
    if account:
        return f"{base}/{entry_id}/acct/{account}/{name}/{p}"
    return f"{base}/{entry_id}/{name}/{p}"


class RouteResolutionTest(unittest.TestCase):
    """生成的 URL 必须命中**它本该命中的那个视图**。"""

    def setUp(self):
        self.routes = registered_routes()
        self.dispatcher = FakeDispatcher(self.routes)

    def test_we_have_both_image_routes(self):
        names = [n for n, _ in self.routes]
        self.assertIn("HuaweiStorageImageView", names)
        self.assertIn("HuaweiStorageAccountImageView", names)

    def test_single_account_url_hits_plain_view(self):
        url = build_image_url("E1", "picture/thumb/a.jpg", "thumb")
        got = self.dispatcher.resolve(url)
        self.assertIsNotNone(got, f"单账号 URL 没有任何路由匹配（404）: {url}")
        cls, params = got
        self.assertEqual(cls, "HuaweiStorageImageView")
        self.assertEqual(params["entry_id"], "E1")
        self.assertEqual(params["name"], "thumb")
        self.assertEqual(params["path"], "picture/thumb/a.jpg")

    def test_multi_account_url_hits_account_view(self):
        """核心回归：多账号 URL 必须命中 acct 视图，且参数解析正确。"""
        url = build_image_url("E1", "picture/thumb/a.jpg", "thumb", "13800138000")
        got = self.dispatcher.resolve(url)
        self.assertIsNotNone(got, f"多账号 URL 没有任何路由匹配（404）: {url}")
        cls, params = got
        self.assertEqual(
            cls, "HuaweiStorageAccountImageView",
            f"多账号 URL 被 {cls} 抢先匹配了 —— 账号段被当成 name 用，"
            f"取图必然失败。URL={url} 参数={params}",
        )
        self.assertEqual(params["account"], "13800138000")
        self.assertEqual(params["name"], "thumb")
        self.assertEqual(params["path"], "picture/thumb/a.jpg")

    def test_any_alias_works_as_account(self):
        """账号段是别名（sha256 前 12 位），格式与真实 key 不同也要能匹配。"""
        for acc in ("13800138000", "a1b2c3d4e5f6", "user@example.com"):
            url = build_image_url("E1", "picture/a.jpg", "raw", acc)
            got = self.dispatcher.resolve(url)
            self.assertIsNotNone(got)
            cls, params = got
            self.assertEqual(cls, "HuaweiStorageAccountImageView", f"acc={acc}")
            self.assertEqual(params["account"], acc)

    def test_deep_device_paths_still_resolve(self):
        """设备路径带很多段（真实情况）也要正确。"""
        deep = "picture/thumb/0001/18242_abc_2026-10-29.jpg"
        url = build_image_url("E1", deep, "thumb", "13800138000")
        got = self.dispatcher.resolve(url)
        self.assertIsNotNone(got)
        _cls, params = got
        self.assertEqual(params["path"], deep)

    def test_registration_order_specific_first(self):
        """更具体的 ``acct`` 路由必须**先**注册（贪婪路由会抢）。"""
        names = [n for n, _ in self.routes]
        i_acct = names.index("HuaweiStorageAccountImageView")
        i_raw = names.index("HuaweiStorageImageView")
        self.assertLess(
            i_acct, i_raw,
            "HuaweiStorageAccountImageView 必须比 HuaweiStorageImageView 先注册 —— "
            "后者 {path:.*} 贪婪，先注册会吞掉所有 /acct/ 请求",
        )


class UrlFormatTest(unittest.TestCase):
    """``build_image_url`` 的源码必须真的生成带 ``acct`` 的 URL。"""

    def test_source_contains_acct_segment(self):
        src = _read(VIEWS)
        m = re.search(r"def build_image_url\(.*?\n(.*?)(?=\ndef )", src, re.DOTALL)
        self.assertIsNotNone(m, "找不到 build_image_url")
        body = m.group(1)
        self.assertIn(
            "acct", body,
            "build_image_url 没有生成 acct 段 —— 生成的多账号 URL 会匹配错视图",
        )

    def test_docstring_mentions_acct(self):
        """文档要写清楚两套格式，否则下一个人还会犯同样的错。"""
        src = _read(VIEWS)
        m = re.search(r'def build_image_url\(.*?"""(.*?)"""', src, re.DOTALL)
        self.assertIsNotNone(m)
        doc = m.group(1)
        self.assertIn("acct", doc)
        self.assertIn("/image/<entry>/<name>/<path>", doc)


class PanelUsesCorrectShapeTest(unittest.TestCase):
    """面板自拼的图片 URL 也必须符合路由格式。

    面板有两处自拼 URL：``renderDup`` 的缩略图 base、``downloadFile`` 的下载。
    两处都必须遵循 ``build_image_url`` 的格式 —— 带账号时**必须**有 ``acct``
    字面段，否则会被贪婪的单账号路由吞掉。
    """

    @staticmethod
    def _func_body(name: str) -> str:
        src = _read(PANEL)
        idx = src.find(f"function {name}(")
        assert idx > 0, f"面板里找不到 {name}"
        rest = src[idx:]
        nxt = re.search(r"\nasync function |\nfunction |\nconst \w+ = \(", rest[1:])
        return rest[: nxt.start() + 1] if nxt else rest

    def test_any_account_segment_is_prefixed_by_acct(self):
        """往图片 URL 里插账号的地方，最终都必须带 ``acct/``。

        做法：把所有插账号的写法归一到 ``accSeg`` 这类局部变量，然后断言
        每个用到它的地方，其**定义**里含 ``acct/``。
        直接对使用处做字面断言会误报（``/.../${accSeg}raw...`` 本身不含
        ``acct``，是变量带进来的）—— 写这条时踩过。
        """
        src = _read(PANEL)
        # 1) 收集「账号**路径段**变量」的定义。
        #
        #    ⚠️ 不能简单按名字含 acc/seg 收集：面板里还有
        #    ``acc``（查询参数 ``&account=``）、``accs``（账号列表）、
        #    ``acct``（登录表单输入框）—— 它们都不是 URL 路径段。
        #
        #    判定「是路径段」的依据：表达式里含 ``/``（路径分隔符）或含
        #    ``acct``。注意**不能**用「含 acct」来筛选后再断言「含 acct」，
        #    那样定义里漏了 acct 的变量会被直接过滤掉，断言恒真
        #    （变异测试时发现的自我豁免）。
        seg_defs: dict[str, str] = {}
        for line in src.splitlines():
            m = re.match(r"\s*const (\w+) = (.+);\s*$", line)
            if not m:
                continue
            name, expr = m.group(1), m.group(2)
            if not re.search(r"(acc|seg)", name, re.IGNORECASE):
                continue
            # 排除「查询参数」形态（&account= / ?account=）
            if re.search(r"[?&]account=", expr):
                continue
            # 必须像路径片段：含 / 或 acct
            if "/" not in expr and "acct" not in expr:
                continue
            seg_defs[name] = expr

        bad_defs = {
            name: expr for name, expr in seg_defs.items()
            if "acct" not in expr
        }
        self.assertEqual(
            bad_defs, {},
            "这些账号段变量没带 acct 字面量（生成的多账号 URL 会匹配错路由）: "
            + str(bad_defs),
        )

        # 2) 用到图片 URL 的账号段，必须在 seg_defs 里（即经过统一构造）
        offenders = []
        for line in src.splitlines():
            if "/api/huawei_home_storage/image/" not in line:
                continue
            if not re.search(r"(SEL\.account|accSeg|\w*[Aa]cc\w*)", line):
                continue
            # 允许两种写法：本行直接含 acct/，或用 seg 变量
            uses_seg_var = any(v in line for v in seg_defs)
            if "acct/" in line or uses_seg_var:
                continue
            offenders.append(line.strip())
        self.assertEqual(
            offenders, [],
            "这些行往图片 URL 里插了账号但既没 acct/ 也没用统一构造的变量:\n"
            + "\n".join(offenders),
        )

    def test_download_builds_acct_segment(self):
        body = self._func_body("downloadFile")
        self.assertIn("/image/", body)
        # 有账号时应插 acct 段
        self.assertIn("acct/", body,
                      "downloadFile 没构造 acct 段 —— 多账号下下载会走主账号会话")

    def test_dup_thumbnail_base_builds_acct_segment(self):
        body = self._func_body("renderDup")
        self.assertIn("acct/", body,
                      "renderDup 的缩略图 base 没构造 acct 段 —— 多账号下缩略图取不到")


if __name__ == "__main__":
    unittest.main(verbosity=2)
