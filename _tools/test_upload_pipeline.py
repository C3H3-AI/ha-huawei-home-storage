#!/usr/bin/env python3
"""上传链路的功能性回归测试（含真实行为断言，不只是文本）。

**为什么单独一套**：上传是本集成里唯一「用户直接感知、失败率高、且出错后
很难自查」的写操作。它的三个实现（``transfer.upload_stream`` /
``api.device.async_upload_file`` / 面板 XHR）各自独立写过一遍，容易出现
「一处修了、另一处忘」——下面这些缺陷正是这么产生的：

* 文件名没做百分号编码 → 中文文件名上传直接抛 ``UnicodeEncodeError``；
* ``ctime``/``mtime`` 传了分块偏移 → 上传后的文件时间戳是 1970 年；
* 面板上传 URL 漏传 ``account`` → 多账号下文件落进别人的账号。

**运行**::

    python3 _tools/test_upload_pipeline.py
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "huawei_home_storage"
TRANSFER = COMPONENT / "transfer.py"
DEVICE = COMPONENT / "api" / "device.py"
PANEL = COMPONENT / "www" / "huawei-storage-panel.js"
VIEWS = COMPONENT / "views.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_source(path: Path, name: str) -> str:
    """取某个函数的源码（支持 async / 嵌套定义外的顶层函数）。"""
    src = _read(path)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{path.name} 里找不到函数 {name}")


class FilenameEncodingTest(unittest.TestCase):
    """``Content-Disposition`` 的文件名必须百分号编码。

    HTTP/1.1 的 header 是 latin-1；直接塞中文，aiohttp 会在**发送前**抛
    ``UnicodeEncodeError``（用户看到的是与文件名毫无关系的堆栈）。
    """

    #: 两处上传实现都必须编码 —— 它们是独立写的两份报文
    IMPLS = [
        ("transfer.py::upload_stream(内层 _send)", TRANSFER, "upload_stream"),
        ("api/device.py::async_upload_file", DEVICE, "async_upload_file"),
    ]

    def test_both_implementations_encode_filename(self):
        problems = []
        for label, path, func in self.IMPLS:
            src = _func_source(path, func)
            line = [
                ln for ln in src.splitlines() if "Content-Disposition" in ln
            ]
            self.assertTrue(line, f"{label} 里找不到 Content-Disposition")
            joined = " ".join(line)
            # 必须出现某种编码调用（quote / quote_from_bytes 等）
            if not re.search(r"quote", joined):
                problems.append(f"{label}: {line[0].strip()}")
        self.assertEqual(
            problems, [],
            "这些上传实现没给文件名做百分号编码（中文名会失败）: "
            + "; ".join(problems),
        )

    def test_chinese_filename_would_break_without_encoding(self):
        """证明「不编码真的会炸」—— 这是缺陷的存在性证明，不是文本断言。"""
        name = "测试照片.jpg"
        header_bad = f'attachment;filename="{name}"'
        with self.assertRaises(UnicodeEncodeError):
            # header 值按 latin-1 编码（HTTP 的实际要求）
            header_bad.encode("latin-1")

        header_ok = f'attachment;filename="{quote(name)}"'
        self.assertEqual(header_ok.encode("latin-1").decode("latin-1"), header_ok)

    def test_quote_is_imported(self):
        src = _read(TRANSFER)
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "urllib.parse":
                for a in node.names:
                    imported.add(a.asname or a.name)
        self.assertTrue(
            any("quote" in n for n in imported),
            f"transfer.py 用了 quote 但没导入（实际导入: {imported}）",
        )


class TimestampTest(unittest.TestCase):
    """``ctime``/``mtime`` 必须是**文件时间戳**，不能是分块偏移。"""

    def test_query_uses_timestamp_not_offset(self):
        src = _func_source(TRANSFER, "upload_stream")
        # 取出 query 字典里 ctime / mtime 的取值表达式
        bad = []
        for key in ("ctime", "mtime"):
            m = re.search(rf'"{key}":\s*([^,\n]+)', src)
            self.assertIsNotNone(m, f"transfer.py 缺少 {key} 参数")
            expr = m.group(1).strip()
            # ``str(start)`` / ``start`` 都是错的（start = 分块起始偏移）
            if re.fullmatch(r"str\(\s*start\s*\)", expr) or expr == "start":
                bad.append(f"{key}={expr}")
        self.assertEqual(
            bad, [],
            f"ctime/mtime 用了分块偏移（会让上传的文件时间是 1970 年）: {bad}",
        )

    def test_accepts_caller_mtime(self):
        """备份恢复要保留原始时间 —— 必须能从外部传入。"""
        src = _func_source(TRANSFER, "upload_stream")
        # 签名里应有 mtime_ms 参数
        sig_end = src.index(")", src.index("def upload_stream"))
        sig = src[:sig_end]
        self.assertIn("mtime_ms", sig, "upload_stream 不接受 mtime_ms，备份恢复无法保留时间")
        # 且确实被用到
        self.assertRegex(src, r"mtime_ms\s+if\s+mtime_ms\s+is\s+not\s+None")

    def test_offset_still_used_in_content_range(self):
        """偏移量该去的地方是 ``Content-Range`` —— 别把两者一起删了。"""
        src = _func_source(TRANSFER, "upload_stream")
        m = re.search(r'"Content-Range":\s*([^\n]+)', src)
        self.assertIsNotNone(m, "找不到 Content-Range 头")
        self.assertIn("start", m.group(1), "Content-Range 必须仍带分块起始偏移")
        self.assertIn("end", m.group(1))
        self.assertIn("total_size", m.group(1))


class PanelAccountTest(unittest.TestCase):
    """面板的**写操作**必须带 ``account``，否则多账号下会写错地方。"""

    @staticmethod
    def _upload_url_exprs() -> list[tuple[str, int]]:
        """找出面板里**所有**构造上传 URL 的表达式，返回 ``(表达式, 起始位置)``。

        ⚠️ 不按函数名定位（2026-10-29 改）：这个 URL 原本写在 ``doUpload``
        里，后来为了复用（照片上传要"传完再 copy_to_album"）抽到了
        ``uploadRaw``，按 ``doUpload`` 找的测试立刻误报 —— 而代码本身是对的。
        真正的风险是"某处上传漏了 account"，所以扫全文件的赋值点：
        有几个上传入口就要检查几个，新增第三个时也不会漏。

        带上起始位置是给 ``test_upload_url_account_var_is_defined`` 用的 ——
        它要据此定位**该表达式所在的函数**，不能用一个固定宽度的窗口。
        """
        src = _read(PANEL)
        out: list[tuple[str, int]] = []
        for m in re.finditer(r"const url\s*=\s*(.+?);\s*\n", src, re.DOTALL):
            expr = m.group(1)
            if "/upload/" in expr:
                out.append((expr, m.start()))
        return out

    def test_upload_url_appends_account_variable(self):
        """``acc`` 必须真的拼到 URL 上。

        ⚠️ 这里不能只断言 ``"account=" in body``：``const acc = "...&account=..."``
        那**一行定义**本身就含 ``account=``，即使忘了把它拼进 URL 断言也恒为真
        （写这套测试时踩过：还原缺陷后仍然"通过"）。
        要断言的是 URL 表达式里出现了 ``${acc}``。
        """
        pairs = self._upload_url_exprs()
        self.assertTrue(pairs, "找不到任何上传 URL 构造点（抽取逻辑坏了）")
        for expr, _pos in pairs:
            self.assertIn(
                "${acc}", expr,
                "url 没有拼接 ${acc} —— 多账号下上传会落进「可见的第一个账号」。"
                f"实际表达式：\n{expr}",
            )

    def test_upload_url_account_var_is_defined(self):
        """``acc`` 必须定义在**本函数**里，否则模板渲染成 ``undefined``。

        只断言 ``${acc}`` 不够：把 ``const acc = ...`` 删掉，``${acc}`` 依然
        存在，只是渲染成字符串 ``"undefined"``，URL 变成
        ``&account=undefined`` —— 后端查不到该账号直接 400，但错误信息与
        真正成因（变量没定义）无关，极难定位。

        ⚠️ 也**不能**用"文件里存在 ``const acc``"来判定（2026-10-29 再修）：
        全文件共有 4 处 ``const acc = SEL.account ? ...``（两个读接口用
        ``?account=``，两个写操作用 ``&account=``），删掉 uploadRaw 那处
        之后，断言去隔壁函数捞到一个照样通过 —— 变异测试当场抓到
        （删掉定义，测试仍然 OK，等于没测）。必须绑定到本函数作用域。
        """
        src = _read(PANEL)
        pairs = self._upload_url_exprs()
        self.assertTrue(pairs, "找不到上传 URL 构造点")
        for _expr, pos in pairs:
            fstart = max(
                src.rfind("\nasync function ", 0, pos),
                src.rfind("\nfunction ", 0, pos),
            )
            self.assertGreater(fstart, 0, "找不到上传函数起点")
            body = src[fstart:pos]
            self.assertRegex(
                body,
                r"const acc\s*=\s*SEL\.account\s*\?\s*`&account=",
                "本函数里没有 `const acc = SEL.account ? ...&account=...` 定义。"
                "注意要匹配 ``&account=``（写操作用 & 追加查询参数），"
                "不是读接口的 ``?account=``",
            )

    def test_read_views_also_carry_account(self):
        """对照：读接口都带了，说明写接口漏传是疏忽而非有意。"""
        src = _read(PANEL)
        idx = src.find("/api/huawei_home_storage/files/")
        self.assertGreater(idx, 0, "面板里找不到 files 读接口")
        window = src[max(0, idx - 800): idx + 200]
        self.assertIn("account", window, "files 读接口没有带 account（与上传对照）")


class UploadSurfaceTest(unittest.TestCase):
    """上传的两种用户路径都要存在且可用（面板 + 服务）。"""

    def test_panel_view_registered(self):
        src = _read(VIEWS)
        self.assertIn("HuaweiStorageUploadView()", src, "上传视图没注册")
        self.assertIn("class HuaweiStorageUploadView", src)

    def test_upload_view_requires_content_length(self):
        """设备侧 prepareUpload 要声明大小，没有 Content-Length 必须早失败。"""
        src = _func_source(VIEWS, "post")
        # 该函数在 UploadView 类里；上面按名字抓到的是第一个 post，
        # 所以这里直接对整份视图源码断言更稳。
        full = _read(VIEWS)
        self.assertIn("缺少 Content-Length", full)
        self.assertIn("status=411", full, "缺 Content-Length 应返回 411 Length Required")

    def test_upload_view_checks_account(self):
        src = _read(VIEWS)
        start = src.index("class HuaweiStorageUploadView")
        nxt = src.find("\ndef async_register_views", start)
        body = src[start:nxt if nxt > 0 else len(src)]
        self.assertIn("_gate_account", body, "上传视图没有账号隔离（写操作越权）")

    def test_service_upload_restricts_local_path(self):
        """``upload_file`` 服务只允许读 uploads 目录，防读到 secrets.yaml。"""
        src = _read(COMPONENT / "services.py")
        start = src.index("async def _upload_file(")
        nxt = src.find("async def _download_file(", start)
        body = src[start:nxt]
        self.assertIn("_allowed_upload_dir", body)
        self.assertIn("realpath", body, "没有做路径归一化，可用 ../ 绕过")
        self.assertIn("MAX_UPLOAD_BYTES", body)

    def test_stream_verifies_byte_count(self):
        """声明大小与实发不一致必须失败（否则残缺文件被当成成功）。"""
        src = _func_source(TRANSFER, "upload_stream")
        self.assertIn("sent != total_size", src)
        self.assertIn("文件不完整", src)

    def test_stream_rejects_invalid_size(self):
        src = _func_source(TRANSFER, "upload_stream")
        self.assertIn("total_size is None or total_size <= 0", src)

    def test_upload_view_uses_safe_parent_helper(self):
        """上传视图不能自己手拼父目录。

        ⚠️ 原来写的是 ``dest.rstrip("/").rsplit("/", 1)[0] + "/"``：
        当 ``dest`` 没有斜杠（``"photo.jpg"``，服务/自动化里手写 path
        很容易漏前导斜杠）时，父目录被算成 ``"photo.jpg/"`` —— 我们会去
        设备上建一个**与目标文件同名**的目录，真正的写入随后撞在这个目录上，
        报「目录不可用」，与真实成因（路径缺斜杠）完全无关。
        """
        src = _read(VIEWS)
        start = src.index("class HuaweiStorageUploadView")
        nxt = src.find("\ndef async_register_views", start)
        body = src[start:nxt if nxt > 0 else len(src)]
        self.assertIn("_parent_dir_of", body, "上传视图应使用统一的父目录计算助手")
        self.assertNotIn(
            'rsplit("/", 1)[0]',
            body,
            "上传视图里还有手拼父目录的代码，边界情况会算错",
        )

    def test_parent_dir_helper_boundaries(self):
        """``_parent_dir_of`` 对边界输入给出可预期的结果。"""
        src = _read(VIEWS)
        start = src.index("def _parent_dir_of")
        nxt = src.find("\ndef ", start + 10)
        ns: dict = {}
        # 只执行这个纯函数（不 import HA）
        exec(compile(src[start:nxt], VIEWS, "exec"), ns)  # noqa: S102
        fn = ns["_parent_dir_of"]
        self.assertEqual(fn("/file/a.jpg"), "/file/")
        self.assertEqual(fn("/file/a/b.jpg"), "/file/a/")
        self.assertEqual(fn("/a.jpg"), "/")
        self.assertEqual(fn("a.jpg"), "/", "无斜杠必须落到根目录，不能算成 'a.jpg/'")
        self.assertEqual(fn(""), "/")
        self.assertEqual(fn("/file/"), "/")


class GalleryUploadStatusTest(unittest.TestCase):
    """相册域上传的**真实状态**必须被代码如实记录。

    ⚠️ 这条测试自己错过一次，值得记下来：它原来断言"注释里必须写着卡在
    ``30104``、没跑通"，把那次的**错误结论**钉成了事实。2026-10-30 用 PC
    客户端完整抓包证明该结论是错的 —— 设备支持，是我们三处实现有错：

    1. 报文模型照插件反编译写成 ``dataList`` + ``hash``（实际是 ``files``）；
    2. 相册分支定义 ``prep_items`` 却用 ``prep_files`` 发请求 → 调用即
       ``NameError``，且没有调用方，所以从未被执行；
    3. ``mediaType`` 恒为 ``0``，照片被当成普通文件，相册收不进去。

    教训：**测试要锁"实现是否符合抓包事实"，不要锁"上一轮的结论"**。
    结论会被推翻，把结论写进断言就等于把错误固化下来。
    """

    def test_transfer_documents_gallery_correctly(self):
        src = _read(TRANSFER)
        idx = src.index("service_type")
        window = src[idx: idx + 3000]
        # 必须说明"可用"，且说清当年为什么误判（否则下一个人又会照反编译改回去）
        self.assertTrue("可用" in window, "没有记录 gallery 域的真实状态（可用）")
        self.assertIn("prep_items", window, "没有记录 prep_items/prep_files 那个笔误")
        self.assertIn("mediaType", window, "没有记录 mediaType 必须按类型传")

    def test_gallery_upload_has_no_caller(self):
        """当前不该有调用方 —— 有了就意味着有人接了个跑不通的功能。"""
        callers = []
        for path in COMPONENT.rglob("*.py"):
            if path.name == "transfer.py":
                continue
            text = _read(path)
            if re.search(r'service_type\s*=\s*["\']gallery["\']', text):
                callers.append(path.name)
        self.assertEqual(
            callers, [],
            f"这些文件在调用未跑通的 gallery 域上传: {callers}",
        )

    def test_device_py_does_not_claim_filesvc_fileid_is_gallery(self):
        """``device.py`` 曾写「filesvc 的 fileId 就是相册域的」—— 与实据相反。"""
        src = _read(DEVICE)
        # 找出提到 fileId 域归属的注释行
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            if "相册域" in stripped and "fileId" in stripped:
                # 允许的形式是「**不是**相册域」「相册域（281…）」这种澄清
                self.assertFalse(
                    re.search(r"就是相册域的\s*fileId", stripped),
                    f"device.py 仍有错误注释: {stripped}",
                )

    def test_const_documents_30101(self):
        """const.py 必须记录「文件域 fileId 加相册会被 30101 拒」。"""
        src = _read(COMPONENT / "const.py")
        idx = src.find("API_GALLERY_PREPARE_UPLOAD")
        self.assertGreater(idx, 0)
        window = src[max(0, idx - 600): idx + 600]
        self.assertIn("30101", window)


class FilenameSanitizeTest(unittest.TestCase):
    """文件名里的特殊字符不能破坏 header 或路径。"""

    def test_quote_escapes_quote_and_newline(self):
        """文件名带 ``"`` 或换行会注入/断裂 header。"""
        for evil in ['a"b.jpg', "a\nb.jpg", "a\rb.jpg", "a;b.jpg"]:
            quoted = quote(evil)
            for ch in ('"', "\n", "\r", ";", " "):
                self.assertNotIn(ch, quoted,
                                 f"{evil!r} 编码后仍含 {ch!r}: {quoted}")

    def test_chinese_and_space_are_encoded(self):
        quoted = quote("我的 照片.jpg")
        self.assertNotIn(" ", quoted)
        self.assertTrue(all(ord(c) < 128 for c in quoted),
                        "编码后必须全 ASCII")


if __name__ == "__main__":
    unittest.main(verbosity=2)
