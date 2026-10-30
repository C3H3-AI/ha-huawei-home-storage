#!/usr/bin/env python3
"""端到端接线审计：面板每个动作都必须有真实后端。

**为什么需要这一层**

前面五个套件各自验证「单个文件内部是否正确」：
服务定义三处对齐、路由格式契约、上传参数、隐私隔离…… 但它们都**默认
「面板调用点」是存在的**。真实故障往往长这样：

    面板上有个"清空回收站"按钮 → 点击调 ``svc("empty_recycle")``
    → 但 ``services.py`` 里那个服务叫 ``empty_recycle_bin``
    → 用户点下去只看到 "失败：Service not found"

这类断链**不报错、不崩溃、CI 全绿**，因为两边各自都是"对的"。只有把
面板侧字符串和后端侧注册表**放在一起比对**才看得见。

本套件做四件事：

1. 面板调用的每个 ``svc("x")``，必须真的注册过（含动态分发里的元组）。
2. 面板请求的每个 ``/api/...`` 端点，必须有对应视图（含方法约束）。
3. 面板上传必须带 ``account``（多账号写错账号的回归）。
4. 注册过的服务必须同时出现在 ``services.yaml``（否则 HA 不校验参数、
   前端不显示说明）与两份翻译（否则界面上是裸 key）。

全部静态分析，不需要 HA / aiohttp。跑法::

    python3 _tools/test_wiring.py
"""
from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "custom_components" / "huawei_home_storage"
PANEL = PKG / "www" / "huawei-storage-panel.js"
SERVICES_PY = PKG / "services.py"
VIEWS_PY = PKG / "views.py"
DEVICE_PY = PKG / "api" / "device.py"
TRANSFER = PKG / "transfer.py"
SERVICES_YAML = PKG / "services.yaml"
STRINGS = PKG / "strings.json"
ZH = PKG / "translations" / "zh-Hans.json"
EN = PKG / "translations" / "en.json"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _module_str_consts(tree: ast.Module) -> dict[str, str]:
    """收集模块级 ``NAME = "literal"`` 常量。

    服务名在 ``services.py`` 里是用常量传的（``SERVICE_QUERY_FILES``），
    直接取 ``n.args[1].value`` 会拿到 ``None``，必须先查常量表。
    """
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out[tgt.id] = node.value.value
    return out


def registered_services() -> set[str]:
    """从 ``services.py`` 抽出所有真正注册的服务名。

    ⚠️ 必须处理**动态分发**（``for _svc, _func in ((CONST, fn), ...)``）：
    插件三件套就是这样注册的。早前写服务一致性测试时漏了这一步，把
    ``dev_err_code`` / ``repair_mode`` 这种**循环里的局部变量**误当成
    服务名，导致断言对着空气检查。这里的做法是：只认 ``async_register``
    调用点，常量名查表，查不到就报出来（见 ``test_no_unresolvable``）。
    """
    tree = ast.parse(_read(SERVICES_PY))
    consts = _module_str_consts(tree)
    names: set[str] = set()

    # 先找出**动态分发**的循环变量名：``for _svc, _func in (...): async_register(..)``
    #
    # 这些循环变量必须排除在「直扫」之外 —— 否则 ``_svc`` 会被当成一个
    # 解析不出来的常量名，误报 ``<UNRESOLVED:_svc>``。它的真实取值由下面的
    # 元组展开负责（写这套测试时踩过：第一版就报了 UNRESOLVED）。
    dispatch_vars: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        body_src = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        if "async_register" not in body_src:
            continue
        if not isinstance(node.iter, (ast.Tuple, ast.List)):
            continue
        tgt = node.target
        if isinstance(tgt, ast.Tuple):
            for t in tgt.elts:
                if isinstance(t, ast.Name):
                    dispatch_vars.add(t.id)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "async_register"):
            continue
        if len(node.args) < 2:
            continue
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            names.add(arg.value)
        elif isinstance(arg, ast.Name):
            if arg.id in dispatch_vars:
                continue  # 由下面的元组展开处理
            names.add(consts.get(arg.id, f"<UNRESOLVED:{arg.id}>"))

    # 动态分发：把元组首元素展开成真实服务名
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        body_src = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        if "async_register" not in body_src:
            continue
        if not isinstance(node.iter, (ast.Tuple, ast.List)):
            continue
        for elt in node.iter.elts:
            if not isinstance(elt, ast.Tuple) or not elt.elts:
                continue
            first = elt.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
            elif isinstance(first, ast.Name):
                names.add(consts.get(first.id, f"<UNRESOLVED:{first.id}>"))

    return names


def panel_service_calls() -> set[str]:
    """面板里 ``svc("name", ...)`` 调用的服务名。"""
    return set(re.findall(r'svc\(\s*"([a-z_0-9]+)"', _read(PANEL)))


def panel_api_paths() -> set[str]:
    """面板请求的 ``/api/huawei_home_storage/<segment>`` 端点前缀。"""
    return set(
        re.findall(
            r"/api/huawei_home_storage/([a-z_]+)", _read(PANEL)
        )
    )


def view_routes() -> dict[str, str]:
    """``{视图类名: url 模板}``，常量引用会被解析。"""
    src = _read(VIEWS_PY)
    tree = ast.parse(src)
    consts = _module_str_consts(tree)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(
                isinstance(t, ast.Name) and t.id == "url" for t in stmt.targets
            ):
                continue
            val = stmt.value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                out[node.name] = val.value
            elif isinstance(val, ast.Name):
                out[node.name] = consts.get(val.id, f"<UNRESOLVED:{val.id}>")
    return out


def _strip_py_comments(text: str) -> str:
    """去掉 Python 的 docstring 与 ``#`` 行注释。

    ⚠️ 这已经是**第五次**因为"注释和断言撞车"导致假测试了（前四次在 JS 侧）。
    这次的具体情形：``_copy_to_album`` 的 docstring 里写着

        ⚠️ 必须用 ``_client_for(runtime, call)``（2026-10-29 修）

    于是把真正的 ``client = _client_for(runtime, call)`` 改回
    ``runtime.client`` 之后，断言 ``assertIn("_client_for(runtime, call)")``
    **仍然匹配 docstring**，测试全绿。

    规律很清楚：**只要断言的关键字出现在注释里，这条断言就废了**。
    所有"代码里有没有 X"的断言，都必须先剥注释。
    """
    # docstring（三引号，可能跨行；先长后短避免误伤）
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    text = re.sub(r"'''[\s\S]*?'''", "", text)
    out = [ln for ln in text.split("\n") if not ln.strip().startswith("#")]
    return "\n".join(out)


def _py_func(name: str, path=None) -> str:
    """取 ``transfer.py`` 里 ``async def <name>(...)`` 的函数体（剥离注释）。

    顶层函数（缩进 0），与 ``py_fn_body`` 不同 —— 那个是 services.py 里
    ``async_register_services`` 内部的闭包（缩进 4）。
    """
    src = _read(path or TRANSFER)
    start = src.find(f"async def {name}(")
    if start < 0:
        raise AssertionError(f"找不到函数 {name}")
    nxt = re.search(r"\n(?:async )?def ", src[start + 1:])
    body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
    return _strip_line_comments(body)


def py_fn_body(name: str) -> str:
    """取 ``services.py`` 里 ``async def <name>(...)`` 的函数体（**已剥离注释**）。

    这些处理函数是 ``async_register_services`` 内部的闭包（缩进 4 空格），
    所以结束边界要按 ``\\n    async def `` / ``\\n    def `` 找，不能复用 JS 版。
    """
    src = _read(SERVICES_PY)
    start = src.find(f"async def {name}(")
    if start < 0:
        raise AssertionError(f"找不到函数 {name}")
    nxt = re.search(r"\n    (?:async )?def ", src[start + 1:])
    body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
    return _strip_py_comments(body)


def fn_body(name: str) -> str:
    """取一个 ``async function <name>(...)`` 的函数体，**已剥离整行注释**。

    ⚠️ 剥离注释不是洁癖（2026-10-29 第二次栽在这里）：
    ``albumUploadFiles`` 里有一行说明写着"**不要**用 curSpace()"，
    而 ``test_album_upload_uses_fixed_space`` 断言
    ``assertNotIn("curSpace()", body)`` —— 改成正确写法之后，那句注释
    反而让断言失败。注释描述"不做什么"是必要的，那就必须让断言只看代码。

    另：这曾是**两份**一模一样的实现（两个测试类各拷一份），改一处漏一处
    的风险太高，合并成模块级。
    """
    src = _read(PANEL)
    start = src.find(f"async function {name}(")
    if start < 0:
        raise AssertionError(f"找不到函数 {name}")
    nxt = re.search(r"\nasync function |\nfunction ", src[start + 1:])
    body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
    return _strip_line_comments(body)


class ServiceWiringTest(unittest.TestCase):
    """面板 → 服务：不能出现"调用了不存在的服务"。"""

    def test_all_panel_services_are_registered(self):
        registered = registered_services()
        called = panel_service_calls()
        self.assertTrue(called, "面板里一个 svc() 都没找到，抽取逻辑坏了")
        missing = sorted(called - registered)
        self.assertEqual(
            missing,
            [],
            f"面板调用了未注册的服务，用户点下去必然 'Service not found'：{missing}",
        )

    def test_no_unresolvable_service_const(self):
        bad = [n for n in registered_services() if n.startswith("<UNRESOLVED:")]
        self.assertEqual(
            bad,
            [],
            f"服务名常量解析失败（常量可能定义在别的模块）：{bad}",
        )

    def test_no_duplicate_registration(self):
        """同名服务注册两次，HA 会静默覆盖，前一个 handler 永远不生效。"""
        tree = ast.parse(_read(SERVICES_PY))
        consts = _module_str_consts(tree)
        seen: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "async_register"):
                continue
            if len(node.args) < 2:
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                seen.append(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in consts:
                seen.append(consts[arg.id])
        dupes = sorted({n for n in seen if seen.count(n) > 1})
        self.assertEqual(dupes, [], f"服务被重复注册（后者覆盖前者）：{dupes}")


class ViewWiringTest(unittest.TestCase):
    """面板 → HTTP 端点：不能请求不存在的视图。"""

    def test_all_panel_paths_have_view(self):
        routes = view_routes()
        # 路由模板里的第一段（静态字面部分）
        served: set[str] = set()
        for tpl in routes.values():
            m = re.match(r"^/api/huawei_home_storage/([a-z_]+)", tpl)
            if m:
                served.add(m.group(1))
        requested = panel_api_paths()
        self.assertTrue(requested, "面板里一个 /api/ 请求都没找到，抽取逻辑坏了")
        missing = sorted(requested - served)
        self.assertEqual(
            missing,
            [],
            f"面板请求了没有视图承接的端点，必然 404：{missing}",
        )

    def test_image_route_has_account_variant(self):
        """取图必须有 ``acct`` 变体，否则多账号下拿到的是主账号的图。"""
        routes = view_routes()
        self.assertTrue(
            any("/acct/" in t for t in routes.values()),
            "缺少带 acct 段的取图路由，多账号取图会静默串号",
        )

    def test_upload_view_is_post_only(self):
        """上传视图必须限定 POST。

        否则 ``GET /api/huawei_home_storage/upload/<entry>`` 会被当正常
        请求处理，而它读 ``request.post()`` 拿到空 body —— 报错信息会是
        "缺少文件" 之类，与真正的成因（方法错了）无关。
        """
        src = _read(VIEWS_PY)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            has_upload = any(
                isinstance(s, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "url" for t in s.targets
                )
                for s in node.body
            )
            if not has_upload:
                continue
            names = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
            # 上传视图：定义了 post 但**不该**定义 get
            if "post" in names and any(
                isinstance(s, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "name" for t in s.targets
                )
                for s in node.body
            ):
                # 有 name 属性的是缩略图变体视图，跳过
                continue
            if "post" in names:
                self.assertNotIn(
                    "get",
                    names,
                    f"{node.name} 同时实现了 get 与 post；上传端点是写操作，"
                    f"不该有 get",
                )


class PanelUploadTest(unittest.TestCase):
    """上传是最容易"看起来能用其实写错地方"的动作。"""

    def test_upload_url_passes_account(self):
        """上传 URL 必须拼 ``account``。

        ⚠️ 两个坑（都踩过）：

        1. 不能只断言 ``"account=" in body``：``const acc = "...&account=..."``
           那一行定义本身就含 ``account=``，即使忘了拼进 URL，断言也恒为真。
        2. 不能只抓**第一行** ``const url = ...``：真实代码是两行拼接 ——

              const url = `/api/.../upload/${...}`
                + `?path=...${acc}`;

           只抓首个反引号串会得到不含 ``${acc}`` 的前半句，误报失败。

        正确做法是把 ``const url =`` 之后到分号之间的**整段拼接表达式**
        取出来，再检查其中是否引用 ``acc``。
        """
        src = _read(PANEL)
        m = re.search(r"const url\s*=\s*(.+?);", src, re.S)
        self.assertIsNotNone(m, "找不到上传 URL 的构造语句")
        expr = m.group(1)
        self.assertIn(
            "upload",
            expr,
            "抓到的不是上传 URL 的构造语句（抽取逻辑坏了）",
        )
        # 接受 ``${acc}`` 与 ``+ acc`` 两种拼法
        self.assertTrue(
            "${acc}" in expr or re.search(r"\+\s*acc\b", expr),
            "上传 URL 没有拼 acc 变量：多账号下文件会被塞进"
            "「当前用户可见的第一个账号」，且两个账号目录树看起来一样，"
            "用户极难发现传错了地方。实际表达式：\n" + expr,
        )

    def test_upload_uses_filesvc_space(self):
        """默认走文件空间（相册域至今未跑通）。"""
        src = _read(PANEL)
        self.assertIn(
            "filesvc",
            src,
            "面板应默认使用文件空间上传",
        )

    def test_panel_warns_album_not_synced(self):
        """文件页上传必须说清"传的是文件空间，不会自动进相册"。

        这是既有事实：文件页的上传落在 filesvc，相册是 gallery 的另一个域。
        但**现在有了出路** —— 右键「加入相册」走 ``copy_to_album``（真机可用）。
        所以文案必须同时给出「不会自动进」和「怎么手动进」，
        只写前半句等于把人堵在死胡同里（这正是之前的毛病）。
        """
        src = _read(PANEL)
        self.assertTrue(
            "不会自动进相册" in src,
            "文件页缺少「上传到文件空间 ≠ 进相册」的提示，用户会以为功能坏了",
        )
        self.assertIn(
            "加入相册", src,
            "既然 copy_to_album 已经可用，就必须告诉用户入口在哪",
        )

    def test_panel_does_not_promise_album_import(self):
        """提示不能给出做不到的第二条路。

        ⚠️ 原来那句写的是"想放进相册：到相册页勾选已有照片 → 「加入相册」"
        （2026-10-29 改）：相册页**只列相册内的照片**，刚传到文件空间、
        还没进任何相册的文件根本不在那个列表里，勾不到。这句话等于告诉
        用户"还有条路"，实际是死路 —— 比不说更糟。
        """
        src = _read(PANEL)
        # ⚠️ 用 assertNotIn 会把**整个面板文件**塞进报错信息（实测 124KB），
        # 日志直接被淹掉。这里自己定位并只报出上下文。
        needle = "到相册页勾选已有照片"
        pos = src.find(needle)
        if pos >= 0:
            line_no = src.count("\n", 0, pos) + 1
            self.fail(
                f"面板还在承诺一条走不通的路（相册页列不出刚上传的文件）。"
                f"位置：面板第 {line_no} 行\n"
                f"    {(src[max(0, pos - 60):pos + 60]).strip()}"
            )

    def test_no_always_true_dead_string(self):
        """``|| true`` 这类恒真条件会让分支失去意义，是隐藏死逻辑的温床。

        原来那句提示写的是 ``${PH.uploads && PH.uploads.length || true ? ...}``
        —— 恒为真，条件纯属装饰。写成 ``${... || true`` 的人显然在调试时
        临时短路，忘了删。
        """
        src = _read(PANEL)
        self.assertIsNone(
            re.search(r"\|\|\s*true\s*\?", src),
            "面板里有 `|| true ?` 恒真条件（调试残留，分支已失去意义）",
        )


def _strip_line_comments(text: str) -> str:
    """去掉 JS 的整行注释（``// ...``）。

    ⚠️ 这一步是断言可信的前提（2026-10-29 第四次栽在注释上）：
    代码里写着

        // ⚠️ 后端要求 confirm: "EMPTY_RECYCLE"
        confirm: "EMPTY_RECYCLE",

    把赋值那行删掉之后，断言 ``confirm:\\s*"EMPTY_RECYCLE"`` **照样匹配到
    注释**，变异测试显示"测试仍然通过"。注释写得好反而让测试失效 ——
    所以断言前必须先把注释剔除，只在**真实代码**上匹配。
    """
    out = []
    for line in text.split("\n"):
        if line.strip().startswith("//"):
            continue
        out.append(line)
    return "\n".join(out)


def _svc_call_block(service: str) -> str:
    """取出 ``svc("<service>", { ... })`` 调用块（含参数对象），**已去掉注释**。

    用来断言"这个调用**带了哪些字段**"。只查全局有没有 ``confirm:`` 是不够的
    —— 文件里别的服务也传 confirm，断言会恒真（这一轮第三次踩到这个坑）。

    实现：从 ``svc("<service>"`` 开始，按括号配平找到调用结尾。
    找不到就返回空串，让调用方断言失败时信息清晰。
    """
    src = _read(PANEL)
    pos = src.find(f'svc("{service}"')
    if pos < 0:
        return ""
    depth = 0
    end = len(src)
    for i in range(pos, len(src)):
        ch = src[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return _strip_line_comments(src[pos:end])


class AlbumUiTest(unittest.TestCase):
    """相册页/文件页的相册操作必须真的接到后端，且参数正确。

    这一组是 2026-10-29 「UI 挖掘」的直接产物：用户反馈
    「照片好像不能上传，新建相册，添加到共享也没有」。
    查下来后端 59 个服务里，面板只用了 13 个 —— 相册那组几乎全没接：

    * ``add_album``（新建相册）— 没入口
    * ``del_album``（删除相册）— 没入口
    * ``copy_to_album``（把文件收进相册）— 没入口，而这正是"上传照片"的正解
    * ``move_paths``/``copy_paths`` 的 ``dest_category``（跨空间）— 后端支持、
      yaml 声明了，面板从来不传 → 「移到共享」在 UI 上根本做不到
    """

    def test_create_album_uses_type_6(self):
        """新建相册必须传 ``album_type: 6``。

        设备把 6 号当「共享相册」（家庭共建）。服务端默认值 0 在设备上不是
        合法的用户相册类型 —— 传 0 会"建了但哪个分组都看不到"，用户以为失败。
        """
        block = _svc_call_block("add_album")
        self.assertTrue(block, "面板没有调用 add_album（新建相册没接）")
        self.assertRegex(
            block,
            r"album_type:\s*6\b",
            "add_album 没有传 album_type: 6，建出来的相册不会出现在「共享相册」分组",
        )

    def test_delete_album_sends_confirm(self):
        """删除相册必须带 ``confirm: "DELETE_ALBUM"``（后端第一层拦截）。

        后端自本次起要求该字段，不传直接被拒。前端漏传的后果不是"删不掉"，
        而是用户点了删除、看到「删除相册失败」，以为设备不支持 —— 实际是
        两边约定没对齐。
        """
        block = _svc_call_block("del_album")
        self.assertTrue(block, "面板没有调用 del_album（删除相册没接）")
        # 同上：匹配赋值语法，别被注释里的词蒙混
        self.assertRegex(
            block,
            r'confirm:\s*"DELETE_ALBUM"',
            "del_album 没有带 confirm: DELETE_ALBUM，后端会拒绝执行",
        )

    def test_delete_album_asks_user_first(self):
        """删除相册前必须有浏览器确认（防误点）。

        不可逆操作只靠后端 confirm 字段不够：后端那个字段是给"绕过 UI 直接
        调服务"兜底的，UI 自己还得拦一道。用户点「删除相册」手滑的概率远高于
        写错一个自动化。
        """
        src = _read(PANEL)
        start = src.find("async function deleteAlbum(")
        self.assertGreater(start, 0, "找不到 deleteAlbum")
        nxt = re.search(r"\nasync function |\nfunction ", src[start + 1:])
        body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
        self.assertIn("window.confirm", body, "删除相册没有用户确认，一键就没了")

    def test_album_upload_routes_through_copy_to_album(self):
        """相册页「上传照片」必须走 ``copyPathToAlbum``（= ``copy_to_album``）。

        🚨 这条断言**被真机改了两遍**，过程本身就是这个 bug 的完整病历：

        1. 起初断言"必须走 copy_to_album"（理由：相册域上传卡 30104）。
        2. 真机一测：``copy_to_album`` 假成功（code 0 / progress 100 / 相册不变），
           于是断言被**反转**成"不得走"，入口也从 UI 上撤掉了。
        3. 后来拿 ``capture.jsonl`` 的真实报文逐字段对比，发现 ``dest.dirs``
           少了 ``addTime``。补上后真机实测：临时相册 0 张 → 3 秒内 1 张，
           且照片拿到相册域 fileId（281474976755904）。断言再改回来。

        所以这里**不是**在测"某个函数名出现过"，是在测一条被真机验证过的
        路径不被悄悄改掉。
        """
        body = fn_body("albumUploadFiles")
        self.assertIn(
            "copyPathToAlbum", body,
            "上传流程没有把照片收进相册（漏了 copyPathToAlbum）—— "
            "那上传就只到文件空间，用户在相册里永远看不到新照片",
        )
        self.assertNotIn(
            "add_to_album", body,
            "上传流程用了 add_to_album —— 它只认相册域 fileId，"
            "拿文件域 id 去调必被拒 30101",
        )
        # 第二段：``copyPathToAlbum`` 是**重试壳**（设备索引延迟时"找不到源文件"），
        # 真正发请求的是 ``copyPathToAlbumOnce``。断言要顺着链路走，
        # 不能停在壳上 —— 否则壳里换掉实现也测不出来。
        self.assertIn(
            "copyPathToAlbumOnce", fn_body("copyPathToAlbum"),
            "copyPathToAlbum 没有调用单次实现（链路断了）",
        )
        once = fn_body("copyPathToAlbumOnce")
        self.assertIn(
            'svc("copy_to_album"', once,
            "copyPathToAlbumOnce 没有调 copy_to_album（链路断了）",
        )
        self.assertIn("album_category", once, "copy_to_album 没传 album_category")
        self.assertIn("category", once, "copy_to_album 没传 category")

    def test_album_upload_verifies_before_claiming_success(self):
        """收进相册之后必须**回查相册张数**，不能只凭 ``code=0`` 报成功。

        那个假成功留下的最重要一条：``/trans/acrosscopy`` 是异步任务，
        返回 ``code=0`` 只代表"任务被受理"，不代表数据到了。当年就是凭
        code=0 报"已上传 N 张到相册"，而相册一张没变。

        现在用 ``albumPhotoCount`` 数一遍：没变就报失败，并告诉用户照片
        还在「文件」→「_相册导入」。
        """
        body = fn_body("albumUploadFiles")
        self.assertIn(
            "albumPhotoCount", body,
            "上传后没有回查相册张数 —— 假成功会再次变成「已上传到相册」的谎报",
        )
        # ⚠️ 只查字符串存在是不够的（第 6 次恒真断言就栽在这）：
        # 把条件改成 `else if (false)` 让复核永不执行，`albumPhotoCount`
        # 仍然在文件里，断言照样通过。必须断言**真实的分支条件**。
        self.assertRegex(
            body, r"else if \(before !== null\)",
            "复核分支的条件不是 before !== null —— 它可能被改成恒假，"
            "于是复核形同虚设，又回到凭 code=0 报成功",
        )
        self.assertNotRegex(
            body, r"else if \(\s*(?:false|true|0|1)\s*\)",
            "复核分支被写成常量条件（恒真/恒假），要么永远不复核、要么"
            "在拿不到基线时也强行复核",
        )
        self.assertIn(
            "没变化", body,
            "复核失败时没有明确文案（用户不知道该信谁）",
        )

    def test_album_upload_reports_partial_failure(self):
        """上传成功但收不进相册时，必须告诉用户照片在哪。

        两步操作里第二步失败，最容易让用户以为"照片丢了"。实际照片还在
        文件空间里，必须指明位置。
        """
        body = fn_body("albumUploadFiles")
        self.assertIn(
            "_相册导入", body,
            "没有告知暂存目录，用户找不到「上传成功但没进相册」的照片在哪",
        )
        self.assertRegex(
            body, r"failures", "没有记录失败项，用户不知道哪几张没进相册"
        )

    def test_move_copy_sends_dest_category(self):
        """跨空间移动/复制必须传 ``dest_category``。

        后端 ``move_paths`` / ``copy_paths`` 一直支持（``src_category`` /
        ``dst_category``），``services.yaml`` 也声明了 ``dest_category``，
        但面板从来没传过 —— 于是「移到共享」在 UI 上等于不存在。
        """
        src = _read(PANEL)
        # 两个调用点（批量 pickRun + 单行右键）都要传
        count = 0
        for m in re.finditer(r'op === "move" \? "move_paths" : "copy_paths"', src):
            tail = src[m.end(): m.end() + 600]
            self.assertIn(
                "dest_category", tail,
                "move/copy 调用没有传 dest_category —— 跨空间目标会被后端"
                "兜底成源空间，等于只在原空间内操作",
            )
            count += 1
        self.assertGreater(count, 0, "找不到 move/copy 的调用点")

    def test_dest_picker_offers_space_switch(self):
        """目标选择器要能切空间，否则找不到"共享"那个目录树。"""
        src = _read(PANEL)
        self.assertIn(
            'data-act="dest-space"',
            src,
            "目标选择器没有空间切换，用户无法把文件移到「共享」",
        )

    def test_album_detail_gates_editable(self):
        """只有 ``albumType=6`` 的相册才能上传/删除。

        智能分类/人物/地点/场景（1/2/22/23/24）是设备自动生成的：
        删不掉，也塞不进照片。UI 不给按钮，比给了再报错好。
        """
        src = _read(PANEL)
        start = src.find("function renderAlbumDetail(")
        nxt = re.search(r"\nasync function |\nfunction ", src[start + 1:])
        body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
        self.assertIn(
            "=== 6", body, "相册详情页没有按 albumType=6 限制可编辑性"
        )


    def test_album_upload_uses_fixed_space(self):
        """相册上传必须用**固定空间**，不能跟 ``curSpace()``。

        ⚠️ 相册页没有空间概念（相册视图不传 category），而 ``PH.space`` 是
        **文件页**的状态。用户在文件页切到「共享」再进相册，``PH.space``
        仍是 "public"，照片就会被悄悄传到共享空间的暂存目录，而相册页显示
        的相册跟那个空间没关系 —— 用户看到"传成功了但相册里没有"。
        """
        body = fn_body("albumUploadFiles")
        self.assertNotIn(
            "curSpace()", body,
            "相册上传用了 curSpace()，会继承文件页残留的空间状态",
        )
        self.assertRegex(
            body, r'const space\s*=\s*"user"', "相册上传没有固定用 user 空间"
        )

    def test_share_album_type_not_hardcoded_23(self):
        """``albumShareToPerson`` 不能硬编码 ``album_type: 23``。

        ⚠️ 23 是「人物相册」。但调用方给它的是「共享相册」分组里的相册
        （albumType=6），于是发出去的是 `album_id=<6号相册id>` +
        `album_type=23` —— 后端拿这个 id 去 23 号相册里找，必然错位。
        正确做法是从目标相册的数据里取 type。
        """
        body = fn_body("albumShareToPerson")
        self.assertNotRegex(
            body,
            r"album_type:\s*23\b",
            "albumShareToPerson 又把 album_type 硬编码成 23 了",
        )
        self.assertRegex(
            body,
            r"album_type:\s*Number\(",
            "albumShareToPerson 应该用传入的 albumType（Number(albumType || 6)）",
        )


class RecycleUiTest(unittest.TestCase):
    """回收站的**不可逆**操作：入口要有，confirm 也必须传对。

    背景（2026-10-29）：面板原本只有「恢复」，底部还写着一句
    「设备侧不提供彻底删除，想清空请去 App」—— 而后端明明实现了
    ``empty_recycle`` 与 ``permanent_delete_recycle_items``。
    文案与代码事实相反，属于**主动误导**：用户以为做不到，其实是没入口。
    """

    def test_empty_recycle_sends_confirm(self):
        block = _svc_call_block("empty_recycle")
        self.assertTrue(block, "面板没有调用 empty_recycle（清空回收站没接）")
        # ⚠️ 必须匹配**赋值语法** `confirm: "X"`，不能只查块内有没有这个词：
        # 代码里恰好有一句注释 `// ⚠️ 后端要求 confirm: "EMPTY_RECYCLE"`，
        # 于是把赋值删掉后 assertIn 照样通过 —— 变异测试当场抓到（第四次
        # 栽在"注释里的同一个词"上）。这类断言看起来在测行为，实际在测注释。
        self.assertRegex(
            block,
            r'confirm:\s*"EMPTY_RECYCLE"',
            "empty_recycle 没有带 confirm: EMPTY_RECYCLE（注意别被注释蒙混），"
            "schema 层就会拒",
        )

    def test_permanent_delete_sends_confirm(self):
        block = _svc_call_block("permanent_delete_recycle_items")
        self.assertTrue(
            block, "面板没有调用 permanent_delete_recycle_items（永久删除没接）"
        )
        self.assertRegex(
            block,
            r'confirm:\s*"PERMANENT_DELETE"',
            "永久删除没有带 confirm: PERMANENT_DELETE（注意别被注释蒙混），"
            "schema 层就会拒",
        )

    def test_permanent_delete_passes_rids(self):
        """``permanent_delete_recycle_items`` 必须传 rids。

        不传的话后端只能报"没给条目"，用户点了"永久删除选中"却什么都没发生，
        还以为按钮坏了。
        """
        block = _svc_call_block("permanent_delete_recycle_items")
        self.assertIn("rids", block, "永久删除没有传 rids（选了也没用）")

    def test_both_ask_user_first(self):
        """两个不可逆操作都必须有浏览器确认弹窗。"""
        for name in ("emptyRecycle", "purgeRecycleItems"):
            body = fn_body(name)
            self.assertIn(
                "window.confirm", body,
                f"{name} 没有用户确认 —— 一键就把数据永久抹掉",
            )

    def test_panel_no_longer_denies_permanent_delete(self):
        """面板不能再声称"设备侧不提供彻底删除"。

        那句话直接把人劝退，而两个服务一直都在。既要给入口，文案也得改。
        """
        src = _read(PANEL)
        self.assertNotIn(
            "设备侧不提供「彻底删除」",
            src,
            "面板还在说设备不支持彻底删除，但 empty_recycle / "
            "permanent_delete_recycle_items 都实现了",
        )


class MultiAccountServiceTest(unittest.TestCase):
    """相册类服务必须能**按账号路由**，不能固定操作主账号。

    ⚠️ 背景（2026-10-29）：服务层一直只操作主账号（``runtime.client`` 构造时
    ``is_primary=True``），多账号支持此前只做在**视图**里。这在纯服务调用时
    只是"能力不足"，但「相册上传照片」是**视图写 + 服务读**的组合：

        1. 上传走视图 → 按 account 正确进了账号 B
        2. ``copy_to_album`` 走服务 → 主账号 → 找不到刚传进 B 的文件

    结果就是"上传成功但加不进相册"，而文件明明在那儿。所以这几个服务必须
    支持 ``account``。
    """

    #: 需要按账号路由的服务 → 其处理函数名
    ALBUM_SERVICES = {
        "copy_to_album": "_copy_to_album",
        "add_to_album": "_add_to_album",
        "add_album": "_add_album",
        "del_album": "_del_album",
        "share_to_person": "_share_to_person",
        # 2026-10-30 补：这三个处理函数早就用了 _client_for，但**注册 schema
        # 漏了 ACCOUNT_FIELD**，而面板 `accArg()` 又会带上 account
        # → 多账号下点「重命名 / 设为封面 / 移出相册」直接 400。
        "album_rename": "_album_rename",
        "album_set_cover": "_album_set_cover",
        "remove_album_members": "_remove_album_members",
    }

    def _schema_block(self, svc_const: str) -> str:
        src = _read(SERVICES_PY)
        pos = src.find(f"DOMAIN, {svc_const},")
        self.assertGreater(pos, 0, f"找不到注册点 {svc_const}")
        tail = src[pos: pos + 900]
        return _strip_line_comments(tail)

    def test_schema_declares_account(self):
        """schema 必须声明 ``account``，否则服务调用时这个参数会被 voluptuous 丢弃。"""
        consts = {
            "copy_to_album": "SERVICE_COPY_TO_ALBUM",
            "add_to_album": "SERVICE_ADD_TO_ALBUM",
            "add_album": "SERVICE_ADD_ALBUM",
            "del_album": "SERVICE_DEL_ALBUM",
            "share_to_person": "SERVICE_SHARE_TO_PERSON",
        }
        for svc, const in consts.items():
            block = self._schema_block(const)
            self.assertIn(
                "**ACCOUNT_FIELD", block,
                f"{svc} 的 schema 没有 **ACCOUNT_FIELD —— 传了 account 也会被丢掉",
            )

    def test_panel_acc_arg_requires_schema_support(self):
        """面板凡是带 ``...accArg()`` 的调用，对应服务 schema 必须声明 ``account``。

        ⚠️ 2026-10-30 真实事故：``album_rename`` / ``album_set_cover`` /
        ``remove_album_members`` 的处理函数都用了 ``_client_for``（看着完全正确），
        但**注册 schema 里没写 ACCOUNT_FIELD**。而面板 ``accArg()`` 在选了账号时
        一定会带上 ``account`` → voluptuous 判定为未知字段 → 调用直接 400。

        单账号下 ``accArg()`` 返回 ``{}``，所以本地怎么点都正常；多账号一选就坏。
        这类"两边各自都对、拼起来才错"的缺陷，只有把面板调用与服务 schema
        放在一起比对才抓得到。
        """
        panel = PANEL.read_text(encoding="utf-8")
        svc_src = _read(SERVICES_PY)

        # 收集面板里「带 accArg 的 svc 调用」→ 服务名
        offenders: list[str] = []
        checked: set[str] = set()
        for m in re.finditer(r"svc\(([^()]*?)\{(.{0,900}?)\}\)", panel, re.S):
            head, body = m.group(1), m.group(2)
            if "accArg()" not in body:
                continue
            names = re.findall(r'"([a-z_]+)"', head)
            for name in names:
                const = f"SERVICE_{name.upper()}"
                pos = svc_src.find(f"DOMAIN, {const},")
                if pos < 0:
                    continue  # 动态分发或常量名不同，跳过
                checked.add(name)
                # ⚠️ 必须截到本注册块的 endsupports_response，不能用固定长度窗口：
                # 900 字符会跨进**下一个**服务的 schema，而那个恰好有 ACCOUNT_FIELD
                # → 假阴性（变异验证时踩到：删掉 album_rename 的字段，测试仍绿）。
                end = svc_src.find("supports_response", pos)
                self.assertGreater(end, pos, f"{name} 的注册块不完整")
                block = _strip_line_comments(svc_src[pos:end])
                if "**ACCOUNT_FIELD" not in block:
                    offenders.append(name)

        self.assertEqual(
            sorted(set(offenders)), [],
            "这些服务面板会传 account，但 schema 没声明 —— 多账号下必然 400: "
            + ", ".join(sorted(set(offenders))),
        )
        # 防"正则没匹配到任何东西"造成的恒真
        self.assertGreaterEqual(
            len(checked), 3,
            f"只核对到 {len(checked)} 个服务，解析可能失效了",
        )

    def test_handler_uses_client_for(self):
        """处理函数必须用 ``_client_for(runtime, call)``，不能直接 ``runtime.client``。"""
        for svc, fn in self.ALBUM_SERVICES.items():
            body = py_fn_body(fn)
            self.assertIn(
                "_client_for(runtime, call)", body,
                f"{svc} 没有按 account 取 client —— 多账号下会去主账号找文件",
            )
            # ⚠️ 用正则 ``\b`` 而不是 assertNotIn("runtime.client.")：
            # 后者靠结尾的点区分，而 ``client = runtime.client`` 后面紧跟换行，
            # 没有点 —— 漏掉了最危险的那种写法。
            self.assertIsNone(
                re.search(r"runtime\.client\b", body),
                f"{svc} 里还有裸的 runtime.client（固定主账号）",
            )

    def test_client_for_rejects_unknown_account(self):
        """``_client_for`` 传了不认识的账号必须报错，不能 fallback 到主账号。

        fallback 是越权的来源（视图层 ``_client_of`` 已按同一原则修过）。
        """
        src = _read(SERVICES_PY)
        start = src.find("def _client_for(")
        self.assertGreater(start, 0, "找不到 _client_for")
        nxt = re.search(r"\ndef |\nasync def ", src[start + 1:])
        body = src[start: start + 1 + nxt.start()] if nxt else src[start:]
        self.assertIn("raise ValueError", body, "_client_for 不认识账号时必须报错")
        self.assertIn("resolve_account", body, "_client_for 要用 resolve_account 反解别名")
        self.assertIn(
            "if not account", body,
            "_client_for 必须区分「没传 account」与「传了但不认识」："
            "前者用主账号，后者报错",
        )

    def test_panel_sends_account_for_album_services(self):
        """面板调用相册服务时必须带 ``accArg()``。"""
        for svc in ("copy_to_album", "add_album", "del_album", "add_to_album",
                    "share_to_person"):
            block = _svc_call_block(svc)
            self.assertTrue(block, f"面板没有调用 {svc}")
            self.assertIn(
                "accArg()", block,
                f"面板调 {svc} 时没带 accArg() —— 多账号下会操作主账号",
            )


class ReverseEngineeringContractTest(unittest.TestCase):
    """把逆向得到并已真机验证的结论固化成断言。

    逆向档案（`gallery_upload_reverse.md` / `feature_parity.md`）是靠解包
    45MB 的 App 插件 smali 得来的，结论很贵。但如果只写在 markdown 里，
    下一个人改代码时不会去读，改错了也没人知道 —— 所以把关键契约搬进测试。

    每一条都注明依据，避免以后有人"顺手简化"掉。
    """

    def test_gallery_prepare_mirrors_capture(self):
        """相册域 prepareUpload 必须照抓包用 ``files`` + 空 ``path``。

        🚨 这条断言原来写的是**反的**（断言"必须用 ``dataList``"，理由是
        早前从插件反编译得出的结论）。抓包把它推翻了：

            _frida/capture_all_1791417873.jsonl:24953（官方 Windows 客户端）
            POST /gallery/prepareUpload
            {"deviceId":"...","uploadType":1,
             "files":[{"viewPath":...,"srcPath":...,"path":"",   ← 空串
                       "sessionId":"","fileId":0,"fileSize":116316,
                       "orientation":0,"taskId":195}]}

        同一个错误结论也曾套到 filesvc 上（``dataList`` + ``hash``），真机
        固定回 ``code=1101``；改回 ``files`` 后上传才通。所以这里断言的是
        **抓包事实**，而不是反编译推断。
        """
        body = _py_func("upload_stream")
        seg = body[body.find('if service_type == "gallery"'):
                   body.find('prep_path = API_PREPARE_UPLOAD')]
        # 再手动去掉 # 注释行：注释里为了说明"不是 dataList"必然会写出该词，
        # 留着就会让下面的 assertNotIn 恒真/恒假（第 7 次踩这个坑）。
        seg = "\n".join(
            ln for ln in seg.split("\n") if not ln.strip().startswith("#")
        )
        # 断言"发出去的报文键名"，而不是某个中间变量名 ——
        # 2026-10-30 这里因为改掉了中间变量（prep_files → prep_items）而误报。
        whole = "\n".join(
            ln for ln in body.split("\n") if not ln.strip().startswith("#")
        )
        self.assertIn('"files": prep_items', whole,
                      "相册域 prepareUpload 没有用 files 键（抓包证伪 dataList）")
        # 只断言"作为键名"出现：注释/文档里为了说明历史必然会提到 dataList，
        # 裸词断言会被自己的注释坑（本项目已踩过多次）。
        self.assertNotIn('"dataList"', whole, "相册域又用回 dataList 了（抓包证伪）")
        self.assertIn('"path": ""', seg, "相册域的 path 应为空串（官方客户端如此）")
        # 防呆：相册分支必须真的把 items 用出去。曾经写成 prep_items 定义、
        # prep_files 使用 → 调用即 NameError，而这段代码没有调用方，谁都没发现。
        self.assertTrue(seg.count("prep_items") >= 1,
                        "相册域没有构造 prep_items")
    def test_gallery_prepare_has_no_hash_field(self):
        """相册域 prepareUpload **没有** ``hash`` 字段（不需要 MD5）。

        原断言要求"必须用真实 MD5 算 hash"，依据同样是反编译档案。抓包里
        官方客户端的报文里根本没有 ``hash``：``files`` 元素只有
        viewPath/srcPath/path/sessionId/fileId/fileSize/orientation/taskId。

        所以 ``file_bytes`` 对相册域也不再是必需的 —— 那个"必须传某用于算
        MD5"的限制是错误结论带来的。
        """
        body = _py_func("upload_stream")
        seg = body[body.find('if service_type == "gallery"'):
                   body.find('prep_path = API_PREPARE_UPLOAD')]
        # 再手动去掉 # 注释行：注释里为了说明"不是 dataList"必然会写出该词，
        # 留着就会让下面的 assertNotIn 恒真/恒假（第 7 次踩这个坑）。
        seg = "\n".join(
            ln for ln in seg.split("\n") if not ln.strip().startswith("#")
        )
        self.assertNotIn('"hash":', seg, "相册域又加回 hash 字段了（抓包里没有）")
        self.assertNotIn("md5(", seg, "相册域不需要算 MD5")
    def test_upload_headers_do_not_require_file_size(self):
        """File-Size 头**不是必需的**（真机实测）。

        原断言要求必须带 File-Size（依据逆向档案）。2026-10-29 真机验证：
        不带该头，中文名文本 + 165KB PNG 连续 10 次上传全部成功（code 0，
        落盘大小精确）。所以这里断言"不依赖它"，避免后人加回去。

        仍然必需的是 Expect: 100-continue（实测去掉即 500）。
        """
        body = _py_func("upload_stream")
        self.assertNotIn(
            '"File-Size"', body,
            "又加回 File-Size 了 —— 真机不需要它也能传成功",
        )
        self.assertIn(
            '"Expect": "100-continue"', body,
            "Expect: 100-continue 是必需的（实测去掉即 500）",
        )

    def test_upload_headers_keep_expect_100(self):
        """``Expect: 100-continue`` 不能丢 —— 去掉实测直接 500。"""
        src = _read(TRANSFER)
        self.assertIn('"Expect": "100-continue"', src)

    def test_album_write_requests_carry_clienttype_devicid(self):
        """相册域**写**接口的 body 必须带 ``clientType`` / ``deviceId``。

        依据是一次真机对比（2026-10-29）：

            /gallery/addAlbum                 body={albumName,albumType,parentAlbumId} → 30102
            /gallery/modifyAlbumsHiddenStatus body={albumIds,albumType,hidden}         → 30102
            /gallery/addAlbumMemb             body={clientType,deviceId,albumId,...}   → code 0 ✓

        差别就在这两个公共字段：能成的有，报 30102 的都没有。
        （``_request`` 只把这两个放 **query**，相册域写接口显然还要在 body 里看到。）
        """
        for fn in ("async_add_album", "async_hide_albums"):
            start = _read(DEVICE_PY).find(f"async def {fn}(")
            self.assertGreater(start, 0, f"找不到 {fn}")
            src = _read(DEVICE_PY)
            nxt = re.search(r"\n    async def ", src[start + 1:])
            body = src[start: start + 1 + nxt.start()] if nxt else src[start + 5000:]
            body = _strip_py_comments(body)
            self.assertIn('"clientType"', body, f"{fn} 的 body 缺 clientType")
            self.assertIn('"deviceId"', body, f"{fn} 的 body 缺 deviceId")

    def test_hide_albums_uses_hidden_status_field(self):
        """``modifyAlbumsHiddenStatus`` 的字段名必须是 ``hiddenStatus``（整数）。

        🚨 真机实测：这个接口卡了两轮，第 2 轮才是真正的坑：

            {albumIds, albumType, hidden}       → 30102
            + clientType + deviceId             → 仍 30102
            hidden → hiddenStatus (1/0)         → code 0 ✓

        字段名要和**设备自己返回的结构**一致 —— 它返回的相册对象里就叫
        ``hiddenStatus``、值是 0/1。名字对不上就当"必填没给"，而错误响应里
        只有 ``{"code":30102}``，一个字都不多，无法反推。

        所以写接口逆向的最省力路径：先读设备返回的同一对象，照抄字段名。
        """
        src = _read(DEVICE_PY)
        start = src.find("async def async_hide_albums(")
        self.assertGreater(start, 0, "找不到 async_hide_albums")
        nxt = re.search(r"\n    async def ", src[start + 1:])
        body = src[start: start + 1 + nxt.start()] if nxt else src[start + 2000:]
        body = _strip_py_comments(body)
        self.assertIn('"hiddenStatus"', body, "hide_albums 没有用 hiddenStatus 字段")
        self.assertNotIn(
            '"hidden":', body,
            "hide_albums 又用回 hidden 了 —— 设备只认 hiddenStatus(0/1)",
        )

    def test_del_album_sends_album_name(self):
        """``delAlbum`` 的 body 必须含 ``albumName``（真机实测结论）。

        这个接口错误码一路在变，正好标出缺什么：

            原始 {albumId, albumType}          → 30102
            + clientType + deviceId            → 30100
            + albumName                        → code 0 ✓（实测删除成功）

        所以相册域写接口 = 公共字段 + 相册名，缺哪个都会换一个错误码。
        """
        src = _read(DEVICE_PY)
        start = src.find("async def async_del_album(")
        self.assertGreater(start, 0, "找不到 async_del_album")
        nxt = re.search(r"\n    async def ", src[start + 1:])
        body = src[start: start + 1 + nxt.start()] if nxt else src[start + 3000:]
        body = _strip_py_comments(body)
        self.assertIn('"albumName"', body, "del_album 的 body 缺 albumName")
        self.assertIn(
            "_album_name_by_id", body,
            "albumName 应自动按 albumId 反查（与 addAlbumMemb 一致）",
        )

    def test_addtime_uses_wall_clock_not_monotonic(self):
        """``addTime`` 必须是 Unix 毫秒，不能用 ``get_event_loop().time()``。

        后者是**单调时钟**（事件循环启动以来的秒数），乘 1000 只有 ~1e7 量级，
        而真实时间戳是 1.79e12 —— 差 5 个数量级，等于告诉设备"这是 1970 年
        加进来的"。这和之前 ``ctime``/``mtime`` 拿分块偏移当时间戳是同一类
        错误：时序字段拿到了别的量纲。设备照单全收，只有排序会不对。

        ⚠️ 断言只盯 ``addTime`` 这个**时序字段**。`trans/move`、`trans/copy`
        里的 ``"name": str(int(get_event_loop().time() * 1000))`` 是**任务名**
        （唯一标识），没有时间语义，用单调时钟并不会造成"1970 年"问题 ——
        一开始把断言写成全局 assertNotIn，就误伤了那两处。
        """
        src = _strip_py_comments(_read(DEVICE_PY))
        self.assertIsNone(
            re.search(r'"addTime"\s*:\s*int\(\s*asyncio\.get_event_loop', src),
            "还有 addTime 字段在拿单调时钟当毫秒时间戳",
        )
        self.assertIn(
            "_time.time() * 1000", src, "addTime 应该用 _time.time() * 1000"
        )


class ServiceMetadataTest(unittest.TestCase):
    """注册了服务但没写 yaml/翻译 —— 界面上是一坨裸 key。"""

    @classmethod
    def setUpClass(cls):
        cls.registered = {
            n for n in registered_services() if not n.startswith("<UNRESOLVED:")
        }

    def test_every_service_in_yaml(self):
        yaml_names = set(
            re.findall(r"^([a-z_0-9]+):", _read(SERVICES_YAML), re.M)
        )
        missing = sorted(self.registered - yaml_names)
        self.assertEqual(
            missing,
            [],
            f"服务注册了但 services.yaml 没有：HA 不校验参数、"
            f"开发者工具里不显示字段说明：{missing}",
        )

    def test_no_orphan_yaml_entry(self):
        yaml_names = set(
            re.findall(r"^([a-z_0-9]+):", _read(SERVICES_YAML), re.M)
        )
        orphan = sorted(yaml_names - self.registered)
        self.assertEqual(
            orphan,
            [],
            f"services.yaml 里有代码没注册的服务（文档与实现脱节）：{orphan}",
        )

    def test_every_service_translated(self):
        for path, label in ((ZH, "zh-Hans"), (EN, "en")):
            data = json.loads(_read(path))
            svc = (data.get("services") or {})
            missing = sorted(self.registered - set(svc))
            self.assertEqual(
                missing,
                [],
                f"{label}.json 的 services 缺少：{missing}（界面上会显示裸 key）",
            )

    def test_strings_json_matches_translations(self):
        """``strings.json`` 是翻译源，两份 translations 必须是它的超集。"""
        base = json.loads(_read(STRINGS))
        base_svc = set((base.get("services") or {}))
        for path, label in ((ZH, "zh-Hans"), (EN, "en")):
            data = json.loads(_read(path))
            have = set((data.get("services") or {}))
            self.assertTrue(
                base_svc <= have,
                f"{label}.json 缺了 strings.json 里的服务：{sorted(base_svc - have)}",
            )




class CopyToAlbumContractTest(unittest.TestCase):
    """``copy_to_album`` 的报文契约（真机验证过的那一条）。"""

    def test_copy_to_album_sends_add_time(self):
        """``dest.dirs`` 必须带 ``addTime``。

        🚨 这是本仓库最"贵"的一个字段（2026-10-29）。

        缺它的表现：设备返回 ``{"code":0,"data":{"tasks":[{"transId":...}]}}``，
        传输任务 ``taskType=201 progress=100 errorInfo.detail=[]`` —— 一切正常，
        但目标相册一张不多、源空间也没副本。数据被**静默丢弃**。

        依据是真实抓包（``capture.jsonl`` 的 ``/trans/acrosscopy``）：
        ``dest.dirs`` 里带 ``"addTime":1791391599804``；反方向
        （gallery→filesvc）的抓包里它是 ``0`` —— 说明设备做的是**字段存在性**
        校验，值可以为 0。补上后真机立刻见效：临时相册 0 张 → 3 秒内 1 张。

        断言不能只写 ``assertIn("addTime", body)``：那样会被注释里的
        "addTime" 蒙过去（本项目已经栽过 5 次恒真断言）。这里要求它出现在
        **字典赋值语法**里，且不是写死的 0。
        """
        body = _strip_py_comments(py_fn_body("_copy_to_album"))
        self.assertRegex(
            body, r'"addTime"\s*:',
            "copy_to_album 的 dest dirs 没有 addTime —— 任务会假成功，"
            "用户看到「已加入相册」但相册里什么都没有",
        )
        self.assertNotRegex(
            body, r'"addTime"\s*:\s*0\s*,',
            "addTime 写死成 0 虽然能过校验，但设备侧会按 1970 排序；"
            "这里应该给真实时间戳",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
