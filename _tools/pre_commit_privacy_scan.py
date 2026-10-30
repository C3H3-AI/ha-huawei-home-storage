#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前隐私扫描：拦住手机号、设备/硬盘序列号、内网 IP、凭据、GitHub token。

安装（在本仓库根目录执行一次）：
    python _tools/install_hooks.py

本脚本被安装为**两个**钩子，因为二者职责不同：
  * ``pre-commit`` —— 扫暂存区文件内容
  * ``commit-msg`` —— 扫提交信息（git 参数为消息文件路径）

⚠️ 为什么必须分两个钩子：git 的执行顺序是
``pre-commit`` → 生成 COMMIT_EDITMSG → ``prepare-commit-msg`` → ``commit-msg``。
在 ``pre-commit`` 阶段 COMMIT_EDITMSG 里**还是上一次的提交信息**，
所以本次的提交信息只能靠 ``commit-msg`` 检查。
（本次事故中提交信息也泄了手机号，这条路径不能漏。）

跳过（仅在确认无误时）：
    git commit --no-verify

为什么存在：2026-10-06 发现手机号、设备序列号、硬盘 SN、账号密码被写进
公开仓库（含提交信息与 PR 正文），本钩子用于防止复发。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# ---- 硬规则：这些形态一律拦截 ------------------------------------------------
RULES = [
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("华为设备序列号", re.compile(r"(?<![A-Za-z0-9])A4DEQ[A-Z0-9]{11}(?![A-Za-z0-9])")),
    ("西数硬盘序列号", re.compile(r"(?<![A-Za-z0-9])WD-WX[A-Z0-9]{10}(?![A-Za-z0-9])")),
    ("GitHub token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}")),
    ("GitHub 细粒度 token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("SSH 私钥", re.compile(r"BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY")),
    ("URL 内嵌凭据", re.compile(r"https?://[^/\s:@]+:[^/\s@]+@")),
    ("华为 JWT", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")),
]

# ---- 私有地址：报但默认可放行（本仓库确实需要示例内网 IP）--------------------
PRIVATE_IP = re.compile(
    r"(?<![\d.])(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])"
)

# 允许出现的占位/示例值（命中这些不算问题）
ALLOW = re.compile(
    r"1380013800\d|SN-EXAMPLE-\d+|WD-EXAMPLE-\d+|192\.168\.1\.100|"
    r"192\.168\.1\.101|YOUR_PASSWORD_HERE|example\.(?:com|org)|"
    r"127\.0\.0\.1|0\.0\.0\.0"
)

# 只看这些文件类型（避免扫二进制/锁文件）
EXTS = (".py", ".json", ".md", ".yaml", ".yml", ".sh", ".ps1", ".txt", ".cfg",
        ".ini", ".toml", ".js", ".ts", ".html")


def run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def staged_files() -> list[str]:
    out = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [f for f in out.splitlines() if f.strip()]


def staged_hunks(path: str) -> str:
    """只取本次新增的行（+），避免因历史遗留问题挡住正常提交。"""
    out = run(["git", "diff", "--cached", "-U0", "--", path])
    return "\n".join(l[1:] for l in out.splitlines()
                     if l.startswith("+") and not l.startswith("+++"))


def main() -> int:
    # git 传给 commit-msg 钩子的参数是「消息文件路径」；pre-commit 无参数。
    msg_path = sys.argv[1] if len(sys.argv) > 1 else None
    is_msg_hook = bool(msg_path)

    problems: list[tuple[str, str, str, str]] = []
    private: list[tuple[str, str, str]] = []

    # ---- 1) 提交信息（commit-msg 钩子）----
    if is_msg_hook:
        try:
            with open(msg_path, encoding="utf-8", errors="replace") as fh:
                msg = fh.read()
        except OSError:
            msg = ""
        for lineno, line in enumerate(msg.splitlines(), 1):
            if ALLOW.search(line):
                continue
            for name, rx in RULES:
                for m in rx.finditer(line):
                    problems.append((f"(提交信息:{lineno})", name, m.group(0), line.strip()[:90]))

    # ---- 2) 暂存文件内容（pre-commit 钩子）----
    if not is_msg_hook:
        files = staged_files()
        for f in files:
            if not f.endswith(EXTS):
                continue
            for line in staged_hunks(f).splitlines():
                if ALLOW.search(line):
                    continue
                for name, rx in RULES:
                    for m in rx.finditer(line):
                        problems.append((f, name, m.group(0), line.strip()[:90]))
                for m in PRIVATE_IP.finditer(line):
                    private.append((f, m.group(0), line.strip()[:90]))

    if private:
        print("⚠️  检测到内网 IP（不阻断，请确认是示例值）：")
        seen = set()
        for f, ip, _ in private:
            if (f, ip) in seen:
                continue
            seen.add((f, ip))
            print(f"     {f}: {ip}")
        print()

    if problems:
        label = "提交信息" if is_msg_hook else "暂存区文件"
        print("=" * 68)
        print(f"❌ 隐私扫描未通过（{label}）—— 提交已阻止")
        print("=" * 68)
        for f, name, val, ctx in problems:
            shown = val if len(val) <= 12 else val[:6] + "…" + val[-4:]
            print(f"  [{name}] {f}")
            print(f"       命中: {shown}")
            if ctx:
                print(f"       行  : {ctx}")
        print()
        print("处理方式：把真实值换成占位符（如 SN-EXAMPLE-0001 / 13800138000），")
        print("或改用环境变量读取。确需跳过：git commit --no-verify")
        return 1

    print("✅ 隐私扫描通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())