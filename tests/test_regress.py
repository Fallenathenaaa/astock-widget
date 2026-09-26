# -*- coding: utf-8 -*-
"""综合回归：渲染/Konami/农历/菜单/找窗口/单实例"""
"""综合回归：确认加备份功能后老功能没被碰坏。临时目录，绝不碰真实配置。"""
import io
import json
import os
import re
import sys
import tempfile
import time
import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
import safety_guard  # noqa: E402
from PySide6.QtCore import Qt, QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


tmp = tempfile.mkdtemp(prefix="astock-reg-")
# 关键：测试不能依赖开发者机器上那份真实的 stocks.json。干净 clone 里没有它，
# 测试会假失败；而且万一哪天它格式变了，回归结果就不可信了。一律用默认配置打底。
real_cfg = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "stocks.json")
REAL = None
if os.path.exists(real_cfg):
    with io.open(real_cfg, encoding="utf-8") as f:
        REAL = f.read()          # 只在它存在时留个指纹，最后验它没被改动
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")

CFG = W.validate_config(W.DEFAULT_CONFIG)
CFG["positions"] = {"sh600519": {"cost": 1250.0, "shares": 100}}
with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(json.dumps(CFG, ensure_ascii=False, indent=2))
app = QApplication([])
# 必须在建 Ticker 之前屏蔽：线程真跑起来的话，退出时 Qt 会"QThread destroyed while running" 直接 abort（0xC0000409）
W.Fetcher.start = lambda self: None
W.SparkFetcher.start = lambda self: None
W.Searcher.start = lambda self: None
w = W.Ticker(dict(CFG))


def key(k):
    w._feed_konami(k)


print("== 版本号 ==")
# 别把版本号写死在测试里 —— 每发一版就得改一次，忘了就红。
# 这里只管格式（vX.Y.Z），具体是哪个版本由 widget.py 说了算。
chk("APP_VERSION 形如 vX.Y.Z：%s" % W.APP_VERSION,
    bool(re.fullmatch(r"v\d+\.\d+\.\d+", W.APP_VERSION or "")), W.APP_VERSION)

print("== 渲染冒烟 ==")
w.rows = [
    {"name": "贵州茅台", "code": "600519", "full": "sh600519",
     "price": 1432.5, "change": 12.5, "pct": 0.88, "decimals": 2},
    {"name": "平安银行", "code": "000001", "full": "sz000001",
     "price": 11.32, "change": -0.21, "pct": -1.82, "decimals": 2},
]
try:
    w.resize(w.sizeHint())
    pm = w.grab()
    chk("有数据时能渲染", not pm.isNull() and pm.width() > 0)
    pm.save(os.path.join(tmp, "rows.png"))
    chk("渲染出文件", os.path.exists(os.path.join(tmp, "rows.png")))
except Exception as e:
    chk("有数据时能渲染", False, repr(e))

w.rows = []
try:
    pm2 = w.grab()
    chk("空面板也能渲染", not pm2.isNull())
except Exception as e:
    chk("空面板也能渲染", False, repr(e))

print("== 持仓盈亏 ==")
w.cfg["positions"] = {"sh600519": {"cost": 1250.0, "shares": 100}}
w.rows = [{"name": "贵州茅台", "code": "600519", "full": "sh600519",
           "price": 1432.5, "change": 12.5, "pct": 0.88, "decimals": 2}]
try:
    w.grab()
    chk("带持仓能渲染", True)
except Exception as e:
    chk("带持仓能渲染", False, repr(e))

print("== 备源补上的那行也能画（会挂一个来源小字）==")
w.cfg["data_source"] = "auto"
w.rows = [
    {"name": "贵州茅台", "code": "600519", "full": "sh600519",
     "price": 1432.5, "change": 12.5, "pct": 0.88, "decimals": 2,
     "provider": "tencent"},
    {"name": "宁德时代", "code": "300750", "full": "sz300750",
     "price": 182.4, "change": -1.58, "pct": -0.86, "decimals": 2,
     "provider": "sina"},
]
try:
    w.grab()
    chk("混着两个源能渲染", True)
except Exception as e:
    chk("混着两个源能渲染", False, repr(e))
# 手选新浪时，期望源变成新浪 —— 该标的那行变成腾讯那行，两条路都要能画
w.cfg["data_source"] = "sina"
try:
    w.grab()
    chk("手选源后也能渲染", True)
except Exception as e:
    chk("手选源后也能渲染", False, repr(e))
w.cfg["data_source"] = "auto"
w.rows = []

print("== Konami 口令 ==")
w._unlocked = False
for k in W.KONAMI:
    key(k)
chk("输对 12 键解锁", w._unlocked is True)
chk("解锁写进 cfg", w.cfg.get("unlocked") is True)
for k in W.KONAMI:
    key(k)
chk("再输一次不再收起（只提示）", w._unlocked is True)
w.lock_hidden_menu()
chk("菜单项可以收起", w._unlocked is False)
chk("收起写进 cfg", w.cfg.get("unlocked") is False)
for k in W.KONAMI:
    key(k)
chk("收起后再输口令能重新打开", w._unlocked is True)
key(Qt.Key_Up)
key(Qt.Key_Z)          # 不属于口令的键 → 清空
chk("按错键清空进度", w._konami == [])

print("== 口令 10 秒时限 ==")
w.lock_hidden_menu()
w._konami = []
for k in W.KONAMI[:6]:
    key(k)
chk("按了前 6 个还没解锁", w._unlocked is False)
w._konami_t0 = time.time() - W.KONAMI_TIMEOUT - 1   # 假装中间过了 11 秒
for k in W.KONAMI[6:]:
    key(k)
chk("超时 → 口令作废，不解锁", w._unlocked is False)
w._konami = []
w._konami_t0 = 0.0
for k in W.KONAMI:
    key(k)
chk("一口气输完 → 解锁", w._unlocked is True)
chk("输完把计时清掉", w._konami_t0 == 0.0)

print("== 鼠标连点解锁 ==")
w.lock_hidden_menu()
chk("先锁上", w._unlocked is False)


def tap():
    """在左上角状态点位置点一下"""
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(4.0, 4.0),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.mousePressEvent(ev)


for _ in range(W.DOT_TAP_N - 1):
    tap()
chk("点 %d 次还不够" % (W.DOT_TAP_N - 1), w._unlocked is False)
tap()
chk("点满 %d 次 → 解锁" % W.DOT_TAP_N, w._unlocked is True)
w.lock_hidden_menu()
for _ in range(W.DOT_TAP_N - 1):
    tap()
w._dot_taps_at = time.time() - W.DOT_TAP_WINDOW - 1   # 中间停了超过窗口时间
tap()
chk("点太慢 → 不算数", w._unlocked is False)

# ★ 下面这两段都要求"今天不是触发日"。这个假设**不能依赖真实日期**：
# 放彩蛋的日子是"假期开始前最后一个交易日"，所以一年里有好几天天然就是
# 触发日（临近长假的那几天）。之前没钉日期，于是一到长假前测试就集体变红。
# 这里把日期钉死在远离任何触发日的一天，测的才是判定逻辑本身。
_real_market_now = W.market_clock.market_now
_safe_day = datetime.datetime(2026, 3, 10, 10, 30, 0)
W.market_clock.market_now = lambda: _safe_day
W._fest_cache.clear()
chk("测试用的日期确实不是触发日",
    W.active_festival(today=_safe_day.date()) is None,
    W.active_festival(today=_safe_day.date()))

print("== 强制节日是运行时状态，不落盘 ==")
# 强制开关只活在内存里：崩溃 / 强杀之后下次启动必须回到"按日期自动触发"，
# 不能像以前那样从 stocks.json 里把上次的强制特效读回来。
w.toggle_festival("valentine")
chk("开一个 → 生效", w._festival() is not None and w._festival()["key"] == "valentine",
    w._festival()["key"] if w._festival() else None)
chk("开着的那个不进配置", not any(
    f["key"] + "_test" in w.cfg for f in W.FESTIVALS))
chk("落盘的配置里没有强制开关",
    not any(k.endswith("_test")
            for k in json.loads(io.open(W.CONFIG_PATH, encoding="utf-8").read())))
w.toggle_festival("valentine")
chk("再点一次 = 关掉", w._festival() is None)
w.toggle_festival("midautumn")
w.toggle_festival("national")
chk("同一时刻只留一个（后点的那个）",
    w._festival() is not None and w._festival()["key"] == "national",
    w._festival()["key"] if w._festival() else None)
w.clear_festivals()
chk("全部关闭 → 回到按日期", w._forced_festival is None)

print("== 节日判断 ==")
# _need_anim 还叠了"窗口不可见就不画"这一层，这里单独测节日本身
w._konami_show = 0.0          # 上面敲过口令，进度点还在显示期，会误判成"有动画"
w._forced_festival = None
chk("平时没有节日", w._festival() is None)
w._forced_festival = "midautumn"
chk("强制中秋 → 要动画", w._need_anim() is True)
w._forced_festival = "national"
chk("强制国庆 → 要动画", w._need_anim() is True)
w._forced_festival = "spring"
chk("强制春节 → 要动画", w._need_anim() is True)
w._forced_festival = None
chk("关掉后不要动画", w._need_anim() is False)
w._forced_festival = "midautumn"
chk("藏起来时不画动画（省 CPU）", (w.hide(), w._need_anim())[1] is False)
w._forced_festival = None
# 日期恢复真实值，别影响后面的用例
W.market_clock.market_now = _real_market_now
W._fest_cache.clear()

print("== 清理历史遗留字段 ==")
# 老版本把"强制开启"写进过 stocks.json，新版本要能把这些残留键删掉
for f in W.FESTIVALS:
    w.cfg[f["key"] + "_test"] = True
chk("有残留时能识别", w.clear_forced_festivals() is True)
chk("一个残留键都不剩",
    not any(f["key"] + "_test" in w.cfg for f in W.FESTIVALS))
chk("没残留时不算改动", w.clear_forced_festivals() is False)

print("== 农历 ==")
chk("2026 中秋 = 9/25", str(W.lunar_to_solar(2026, 8, 15)) == "2026-09-25",
    str(W.lunar_to_solar(2026, 8, 15)))
chk("2025 中秋 = 10/6", str(W.lunar_to_solar(2025, 8, 15)) == "2025-10-06",
    str(W.lunar_to_solar(2025, 8, 15)))
chk("2027 春节 = 2/6", str(W.lunar_to_solar(2027, 1, 1)) == "2027-02-06",
    str(W.lunar_to_solar(2027, 1, 1)))
chk("越界返回 None", W.lunar_to_solar(1800, 8, 15) is None)

print("== 菜单 ==")
m = QMenu()
w._unlocked = True
w._build_menu(m)
txts = [a.text() for a in m.actions()]
chk("解锁后有节日特效菜单", "节日特效" in txts, " ".join(txts))
sub_f = [a for a in m.actions() if a.text() == "节日特效"][0].menu()
ftxts = [a.text() for a in sub_f.actions()]
chk("节日特效里每个节日都有开关",
    all(f["name"] in " ".join(ftxts) for f in W.FESTIVALS), " ".join(ftxts))
chk("有配置备份子菜单", "配置备份" in txts)
sub_b = [a for a in m.actions() if a.text() == "配置备份"][0].menu()
chk("备份菜单含崩溃日志入口", any("崩溃日志" in a.text() for a in sub_b.actions()))
w._unlocked = False
m2 = QMenu()
w._build_menu(m2)
txts2 = [a.text() for a in m2.actions()]
chk("未解锁时节日开关不出现", "🌕 中秋节彩蛋（测试）" not in txts2)

print("== 找窗口（不能撞上微信） ==")
chk("不存在的标题返回 0", W.find_widget_window("肯定没有这个标题__xyz") == 0)
h = W.find_widget_window("AShareWidget-Test")
if h:
    pid = W._window_pid(h)
    exe = W._process_name(pid)
    print("  命中 pid=%s exe=%s" % (pid, exe))
    chk("命中的是 python 进程，不是微信", exe.startswith("python"), exe)
else:
    print("  (挂件没在跑，跳过)")

print("== 单实例 ==")
# 不能靠"碰巧有挂件在跑"来测 —— 没人跑的时候这个用例会假失败。
# 改成显式起一个子进程占住 mutex，模拟"已经有一个实例了"。
#
# 名字必须用本进程私有的：用正式名的话，用户一边开着挂件一边跑测试时，
# 真挂件会一直占着那个 mutex，"别人退出后 → 本进程能拿到锁"这两条就必然红，
# 而且只在这台机器上红 —— 典型的"环境一变就随机失败"。
import subprocess  # noqa: E402
import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

_MUTEX = "Local\\AStockWidget-Test-%d" % os.getpid()

_holder = None
try:
    # 让子进程建好 mutex 后**主动打一行**告诉我，而不是靠 sleep 猜。
    # 两个原因：
    #   1) 固定 sleep(1.0) 在慢机器 / CI（没有 .pyc 缓存，Python 冷启动更慢）
    #      上不够，子进程还没建好 mutex，断言就红了 —— 真在干净 checkout 上红过
    #   2) 更麻烦的是 _singleton_check 第一次调用时若 mutex 不存在，会**自己
    #      创建并持有**，之后因为 _held_mutexes 里已有它，永远返回 False ——
    #      所以光把 sleep 加长也救不回来，必须等子进程真的先建好
    _code = ("import ctypes,sys,time;"
             "ctypes.windll.kernel32.CreateMutexW(None, False, %r);"
             "sys.stdout.write('ok\\n');"
             "sys.stdout.flush();"
             "time.sleep(60)" % _MUTEX)
    _holder = subprocess.Popen([sys.executable, "-c", _code],
                               stdout=subprocess.PIPE, text=True)
    _holder.stdout.readline()      # 阻塞到子进程把 mutex 建好为止
    chk("别人占着 mutex → 检测到已有实例", W._singleton_check(_MUTEX) is True)
finally:
    if _holder is not None:
        _holder.terminate()
        try:
            _holder.wait(timeout=5)
        except Exception:
            _holder.kill()
    time.sleep(0.5)          # 等内核把 mutex 收回去

chk("别人退出后 → 本进程能拿到锁", W._singleton_check(_MUTEX) is False)
chk("进程内二次调用不误报自己", W._singleton_check(_MUTEX) is False)
chk("默认用的是挂件正式名", W.SINGLETON_MUTEX == "Local\\AStockWidget-Singleton-v1",
    W.SINGLETON_MUTEX)

print("== 备份 ==")
p = W.snapshot_config(force=True)
chk("能生成快照", bool(p) and os.path.exists(p))
chk("快照目录跟着 CONFIG_PATH", os.path.dirname(p) == os.path.join(tmp, "backups"), p)

print("== 真实配置未被改动 ==")
safety_guard.check_after(chk)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
