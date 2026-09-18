# -*- coding: utf-8 -*-
"""节日特效实时预览器 —— 不用等节日当天，现在就能看全部飘落效果。

用法：python tools/preview_festival.py
      python tools/preview_festival.py --shot out.png   （渲染一帧存图，用来出文档配图）

操作：
  ← → / 空格   切换上一个 / 下一个
  1 ~ 9        直接跳到第 n 种
  A            自动轮播（每 6 秒换一个）
  Esc / Q      退出

复用 widget.py 里的 FESTIVALS / FALL_DRAW / draw_falling，
所以这里看到的就是挂件里真实会画的样子（同样的 20fps、同样的轨道算法）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import widget as W
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


def init_fonts(app):
    """offscreen 平台不会自动加载系统字体 —— 中文会渲染成方块。
    真机运行时 Qt 会自动用系统字体，不用管。"""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    paths = [
        "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑（首选）
        "C:/Windows/Fonts/msyhl.ttc",    # 微软雅黑 Light
        "C:/Windows/Fonts/simhei.ttf",   # 黑体（fallback）
        "C:/Windows/Fonts/seguiemj.ttf", # Segoe UI Emoji（emoji 兜底）
    ]
    for p in paths:
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei", 10))


def build_rows():
    """同一种飘落物只留一格，但把用它的节日名都列出来"""
    order = []
    by_fall = {}
    for f in W.FESTIVALS:
        fall = f["fall"]
        if fall not in by_fall:
            by_fall[fall] = []
            order.append(fall)
        by_fall[fall].append(f)
    return [(fall, by_fall[fall]) for fall in order]


def trigger_text(festivals, year=None):
    """把这些节日的触发日拼成一行字"""
    import datetime
    year = year or datetime.date.today().year
    parts = []
    for f in festivals:
        days = W.festival_trigger_days(f, year)
        if days:
            parts.append("%s %s" % (f["icon"], "-".join(d.strftime("%m-%d") for d in days)))
    return "   ".join(parts) if parts else "今年不触发"


class Preview(QWidget):
    WIDTH, HEIGHT = 380, 240
    AUTO_MS = 6000

    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.idx = 0
        self.auto = False
        self.setWindowTitle("节日特效预览  ·  A股盯盘挂件")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        # 20fps —— 和挂件里 ANIM_TICK_MS 一致，看到的就是真实帧率
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(50)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.next_one)
        self.update_title()

    def update_title(self):
        fall, festivals = self.rows[self.idx]
        names = " / ".join(f["name"] for f in festivals)
        extra = "  [自动轮播]" if self.auto else ""
        self.setWindowTitle("%s%s   （%d/%d）" % (names, extra, self.idx + 1, len(self.rows)))

    def next_one(self):
        self.idx = (self.idx + 1) % len(self.rows)
        self.update_title()
        self.update()

    def prev_one(self):
        self.idx = (self.idx - 1) % len(self.rows)
        self.update_title()
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space):
            self.next_one()
        elif k in (Qt.Key_Left, Qt.Key_Up):
            self.prev_one()
        elif k == Qt.Key_A:
            self.auto = not self.auto
            if self.auto:
                self.auto_timer.start(self.AUTO_MS)
            else:
                self.auto_timer.stop()
            self.update_title()
        elif k in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        elif Qt.Key_1 <= k <= Qt.Key_9:
            n = k - Qt.Key_1
            if n < len(self.rows):
                self.idx = n
                self.update_title()
                self.update()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _e):
        fall, festivals = self.rows[self.idx]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(16, 17, 22))
        draw_one = W.FALL_DRAW[fall]
        cnt = festivals[0].get("count", 14)
        W.draw_falling(p, self.WIDTH, self.HEIGHT - 34, draw_one, cnt)

        # 底部信息条
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(22, 24, 30))
        p.drawRect(QRectF(0, self.HEIGHT - 34, self.WIDTH, 34))
        p.setPen(QPen(QColor(120, 126, 136), 1))
        p.drawLine(0, self.HEIGHT - 34, self.WIDTH, self.HEIGHT - 34)
        p.setPen(QColor(214, 219, 226))
        p.setFont(QFont("Microsoft YaHei", 10))
        names = " / ".join(("%s %s" % (f["icon"], f["name"])) for f in festivals)
        p.drawText(QRectF(10, self.HEIGHT - 30, self.WIDTH - 20, 17), Qt.AlignLeft, names)
        p.setPen(QColor(138, 144, 154))
        p.setFont(QFont("Microsoft YaHei", 8))
        p.drawText(QRectF(10, self.HEIGHT - 15, self.WIDTH - 20, 14), Qt.AlignLeft,
                   trigger_text(festivals))
        p.end()


def main():
    shot = None
    shot_idx = 0
    if "--shot" in sys.argv:
        i = sys.argv.index("--shot")
        if i + 1 < len(sys.argv):
            shot = sys.argv[i + 1]
    if "--idx" in sys.argv:
        i = sys.argv.index("--idx")
        if i + 1 < len(sys.argv):
            shot_idx = int(sys.argv[i + 1])

    app = QApplication(sys.argv)
    init_fonts(app)
    rows = build_rows()
    w = Preview(rows)
    if 0 <= shot_idx < len(rows):
        w.idx = shot_idx
        w.update_title()

    if shot:
        offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        if not offscreen:
            w.show()
            app.processEvents()
        img = w.grab()
        img.save(shot)
        print("SAVED", shot, img.width(), "x", img.height(),
              " idx=%d (%s)" % (shot_idx, rows[shot_idx][0]))
        return 0

    w.show()
    print("共 %d 种飘落物。← → 切换，1-9 直达，A 自动轮播，Esc 退出。" % len(rows))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
