# -*- coding: utf-8 -*-
"""异步状态：行情 generation / 搜索 seq / 空自选 / 提醒去重。

行情和搜索都是"发出请求 → 过一会儿才有结果"的。这中间用户可以改自选股、
可以改关键字、可以按 Esc。旧结果晚一步回来时如果不认得出来，界面就会显示
错的股票或错的候选。

不联网：线程不启，信号直接从测试里 emit。
"""
import io
import os
import sys
import copy
import json
import tempfile
import threading
import time
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
import providers as P  # noqa: E402
import market_clock  # noqa: E402
from PySide6.QtCore import QThread  # noqa: E402
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


tmp = tempfile.mkdtemp(prefix="astock-async-")
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")
# 这个文件会跑**真的** worker 线程（P0 那几条），worker 失败时会写运行日志 ——
# 不把 LOG_DIR 也指到临时目录，就会在仓库里留下真实的 logs/
W.LOG_DIR = os.path.join(tmp, "logs")

app = QApplication([])
# 别让线程真跑起来：退出时 Qt 会 "QThread destroyed while running" 直接 abort
# 屏蔽只是默认；P0 那几条要真跑线程，所以把真正的 start 留一份
_real_fetcher_start = QThread.start
_real_sparker_start = QThread.start
W.Fetcher.start = lambda self: None
W.SparkFetcher.start = lambda self: None
W.Searcher.start = lambda self: None

cfg = copy.deepcopy(W.DEFAULT_CONFIG)
cfg["codes"] = ["sh600519", "sz000001"]
w = W.Ticker(cfg)


def row(full, code, name, pct=0.0):
    # 时间戳用"现在"：提醒现在要查新鲜度，写死日期会在第二天集体失效
    return {"full": full, "code": code, "name": name, "price": 10.0,
            "prev": 10.0, "change": 0.0, "pct": pct, "decimals": 2,
            "time": market_clock.market_now().strftime("%Y%m%d%H%M%S"),
            "status": "normal"}


def emit(rows, idx=None, gen=None):
    """模拟行情线程把一批数据送回来。"""
    w.fetcher.data_ready.emit({
        "generation": w.watchlist_generation if gen is None else gen,
        "rows": rows,
        "idx": idx or [],
    })


# ------------------------------------------------------------ generation
print("== 换了自选股后，旧行情要被丢掉 ==")
gen0 = w.watchlist_generation
chk("起始 generation 记下来了", gen0 == w.fetcher._generation, (gen0, w.fetcher._generation))

w.apply_watchlist(["sz300750"])
gen1 = w.watchlist_generation
chk("换自选 → generation +1", gen1 == gen0 + 1, (gen0, gen1))

# 老一批的结果现在才回来（请求是在换之前发出去的）
w.rows = []
emit([row("sh600519", "600519", "贵州茅台")], gen=gen0)
chk("旧 generation 的结果被丢弃", w.rows == [], w.rows)

emit([row("sz300750", "300750", "宁德时代")], gen=gen1)
chk("当前 generation 的结果收下", len(w.rows) == 1 and w.rows[0]["full"] == "sz300750",
    w.rows)

print("== 删掉的股票不能还挂在界面上 ==")
emit([row("sh600519", "600519", "贵州茅台"), row("sz300750", "300750", "宁德时代")],
     gen=gen1)
w.apply_watchlist(["sz300750"])
chk("界面上立刻只剩留下的那只",
    [r["full"] for r in w.rows] == ["sz300750"], [r["full"] for r in w.rows])

print("== 一次清空也是合法状态 ==")
w.apply_watchlist([])
chk("配置里是空列表", w.cfg["codes"] == [], w.cfg["codes"])
chk("界面行清空", w.rows == [], w.rows)
with io.open(W.CONFIG_PATH, encoding="utf-8") as f:
    chk("空列表照样落盘", json.load(f).get("codes") == [])
# 空自选时指数必须照样刷新 —— 这条在 Fetcher._loop 里是把指数单独请求的
snap_idx = [row("sh000001", "000001", "上证指数")]
emit([], idx=snap_idx)
chk("自选为空时指数仍然刷新", len(w.indices) == 1, w.indices)

print("== 去重与截断 ==")
w.apply_watchlist(["sh600519", "sh600519", "sz000001"])
chk("重复只留一次", w.cfg["codes"] == ["sh600519", "sz000001"], w.cfg["codes"])
w.apply_watchlist(["1", "2", "3", "4", "5", "6", "7"])
chk("最多 5 只", len(w.cfg["codes"]) == 5, w.cfg["codes"])

print("== 添加 / 删除都走同一个入口 ==")
w.apply_watchlist(["sh600519"])
w.add_stock({"full": "sz000001", "code": "000001", "name": "平安银行"})
chk("添加生效", w.cfg["codes"] == ["sh600519", "sz000001"], w.cfg["codes"])
chk("加了之后 generation 又变了", w.watchlist_generation != gen1)
w.add_stock({"full": "sz000001", "code": "000001", "name": "平安银行"})
chk("重复添加不生效", w.cfg["codes"] == ["sh600519", "sz000001"], w.cfg["codes"])
w.apply_watchlist(["sh600519", "sz000001", "sz300750", "sh601318", "sh600036"])
chk("先填满 5 只", len(w.cfg["codes"]) == 5)
# 满 5 只之后再加：以前会静默挤掉最后一只（用户加完第六只，第五只无声无息
# 没了，还以为是自己记错了）。现在明确拒绝 —— 要换哪一只由用户自己决定。
w.add_stock({"full": "sh688981", "code": "688981", "name": "中芯国际"})
chk("满了就拒绝，最后一只没被挤掉", w.cfg["codes"][-1] == "sh600036",
    w.cfg["codes"])
chk("被拒的那只没进来", "sh688981" not in w.cfg["codes"], w.cfg["codes"])
chk("满了之后仍是 5 只", len(w.cfg["codes"]) == 5, w.cfg["codes"])

# ------------------------------------------------------------ 搜索 seq
print("== 搜索：旧关键字的结果不能盖住新的 ==")
w.search_edit.setText("mao")
w.do_search()
seq_mao = w.search_seq
chk("发了请求，编号 +1", seq_mao >= 1)
# 用户又改了关键字
w.search_edit.setText("pingan")
w.do_search()
seq_pingan = w.search_seq
chk("改关键字 → 新编号", seq_pingan == seq_mao + 1, (seq_mao, seq_pingan))

# 先发的 "mao" 现在才回来
w.on_search_result("mao", seq_mao, [{"full": "sh600519", "code": "600519",
                                     "name": "贵州茅台", "type": ""}])
chk("旧 query 的结果被丢弃", w.candidates == [], w.candidates)

# 当前关键字的结果才收
w.on_search_result("pingan", seq_pingan,
                   [{"full": "sz000001", "code": "000001", "name": "平安银行", "type": ""}])
chk("新 query 的结果收下", len(w.candidates) == 1 and w.candidates[0]["full"] == "sz000001",
    w.candidates)
chk("候选对应的关键字记下来了", w.candidate_query == "pingan", w.candidate_query)

print("== 搜索：输入已经变了也不收 ==")
w.candidates = []
w.candidate_query = ""
w.search_edit.setText("ningde")      # 编号没变，但输入框已经不是那个词了
w.on_search_result("pingan", seq_pingan,
                   [{"full": "sz000001", "code": "000001", "name": "平安银行", "type": ""}])
chk("关键字对不上就不收", w.candidates == [], w.candidates)

print("== Esc 之后，在途的旧结果不能再弹回来 ==")
w.search_edit.setText("maotai")
w.do_search()
seq_before_esc = w.search_seq
w._close_search()
chk("Esc 让编号作废", w.search_seq == seq_before_esc + 1)
chk("Esc 清空了输入框", w.search_edit.text() == "")
w.on_search_result("maotai", seq_before_esc,
                   [{"full": "sh600519", "code": "600519", "name": "贵州茅台", "type": ""}])
chk("Esc 后的旧结果不显示", w.candidates == [], w.candidates)

print("== 回车只加当前关键字对应的候选 ==")
w.apply_watchlist(["sz300750"])       # 先清干净，免得前面的用例留了同一只票
w.search_edit.setText("maotai")
w.do_search()
w.on_search_result("maotai", w.search_seq,
                   [{"full": "sh600519", "code": "600519", "name": "贵州茅台", "type": ""}])
w.search_edit.setText("pingan")     # 结果还没回来，用户已经改成别的词了
w.add_first_candidate()
chk("关键字对不上时不乱加", "sh600519" not in w.cfg["codes"], w.cfg["codes"])
w.search_edit.setText("maotai")
w.add_first_candidate()
chk("对得上才加进去", "sh600519" in w.cfg["codes"], w.cfg["codes"])

print("== 同一个关键字不重复发请求 ==")
w._close_search()
w.search_edit.setText("maotai")
w.do_search()
s1 = w.search_seq
w.do_search()
chk("重复调用不加编号", w.search_seq == s1, (s1, w.search_seq))

# ------------------------------------------------------------ 提醒去重
print("== 异动提醒：不在交易时段不提醒 ==")
w.apply_watchlist(["sh600519"])
w.cfg["alert_pct"] = 3.0
w._alert_armed.clear()
w.flash.clear()
_real_phase = market_clock.market_phase
try:
    market_clock.market_phase = lambda now=None: market_clock.CLOSED
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=9.0)])
    chk("休市时不提醒", w.flash == {}, w.flash)

    market_clock.market_phase = lambda now=None: market_clock.MORNING
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=9.0)])
    chk("交易中突破阈值 → 提醒一次", "sh600519" in w.flash, w.flash)

    w.flash.clear()
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=9.5)])
    chk("一直超阈值 → 不重复提醒", w.flash == {}, w.flash)

    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=1.0)])
    chk("回到安全区 → 重新武装", w._alert_armed.get("sh600519") is True)
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=4.0)])
    chk("再次突破 → 又能提醒", "sh600519" in w.flash, w.flash)

    w.flash.clear()
    w._alert_armed.clear()             # 重新武装后再来一次
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=-9.0)])
    chk("跌超阈值同样提醒", "sh600519" in w.flash, w.flash)

    w.flash.clear()
    w._alert_armed.clear()
    w.cfg["alert_pct"] = 0
    w.check_alert([row("sh600519", "600519", "贵州茅台", pct=9.0)])
    chk("阈值关掉（0）→ 不提醒", w.flash == {}, w.flash)
finally:
    market_clock.market_phase = _real_phase
    w.cfg["alert_pct"] = 3.0


print("== 异动提醒：旧数据不许当实时提醒 ==")
# 光看"是不是交易时段"不够 —— provider 可能返回一个格式正确、
# 但时间是昨天收盘的 row，那时弹"实时异动 +5%"是假的。
_real_phase2 = market_clock.market_phase
try:
    market_clock.market_phase = lambda now=None: market_clock.MORNING
    w.cfg["alert_pct"] = 3.0

    def alert_with(time_str):
        w._alert_armed.clear()
        w.flash.clear()
        w.check_alert([row("sh600519", "600519", "贵州茅台", pct=5.0)
                       | {"time": time_str}])
        return bool(w.flash)

    today = market_clock.market_now()
    chk("今天且新鲜 → 提醒", alert_with(today.strftime("%Y%m%d%H%M%S")))
    chk("昨天 → 不提醒",
        not alert_with((today - timedelta(days=1)).strftime("%Y%m%d150000")))
    chk("今天但太旧（3 小时前）→ 不提醒",
        not alert_with((today.replace(hour=0, minute=0, second=0)
                        ).strftime("%Y%m%d%H%M%S")))
    chk("时间戳是 20269999（不是日期）→ 不提醒", not alert_with("20269999"))
    chk("时间戳是 99999999 → 不提醒", not alert_with("99999999"))
    chk("时间戳为空 → 不提醒", not alert_with(""))
    chk("未来的时间戳 → 不提醒",
        not alert_with((today + timedelta(days=1)).strftime("%Y%m%d%H%M%S")))
finally:
    market_clock.market_phase = _real_phase2
    w._alert_armed.clear()
    w.flash.clear()

print("== 收盘彩蛋：整段窗口内只触发一次 ==")
w.cfg["effect_pct"] = 3.0
w.effects.clear()
w._effect_date = ""
_real = market_clock.market_phase
_real_now = market_clock.market_now


def fixed_now():
    """钉死成 2026-09-18 14:58，省得夜里跑测试翻车。"""
    from datetime import datetime
    return datetime(2026, 9, 18, 14, 58, 0)


try:
    market_clock.market_phase = lambda now=None: market_clock.CLOSING_CALL
    market_clock.market_now = fixed_now
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=5.0)])
    chk("收盘竞价 + 涨幅够 → 燃烧", w.effects.get("sh600519", {}).get("type") == "fire",
        w.effects)
    n = len(w.effects)
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=5.0)])
    chk("同一天不再重复触发", len(w.effects) == n)

    w.effects.clear()
    w._effect_date = ""
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=-5.0)])
    chk("跌幅够 → 结霜", w.effects.get("sh600519", {}).get("type") == "frost",
        w.effects)

    w.effects.clear()
    w._effect_date = ""
    # 手里的还是昨天的数 → 等下一轮，别拿陈数据放彩蛋
    stale = row("sh600519", "600519", "贵州茅台", pct=5.0)
    stale["time"] = "20260917150000"
    w.check_close_effect([stale])
    chk("昨天的行情不触发彩蛋", w.effects == {}, w.effects)

    w.effects.clear()
    w._effect_date = ""
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=0.5)])
    chk("没到阈值不触发", w.effects == {}, w.effects)

    w.effects.clear()
    w._effect_date = ""
    market_clock.market_phase = lambda now=None: market_clock.AFTERNOON
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=5.0)])
    chk("14:56 还不触发（没进收盘竞价）", w.effects == {}, w.effects)
    market_clock.market_phase = lambda now=None: market_clock.CLOSED
    w.check_close_effect([row("sh600519", "600519", "贵州茅台", pct=5.0)])
    chk("15:00 之后不触发", w.effects == {}, w.effects)

    # 逐行看日期：以前是"有一行是今天"就全体放行，于是 A 涨 5% 触发之后，
    # 挂着昨天收盘价的 B 也能拿昨天的 +8% 跟着一起烧。
    market_clock.market_phase = lambda now=None: market_clock.CLOSING_CALL
    w.effects.clear()
    w._effect_date = ""
    today_row = row("sh600519", "600519", "贵州茅台", pct=5.0)
    old_row = row("sz000001", "000001", "平安银行", pct=8.0)
    old_row["time"] = "20260917150000"      # 昨天
    w.check_close_effect([today_row, old_row])
    chk("只烧今天的，昨天的那只不跟着",
        set(w.effects) == {"sh600519"}, set(w.effects))
    chk("今天的确实是 fire", w.effects.get("sh600519", {}).get("type") == "fire")
    chk("昨天的没被记上", "sz000001" not in w.effects, set(w.effects))

    # 全都是昨天的 → 一行都不触发（哪怕涨幅更大）
    w.effects.clear()
    w._effect_date = ""
    w.check_close_effect([old_row])
    chk("全是昨天的就一行都不触发", w.effects == {}, w.effects)
finally:
    market_clock.market_phase = _real
    market_clock.market_now = _real_now

print("== 提醒与彩蛋的 key 是完整代码 ==")
# sh000001 和 sz000001 的 6 位 code 相同，key 用 code 会互相串
w._alert_armed.clear()
w.flash.clear()
w.cfg["alert_pct"] = 3.0
_real_phase = market_clock.market_phase
try:
    market_clock.market_phase = lambda now=None: market_clock.MORNING
    w.check_alert([row("sh000001", "000001", "上证指数", pct=5.0),
                   row("sz000001", "000001", "平安银行", pct=5.0)])
    chk("两个 000001 各自独立记一笔",
        set(w.flash) == {"sh000001", "sz000001"}, set(w.flash))
finally:
    market_clock.market_phase = _real_phase

print("== 换数据源后，旧源的在途行情要被丢掉 ==")
w.apply_watchlist(["sh600519"])
gen_a = w.watchlist_generation
w.set_data_source("sina")
gen_b = w.watchlist_generation
chk("切源 → generation +1", gen_b == gen_a + 1, (gen_a, gen_b))
# 旧源（腾讯）的请求是在切源之前发出去的，现在才回来
w.rows = []
emit([row("sh600519", "600519", "贵州茅台", 9.9)], gen=gen_a)
chk("旧源的行情不进界面", w.rows == [], w.rows)
emit([row("sh600519", "600519", "贵州茅台", 1.1)], gen=gen_b)
chk("新源的行情照常收下", len(w.rows) == 1, w.rows)
w.set_data_source("auto")

print("== 切数据源后，旧源的分时不能污染新源的缓存 ==")
# generation 保护的是 rows（旧整批结果会被 UI 丢掉），没保护 spark cache：
# 旧请求在途时切源，切源会 generation+1 并清空缓存，但**旧请求回来之后会
# 把它的结果再写一遍** —— 刚清掉的缓存又长回来，装的是旧源的走势。新源
# 下一轮读到它直接命中、不再发请求。价格是新源的，迷你分时是旧源画的。
#
# 用 Event 卡住时序，不用 sleep 猜：让旧请求精确地停在"网络已发出、还没返回"。
_real_spark = W.providers.fetch_spark
calls = []
f = W.SparkFetcher()
f.set_codes(["sh600519"])
gen_t = f._generation


_blocked = []


def fake_spark(full, prefer="auto"):
    calls.append((full, prefer))
    # 只卡住"第一通请求"，不能靠 len(calls)（测试中间会 clear，又会卡一次）
    if not _blocked:
        _blocked.append(1)
        started.set()
        release.wait(5)
    return [10.0, 10.2, 10.1] if prefer == "tencent" else [20.0, 20.5, 20.3]


started, release = threading.Event(), threading.Event()
W.providers.fetch_spark = fake_spark
box = {}
t = threading.Thread(
    target=lambda: box.update(v=f._spark("sh600519", "tencent", gen_t)))
t.start()
try:
    chk("旧请求确实卡在网络里", started.wait(5))

    # 用户此刻切源：新的 generation + 清空缓存
    f.set_source("sina", gen_t + 1)
    gen_s = f._generation
    release.set()
    t.join(5)

    chk("切源 → generation +1", gen_s == gen_t + 1, (gen_t, gen_s))
    chk("旧请求放弃了它的结果（身份已经变了）", box.get("v") is None, box.get("v"))
    chk("旧源的结果没被写回缓存", f._spark_cache.get("sh600519") is None,
        f._spark_cache)

    calls.clear()
    pts_s = f._spark("sh600519", "sina", gen_s)
    chk("新源没命中旧缓存，真的发了请求", ("sh600519", "sina") in calls, calls)
    chk("新源拿到的是新源的走势", pts_s == [20.0, 20.5, 20.3], pts_s)
    entry = f._spark_cache.get("sh600519") or {}
    chk("缓存条目记着自己的身份",
        entry.get("source") == "sina" and entry.get("generation") == gen_s, entry)

    calls.clear()
    chk("同一身份第二次命中缓存", f._spark("sh600519", "sina", gen_s) == pts_s)
    chk("命中缓存就不再发请求", calls == [], calls)

    # 换回腾讯（又一代）→ 新浪那条不该被命中
    calls.clear()
    gen_t2 = f.set_source("tencent", gen_s + 1)
    pts_t = f._spark("sh600519", "tencent", gen_t2)
    chk("切回腾讯后拿到的确实是腾讯的走势", pts_t == [10.0, 10.2, 10.1], pts_t)
finally:
    release.set()
    t.join(5)
    f._stop = True
    W.providers.fetch_spark = _real_spark

print("== 换自选股也要让旧分时失效 ==")
f2 = W.SparkFetcher()
f2.set_codes(["sh600519"])
gen1 = f2._generation
f2._spark_cache["sh600519"] = {"ts": time.time(), "source": "auto",
                               "generation": gen1, "pts": [1.0, 2.0, 3.0]}
f2.set_codes(["sz000001"], gen1 + 1)   # 换自选 → 又一代
gen2 = f2._generation
chk("换自选 → generation +1", gen2 == gen1 + 1, (gen1, gen2))
calls.clear()
W.providers.fetch_spark = fake_spark
try:
    pts = f2._spark("sh600519", "auto", gen2)
    chk("换自选后旧分时不再命中（重新去拉）", calls != [], calls)
finally:
    W.providers.fetch_spark = _real_spark
    f2._stop = True

print("== 切源 / 换自选后，当轮就要拉新身份的分时 ==")
# 二阶竞态：旧 generation 的 _fill_spark() 在循环结束后会把全局计数值重新抬高，
# 于是刚切完源的新一轮读到"计数 > 0"就直接返回 —— 价格已经是新源的了，
# 分时图却空白着，要等计数倒数归零（交易时段最长接近 5 分钟）。
# 所以不要留第二套 TTL 状态，让每条 cache entry 自己决定过没过期。


def race_fill(bump, label, src_old, src_new):
    """bump: 让身份变化的那个动作（set_source / set_codes）。"""
    fx = W.SparkFetcher()
    fx.set_codes(["sh600519"])
    g_old = fx._generation
    seen = []

    blocked = []

    def fake(full, prefer="auto"):
        seen.append((full, prefer))
        if not blocked:                 # 只卡住第一通（旧身份的）
            blocked.append(1)
            go.set()
            done.wait(5)
        return [10.0, 10.2] if prefer == "tencent" else [20.0, 20.5]

    go, done = threading.Event(), threading.Event()
    W.providers.fetch_spark = fake
    box = {}
    t = threading.Thread(
        target=lambda: box.update(v=fx._spark("sh600519", src_old, g_old)))
    t.start()
    try:
        if not go.wait(5):
            chk("%s：旧 spark 请求卡进网络" % label, False, "没等到")
            return
        g_new = bump(fx)                # 身份变化（切源 / 换自选）
        done.set()
        t.join(5)

        # 新身份的**当轮**就必须真的去拉，不能返回全 None
        seen.clear()
        pts = fx._spark("sh600519", src_new, g_new)
        chk("%s：当轮就发新身份的 spark 请求" % label, seen != [], seen)
        chk("%s：当轮就拿到分时，不是 None" % label, pts is not None, pts)
        chk("%s：拿到的是新身份的走势" % label,
            pts == [20.0, 20.5] or src_new == "tencent", pts)
    finally:
        done.set()
        t.join(5)
        fx._stop = True
        W.providers.fetch_spark = _real_spark


race_fill(lambda fx: fx.set_source("sina", fx._generation + 1), "切源",
          "tencent", "sina")
race_fill(lambda fx: fx.set_codes(["sh600519"], fx._generation + 1), "换自选",
          "auto", "auto")


print("== P0：spark 卡死，不许挡住核心报价 ==")
# 这是 P0 的核心：报价早就取到了，以前要等 5 只 spark 拉完才 emit。
# 两个分时接口同时挂时，价格最长接近 60 秒不刷新。
_real_quotes = W.providers.fetch_quotes
_real_spark_fn = W.providers.fetch_spark
stuck = threading.Event()


def quick_quotes(codes, prefer="auto"):
    """报价：立即返回"""
    return [P.make_quote(c, c[2:], "测试", "11.0", "10.0", volume=100)
            for c in codes]


def stuck_spark(code, prefer="auto"):
    stuck.wait(120)          # 永久卡住（模拟分时接口挂了）
    return None


W.providers.fetch_quotes = quick_quotes
W.providers.fetch_spark = stuck_spark
got = []
fq = W.Fetcher()
fq.set_interval(1)
fq.set_codes(["sh600519"])
fq.data_ready.connect(got.append)
_real_fetcher_start(fq)
try:
    end = time.time() + 5
    while time.time() < end and not got:
        QApplication.processEvents()      # 跨线程信号要事件循环才会投递
        time.sleep(0.05)
    chk("spark 卡死时报价照样发出", bool(got), got)
    if got:
        _r = got[0].get("rows") or []
        chk("报价里带着行", bool(_r), got[0])
        if _r:
            chk("行里带着价格", _r[0].get("price") == 11.0, _r[0])
        chk("rows_ok 为真", got[0].get("rows_ok") is True, got[0])
finally:
    fq._stop = True
    stuck.set()
    fq.wait(W.Fetcher.WORKER_WAIT_MS)
    W.providers.fetch_quotes = _real_quotes
    W.providers.fetch_spark = _real_spark_fn

print("== P0：spark 慢/失败，报价节奏不受影响 ==")
# 5 只 spark 每只都慢 0.3 秒：如果还在关键路径上，一轮要多花 1.5 秒
slow_got = []
W.providers.fetch_quotes = quick_quotes


def slow_spark(code, prefer="auto"):
    time.sleep(0.3)
    return None              # 两源都失败


W.providers.fetch_spark = slow_spark
# 非交易时段会走 slow=60 秒一轮，那就测不出节奏了 —— 这里按活跃时段算
_real_active = market_clock.is_active
market_clock.is_active = lambda: True
fs = W.Fetcher()
fs.set_interval(1)
fs.set_codes(["sh600519", "sz000001", "sz300750", "sh000001", "sz399001"])
fs.data_ready.connect(slow_got.append)
_real_fetcher_start(fs)
try:
    end = time.time() + 3.2
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.05)
    # 解耦后：1 秒一轮，3 秒至少 2 轮。如果 spark 还在关键路径上，
    # 一轮要 1 + 5*0.3 = 2.5 秒，3 秒只够 1 轮。
    chk("报价节奏没有被 spark 拖慢", len(slow_got) >= 2, len(slow_got))
finally:
    fs._stop = True
    fs.wait(W.Fetcher.WORKER_WAIT_MS)
    market_clock.is_active = _real_active
    W.providers.fetch_quotes = _real_quotes
    W.providers.fetch_spark = _real_spark_fn

print("== P0：旧身份的 spark 不许 patch 新行 ==")
w.rows = [{"full": "sh600519", "spark": None}]
w.watchlist_generation = 5
w._on_spark(5, "sh600519", [1.0, 2.0, 3.0])
chk("同一代 → patch 上了", w.rows[0]["spark"] == [1.0, 2.0, 3.0],
    w.rows[0].get("spark"))
w.rows[0]["spark"] = None
w._on_spark(4, "sh600519", [9.0, 9.0, 9.0])
chk("旧一代 → 不 patch", w.rows[0]["spark"] is None, w.rows[0].get("spark"))
# 占位行没有走势可画
w.rows = [dict(W.unavailable_row("sh600519"))]
w._on_spark(5, "sh600519", [1.0, 2.0, 3.0])
chk("占位行不接分时", w.rows[0].get("spark") is None, w.rows[0].get("spark"))

print("== P0：退出时两个线程都 bounded stop ==")
W.providers.fetch_quotes = quick_quotes
W.providers.fetch_spark = lambda *a, **k: None
fz, sz = W.Fetcher(), W.SparkFetcher()
fz.set_codes(["sh600519"])
_real_fetcher_start(fz)
_real_sparker_start(sz)
time.sleep(0.4)
t0 = time.time()
fz.stop()
sz.stop()
cost = time.time() - t0
budget = (W.Fetcher.WORKER_WAIT_MS + W.SparkFetcher.WORKER_WAIT_MS) / 1000.0 + 2
chk("stop 是有界的", cost < budget, (cost, budget))
chk("两个线程都停了", not fz.isRunning() and not sz.isRunning())
W.providers.fetch_quotes = _real_quotes
W.providers.fetch_spark = _real_spark_fn

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
