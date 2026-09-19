# -*- coding: utf-8 -*-
"""代码自检：未使用的 import / 未被引用的模块级名字 / 语法编译。

用法：python tools/selfcheck.py
"""
import ast
import os
import sys
import shutil
import tempfile
import py_compile

# 同上：Windows 控制台不默认 UTF-8，打中文会 UnicodeEncodeError（CI 上踩过）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TMPDIR = tempfile.mkdtemp(prefix="selfcheck-")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

TARGET = sys.argv[1] if len(sys.argv) > 1 else "widget.py"
src = open(TARGET, "r", encoding="utf-8").read()
tree = ast.parse(src, filename=TARGET)

# ---- 1. 收集 import 的名字 ----
imported = {}          # 绑定名 -> lineno
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        for a in n.names:
            imported[(a.asname or a.name).split(".")[0]] = n.lineno
    elif isinstance(n, ast.ImportFrom):
        for a in n.names:
            if a.name != "*":
                imported[a.asname or a.name] = n.lineno

# ---- 2. 收集所有"用到"的名字（含字符串里的 getattr 无法静态查，忽略） ----
used = set()
for n in ast.walk(tree):
    if isinstance(n, ast.Name):
        used.add(n.id)
    elif isinstance(n, ast.Attribute):
        cur = n
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if isinstance(cur, ast.Name):
            used.add(cur.id)

# 类型注解 / 装饰器 / 全局语句
for n in ast.walk(tree):
    if isinstance(n, ast.arg) and n.annotation is not None:
        for s in ast.walk(n.annotation):
            if isinstance(s, ast.Name):
                used.add(s.id)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        for d in n.decorator_list:
            for s in ast.walk(d):
                if isinstance(s, ast.Name):
                    used.add(s.id)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns:
            for s in ast.walk(n.returns):
                if isinstance(s, ast.Name):
                    used.add(s.id)

dead = [(k, v) for k, v in imported.items() if k not in used]
print("== 1. 未使用的 import ==")
if dead:
    for k, v in sorted(dead, key=lambda x: x[1]):
        print("   行 %-5d %s" % (v, k))
else:
    print("   无")

# ---- 3. 模块级函数/常量：定义了但全文件没第二次出现 ----
def text_hits(name):
    """粗略：源码里这个名字出现的次数（定义 1 次 + 引用 N 次）"""
    return src.count(name)

top_defs = []
for n in tree.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_defs.append(("函数", n.name, n.lineno))
    elif isinstance(n, ast.ClassDef):
        top_defs.append(("类", n.name, n.lineno))
    elif isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                top_defs.append(("常量", t.id, n.lineno))

orphan = []
for kind, name, ln in top_defs:
    # 名字在源码里出现 <=1 次 = 只有定义处
    if text_hits(name) <= 1:
        orphan.append((kind, name, ln))

print("\n== 2. 定义了但从未引用的顶层名字 ==")
if orphan:
    for kind, name, ln in sorted(orphan, key=lambda x: x[2]):
        print("   行 %-5d %s %s" % (ln, kind, name))
else:
    print("   无")

# ---- 4. 编译检查 ----
print("\n== 3. 编译检查 ==")
ok = True
for f in [TARGET] + ["tests/%s" % x for x in sorted(os.listdir("tests")) if x.endswith(".py")] \
        + ["tools/%s" % x for x in sorted(os.listdir("tools")) if x.endswith(".py")] \
        + ["run_tests.py", "demo.py"]:
    if not os.path.exists(f):
        continue
    try:
        # Windows 上 cfile=os.devnull 会被 py_compile 拒绝，丢到临时目录
        py_compile.compile(f, doraise=True,
                           cfile=os.path.join(TMPDIR, os.path.basename(f) + "c"))
    except Exception as e:
        ok = False
        print("   FAIL %s : %s" % (f, e))
print("   全部编译通过" if ok else "   有文件编译失败")

# ---- 5. 过长的函数 ----
print("\n== 4. 超过 120 行的函数（可读性的债） ==")
longs = []
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        span = (n.end_lineno or n.lineno) - n.lineno + 1
        if span > 120:
            longs.append((span, n.name, n.lineno))
if longs:
    for span, name, ln in sorted(longs, reverse=True):
        print("   行 %-5d %-28s %d 行" % (ln, name, span))
else:
    print("   无")

shutil.rmtree(TMPDIR, ignore_errors=True)
print("\n自检完成。")
