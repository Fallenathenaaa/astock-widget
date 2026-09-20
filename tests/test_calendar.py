# -*- coding: utf-8 -*-
"""节日系统验证：触发日算法 / 单激活 / 表完整性。不碰真实配置。"""
import os
import sys
import tempfile
import io
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
import safety_guard  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


tmp = tempfile.mkdtemp(prefix="astock-fest-")
# 注意：测试不能依赖开发者机器上那份真实的 stocks.json —— 干净 clone 里没有它，
# 测试会假失败。这里只把配置路径指到临时目录，真实配置压根不读。
real = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "stocks.json")
REAL = None
if os.path.exists(real):
    with io.open(real, encoding="utf-8") as f:
        REAL = f.read()          # 只在它存在时留个指纹，最后验它没被改动
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")


def key(k):
    return W.FEST_BY_KEY[k]


def trig(k, year):
    return [str(d) for d in W.festival_trigger_days(key(k), year)]


print("== 1. 表完整性 ==")
chk("节日数量 = 10", len(W.FESTIVALS) == 10, str(len(W.FESTIVALS)))
chk("优先级递减排列",
    all(W.FESTIVALS[i]["pri"] >= W.FESTIVALS[i + 1]["pri"]
        for i in range(len(W.FESTIVALS) - 1)))
chk("每个画法都实现了", all(f["fall"] in W.FALL_DRAW for f in W.FESTIVALS),
    str([f["fall"] for f in W.FESTIVALS if f["fall"] not in W.FALL_DRAW]))
chk("key 不重复", len({f["key"] for f in W.FESTIVALS}) == len(W.FESTIVALS))
# 反过来：强制开关是运行时状态，**不能**进配置。存过一次就可能在崩溃后残留，
# 下次启动还挂着强制特效，和"严格按日期触发"对不上。
chk("强制开关不进配置",
    not any(f["key"] + "_test" in W.DEFAULT_CONFIG for f in W.FESTIVALS),
    str([f["key"] for f in W.FESTIVALS if f["key"] + "_test" in W.DEFAULT_CONFIG]))

print("== 2. 放假节日 → 假期前最后一个交易日 ==")
# 用户给的例子：2026 中秋 9/25 是周五，不交易 → 9/24 周四触发
chk("2026 中秋名义 09-25", str(W.festival_nominal_days(key("midautumn"), 2026)[0])
    == "2026-09-25")
chk("2026 中秋触发 09-24", trig("midautumn", 2026) == ["2026-09-24"], trig("midautumn", 2026))
chk("2026 国庆触发 09-30", trig("national", 2026) == ["2026-09-30"], trig("national", 2026))
chk("2027 国庆触发 09-30", trig("national", 2027) == ["2027-09-30"], trig("national", 2027))
# 2026 春节：除夕 2/16(周一) → 往前最近交易日 2/13(周五)
chk("2026 春节触发 02-13", trig("spring", 2026) == ["2026-02-13"], trig("spring", 2026))
chk("2027 春节触发 02-04", trig("spring", 2027) == ["2027-02-04"], trig("spring", 2027))
chk("触发日一定是工作日",
    all(d.weekday() < 5 for k in ("spring", "national", "midautumn")
        for y in range(2025, 2032) for d in W.festival_trigger_days(key(k), y)))

print("== 3. 不放假的节日：当天触发 ==")
chk("2026 元宵 03-03", trig("lantern", 2026) == ["2026-03-03"], trig("lantern", 2026))
chk("2026 小年 两天", trig("xiaonian", 2026) == ["2026-02-10", "2026-02-11"],
    trig("xiaonian", 2026))
# 2027 小年廿三周六 / 廿四周日 → 都不开盘，一起退回周五，合并成一天
chk("2027 小年周末 → 退回周五", trig("xiaonian", 2027) == ["2027-01-29"],
    trig("xiaonian", 2027))
chk("2027 元宵 02-20 周六 → 退回 02-19 周五",
    trig("lantern", 2027) == ["2027-02-19"], trig("lantern", 2027))
chk("2026 感恩节 = 11 月第 4 个周四", trig("thanks", 2026) == ["2026-11-26"],
    trig("thanks", 2026))
chk("感恩节一直是周四",
    all(d.weekday() == 3 for y in range(2025, 2032)
        for d in W.festival_trigger_days(key("thanks"), y)))

print("== 4. 西方节日 / 12-31 逢周末不启动 ==")
chk("2026 万圣节 10-31 是周六 → 不触发", trig("halloween", 2026) == [], trig("halloween", 2026))
chk("2027 万圣节 周日 → 不触发", trig("halloween", 2027) == [], trig("halloween", 2027))
chk("2028 万圣节 周二 → 触发", trig("halloween", 2028) == ["2028-10-31"],
    trig("halloween", 2028))
chk("2026 情人节 周六 → 不触发", trig("valentine", 2026) == [], trig("valentine", 2026))
chk("2026 圣诞 周五 → 触发", trig("christmas", 2026) == ["2026-12-25"],
    trig("christmas", 2026))
chk("2027 圣诞 周六 → 不触发", trig("christmas", 2027) == [], trig("christmas", 2027))
chk("2026-12-31 周四 → 红包雨", trig("yearend", 2026) == ["2026-12-31"], trig("yearend", 2026))
chk("跨年红包雨必须是交易日",
    all(d.weekday() < 5 for y in range(2025, 2032)
        for d in W.festival_trigger_days(key("yearend"), y)))
chk("圣诞/万圣/情人节绝不在周末",
    all(d.weekday() < 5 for k in ("christmas", "halloween", "valentine", "thanks")
        for y in range(2025, 2032) for d in W.festival_trigger_days(key(k), y)))
# 挂件是盯盘用的，周末没行情 —— 所有节日都不该在周六周日放
chk("任何节日都不在周末触发（2025-2032，全部 10 个节日）",
    all(d.weekday() < 5 for f in W.FESTIVALS
        for y in range(2025, 2033) for d in W.festival_trigger_days(f, y)))

print("== 5. 同时只激活一个 ==")
# forced 是运行时强制开启的那一个 key（不落盘），只能有一个
f = W.active_festival(date(2026, 6, 1), forced="spring")
chk("强制春节 → 春节", f is not None and f["key"] == "spring", f["key"] if f else None)
chk("强制圣诞 → 圣诞（一次只认一个）",
    W.active_festival(date(2026, 6, 1), forced="christmas")["key"] == "christmas")
chk("不认识的 key 不生效（退回按日期）",
    W.active_festival(date(2026, 6, 1), forced="not_a_festival") is None)
chk("非节日 + 不强制 → None", W.active_festival(date(2026, 6, 1)) is None)
chk("按日期自动命中（2026-09-24 中秋）",
    W.active_festival(date(2026, 9, 24))["key"] == "midautumn",
    str(W.active_festival(date(2026, 9, 24))))
chk("中秋当天(9-25)不再触发", W.active_festival(date(2026, 9, 25)) is None)
chk("强制优先于日期（中秋当天强制情人节）",
    W.active_festival(date(2026, 9, 24), forced="valentine")["key"] == "valentine")

print("== 6. 缓存一致 ==")
a = W.active_festival(date(2026, 9, 24))
b = W.active_festival(date(2026, 9, 24))
chk("同样入参结果一致", (a["key"] if a else None) == (b["key"] if b else None))
chk("缓存命中后仍正确", W.active_festival(date(2026, 10, 1)) is None)
chk("强制与否分开缓存",
    W.active_festival(date(2026, 9, 24), forced="christmas")["key"] == "christmas"
    and W.active_festival(date(2026, 9, 24))["key"] == "midautumn")

print("== 7. next_festival 提示 ==")
nxt = W.next_festival(date(2026, 1, 1))
chk("返回未来日期", nxt is not None and nxt[1] >= date(2026, 1, 1), str(nxt))
chk("2026-01-01 之后最近的是小年/春节",
    nxt[0]["key"] in ("xiaonian", "spring"), nxt[0]["key"])
nxt2 = W.next_festival(date(2026, 9, 20))
chk("2026-09-20 之后最近是中秋", nxt2[0]["key"] == "midautumn" and str(nxt2[1]) == "2026-09-24",
    str(nxt2))

print("== 8. 画法函数签名可用 ==")
try:
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    pm = QPixmap(120, 80)
    pm.fill(W.QColor(20, 20, 24))
    p = QPainter(pm)
    for name, fn in W.FALL_DRAW.items():
        W.draw_falling(p, 120, 80, fn)
    p.end()
    chk("9 种飘落物都能画出来", True)
except Exception as e:
    chk("9 种飘落物都能画出来", False, repr(e))

print("== 9. 真实配置未动 ==")
safety_guard.check_after(chk)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
