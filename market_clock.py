# -*- coding: utf-8 -*-
"""交易时段判断 —— 一律按北京时间。

用户在海外、或者 Windows 时区被改过之后，本地 datetime.now() 会把实盘判成休市、
把休市判成实盘，14:57 的彩蛋也会错时。所以 A 股相关的时间一律走 market_now()。
"""
from datetime import datetime, timedelta, timezone

MARKET_TZ = timezone(timedelta(hours=8))    # 中国固定 UTC+8，不需要 tzdata

PREOPEN = "preopen"              # 09:15-09:25 集合竞价
PREOPEN_GAP = "preopen_gap"      # 09:25-09:30 竞价已结束，等开盘
MORNING = "morning"              # 09:30-11:30
LUNCH = "lunch"                  # 11:30-13:00
AFTERNOON = "afternoon"          # 13:00-14:57
CLOSING_CALL = "closing_call"    # 14:57-15:00 收盘集合竞价（收盘彩蛋在这一段）
CLOSED = "closed"                # 休市：收盘后 / 盘前太早 / 周末 / 法定休市日

PHASE_TEXT = {PREOPEN: "盘前", PREOPEN_GAP: "盘前", MORNING: "交易中",
              LUNCH: "午休", AFTERNOON: "交易中", CLOSING_CALL: "收盘竞价",
              CLOSED: "休市"}
PHASE_DOT = {PREOPEN: "#fbbf24", PREOPEN_GAP: "#fbbf24", MORNING: "#4ade80",
             LUNCH: "#fbbf24", AFTERNOON: "#4ade80", CLOSING_CALL: "#4ade80",
             CLOSED: "#6b7280"}

# 有连续撮合、数据在动，值得快刷
TRADING_PHASES = (PREOPEN, MORNING, AFTERNOON, CLOSING_CALL)
# 真正处于交易时段（用来判断"成交量 0 是不是停牌"、异动提醒要不要发）
OPEN_PHASES = (MORNING, AFTERNOON, CLOSING_CALL)

_M_CALL_START = 9 * 60 + 15     # 集合竞价开始，接口开始有数
_M_CALL_END = 9 * 60 + 25       # 集合竞价结束
_M_OPEN = 9 * 60 + 30           # 开盘
_M_LUNCH = 11 * 60 + 30         # 午休开始
_M_AFTERNOON = 13 * 60          # 下午开盘
_M_CLOSING_CALL = 14 * 60 + 57  # 收盘集合竞价开始
_M_CLOSE = 15 * 60              # 收盘

# ---- 法定休市日（只列"工作日也休市"的那些，周末靠 weekday 排除）----
# 每年交易所公布后手工维护一次；没维护到的年份会退回"只按 weekday 判断"，
# 可能把节假日误判成开市 —— 宁可多刷新，也不会少刷新。
# ★ 已知时间炸弹：现在只有 2026。到 2027 元旦之后，如果还没补上那一年的表，
# 法定休市的工作日会被当作交易日 —— 快刷、stale 行情可能被当实时、提醒风险更大。
# 交易所一般在 11~12 月公布次年安排；公布后立刻补进来。
# tests/test_clock.py 会在每年 12 月起把"明年还没维护"变成红项，不用谁记着。
MARKET_CLOSED_BY_YEAR = {
    # 2026 年按上交所《关于 2026 年部分节假日休市安排的通知》
    # （上证公告〔2025〕45 号，2025-12-22）逐日换算。
    # 公告给的是"假期起止"，这里只记**工作日**的休市日，周末靠 weekday 排除。
    2026: {
        "2026-01-01", "2026-01-02",                     # 元旦（假期 1/1 四 ~ 1/3 六）
        "2026-02-16", "2026-02-17", "2026-02-18",       # 春节（假期 2/15 日 ~ 2/23 一）
        "2026-02-19", "2026-02-20", "2026-02-23",
        "2026-04-06",                                   # 清明（假期 4/4 六 ~ 4/6 一）
        "2026-05-01", "2026-05-04", "2026-05-05",       # 劳动节（假期 5/1 五 ~ 5/5 二）
        "2026-06-19",                                   # 端午（假期 6/19 五 ~ 6/21 日）
        "2026-09-25",                                   # 中秋（假期 9/25 五 ~ 9/27 日）
        "2026-10-01", "2026-10-02", "2026-10-05",       # 国庆（假期 10/1 四 ~ 10/7 三）
        "2026-10-06", "2026-10-07",                     # （10/3、10/4 是周末）
    },
}


def market_now():
    """当前北京时间（带时区）"""
    return datetime.now(MARKET_TZ)


def _minutes(t):
    return t.hour * 60 + t.minute


def is_market_day(d):
    """这天开市吗：不是周末、且不在法定休市表里"""
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in MARKET_CLOSED_BY_YEAR.get(d.year, set())


def calendar_is_maintained(year):
    """这一年的休市日表维护过了没有。

    没维护到的年份会静默退化成"只按星期几判断" —— 于是国庆那周会照常每 3 秒
    刷一次行情（接口当然没数据）。功能上不崩，但白耗资源，而且**没有任何提示**
    告诉你"表过期了"。这个函数让"表有没有覆盖"变成一个能被检查的事实：
    启动自检和 CI 都可以拿它问一句"明年还有没有"。
    """
    return year in MARKET_CLOSED_BY_YEAR


def calendar_horizon(now=None):
    """这份表覆盖到哪一年。没维护任何一年返回 None。"""
    years = sorted(MARKET_CLOSED_BY_YEAR)
    return years[-1] if years else None


def market_phase(now=None):
    """返回当前时段（见上面的常量）。now 不带时区时按北京时间算。"""
    now = now or market_now()
    if now.tzinfo is not None:
        now = now.astimezone(MARKET_TZ)
    if not is_market_day(now.date()):
        return CLOSED
    m = _minutes(now)
    if m < _M_CALL_START:
        return CLOSED            # 太早，接口还是昨天的数
    if m < _M_CALL_END:
        return PREOPEN
    if m < _M_OPEN:
        return PREOPEN_GAP
    if m < _M_LUNCH:
        return MORNING
    if m < _M_AFTERNOON:
        return LUNCH
    if m < _M_CLOSING_CALL:
        return AFTERNOON
    if m < _M_CLOSE:
        return CLOSING_CALL
    return CLOSED


def is_trading_now(now=None):
    """真的在交易时段里（午休和收盘都不算）"""
    return market_phase(now) in OPEN_PHASES


def is_active(now=None):
    """数据在动、值得频繁刷新：集合竞价 + 上午 + 下午 + 收盘竞价"""
    return market_phase(now) in TRADING_PHASES


def has_session_started(now=None):
    """最近这次交易开始过了没有（过了 9:30）。

    判断"成交量 0 是不是停牌"要用：盘前所有股票成交量都是 0，不能一律算停牌。
    """
    now = now or market_now()
    if now.tzinfo is not None:
        now = now.astimezone(MARKET_TZ)
    if not is_market_day(now.date()):
        return True              # 休市日：最近一次交易日早已收盘，成交量该有就有
    return _minutes(now) >= _M_OPEN


def parse_quote_stamp(stamp):
    """行情时间戳（yyyymmddHHMMSS）-> 带时区的北京时间 datetime。

    认不出来返回 None。

    ★ 只验"前 8 位是不是数字"是不够的：`20269999` 全是数字，但它不是日期。
    以前它会变成 "99-99"，而且因为字符串比 `20260920` 大，还能把真正的
    日期压掉。必须按真实日历解析。
    """
    s = (stamp or "").strip()
    if len(s) < 8 or not s[:8].isdigit():
        return None
    try:
        dt = datetime.strptime(s[:8], "%Y%m%d")
    except ValueError:
        return None                     # 20269999 / 99999999 之类
    if len(s) >= 14 and s[8:14].isdigit():
        try:
            dt = dt.replace(hour=int(s[8:10]), minute=int(s[10:12]),
                            second=int(s[12:14]))
        except ValueError:
            return None
    return dt.replace(tzinfo=MARKET_TZ)


def stamp_mmdd(stamp):
    """行情时间戳（yyyymmddHHMMSS）-> "MM-dd"；认不出来返回空串。"""
    dt = parse_quote_stamp(stamp)
    return "" if dt is None else dt.strftime("%m-%d")


def stamp_age_seconds(stamp, now=None):
    """行情时间戳距今多少秒。解析不出来返回 None。"""
    dt = parse_quote_stamp(stamp)
    if dt is None:
        return None
    n = now or market_now()
    if n.tzinfo is not None:
        n = n.astimezone(MARKET_TZ)
    return (n - dt).total_seconds()


def last_session_mmdd(now=None):
    """推算最近一个交易日的 MM-dd（跳周末 + 法定休市日）"""
    n = now or market_now()
    if n.tzinfo is not None:
        n = n.astimezone(MARKET_TZ)
    d = n.date()
    if _minutes(n) < _M_CALL_START:
        d -= timedelta(days=1)   # 今天还没开盘，手里的数是上一交易日的
    while not is_market_day(d):
        d -= timedelta(days=1)
    return d.strftime("%m-%d")


def last_quote_mmdd(stamps, now=None):
    """从一批行情时间戳里挑出最新的日期，返回 "MM-dd"。

    接口给的时间戳最可靠（节假日、临时休市都能正确反映）；
    一个都解析不出来时才退回按日历推算。
    """
    # 比的是完整的 yyyymmdd（跨年时 "12-31" 和 "01-02" 光看月日会排错）。
    # 这里用 parse_quote_stamp 过滤：光看 isdigit 会把 20269999 当成最新日期。
    best = None
    for s in stamps or ():
        dt = parse_quote_stamp(s)
        if dt is None:
            continue
        d = dt.strftime("%Y%m%d")
        if best is None or d > best:
            best = d
    return stamp_mmdd(best) if best else last_session_mmdd(now)
