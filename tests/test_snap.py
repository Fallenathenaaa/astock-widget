# -*- coding: utf-8 -*-
"""边缘吸附：四边/阈值边界/四角/开关/多显示器"""
"""边缘吸附验证。临时配置，不碰真实 stocks.json。"""
import io
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


tmp = tempfile.mkdtemp(prefix="astock-snap-")
real_cfg = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "stocks.json")
with io.open(real_cfg, encoding="utf-8") as f:
    REAL = f.read()
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")
with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(REAL)

app = QApplication([])
W.Fetcher.start = lambda self: None    # 同上：别让线程在退出时把进程 abort 掉
W.Searcher.start = lambda self: None
cfg = dict(W.DEFAULT_CONFIG)
cfg["snap"] = True
w = W.Ticker(cfg)
W.Fetcher.start = lambda self: None

g = QApplication.primaryScreen().availableGeometry()
ww, wh = w.width(), w.height()
print("  屏幕可用区 %dx%d @ (%d,%d)，挂件 %dx%d，吸附阈值 %d"
      % (g.width(), g.height(), g.x(), g.y(), ww, wh, W.SNAP_MARGIN))
chk("挂件比屏幕小（否则吸附无从谈起）", ww < g.width() and wh < g.height())

MID_X = g.left() + (g.width() - ww) // 2
MID_Y = g.top() + (g.height() - wh) // 2

print("== 1. 左右吸附 ==")
chk("贴左边：left+5 → left", w.snap_pos(g.left() + 5, MID_Y)[0] == g.left(),
    str(w.snap_pos(g.left() + 5, MID_Y)))
chk("贴右边：right-w-5 → right-w",
    w.snap_pos(g.right() - ww - 5, MID_Y)[0] == g.right() - ww,
    str(w.snap_pos(g.right() - ww - 5, MID_Y)))
chk("刚好在阈值上吸附（=SNAP_MARGIN）",
    w.snap_pos(g.left() + W.SNAP_MARGIN, MID_Y)[0] == g.left())
chk("超出阈值不吸附（+1）",
    w.snap_pos(g.left() + W.SNAP_MARGIN + 1, MID_Y)[0] == g.left() + W.SNAP_MARGIN + 1)
chk("中间位置原样不动", w.snap_pos(MID_X, MID_Y) == (MID_X, MID_Y))

print("== 2. 上下吸附 ==")
chk("贴顶部：top+5 → top", w.snap_pos(MID_X, g.top() + 5)[1] == g.top(),
    str(w.snap_pos(MID_X, g.top() + 5)))
chk("贴底部：bottom-h-5 → bottom-h",
    w.snap_pos(MID_X, g.bottom() - wh - 5)[1] == g.bottom() - wh,
    str(w.snap_pos(MID_X, g.bottom() - wh - 5)))
chk("中间高度原样不动", w.snap_pos(MID_X, MID_Y)[1] == MID_Y)

print("== 3. 四角同时吸 ==")
chk("左上角", w.snap_pos(g.left() + 3, g.top() + 3) == (g.left(), g.top()))
chk("右下角", w.snap_pos(g.right() - ww - 3, g.bottom() - wh - 3)
    == (g.right() - ww, g.bottom() - wh))

print("== 4. 关掉吸附 ==")
w.cfg["snap"] = False
chk("snap=False 完全不吸", w.snap_pos(g.left() + 3, g.top() + 3) == (g.left() + 3, g.top() + 3))
w.cfg["snap"] = True
_old = W.SNAP_MARGIN
W.SNAP_MARGIN = 0
chk("SNAP_MARGIN=0 不吸", w.snap_pos(g.left() + 3, g.top() + 3) == (g.left() + 3, g.top() + 3))
W.SNAP_MARGIN = _old

print("== 5. 传光标点时也不崩 ==")
try:
    r = w.snap_pos(g.left() + 5, g.top() + 5, QPoint(g.left() + 5, g.top() + 5))
    chk("带 cursor 参数能算", r == (g.left(), g.top()), str(r))
except Exception as e:
    chk("带 cursor 参数能算", False, repr(e))

print("== 6. 菜单开关 ==")
w.cfg["snap"] = True
w.toggle_snap()
chk("关掉", w.cfg["snap"] is False)
w.toggle_snap()
chk("再打开", w.cfg["snap"] is True)
import json  # noqa: E402
with io.open(W.CONFIG_PATH, encoding="utf-8") as f:
    chk("写进配置文件", json.load(f).get("snap") is True)

print("== 7. 真实配置未被改动 ==")
chk("真实 stocks.json 原样", io.open(real_cfg, encoding="utf-8").read() == REAL)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
