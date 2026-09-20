# -*- coding: utf-8 -*-
"""Python 版本 gate：升级用户已有的旧 .venv 不能绕过 3.10–3.14 这道闸。

install.bat 原来只在「.venv 还不存在」时挑 Python。老用户升级时 .venv
早就有了（这个项目早期允许过 3.8+），于是 3.8 / 3.9 的 venv 被原样复用：
install 绿灯、start 只查 import PySide6（旧环境装着就过），README 上写的
版本范围成了一句空话。

版本判断放在 tools/check_python.py 里，就是为了能在 CI 上真的测一遍
边界，而不是靠肉眼看 .bat。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_python as CP  # noqa: E402

PY = sys.executable
ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


print("== 版本区间边界 ==")
for ver, want, name in [
    ((3, 8, 0), False, "3.8 拒"),
    ((3, 9, 18), False, "3.9 拒"),
    ((3, 10, 0), True, "3.10 收"),
    ((3, 11, 5), True, "3.11 收"),
    ((3, 12, 1), True, "3.12 收"),
    ((3, 13, 0), True, "3.13 收"),
    ((3, 14, 0), True, "3.14 收"),
    ((3, 15, 0), False, "3.15 拒"),
    ((4, 0, 0), False, "4.0 拒"),
    ((2, 7, 18), False, "2.7 拒"),
]:
    chk(name, CP.version_ok(ver) is want, "%s -> %s" % (ver, CP.version_ok(ver)))
# patch 号不参与判断，只看 major.minor
chk("patch 号不影响", CP.version_ok((3, 10, 99)) and not CP.version_ok((3, 9, 99)))
chk("区间常量是 3.10 ~ 3.14",
    CP.MIN_PY == (3, 10) and CP.MAX_PY == (3, 14), (CP.MIN_PY, CP.MAX_PY))

print("== 描述函数 ==")
chk("describe(3,10,2) -> 3.10.2", CP.describe((3, 10, 2)) == "3.10.2",
    CP.describe((3, 10, 2)))
chk("describe 只用前三段", CP.describe((3, 10, 2, "final", 0)) == "3.10.2")

print("== 解析目标 ==")
chk("不给参数 → 当前解释器", CP.resolve(None) == sys.executable)
chk("给 exe 路径 → 原样返回", CP.resolve(PY) == PY)
# 给目录 → 当 venv 找
import tempfile
tmp = tempfile.mkdtemp(prefix="astock-venv-")
os.makedirs(os.path.join(tmp, "Scripts"))
fake = os.path.join(tmp, "Scripts", "python.exe")
with open(fake, "w") as f:
    f.write("x")
chk("目录 → 找 Scripts/python.exe",
    CP.resolve(tmp) == fake or CP.resolve(tmp) == os.path.join(tmp, "bin", "python"),
    CP.resolve(tmp))
chk("空目录 → 查不到（返回 None）",
    CP.resolve(tempfile.mkdtemp(prefix="astock-empty-")) is None)

print("== 真跑一遍 helper ==")
r = subprocess.run([PY, os.path.join(ROOT, "tools", "check_python.py")],
                   capture_output=True, encoding="utf-8", errors="replace")
chk("当前解释器退出码 0（CI 上的 Python 都在区间内）", r.returncode == 0,
    (r.returncode, (r.stdout or "") + (r.stderr or "")))
chk("输出里有 OK", "OK" in (r.stdout or ""), r.stdout)

r = subprocess.run([PY, os.path.join(ROOT, "tools", "check_python.py"),
                    os.path.join(ROOT, "tools")],
                   capture_output=True, encoding="utf-8", errors="replace")
chk("给一个不是 venv 的目录 → 退出码 1", r.returncode == 1,
    (r.returncode, (r.stdout or "") + (r.stderr or "")))

r = subprocess.run([PY, os.path.join(ROOT, "tools", "check_python.py"), PY],
                   capture_output=True, encoding="utf-8", errors="replace")
chk("显式传解释器路径 → 退出码 0", r.returncode == 0,
    (r.returncode, (r.stdout or "") + (r.stderr or "")))

print("== main() 可直接被塞 argv ==")
chk("main([]) 当前解释器 → 0", CP.main([]) == 0)
chk("main([不存在的目录]) → 1",
    CP.main([os.path.join(tempfile.gettempdir(), "no-such-venv-xyz")]) == 1)

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
