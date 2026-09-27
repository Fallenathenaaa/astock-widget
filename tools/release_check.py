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
YELLOW = "\033[93m"


def remote_tag_sha(tag):
    """查远端这个 tag 指向哪个 commit。

    返回三种东西：
      "missing" —— 远端没这个 tag（新版本，还没发过）
      "unknown" —— 查不到（网络问题 / API 抽风），不该因此挡住发版
      一串 sha   —— tag 指向的 commit
    """
    try:
        import json, urllib.request, urllib.error
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from push_github import OWNER, REPO      # 只取常量，不碰它的网络封装
        # ★ 这里故意**不带** Authorization：push_github.http 在无 token 时会
        # 发一个空 Bearer 头，GitHub 回 401 Bad credentials（真踩过）。
        # 仓库是公开的，匿名查 tag 就够了；也免得给 CI 配额外的 token。
        url = ("https://api.github.com/repos/%s/%s/git/refs/tags/%s"
               % (OWNER, REPO, tag))
        req = urllib.request.Request(url, headers={
            "User-Agent": "astock-widget-release-check",
            "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        obj = d.get("object") or {}
        # ★ 附注标签（annotated tag）这里 type 是 "tag"，sha 指向 tag 对象
        # 而不是 commit —— 拿它跟 GITHUB_SHA（一个 commit sha）比必然不等，
        # 于是每次都误判成"版本分叉"。我们的 tag 都是 release_tag.py 用
        # POST /git/refs 建的轻量标签（type=commit，实测过），但万一哪天换了
        # 建法，宁可跳过也别误报 —— 跟"查不清就不挡"是同一个态度。
        if obj.get("type") not in (None, "commit"):
            return "unknown"
        return obj.get("sha") or "unknown"
    except urllib.error.HTTPError as e:
        return "missing" if e.code == 404 else "unknown"
    except Exception:
        return "unknown"


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
    # 精确匹配「当前版本：**vX.Y.Z**」这一处，不是全篇找子串。
    # 子串匹配会让 "v2.1.1" 在写着 v2.1.10 的页面上"通过"，也会因为正文里
    # 随便一句历史版本号就误判为已更新 —— 那等于没检查。
    m_ver = re.search(r"当前版本：\*\*(v\d+\.\d+\.\d+)\*\*", readme)
    require("README 顶部的「当前版本」就是 %s" % ver,
            bool(ver) and m_ver is not None and m_ver.group(1) == ver,
            (m_ver.group(1) if m_ver else "没找到「当前版本：**vX.Y.Z**」"))
    # 下载链接必须指着同一个 tag，否则用户点进去拿到的是别的版本
    m_dl = re.search(r"releases/tag/(v\d+\.\d+\.\d+)", readme)
    require("README 的下载链接指着 %s" % ver,
            bool(ver) and m_dl is not None and m_dl.group(1) == ver,
            m_dl.group(1) if m_dl else "没找到 releases/tag/ 链接")

    # ------------------------------------------ 0.5 tag 身份（防版本分叉）
    # 场景：v2.1.7 的 tag 已经发出去了，之后又往 main 推了新代码，但
    # APP_VERSION 还写着 v2.1.7。于是 "v2.1.7" 这个版本号同时对应两份
    # 不同的代码 —— 用户说"我用的 v2.1.7 有问题"时，根本不知道他拿的是哪份。
    # 便携包还会更糟：它可能是从后来的 main 构建的，tag 里却没那份 start.bat。
    #
    # ★ 只在 CI 的 main push 上查，两个原因：
    #   1) push_github.py 是在服务端**现建** commit 的，本地 sha 和远端天然
    #      不同（同一份内容两个 sha），本地查必误报
    #   2) PR 上 GITHUB_SHA 是合并提交，也不是 main 本人，同样会误报
    is_main_push = (os.environ.get("GITHUB_EVENT_NAME") == "push"
                    and os.environ.get("GITHUB_REF") == "refs/heads/main")
    sha = os.environ.get("GITHUB_SHA") or ""
    tag = tag_name(ver) if ver else ""
    if not is_main_push or not sha or not tag:
        print("%s[ -- ]%s 非 CI main push，跳过 tag 身份检查"
              "（本地/PR 的 sha 与远端 tag 不可比，查了只会误报）" % (DIM, DIM))
    else:
        tc = remote_tag_sha(tag)
        if tc == "missing":
            ok_line("远端还没有 %s 这个 tag（新版本，可以直接发）" % tag)
        elif tc == "unknown":
            print("%s[WARN]%s 查不到远端 tag %s（网络问题？），跳过身份检查"
                  % (YELLOW, DIM, tag))
        else:
            require("已发布的 %s 仍指着当前 commit" % tag, tc == sha,
                    "tag 指着 %s，当前是 %s —— 版本号没变却已经继续开发了，"
                    "先升 widget.py 里的 APP_VERSION" % (tc[:8], sha[:8]))

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
