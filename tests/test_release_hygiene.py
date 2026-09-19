# -*- coding: utf-8 -*-
"""发布卫生检查：这份代码能不能原样公开。

三件事，全是"出一次事就收不回来"的那类：
1. 仓库里不能有机器的私有路径、token、带凭据的 URL。
   （脚本里写死别人不存在的目录，用户照着跑就只会报错。）
2. 版本、依赖、示例配置这些对外承诺的东西必须和代码对得上。
3. 同一个 class 里不能有同名方法 —— Python 会静默地用后一个覆盖前一个，
   功能悄悄消失且没有任何报错。出过一次（搜索框 Esc 失效），必须守住。

纯静态扫描，不联网、不起界面。
"""
import ast
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


# ---------------------------------------------------------------- 列文件
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "backups", "logs",
             "screenshots", ".idea", ".vscode", "node_modules"}
# 这些是 gitignore 掉的 / 生成物，本来就不进仓库
SKIP_FILES = {"stocks.json", "LOCAL-NOTES.md", "shot.png"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".exe",
            ".dll", ".pyd", ".pyc", ".log", ".csv"}


def tracked_files():
    """列出"会被提交的东西"：已跟踪的 + 未跟踪但没被 gitignore 的。

    --exclude-standard 会把 .gitignore 掉的 stocks.json / backups / logs 排掉，
    所以扫出来的就是别人 clone 下来能看到的那批文件。
    取不到 git（比如源码包解压出来的）就自己走目录，规则保持一致。
    """
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            return [os.path.join(ROOT, p.replace("/", os.sep))
                    for p in r.stdout.split()
                    if os.path.isfile(os.path.join(ROOT, p))]
    except Exception:
        pass
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or os.path.splitext(fn)[1] in SKIP_EXT:
                continue
            out.append(os.path.join(dirpath, fn))
    return out


FILES = tracked_files()
chk("扫到了文件", len(FILES) > 5, len(FILES))


def read(p):
    try:
        with io.open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def scan(pattern, label, allow=()):
    """在全部待发布文件里找 pattern，命中就报一处反例。"""
    hits = []
    for p in FILES:
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if any(a in rel for a in allow):
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            if pattern.search(line):
                hits.append("%s:%d" % (rel, i))
    chk(label, not hits, "、".join(hits[:5]))


# ---------------------------------------------------------------- 1. 敏感内容
print("== 私有路径 ==")
# 别人机器上没有开发者那个用户目录，脚本里写死它就必然跑不起来
scan(re.compile(r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+", re.I),
     "没有硬编码的用户目录",
     allow=("tests/test_release_hygiene.py",))
scan(re.compile(r"\.workbuddy-ai", re.I), "没有引用本机的 .workbuddy-ai 目录",
     allow=("tests/test_release_hygiene.py",))
# 上面那条已经覆盖了任何用户名，不在这里再写一遍具体的 ——
# 免得"规则本身"反倒把开发者用户名留在仓库里

print("== 凭据 ==")
scan(re.compile(r"ghp_[A-Za-z0-9]{10,}"), "没有 GitHub personal token")
scan(re.compile(r"github_pat_[A-Za-z0-9_]{10,}"), "没有 GitHub fine-grained token")
scan(re.compile(r"https?://[A-Za-z0-9._-]+:[^@\s/]+@github\.com"),
     "没有带凭据的 GitHub URL")
scan(re.compile(r"(?i)(api[_-]?key|secret|password)\s*=\s*[\"'][^\"']{8,}[\"']"),
     "没有硬编码的密钥字面量")

# ---------------------------------------------------------------- 2. 对外承诺
print("== 依赖与示例配置 ==")
req = os.path.join(ROOT, "requirements.txt")
chk("有 requirements.txt", os.path.exists(req))
if os.path.exists(req):
    txt = read(req)
    chk("requirements.txt 里锁了 PySide6", "PySide6" in txt, txt[:80])
    chk("版本号是钉死的（不用浮动版本）",
        # 包名允许带后缀：现在装的是 PySide6-Essentials（完整 PySide6 会
        # 多拖一个 168 MB 的 Addons，一个模块都用不上）
        re.search(r"PySide6[\w.-]*\s*==\s*\d", txt) is not None, txt[:80])

import widget as W  # noqa: E402

ex_path = os.path.join(ROOT, "stocks.example.json")
chk("有 stocks.example.json", os.path.exists(ex_path))
if os.path.exists(ex_path):
    import json
    ex = json.loads(read(ex_path))
    missing = [k for k in W.DEFAULT_CONFIG if k not in ex]
    chk("示例配置覆盖了每一个配置项", not missing, "缺 %s" % missing)
    extra = [k for k in ex if k not in W.DEFAULT_CONFIG]
    chk("示例配置里没有已废弃的键", not extra, "多 %s" % extra)

print("== 版本号一致性 ==")
chk("APP_VERSION 形如 vX.Y.Z", re.fullmatch(r"v\d+\.\d+\.\d+", W.APP_VERSION) is not None,
    W.APP_VERSION)
readme = read(os.path.join(ROOT, "README.md"))
chk("README 里写明了当前版本", W.APP_VERSION in readme, W.APP_VERSION)
# 不许宣传 CI 没验证过的版本组合
m = re.search(r"Python\s*3\.\d+\s*[-–~]\s*3\.\d+", readme)
chk("README 里声明了 Python 版本范围", m is not None,
    m.group(0) if m else "没找到")
if m:
    lo, hi = re.findall(r"3\.(\d+)", m.group(0))[:2]
    chk("版本范围是升序的", int(lo) <= int(hi), m.group(0))
    chk("下限不低于 3.10（代码用了 match 之外的 3.10 语法，保守写 3.10）",
        int(lo) >= 10, m.group(0))

print("== 测试清单 ==")
tests_dir = os.path.join(ROOT, "tests")
have = {f for f in os.listdir(tests_dir)
        if f.startswith("test_") and f.endswith(".py")}
if readme:
    listed = set(re.findall(r"test_\w+\.py", readme))
    miss = sorted(listed - have)
    chk("README 里提到的测试文件都存在", not miss, "不存在 %s" % miss)
    unlisted = sorted(have - listed - {"__init__.py"})
    chk("所有测试文件都在 README 里登记过", not unlisted, "没登记 %s" % unlisted)

# ---------------------------------------------------------------- 3. 代码结构
print("== 同一个 class 里不能有同名方法 ==")
# Python 里后定义的会整个覆盖前一个，功能静默消失 —— 出过一次（搜索框 Esc 失效）
dupes = []
py_files = [p for p in FILES if p.endswith(".py")]
for p in py_files:
    rel = os.path.relpath(p, ROOT).replace("\\", "/")
    try:
        tree = ast.parse(read(p), filename=p)
    except SyntaxError as e:
        chk("%s 语法正确" % rel, False, str(e))
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        seen = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name in seen:
                    dupes.append("%s: %s.%s (行 %d / %d)"
                                 % (rel, node.name, item.name,
                                    seen[item.name], item.lineno))
                else:
                    seen[item.name] = item.lineno
chk("没有重复的方法定义", not dupes, "；".join(dupes[:5]))

print("== 主程序不能被语法/结构问题卡住 ==")
src = read(os.path.join(ROOT, "widget.py"))
tree = ast.parse(src)
classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
chk("Ticker 类只有一处定义", classes.count("Ticker") == 1, classes)
methods = [f.name for n in tree.body if isinstance(n, ast.ClassDef)
           and n.name == "Ticker" for f in n.body
           if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
chk("Ticker 里 eventFilter 只有一个", methods.count("eventFilter") == 1,
    methods.count("eventFilter"))

print("== 不该提交的东西 ==")
for name in ("stocks.json", "backups", "logs"):
    p = os.path.join(ROOT, name)
    rel_name = name
    gi = read(os.path.join(ROOT, ".gitignore"))
    chk(".gitignore 忽略了 %s" % rel_name, rel_name in gi, "")

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
