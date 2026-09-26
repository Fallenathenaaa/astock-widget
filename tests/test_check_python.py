# -*- coding: utf-8 -*-
"""Python 版本 gate：升级用户已有的旧 .venv 不能绕过 3.10–3.14 这道闸。

install.bat 原来只在「.venv 还不存在」时挑 Python。老用户升级时 .venv
早就有了（这个项目早期允许过 3.8+），于是 3.8 / 3.9 的 venv 被原样复用：
install 绿灯、start 只查 import PySide6（旧环境装着就过），README 上写的
版本范围成了一句空话。

版本判断放在 tools/check_python.py 里，就是为了能在 CI 上真的测一遍
边界，而不是靠肉眼看 .bat。
"""
import io
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

print("== --range / --find：让 .bat 不再复制版本表 ==")
HELPER = os.path.join(ROOT, "tools", "check_python.py")

r = subprocess.run([PY, HELPER, "--range"], capture_output=True,
                   encoding="utf-8", errors="replace")
chk("--range 退出码 0", r.returncode == 0, r.returncode)
chk("--range 输出就是 MIN/MAX 那一对",
    (r.stdout or "").strip() == "3.10 3.14", (r.stdout or "").strip())
chk("--range 和常量一致",
    (r.stdout or "").split() == ["%d.%d" % CP.MIN_PY, "%d.%d" % CP.MAX_PY])

r = subprocess.run([PY, HELPER, "--find"], capture_output=True,
                   encoding="utf-8", errors="replace")
chk("--find 退出码 0（CI 上三个版本都在区间内）", r.returncode == 0,
    (r.returncode, (r.stdout or "") + (r.stderr or "")))
found = (r.stdout or "").strip()
chk("--find 输出非空", bool(found), found)
if found:
    # 输出必须能直接拼 -m venv 用 —— 这就是 bat 接下来要做的事
    v = CP.probe(found.split())
    chk("--find 出来的解释器版本受支持", v is not None and CP.version_ok(v),
        (found, v))

cmd, ver = CP.find_interpreter()
chk("find_interpreter() 也能找到", cmd is not None and ver is not None, (cmd, ver))
if cmd:
    chk("find_interpreter() 返回的版本受支持", CP.version_ok(ver), ver)

print("== 版本表不能被复制到别处 ==")
# 如果 install.bat 里又出现一份 `3.14 3.13 3.12 ...`，那"唯一真相源"就是假的：
# 以后升到 3.15 要改两个地方，而且一定会漂。
bat = io.open(os.path.join(ROOT, "install.bat"), encoding="utf-8",
              errors="replace").read()
chk("install.bat 不再硬编码版本表",
    "3.14 3.13" not in bat and "3.13 3.12" not in bat and "3.12 3.11" not in bat)
chk("install.bat 改用 --find 问 helper", "--find" in bat)
chk("install.bat 指向 check_python.py", "check_python.py" in bat)
# 错误提示里也不能写死 —— 那是最容易被漏掉的第二种复制方式
import re
for name in ("install.bat", "start.bat"):
    txt = io.open(os.path.join(ROOT, name), encoding="utf-8",
                  errors="replace").read()
    hits = [l.strip() for l in txt.splitlines()
            if re.search(r"^\s*echo\b.*\d+\.\d+", l, re.I)]
    chk("%s 的用户可见提示里没有写死版本号" % name, not hits, hits[:3])
    if name == "install.bat":
        chk("install.bat 用 --range 填提示", "--range" in txt)

print("== portable 启动分支必须先做可见预检 ==")
# 报告 P2-13：只要 py\pythonw.exe 存在就直接 pythonw 启动。包损坏 / 缺 DLL /
# _pth 写错时 pythonw 静默退出，而多数 import 发生在崩溃处理器安装之前 ——
# 连 crash log 都不会有，用户只看到"双击没反应"。所以必须先用控制台 python
# 预检一遍，失败要给看得见的错误 + 非零退出，而不是继续静默拉起 pythonw。
# （这里做静态断言：真跑 start.bat 会撞上 pause 把测试挂住。）
_ptxt = io.open(os.path.join(ROOT, "start.bat"), encoding="utf-8").read()
chk("便携分支用带控制台的 python 做预检",
    'py\\python.exe" -c "import PySide6' in _ptxt)
chk("预检覆盖 providers / market_clock（不只是 PySide6）",
    "providers, market_clock" in _ptxt)
chk("预检失败给可见错误", "ERROR" in _ptxt)
chk("预检失败非零退出，不再静默启动", "exit /b 1" in _ptxt)
chk("预检失败会 pause（窗口不会一闪而过）", "pause" in _ptxt)
_i_pre = _ptxt.index('py\\python.exe" -c')
_i_launch = _ptxt.index('start "" "%~dp0py\\pythonw.exe"')
chk("预检在启动之前", _i_pre < _i_launch, (_i_pre, _i_launch))

print("== --find 的输出要能直接当命令用（带空格的路径得有引号）==")
# install.bat 是 `%PYCMD% -m venv "%VENV%"`，拿 --find 的输出原样当命令跑。
# 解释器装在 C:\Program Files\Python313\ 时，裸 " ".join 出来的没有引号，
# cmd 会把它拆成两个 token，venv 建不起来。
s_spaced = subprocess.list2cmdline([r"C:\Program Files\Python313\python.exe"])
chk("带空格的路径被加上引号", s_spaced.startswith('"'), s_spaced)
chk("不带空格的路径不多加引号",
    subprocess.list2cmdline([r"C:\Python313\python.exe"])
    == r"C:\Python313\python.exe")
chk("py -3.13 这种拼出来不变",
    subprocess.list2cmdline(["py", "-3.13"]) == "py -3.13")
if os.name == "nt":
    _src = io.open(HELPER, encoding="utf-8").read()
    chk("helper 在 Windows 上用 list2cmdline 拼（不是裸 join）",
        "subprocess.list2cmdline(cmd)" in _src)

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
