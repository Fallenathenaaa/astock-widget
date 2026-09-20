# -*- coding: utf-8 -*-
"""检查一个 Python 解释器（或 .venv）是不是这个项目支持的版本。

    python tools/check_python.py                 # 检查当前解释器
    python tools/check_python.py .venv           # 检查这个 venv 里的解释器
    python tools/check_python.py C:\\path\\to\\python.exe

退出码 0 = 合格（3.10 ~ 3.14），1 = 不合格 / 查不到。
版本区间写在这里，是唯一真相源 —— README 和 .bat 都从它取。

★ 为什么要有这个 helper

`install.bat` 原来只在「`.venv` 还不存在」的时候挑 Python：

    if not exist "%PYEXE%"  ( 挑 3.14 -> 3.10 )

可老用户升级时 `.venv` 早就有了 —— 这个项目早期允许过 Python 3.8+，
于是 3.8 / 3.9 的 venv 会被原样复用：install 一路绿灯，start 只检查
`import PySide6`（旧环境里 PySide6 装着的话照样过）。README 上写的
「Python 3.10–3.14」就成了一句空话，等真正踩到 3.10 语法才炸，
而且报错信息和真正的原因八竿子打不着。

版本比较在 .bat 里写很难读（整数比较、for 循环里的延迟展开都是坑），
交给 Python 自己判断最稳，还能在 CI 上测。
"""
import os
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MIN_PY = (3, 10)
MAX_PY = (3, 14)


def version_ok(ver):
    """(major, minor) 落在 [3.10, 3.14] 里就算合格。patch 不参与判断。"""
    return MIN_PY <= tuple(ver[:2]) <= MAX_PY


def describe(ver):
    return ".".join(str(p) for p in ver[:3])


def resolve(target):
    """把参数解析成一个可执行文件：目录就当 venv 找里面的解释器。"""
    if not target:
        return sys.executable
    if os.path.isdir(target):
        for rel in ("Scripts/python.exe", "bin/python", "bin/python3"):
            p = os.path.join(target, *rel.split("/"))
            if os.path.exists(p):
                return p
        return None                     # 目录里没有解释器
    return target


def probe(cmd):
    """问一个解释器它自己是什么版本。问不出来返回 None。

    cmd 可以是字符串，也可以是 ["py", "-3.13"] 这种列表。
    """
    args = [cmd] if isinstance(cmd, str) else list(cmd)
    try:
        out = subprocess.run(
            args + ["-c",
                    "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    txt = (out.stdout or "").strip().splitlines()
    if not txt:
        return None
    try:
        return tuple(int(x) for x in txt[-1].strip().split("."))
    except ValueError:
        return None


def find_interpreter():
    """在本机找第一个受支持的 Python。

    返回 (命令列表, 版本元组)；命令列表可以直接拼 `-m venv` 用。
    先试 py launcher（从 3.14 往 3.10），再试 python3 / python。
    找不到返回 (None, None)。

    ★ 让 .bat 用这个而不是自己抄一份版本表 —— 否则"唯一真相源"就是假的：
    helper 改了 3.15，install.bat 的 `for %%V in (3.14 3.13 ...)` 还在原地。
    """
    import shutil
    candidates = []
    py = shutil.which("py")
    if py:
        for minor in range(MAX_PY[1], MIN_PY[1] - 1, -1):
            candidates.append([py, "-%d.%d" % (MIN_PY[0], minor)])
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            candidates.append([p])
    for cmd in candidates:
        ver = probe(cmd)
        if ver and version_ok(ver):
            return cmd, ver
    return None, None


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    if "--range" in argv:
        print("%d.%d %d.%d" % (MIN_PY + MAX_PY))
        return 0

    if "--find" in argv:
        cmd, ver = find_interpreter()
        if not cmd:
            print("找不到受支持的 Python（需要 %d.%d - %d.%d）"
                  % (MIN_PY + MAX_PY), file=sys.stderr)
            return 1
        print(" ".join(cmd))
        return 0

    target = argv[0] if argv else None

    if target is None:
        ver = sys.version_info[:3]
        where = "当前解释器"
    else:
        exe = resolve(target)
        if not exe:
            print("查不到 Python 解释器：%s" % target)
            return 1
        ver = probe(exe)
        if ver is None:
            print("问不出版本：%s（跑不起来？）" % exe)
            return 1
        where = exe

    if version_ok(ver):
        print("OK  %s  %s（支持 %s ~ %s）"
              % (where, describe(ver),
                 describe(MIN_PY + (0,))[:4], describe(MAX_PY + (0,))[:4]))
        return 0
    print("不合格  %s  %s" % (where, describe(ver)))
    print("本项目需要 Python %s ~ %s"
          % (describe(MIN_PY + (0,))[:4], describe(MAX_PY + (0,))[:4]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
