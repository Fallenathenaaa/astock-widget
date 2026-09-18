# -*- coding: utf-8 -*-
"""
A股桌面盯盘挂件 (Windows 11)
- 无边框 / 半透明 / 置顶 / 可拖动
- 最多 5 只股票，红涨绿跌，含分时迷你走势
- 数据源：腾讯财经行情接口（免费、无需 Key）
"""
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import io
import glob
import shutil
import ctypes
import traceback
import threading
from ctypes import wintypes
from datetime import datetime, timedelta

from PySide6.QtCore import (Qt, QThread, Signal, QRectF, QRect, QPointF,
                            QLineF, QTimer, QEvent)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QIcon, QFontMetrics, QImage,
    QPalette, QLinearGradient, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QMenu, QInputDialog, QSystemTrayIcon, QMessageBox,
    QLineEdit, QListWidget, QListWidgetItem,
)

APP_NAME = "A股桌面盯盘挂件"
APP_VERSION = "v2.0.1"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "stocks.json")

# ---- 配置自动备份 ----
BACKUP_KEEP = 30            # 最多保留的快照份数（超出删最旧的）
BACKUP_PREFIX = "stocks-"   # 快照文件名前缀：stocks-20260918-142530.json

# ---- 崩溃日志 ----
# pythonw 启动没有控制台，一旦异常就是"挂件不见了"，啥痕迹都没有。
# 所以未捕获异常一律落盘到 logs/，并弹个窗告诉用户去哪看。
LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_KEEP = 10               # 最多保留的崩溃日志份数
LOG_PREFIX = "crash-"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ---------------- 配色 ----------------
BG = (16, 17, 22)
UP = QColor("#ff4d4f")      # 涨 红
DOWN = QColor("#22c55e")    # 跌 绿
FLAT = QColor("#9ca3af")    # 平 灰
TXT_MAIN = QColor("#e8eaed")
TXT_DIM = QColor("#7c828e")
TXT_FADE = QColor("#565c68")

# 浅色壁纸模式（背景很透明 + 壁纸偏亮）下换用的深色文字
TXT_MAIN_LT = QColor("#14181d")     # 主文字：近黑
TXT_DIM_LT = QColor("#4b5159")      # 次要文字
TXT_FADE_LT = QColor("#6b737d")     # 弱化文字
UP_LT = QColor("#d32029")           # 涨 深红（白底上更实）
DOWN_LT = QColor("#0e8a3f")         # 跌 深绿（原 #22c55e 在白底上太浅）
FLAT_LT = QColor("#6b7280")         # 平 深灰

BG_LUM_THRESHOLD = 140    # 壁纸亮度高于此值算"浅色壁纸"
BG_SAMPLE_MAX_ALPHA = 120  # 背景不透明度高于此值就不切深色文字（背景够实，白字看得清）

# ---- 农历 1900-2100 编码表 ----
#   bit16      : 闰月大小（1=30 0=29，无闰月时无意义）
#   bit15..bit4: 正月..腊月的大小（1=30 0=29）
#   bit3..bit0 : 闰哪个月（0=不闰）
# 验证脚本 _lunar_check.py 校验过 2020-2035 的 14 个已知日期（中秋/春节），全对。
LUNAR_INFO = [
    0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
    0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
    0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
    0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,
    0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,
    0x06ca0,0x0b550,0x15355,0x04da0,0x0a5b0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0,
    0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
    0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b5a0,0x195a6,
    0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
    0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x055c0,0x0ab60,0x096d5,0x092e0,
    0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
    0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
    0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
    0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
    0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
    0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06b20,0x1a6c4,0x0aae0,
    0x0a2e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,
    0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,
    0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,
    0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a2d0,0x0d150,0x0f252,
    0x0d520,
]
_LUNAR_BASE_YEAR = 1900
_LUNAR_BASE_DATE = datetime(_LUNAR_BASE_YEAR, 1, 31).date()   # 1900 年正月初一


def _lunar_info(y):
    return LUNAR_INFO[y - _LUNAR_BASE_YEAR]


def _leap_month(y):
    return _lunar_info(y) & 0x0f


def _leap_days(y):
    lm = _leap_month(y)
    if not lm:
        return 0
    return 30 if (_lunar_info(y) & 0x10000) else 29


def _lunar_month_days(y, m):
    return 30 if (_lunar_info(y) & (0x10000 >> m)) else 29


def _lunar_year_days(y):
    total = 348                       # 12 个月都按 29 天算
    bit = 0x8000                      # bit15..bit4 = 正月..腊月
    while bit > 0x8:
        if _lunar_info(y) & bit:
            total += 1
        bit >>= 1
    return total + _leap_days(y)


def lunar_to_solar(y, m, d, is_leap=False):
    """农历 y 年 m 月 d 日 → datetime.date（不在 1900-2100 范围返回 None）"""
    if not (_LUNAR_BASE_YEAR <= y < _LUNAR_BASE_YEAR + len(LUNAR_INFO)):
        return None
    offset = 0
    for i in range(_LUNAR_BASE_YEAR, y):
        offset += _lunar_year_days(i)
    leap = _leap_month(y)
    for i in range(1, m):
        offset += _lunar_month_days(y, i)
        if leap and i == leap:
            offset += _leap_days(y)
    if is_leap:
        offset += _lunar_month_days(y, m)
    offset += d - 1
    return _LUNAR_BASE_DATE + timedelta(days=offset)


# ==================== 节日彩蛋（v2.0 表驱动重写） ====================
# 三条硬规则：
#  1. 同时只激活**一个**节日，按 pri 取优先级最高的那个（以前中秋+国庆+春节会一起飘）
#  2. 放假的节日（春节/国庆/中秋）在**假期前最后一个交易日**触发 —— 放假期间不开盘，
#     飘给谁看？不放假的节日当天触发，赶上周末同样不触发
#  3. 加新节日 = 这张表加一行 + 一个画法函数，菜单和开关自己长出来
#
# 字段说明：
#   key       配置键（测试开关叫 <key>_test）
#   pri       优先级，大的赢
#   lunar     农历 (月, 日)；lunar12 表示腊月里的多个日子（小年北方廿三/南方廿四）
#   solar     公历 (月, 日)；thanksgiving 表示 11 月第 4 个周四
#   holiday   放假起点："self" = 节日当天开始放假，"eve" = 除夕开始放假；None = 不放假
#   fall      飘落物画法名（见 FALL_DRAW）
#   count     同时在场数量（默认 14；雪花大，少放几片）
#   wk_off    赶上周六周日就不放（西方节日 + 12/31 红包雨：后者要求是交易日）
FESTIVALS = [
    dict(key="spring",    icon="🧧", name="春节",   pri=100,
         lunar=(1, 1),   holiday="eve",  fall="packet"),
    dict(key="national",  icon="🎆", name="国庆节", pri=90,
         solar=(10, 1),  holiday="self", fall="star"),
    dict(key="midautumn", icon="🌕", name="中秋节", pri=80,
         lunar=(8, 15),  holiday="self", fall="petal"),
    dict(key="yearend",   icon="🧧", name="跨年红包雨", pri=70,
         solar=(12, 31), wk_off=True,    fall="packet"),
    dict(key="lantern",   icon="🏮", name="元宵节", pri=60,
         lunar=(1, 15),                 fall="tangyuan"),
    dict(key="xiaonian",  icon="🥟", name="小年",   pri=50,
         lunar12=(23, 24),              fall="dumpling"),
    dict(key="christmas", icon="🎄", name="圣诞节", pri=45,
         solar=(12, 25), wk_off=True,    fall="snow",   count=9),
    dict(key="halloween", icon="🎃", name="万圣节", pri=40,
         solar=(10, 31), wk_off=True,    fall="pumpkin"),
    dict(key="thanks",    icon="🦃", name="感恩节", pri=35,
         thanksgiving=True, wk_off=True, fall="drumstick"),
    dict(key="valentine", icon="💝", name="情人节", pri=30,
         solar=(2, 14),  wk_off=True,    fall="heart"),
]
FEST_BY_KEY = {f["key"]: f for f in FESTIVALS}


def _nth_weekday(year, month, weekday, n):
    """某月第 n 个星期 weekday（周一=0）。感恩节 = 11 月第 4 个周四。"""
    d = datetime(year, month, 1).date()
    return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))


def _is_trading_day(d):
    """只按周一~周五算交易日。调休/临时休市没法预知，不猜。"""
    return d.weekday() < 5


def _last_trading_day_before(d):
    """d 之前最后一个交易日"""
    d -= timedelta(days=1)
    while not _is_trading_day(d):
        d -= timedelta(days=1)
    return d


def festival_nominal_days(f, year):
    """这个节日在公历 year 年的「名义日期」（可能落在相邻农历年里，所以查两年）"""
    out = []
    for ly in (year - 1, year):
        if "lunar" in f:
            m, d = f["lunar"]
            s = lunar_to_solar(ly, m, d)
            if s and s.year == year:
                out.append(s)
        elif "lunar12" in f:
            for d in f["lunar12"]:
                s = lunar_to_solar(ly, 12, d)
                if s and s.year == year:
                    out.append(s)
        elif f.get("thanksgiving"):
            s = _nth_weekday(year, 11, 3, 4)
            if s.year == year:
                out.append(s)
        elif "solar" in f:
            m, d = f["solar"]
            out.append(datetime(year, m, d).date())
    return sorted(set(out))


def festival_trigger_days(f, year):
    """真正放彩蛋的日子。周末 A 股不开盘，所以一律不在周末放。

    三条规则，按表里字段决定：
      · holiday（春节/国庆/中秋）→ 假期开始前最后一个交易日
      · wk_off（西方节日 / 12-31 红包雨）→ 逢周末直接不启动
      · 其余（元宵/小年这类不放假的中国节日）→ 逢周末提前到最近的前一个交易日
    """
    out = []
    for d in festival_nominal_days(f, year):
        if f.get("holiday"):
            start = d - timedelta(days=1) if f["holiday"] == "eve" else d
            out.append(_last_trading_day_before(start))
        elif _is_trading_day(d):
            out.append(d)
        elif not f.get("wk_off"):
            out.append(_last_trading_day_before(d))   # 周六/周日 → 退回周五
    return sorted(set(out))


_fest_cache = {}


def active_festival(cfg=None, today=None):
    """今天生效的节日 —— 有且只有一个。

    测试开关优先级最高（多个同时开时按 pri 取第一个），否则看触发日。
    结果按 (今天, 开关组合) 缓存：这个函数每秒会被调几十次。
    """
    cfg = cfg or {}
    today = today or datetime.now().date()
    tests = tuple(f["key"] for f in FESTIVALS if cfg.get(f["key"] + "_test"))
    ck = (today, tests)
    if ck in _fest_cache:
        k = _fest_cache[ck]
        return FEST_BY_KEY.get(k) if k else None
    hit = None
    if tests:
        hit = FEST_BY_KEY[tests[0]]       # FESTIVALS 已按 pri 降序
    else:
        for f in FESTIVALS:
            if today in festival_trigger_days(f, today.year):
                hit = f
                break
    if len(_fest_cache) > 128:
        _fest_cache.clear()
    _fest_cache[ck] = hit["key"] if hit else ""
    return hit


def next_festival(today=None, within=400):
    """下一个会触发的节日 (festival, date)，用于菜单提示。没有返回 None。"""
    today = today or datetime.now().date()
    best = None
    years = sorted({today.year, (today + timedelta(days=within)).year})
    for f in FESTIVALS:
        for y in years:
            for d in festival_trigger_days(f, y):
                if d >= today and (best is None or d < best[1]):
                    best = (f, d)
    return best


# ---- 飘落物画法 ----
# 约定：draw(p, fx, fy, alpha, life, t, seed)，都是模块级函数（不碰 self，省一层开销）
_col_cache = {}


def _col(r, g, b, a):
    """带缓存的 QColor：一帧要造几十个颜色对象，复用能省不少分配"""
    k = (r, g, b, a)
    c = _col_cache.get(k)
    if c is None:
        if len(_col_cache) > 2048:
            _col_cache.clear()
        c = QColor(r, g, b, a)
        _col_cache[k] = c
    return c


def _d_petal(p, fx, fy, a, life, t, seed):
    """中秋 · 金色花瓣：随下落微微翻面"""
    flutter = 0.55 + 0.45 * abs(math.sin(t * 1.6 + seed))
    p.setBrush(_col(247, 199, 96, a))
    p.drawEllipse(QPointF(fx, fy), 2.9 * flutter, 2.1)


def _d_star(p, fx, fy, a, life, t, seed):
    """国庆 · 金色五角星 #FFDE00：边飘边自转"""
    r = 2.7
    p.save()
    p.translate(fx, fy)
    p.rotate(math.degrees(t * 0.9 + seed))
    path = QPainterPath()
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.42
        ang = -math.pi / 2 + i * math.pi / 5
        x, y = rr * math.cos(ang), rr * math.sin(ang)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    p.setBrush(_col(255, 222, 0, a))
    p.drawPath(path)
    p.restore()


def _d_packet(p, fx, fy, a, life, t, seed):
    """春节 / 跨年 · 红包：红封身 + 金封口 + 金扣，边飘边转"""
    p.save()
    p.translate(fx, fy)
    p.rotate(math.degrees(t * 1.15 + seed))
    w, h = 4.8, 6.4
    p.setBrush(_col(198, 32, 42, a))
    p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 1.3, 1.3)
    p.setBrush(_col(247, 202, 88, a))
    p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, 1.7), 0.7, 0.7)
    p.setBrush(_col(255, 216, 96, a))
    p.drawEllipse(QRectF(-0.75, -0.5, 1.5, 1.5))
    p.restore()


def _d_tangyuan(p, fx, fy, a, life, t, seed):
    """元宵 · 汤圆：米白团子 + 一点高光"""
    r = 3.0
    p.setBrush(_col(250, 246, 238, a))
    p.drawEllipse(QPointF(fx, fy), r, r)
    p.setBrush(_col(255, 255, 255, min(255, a + 25)))
    p.drawEllipse(QPointF(fx - r * 0.32, fy - r * 0.36), r * 0.28, r * 0.22)


def _d_dumpling(p, fx, fy, a, life, t, seed):
    """小年 · 饺子：半月形肚皮 + 三道褶"""
    p.save()
    p.translate(fx, fy)
    p.rotate(12 * math.sin(t * 0.9 + seed))
    p.setBrush(_col(244, 233, 208, a))
    path = QPainterPath()
    path.moveTo(-3.4, 1.1)
    path.quadTo(0, -3.5, 3.4, 1.1)          # 上沿
    path.quadTo(0, 2.5, -3.4, 1.1)          # 肚
    p.drawPath(path)
    p.setPen(QPen(_col(212, 196, 166, a), 0.7))
    p.setBrush(Qt.NoBrush)
    for i in (-1, 0, 1):
        p.drawLine(QLineF(i * 1.05, -1.7, i * 1.3, -0.4))
    p.restore()


def _d_heart(p, fx, fy, a, life, t, seed):
    """情人节 · 红心：两条贝塞尔 + 心跳缩放"""
    s = 0.85 + 0.15 * abs(math.sin(t * 2.2 + seed))
    p.save()
    p.translate(fx, fy)
    p.scale(s, s)
    p.setBrush(_col(233, 46, 74, a))
    path = QPainterPath()
    path.moveTo(0, 2.6)
    path.cubicTo(-4.2, -0.6, -2.2, -3.6, 0, -1.6)
    path.cubicTo(2.2, -3.6, 4.2, -0.6, 0, 2.6)
    p.drawPath(path)
    p.restore()


def _d_drumstick(p, fx, fy, a, life, t, seed):
    """感恩节 · 火鸡腿：烤色肉锤 + 白骨柄，边飘边摆"""
    p.save()
    p.translate(fx, fy)
    p.rotate(20 * math.sin(t * 1.1 + seed))
    p.setBrush(_col(196, 132, 58, a))
    p.drawEllipse(QRectF(-2.4, -1.4, 4.0, 3.2))
    p.setBrush(_col(226, 196, 168, a))
    p.drawRoundedRect(QRectF(1.2, -0.7, 2.6, 1.4), 0.6, 0.6)
    p.setBrush(_col(245, 240, 232, a))
    p.drawEllipse(QRectF(3.2, -1.0, 1.2, 2.0))
    p.restore()


def _d_pumpkin(p, fx, fy, a, life, t, seed):
    """万圣节 · 鬼南瓜：橙瓜身 + 三角眼 + 锯齿嘴"""
    p.save()
    p.translate(fx, fy)
    p.rotate(8 * math.sin(t * 0.8 + seed))
    p.setBrush(_col(234, 128, 32, a))
    p.drawEllipse(QRectF(-3.4, -3.0, 6.8, 6.0))
    p.setBrush(_col(58, 26, 8, a))
    p.drawRect(QRectF(-0.35, -4.3, 0.7, 1.5))           # 瓜蒂
    for sx in (-1, 1):                                   # 两只三角眼
        e = QPainterPath()
        e.moveTo(sx * 2.2, -1.0)
        e.lineTo(sx * 0.7, -1.0)
        e.lineTo(sx * 1.45, 0.4)
        e.closeSubpath()
        p.drawPath(e)
    mouth = QPainterPath()                               # 锯齿嘴
    mouth.moveTo(-2.3, 1.2)
    for i in range(4):
        mouth.lineTo(-2.3 + i * 1.53, 1.2 + (0.9 if i % 2 == 0 else 0.0))
    mouth.lineTo(2.3, 1.2)
    mouth.lineTo(2.3, 2.3)
    mouth.lineTo(-2.3, 2.3)
    mouth.closeSubpath()
    p.drawPath(mouth)
    p.restore()


def _d_snow(p, fx, fy, a, life, t, seed):
    """圣诞 · 雪花❄：六角带分叉，比别的飘落物大一号，慢悠悠地转"""
    R = 5.0
    p.save()
    p.translate(fx, fy)
    p.rotate(math.degrees(t * 0.35 + seed))
    p.setPen(QPen(_col(255, 255, 255, a), 1.1))
    for i in range(6):
        ang = i * math.pi / 3
        p.drawLine(QLineF(0, 0, R * math.cos(ang), R * math.sin(ang)))
        bx, by = R * 0.6 * math.cos(ang), R * 0.6 * math.sin(ang)
        for s in (-0.55, 0.55):
            p.drawLine(QLineF(bx, by,
                              bx + R * 0.3 * math.cos(ang + s),
                              by + R * 0.3 * math.sin(ang + s)))
    p.restore()


FALL_DRAW = {
    "petal": _d_petal, "star": _d_star, "packet": _d_packet,
    "tangyuan": _d_tangyuan, "dumpling": _d_dumpling, "heart": _d_heart,
    "drumstick": _d_drumstick, "pumpkin": _d_pumpkin, "snow": _d_snow,
}


def draw_falling(p, w, h, draw_one, count=14):
    """通用飘落轨道：黄金比散列分道 + 梯形 alpha 包络。

    为什么是梯形而不是 sin：sin 在两端停留太久会出现"断片"（掉到一半突然没了）。
    梯形包络（前 8% 快淡入、中段实心、后 18% 慢淡出）能保证任意时刻都有
    接近满额的数量在场，视觉上是一条不断的风。
    """
    t = time.time()
    p.setPen(Qt.NoPen)
    for k in range(count):
        seed = k * 2.399                       # 黄金角，分布自然不规律
        life = (t * 0.13 + k / count) % 1.0    # 生命周期 ≈ 7.7s
        lane = (k * 0.618033) % 1.0
        fx = 12 + lane * (w - 24) + 9 * math.sin(t * 0.55 + seed)
        fy = 2 + life * (h - 6)
        if life < 0.08:
            a = int(215 * (life / 0.08))
        elif life > 0.82:
            a = int(215 * (1 - (life - 0.82) / 0.18))
        else:
            a = 215
        if a > 4:
            draw_one(p, fx, fy, a, life, t, seed)


EDIT_QSS = """
QLineEdit {
  background: rgba(255,255,255,0.09);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 4px;
  color: #e8eaed;
  padding: 0 6px;
  font-family: 'Microsoft YaHei';
  selection-background-color: #2a2f3a;
}
QLineEdit:focus { border: 1px solid rgba(255,255,255,0.5); background: rgba(255,255,255,0.15); }
"""
EDIT_QSS_DARK = """
QLineEdit {
  background: rgba(16,18,24,0.82);
  border: 1px solid rgba(255,255,255,0.42);
  border-radius: 4px;
  color: #e8eaed;
  padding: 0 6px;
  font-family: 'Microsoft YaHei';
  selection-background-color: #2a2f3a;
}
QLineEdit:focus { border: 1px solid rgba(255,255,255,0.75); background: rgba(16,18,24,0.92); }
"""
LIST_QSS = """
QListWidget {
  background: #181a20;
  border: 1px solid #2a2d35;
  border-radius: 6px;
  color: #e8eaed;
  font-family: 'Microsoft YaHei';
  outline: 0;
}
QListWidget::item { padding: 5px 8px; border-radius: 4px; }
QListWidget::item:selected, QListWidget::item:hover { background: #2a2f3a; }
"""

W_WIDTH = 300          # 加宽以容纳搜索框
HEADER_H = 32
SEARCH_W = 132         # 搜索框宽度
IDX_H = 20
ROW_H = 46
FOOTER_H = 18

EFFECT_SECONDS = 180   # 收盘彩蛋持续时间：3 分钟
EFFECT_MINUTE = (14, 57)   # 触发时刻：14:57 集合竞价

IDLE_TICK_MS = 500     # 平时心跳：2fps，只用来倒计时 pulse / 清理过期状态
ANIM_TICK_MS = 50      # 有动画时的心跳：20fps（飘落物 / 火焰 / 冰霜）
                       # 40ms(25fps) 和 20fps 肉眼几乎无差，但唤醒次数少 20%

SNAP_MARGIN = 16       # 拖到距屏幕边缘这么多像素内就吸附上去（0 = 关）

# 隐藏开关的解锁口令：↑↑↓↓←→←→ B A B A（再输一次收起）
KONAMI = [Qt.Key_Up, Qt.Key_Up, Qt.Key_Down, Qt.Key_Down,
          Qt.Key_Left, Qt.Key_Right, Qt.Key_Left, Qt.Key_Right,
          Qt.Key_B, Qt.Key_A, Qt.Key_B, Qt.Key_A]
KONAMI_KEYS = set(KONAMI)   # 属于口令的键（用来判断"按错了就重来"）
KONAMI_TIMEOUT = 10.0       # 口令要在 10 秒内一口气输完，超时作废
# 备用解锁：连点左上角状态点，2 秒内 5 次。键盘口令要窗口有焦点才收得到，
# 鼠标点击一定能收到，留条后路。（具体数字不写进 README —— 隐藏菜单就是要藏着）
DOT_TAP_WINDOW = 2.0
DOT_TAP_N = 5

INDEX_CODES = ["sh000001", "sz399001", "sz399006"]   # 上证 / 深证 / 创业板
INDEX_NAMES_LIST = ["上证", "深证", "创业板"]   # 按 INDEX_CODES 顺序；注意 sh000001 与 sz000001 返回的 code 都是 000001，只能按位置区分

DEFAULT_CONFIG = {
    "title": "A股盯盘",
    "show_index": True,
    "ui_scale": 1.0,        # 整体缩放（字体/行高/间距一起变）
    "alert_pct": 3.0,       # 涨跌幅绝对值超过此值就提醒；0 = 关闭
    "effect_pct": 3.0,      # 14:57 收盘彩蛋阈值：涨超=燃烧，跌超=结霜；0 = 关闭
    "positions": {},        # 持仓：{"sh600519": {"cost": 1250.0, "shares": 100}}；shares 可省略
    "codes": ["sh600519", "sz000001", "sz300750"],
    "interval": 3,
    "bg_alpha": 190,        # 背景不透明度 0-255
    "locked": False,
    "spark": True,
    "click_through": False,
    "always_on_top": True,
    "autostart": False,
    # 每个节日一个「强制开启」开关，由 FESTIVALS 表自动生成（加节日不用改这里）
    **{f["key"] + "_test": False for f in FESTIVALS},
    "unlocked": False,          # 隐藏菜单是否已解锁（输对一次口令后记住，免得每次重启重输）
    "snap": True,               # 拖动时吸附到屏幕边缘
    "pos": None,
}


# ---------------- 工具 ----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        return cfg                    # 全新安装：别去翻旧备份
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
        return cfg
    except Exception:
        pass                          # 文件在但读不出来：试着从备份捞
    saved = recover_from_snapshot()
    return saved if saved is not None else cfg


def save_config(cfg):
    try:
        snapshot_config()          # 先把「改动前」这份存下来，写完就晚了
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------- 配置快照 / 恢复 ----------------
# 起因：持仓成本（positions）被临时脚本洗掉过 3 次，没有存档就找不回来。
# 策略：每次写配置前先把「改动前」的那份存进 backups/，内容没实质变化就不存，
#       超过 BACKUP_KEEP 份删最旧的。启动时也存一份。
def _read_text(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


_recovered_from = None      # 本次启动是否从备份恢复的（Ticker 用来提示用户）


def recover_from_snapshot():
    """`stocks.json` 读不出来时，从最近的快照里挑一份能用的。

    以前读失败是静默退回默认配置 —— 自选股和持仓等于凭空消失。
    成功返回 cfg dict，并把来源记进 `_recovered_from`；全都不行返回 None。
    """
    global _recovered_from
    for p in list_snapshots():
        try:
            d = json.loads(_read_text(p) or "")
        except Exception:
            continue                  # 这份也是坏的，换下一份
        if isinstance(d, dict):
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(d)
            _recovered_from = p
            return cfg
    return None


def _essence(text):
    """判断两份配置有没有"实质变化"——只挪了窗口位置（pos）不算。"""
    try:
        d = json.loads(text)
    except Exception:
        return text
    if isinstance(d, dict):
        d = {k: v for k, v in d.items() if k != "pos"}
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _backup_dir():
    """快照目录跟着配置目录走（测试里把 CONFIG_PATH 指到临时目录时不会污染真实备份）。"""
    return os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)) or ".", "backups")


def _snap_parts(path):
    """拆出 (日期, 时间, 序号)。无后缀的 base 是当秒第一份，序号记 1。"""
    name = os.path.basename(path)
    if name.startswith(BACKUP_PREFIX):
        name = name[len(BACKUP_PREFIX):]
    if name.endswith(".json"):
        name = name[:-5]
    parts = name.split("-")
    try:
        seq = int(parts[2]) if len(parts) > 2 else 1
    except Exception:
        seq = 1
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "", seq)


def _snap_key(path):
    """排序键：先按时间戳，同一秒内的 -2/-3 后缀按数字排（字典序会把 -9 排到 -2 前面）。"""
    return _snap_parts(path)


def list_snapshots():
    """按生成时间从新到旧返回快照路径列表。"""
    try:
        files = glob.glob(os.path.join(_backup_dir(), BACKUP_PREFIX + "*.json"))
    except Exception:
        return []
    return sorted(files, key=_snap_key, reverse=True)


def _rotate_snapshots():
    """只留最近 BACKUP_KEEP 份，多出来的删掉。"""
    try:
        files = list_snapshots()
        for old in files[BACKUP_KEEP:]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def snapshot_config(force=False):
    """把当前 stocks.json 复制一份到 backups/。
    返回快照路径；配置不存在 / 与最近一份实质相同（且非 force）→ 返回 None。"""
    try:
        text = _read_text(CONFIG_PATH)
        if not text:
            return None
        try:
            json.loads(text)          # 坏掉的 JSON 不存档：别让垃圾占掉备份位
        except Exception:
            return None
        newest = list_snapshots()[0] if list_snapshots() else None
        if not force and newest:
            if _essence(_read_text(newest) or "") == _essence(text):
                return None
        bdir = _backup_dir()
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # 同一秒内的序号取「已有最大值 +1」：轮转删掉旧文件后空出来的号不能复用，
        # 否则新快照会往被删掉的号上反复覆盖，越存越旧。
        used = [s for f, s in ((f, _snap_parts(f)[2]) for f in list_snapshots())
                if _snap_parts(f)[0] == stamp[:8] and _snap_parts(f)[1] == stamp[9:]]
        nxt = (max(used) + 1) if used else 1
        name = BACKUP_PREFIX + stamp + ("" if nxt == 1 else "-%d" % nxt) + ".json"
        dst = os.path.join(bdir, name)
        shutil.copyfile(CONFIG_PATH, dst)   # 不用 copy2：别把源文件的 mtime 带过来
        _rotate_snapshots()
        return dst
    except Exception:
        return None


def restore_snapshot(path):
    """把某份快照写回 stocks.json（顺手把当前状态也存一份，方便反悔）。
    成功返回 True。"""
    try:
        text = _read_text(path)
        if not text:
            return False
        json.loads(text)                 # 先确认是合法 JSON，别把配置写坏
        snapshot_config(force=True)      # 覆盖前留一份当前的
        with io.open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False


# ---------------- 崩溃日志 ----------------
def list_crash_logs():
    """从新到旧返回崩溃日志路径。"""
    try:
        files = glob.glob(os.path.join(LOG_DIR, LOG_PREFIX + "*.log"))
    except Exception:
        return []
    return sorted(files, reverse=True)


def _rotate_logs():
    try:
        for old in list_crash_logs()[LOG_KEEP:]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def write_crash_log(text):
    """写一份崩溃日志，返回路径（写不进去返回 None）。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(LOG_DIR, LOG_PREFIX + stamp + ".log")
        n = 2
        while os.path.exists(path):          # 同一秒崩多次：加序号，别互相覆盖
            path = os.path.join(LOG_DIR, "%s%s-%d.log" % (LOG_PREFIX, stamp, n))
            n += 1
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(text)
        _rotate_logs()
        return path
    except Exception:
        return None


def _crash_text(exc_type, exc, tb):
    head = ["%s %s" % (APP_NAME, APP_VERSION),
            "Python %s" % sys.version.split()[0],
            "时间 %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ""]
    try:
        body = traceback.format_exception(exc_type, exc, tb)
    except Exception:
        body = ["%s: %s\n" % (getattr(exc_type, "__name__", "?"), exc)]
    return "\n".join(head) + "".join(body)


def _crash_alert(path, exc):
    """弹窗告知。用 Win32 MessageBox 而不是 QMessageBox —— Qt 自己崩了的时候还能弹出来。"""
    try:
        if sys.platform != "win32":
            return
        msg = ("挂件遇到了一个未处理的错误：\n\n%s: %s\n\n"
               "详情已写入：\n%s\n\n把这份日志发我就能定位问题。"
               % (getattr(type(exc), "__name__", "Exception"), exc, path or "(日志写入失败)"))
        ctypes.windll.user32.MessageBoxW(None, msg, "A股盯盘 - 出错了", 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    _crash_alert(write_crash_log(_crash_text(exc_type, exc, tb)), exc)


def _thread_excepthook(args):
    _crash_alert(write_crash_log(_crash_text(args.exc_type, args.exc_value,
                                             args.exc_traceback)), args.exc_value)


def install_crash_handler():
    """装上全局兜底：主线程 + 子线程 + Qt 槽里的异常都能落盘。"""
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


def normalize_code(raw):
    """600519 / sh600519 / 600519.SH / 000001 -> sh600519"""
    s = str(raw).strip().lower().replace(" ", "")
    if not s:
        return None
    if "." in s:
        s = s.split(".")[0]
    if s.startswith(("sh", "sz", "bj")) and len(s) == 8:
        return s
    s = "".join(ch for ch in s if ch.isdigit() or ch in "shzjbj")
    s = s.lstrip("shzjbj") if not s[:2] in ("sh", "sz", "bj") else s
    if s.startswith(("sh", "sz", "bj")):
        return s
    if not s.isdigit():
        return None
    if s.startswith(("60", "68", "90", "51", "58", "56", "11", "50")):
        return "sh" + s
    if s.startswith(("00", "30", "20", "12", "15", "16", "18")):
        return "sz" + s
    if s.startswith(("43", "83", "87", "88", "92", "82")):
        return "bj" + s
    return "sh" + s


def parse_positions(text):
    """"600519=1250:100, 000001=11.5" -> {"sh600519": {"cost":1250.0,"shares":100}, ...}"""
    pos = {}
    for item in str(text).replace("，", ",").replace("、", ",").replace(" ", "").split(","):
        if "=" not in item:
            continue
        raw, val = item.split("=", 1)
        code = normalize_code(raw)
        if not code or not val:
            continue
        parts = val.split(":")
        try:
            cost = float(parts[0])
        except ValueError:
            continue
        entry = {"cost": cost}
        if len(parts) > 1 and parts[1]:
            try:
                entry["shares"] = int(float(parts[1]))
            except ValueError:
                pass
        pos[code] = entry
    return pos


def http_get(url, timeout=5):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_quotes(codes):
    """返回行情列表"""
    if not codes:
        return []
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    raw = http_get(url, timeout=5).decode("gbk", errors="ignore")
    out = []
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line.startswith("v_"):
            continue
        body = line[line.find('="') + 2: line.rfind('"')]
        f = body.split("~")
        if len(f) < 35:
            continue
        try:
            price = float(f[3])
            prev = float(f[4])
            chg = float(f[31])
            pct = float(f[32])
        except Exception:
            continue
        code = f[2]
        out.append({
            "code": code,
            "name": f[1],
            "decimals": 3 if code.startswith(("51", "52", "56", "58", "50", "15", "16", "159", "588", "518")) else 2,
            "price": price,
            "prev": prev,
            "change": chg,
            "pct": pct,
            "high": f[33],
            "low": f[34],
            "open": f[5],
            "time": f[30],
        })
    return out


def search_stocks(keyword, limit=8):
    """搜索股票：支持拼音缩写(mt) / 代码(600519) / 全名(茅台)。
    腾讯 smartbox，返回格式 v_hint="市场~代码~名称~拼音~类型^..."，无结果为 N"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    url = "https://smartbox.gtimg.cn/s3/?q=" + urllib.parse.quote(kw) + "&t=all"
    raw = http_get(url, timeout=5).decode("utf-8", "ignore")
    m = re.search(r'v_hint="(.*?)"', raw)
    if not m or m.group(1) == "N":
        return []
    body = m.group(1)
    if "\\u" in body:                      # 接口返回的是 \uXXXX 字面量，需要解码
        try:
            body = json.loads('"' + body.replace('"', '\\"') + '"')
        except Exception:
            pass
    out = []
    for item in body.split("^"):
        f = item.split("~")
        if len(f) < 3:
            continue
        mk, code, name = f[0], f[1], f[2]
        if mk not in ("sh", "sz", "bj"):        # 只留沪深京，过滤港股/美股/场外基金
            continue
        if not (code.isdigit() and len(code) == 6):
            continue
        out.append({
            "full": mk + code,
            "code": code,
            "name": name,
            "pinyin": f[3] if len(f) > 3 else "",
            "type": f[4] if len(f) > 4 else "",
        })
    return out[:limit]


def fetch_spark(code, cache):
    """分时迷你走势，5 分钟缓存一次；失败返回 None"""
    now = time.time()
    hit = cache.get(code)
    if hit and now - hit[0] < 300:
        return hit[1]
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=" + code
        data = json.loads(http_get(url, timeout=5).decode("utf-8", "ignore"))
        node = data["data"][code]["data"]
        arr = node["data"] if isinstance(node, dict) else node
        pts = []
        for item in arr:
            p = item.split()
            if len(p) >= 2:
                try:
                    pts.append(float(p[1]))
                except Exception:
                    pass
        if len(pts) < 2:
            raise ValueError
        cache[code] = (now, pts)
        return pts
    except Exception:
        return hit[1] if hit else None


def is_trading_now():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= m <= (11 * 60 + 30) or (13 * 60) <= m <= (15 * 60 + 5)


# ---------------- 数据线程 ----------------
class Fetcher(QThread):
    data_ready = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.codes = []
        self.show_index = True
        self.fast = 3
        self.slow = 60
        self._stop = False
        self._fail_count = 0
        self._spark_cache = {}
        self._spark_tick = 0

    def stop(self):
        self._stop = True
        self.wait(3000)

    def run(self):
        """QThread 里冒出去的异常不一定走 sys.excepthook，自己兜一层落盘。"""
        try:
            self._loop()
        except Exception:
            write_crash_log(_crash_text(*sys.exc_info()))

    def _loop(self):
        while not self._stop:
            if self.codes:
                try:
                    rows = fetch_quotes(self.codes)
                    if rows:
                        self._fail_count = 0
                        if self._spark_tick <= 0:
                            for r in rows:
                                r["spark"] = fetch_spark(self._get_full(r["code"]), self._spark_cache)
                            self._spark_tick = max(1, int(300 / max(self.fast, 1)))
                        else:
                            for r in rows:
                                r["spark"] = (self._spark_cache.get(self._get_full(r["code"])) or [None, None])[1]
                        for i, r in enumerate(rows):
                            if i < len(self.codes):
                                r["full"] = self.codes[i]      # sh600519 这种完整代码，用于查持仓
                        idx = []
                        if self.show_index:
                            try:
                                idx = fetch_quotes(INDEX_CODES)
                            except Exception:
                                idx = []
                        self.data_ready.emit({"rows": rows, "idx": idx})
                    else:
                        self._fail_count += 1
                        self.failed.emit("未取到行情")
                except Exception as e:
                    self._fail_count += 1
                    self.failed.emit(str(e))
                self._spark_tick -= 1
            interval = self._next_interval()
            slept = 0.0
            while slept < interval and not self._stop:
                time.sleep(0.25)
                slept += 0.25

    def _next_interval(self):
        """连续失败就退避，避免断网时死命重试；恢复成功后自动回到正常频率"""
        interval = self.fast if is_trading_now() else self.slow
        if self._fail_count >= 5:
            interval = max(interval, 30)
        return interval

    def _get_full(self, code):
        for c in self.codes:
            if c.endswith(code):
                return c
        return normalize_code(code) or code


class Searcher(QThread):
    """搜索线程：避免输入时卡顿"""
    result_ready = Signal(list)

    def __init__(self):
        super().__init__()
        self.keyword = ""
        self._stop = False

    def stop(self):
        self._stop = True
        self.wait(2000)

    def run(self):
        try:
            self._loop()
        except Exception:
            write_crash_log(_crash_text(*sys.exc_info()))

    def _loop(self):
        while not self._stop:
            if self.keyword:
                kw = self.keyword
                self.keyword = ""
                try:
                    self.result_ready.emit(search_stocks(kw))
                except Exception:
                    self.result_ready.emit([])
            time.sleep(0.15)


# ---------------- 主窗口 ----------------
class Ticker(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.scale = float(cfg.get("ui_scale") or 1.0)
        self.rows = []
        self.indices = []
        self.alerted = {}     # code -> 上次提醒时间戳（5 分钟冷却）
        self.flash = {}       # code -> 触发时间戳（高亮 10 秒）
        self.effects = {}     # code -> {"type": "fire"/"frost", "until": ts, "t0": ts}，收盘彩蛋
        self._effect_date = None   # 彩蛋每天只在 14:57 触发一次
        self.err = ""
        self.updated_at = ""
        self.drag_pos = None
        self.pulse = 0
        self._bg_lum = None        # 挂件背后壁纸的平均亮度（0-255），None = 还没采样
        self._bg_sampled_at = 0.0  # 上次采样时间
        self._sampling = False     # 采样中，防止重入
        self._konami = []          # 已按下的键序列（口令匹配用）
        self._konami_show = 0.0    # 进度提示显示到什么时候（0 = 不显示）
        self._konami_t0 = 0.0      # 第一个键按下的时刻（超时就作废重来）
        self._dot_taps = 0         # 状态点连击计数（备用解锁）
        self._dot_taps_at = 0.0
        self._unlocked = bool(cfg.get("unlocked"))   # 隐藏菜单是否已解锁（持久化）

        # 全局按键监听：焦点在搜索框里也能收到方向键/字母
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

        # ---- 多选删除 ----
        self.sel_mode = False         # 是否处于多选状态
        self.selected = set()         # 选中的完整代码，如 {"sh600519"}
        self._press_row = None        # 按下时命中的行号
        self._press_pos = None        # 按下时的全局坐标（判断是拖窗口还是长按）
        self._moved = False           # 按下后是否移动过（移动过就不再算长按/点击）
        self._long_timer = QTimer(self)
        self._long_timer.setSingleShot(True)
        self._long_timer.setInterval(450)      # 长按阈值
        self._long_timer.timeout.connect(self._on_long_press)

        self.setFocusPolicy(Qt.StrongFocus)     # 让 Esc 能生效
        self.setWindowTitle(cfg.get("title") or "A股盯盘")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(W_WIDTH)
        self.apply_flags()
        self.resize_to_rows()

        # 恢复上次位置，但先确认还在某个屏幕内（防止拔显示器后窗口跑到屏幕外）
        pos = cfg.get("pos")
        ok = False
        if pos and isinstance(pos, list) and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
            for scr in QApplication.screens():
                g = scr.availableGeometry()
                if g.left() - 40 <= x <= g.right() and g.top() - 40 <= y <= g.bottom():
                    ok = True
                    break
        if ok:
            self.move(int(pos[0]), int(pos[1]))
        else:
            self.move_to_default()

        self.fetcher = Fetcher()
        self.fetcher.codes = cfg.get("codes") or []
        self.fetcher.show_index = bool(cfg.get("show_index", True))
        self.fetcher.fast = int(cfg.get("interval") or 3)
        self.fetcher.data_ready.connect(self.on_data)
        self.fetcher.failed.connect(self.on_fail)
        self.fetcher.start()

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.tick_pulse)
        self.pulse_timer.start(IDLE_TICK_MS)

        self._build_search()
        self.build_tray()

        # 配置读坏了、刚从备份里捞回来 —— 得让用户知道（不然他会以为自选股自己没了）
        if _recovered_from:
            src = os.path.basename(_recovered_from)
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                "A股盯盘",
                "stocks.json 读不出来，已自动用备份 %s 恢复\n（坏文件原样留着，可手动查看）" % src,
                QSystemTrayIcon.Warning, 8000))

        # 壁纸明暗采样：启动后延迟 600ms 采一次（等窗口真正贴上去），之后每 20 秒
        # 复查一次（壁纸可能切换/换主题）。真正的采样频率由 sample_bg 自己压。
        QTimer.singleShot(600, lambda: self.sample_bg(force=True))
        self._bg_timer = QTimer(self)
        self._bg_timer.timeout.connect(lambda: self.sample_bg())
        self._bg_timer.start(20000)

    # ---- 窗口属性 ----
    def apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Window
        if self.cfg.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        if self.cfg.get("click_through", False):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.show()

    # ---- 搜索框 / 候选列表 ----
    def _build_search(self):
        self.candidates = []
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("代码 / 拼音 / 名称  ↵")
        self.search_edit.setStyleSheet(EDIT_QSS)
        self.search_edit.returnPressed.connect(self.add_first_candidate)
        self.search_edit.textChanged.connect(self.on_search_text)
        self.search_edit.installEventFilter(self)

        self.cand_list = QListWidget(self)
        self.cand_list.setStyleSheet(LIST_QSS)
        self.cand_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cand_list.hide()
        self.cand_list.itemClicked.connect(self.on_pick_candidate)

        # 子控件默认不显，必须显式 show（WA_TranslucentBackground 下被静默吞了显隐状态）
        self.search_edit.show()

        self.searcher = Searcher()
        self.searcher.result_ready.connect(self.on_search_result)
        self.searcher.start()

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(320)          # 输入防抖
        self.search_timer.timeout.connect(self.do_search)

        self._update_edit_style()
        self.layout_children()

    def layout_children(self):
        s = self.scale
        f = QFont("Microsoft YaHei")
        f.setPointSizeF(8.5 * s)
        self.search_edit.setFont(f)
        self.cand_list.setFont(f)
        self.search_edit.setGeometry(
            int((W_WIDTH - SEARCH_W - 10) * s), int(5 * s),
            int(SEARCH_W * s), int(22 * s))
        n = min(len(self.candidates), 6)
        self.cand_list.setGeometry(
            int(8 * s), int(HEADER_H * s),
            int((W_WIDTH - 16) * s), int((n * 24 + 8) * s))
        self.cand_list.setVisible(n > 0)

    def on_search_text(self, text):
        if not text.strip():
            self.candidates = []
            self.layout_children()
            return
        self.search_timer.start()

    def do_search(self):
        kw = self.search_edit.text().strip()
        if kw:
            self.searcher.keyword = kw

    def on_search_result(self, items):
        self.candidates = items
        self.cand_list.clear()
        for it in items:
            tag = {"ZS": "指数", "ET": "基金", "GP-B": "B股"}.get(it.get("type", ""), "")
            label = "%s  %s%s" % (it["code"], it["name"], ("  · " + tag) if tag else "")
            self.cand_list.addItem(QListWidgetItem(label))
        self.layout_children()

    def on_pick_candidate(self, item):
        idx = self.cand_list.row(item)
        if 0 <= idx < len(self.candidates):
            self.add_stock(self.candidates[idx])

    def add_first_candidate(self):
        if self.candidates:
            self.add_stock(self.candidates[0])
        elif self.search_edit.text().strip():
            self.do_search()

    def add_stock(self, item):
        codes = list(self.cfg.get("codes") or [])
        full = item["full"]
        if full in codes:
            self._close_search()
            return
        if len(codes) >= 5:
            codes = codes[:4]          # 满了就挤掉最后一只，让新加的进来
        codes.append(full)
        self.cfg["codes"] = codes
        save_config(self.cfg)
        self.fetcher.codes = codes
        self.fetcher._spark_tick = 0
        self._close_search()
        self.resize_to_rows()

    def _close_search(self):
        self.candidates = []
        self.cand_list.clear()
        self.search_edit.clear()
        self.layout_children()

    def eventFilter(self, obj, event):
        if obj is self.search_edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._close_search()
                return True
        return super().eventFilter(obj, event)

    def move_to_default(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 24, scr.top() + 80)

    # ---- 边缘吸附 ----
    def _snap_screen(self, cursor=None):
        """取用于吸附的屏幕：优先光标所在那块（多显示器），退回窗口所在 / 主屏。"""
        scr = None
        if cursor is not None:
            try:
                scr = QApplication.screenAt(cursor)
            except Exception:
                scr = None
        return scr or self.screen() or QApplication.primaryScreen()

    def snap_pos(self, x, y, cursor=None):
        """把 (x, y) 吸到屏幕边缘：距离边缘 SNAP_MARGIN 以内就贴上去。
        做了缩放后 width()/height() 是物理像素，和屏幕坐标同一套，可以直接算。"""
        if not self.cfg.get("snap", True) or SNAP_MARGIN <= 0:
            return x, y
        scr = self._snap_screen(cursor)
        if scr is None:
            return x, y
        g = scr.availableGeometry()
        w, h = self.width(), self.height()
        if x - g.left() <= SNAP_MARGIN:
            x = g.left()
        elif g.right() - (x + w) <= SNAP_MARGIN:
            x = g.right() - w
        if y - g.top() <= SNAP_MARGIN:
            y = g.top()
        elif g.bottom() - (y + h) <= SNAP_MARGIN:
            y = g.bottom() - h
        return x, y

    def resize_to_rows(self):
        n = max(1, len(self.rows) if self.rows else len(self.cfg.get("codes") or []) or 1)
        n = min(n, 5)
        h = HEADER_H + (IDX_H if self.cfg.get("show_index", True) else 0) + ROW_H * n + FOOTER_H
        s = self.scale
        self.setFixedSize(int(W_WIDTH * s), int(h * s))
        if hasattr(self, "search_edit"):
            self.layout_children()

    # ---- 数据 ----
    def on_data(self, data):
        self.rows = (data.get("rows") or [])[:5]
        self.indices = data.get("idx") or []
        self.err = ""
        self.updated_at = datetime.now().strftime("%H:%M:%S")
        self.pulse = 3
        self.resize_to_rows()
        self.check_alert(self.rows)
        self.check_close_effect(self.rows)
        self.update()
        self.update_tray_tip()
        self.update_tray_icon()

    def on_fail(self, msg):
        self.err = msg[:40]
        self.update()

    def tick_pulse(self):
        anim = False
        if self.pulse > 0:
            self.pulse -= 1
            self.update()
        if self.flash:
            now = time.time()
            self.flash = {k: v for k, v in self.flash.items() if now - v < 10}
            self.update()
        if self.effects:
            # 彩蛋期间持续重绘：火焰要跳动、冰霜要闪烁
            now = time.time()
            self.effects = {k: v for k, v in self.effects.items()
                            if v["until"] > now}
            self.update()
            anim = True
        if self._need_anim():
            # 节日花瓣等全屏动画：平时挂件是不重绘的（只有数据到达才刷一帧），
            # 不在这里驱动的话动画会几十秒才动一下就冻住。
            self.update()
            anim = True
        # 有动画就提到 ~25fps，没动画回到 200ms 省电
        want = ANIM_TICK_MS if anim else IDLE_TICK_MS
        if self.pulse_timer.interval() != want:
            self.pulse_timer.setInterval(want)

    def _need_anim(self):
        """当前有没有需要逐帧重绘的动画。

        隐藏到托盘 / 窗口不可见时一律不画 —— 看不见的东西不值得烧 CPU。
        """
        if not self.isVisible():
            return False
        return self._festival() is not None or time.time() < self._konami_show

    def _festival(self):
        """今天生效的节日（同时只有一个），带一次一日的缓存"""
        return active_festival(self.cfg)

    def check_alert(self, rows):
        """涨跌幅超阈值 → 托盘气泡 + 该行高亮闪烁"""
        th = float(self.cfg.get("alert_pct") or 0)
        if th <= 0:
            return
        now = time.time()
        msgs = []
        for r in rows:
            if abs(r["pct"]) >= th:
                if now - self.alerted.get(r["code"], 0) > 300:      # 同一只 5 分钟内不重复
                    self.alerted[r["code"]] = now
                    self.flash[r["code"]] = now
                    msgs.append("%s  %+.2f%%" % (r["name"], r["pct"]))
        if msgs and getattr(self, "tray", None):
            self.tray.showMessage("A股盯盘 · 异动", "\n".join(msgs),
                                  QSystemTrayIcon.Information, 6000)

    def check_close_effect(self, rows):
        """收盘彩蛋：14:57 集合竞价这一刻，涨幅超阈值 -> 燃烧 3 分钟；跌幅超阈值 -> 结霜 3 分钟。
        每个交易日只触发一次。"""
        th = float(self.cfg.get("effect_pct") or 0)
        if th <= 0 or not is_trading_now():
            return
        now = datetime.now()
        if (now.hour, now.minute) != EFFECT_MINUTE:
            return
        today = now.strftime("%Y-%m-%d")
        if self._effect_date == today:
            return
        self._effect_date = today
        until = time.time() + EFFECT_SECONDS
        hit_fire, hit_frost = [], []
        for r in rows:
            code = r.get("code")
            if not code:
                continue
            pct = r.get("pct", 0)
            if pct >= th:
                self.effects[code] = {"type": "fire", "until": until, "t0": time.time()}
                hit_fire.append(r["name"])
            elif pct <= -th:
                self.effects[code] = {"type": "frost", "until": until, "t0": time.time()}
                hit_frost.append(r["name"])
        msgs = []
        if hit_fire:
            msgs.append("🔥 燃烧：" + "、".join(hit_fire))
        if hit_frost:
            msgs.append("❄ 结霜：" + "、".join(hit_frost))
        if msgs and getattr(self, "tray", None):
            self.tray.showMessage("A股盯盘 · 收盘定格", "\n".join(msgs),
                                  QSystemTrayIcon.Information, 8000)

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        s = self.scale
        p.scale(s, s)          # 之后一律用逻辑坐标，字号/间距/行高自动跟着缩放
        w, h = W_WIDTH, self.height() / s

        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BG[0], BG[1], BG[2], int(self.cfg.get("bg_alpha", 190))))
        p.drawPath(path)
        ba = self._dim(34)
        if ba > 0:
            p.setPen(QPen(QColor(255, 255, 255, ba), 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        # 头部 —— 状态圆点 + 标题（左上角不画任何节日图形）
        dot_color = QColor("#4ade80") if is_trading_now() else QColor("#6b7280")
        if self.pulse > 0:
            dot_color = QColor("#ffffff") if self.pulse % 2 else dot_color
        p.setPen(Qt.NoPen)
        p.setBrush(dot_color)
        p.drawEllipse(QRectF(13, HEADER_H / 2 - 2.5, 5, 5))
        title_x, title_w = 24, W_WIDTH - SEARCH_W - 34

        # 口令输入进度：按一个键就多一颗金点，能立刻看出挂件有没有收到按键
        if time.time() < self._konami_show and self._konami:
            p.setPen(Qt.NoPen)
            for i in range(len(self._konami)):
                p.setBrush(QColor(247, 199, 96, 215))
                p.drawEllipse(QRectF(24 + i * 6.0, HEADER_H / 2 - 1.7, 3.4, 3.4))
        else:
            # 标题文字
            title_text = self.cfg.get("title") or "A股盯盘"
            p.setFont(QFont("Microsoft YaHei", 8))
            self._text(p, QRect(title_x, 0, title_w, HEADER_H),
                       Qt.AlignVCenter | Qt.AlignLeft, title_text, self._fg_dim())

        show_idx = self.cfg.get("show_index", True)
        body_y = HEADER_H + (IDX_H if show_idx else 0)
        if show_idx:
            self._index_bar(p, w, HEADER_H)

        if not self.rows:
            f2 = QFont("Microsoft YaHei", 9)
            p.setFont(f2)
            self._text(p, QRect(0, body_y, w, ROW_H), Qt.AlignCenter,
                       self.err or "右键 → 编辑股票", self._fg_fade())
            self._footer(p, w, h)
            self._draw_holiday_fall(p, w, h)
            p.end()
            return

        for i, r in enumerate(self.rows):
            self._row(p, r, body_y + i * ROW_H, i)
        self._footer(p, w, h)
        self._draw_holiday_fall(p, w, h)
        p.end()

    def _draw_holiday_fall(self, p, w, h):
        """节日飘落物：铺满整个面板，画在最上层，像真的飘在眼前。

        同时只有一个节日生效。没有股票数据时也要画，所以两条返回路径都要调它。"""
        f = self._festival()
        if f:
            draw_one = FALL_DRAW.get(f["fall"])
            if draw_one:
                draw_falling(p, w, h, draw_one, f.get("count", 14))

    # ---- 壁纸明暗检测：浅色壁纸 + 背景很透明时，文字切成深色 ----
    def _ghost(self):
        return int(self.cfg.get("bg_alpha", 190)) <= 60

    def _need_sample(self):
        """背景太实就不用采样了——白字在深色面板上本来就清楚"""
        return int(self.cfg.get("bg_alpha", 190)) <= BG_SAMPLE_MAX_ALPHA

    def sample_bg(self, force=False):
        """抓挂件所在区域的桌面，算平均亮度。

        我们的窗口是分层窗口（WA_TranslucentBackground），Windows 的 BitBlt
        从桌面 DC 复制时抓不到它，所以抓到的基本就是纯壁纸 —— 正好合用。
        采样有代价（一次全屏区域拷贝），调用频率要压住。"""
        if self._sampling:
            return
        if not self._need_sample() and not force:
            return
        now = time.time()
        if not force and now - self._bg_sampled_at < 1.5:
            return
        self._sampling = True
        try:
            scr = self.screen() or QApplication.primaryScreen()
            if scr is None:
                return
            g = self.geometry()
            x, y = max(0, g.x()), max(0, g.y())
            w = min(g.width(), scr.size().width() - x)
            h = min(max(g.height(), 60), scr.size().height() - y)
            if w <= 4 or h <= 4:
                return
            pix = scr.grabWindow(0, x, y, w, h)
            img = pix.toImage()
            if img.isNull():
                return
            tot = cnt = 0
            step_x = max(1, img.width() // 20)
            step_y = max(1, img.height() // 12)
            for yy in range(0, img.height(), step_y):
                for xx in range(0, img.width(), step_x):
                    c = img.pixelColor(xx, yy)
                    # 感知亮度（Rec.601）
                    tot += (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
                    cnt += 1
            if cnt:
                self._bg_lum = tot // cnt
                self._bg_sampled_at = now
        except Exception:
            pass
        finally:
            self._sampling = False

    def _light_bg(self):
        """当前是不是"浅色壁纸 + 背景很透明"——是的话文字要切成深色"""
        if not self._need_sample():
            return False
        return self._bg_lum is not None and self._bg_lum > BG_LUM_THRESHOLD

    def _fg(self):
        """主文字色：浅底用近黑，深底用亮白"""
        return TXT_MAIN_LT if self._light_bg() else TXT_MAIN

    def _fg_dim(self):
        return TXT_DIM_LT if self._light_bg() else TXT_DIM

    def _fg_fade(self):
        return TXT_FADE_LT if self._light_bg() else TXT_FADE

    def _up(self):
        return UP_LT if self._light_bg() else UP

    def _down(self):
        return DOWN_LT if self._light_bg() else DOWN

    def _flat(self):
        return FLAT_LT if self._light_bg() else FLAT

    def _text(self, p, rect, align, txt, color, outline=None):
        """画文字。
        - 浅色壁纸模式：先描一圈 1px 白色，深色文字在稍暗的壁纸上也不糊
        - _ghost() 模式（背景全透明）：自动加 1px 黑色阴影
        - outline 显式传颜色时再画一圈四方向 1px 描边——彩蛋行给价格用"""
        if self._light_bg():
            p.setPen(QPen(QColor(255, 255, 255, 200)))
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                p.drawText(rect.translated(dx, dy), align, txt)
        elif self._ghost():
            p.setPen(QPen(QColor(0, 0, 0, 200)))
            p.drawText(rect.translated(1, 1), align, txt)
        if outline is not None:
            p.setPen(QPen(outline))
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                p.drawText(rect.translated(dx, dy), align, txt)
        p.setPen(QPen(color))
        p.drawText(rect, align, txt)

    def _dim(self, base_alpha):
        """装饰性元素（分隔线/色块/边框）的透明度跟随背景走，背景全透明时它们也消失"""
        ba = int(self.cfg.get("bg_alpha", 190))
        return int(base_alpha * ba / 255)

    def _index_bar(self, p, w, y):
        """大盘指数条：上证 / 深证 / 创业板"""
        if not self.indices:
            return
        la = self._dim(14)
        if la > 0:
            p.setPen(QPen(QColor(255, 255, 255, la), 1))
            p.drawLine(14, y, w - 14, y)
        p.setFont(QFont("Microsoft YaHei", 7.5))
        slot = (w - 28) // 3
        for i, r in enumerate(self.indices[:3]):
            pct = r["pct"]
            color = (self._up() if pct > 0
                     else (self._down() if pct < 0 else self._flat()))
            txt = "%s %+.2f%%" % (INDEX_NAMES_LIST[i] if i < len(INDEX_NAMES_LIST) else r["code"], pct)
            if i == 0:
                rect, align = QRect(14, y, slot, IDX_H), Qt.AlignVCenter | Qt.AlignLeft
            elif i == 1:
                rect, align = QRect(14 + slot, y, slot, IDX_H), Qt.AlignVCenter | Qt.AlignCenter
            else:
                rect, align = QRect(14 + slot * 2, y, slot, IDX_H), Qt.AlignVCenter | Qt.AlignRight
            self._text(p, rect, align, txt, color)

    # ---- 收盘彩蛋：火焰 / 冰霜 ----
    def _row_effect(self, code):
        """返回该行当前的彩蛋类型："fire" / "frost" / None"""
        e = self.effects.get(code)
        if not e:
            return None
        if e["until"] <= time.time():
            return None
        return e["type"]

    @staticmethod
    def _noise(v):
        """伪噪声：多个不同频率正弦叠加，输出约 -1..1。
        比单一 sin 自然得多——不会出现机械的等幅摆动。"""
        return (math.sin(v) * 0.5
                + math.sin(v * 2.31 + 1.7) * 0.3
                + math.sin(v * 4.73 + 0.4) * 0.2)

    def _draw_fire(self, p, x, y, w, h):
        """格子发烫：只有红色底色（底部热辐射 + 竖直暖光）+ 12 颗上升火星。
        没有火焰 / 火苗 / 火舌形状——热度靠底色和火星表达。"""
        t = time.time()
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(x, y, w, h), 8, 8)

        # 1) 底部热量辐射辉光（#FF5500 橙红点缀色）
        rg = QRadialGradient(x + w / 2, y + h, w * 0.6)
        rg.setColorAt(0, QColor(255, 85, 0, 104))
        rg.setColorAt(0.55, QColor(255, 85, 0, 50))
        rg.setColorAt(1, QColor(255, 85, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawPath(frame)

        # 2) 竖直暖光渐变（自下而上由浓到淡）
        g = QLinearGradient(0, y + h, 0, y)
        g.setColorAt(0, QColor(255, 85, 0, 118))
        g.setColorAt(0.45, QColor(255, 128, 24, 54))
        g.setColorAt(1, QColor(255, 200, 90, 0))
        p.setBrush(g)
        p.drawPath(frame)

        # 3) 上升的火星余烬 —— 唯一的动感来源
        base = y + h - 3
        for k in range(12):
            seed = k * 1.37
            life = (t * 0.45 + k / 12.0) % 1.0
            start_x = x + w * (0.06 + 0.88 * ((math.sin(seed * 3.1) + 1) / 2))
            ex = start_x + 5.5 * math.sin(t * 1.9 + seed * 5.0) * life
            ey = base - life * h * 1.05            # 略超过 cell 顶部
            a = int(235 * (1.0 - life) ** 1.7)
            if a <= 4:
                continue
            sz = 2.4 * (1.0 - life * 0.55)
            # 火星由亮黄转橙再转暗红
            cg = int(170 + 85 * (1.0 - life))
            cb = int(110 * (1.0 - life) ** 1.5)
            p.setBrush(QColor(255, cg, cb, a))
            p.drawEllipse(QRectF(ex - sz / 2, ey - sz / 2, sz, sz))

        # 4) 呼吸描边（#FF5500）
        a = 118 + int(62 * (1 + self._noise(t * 2.6)) / 2)
        p.setPen(QPen(QColor(255, 85, 0, a), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawPath(frame)

    def _draw_frost(self, p, x, y, w, h):
        """格子结冰 —— 水晶蓝白配色（参考宝石切割的高光与折射）：
        主体 #E8F2FE / #B5D2F0 / #D6E6FA 浅水晶蓝白渐变，中心白色高光向外淡出到宝蓝，
        #FFFFFF 纯白当反光、雪花、冰晶。没有裂纹、没有边缘锯齿、没有青绿色调。"""
        t = time.time()
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(x, y, w, h), 8, 8)

        # 1) 水晶蓝白渐变（纯蓝白，没有青绿）
        g = QLinearGradient(0, y, 0, y + h)
        g.setColorAt(0.0, QColor(232, 242, 254, 162))    # #E8F2FE
        g.setColorAt(0.5, QColor(181, 210, 240, 96))     # #B5D2F0
        g.setColorAt(1.0, QColor(214, 230, 250, 162))    # #D6E6FA
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(frame)

        # 2) 中心水晶高光（白色向外淡出到宝蓝 #5B95E8）
        br = 0.65 + 0.35 * (0.5 + 0.5 * self._noise(t * 1.1))
        eg = QRadialGradient(x + w * 0.42, y + h * 0.50, w * 0.62)
        eg.setColorAt(0.00, QColor(255, 255, 255, int(96 * br)))
        eg.setColorAt(0.45, QColor(214, 230, 250, int(58 * br)))
        eg.setColorAt(1.00, QColor(91, 149, 232, 0))       # 收尾到宝蓝透明
        p.setBrush(eg)
        p.drawPath(frame)

        # 3) 斜向冰面反光：纯白，比之前更亮更冷
        sh = QLinearGradient(x, y, x + w * 0.6, y + h)
        sh.setColorAt(0.00, QColor(255, 255, 255, 0))
        sh.setColorAt(0.40, QColor(255, 255, 255, 86))
        sh.setColorAt(0.48, QColor(255, 255, 255, 118))
        sh.setColorAt(0.56, QColor(255, 255, 255, 86))
        sh.setColorAt(1.00, QColor(255, 255, 255, 0))
        p.setBrush(sh)
        p.drawPath(frame)

        # 4) 飘落的雪花（纯白，缓慢下沉 + 横向摇摆）
        for k in range(9):
            seed = k * 1.91
            life = (t * 0.20 + k / 9.0) % 1.0
            sx = x + w * (0.08 + 0.84 * ((math.sin(seed * 2.7) + 1) / 2))
            px_ = sx + 3.2 * math.sin(t * 0.75 + seed * 4.0)
            py_ = y + 3 + life * (h - 6)
            a = int(192 * math.sin(life * math.pi))     # 中段最明显，两头淡出
            if a <= 3:
                continue
            sz = 1.9
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QRectF(px_ - sz / 2, py_ - sz / 2, sz, sz))

        # 5) 六角冰晶：三处，缓慢闪烁（避开涨幅块）
        tw = 0.70 + 0.30 * self._noise(t * 1.7)
        for ux, uy, rr in ((0.50, 0.30, 5.5), (0.20, 0.78, 4.2), (0.55, 0.78, 3.4)):
            cx, cy = x + ux * w, y + uy * h
            a = int(232 * tw)
            p.setPen(QPen(QColor(255, 255, 255, a), 1.1))
            for k in range(3):                       # 三条过中心的线 = 六角
                ang = math.radians(60 * k + 12)
                dx, dy = math.cos(ang) * rr, math.sin(ang) * rr
                p.drawLine(QLineF(cx - dx, cy - dy, cx + dx, cy + dy))
            # 端部分叉：浅水晶蓝
            p.setPen(QPen(QColor(181, 210, 240, int(a * 0.78)), 0.9))
            for k in range(3):
                ang = math.radians(60 * k + 12)
                for sgn in (1, -1):
                    ex = cx + math.cos(ang) * rr * sgn
                    ey = cy + math.sin(ang) * rr * sgn
                    for da in (-0.7, 0.7):
                        aa = ang + da
                        p.drawLine(QLineF(ex, ey, ex + math.cos(aa) * 2.0,
                                          ey + math.sin(aa) * 2.0))

        # 6) 描边：宝蓝 #5B95E8（饱和度更高，更像水晶切割面）
        a = 132 + int(56 * (1 + self._noise(t * 1.9)) / 2)
        p.setPen(QPen(QColor(91, 149, 232, a), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(frame)

    def _row(self, p, r, y, i):
        w = W_WIDTH            # 逻辑宽度（paintEvent 已 scale，不能用 self.width()）
        if i:
            la = self._dim(16)
            if la > 0:
                p.setPen(QPen(QColor(255, 255, 255, la), 1))
                p.drawLine(14, y, w - 14, y)

        pct = r["pct"]
        color = (self._up() if pct > 0
                 else (self._down() if pct < 0 else self._flat()))

        # 多选模式：选中行整行底色高亮
        sel = self.sel_mode and (r.get("full") or r.get("code")) in self.selected
        if sel:
            hl = QPainterPath()
            hl.addRoundedRect(QRectF(6, y + 2, w - 12, ROW_H - 4), 8, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(96, 165, 250, 42))
            p.drawPath(hl)

        # 收盘彩蛋（14:57 定格，持续 3 分钟）
        eff = self._row_effect(r.get("code"))
        if eff == "fire":
            self._draw_fire(p, 6, y + 2, w - 12, ROW_H - 4)
        elif eff == "frost":
            self._draw_frost(p, 6, y + 2, w - 12, ROW_H - 4)
        # 彩蛋行文字描边：火焰/冰霜背景亮，加深色轮廓保证可读
        ol = QColor(58, 10, 0, 215) if eff == "fire" else (
            QColor(19, 53, 119, 205) if eff == "frost" else None)   # #133577

        # 异动高亮（触发后 10 秒内呼吸闪烁）
        ft = self.flash.get(r["code"])
        if ft and time.time() - ft < 10:
            glow = QPainterPath()
            glow.addRoundedRect(QRectF(6, y + 2, w - 12, ROW_H - 4), 8, 8)
            p.setPen(Qt.NoPen)
            a = 24 + int(26 * (1 + math.sin(time.time() * 5)) / 2)
            p.setBrush(QColor(color.red(), color.green(), color.blue(), a))
            p.drawPath(glow)

        # 多选模式：左侧复选框
        ox = 0                 # 内容整体右移，给复选框腾位置
        if self.sel_mode:
            ox = 22
            cbx, cby, cbs = 14, y + (ROW_H - 15) / 2, 15
            box = QPainterPath()
            box.addRoundedRect(QRectF(cbx, cby, cbs, cbs), 4, 4)
            if sel:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#60a5fa"))
                p.drawPath(box)
                p.setPen(QPen(QColor("#0b1020"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawLine(cbx + 4, cby + 7.5, cbx + 6.5, cby + 10.5)
                p.drawLine(cbx + 6.5, cby + 10.5, cbx + 11, cby + 4.5)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 110), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(box)

        # 名称 + 代码
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        name = r["name"]
        self._text(p, QRect(14 + ox, y + 6, 140, 18), Qt.AlignVCenter | Qt.AlignLeft, name, self._fg(), ol)
        p.setFont(QFont("Microsoft YaHei", 7))
        fm = QFontMetrics(QFont("Microsoft YaHei", 9, QFont.Bold))
        nx = 14 + ox + fm.horizontalAdvance(name) + 6
        self._text(p, QRect(nx, y + 7, 60, 16), Qt.AlignVCenter | Qt.AlignLeft, r["code"], self._fg_fade())

        # 涨跌幅色块
        bw, bh = 58, 20
        bx = w - 14 - bw
        by = y + 6
        block = QPainterPath()
        block.addRoundedRect(QRectF(bx, by, bw, bh), 5, 5)
        p.setPen(Qt.NoPen)
        ba = self._dim(46)
        if ba > 0:
            p.setBrush(QColor(color.red(), color.green(), color.blue(), ba))
            p.drawPath(block)
        p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        sign = "+" if pct > 0 else ""
        self._text(p, QRectF(bx, by, bw, bh), Qt.AlignCenter, "%s%.2f%%" % (sign, pct), color, ol)

        # 现价 + 涨跌额
        d = r.get("decimals", 2)
        p.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        price_txt = "%.*f" % (d, r["price"])
        self._text(p, QRect(14 + ox, y + 24, 90, 18), Qt.AlignVCenter | Qt.AlignLeft, price_txt, color, ol)
        pw = QFontMetrics(QFont("Microsoft YaHei", 12, QFont.Bold)).horizontalAdvance(price_txt)
        p.setFont(QFont("Microsoft YaHei", 7.5))
        chg_txt = "%s%.*f" % ("+" if r["change"] > 0 else "", d, r["change"])
        self._text(p, QRect(14 + ox + pw + 6, y + 25, 70, 16), Qt.AlignVCenter | Qt.AlignLeft, chg_txt, color, ol)

        # 持仓盈亏（只在填了成本价的股票上显示）
        pos = (self.cfg.get("positions") or {}).get(r.get("full", ""))
        if pos and pos.get("cost"):
            try:
                cost = float(pos["cost"])
            except (TypeError, ValueError):
                cost = 0.0
            if cost > 0:
                pl_pct = (r["price"] - cost) / cost * 100
                plc = (self._up() if pl_pct > 0
                       else (self._down() if pl_pct < 0 else self._flat()))
                shares = pos.get("shares")
                if shares:
                    amt = (r["price"] - cost) * float(shares)
                    ptxt = "%+.0f (%+.1f%%)" % (amt, pl_pct)
                else:
                    ptxt = "%+.2f%%" % pl_pct
                cw = QFontMetrics(QFont("Microsoft YaHei", 7.5)).horizontalAdvance(chg_txt)
                p.setFont(QFont("Microsoft YaHei", 7.5, QFont.Bold))
                self._text(p, QRect(14 + ox + pw + 6 + cw + 8, y + 25, 84, 16),
                           Qt.AlignVCenter | Qt.AlignLeft, ptxt, plc, ol)

        # 分时走势
        if self.cfg.get("spark", True):
            pts = r.get("spark")
            if pts and len(pts) > 2:
                sx, sy = w - 14 - 62, y + 24
                sw, sh = 62, 18
                self._spark(p, pts, sx, sy, sw, sh, color, r["prev"])

    def _spark(self, p, pts, x, y, w, h, color, prev):
        lo, hi = min(pts), max(pts)
        base = prev or (lo + hi) / 2
        lo = min(lo, base)
        hi = max(hi, base)
        span = (hi - lo) or 0.01
        step = w / (len(pts) - 1)
        p.save()
        p.setClipRect(QRectF(x, y - 2, w, h + 4))
        # 昨收基准线（背景全透明时改成深色虚线，否则在浅壁纸上会看不见）
        la = self._dim(28)
        if la > 0:
            p.setPen(QPen(QColor(255, 255, 255, la), 1, Qt.DashLine))
        else:
            p.setPen(QPen(QColor(0, 0, 0, 120), 1, Qt.DashLine))
        by = y + h - (base - lo) / span * h
        p.drawLine(x, by, x + w, by)
        path = QPainterPath()
        for i, v in enumerate(pts):
            px = x + i * step
            py = y + h - (v - lo) / span * h
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        p.setPen(QPen(color, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.restore()

    def _footer(self, p, w, h):
        p.setFont(QFont("Microsoft YaHei", 7))
        if self.sel_mode:
            # 多选模式：左边显示已选数量，右边两个按钮
            n = len(self.selected)
            self._text(p, QRect(14, h - FOOTER_H, 90, FOOTER_H),
                       Qt.AlignVCenter | Qt.AlignLeft, "已选 %d 只" % n, self._fg_dim())
            del_r, cancel_r = self.footer_buttons()
            # 浅色壁纸下"取消"按钮改用深色底 + 深色字，白底白字会看不见
            cancel_bg = (QColor(20, 24, 30, 40) if self._light_bg()
                         else QColor(255, 255, 255, 26))
            for rect, label, bg, fg in (
                (cancel_r, "取消", cancel_bg, self._fg_dim()),
                (del_r, "删除%s" % ("(%d)" % n if n else ""), QColor(220, 38, 45, 210), QColor("#ffffff")),
            ):
                bp = QPainterPath()
                bp.addRoundedRect(rect, 4, 4)
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawPath(bp)
                p.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
                self._text(p, rect.toRect(), Qt.AlignCenter, label, fg)
            return
        status = self.err or ("更新 %s · %ss · %s" % (
            self.updated_at, self.cfg.get("interval", 3),
            "交易中" if is_trading_now() else "休市"))
        self._text(p, QRect(14, h - FOOTER_H, w - 28, FOOTER_H), Qt.AlignVCenter | Qt.AlignLeft,
                   status, self._fg_fade())

    # ---- 交互 ----
    # ---- 多选删除：命中测试 ----
    def _logic_pos(self, e):
        """鼠标事件坐标 -> 逻辑坐标（paintEvent 里做过 p.scale，所以要除回去）"""
        lp = e.position() if hasattr(e, "position") else e.localPos()
        return lp.x() / self.scale, lp.y() / self.scale

    def hit_test(self, lx, ly):
        """逻辑坐标 -> ('row', idx) / ('footer', None) / ('header', None)"""
        show_idx = self.cfg.get("show_index", True)
        body_y = HEADER_H + (IDX_H if show_idx else 0)
        if ly < body_y:
            return ("header", None)
        if self.rows:
            idx = int((ly - body_y) // ROW_H)
            if 0 <= idx < len(self.rows):
                return ("row", idx)
        return ("footer", None)

    def footer_buttons(self):
        """选择模式下，底部两个按钮的逻辑矩形：(删除, 取消)"""
        w = W_WIDTH
        h = self.height() / self.scale
        bh = FOOTER_H - 3
        by = h - FOOTER_H + 1
        del_w, cancel_w = 62, 40
        del_r = QRectF(w - 14 - del_w, by, del_w, bh)
        cancel_r = QRectF(w - 14 - del_w - 6 - cancel_w, by, cancel_w, bh)
        return del_r, cancel_r

    def _full_of_row(self, idx):
        r = self.rows[idx]
        return r.get("full") or r.get("code")

    # ---- 多选删除：状态切换 ----
    def enter_sel_mode(self, idx=None):
        self.sel_mode = True
        self.selected = set()
        if idx is not None and 0 <= idx < len(self.rows):
            self.selected.add(self._full_of_row(idx))
        self.drag_pos = None          # 多选时不再拖窗口，免得点选变成移动
        self.update()

    def exit_sel_mode(self):
        self.sel_mode = False
        self.selected = set()
        self.update()

    def _on_long_press(self):
        if self._moved or self._press_row is None:
            return
        self.enter_sel_mode(self._press_row)

    def delete_selected(self):
        if not self.selected:
            self.exit_sel_mode()
            return
        codes = [c for c in (self.cfg.get("codes") or []) if c not in self.selected]
        self.cfg["codes"] = codes
        positions = self.cfg.get("positions") or {}
        for c in self.selected:
            positions.pop(c, None)      # 删股票同时清掉它的持仓，免得留下脏数据
        self.cfg["positions"] = positions
        save_config(self.cfg)
        self.fetcher.codes = codes
        self.fetcher._spark_tick = 0
        self.exit_sel_mode()
        self.resize_to_rows()

    def mousePressEvent(self, e):
        # 拿到键盘焦点：全局监听只能收到"进入本应用"的按键，窗口没焦点时
        # 方向键是发给别的程序的，口令就收不到。activateWindow 是 setFocus 的保险。
        self.activateWindow()
        self.setFocus()
        lx, ly = self._logic_pos(e)
        kind, idx = self.hit_test(lx, ly)

        # 备用解锁：连击左上角状态点（见 DOT_TAP_WINDOW / DOT_TAP_N）
        # 键盘口令必须窗口有焦点才收得到，鼠标点击则一定能收到，留条后路。
        if ly < HEADER_H and lx < 22 and e.button() == Qt.LeftButton:
            now = time.time()
            if now - self._dot_taps_at > DOT_TAP_WINDOW:
                self._dot_taps = 0
            self._dot_taps_at = now
            self._dot_taps += 1
            if self._dot_taps >= DOT_TAP_N:
                self._dot_taps = 0
                self._toggle_unlock()
                e.accept()
                return

        if e.button() == Qt.RightButton:
            if self.sel_mode:
                self.exit_sel_mode()          # 多选态下右键 = 取消
                e.accept()
                return
            if kind == "row":
                self.enter_sel_mode(idx)      # 在股票上右键 = 进入多选并勾上它
                self.show_row_menu(e.globalPosition().toPoint(), idx)
            else:
                self.show_menu(e.globalPosition().toPoint())
            e.accept()
            return

        if e.button() == Qt.LeftButton:
            if self.sel_mode:
                if kind == "row":
                    full = self._full_of_row(idx)
                    if full in self.selected:
                        self.selected.discard(full)
                    else:
                        self.selected.add(full)
                    self.update()
                elif kind == "footer":
                    del_r, cancel_r = self.footer_buttons()
                    if del_r.contains(lx, ly):
                        self.delete_selected()
                    elif cancel_r.contains(lx, ly):
                        self.exit_sel_mode()
                e.accept()
                return
            # 普通模式：记下按下点，长按 450ms 进多选；移动超过阈值则当拖窗口
            if not self.cfg.get("locked"):
                self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = e.globalPosition().toPoint()
            self._press_row = idx if kind == "row" else None
            self._moved = False
            if self._press_row is not None:
                self._long_timer.start()
            e.accept()

    def mouseMoveEvent(self, e):
        if self.drag_pos and e.buttons() & Qt.LeftButton:
            # 移动超过阈值就认定是拖窗口，取消长按
            if self._press_pos is not None:
                d = e.globalPosition().toPoint() - self._press_pos
                if abs(d.x()) > 5 or abs(d.y()) > 5:
                    if not self._moved:
                        self._moved = True
                        self._long_timer.stop()
            raw = e.globalPosition().toPoint() - self.drag_pos
            self.move(*self.snap_pos(raw.x(), raw.y(), e.globalPosition().toPoint()))
            e.accept()

    def mouseReleaseEvent(self, e):
        self._long_timer.stop()
        if self.drag_pos:
            self.move(*self.snap_pos(self.x(), self.y(),
                                     e.globalPosition().toPoint()))  # 松手再吸一次，保证落位
            self.cfg["pos"] = [self.x(), self.y()]
            save_config(self.cfg)
            # 拖到新位置，壁纸可能不一样了 —— 重采一次
            QTimer.singleShot(250, lambda: self.sample_bg(force=True))
        self.drag_pos = None
        self._press_pos = None
        self._press_row = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.sel_mode:
            self.exit_sel_mode()
            e.accept()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        # 摘掉装在 QApplication 上的全局监听，否则本对象销毁后 app 还会回调它
        _app = QApplication.instance()
        if _app is not None:
            _app.removeEventFilter(self)
        # 窗口被关（Alt+F4 等）不走 quit()，这里也要清一次强制特效
        self.clear_forced_festivals()
        super().closeEvent(e)

    # ---- 隐藏菜单的解锁口令：↑↑↓↓←→←→ B A B A ----
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and not ev.isAutoRepeat():
            self._feed_konami(ev.key())
        return False   # 绝不拦截，原样放行（搜索框还要正常打字）

    def _feed_konami(self, key):
        now = time.time()
        # 口令必须在 KONAMI_TIMEOUT 秒内一口气输完，超时作废重来
        if self._konami and now - self._konami_t0 > KONAMI_TIMEOUT:
            self._konami = []
            self._konami_t0 = 0.0
            self._konami_show = now + 0.6
        if key not in KONAMI_KEYS:      # 不属于口令的键：直接清空，重新来
            if self._konami:
                self._konami = []
                self._konami_show = now + 0.6
            self._konami_t0 = 0.0
            return
        if not self._konami:
            self._konami_t0 = now       # 从第一个键开始计时
        seq = self._konami
        seq.append(key)
        # 剪掉头部，直到剩下的是 KONAMI 的前缀（这样按错了也能继续接上）
        while seq and seq != KONAMI[:len(seq)]:
            del seq[0]
        self._konami_show = now + 1.6   # 进度点显示 1.6 秒
        if seq == KONAMI:
            seq.clear()
            self._konami_t0 = 0.0
            self._konami_show = 0.0
            self._toggle_unlock()

    def _toggle_unlock(self):
        """口令正确 → 解锁。已经解锁就只提示，不再收起。

        原来的「再输一次收起」太坑：手滑多输一遍开关就没了（真事：5 分钟内被触发了
        5 次）。现在口令只负责开，收起走菜单里那一项。
        """
        if self._unlocked:
            if getattr(self, "tray", None):
                self.tray.showMessage("A股盯盘", "已经解锁了 —— 右键菜单里就能看到",
                                      QSystemTrayIcon.Information, 2500)
            self.pulse = 4
            self.update()
            return
        self._unlocked = True
        self.cfg["unlocked"] = True
        try:
            save_config(self.cfg)
        except Exception:
            pass
        if getattr(self, "tray", None):
            self.tray.showMessage("A股盯盘", "节日彩蛋开关已解锁 —— 右键菜单可见",
                                  QSystemTrayIcon.Information, 4000)
        self.pulse = 6          # 状态点闪几下当反馈
        self.update()

    def lock_hidden_menu(self):
        """收起节日彩蛋开关（菜单项，解锁后可见）"""
        self._unlocked = False
        self.cfg["unlocked"] = False
        try:
            save_config(self.cfg)
        except Exception:
            pass
        if getattr(self, "tray", None):
            self.tray.showMessage("A股盯盘", "节日彩蛋开关已收起",
                                  QSystemTrayIcon.Information, 2500)
        self.update()

    def contextMenuEvent(self, e):
        self.show_menu(e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        self.show_menu(e.globalPosition().toPoint())

    def show_row_menu(self, pos, idx):
        """在某只股票上右键：直接给出针对这一只的操作"""
        self.activateWindow()
        self.raise_()
        r = self.rows[idx]
        full = self._full_of_row(idx)
        name = r["name"]
        m = QMenu(self)
        act_del = m.addAction("删除「%s」" % name)
        act_cost = m.addAction("编辑这只的持仓成本")
        m.addSeparator()
        act_all = m.addAction("全选 %d 只" % len(self.rows))
        act_cancel = m.addAction("取消多选")
        act = m.exec(pos)
        if act is None:
            return
        if act is act_del:
            self.selected = {full}
            self.delete_selected()
        elif act is act_cost:
            self.exit_sel_mode()
            self.edit_positions()
        elif act is act_all:
            self.selected = {self._full_of_row(i) for i in range(len(self.rows))}
            self.update()
        elif act is act_cancel:
            self.exit_sel_mode()

    def show_menu(self, pos):
        self.activateWindow()
        self.raise_()
        m = QMenu(self)
        m.setWindowFlags(m.windowFlags() | Qt.NoDropShadowWindowHint)
        m.setStyleSheet("""
            QMenu { background:#181a20; color:#e8eaed; border:1px solid #2a2d35; padding:5px; }
            QMenu::item { padding:6px 24px 6px 18px; border-radius:4px; font-family:'Microsoft YaHei'; font-size:9pt; }
            QMenu::item:selected { background:#2a2f3a; }
            QMenu::separator { height:1px; background:#2a2d35; margin:4px 8px; }
        """)
        self._build_menu(m)
        m.exec(pos)

    def _build_menu(self, m):
        """右键菜单的内容。

        单独拆成方法是为了可测：QMenu.exec() 会阻塞事件循环（而且是 C++ 绑定，
        monkeypatch 不掉），拆出来后测试可以直接构造菜单检查项，不用真的弹出。
        """
        m.addAction("修改标题").triggered.connect(self.edit_title)
        m.addAction("多选删除股票…").triggered.connect(lambda: self.enter_sel_mode())
        m.addAction("编辑股票代码（最多5只）").triggered.connect(self.edit_codes)
        m.addAction("编辑持仓成本 / 盈亏").triggered.connect(self.edit_positions)

        sub_i = m.addMenu("刷新间隔")
        for v in (1, 3, 5, 10, 30):
            a = sub_i.addAction("%d 秒" % v)
            a.setCheckable(True)
            a.setChecked(int(self.cfg.get("interval", 3)) == v)
            a.triggered.connect(lambda _, x=v: self.set_interval(x))

        sub_a = m.addMenu("异动提醒阈值")
        cur_a = float(self.cfg.get("alert_pct") or 0)
        for label, v in (("关闭", 0), ("±1%", 1.0), ("±2%", 2.0), ("±3%", 3.0), ("±5%", 5.0)):
            a = sub_a.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(cur_a - v) < 0.01)
            a.triggered.connect(lambda _, x=v: self.set_alert(x))

        sub_e = m.addMenu("收盘彩蛋阈值（14:57）")
        cur_e = float(self.cfg.get("effect_pct") or 0)
        for label, v in (("关闭", 0), ("±2%", 2.0), ("±3%", 3.0), ("±5%", 5.0)):
            a = sub_e.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(cur_e - v) < 0.01)
            a.triggered.connect(lambda _, x=v: self.set_effect_pct(x))

        # 节日彩蛋 —— 默认隐藏，需口令 ↑↑↓↓←→←→ B A B A 解锁
        if self._unlocked:
            sub_f = m.addMenu("节日特效")
            nxt = next_festival()
            if nxt:
                head = sub_f.addAction("下次触发：%s %s" % (nxt[1].strftime("%m-%d"),
                                                           nxt[0]["name"]))
            else:
                head = sub_f.addAction("近 400 天内没有节日")
            head.setEnabled(False)
            sub_f.addSeparator()
            for f in FESTIVALS:                 # 表驱动：加节日不用改这里
                a = sub_f.addAction("%s %s（强制）" % (f["icon"], f["name"]))
                a.setCheckable(True)
                a.setChecked(bool(self.cfg.get(f["key"] + "_test")))
                a.triggered.connect(lambda _, k=f["key"]: self.toggle_festival(k))
            sub_f.addSeparator()
            sub_f.addAction("全部关闭").triggered.connect(self.clear_festivals)
            sub_f.addAction("🔒 收起节日特效菜单").triggered.connect(self.lock_hidden_menu)

        sub_o = m.addMenu("背景透明度")
        for label, v in (("0%（仅文字）", 0), ("20%", 51), ("40%", 102),
                         ("60%", 153), ("75%", 191), ("90%", 230), ("100%", 255)):
            a = sub_o.addAction(label)
            a.setCheckable(True)
            a.setChecked(int(self.cfg.get("bg_alpha", 190)) == v)
            a.triggered.connect(lambda _, x=v: self.set_alpha(x))

        sub_s = m.addMenu("界面大小")
        for label, v in (("小 85%", 0.85), ("标准", 1.0), ("大 115%", 1.15), ("特大 130%", 1.3)):
            a = sub_s.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(self.scale - v) < 0.01)
            a.triggered.connect(lambda _, x=v: self.set_scale(x))

        m.addSeparator()

        a_idx = m.addAction("大盘指数（上证/深证/创业板）")
        a_idx.setCheckable(True)
        a_idx.setChecked(bool(self.cfg.get("show_index", True)))
        a_idx.triggered.connect(self.toggle_index)

        a_spark = m.addAction("分时走势图")
        a_spark.setCheckable(True)
        a_spark.setChecked(bool(self.cfg.get("spark", True)))
        a_spark.triggered.connect(self.toggle_spark)

        a_snap = m.addAction("拖动吸附屏幕边缘")
        a_snap.setCheckable(True)
        a_snap.setChecked(bool(self.cfg.get("snap", True)))
        a_snap.triggered.connect(self.toggle_snap)

        a_lock = m.addAction("锁定位置")
        a_lock.setCheckable(True)
        a_lock.setChecked(bool(self.cfg.get("locked")))
        a_lock.triggered.connect(self.toggle_lock)

        a_top = m.addAction("始终置顶")
        a_top.setCheckable(True)
        a_top.setChecked(bool(self.cfg.get("always_on_top", True)))
        a_top.triggered.connect(self.toggle_top)

        a_ct = m.addAction("鼠标穿透（用托盘恢复）")
        a_ct.setCheckable(True)
        a_ct.setChecked(bool(self.cfg.get("click_through")))
        a_ct.triggered.connect(self.toggle_click_through)

        a_auto = m.addAction("开机自启")
        a_auto.setCheckable(True)
        a_auto.setChecked(bool(self.cfg.get("autostart")))
        a_auto.triggered.connect(self.toggle_autostart)

        # 配置备份 / 回滚：持仓成本被误删过，有存档就能捞回来
        sub_b = m.addMenu("配置备份")
        sub_b.addAction("立即备份").triggered.connect(self.backup_now)
        sub_b.addAction("打开备份目录").triggered.connect(self.open_backup_dir)
        n_crash = len(list_crash_logs())
        sub_b.addAction("崩溃日志（%s）" % (n_crash or "无")).triggered.connect(
            self.open_log_dir)
        snaps = list_snapshots()[:8]
        if snaps:
            sub_b.addSeparator()
            for sp in snaps:
                d, t, seq = _snap_parts(sp)
                stamp = "%s-%s-%s %s:%s:%s" % (d[0:4], d[4:6], d[6:8],
                                               t[0:2], t[2:4], t[4:6])
                if seq > 1:                      # 同一秒存了好几份，标一下第几份
                    stamp += " (第%d份)" % seq
                sub_b.addAction("恢复到 %s" % stamp).triggered.connect(
                    lambda _, x=sp: self.restore_backup(x))
        else:
            a_none = sub_b.addAction("（暂无备份）")
            a_none.setEnabled(False)

        m.addSeparator()
        m.addAction("隐藏到托盘").triggered.connect(self.hide)
        m.addAction("退出").triggered.connect(self.quit)
        m.addSeparator()
        act_about = m.addAction("%s %s" % (APP_NAME, APP_VERSION))
        act_about.setEnabled(False)

    # ---- 菜单动作 ----
    def edit_codes(self):
        cur = ", ".join(self.cfg.get("codes") or [])
        text, ok = QInputDialog.getText(
            self, "编辑股票", "输入代码，逗号分隔，最多 5 只：\n（如 600519, 000001, 300750）",
            text=cur,
        )
        if not ok:
            return
        codes, bad = [], []
        for item in text.replace("，", ",").replace("、", ",").replace(" ", ",").split(","):
            if not item.strip():
                continue
            c = normalize_code(item)
            if c:
                codes.append(c)
            else:
                bad.append(item)
        codes = codes[:5]
        self.cfg["codes"] = codes
        save_config(self.cfg)
        self.fetcher.codes = codes
        self.fetcher._spark_tick = 0
        self.rows = []
        self.resize_to_rows()
        self.update()
        if bad:
            QMessageBox.warning(self, "部分代码未识别", "未识别：%s" % ", ".join(bad))

    def edit_title(self):
        cur = self.cfg.get("title") or "A股盯盘"
        text, ok = QInputDialog.getText(self, "修改标题", "窗口标题（最多 12 字）：", text=cur)
        if not ok:
            return
        t = (text or "").strip()[:12] or "A股盯盘"
        self.cfg["title"] = t
        self.setWindowTitle(t)
        save_config(self.cfg)
        self.update()

    def _positions_text(self):
        out = []
        for code, p in (self.cfg.get("positions") or {}).items():
            c, s = p.get("cost"), p.get("shares")
            if c is None:
                continue
            out.append("%s=%s:%s" % (code, c, s) if s else "%s=%s" % (code, c))
        return ", ".join(out)

    def edit_positions(self):
        text, ok = QInputDialog.getText(
            self, "编辑持仓成本",
            "格式：代码=成本价[:股数]，逗号分隔\n"
            "例：600519=1250:100, 000001=11.5\n\n"
            "填了股数显示盈亏金额，省略则只显示盈亏比例。\n"
            "不填的股票不显示盈亏。",
            text=self._positions_text())
        if not ok:
            return
        self.cfg["positions"] = parse_positions(text)
        save_config(self.cfg)
        self.update()
        self.update_tray_tip()

    def set_interval(self, v):
        self.cfg["interval"] = v
        self.fetcher.fast = v
        save_config(self.cfg)
        self.update()

    def set_scale(self, v):
        self.cfg["ui_scale"] = v
        self.scale = float(v)
        save_config(self.cfg)
        self.resize_to_rows()
        self.update()

    def set_alpha(self, v):
        self.cfg["bg_alpha"] = v
        save_config(self.cfg)
        self._update_edit_style()
        # 透明度变了，可能需要重新判断壁纸明暗
        QTimer.singleShot(150, lambda: self.sample_bg(force=True))
        self.update()

    def toggle_festival(self, key):
        """菜单切换某个节日的「强制开启」。同时只让一个生效 —— 打开这个就关掉别的。"""
        k = key + "_test"
        on = not self.cfg.get(k)
        for f in FESTIVALS:                 # 单激活：一次只能强制一个
            self.cfg[f["key"] + "_test"] = False
        self.cfg[k] = on
        save_config(self.cfg)
        self.update()

    def clear_festivals(self):
        """全部关闭（回到按日期自动触发）"""
        for f in FESTIVALS:
            self.cfg[f["key"] + "_test"] = False
        save_config(self.cfg)
        self.update()

    def _update_edit_style(self):
        """背景接近全透明时，搜索框得有自己的深色底，否则在浅色壁纸上完全看不见"""
        if not hasattr(self, "search_edit"):
            return
        dark = self._ghost()
        self.search_edit.setStyleSheet(EDIT_QSS_DARK if dark else EDIT_QSS)
        pal = self.search_edit.palette()
        pal.setColor(QPalette.PlaceholderText,
                     QColor("#b9bfc9" if dark else "#8b8f9a"))
        self.search_edit.setPalette(pal)

    def set_alert(self, v):
        self.cfg["alert_pct"] = v
        save_config(self.cfg)

    def set_effect_pct(self, v):
        self.cfg["effect_pct"] = v
        save_config(self.cfg)
        if v <= 0:
            self.effects = {}
            self.update()

    def toggle_index(self):
        self.cfg["show_index"] = not self.cfg.get("show_index", True)
        self.fetcher.show_index = self.cfg["show_index"]
        save_config(self.cfg)
        self.resize_to_rows()
        self.update()

    def toggle_spark(self):
        self.cfg["spark"] = not self.cfg.get("spark", True)
        save_config(self.cfg)
        self.update()

    def toggle_lock(self):
        self.cfg["locked"] = not self.cfg.get("locked")
        save_config(self.cfg)

    def toggle_snap(self):
        self.cfg["snap"] = not self.cfg.get("snap", True)
        save_config(self.cfg)
        if self.cfg["snap"]:                    # 打开时立刻吸一次，省得用户还得拖一下
            self.move(*self.snap_pos(self.x(), self.y()))

    def toggle_top(self):
        self.cfg["always_on_top"] = not self.cfg.get("always_on_top", True)
        save_config(self.cfg)
        self.apply_flags()

    def toggle_click_through(self):
        self.cfg["click_through"] = not self.cfg.get("click_through")
        save_config(self.cfg)
        self.apply_flags()

    def toggle_autostart(self):
        self.cfg["autostart"] = not self.cfg.get("autostart")
        save_config(self.cfg)
        set_autostart(self.cfg["autostart"])

    # ---- 配置备份 / 恢复 ----
    def backup_now(self):
        p = snapshot_config(force=True)
        if getattr(self, "tray", None):
            if p:
                self.tray.showMessage("A股盯盘", "已备份到 backups/%s" % os.path.basename(p),
                                      QSystemTrayIcon.Information, 3000)
            else:
                self.tray.showMessage("A股盯盘", "备份失败：配置文件读不到",
                                      QSystemTrayIcon.Warning, 3000)

    def open_backup_dir(self):
        d = _backup_dir()
        try:
            os.makedirs(d, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(d)      # noqa: S606 - 就是想用资源管理器打开
            else:
                import subprocess
                subprocess.Popen(["explorer", d])
        except Exception:
            pass

    def open_log_dir(self):
        """打开崩溃日志目录（pythonw 没有控制台，出错只能看这里）。"""
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(LOG_DIR)    # noqa: S606
        except Exception:
            pass

    def restore_backup(self, path):
        """回滚到某份快照：覆盖前会先自动备份当前状态，然后提示重启生效。"""
        if not restore_snapshot(path):
            QMessageBox.warning(self, "恢复失败", "这份备份读不出来，可能已损坏。")
            return
        if getattr(self, "tray", None):
            self.tray.showMessage("A股盯盘", "配置已回滚，重启挂件后生效",
                                  QSystemTrayIcon.Information, 4000)
        QMessageBox.information(
            self, "已恢复",
            "配置已回滚到这份备份（当前状态也顺手存了一份）。\n\n"
            "建议现在退出并重新启动挂件，让新配置完全生效。")

    # ---- 托盘 ----
    def build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(make_icon(FLAT))
        self.tray.activated.connect(lambda r: self.showNormal() if r == QSystemTrayIcon.Trigger else None)
        tm = QMenu()
        tm.setStyleSheet("QMenu{background:#181a20;color:#e8eaed;border:1px solid #2a2d35;padding:5px;}"
                         "QMenu::item{padding:6px 22px;border-radius:4px;font-family:'Microsoft YaHei';font-size:9pt;}"
                         "QMenu::item:selected{background:#2a2f3a;}")
        tm.addAction("显示 / 隐藏").triggered.connect(
            lambda: self.hide() if self.isVisible() else self.showNormal())
        tm.addAction("编辑股票").triggered.connect(self.edit_codes)
        tm.addAction("取消鼠标穿透").triggered.connect(
            lambda: (self.cfg.update({"click_through": False}), save_config(self.cfg), self.apply_flags()))
        tm.addSeparator()
        tm.addAction("退出").triggered.connect(self.quit)
        self.tray.setContextMenu(tm)
        self.tray.show()

    def update_tray_tip(self):
        if not self.rows:
            return
        positions = self.cfg.get("positions") or {}
        lines = []
        for r in self.rows:
            line = "%s %.*f  %s%.2f%%" % (
                r["name"], r.get("decimals", 2), r["price"],
                "+" if r["pct"] > 0 else "", r["pct"])
            pos = positions.get(r.get("full", ""))
            if pos and pos.get("cost"):
                try:
                    cost = float(pos["cost"])
                    if cost > 0:
                        pl = (r["price"] - cost) / cost * 100
                        line += "  持仓%+.2f%%" % pl
                        if pos.get("shares"):
                            line += " (%+.0f)" % ((r["price"] - cost) * float(pos["shares"]))
                except (TypeError, ValueError):
                    pass
            lines.append(line)
        self.tray.setToolTip("A股盯盘\n" + "\n".join(lines))

    def update_tray_icon(self):
        if not self.rows:
            return
        avg = sum(r["pct"] for r in self.rows) / len(self.rows)
        self.tray.setIcon(make_icon(UP if avg > 0 else (DOWN if avg < 0 else FLAT)))

    def clear_forced_festivals(self):
        """把所有「强制开启」的节日特效清掉 —— 特效只在特定日期自动触发。

        手动开的强制开关是持久化的，不清的话上次开的会一直挂着：
        2 月开的爱心能飘到 8 月。所以退出前一律清干净。
        """
        if not any(self.cfg.get(f["key"] + "_test") for f in FESTIVALS):
            return False
        for f in FESTIVALS:
            self.cfg[f["key"] + "_test"] = False
        try:
            save_config(self.cfg)
        except Exception:
            pass
        return True

    def quit(self):
        self.clear_forced_festivals()
        self.fetcher.stop()
        if hasattr(self, "searcher"):
            self.searcher.stop()
        self.tray.hide()
        QApplication.quit()


def make_icon(color):
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(3, 3, 58, 58)
    p.setPen(QColor("#101116"))
    p.setFont(QFont("Microsoft YaHei", 32, QFont.Bold))
    p.drawText(QRect(0, 0, 64, 66), Qt.AlignCenter, "A")
    p.end()
    return QIcon(pm)


def set_autostart(enable):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        name = "AStockWidget"
        if enable:
            bat = os.path.join(APP_DIR, "start.bat")
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, '"%s"' % bat)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def save_shot(widget, path):
    """自检用：把窗口绘制到白底上存成 png"""
    pix = widget.grab()
    img = QImage(pix.size(), QImage.Format_RGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.drawPixmap(0, 0, pix)
    p.end()
    img.save(path)
    print("SHOT_SAVED", path)


_singleton_locked = False   # 模块级：本进程是否已持有 mutex


def _singleton_check():
    """Windows 命名 mutex 单实例检测。
    已在运行 → True。没在运行 → False。

    CreateMutexW 返回的 handle **必须保留到进程结束**，不能 CloseHandle，
    否则 mutex 对象会销毁，下次同名 CreateMutexW 会"成功创建"。
    """
    global _singleton_locked
    if sys.platform != "win32":
        return False
    if _singleton_locked:                # 本进程已持有，再调只会看到自己（永远 False）
        return False
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    u32.MessageBoxW.restype  = wintypes.INT
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype  = wintypes.HANDLE
    k32.GetLastError.argtypes = []
    k32.GetLastError.restype  = wintypes.DWORD

    h = k32.CreateMutexW(None, False, "Local\\AStockWidget-Singleton-v1")
    if h:
        err = k32.GetLastError()
        if err == 183:                       # ERROR_ALREADY_EXISTS
            # 已存在时必须 CloseHandle：不然这个 handle 会一直占着 mutex 的
            # 引用计数，别人退出后 mutex 也不销毁，下次启动就永远是"已在运行"。
            k32.CloseHandle(h)
            return True
        _singleton_locked = True             # 本进程持 mutex 到退出（handle 不 Close）
    return False


def _windows_with_title(title):
    """枚举出所有标题完全等于 title 的可见窗口。"""
    u32 = ctypes.windll.user32
    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                                   wintypes.LPARAM), wintypes.LPARAM]
    found = []

    def cb(h, l):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, buf, 256)
        if buf.value == title:
            found.append(h)
        return True

    u32.EnumWindows(u32.EnumWindows.argtypes[0](cb), 0)
    return found


def _window_pid(hwnd):
    u32 = ctypes.windll.user32
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                             ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _process_name(pid):
    """进程的可执行文件名（不含路径）。查不到返回空串。"""
    try:
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                   wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ""


def find_widget_window(title):
    """找到挂件自己的窗口。

    不能只靠 FindWindowW(None, 标题) —— 标题是用户自己设的，很容易跟别的窗口撞。
    真事：有人的微信会话窗口和挂件设了同名的标题（微信也是 Qt 写的，连窗口类名都是
    Qt5xxxxQWindowIcon），单实例唤醒时会把**微信**弹到前台。
    所以这里按「进程是 python(w).exe」来筛。"""
    if sys.platform != "win32":
        return 0
    for h in _windows_with_title(title):
        name = _process_name(_window_pid(h))
        if name.startswith("python"):
            return h
    return 0


def _bring_existing_to_front():
    """找到旧实例的窗口，唤到前台（用 cfg 标题或默认值）。"""
    if sys.platform != "win32":
        return
    cfg = {}
    try:
        if os.path.exists(CONFIG_PATH):
            cfg = json.load(io.open(CONFIG_PATH, encoding="utf-8"))
    except Exception:
        pass
    title = cfg.get("title") or "A股盯盘"
    u32 = ctypes.windll.user32
    u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    u32.SetForegroundWindow.restype  = wintypes.BOOL
    u32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
    u32.ShowWindow.restype  = wintypes.BOOL

    hwnd = find_widget_window(title)
    if hwnd:
        u32.ShowWindow(hwnd, 9)               # SW_RESTORE
        u32.SetForegroundWindow(hwnd)


def main():
    install_crash_handler()     # 越早越好：连下面的 import 级 / 启动级异常都能兜住
    try:
        _run()
    except SystemExit:
        raise
    except Exception:
        _crash_alert(write_crash_log(_crash_text(*sys.exc_info())), sys.exc_info()[1])
        sys.exit(1)


def _run():
    if _singleton_check():
        _bring_existing_to_front()
        ctypes.windll.user32.MessageBoxW(
            None,
            "A 股盯盘挂件已经在运行了。\n\n"
            "新窗口已退出，托盘区的旧实例已恢复显示。",
            "已在运行",
            0x40 | 0x0,                         # MB_ICONINFORMATION | MB_OK
        )
        return

    cfg = load_config()
    if "codes" not in cfg or not cfg["codes"]:
        cfg["codes"] = list(DEFAULT_CONFIG["codes"])
    snapshot_config()          # 每次启动存一份，作为"上次正常退出时的样子"
    if not os.path.exists(CONFIG_PATH):
        save_config(cfg)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = Ticker(cfg)
    w.show()

    if "--shot" in sys.argv:
        i = sys.argv.index("--shot")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.join(APP_DIR, "shot.png")
        QTimer.singleShot(5000, lambda: (save_shot(w, out), app.quit()))  # noqa: F821

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
