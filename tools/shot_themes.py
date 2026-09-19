# -*- coding: utf-8 -*-
"""把各种飘落物各画一格，拼成一张预览图。

用法：python tools/shot_themes.py   （需要能 import PySide6）
输出到 local-shots/themes-all.png
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 脚本在 tools/ 下，widget.py 在上一级
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication


def init_fonts(app):
    """offscreen 平台不自动加载系统字体 —— 中文会渲染成方块"""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    for p in ("C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/msyhl.ttc",
              "C:/Windows/Fonts/simhei.ttf",
              "C:/Windows/Fonts/seguiemj.ttf"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei", 9))

CELL_W, CELL_H = 200, 130
COLS = 3
# 同一种飘落物只画一格（春节和跨年都是红包）
seen = set()
rows = []
for f in W.FESTIVALS:
    fall = f["fall"]
    if fall in seen:
        continue
    seen.add(fall)
    rows.append((f["icon"], f["name"], fall, f.get("count", 14)))
n = len(rows)
rows_n = (n + COLS - 1) // COLS
app = QApplication([])   # 没有 QApplication 就 QPainter，Qt 会直接 abort
init_fonts(app)
img = QImage(CELL_W * COLS, CELL_H * rows_n, QImage.Format_RGB32)
img.fill(QColor(16, 17, 22))
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing, True)
for i, (icon, name, fall, cnt) in enumerate(rows):
    cx, cy = (i % COLS) * CELL_W, (i // COLS) * CELL_H
    p.save()
    p.translate(cx, cy)
    p.setPen(QPen(QColor(60, 64, 74), 1))
    p.setBrush(QColor(22, 24, 30))
    p.drawRoundedRect(QRectF(4, 4, CELL_W - 8, CELL_H - 8), 8, 8)
    p.setClipRect(QRectF(6, 6, CELL_W - 12, CELL_H - 12))
    W.draw_falling(p, CELL_W, CELL_H, W.FALL_DRAW[fall], cnt)
    p.setClipping(False)
    p.setPen(QColor(200, 206, 214))
    p.setFont(QFont("Microsoft YaHei", 9))
    p.drawText(QRectF(8, CELL_H - 24, CELL_W - 16, 18), Qt.AlignLeft, "%s %s" % (icon, name))
    p.restore()
p.end()
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "local-shots", "themes-all.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print("SAVED", out, img.width(), "x", img.height(), "items:", n)
