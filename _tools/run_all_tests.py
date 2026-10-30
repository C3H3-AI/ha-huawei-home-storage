#!/usr/bin/env python3
"""一次性跑完全部离线测试。

不需要安装 Home Assistant、aiohttp、cryptography 或 voluptuous —— 每个套件
自己负责 stub 缺失的依赖，或只做静态分析（AST / JSON / 文件结构）。

**运行**::

    python3 _tools/run_all_tests.py           # 全跑
    python3 _tools/run_all_tests.py -v        # 带每个测试名
    python3 _tools/run_all_tests.py privacy   # 只跑匹配名字的套件

退出码：全部通过 0，否则 1（可直接用于 CI / pre-commit）。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent

#: (显示名, 文件, 覆盖范围)
SUITES = [
    (
        "隐私隔离",
        "test_privacy_isolation.py",
        "账号别名/反解、可见账号过滤、统一鉴权出口、视图覆盖、别名往返",
    ),
    (
        "服务一致性",
        "test_services_consistency.py",
        "注册重名、yaml↔代码↔翻译三处对齐、confirm 双层校验、翻译覆盖",
    ),
    (
        "图片路由",
        "test_image_routes.py",
        "URL 格式↔路由模板契约、注册顺序、多账号取图",
    ),
    (
        "上传链路",
        "test_upload_pipeline.py",
        "文件名编码、时间戳、面板 account、字节数校验、相册域现状",
    ),
    (
        "集成结构",
        "test_integration_structure.py",
        "manifest、平台文件、配置流步骤翻译、视图注册、面板重建",
    ),
    (
        "端到端接线",
        "test_wiring.py",
        "面板→服务→yaml→翻译四段打通、端点↔视图、上传 account、"
        "重复注册、孤儿 yaml",
    ),
    (
        "面板 UI 结构",
        "test_panel_ui.js",
        "用构造数据**真的渲染**各页面：新建/删除/上传按钮的出现与隐藏、"
        "空态文案、回收站不可逆操作、目标选择器跨空间",
    ),
]


def main(argv: list[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv
    filters = [a for a in argv[1:] if not a.startswith("-")]

    # ⚠️ SUITES 被清空时不能"静默通过"：0 个套件跑完返回 0，CI 全绿而
    # 实际什么都没验证 —— 正是这套测试要防的那类缺陷。
    if not SUITES:
        print("✗ SUITES 为空：没有任何测试被运行（这本身就是一个失败状态）")
        return 1

    selected = [
        s for s in SUITES
        if not filters or any(f.lower() in s[0].lower() or f.lower() in s[1]
                              for f in filters)
    ]
    if not selected:
        print(f"✗ 过滤条件没匹配到任何套件（可用: {[s[0] for s in SUITES]}）")
        # 过滤后为空是**用户输入错误**，不是"无事可做"
        return 1

    failures: list[str] = []
    skipped_suites: list[str] = []
    total_start = time.monotonic()
    total_cases = 0
    skipped_cases = 0

    for name, filename, scope in selected:
        path = TOOLS / filename
        if not path.exists():
            print(f"\n✗ {name}: 文件不存在 {path}")
            failures.append(f"{name}（缺文件）")
            continue

        print(f"\n{'=' * 70}\n▶ {name}  ({filename})\n  覆盖: {scope}\n{'=' * 70}")
        if filename.endswith(".js"):
            # 面板是 JS，渲染测试只能跑在 node 上
            node = shutil.which("node")
            if not node:
                # 环境缺 node 时**显式跳过并报出来**，不能静默当成通过。
                # （CI 的 ubuntu-latest 自带 node；本地没装的人也不至于被卡住）
                skipped_suites.append(f"{name}（未安装 node）")
                print("  ⚠️ 跳过：本机没有 node，无法运行为面板写的渲染测试")
                continue
            cmd = [node, str(path)]
        else:
            cmd = [sys.executable, str(path)]
        if verbose:
            cmd.append("-v")
        start = time.monotonic()
        # ⚠️ 无论 verbose 与否都要捕获输出：下面靠 ``Ran N tests`` 统计用例数，
        # 不捕获就永远匹配不到 → 每个套件都被判成「0 用例」。
        # 之前写成 ``capture_output=not verbose``，导致 **``-v`` 模式必然全失败**，
        # 本地跑的是不带 -v 的所以没暴露，CI 一上 -v 就 7/7 挂掉。
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), check=False,
            capture_output=True, text=True,
        )
        cost = time.monotonic() - start
        output = (proc.stdout or "") + (proc.stderr or "")
        if output:
            # verbose 时也回显（只是作为可读日志），不再影响统计
            print(output.rstrip())

        # 统计用例数与跳过数：**全部跳过**是可疑状态（例如环境缺库后
        # 整套 skip，退出码仍为 0），必须显式报出来。
        # JS 套件打印的是 "Ran N checks"（没有 unittest 的 test 字样）
        m = re.search(r"^Ran (\d+) (?:test|check)", output, re.MULTILINE)
        ran = int(m.group(1)) if m else 0
        skip_m = re.search(r"skipped=(\d+)", output)
        skipped = int(skip_m.group(1)) if skip_m else 0
        total_cases += ran
        skipped_cases += skipped
        if ran == 0:
            # 文件存在、退出码 0，但**一个用例都没跑** —— 通常是忘了写
            # ``if __name__ == "__main__": unittest.main()``，脚本什么都不做
            # 却返回成功。这与「全部跳过」一样是零验证。
            print(f"  ⚠️ {name}: 一个用例都没跑（是否漏了 unittest.main()？）")
            failures.append(f"{name}（0 用例）")
            continue
        if skipped == ran:
            print(f"  ⚠️ {name}: {ran} 个用例**全部跳过**，实际零验证")
            failures.append(f"{name}（全部跳过）")
            continue

        if proc.returncode != 0:
            failures.append(f"{name}（{filename}, {cost:.2f}s）")

    total = time.monotonic() - total_start
    print(f"\n{'=' * 70}")
    if failures:
        print(f"✗ {len(failures)}/{len(selected)} 个套件失败（{total:.2f}s）:")
        for item in failures:
            print(f"    - {item}")
        return 1
    note = f"，{skipped_cases} 个跳过" if skipped_cases else ""
    print(f"✓ 全部 {len(selected)} 个套件通过：{total_cases} 个用例{note}"
          f"（{total:.2f}s）")
    if skipped_suites:
        # 环境原因跳过的套件必须点名，否则"全绿"有歧义
        print(f"  ⚠️ 因环境缺失未运行：{', '.join(skipped_suites)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
