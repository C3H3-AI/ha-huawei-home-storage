#!/usr/bin/env python3
"""发布工作流的回归测试。

**为什么要这些测试**：`.github/workflows/release.yml` 里的防御措施全都是
真实事故换来的，而它们**出错时不会报错** —— 比如 Release 静默绑成
`untagged-<hash>`，草稿照建、ZIP 照传、日志三行全对，只有 HACS 用户收不到更新。
没有测试的话，下一个人"顺手清理一下"就可能把 `--verify-tag` 删掉而无人察觉。

**运行**：
    python3 -m unittest _tools.test_release_workflow -v
    或  python3 _tools/test_release_workflow.py

**注意断言范围**：工作流里有多处**注释**提到 `--target`、`untagged-`、
`html_url`、`/releases/tags/`（因为要解释为什么不能那么写）。
如果直接对整份文件做子串断言，断言会**恒为真**、永远抓不到回归
（写这套测试时就踩过这个坑）。所以下面统一先取「去掉注释后的代码」再断言。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
VALIDATE = REPO_ROOT / ".github" / "workflows" / "validate.yml"
RELEASE_YML = REPO_ROOT / ".github" / "release.yml"

# 仓库里真实存在的 label（GitHub 默认集）。release.yml 只允许引用这些。
KNOWN_LABELS = {
    "accessibility",
    "bug",
    "documentation",
    "duplicate",
    "enhancement",
    "good first issue",
    "help wanted",
    "invalid",
    "question",
    "wontfix",
    "skip-changelog",  # 本仓库新增的排除用 label（可为不存在，仅用于 exclude）
}


def _load_yaml(path: Path):
    """解析 YAML；缺 PyYAML 时给出清楚的指引。"""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        raise unittest.SkipTest("需要 PyYAML：pip install pyyaml") from None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    wf = _load_yaml(WORKFLOW)
    return wf["jobs"]["build-and-draft"]["steps"]


def _step(name_fragment: str) -> dict:
    for step in _steps():
        if name_fragment.lower() in (step.get("name") or "").lower():
            return step
    raise AssertionError(f"找不到步骤：{name_fragment}")


def strip_comments(code: str) -> str:
    """去掉**整行**注释。

    工作流里所有 `#` 注释都是独立成行的，逐行判断即可；这样既能剥掉
    「解释为什么不能用 X」的注释，又不会误伤 shell 单引号里的内容。
    """
    out = []
    for line in code.splitlines():
        if line.strip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def release_create_cmd() -> str:
    """只取 `gh release create` 这条命令（含 `\\` 续行），不含任何注释。

    这正是本仓库踩过的陷阱形态：注释里也出现过 `gh release create
    --generate-notes`，如果按子串定位会取到注释、断言随之失效。
    """
    code = strip_comments(_step("Create draft release")["run"])
    lines = code.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("gh release create"):
            segment = [line]
            for nxt in lines[idx + 1:]:
                if segment[-1].rstrip().endswith("\\"):
                    segment.append(nxt)
                else:
                    break
            return "\n".join(segment)
    raise AssertionError("找不到 `gh release create` 命令行")


class TestReleaseWorkflow(unittest.TestCase):
    """防的是「不报错的坏」—— 每条都对应一次真实事故。"""

    def test_workflow_and_release_yml_parse(self):
        """两个 YAML 必须能解析（缩进错 / heredoc 顶格会直接 ScannerError）。"""
        self.assertIn("jobs", _load_yaml(WORKFLOW))
        self.assertIn("changelog", _load_yaml(RELEASE_YML))

    def test_release_command_never_uses_target(self):
        """★ 坑 3：带了 --target，tag 已建好也照样可能绑成 untagged-<hash>。"""
        cmd = release_create_cmd()

        self.assertNotIn("--target", cmd)

    def test_release_command_verifies_tag(self):
        """★ tag 远程不可见时必须**直接失败**，而不是静默建出坏草稿。"""
        cmd = release_create_cmd()

        self.assertIn("--verify-tag", cmd)

    def test_release_uses_existing_tag_without_creating(self):
        """Release 只引用 tag，不应自己做 tag 创建（--target 就是干这个的）。"""
        cmd = release_create_cmd()

        self.assertIn("--draft", cmd)
        self.assertNotIn("--target", cmd)

    def test_tag_created_before_release(self):
        """★ 坑 2：草稿 Release 不会自动建 tag，必须先显式创建并推送。"""
        names = [s.get("name") or "" for s in _steps()]
        tag_idx = next(i for i, n in enumerate(names) if "push tag" in n)
        rel_idx = next(i for i, n in enumerate(names) if "draft release" in n)

        self.assertLess(tag_idx, rel_idx, "建 tag 的步骤必须排在建 Release 之前")

    def test_tag_step_actually_pushes(self):
        """只 `git tag` 不 push，远程就没有 tag —— 等于没建。"""
        code = strip_comments(_step("Create and push tag")["run"])

        self.assertIn("git tag", code)
        self.assertIn("git push origin", code)

    def test_binding_check_uses_list_endpoint(self):
        """★ 草稿不能用 /releases/tags/{tag} 查 —— 那个接口对草稿返回 404。"""
        code = strip_comments(_step("Verify release bound")["run"])

        self.assertIn("/releases?per_page=", code)
        self.assertNotIn("/releases/tags/", code)

    def test_binding_check_retries(self):
        """★ GET /releases 是最终一致性的（实测 3 次丢 1 次），必须重试。"""
        code = strip_comments(_step("Verify release bound")["run"])

        m = re.search(r"for _ in ([0-9 ]+); do", code)
        self.assertIsNotNone(m, "找不到重试循环")
        attempts = [int(x) for x in m.group(1).split()]
        self.assertGreaterEqual(
            len(attempts), 3, f"重试次数过少（{attempts}），最终一致性会漏判"
        )

    def test_binding_judged_by_tag_name_not_html_url(self):
        """★ 判据只能是 tag_name：健康草稿的 html_url 也是 untagged- 占位符。"""
        code = strip_comments(_step("Verify release bound")["run"])

        self.assertIn("tag_name", code)
        self.assertNotIn("html_url", code)

    def test_unbound_draft_matched_by_untagged_prefix(self):
        """★ 找未绑定草稿要认 untagged- 前缀，版本号前缀会误匹配 v1.2.40。"""
        code = strip_comments(_step("Verify release bound")["run"])

        self.assertIn('startswith("untagged-")', code)
        # 反例：用版本号前缀匹配
        self.assertNotRegex(code, r"startswith\(\"v\$\{TAG\}")

    def test_binding_failure_is_fatal(self):
        """修复不了就必须 exit 1 —— 否则 workflow 变绿，没人知道 HACS 收不到更新。"""
        code = strip_comments(_step("Verify release bound")["run"])

        self.assertGreaterEqual(code.count("exit 1"), 2)

    def test_tag_existence_check_uses_ls_remote(self):
        """校验 tag 要用远程真相（ls-remote），不是本地有没有打。"""
        code = strip_comments(_step("Verify tag exists")["run"])

        self.assertIn("ls-remote", code)
        self.assertIn("exit 1", code)

    # ── 坑 1：heredoc 顶格 → YAML ScannerError ────────────────────────────
    def test_no_heredoc_in_run_blocks(self):
        """run 块内不允许 heredoc：内部顶格代码会被 YAML 当成新的 key。"""
        for step in _steps():
            code = step.get("run")
            if not code:
                continue
            self.assertNotRegex(
                code,
                r"<<-?\s*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?",
                f"步骤「{step.get('name')}」含 heredoc，会让 YAML 解析失败",
            )

    # ── 版本比较 ──────────────────────────────────────────────────────────
    def test_version_compare_uses_packaging(self):
        """版本比较必须语义化（0.10.0 > 0.9.1；字符串比较会得出相反结论）。"""
        code = strip_comments(_step("Version increment check")["run"])

        self.assertIn("packaging", code)
        self.assertIn("version.parse", code)

    def test_manifest_path_exists(self):
        """工作流里写死的组件路径必须真实存在（改名后不能静默失效）。"""
        wf = _load_yaml(WORKFLOW)
        component = wf["env"]["COMPONENT"]
        manifest = wf["env"]["MANIFEST"]

        self.assertTrue(
            (REPO_ROOT / "custom_components" / component).is_dir(),
            f"custom_components/{component} 不存在",
        )
        self.assertTrue((REPO_ROOT / manifest).is_file(), f"{manifest} 不存在")

    def test_trigger_path_matches_manifest(self):
        """触发路径必须与真正的 manifest 位置一致，否则工作流永不触发。"""
        wf = _load_yaml(WORKFLOW)
        paths = wf[True]["push"]["paths"] if True in wf else wf["on"]["push"]["paths"]

        self.assertEqual(paths, [wf["env"]["MANIFEST"]])

    def test_prerelease_detection(self):
        """beta / rc / alpha 要标成 prerelease，否则会被当成稳定版推给用户。"""
        code = strip_comments(_step("Version increment check")["run"])

        self.assertRegex(code, r"beta\|rc\|alpha")
        self.assertIn("is_prerelease", code)


class TestReleaseYmlCategories(unittest.TestCase):
    """changelog 分类配置。"""

    def _config(self) -> dict:
        return _load_yaml(RELEASE_YML)["changelog"]

    def test_wildcard_fallback_is_last(self):
        """★ 兜底 `*` 必须最后 —— GitHub 按顺序匹配，放前面会吞掉全部分类。"""
        cats = self._config()["categories"]

        self.assertIn("*", cats[-1]["labels"], "`*` 兜底必须是最后一个分类")

    def test_no_wildcard_outside_last(self):
        for cat in self._config()["categories"][:-1]:
            self.assertNotIn("*", cat["labels"])

    def test_categories_use_real_labels(self):
        """★ 用了不存在的 label，那些 PR 会全掉进兜底，分类等于没做。"""
        for cat in self._config()["categories"]:
            for label in cat["labels"]:
                if label == "*":
                    continue
                self.assertIn(
                    label, KNOWN_LABELS, f"分类「{cat['title']}」引用了不存在的 label: {label}"
                )

    def test_every_category_has_title_and_labels(self):
        for cat in self._config()["categories"]:
            self.assertTrue(cat.get("title"))
            self.assertTrue(cat.get("labels"))

    def test_ci_actually_runs_these_tests(self):
        """★ 测试不跑等于没有。validate.yml 必须有一步执行本套件。

        没有这条断言时，把 CI 里的运行步骤删掉，整套测试就静默失效了
        —— 而它守的恰恰是「不报错」的那类缺陷。
        """
        validate = REPO_ROOT / ".github" / "workflows" / "validate.yml"
        wf = _load_yaml(validate)
        runs = [
            step.get("run", "")
            for job in wf["jobs"].values()
            for step in job.get("steps", [])
        ]
        joined = "\n".join(runs)

        self.assertIn("_tools.test_release_workflow", joined, "CI 没有运行本测试套件")
        self.assertIn("unittest", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
