# -*- coding: utf-8 -*-
"""综合回归：渲染/Konami/农历/菜单/找窗口/单实例"""
"""综合回归：确认加备份功能后老功能没被碰坏。临时目录，绝不碰真实配置。"""
import io
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
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
real_cfg = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "stocks.json")
with io.open(real_cfg, encoding="utf-8") as f:
    REAL = f.read()
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")
with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(REAL)

CFG = json.loads(REAL)
CFG["positions"] = {"sh600519": {"cost": 1250.0, "shares": 100}}
app = QApplication([])
# 必须在建 Ticker 之前屏蔽：线程真跑起来的话，退出时 Qt 会"QThread destroyed while running" 直接 abort（0xC0000409）
W.Fetcher.start = lambda self: None
W.Searcher.start = lambda self: None
w = W.Ticker(dict(CFG))


def key(k):
    w._feed_konami(k)


print("== 版本号 ==")
chk("APP_VERSION = v2.0.1", W.APP_VERSION == "v2.0.1", W.APP_VERSION)

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

print("== 退出清空强制特效 ==")
w.cfg["valentine_test"] = True
w.cfg["christmas_test"] = True
changed = w.clear_forced_festivals()
chk("退出时清掉了强制开关", changed is True)
chk("一个强制开关都不剩",
    not any(w.cfg.get(f["key"] + "_test") for f in W.FESTIVALS))
chk("没开开关时不算改动", w.clear_forced_festivals() is False)
for f in W.FESTIVALS:
    w.cfg[f["key"] + "_test"] = True
w.clear_forced_festivals()
chk("全开也能一次清干净",
    not any(w.cfg.get(f["key"] + "_test") for f in W.FESTIVALS))

print("== 节日判断 ==")
w.cfg.update({"midautumn_test": False, "national_test": False, "spring_test": False})
w._konami_show = 0.0          # 上面敲过口令，进度点还在显示期，会误判成"有动画"
chk("平时不开动画", w._need_anim() is False)
w.cfg["midautumn_test"] = True
chk("中秋测试 → 要动画", w._need_anim() is True)
w.cfg["midautumn_test"] = False
w.cfg["national_test"] = True
chk("国庆测试 → 要动画", w._need_anim() is True)
w.cfg["national_test"] = False
w.cfg["spring_test"] = True
chk("春节测试 → 要动画", w._need_anim() is True)
w.cfg["spring_test"] = False

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
import subprocess  # noqa: E402
import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

_holder = None
try:
    _code = ("import ctypes,time;"
             "ctypes.windll.kernel32.CreateMutexW(None, False,"
             " 'Local\\\\AStockWidget-Singleton-v1');"
             "time.sleep(60)")
    _holder = subprocess.Popen([sys.executable, "-c", _code])
    time.sleep(1.0)          # 等子进程把 mutex 建好
    chk("别人占着 mutex → 检测到已有实例", W._singleton_check() is True)
finally:
    if _holder is not None:
        _holder.terminate()
        try:
            _holder.wait(timeout=5)
        except Exception:
            _holder.kill()
    time.sleep(0.5)          # 等内核把 mutex 收回去

chk("别人退出后 → 本进程能拿到锁", W._singleton_check() is False)
chk("进程内二次调用不误报自己", W._singleton_check() is False)

print("== 备份 ==")
p = W.snapshot_config(force=True)
chk("能生成快照", bool(p) and os.path.exists(p))
chk("快照目录跟着 CONFIG_PATH", os.path.dirname(p) == os.path.join(tmp, "backups"), p)

print("== 真实配置未被改动 ==")
chk("真实 stocks.json 原样", io.open(real_cfg, encoding="utf-8").read() == REAL)
real_bak = os.path.join(os.path.dirname(real_cfg), "backups")
_before = set(os.listdir(real_bak)) if os.path.isdir(real_bak) else set()
chk("真实 backups/ 未被测试新增文件",
    (set(os.listdir(real_bak)) if os.path.isdir(real_bak) else set()) == _before,
    "前后不一致")

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
