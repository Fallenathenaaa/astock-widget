# -*- coding: utf-8 -*-
"""
收盘彩蛋 Demo —— 独立演示窗口，不碰你真实的 stocks.json

- 配置读写全部重定向到系统临时目录
- 强制点亮「燃烧」和「结霜」两种彩蛋，并持续续期（不会 3 分钟后消失）
- 停掉行情线程，用固定示例数据，保证涨幅和彩蛋对得上
"""
import os
import sys
import tempfile
import time

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CWD)
os.chdir(CWD)

import widget  # noqa: E402

# 关键：别读写用户真实配置
widget.CONFIG_PATH = os.path.join(tempfile.gettempdir(), "astock_demo_stocks.json")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SAMPLE = [
    # 红涨 + 燃烧：价格 / 涨跌额 / 涨幅 / 昨收 / 分时 全部自洽
    {"full": "sh600519", "code": "600519", "name": "贵州茅台",
     "price": 1500.00, "change": 87.70, "pct": 6.21, "decimals": 2, "prev": 1412.30,
     "spark": [1412, 1428, 1450, 1465, 1478, 1490, 1500]},
    # 绿跌 + 结霜
    {"full": "sz000001", "code": "000001", "name": "平安银行",
     "price": 11.00, "change": -0.61, "pct": -5.28, "decimals": 2, "prev": 11.61,
     "spark": [11.61, 11.50, 11.38, 11.25, 11.15, 11.05, 11.00]},
    # 对照组：几乎平盘，无彩蛋
    {"full": "sz300750", "code": "300750", "name": "宁德时代",
     "price": 200.00, "change": 1.09, "pct": 0.55, "decimals": 2, "prev": 198.91,
     "spark": [198.9, 199.2, 199.5, 199.8, 200.0, 199.9, 200.0]},
]
IDX = [
    {"name": "上证", "price": 3210.55, "pct": 0.42},
    {"name": "深证", "price": 10150.20, "pct": -0.18},
    {"name": "创业板", "price": 2050.13, "pct": 0.95},
]


def main():
    app = QApplication(sys.argv)

    # 把 Fetcher.start() 替换成 noop —— Ticker.__init__ 末尾启动的行情线程
    # 就不跑了，SAMPLE 数据不会被真实行情覆盖
    widget.Fetcher.start = lambda self: None

    cfg = dict(widget.DEFAULT_CONFIG)
    cfg["title"] = "收盘彩蛋 Demo"
    cfg["codes"] = ["sh600519", "sz000001", "sz300750"]
    cfg["positions"] = {}
    cfg["show_index"] = True
    cfg["bg_alpha"] = 190
    cfg["ui_scale"] = 1.0

    t = widget.Ticker(dict(cfg))
    # 行情线程根本不启动（patch class start 为 noop），rows 不会被真实数据覆盖
    # 这样 SAMPLE 完全生效，红涨绿跌 + 彩蛋一一对应
    t.rows = [dict(r) for r in SAMPLE]
    t.indices = [dict(i) for i in IDX]
    t.err = ""
    t.resize_to_rows()

    t0 = time.time()
    t.effects = {
        "600519": {"type": "fire", "until": time.time() + 180, "t0": t0},
        "000001": {"type": "frost", "until": time.time() + 180, "t0": t0},
    }

    def keep_alive():
        """持续续期，别让彩蛋 3 分钟后消失"""
        now = time.time()
        t.effects = {
            "600519": {"type": "fire", "until": now + 180, "t0": t0},
            "000001": {"type": "frost", "until": now + 180, "t0": t0},
        }

    timer = QTimer()
    timer.timeout.connect(keep_alive)
    timer.start(1000)

    # 放到屏幕右侧偏下，避免和正在运行的主挂件（右上角）重叠
    scr = QApplication.primaryScreen().availableGeometry()
    t.move(scr.right() - t.width() - 24, scr.top() + 320)
    t.show()
    t.setWindowTitle("A股盯盘 · 彩蛋 Demo")
    print("demo 已启动（火焰 + 冰霜），关闭窗口即退出")
    sys.stdout.flush()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
