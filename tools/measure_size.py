# -*- coding: utf-8 -*-
"""自身体积报告生成器。

用法：python tools/measure_size.py
输出一份 markdown 表格，可以直接贴进 README 的「体积」章节。
"""
# -*- coding: utf-8 -*-
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def du(d):
    n, c = 0, 0
    for dp, _, fs in os.walk(d):
        for f in fs:
            n += size(os.path.join(dp, f))
            c += 1
    return n, c


def kb(n):
    return "%.1f KB" % (n / 1024.0)


def count_lines(p):
    """总行 / 空行 / 注释行 / 有效代码行"""
    total = blank = comment = 0
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            total += 1
            s = ln.strip()
            if not s:
                blank += 1
            elif s.startswith("#"):
                comment += 1
    return total, blank, comment, total - blank - comment


print("=" * 62)
print("体积报告  根目录：%s" % ROOT)
print("=" * 62)

wp = "widget.py"
wt, wblk, wcmt, wcode = count_lines(wp)
print("\n## 主程序\n")
print("| 项目 | 数值 |")
print("|---|---|")
print("| `widget.py` 源文件 | %s（%d 行） |" % (kb(size(wp)), wt))
print("| ├ 有效代码行 | %d 行 |" % wcode)
print("| ├ 注释行 | %d 行（%.0f%%） |" % (wcmt, 100.0 * wcmt / wt))
print("| └ 空行 | %d 行 |" % wblk)
for cand in ("__pycache__/widget.cpython-313.pyc", "__pycache__/widget.cpython-311.pyc"):
    if os.path.exists(cand):
        print("| 编译字节码 `%s` | %s（运行缓存，可删） |" % (cand, kb(size(cand))))
        break

print("\n## 目录\n")
print("| 目录 | 大小 | 文件数 | 说明 |")
print("|---|---|---|---|")
tests_n, tests_c = du("tests")
tools_n, tools_c = du("tools")
shot_n, shot_c = du("screenshots")
print("| `tests/` | %s | %d | 回归测试，日常运行不需要 |" % (kb(tests_n), tests_c))
print("| `tools/` | %s | %d | 体积/占用/预览图脚本 |" % (kb(tools_n), tools_c))
print("| `screenshots/` | %s | %d | 文档配图，只给 README 看 |" % (kb(shot_n), shot_c))

# git 仓库体积
git_dir = ".git"
if os.path.isdir(git_dir):
    g, gc = du(git_dir)
    print("| `.git/` | %s | %d | 版本历史 |" % (kb(g), gc))

print("\n## 真正跑起来需要的\n")
need = size(wp) + size("stocks.json")
print("- `widget.py` %s + `stocks.json` %s = **%s**" % (kb(size(wp)), kb(size("stocks.json")), kb(need)))
print("- 不算 PySide6 运行时（那是环境依赖，不是本项目的体积）")

# 代码行数明细
print("\n## 各文件行数\n")
print("| 文件 | 行数 | 说明 |")
print("|---|---|---|")
files = [("widget.py", "主程序"),
         ("run_tests.py", "测试运行器"),
         ("demo.py", "演示脚本")]
for f, desc in files:
    if os.path.exists(f):
        print("| `%s` | %d | %s |" % (f, count_lines(f)[0], desc))
for f in sorted(os.listdir("tests")):
    p = os.path.join("tests", f)
    if os.path.isfile(p) and f.endswith(".py"):
        print("| `tests/%s` | %d | 测试 |" % (f, count_lines(p)[0]))
for f in sorted(os.listdir("tools")):
    p = os.path.join("tools", f)
    if os.path.isfile(p):
        print("| `tools/%s` | %d | 工具 |" % (f, count_lines(p)[0]))

# 运行时内存快照（挂件开着才拿得到）
print("\n## 运行时内存\n")
try:
    import ctypes
    import ctypes.wintypes as w
    import widget as W

    h = W.find_widget_window("AShareWidget-Test")
    if not h:
        print("- 挂件没在跑，跳过内存快照")
    else:
        k32, p32 = ctypes.windll.kernel32, ctypes.windll.psapi

        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        hp = k32.OpenProcess(0x1010, False, W._window_pid(h))
        if hp:
            p32.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
            p32.GetProcessMemoryInfo.restype = ctypes.c_bool
            c = PMC()
            c.cb = ctypes.sizeof(c)
            p32.GetProcessMemoryInfo(hp, ctypes.byref(c), ctypes.sizeof(c))
            mb = 1048576.0
            print("| 指标 | 数值 |")
            print("|---|---|")
            print("| 当前工作集 RSS | %.1f MB |" % (c.WorkingSetSize / mb))
            print("| 峰值工作集 | %.1f MB |" % (c.PeakWorkingSetSize / mb))
            print("| 提交内存 Pagefile | %.1f MB |" % (c.PagefileUsage / mb))
            print("| 峰值提交内存 | %.1f MB |" % (c.PeakPagefileUsage / mb))
            print("| 缺页次数 | %d |" % c.PageFaultCount)
            k32.CloseHandle(hp)
except Exception as e:
    print("- 内存快照失败：%r" % (e,))

print("\n完成。")
