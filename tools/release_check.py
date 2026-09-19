# -*- coding: utf-8 -*-
"""发版前的一次性检查：把"发出去才发现"的那类问题挡在本地。

    python tools/release_check.py

查这些：
  0. 版本号（从 widget.py 读，唯一真相源）
  1. 全部测试通过
  2. 静态自检（未使用 import / 死代码 / 超长函数）没有硬伤
  3. 主程序能编译
  4. 关键文件齐全（requirements.txt / stocks.example.json / LICENSE / .gitignore）
  5. 仓库里没有私有路径 / token

任何一项不过就退出码非 0，可以直接挂到 CI 上。

`read_version()` 是**版本号的唯一真相源**：用 ast 从 widget.py 里读 `APP_VERSION`，
不 import widget（那会把 PySide6 拉起来，慢几秒还没好处）。打包脚本和
push_github.py 都从这里取，别再各写一份 —— README 曾经写成 v1.4.6 而代码是
v1.4.7，就是因为三处各写各的。
"""
import ast
import io
import os
import re
import subprocess
import sys

# 同上：Windows 控制台不默认 UTF-8，打中文会 UnicodeEncodeError（CI 上踩过）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

GREEN, RED, DIM = "\033[92m", "\033[91m", "\033[90m"


def read_version(root=ROOT):
    """从 widget.py 里读 APP_VERSION。读不到返回空串。"""
    try:
        with io.open(os.path.join(root, "widget.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "APP_VERSION":
                        v = node.value
                        if isinstance(v, ast.Constant) and isinstance(v.value, str):
                            return v.value
    except Exception:
        pass
    return ""


def tag_name(version):
    """版本号就是要打的 tag 名（v2.1.0 -> v2.1.0），别再手工敲一遍。"""
    return version


def run(cmd, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    if os.name == "nt":
        os.system("")           # 打开 Windows 终端的 ANSI 支持

    problems = []

    def ok_line(t):
        print("%s[ OK ]%s %s" % (GREEN, DIM, t))

    def bad_line(t, detail=""):
        print("%s[FAIL]%s %s%s" % (RED, DIM, t, ("  -- " + detail) if detail else ""))

    def require(label, cond, detail=""):
        if cond:
            ok_line(label)
        else:
            bad_line(label, detail)
            problems.append(label)

    print("=" * 62)
    print("发版检查  %s" % ROOT)
    print("=" * 62)

    # ------------------------------------------------------------ 0. 版本
    ver = read_version()
    require("widget.py 里有 APP_VERSION", bool(ver), "读不到")
    require("版本号形如 vX.Y.Z",
            re.fullmatch(r"v\d+\.\d+\.\d+", ver or "") is not None, ver)
    try:
        readme = io.open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    except Exception:
        readme = ""
    require("README 里有当前版本 %s" % ver, bool(ver) and ver in readme, ver)

    # ------------------------------------------------------------ 1. 测试
    rc, out = run([PY, "run_tests.py"])
    m = re.search(r"合计：(\d+) passed, (\d+) failed", out)
    if m:
        n_ok, n_fail = int(m.group(1)), int(m.group(2))
        require("测试 %d 项通过" % n_ok, n_fail == 0, "%d 项失败" % n_fail)
        require("测试进程退出码为 0", rc == 0, "exit=%s" % rc)
        if n_fail:
            for line in out.splitlines():
                if "FAIL" in line:
                    print("      " + line.strip())
    else:
        require("测试跑出了统计行", False, out.strip()[-400:])

    # ------------------------------------------------------------ 2. 静态自检
    rc, out = run([PY, "tools/selfcheck.py"])
    require("静态自检通过", rc == 0, out.strip()[-300:])

    # ------------------------------------------------------------ 3. 编译
    rc, out = run([PY, "-m", "py_compile", "widget.py", "providers.py",
                   "market_clock.py", "run_tests.py"])
    require("主程序能编译", rc == 0, out.strip()[-300:])

    # ------------------------------------------------------------ 4. 文件齐全
    for name in ("requirements.txt", "stocks.example.json", "LICENSE",
                 ".gitignore", "README.md", "widget.py"):
        require("存在 %s" % name, os.path.exists(os.path.join(ROOT, name)))

    # ------------------------------------------------------------ 5. 敏感内容
    rc, out = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
    files = [os.path.join(ROOT, p) for p in out.split()] if rc == 0 else []
    if not files:
        for dp, dn, fn in os.walk(ROOT):
            dn[:] = [d for d in dn if d not in {".git", "__pycache__", ".venv",
                                                "backups", "logs", "screenshots"}]
            files += [os.path.join(dp, f) for f in fn]

    bad = []
    pat_user = re.compile(r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+", re.I)
    pat_tok = re.compile(r"(ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,})")
    pat_url = re.compile(r"https?://[A-Za-z0-9._-]+:[^@\s/]+@github\.com")
    for p in files:
        if os.path.splitext(p)[1] in {".png", ".jpg", ".zip", ".pyc"}:
            continue
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if "tools/release_check.py" in rel or "test_release_hygiene.py" in rel:
            continue                       # 这两个文件里存的就是这些规则本身
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if pat_user.search(line) or pat_tok.search(line) or pat_url.search(line):
                bad.append("%s:%d" % (rel, i))
    require("仓库里没有私有路径 / token", not bad, "、".join(bad[:5]))

    # ------------------------------------------------------- 6. 三路扫描
    # 上面那条只扫文件内容；这条还扫**文件名**（彩蛋名字外泄）和**全部 commit
    # message**（历史里塞过的东西不会因为后来删了就消失）。
    rc, out = run([PY, "tools/privacy_scan.py"])
    require("三路扫描零命中（文件名 / 内容 / commit）", rc == 0, out.strip()[-300:])

    # ------------------------------------------------------------ 结果
    print("=" * 62)
    if problems:
        print("%s发版检查未通过：%d 项%s" % (RED, len(problems), DIM))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("%s发版检查全部通过%s" % (GREEN, DIM))
    print("版本 %s   建议 tag：%s" % (ver, tag_name(ver)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
