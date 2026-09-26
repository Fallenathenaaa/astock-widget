# -*- coding: utf-8 -*-
"""构建便携版：内嵌 Python，解压即用（不用装 Python、不用联网装依赖）。

    python tools/build_portable.py                  # 构建当前 checkout
    python tools/build_portable.py --out DIR        # 指定产物目录
    python tools/build_portable.py --from-venv PATH # 从这个 venv 复制 PySide6
    python tools/build_portable.py --dry-run        # 只打印要做什么

产物（在 --out 目录下，默认 ./dist）：

    astock-widget-vX.Y.Z-portable.zip
    SHA256SUMS.txt

版本号取自 widget.py 的 APP_VERSION —— 便携包必须和源码版本一致，
不要在这儿另起一套。

为什么要有这个脚本
------------------
便携包 89 MB，以前是手工一步步拼出来的：embeddable 用的哪个精确版本、
PySide6 怎么进去的、_pth 改了哪一行、哪些文件进了 zip，全靠人记。
下次再构建没人能回答，也没法审计。所以把每一步都代码化。

★ 改这个脚本前必读的三个坑
--------------------------
1. embeddable 的 `python3xx._pth` 让 sys.path **完全由那个文件决定**：
   - 不会自动把脚本所在目录加进 sys.path
   - PYTHONPATH 环境变量也会被忽略
   所以直接 `py\\pythonw.exe widget.py` 会 ModuleNotFoundError（找不到
   market_clock）。修法：把 py/ 放在 app 根**下面**，_pth 里写 `..`
   （相对 python.exe 所在目录）指回 app 根，同级源码才能被 import。

2. 便携 Python 不带 certifi。但 Windows 上 CPython 从**系统证书存储**加载
   证书，实测 HTTPS 取数正常 —— 不要额外塞证书，那是多余的。

3. `--from-venv` 复制的是**已装好的** PySide6。venv 里的 .pyd/.dll 是
   和那个 Python 版本绑定的（cp313），所以 embeddable 版本必须和 venv 的
   Python 版本一致，否则 import 会失败。脚本会检查这一点。
"""

import argparse
import ast
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Python embeddable 的精确版本 —— 钉死，不许浮动。
# 它必须和 --from-venv 那个 venv 的 Python 版本一致（abi 标签 cp313）。
EMBED_VERSION = "3.13.12"
EMBED_URLS = [
    # 先试镜像：python.org 官方直连 HEAD 能通但 GET 很慢，国内基本下不动
    "https://registry.npmmirror.com/-/binary/python/%s/python-%s-embed-amd64.zip"
    % (EMBED_VERSION, EMBED_VERSION),
    # 官方兜底
    "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (
        EMBED_VERSION, EMBED_VERSION),
]

# 进 zip 的源码文件（app 根下）
SOURCE_FILES = [
    "widget.py", "market_clock.py", "providers.py", "run_tests.py",
    "demo.py", "requirements.txt", "start.bat", "install.bat",
    "stocks.example.json", "LICENSE", "README.md", "README-portable.md",
]

# 从 venv 复制进便携包的依赖目录
VENV_PACKAGES = ["PySide6", "shiboken6"]


def read_version():
    """从 widget.py 读 APP_VERSION。

    用 ast 而不是 import widget —— import 会拉起 PySide6、建 QApplication，
    在一个只想知道版本号的脚本里那是灾难。
    """
    path = os.path.join(ROOT, "widget.py")
    src = io.open(path, encoding="utf-8").read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "APP_VERSION":
                    return ast.literal_eval(node.value)
    raise SystemExit("widget.py 里找不到 APP_VERSION")


def log(msg):
    print(msg, flush=True)


def download(url, dest):
    """下一个文件，带简单的重试。"""
    import urllib.request
    for attempt in range(1, 4):
        try:
            log("  下载 %s (第 %d 次)" % (url, attempt))
            req = urllib.request.Request(url, headers={"User-Agent": "astock-widget"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            log("    失败: %s: %s" % (type(e).__name__, e))
    return False


def prepare_python(pydir, from_venv, dry_run):
    """下载 embeddable + 解包 + 改 _pth + 装依赖。"""
    if dry_run:
        log("  [dry-run] 准备便携 Python %s -> %s" % (EMBED_VERSION, pydir))
        return

    os.makedirs(pydir, exist_ok=True)
    tmp = os.path.join(tempfile.mkdtemp(prefix="astock-embed-"), "py.zip")
    ok = False
    for url in EMBED_URLS:
        if download(url, tmp):
            ok = True
            break
    if not ok:
        raise SystemExit("embeddable Python 下载失败，所有源都试过了")

    with zipfile.ZipFile(tmp) as z:
        z.extractall(pydir)
    os.remove(tmp)

    # 坑 1：_pth 决定 sys.path，必须让 app 根可导入
    tag = "".join(EMBED_VERSION.split(".")[:2])     # 3.13.12 -> "313"
    pth = os.path.join(pydir, "python%s._pth" % tag)
    if not os.path.exists(pth):
        # 版本对不上（比如只换了 EMBED_VERSION 却没同步 tag 规则）：
        # 认实际解出来的那个，别硬写死
        cands = [f for f in os.listdir(pydir) if f.startswith("python")
                 and f.endswith("._pth")]
        if not cands:
            raise SystemExit("解包后找不到 ._pth 文件（embeddable 结构变了？）")
        pth = os.path.join(pydir, cands[0])
        tag = cands[0][len("python"):-len("._pth")]
    with io.open(pth, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("python%s.zip\r\n" % tag)
        f.write("..\r\n")                 # ★ app 根（见文件头坑 1）
        f.write("Lib\\site-packages\r\n")
        f.write("import site\r\n")
    log("  已改 %s（加 .. 指回 app 根）" % os.path.basename(pth))

    install_deps(pydir, from_venv)


def install_deps(pydir, from_venv):
    """把 PySide6 / shiboken6 放进便携包的 site-packages。

    ★ 默认是 pip --target 按 requirements.txt 装（PySide6-**Essentials**），
    不是从 venv 整包复制。原因很实在：
    venv 里常装的是完整 PySide6 元包（641 MB），里面 Qt6WebEngineCore.dll
    一个就 194 MB，还有 QtQuick / OpenGL / avcodec —— 挂件一个都不用。
    整包复制出来的便携 zip 会从约 40 MB 涨到 235 MB。
    requirements.txt 钉的是 Essentials（只有 QtCore / QtGui / QtWidgets），
    这才是挂件真正需要的。
    """
    site_pkgs = os.path.join(pydir, "Lib", "site-packages")
    os.makedirs(site_pkgs, exist_ok=True)

    if not from_venv:
        cur = "%d.%d" % sys.version_info[:2]
        emb = ".".join(EMBED_VERSION.split(".")[:2])
        if cur != emb:
            log("  警告: 当前 Python %s 与 embeddable %s 不一致，"
                "装出来的 wheel 可能是别的 abi" % (cur, emb))
        req = os.path.join(ROOT, "requirements.txt")
        for extra in (["-i", "https://mirrors.aliyun.com/pypi/simple/"], []):
            cmd = [sys.executable, "-m", "pip", "install", "-r", req,
                   "--target", site_pkgs, "--only-binary=:all:",
                   "--upgrade"] + extra
            log("  pip install -r requirements.txt --target ...")
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                log("  依赖装好了")
                return
            log("  失败: %s" % (r.stderr or r.stdout or "")[-300:])
        raise SystemExit("依赖装不上，检查网络或先配好镜像")

    log("  警告: --from-venv 会把 venv 里的完整 PySide6（含 QtWebEngine 等"
        " Addons）一起拷进去，包会大很多；确认你要的是这个再继续。")
    if from_venv:
        vsite = os.path.join(from_venv, "Lib", "site-packages")
        if not os.path.isdir(vsite):
            raise SystemExit("--from-venv 里没有 Lib\\site-packages: %s" % vsite)
        # ★ 必须跳过这些目录，两个原因：
        #   1) PySide6 的 qml/ 下目录嵌套极深，路径轻松超过 Windows 260 字符
        #      上限，copytree 会直接 WinError 3 失败（真踩过）
        #   2) 挂件只用 QtWidgets / QtGui / QtCore，Qt Quick 的 qml、示例、
        #      头文件一律用不上 —— 带上它们白白多出几十 MB
        ignore = shutil.ignore_patterns(
            "qml", "examples", "include", "glslang", "__pycache__")
        for name in VENV_PACKAGES:
            src = os.path.join(vsite, name)
            if not os.path.isdir(src):
                raise SystemExit("venv 里缺 %s，先 pip install -r requirements.txt"
                                 % name)
            dst = os.path.join(site_pkgs, name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=ignore)
            log("  复制 %s" % name)
        return


def build_zip(stage, out_dir, version, dry_run):
    """打包 + 算 SHA256。"""
    name = "astock-widget-%s-portable" % version
    zpath = os.path.join(out_dir, name + ".zip")
    if dry_run:
        log("  [dry-run] 会生成 %s" % zpath)
        return zpath

    # ★ 必须跳过 qml/：PySide6 里 Qt Quick 用的一堆东西，挂件一个控件都不用。
    # 更要命的是它下面目录嵌套极深，路径轻松超过 Windows 260 字符上限，
    # os.walk 能列出来但 os.stat 会 WinError 3 —— zip.write 直接崩，
    # 于是留下一个写了一半的 zip（真踩过：构建"看着成功"，产物却是残的）。
    SKIP_DIRS = {"qml", "examples", "include"}
    entries = []
    for root, dirs, files in os.walk(stage):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            entries.append(os.path.join(root, f))
    log("  打包 %d 个文件 ..." % len(entries))
    skipped = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in entries:
            arc = name + "/" + os.path.relpath(p, stage).replace("\\", "/")
            try:
                z.write(p, arc)
            except OSError:
                # 万一还有别的超长路径：跳过而不是让整个构建崩掉，
                # 但必须报出来 —— 静默跳过会让人以为产物是完整的。
                skipped += 1
    if skipped:
        log("  ★ 跳过了 %d 个读不了的文件（多半还是超长路径），"
            "产物可能不完整，请检查" % skipped)

    # ★ 自检：别再把"写了一半的 zip"当成构建成功。
    # 真踩过：打包在超长路径上崩了，留下一个能打开、条目却只有零头的 zip，
    # 日志看起来一切正常，产物其实是残的。
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        if bad is not None:
            raise SystemExit("zip CRC 校验失败: %s" % bad)
        have = set(z.namelist())
    must = ["widget.py", "start.bat", "market_clock.py", "providers.py",
            "py/pythonw.exe", "py/python313._pth",
            "py/Lib/site-packages/PySide6/QtWidgets.pyd",
            "py/Lib/site-packages/PySide6/plugins/platforms/qwindows.dll"]
    gone = [m for m in must if (name + "/" + m) not in have]
    if gone:
        raise SystemExit("产物缺关键文件: %s" % gone)
    if not any(n.startswith(name + "/py/Lib/site-packages/shiboken6/")
               for n in have):
        # shiboken6 不在的话 PySide6 一 import 就 ImportError，
        # 而 pip --target 偶尔会漏掉它
        raise SystemExit("产物里没有 shiboken6 —— PySide6 会 import 失败")
    log("  自检通过：关键文件齐全，shiboken6 在，CRC 正常")

    # SHA256SUMS：让用户能验下载到的包有没有被改过
    h = hashlib.sha256()
    with open(zpath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sums = os.path.join(out_dir, "SHA256SUMS.txt")
    with io.open(sums, "w", encoding="utf-8", newline="\n") as f:
        f.write("%s  %s\n" % (h.hexdigest(), name + ".zip"))
    log("  产物: %s (%.1f MB)" % (zpath, os.path.getsize(zpath) / 1024 / 1024))
    log("  SHA256: %s" % h.hexdigest())
    return zpath


def main():
    ap = argparse.ArgumentParser(description="构建便携版（内嵌 Python）")
    ap.add_argument("--out", default=None, help="产物目录（默认 ./dist）")
    ap.add_argument("--from-venv", default=None,
                    help="从这个 venv 复制 PySide6（省去联网安装）")
    ap.add_argument("--dry-run", action="store_true", help="只打印要做什么")
    args = ap.parse_args()

    version = read_version()
    out_dir = args.out or os.path.join(ROOT, "dist")
    log("版本 %s" % version)
    log("产物目录 %s" % out_dir)

    if args.dry_run:
        log("[dry-run] 源码文件: %s" % ", ".join(SOURCE_FILES))
        prepare_python("<stage>/py", args.from_venv, True)
        build_zip("<stage>", out_dir, version, True)
        return 0

    stage = tempfile.mkdtemp(prefix="astock-portable-")
    app = os.path.join(stage, "astock-widget-%s-portable" % version)
    os.makedirs(app)
    try:
        log("1/4 收集源码")
        for f in SOURCE_FILES:
            src = os.path.join(ROOT, f)
            if not os.path.exists(src):
                raise SystemExit("缺文件: %s" % f)
            shutil.copy2(src, os.path.join(app, f))
        log("  %d 个文件" % len(SOURCE_FILES))

        log("2/4 准备便携 Python")
        prepare_python(os.path.join(app, "py"), args.from_venv, False)

        log("3/4 运行时预检（import 一遍，别把坏包发出去）")
        pyexe = os.path.join(app, "py", "python.exe")
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        r = subprocess.run(
            [pyexe, "-c", "import PySide6, providers, market_clock"],
            cwd=app, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("预检失败，包不能用:\n%s\n%s"
                             % (r.stdout, r.stderr))
        log("  预检通过")

        log("4/4 打包")
        os.makedirs(out_dir, exist_ok=True)
        build_zip(app, out_dir, version, False)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    log("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
