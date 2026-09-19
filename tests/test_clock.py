# -*- coding: utf-8 -*-
"""交易时段判断：7 个阶段 + 休市日 + "截至 MM-dd"。

纯逻辑，不联网、不需要显示器。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import market_clock as MC  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


def at(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


print("== 七个时段（2026-09-18 周五）==")
for s, want in (
    ("2026-09-18 08:00", MC.CLOSED),           # 太早，接口还是昨天的数
    ("2026-09-18 09:14", MC.CLOSED),
    ("2026-09-18 09:15", MC.PREOPEN),          # 集合竞价开始
    ("2026-09-18 09:24", MC.PREOPEN),
    ("2026-09-18 09:25", MC.PREOPEN_GAP),      # 竞价结束，等开盘
    ("2026-09-18 09:29", MC.PREOPEN_GAP),
    ("2026-09-18 09:30", MC.MORNING),
    ("2026-09-18 11:29", MC.MORNING),
    ("2026-09-18 11:30", MC.LUNCH),
    ("2026-09-18 12:59", MC.LUNCH),
    ("2026-09-18 13:00", MC.AFTERNOON),
    ("2026-09-18 14:56", MC.AFTERNOON),
    ("2026-09-18 14:57", MC.CLOSING_CALL),     # 收盘集合竞价（彩蛋窗口）
    ("2026-09-18 14:59", MC.CLOSING_CALL),
    ("2026-09-18 15:00", MC.CLOSED),
    ("2026-09-18 23:00", MC.CLOSED),
    ("2026-09-19 10:00", MC.CLOSED),           # 周六
    ("2026-09-20 10:00", MC.CLOSED),           # 周日
):
    got = MC.market_phase(at(s))
    chk("%s -> %s" % (s, want), got == want, got)

print("== 是否活跃（决定刷新频率）==")
# 活跃 = 盘前 + 上午 + 下午 + 收盘竞价；午休和盘后不活跃（省请求）
chk("上午算活跃", MC.is_active(at("2026-09-18 10:00")))
chk("盘前算活跃", MC.is_active(at("2026-09-18 09:20")))
chk("收盘竞价算活跃", MC.is_active(at("2026-09-18 14:58")))
chk("午休不活跃", not MC.is_active(at("2026-09-18 12:00")))
chk("收盘不活跃", not MC.is_active(at("2026-09-18 15:30")))

print("== 是否真在交易（决定异动提醒）==")
chk("盘前不算交易中", not MC.is_trading_now(at("2026-09-18 09:20")))
chk("上午算交易中", MC.is_trading_now(at("2026-09-18 10:00")))
chk("下午算交易中", MC.is_trading_now(at("2026-09-18 14:00")))
chk("收盘竞价算交易中", MC.is_trading_now(at("2026-09-18 14:58")))
chk("午休不算交易中", not MC.is_trading_now(at("2026-09-18 12:00")))
chk("收盘不算交易中", not MC.is_trading_now(at("2026-09-18 15:30")))
chk("周末不算交易中", not MC.is_trading_now(at("2026-09-19 10:00")))

print("== 今天开盘了没（停牌判定要用）==")
chk("9:00 还没开盘", not MC.has_session_started(at("2026-09-18 09:00")))
chk("10:00 已开盘", MC.has_session_started(at("2026-09-18 10:00")))
chk("周末按已开盘算", MC.has_session_started(at("2026-09-19 10:00")))

print("== 2026 官方休市日 ==")
# 独立 fixture：照抄上交所《关于 2026 年部分节假日休市安排的通知》
# （上证公告〔2025〕45 号）里的假期起止，再自己换算成工作日休市日。
# 和 market_clock 里那份表**分开维护** —— 两边不一致就是有一边错了。
OFFICIAL_HOLIDAYS_2026 = {
    # 假期起止（含周末）-> 里面属于工作日的那些天
    "元旦":   (("2026-01-01", "2026-01-03"),
               ("2026-01-01", "2026-01-02")),
    "春节":   (("2026-02-15", "2026-02-23"),
               ("2026-02-16", "2026-02-17", "2026-02-18",
                "2026-02-19", "2026-02-20", "2026-02-23")),
    "清明":   (("2026-04-04", "2026-04-06"),
               ("2026-04-06",)),
    "劳动节": (("2026-05-01", "2026-05-05"),
               ("2026-05-01", "2026-05-04", "2026-05-05")),
    "端午":   (("2026-06-19", "2026-06-21"),
               ("2026-06-19",)),
    "中秋":   (("2026-09-25", "2026-09-27"),
               ("2026-09-25",)),
    "国庆":   (("2026-10-01", "2026-10-07"),
               ("2026-10-01", "2026-10-02", "2026-10-05",
                "2026-10-06", "2026-10-07")),
}

official_closed = set()
for name, (span, workdays) in OFFICIAL_HOLIDAYS_2026.items():
    for day in workdays:
        official_closed.add(day)

for name, (span, workdays) in OFFICIAL_HOLIDAYS_2026.items():
    for day in workdays:
        d = datetime.strptime(day, "%Y-%m-%d").date()
        chk("%s %s 休市" % (name, day), not MC.is_market_day(d))
        # 假期里的每一天（含周末）都不能被判成开市
    lo = datetime.strptime(span[0], "%Y-%m-%d").date()
    hi = datetime.strptime(span[1], "%Y-%m-%d").date()
    cur = lo
    while cur <= hi:
        chk("%s 假期内 %s 不开市" % (name, cur.isoformat()),
            not MC.is_market_day(cur))
        cur += timedelta(days=1)

# 反向：2026 全年每个工作日，只要被判成休市，就必须在官方清单里
# —— 防止表里多塞了日期（漏了上面的用例会抓到，多了只有这条能抓到）
extra = []
d = datetime(2026, 1, 1).date()
while d.year == 2026:
    if d.weekday() < 5 and not MC.is_market_day(d):
        if d.isoformat() not in official_closed:
            extra.append(d.isoformat())
    d += timedelta(days=1)
chk("没有官方清单之外的休市日（不多塞）", not extra, "、".join(extra[:8]))
chk("全年工作日休市日共 %d 天" % len(official_closed),
    len(official_closed) == 19, str(len(official_closed)))
# 节假日里的任何一个时刻都不能被判成交易中
chk("国庆当天 10:00 不算交易中",
    not MC.is_trading_now(at("2026-10-01 10:00")))
chk("国庆当天 10:00 不活跃", not MC.is_active(at("2026-10-01 10:00")))
chk("中秋假期前一日 09-24 仍在交易",
    MC.is_trading_now(at("2026-09-24 10:00")))
chk("普通工作日是交易日", MC.is_market_day(datetime(2026, 9, 18).date()))
chk("周六不是交易日", not MC.is_market_day(datetime(2026, 9, 19).date()))

print("== 北京时间 ==")
# 本地时区被改成什么都不能影响判断：UTC-5 的 21:00 = 北京次日 10:00
remote = datetime(2026, 9, 17, 21, 0, tzinfo=timezone(timedelta(hours=-5)))
chk("带时区的时刻换算成北京时间",
    MC.market_phase(remote) == MC.MORNING, MC.market_phase(remote))
chk("MARKET_TZ 是 UTC+8",
    MC.MARKET_TZ.utcoffset(None) == timedelta(hours=8))
now = MC.market_now()
chk("market_now 带时区", now.tzinfo is not None)
chk("market_now 是北京时间",
    abs((now.utcoffset().total_seconds() or 0) - 8 * 3600) < 1)

print("== 时间戳 -> MM-dd ==")
chk("标准时间戳", MC.stamp_mmdd("20260918161436") == "09-18", MC.stamp_mmdd("20260918161436"))
chk("空串返回空", MC.stamp_mmdd("") == "")
chk("太短返回空", MC.stamp_mmdd("2026") == "")
chk("非数字返回空", MC.stamp_mmdd("abcdefgh1234") == "")

print("== 截至日期 ==")
chk("一批里挑最新的",
    MC.last_quote_mmdd(["20260916150000", "20260918161436", "20260917150000"]) == "09-18")
chk("跨年比较正确", MC.last_quote_mmdd(["20251231150000", "20260102150000"]) == "01-02")
chk("周五收盘后 = 当天", MC.last_quote_mmdd([], at("2026-09-18 20:00")) == "09-18")
chk("周六退到周五", MC.last_quote_mmdd([], at("2026-09-19 10:00")) == "09-18")
chk("周一早上退到周五", MC.last_quote_mmdd([], at("2026-09-21 08:00")) == "09-18")
chk("周一开盘后 = 当天", MC.last_quote_mmdd([], at("2026-09-21 10:00")) == "09-21")
# 国庆 7 天假：10-08 开盘前要退到 09-30，不能停在 10-07
chk("长假后退回节前最后一个交易日",
    MC.last_quote_mmdd([], at("2026-10-08 08:00")) == "09-30",
    MC.last_quote_mmdd([], at("2026-10-08 08:00")))

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
