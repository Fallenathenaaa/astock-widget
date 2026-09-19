# -*- coding: utf-8 -*-
"""跑全部测试。

    python run_tests.py

每个 test_*.py 都能单独跑（`python tests/test_backup.py`），自己带断言和退出码。
所有用例都在临时目录里跑，**不会碰真实的 stocks.json / backups / logs**。
offscreen 平台，不需要显示器。
"""
import os
import subprocess
import sys

# Windows 控制台默认不是 UTF-8（中文机器是 cp936，英文机器是 cp1252），
# 往 stdout 打中文会直接 UnicodeEncodeError —— GitHub 的 windows-latest
# runner 就是 cp1252，第一次上 CI 就挂在这儿，本地却完全正常。
# 所以：自己先切成 UTF-8，再让每个子进程也用 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")
PY = sys.executable

files = sorted(f for f in os.listdir(TESTS)
               if f.startswith("test_") and f.endswith(".py"))

if not files:
    print("没找到测试文件：%s" % TESTS)
    sys.exit(1)

total_ok = total_fail = 0
failed = []

print("=" * 60)
for f in files:
    path = os.path.join(TESTS, f)
    print("--- %s" % f)
    r = subprocess.run([PY, path], cwd=HERE, capture_output=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    # 只打印 FAIL 行和最后的统计，PASS 太多会刷屏
    for line in out.splitlines():
        if "FAIL" in line or line.startswith("=="):
            print("    " + line)
    tail = [l for l in out.splitlines() if "passed" in l]
    if tail:
        print("    " + tail[-1])
        try:
            n_ok = int(tail[-1].split()[0])
            n_fail = int(tail[-1].split()[2])
        except Exception:
            n_ok = n_fail = 0
        total_ok += n_ok
        total_fail += n_fail
        # 用例全过但进程退出码非 0 = 退出时炸了（典型：QThread 还在跑就被销毁，
        # Qt 直接 abort，退出码 0xC0000409）。算失败，不然这种问题永远没人发现。
        if n_fail == 0 and r.returncode != 0:
            print("    ! 用例全过，但进程退出码 = %s（退出时异常终止）" % r.returncode)
        if n_fail or r.returncode != 0:
            failed.append(f)
    else:
        failed.append(f)
        print("    (没有输出统计，可能崩了)")
        if out.strip():
            print(out.strip()[-800:])

print("=" * 60)
print("合计：%d passed, %d failed" % (total_ok, total_fail))
if failed:
    print("失败的用例文件：%s" % ", ".join(failed))
sys.exit(1 if failed else 0)
