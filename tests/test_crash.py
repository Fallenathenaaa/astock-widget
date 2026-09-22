# -*- coding: utf-8 -*-
"""崩溃兜底：日志落盘/轮转/三层 hook/main 兜底"""
"""崩溃兜底验证。临时 LOG_DIR / CONFIG_PATH，不碰真实目录，不弹 MessageBox。"""
import ast
import io
import os
import sys
import time
import types
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


tmp = tempfile.mkdtemp(prefix="astock-crash-")
W.LOG_DIR = os.path.join(tmp, "logs")
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")
# 真实 logs/ 可能**已经存在**（用户自己跑过挂件就会建）。
# 所以不能断言"不存在"，只能断言"不是这次测试建的"。
_real_logs = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "logs")
_real_logs_before = os.path.exists(_real_logs)
alerts = []
W._crash_alert = lambda path, exc: alerts.append((path, exc))   # 别真弹窗


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


print("== 1. 写日志 ==")
try:
    raise ValueError("boom-测试异常")
except Exception:
    p = W.write_crash_log(W._crash_text(*sys.exc_info()))
chk("生成日志文件", bool(p) and os.path.exists(p), str(p))
txt = read(p)
chk("含版本号", W.APP_VERSION in txt)
chk("含异常类型", "ValueError" in txt)
chk("含异常信息", "boom-测试异常" in txt)
chk("含 traceback", "Traceback" in txt and os.path.basename(__file__) in txt)
chk("含 Python 版本", "Python" in txt)

print("== 2. 同一秒多份不互相覆盖 ==")
paths = set()
for i in range(3):
    try:
        raise RuntimeError("dup%d" % i)
    except Exception:
        paths.add(W.write_crash_log(W._crash_text(*sys.exc_info())))
chk("3 次生成 3 个不同文件", len(paths) == 3, str(paths))

print("== 3. 轮转：只留 LOG_KEEP 份 ==")
W.LOG_KEEP = 5
for i in range(10):
    try:
        raise RuntimeError("r%d" % i)
    except Exception:
        W.write_crash_log(W._crash_text(*sys.exc_info()))
n = len(W.list_crash_logs())
chk("裁到 5 份", n == 5, str(n))
W.LOG_KEEP = 10

print("== 4. excepthook 落盘 + 提示 ==")
W.LOG_KEEP = 10
before = len(W.list_crash_logs())
alerts.clear()
W.install_crash_handler()
chk("sys.excepthook 已替换", sys.excepthook is W._excepthook)
import threading  # noqa: E402
chk("threading.excepthook 已替换", threading.excepthook is W._thread_excepthook)
try:
    raise KeyError("via hook")
except Exception:
    W._excepthook(*sys.exc_info())
chk("hook 后多一份日志", len(W.list_crash_logs()) == before + 1)
chk("弹窗被触发（测试里被替换成记录）", len(alerts) == 1, str(alerts))
chk("提示里带日志路径", bool(alerts and alerts[0][0]), str(alerts))

print("== 5. 线程异常 hook ==")
before = len(W.list_crash_logs())
holder = {}


def boom():
    raise ValueError("thread boom")


t = threading.Thread(target=boom)
t.start()
t.join()
chk("线程异常也落盘", len(W.list_crash_logs()) == before + 1,
    str(len(W.list_crash_logs())))

print("== 6. main() 兜底不吞 SystemExit ==")
alerts.clear()
orig_run = W._run
W._run = lambda: (_ for _ in ()).throw(RuntimeError("run 炸了"))
try:
    W.main()
    chk("main 捕获异常", False, "没抛 SystemExit")
except SystemExit as e:
    chk("main 捕获异常后退出码 1", e.code == 1, str(e.code))
finally:
    W._run = orig_run
chk("main 也写了日志", any("run 炸了" in read(p) for p in W.list_crash_logs()))
chk("main 也提示了", len(alerts) == 1, str(alerts))

print("== 7. 运行日志：起停 / 断联 / 恢复都留痕 ==")
# 以前只有崩溃日志，"跑一天断没断联"全查不出来 —— 只能靠用户肉眼看界面。
W.LOG_DIR = os.path.join(tmp, "runlogs")
log_path = W._run_log_path()


def run_txt():
    return read(log_path) if os.path.exists(log_path) else ""


f = W.Fetcher()
f._cycles = 10
f._mark_fail("未取到行情")
f._mark_fail("还在失败")          # 连续第二次：还在断着，不该再记一笔
chk("运行日志建出来了", os.path.exists(log_path), log_path)
chk("连续失败只算一次断联", run_txt().count("OUTAGE") == 1, run_txt())
chk("断联原因写进去了", "未取到行情" in run_txt(), run_txt())

f._mark_ok()
chk("恢复记一笔", run_txt().count("RECOVER") == 1, run_txt())
chk("此时断联 1 次", "断联 1 次" in f.health_summary(), f.health_summary())

f._mark_fail("又断了")             # 恢复之后再断，算第二次
chk("第二次断联单独记", run_txt().count("OUTAGE") == 2, run_txt())
chk("断联 2 次", "断联 2 次" in f.health_summary(), f.health_summary())
chk("轮数对得上", "共 10 轮" in f.health_summary(), f.health_summary())
# 退出时还断着 —— health_summary 要把这最后一段也算进去（不然会少报）。
# 等一小会儿，不然累计时长是 0.0 秒，这条断言就变得没意义了。
time.sleep(0.08)
chk("退出时仍断着，最后这段计入时长",
    "累计 0.0 秒" not in f.health_summary(), f.health_summary())

W.write_run_log("SLOW     本轮取数 7.5 秒（源=auto，5 只）")
chk("慢轮次也记", "SLOW" in run_txt(), run_txt())

# 心跳 + 退出钩子：进程"自己没了"时靠这两个区分
#   有 ALIVE 有 EXIT   -> Python 自己走完的
#   有 ALIVE 无 EXIT   -> 被外部强杀（atexit 不会执行）
W._log_alive(123, 4)
chk("心跳写了 ALIVE", "ALIVE" in run_txt(), run_txt())
chk("心跳带轮数和断联次数",
    "共 123 轮" in run_txt() and "断联 4 次" in run_txt(), run_txt())
W._boot_time = time.time() - 600      # 假装跑了 10 分钟
W._log_exit()
chk("退出钩子写了 EXIT", "EXIT" in run_txt(), run_txt())
chk("EXIT 带运行分钟数", "10.0 分钟" in run_txt(), run_txt())
# 轮转：只留 RUN_KEEP 份
rotate_dir = os.path.join(tmp, "rotate")
os.makedirs(rotate_dir, exist_ok=True)
W.LOG_DIR = rotate_dir
for i in range(W.RUN_KEEP + 4):
    with io.open(os.path.join(rotate_dir, "run-2026%02d01.log" % (i + 1)),
                 "w", encoding="utf-8") as fh:
        fh.write("x")
W._rotate_run_logs()
left = os.listdir(rotate_dir)
chk("运行日志也轮转", len(left) == W.RUN_KEEP, len(left))
W.LOG_DIR = os.path.join(tmp, "logs")

print("== 8. 日志目录跟着 LOG_DIR 走 ==")
chk("日志都在临时目录", all(os.path.dirname(p) == W.LOG_DIR for p in W.list_crash_logs()))
chk("没在真实目录建 logs/",
    (not os.path.exists(_real_logs)) or _real_logs_before,
    "测试之前有=%s，现在有=%s" % (_real_logs_before, os.path.exists(_real_logs)))

print("== 9. 重复启动：提示之后必须硬退出（不留僵尸）==")
# 以前这里是 `return`：关掉提示框之后进程不走完退出流程，留着 1 个空线程、
# 5 MB 内存、0 个窗口 STILL_ACTIVE 挂着 —— 每重复启动一次就多一个僵尸。
# 现在必须是 os._exit(0)。
real_ctypes = W.ctypes
real_os = W.os
real_single = W._singleton_check
real_front = W._bring_existing_to_front
boxes = []
exits = []


class _FakeUser32(object):
    def MessageBoxW(self, *a):
        boxes.append(a)
        return 1                       # 别真弹窗
    def __getattr__(self, n):
        return getattr(real_ctypes.windll.user32, n)


class _FakeWindll(object):
    user32 = _FakeUser32()
    def __getattr__(self, n):
        return getattr(real_ctypes.windll, n)


class _FakeOS(object):
    def __init__(self, real):
        object.__setattr__(self, "_real", real)
    def _exit(self, code):
        exits.append(code)
        raise SystemExit(code)         # 把硬退出变成可观测的异常
    def __getattr__(self, n):
        return getattr(object.__getattribute__(self, "_real"), n)


W.ctypes = types.SimpleNamespace(windll=_FakeWindll(),
                                 wintypes=real_ctypes.wintypes)
W.os = _FakeOS(real_os)
W._singleton_check = lambda: True      # 模拟"已经有一个实例在跑"
W._bring_existing_to_front = lambda: None
try:
    W._run()
    chk("单例命中后必须退出", False, "没退出 —— 会留僵尸进程")
except SystemExit as e:
    chk("单例命中后硬退出", e.code == 0, e.code)
finally:
    W.ctypes = real_ctypes
    W.os = real_os
    W._singleton_check = real_single
    W._bring_existing_to_front = real_front
chk("提示了用户「已在运行」", len(boxes) == 1, boxes)
chk("用的是 os._exit 而不是 return", len(exits) == 1 and exits[0] == 0, exits)

print("== 10. 启动路径的结构（AST 静态检查）==")
# 今天真踩过：把 def _run() 误缩进成 main() 的嵌套函数 —— main() 一进来
# 调它就 UnboundLocalError，挂件根本起不来。而且顺着往下改还会把
# QApplication / app.exec() 提到模块级，于是 import widget 就跑整个启动流程。
# 这种错跑起来才发现，所以在这里钉死。
_src_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "widget.py")
_tree = ast.parse(io.open(_src_path, encoding="utf-8").read())
_top = {n.name for n in _tree.body if isinstance(n, ast.FunctionDef)}
chk("main 在模块顶层", "main" in _top, sorted(_top)[:8])
chk("_run 在模块顶层", "_run" in _top, sorted(_top)[:8])

_nested = []
for _p in ast.walk(_tree):
    if isinstance(_p, ast.FunctionDef) and _p.name != "_run":
        for _c in ast.walk(_p):
            if isinstance(_c, ast.FunctionDef) and _c.name == "_run":
                _nested.append(_p.name)
chk("_run 没有被嵌套进别的函数", not _nested, _nested)

_BAD_CALLS = ("QApplication", "load_config", "snapshot_config", "save_config")
_mod_level = []
for _n in _tree.body:
    if isinstance(_n, ast.Expr) and isinstance(_n.value, ast.Call):
        _fn = _n.value.func
        _nm = getattr(_fn, "id", None) or getattr(_fn, "attr", None)
        if _nm in _BAD_CALLS:
            _mod_level.append("%s(行 %d)" % (_nm, _n.lineno))
chk("模块级没有启动代码", not _mod_level, _mod_level)

chk("__main__ 守卫还在",
    any(isinstance(_n, ast.If) and "__name__" in ast.dump(_n)
        for _n in _tree.body))

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
