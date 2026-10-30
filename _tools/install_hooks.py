#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在本仓库安装 pre-commit 隐私扫描钩子（幂等，可重复执行）。

用法（仓库根目录）：
    python _tools/install_hooks.py
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "_tools", "pre_commit_privacy_scan.py")


def git_root() -> str:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print("✗ 当前目录不是 git 仓库")
        sys.exit(1)
    return r.stdout.strip()


def write_hook(dst: str, body: str, shebang: str) -> None:
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(shebang + "\n" + body + "\n")
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    root = git_root()
    hooks = os.path.join(root, ".git", "hooks")
    os.makedirs(hooks, exist_ok=True)

    if not os.path.isfile(SRC):
        print(f"✗ 找不到源脚本: {SRC}")
        return 1

    # Windows 上的坑：git 默认用 sh 执行钩子，`#!/usr/bin/env python3` 会因
    # PATH 里没有 python3.exe 而失败（`python3` 命令存在不代表这个写法可用），
    # 结果是**每次提交都被拒**——看起来像"扫描很严格"，其实钩子根本没跑。
    # 用 python 更稳；POSIX 下用 env python3。
    shebang = "#!/usr/bin/env python" if os.name == "nt" else "#!/usr/bin/env python3"

    with open(SRC, encoding="utf-8") as f:
        body = f.read()
    lines = body.splitlines()
    if lines and lines[0].startswith("#!"):
        body = "\n".join(lines[1:])

    # pre-commit：扫暂存区文件
    pre = os.path.join(hooks, "pre-commit")
    if os.path.isfile(pre):
        with open(pre, encoding="utf-8", errors="replace") as f:
            old = f.read()
        if "隐私扫描" not in old:
            shutil.copy2(pre, pre + ".bak")
            print(f"• 已备份原 pre-commit 钩子 → {pre}.bak")
        else:
            print("• pre-commit 隐私钩子已存在，覆盖更新")
    write_hook(pre, body, shebang)
    print(f"✓ 已安装: {pre}")

    # commit-msg：扫提交信息（pre-commit 阶段看不到本次提交信息）
    cm = os.path.join(hooks, "commit-msg")
    if os.path.isfile(cm):
        with open(cm, encoding="utf-8", errors="replace") as f:
            old = f.read()
        if "隐私扫描" not in old:
            shutil.copy2(cm, cm + ".bak")
            print(f"• 已备份原 commit-msg 钩子 → {cm}.bak")
    write_hook(cm, body, shebang)
    print(f"✓ 已安装: {cm}")

    print()
    print("测试：")
    print("    提交含手机号/序列号/token 的文件或提交信息会被自动拦下")
    print("    跳过单次检查：git commit --no-verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())