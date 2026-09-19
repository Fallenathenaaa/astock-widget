# -*- coding: utf-8 -*-
"""重新生成节日彩蛋截图（乱码修复版）。

v1.x 那批 300x208 的节日截图是 offscreen 渲染的，没加载系统字体，
中文和 emoji 全画成了空心方块。这个脚本注入字体后重新生成，
并合成到深/浅背景上（原来文件名里的 dark / light 就是背景明暗）。

用法：python tools/shot_effect.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import widget as W  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QImage,  # noqa: E402
                           QPainter)
from PySide6.QtWidgets import QApplication  # noqa: E402


def init_fonts(app):
    """offscreen 平台不自动加载系统字体 —— 中文/emoji 会渲染成方块"""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    for p in ("C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/msyhl.ttc",
              "C:/Windows/Fonts/simhei.ttf",
              "C:/Windows/Fonts/seguiemj.ttf"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei", 9))


# 示例行情（公开示例，不是任何人的真实持仓）
ROWS = [
    {"name": "贵州茅台", "code": "600519", "full": "sh600519",
     "price": 1432.5, "change": 12.5, "pct": 0.88, "decimals": 2},
    {"name": "平安银行", "code": "000001", "full": "sz000001",
     "price": 11.32, "change": -0.21, "pct": -1.82, "decimals": 2},
]

# (输出文件名, 节日 key, 背景明暗, bg_alpha)
JOBS = [
    ("midautumn-v2-dark-0.png", "midautumn", "dark", 0),
    ("midautumn-v2-dark-75.png", "midautumn", "dark", 191),
    ("midautumn-v2-light-0.png", "midautumn", "light", 0),
    ("national-dark-0.png", "national", "dark", 0),
    ("national-dark-75.png", "national", "dark", 191),
    ("national-light-0.png", "national", "light", 0),
    ("spring-dark-0.png", "spring", "dark", 0),
    ("spring-dark-75.png", "spring", "dark", 191),
    ("spring-light-0.png", "spring", "light", 0),
]

BG = {"dark": QColor(24, 25, 30), "light": QColor(238, 240, 244)}

# 收盘彩蛋 demo 图：火焰 + 冰霜（数据取自 demo.py 的示例，非真实持仓）
DEMO_ROWS = [
    {"full": "sh600519", "code": "600519", "name": "贵州茅台",
     "price": 1500.00, "change": 87.70, "pct": 6.21, "decimals": 2, "prev": 1412.30,
     "spark": [1412, 1428, 1450, 1465, 1478, 1490, 1500]},
    {"full": "sz000001", "code": "000001", "name": "平安银行",
     "price": 11.00, "change": -0.61, "pct": -5.28, "decimals": 2, "prev": 11.61,
     "spark": [11.61, 11.50, 11.38, 11.25, 11.15, 11.05, 11.00]},
    {"full": "sz300750", "code": "300750", "name": "宁德时代",
     "price": 200.00, "change": 1.09, "pct": 0.55, "decimals": 2, "prev": 198.91,
     "spark": [198.9, 199.2, 199.5, 199.8, 200.0, 199.9, 200.0]},
]
DEMO_IDX = [
    {"name": "上证", "price": 3210.55, "pct": 0.42},
    {"name": "深证", "price": 10150.20, "pct": -0.18},
    {"name": "创业板", "price": 2050.13, "pct": 0.95},
]


def shot_demo(outdir):
    """收盘彩蛋（火焰 + 冰霜）截图"""
    import time
    cfg = dict(W.DEFAULT_CONFIG)
    cfg["title"] = "收盘彩蛋 Demo"
    cfg["codes"] = ["sh600519", "sz000001", "sz300750"]
    cfg["bg_alpha"] = 190
    w = W.Ticker(cfg)
    w.rows = [dict(r) for r in DEMO_ROWS]
    w.indices = [dict(i) for i in DEMO_IDX]
    w.err = ""
    w.resize_to_rows()
    t0 = time.time()
    w.effects = {
        "600519": {"type": "fire", "until": t0 + 180, "t0": t0},
        "000001": {"type": "frost", "until": t0 + 180, "t0": t0},
    }
    pm = w.grab()
    img = QImage(pm.width(), pm.height(), QImage.Format_RGB32)
    img.fill(QColor(24, 25, 30))
    p = QPainter(img)
    p.drawPixmap(0, 0, pm)
    p.end()
    out = os.path.join(outdir, "preview-demo.png")
    img.save(out)
    print("SAVED %-30s %dx%d" % ("preview-demo.png", img.width(), img.height()))
    w.close()
    del w


def main():
    app = QApplication(sys.argv)
    init_fonts(app)

    tmp = tempfile.mkdtemp(prefix="astock-shot-")
    W.CONFIG_PATH = os.path.join(tmp, "stocks.json")
    # 必须在建 Ticker 之前屏蔽：线程跑起来退出时 Qt 会 abort（0xC0000409）
    W.Fetcher.start = lambda self: None
    W.Searcher.start = lambda self: None

    outdir = os.path.join(ROOT, "screenshots")
    os.makedirs(outdir, exist_ok=True)

    for fname, fest, bg, alpha in JOBS:
        cfg = dict(W.DEFAULT_CONFIG)
        cfg[fest + "_test"] = True
        cfg["bg_alpha"] = alpha
        cfg["codes"] = ["sh600519", "sz000001"]
        cfg["show_index"] = True

        w = W.Ticker(cfg)
        w.rows = [dict(r) for r in ROWS]
        w.resize(w.sizeHint())
        pm = w.grab()

        # 合成到背景上（挂件是半透明的，原图 dark/light 就是背后的桌面明暗）
        img = QImage(pm.width(), pm.height(), QImage.Format_RGB32)
        img.fill(BG[bg])
        p = QPainter(img)
        p.drawPixmap(0, 0, pm)
        p.end()

        out = os.path.join(outdir, fname)
        img.save(out)
        print("SAVED %-30s %dx%d" % (fname, img.width(), img.height()))
        w.close()
        del w

    shot_demo(outdir)

    print("\n完成。用 tools/detect_garbled.py 复查是否还有方块。")


if __name__ == "__main__":
    main()