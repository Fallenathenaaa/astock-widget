# -*- coding: utf-8 -*-
"""崩溃兜底：日志落盘/轮转/三层 hook/main 兜底"""
"""崩溃兜底验证。临时 LOG_DIR / CONFIG_PATH，不碰真实目录，不弹 MessageBox。"""
import io
import os
import sys
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

print("== 7. 日志目录跟着 LOG_DIR 走 ==")
chk("日志都在临时目录", all(os.path.dirname(p) == W.LOG_DIR for p in W.list_crash_logs()))
real = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "logs")
chk("没在真实目录建 logs/", not os.path.exists(real))

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
