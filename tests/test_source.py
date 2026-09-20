# -*- coding: utf-8 -*-
"""数据源：涨跌停/停牌判定、多源降级调度、老板键解析。

纯逻辑，不联网。widget 只为了测 parse_hotkey，用 offscreen 起不来界面也没关系。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import market_clock  # noqa: E402
import providers as P  # noqa: E402
import widget as W  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


print("== 涨跌停价推算 ==")
chk("主板 10%", P.guess_limit("600519", "贵州茅台", 10.0) == (11.0, 9.0),
    P.guess_limit("600519", "贵州茅台", 10.0))
chk("创业板 20%", P.guess_limit("300750", "宁德时代", 10.0) == (12.0, 8.0))
chk("科创板 20%", P.guess_limit("688981", "中芯国际", 10.0) == (12.0, 8.0))
chk("北交所 30%", P.guess_limit("920189", "某某", 10.0) == (13.0, 7.0))
chk("主板 ST 5%", P.guess_limit("000002", "*ST某某", 10.0) == (10.5, 9.5))
chk("创业板 ST 仍是 20%", P.guess_limit("300156", "ST某某", 10.0) == (12.0, 8.0))
chk("昨收为 0 就不判", P.guess_limit("600519", "某某", 0) == (0.0, 0.0))

print("== 停牌 / 涨跌停判定 ==")
# 停牌要看"今天开盘了没"，这里钉死成已开盘，免得夜里跑测试翻车
_real_started = market_clock.has_session_started
market_clock.has_session_started = lambda *a, **k: True
try:
    chk("正常", P.quote_status(10.5, 100, 11.0, 9.0) == P.NORMAL)
    chk("涨停", P.quote_status(11.0, 100, 11.0, 9.0) == P.LIMIT_UP)
    chk("跌停", P.quote_status(9.0, 100, 11.0, 9.0) == P.LIMIT_DN)
    chk("没成交 = 停牌", P.quote_status(10.5, 0, 11.0, 9.0) == P.HALT)
    chk("现价为 0 = 停牌", P.quote_status(0, 100, 11.0, 9.0) == P.HALT)
    chk("没有涨跌停价时只判停牌", P.quote_status(10.5, 100, 0, 0) == P.NORMAL)
    # 推算出来的涨跌停价不能驱动权威徽标：guess_limit 是近似规则（板块百分比），
    # 覆盖不了无涨跌幅限制 / 特殊状态 / 临时规则。拿它当判据 = 把近似值包装成
    # 一个看起来确定的「涨停」，而用户看不出那是估的。不确定就少说。
    chk("推算的涨停价 → 不判涨停",
        P.quote_status(11.0, 100, 11.0, 9.0, trust_limits=False) == P.NORMAL,
        P.quote_status(11.0, 100, 11.0, 9.0, trust_limits=False))
    chk("推算的跌停价 → 不判跌停",
        P.quote_status(9.0, 100, 11.0, 9.0, trust_limits=False) == P.NORMAL)
    chk("接口给的涨停价 → 照常判涨停",
        P.quote_status(11.0, 100, 11.0, 9.0, trust_limits=True) == P.LIMIT_UP)
    chk("接口给的跌停价 → 照常判跌停",
        P.quote_status(9.0, 100, 11.0, 9.0, trust_limits=True) == P.LIMIT_DN)
    chk("不信任涨跌停价时，停牌照样判得出来",
        P.quote_status(10.5, 0, 11.0, 9.0, trust_limits=False) == P.HALT)
    chk("不信任涨跌停价时，现价为 0 照样判停牌",
        P.quote_status(0, 100, 11.0, 9.0, trust_limits=False) == P.HALT)
    chk("不信任涨跌停价 + 缺成交量 → 正常",
        P.quote_status(10.5, None, 11.0, 9.0, trust_limits=False) == P.NORMAL)
    # make_quote 必须把 limit_estimated 和 trust_limits 对上，不能各说各话
    _q1 = P.make_quote("sz000001", "000001", "平安银行", 11.0, 10.0, volume=100)
    chk("没给涨跌停价 → estimated 且不判涨跌停",
        _q1["limit_estimated"] is True and _q1["status"] == P.NORMAL, _q1["status"])
    _q2 = P.make_quote("sz000001", "000001", "平安银行", 11.0, 10.0, volume=100,
                       limit_up=11.0, limit_dn=9.0)
    chk("给了涨跌停价 → 不 estimated 且照常判涨停",
        _q2["limit_estimated"] is False and _q2["status"] == P.LIMIT_UP, _q2["status"])
    market_clock.has_session_started = lambda *a, **k: False
    chk("盘前成交量 0 不算停牌", P.quote_status(10.5, 0, 11.0, 9.0) == P.NORMAL)
finally:
    market_clock.has_session_started = _real_started

print("== 字段归一化 ==")
# make_quote 第一个参数是 full（sh600519）：6 位 code 不唯一，full 才是身份
q = P.make_quote("sh600519", "600519", "贵州茅台", 11.0, 10.0,
                 volume=100, stamp="20260918150000")
chk("full 原样保留", q["full"] == "sh600519", q["full"])
chk("涨跌幅算对", abs(q["pct"] - 10.0) < 1e-9, q["pct"])
chk("涨跌额算对", abs(q["change"] - 1.0) < 1e-9, q["change"])
chk("时间戳原样保留", q["time"] == "20260918150000")
chk("ETF 报 3 位小数",
    P.make_quote("sh515220", "515220", "煤炭ETF", 1.0, 1.0)["decimals"] == 3)
chk("普通股报 2 位小数",
    P.make_quote("sh600519", "600519", "某某", 1.0, 1.0)["decimals"] == 2)
chk("昨收为 0 是废数据", P.make_quote("sh600519", "600519", "某某", 1.0, 0) is None)
chk("没有 full 也是废数据", P.make_quote("", "600519", "某某", 1.0, 10.0) is None)
# 价格读不出来 → 整条作废，不是"价格 0"（后者会被判成停牌）
chk("价格是乱码 → 整条作废", P.make_quote("sh600519", "600519", "某某", "abc", "10.0") is None)
chk("价格是占位符 -- → 整条作废",
    P.make_quote("sh600519", "600519", "某某", "--", "10.0") is None)
chk("价格是 nan / inf → 整条作废",
    P.make_quote("sh600519", "600519", "某某", "nan", "10.0") is None
    and P.make_quote("sh600519", "600519", "某某", "1e999", "10.0") is None)
chk("明确给了 0 → 保留（可能真是停牌）",
    P.make_quote("sh600519", "600519", "某某", "0", "10.0") is not None)

print("== 来自网络的数字一律 finite-aware ==")
# 配置端已经挡住了 ±inf，网络端也得挡：接口给个 1e999 或 400 位数字，
# 让 inf 流进 price / pct / 涨跌停比较，后面全是 inf 传播。
chk("_num(inf) 兜成默认", P._num(float("inf")) == 0.0)
chk("_num(-inf) 兜成默认", P._num(float("-inf")) == 0.0)
chk("_num('1e999') 兜成默认", P._num("1e999") == 0.0)
chk("_num 超大整数兜成默认（OverflowError）", P._num(10 ** 400) == 0.0)
chk("_num 认得出来的照常", P._num("12.5") == 12.5)
chk("_num 的 default 可以是 None（分时线用它过滤废点）",
    P._num("abc", None) is None)
chk("_num 空白兜成默认", P._num("") == 0.0 and P._num(None) == 0.0)
chk("_opt_num 缺失 → None", P._opt_num("") is None and P._opt_num(None) is None)
for bad in ["abc", "--", "nan", "inf", "-inf", "1e999"]:
    chk("_opt_num(%r) → None（不是 0）" % bad, P._opt_num(bad) is None, P._opt_num(bad))
chk("_opt_num 超大整数 → None", P._opt_num(10 ** 400) is None)
for bad in ["-1", "-0.5", -3, "-1e9"]:
    chk("_opt_num(%r) → None（负成交量是坏数据）" % (bad,),
        P._opt_num(bad) is None, P._opt_num(bad))
chk("_opt_num 真实的 0 仍然是 0.0", P._opt_num("0") == 0.0)
chk("_opt_num 正常值照常", P._opt_num("123456") == 123456.0)

print("== 价格读不出来 → 整条丢弃，让备源补 ==")


class BadPrice(P.Provider):
    """主源：价格字段是个占位符（真实接口偶尔给 "--"）。"""

    key = "bad"

    def __init__(self, price="--"):
        self._price = price

    def quotes(self, codes):
        out = []
        for c in codes:
            q = P.make_quote(c, c[2:], "坏价格", self._price, "10.0", volume=100)
            if q:
                out.append(q)
        return out


class GoodPrice(P.Provider):
    """备源：价格正常。"""

    key = "good"

    def quotes(self, codes):
        return [P.make_quote(c, c[2:], "好价格", "11.0", "10.0", volume=100,
                             provider="good") for c in codes]


_old_chain = P._QUOTE_CHAIN
try:
    P._QUOTE_CHAIN = P.ProviderChain([BadPrice(), GoodPrice()])
    out = P.fetch_quotes(["sh600519"])
    chk("主源价格坏了 → 这行由备源补上",
        [o.get("full") for o in out] == ["sh600519"], out)
    chk("补上来的是备源的数据", out and out[0]["price"] == 11.0,
        out[0] if out else None)
    chk("补上来的标着备源（界面会显示灰色小字）",
        out and out[0].get("provider") == "good", out[0] if out else None)
    chk("不是被包装成停牌", out and out[0].get("status") != P.HALT,
        out[0] if out else None)

    # 两源都坏 → 这一行就是缺失，不该显示成"停牌"
    P._QUOTE_CHAIN = P.ProviderChain([BadPrice("--"), BadPrice("abc")])
    out = P.fetch_quotes(["sh600519"])
    chk("两源价格都坏 → 该行缺失", out == [], out)
finally:
    P._QUOTE_CHAIN = _old_chain

print("== 来源标记 / 涨跌停价是不是推算的 ==")
# 一屏里可能混着两个源的数据（主源漏一只、备源补上），出偏差要能问出
# "这行是谁给的"；涨跌停价有一半的情况是我们自己按板块算的，必须标出来
q = P.make_quote("sh600519", "600519", "贵州茅台", 11.0, 10.0, volume=100,
                 limit_up=11.0, limit_dn=9.0, provider="tencent")
chk("provider 记下来了", q["provider"] == "tencent", q["provider"])
chk("接口给了涨跌停价 → 不是推算", q["limit_estimated"] is False, q["limit_estimated"])
q = P.make_quote("sh600519", "600519", "贵州茅台", 11.0, 10.0, volume=100,
                 provider="sina")
chk("没给涨跌停价 → 标成推算", q["limit_estimated"] is True, q["limit_estimated"])
chk("推算值照样算得出来", (q["limit_up"], q["limit_dn"]) == (11.0, 9.0),
    (q["limit_up"], q["limit_dn"]))
chk("没传 provider 就是空串（不是 None）",
    P.make_quote("sh600519", "600519", "某某", 1.0, 1.0)["provider"] == "")
# 只给了一半（只有涨停价）也算推算：那两个数必须同真同假，不然会算出
# 一个"涨停有、跌停没有"的畸形区间
q = P.make_quote("sh600519", "600519", "某某", 1.0, 1.0, limit_up=1.1)
chk("只给一个涨跌停价 → 整体按推算", q["limit_estimated"] is True, q["limit_estimated"])
chk("推算时两个价都有值", q["limit_up"] > 0 and q["limit_dn"] > 0,
    (q["limit_up"], q["limit_dn"]))

print("== 代码分类（搜索白名单）==")
for full, want in (
    ("sh600519", "stock"), ("sh688981", "stock"), ("sz000001", "stock"),
    ("sz300750", "stock"), ("bj920189", "stock"),
    ("sh000001", "index"), ("sz399001", "index"), ("bj899050", "index"),
    ("sh515220", "fund"), ("sz159915", "fund"), ("sh588000", "fund"),
):
    chk("%s -> %s" % (full, want), P.symbol_kind(full) == want, P.symbol_kind(full))
# B 股、港股、乱写法一律不收
for full in ("sh900901", "sz200011", "hk00700", "sh60051", "sh6005199", "", "xx000001"):
    chk("%s 不在范围内" % (full or "(空)"), P.symbol_kind(full) == "", P.symbol_kind(full))

print("== 源注册 ==")
keys = [p.key for p in P.PROVIDERS]
chk("至少两个源", len(keys) >= 2, keys)
chk("每个源都有名字", all(p.label for p in P.PROVIDERS))
chk("菜单选项与源一一对应", [k for k, _ in P.SOURCE_CHOICES][1:] == keys)
chk("默认自动", P.SOURCE_CHOICES[0][0] == "auto")

print("== 降级调度 ==")


class Boom(P.Provider):
    key = "boom"

    def quotes(self, codes):
        raise IOError("down")


class Good(P.Provider):
    key = "good"

    def quotes(self, codes):
        return [{"code": "600519"}]


chain = P.ProviderChain([Boom(), Good()])
chk("主源挂了自动换备源", chain.call("quotes", [])[0]["code"] == "600519")
chk("记住上次成功的是谁", chain.last_ok == "good")
chk("下次优先用上次成功的", chain.order()[0].key == "good")
chk("手选源排最前", chain.order("boom")[0].key == "boom")

chain2 = P.ProviderChain([Boom()])
try:
    chain2.call("quotes", [])
    chk("全挂了要抛异常", False, "竟然没抛")
except IOError:
    chk("全挂了要抛异常", True)

print("== 三个入口各自记源，不互相串 ==")


class TQuotesOk(P.Provider):
    """行情正常，但搜索挂了。"""
    key = "t"

    def quotes(self, codes):
        return [{"full": c} for c in codes]

    def search(self, keyword, limit=8):
        raise IOError("search down")


class SSearchOk(P.Provider):
    """行情挂了，但搜索正常。"""
    key = "s"

    def quotes(self, codes):
        raise IOError("quotes down")

    def search(self, keyword, limit=8):
        return [{"full": "sh600519"}]


_old_chains = (P._QUOTE_CHAIN, P._SEARCH_CHAIN)
try:
    P._QUOTE_CHAIN = P.ProviderChain([TQuotesOk(), SSearchOk()])
    P._SEARCH_CHAIN = P.ProviderChain([TQuotesOk(), SSearchOk()])
    P.fetch_quotes(["sh600519"])
    chk("行情用主源", P.current_source() == "t", P.current_source())
    P.search_stocks("mt")
    chk("搜索降级到备源不改动行情的源",
        P.current_source() == "t", P.current_source())
    chk("搜索链的源是备源",
        P._SEARCH_CHAIN.last_ok == "s", P._SEARCH_CHAIN.last_ok)
finally:
    P._QUOTE_CHAIN, P._SEARCH_CHAIN = _old_chains

print("== 主源部分返回时备源补缺 ==")


class Half(P.Provider):
    """故意漏掉中间那只。"""
    key = "half"

    def __init__(self):
        self.asked = []

    def quotes(self, codes):
        self.asked.append(list(codes))
        return [{"full": c} for c in codes if c != "sh000002"]


class Rest(P.Provider):
    """备源：只回答问到的那些。"""
    key = "rest"

    def __init__(self):
        self.asked = []

    def quotes(self, codes):
        self.asked.append(list(codes))
        return [{"full": c} for c in codes]


half, rest = Half(), Rest()
chain3 = P.ProviderChain([half, rest])
want = ["sh000001", "sh000002", "sh000003"]
out = chain3.call("quotes", want, want=want)
chk("三只全回来了", [o["full"] for o in out] == want, [o["full"] for o in out])
chk("按请求顺序返回", [o["full"] for o in out] == want)
chk("主源被问的是全部", half.asked == [want], half.asked)
chk("备源只被问缺的那一只", rest.asked == [["sh000002"]], rest.asked)
# 主源自己贡献了两只，优先源就该还是主源 —— 备源只补了一只缺的，
# 它"没有功劳"，不能把下一轮的优先源抢走（否则下一轮会先去问更慢的备源）
chk("主源有贡献 → 优先源仍是主源", chain3.last_ok == "half", chain3.last_ok)

# 主源全给了，备源就不该被吵醒
half2, rest2 = Half(), Rest()
chain4 = P.ProviderChain([half2, rest2])
chain4.call("quotes", ["sh000001"], want=["sh000001"])
chk("没缺的就不去问备源", rest2.asked == [], rest2.asked)

# 备源也补不到 → 缺的那只就是没有，其余照常返回
class Empty(P.Provider):
    key = "empty"

    def quotes(self, codes):
        return []


out = P.ProviderChain([Half(), Empty()]).call("quotes", want, want=want)
chk("补不到也不影响已有的两只",
    [o["full"] for o in out] == ["sh000001", "sh000003"], out)

print("== last_ok 的 sticky 语义：谁先给出数据，下一轮就先用谁 ==")


class Give(P.Provider):
    """按构造时给的清单回答：只认问到的代码。"""

    def __init__(self, key, codes):
        self.key = key
        self._codes = set(codes)
        self.asked = []

    def quotes(self, codes):
        self.asked.append(list(codes))
        return [{"full": c} for c in codes if c in self._codes]


class Down(P.Provider):
    """一问就抛异常。"""

    def __init__(self, key="down"):
        self.key = key
        self.asked = []

    def quotes(self, codes):
        self.asked.append(list(codes))
        raise IOError("%s down" % self.key)


WANT3 = ["sh000001", "sh000002", "sh000003"]

# 1) 主源给一半 + 备源补上 → 优先源还是主源
c = P.ProviderChain([Give("a", ["sh000001", "sh000003"]), Give("b", WANT3)])
c.call("quotes", WANT3, want=WANT3)
chk("主源部分 + 备源补缺 → 仍是主源", c.last_ok == "a", c.last_ok)

# 2) 主源给一半 + 备源**一条都没给**（返回空）→ 优先源还是主源
c = P.ProviderChain([Give("a", ["sh000001", "sh000003"]), Give("b", [])])
out = c.call("quotes", WANT3, want=WANT3)
chk("备源空手而归 → 数据不受影响", [o["full"] for o in out] == ["sh000001", "sh000003"], out)
chk("备源没贡献 → 优先源还是主源", c.last_ok == "a", c.last_ok)

# 3) 主源给一半 + 备源**也抛异常** → 优先源还是主源（别被异常源顶掉）
c = P.ProviderChain([Give("a", ["sh000001", "sh000003"]), Down("b")])
c.call("quotes", WANT3, want=WANT3)
chk("备源抛异常 → 优先源还是主源", c.last_ok == "a", c.last_ok)

# 4) 主源一条都没给（返回空）→ 才轮到备源
c = P.ProviderChain([Give("a", []), Give("b", WANT3)])
c.call("quotes", WANT3, want=WANT3)
chk("主源全空 → 切到备源", c.last_ok == "b", c.last_ok)

# 5) 主源抛异常（不是返回空）→ 也算没贡献，切到备源
c = P.ProviderChain([Down("a"), Give("b", WANT3)])
c.call("quotes", WANT3, want=WANT3)
chk("主源挂了 → 切到备源", c.last_ok == "b", c.last_ok)

# 6) 手选源的优先级不受 last_ok 影响：手选谁，谁就站第一个
c = P.ProviderChain([Give("a", WANT3), Give("b", WANT3)])
c.last_ok = "b"
chk("手选源永远排最前（哪怕 last_ok 是另一个）",
    c.order("a")[0].key == "a", [p.key for p in c.order("a")])
chk("没手选时才听 last_ok 的", c.order()[0].key == "b", [p.key for p in c.order()])
chk("auto 等价不手选", c.order("auto")[0].key == "b")

# 7) 手选的源自己挂了 → 仍然降级到备源（这是产品上要的：手选是"优先"，不是"只准"）
a, b = Down("a"), Give("b", WANT3)
c = P.ProviderChain([a, b])
out = c.call("quotes", WANT3, prefer="a", want=WANT3)
chk("手选源挂了会降级，不是直接空手", [o["full"] for o in out] == WANT3, out)
chk("降级后优先源记的是备源", c.last_ok == "b", c.last_ok)

print("== 来源标记只在「不是期望的源」时才出现 ==")
# 界面上不能每行都挂一个源名 —— 满屏都是"腾讯"是噪音。只有主源没给全、
# 由备源补上的那几行才值得标出来。
chk("auto 时期望的是主源", W.expected_source("auto") == P.PROVIDERS[0].key,
    W.expected_source("auto"))
chk("auto / None / 空串都当 auto", W.expected_source(None) == W.expected_source("")
    == W.expected_source("auto"))
chk("手选谁时期望的就是谁", W.expected_source("sina") == "sina")
chk("手选 auto 之外的都原样", W.expected_source("tencent") == "tencent")
chk("期望的源 → 不标（返回空串）", W.source_note("tencent", "tencent") == "")
chk("不是期望的源 → 标出名字", W.source_note("sina", "tencent") == "新浪",
    W.source_note("sina", "tencent"))
chk("反过来自选新浪时腾讯也要标", W.source_note("tencent", "sina") == "腾讯",
    W.source_note("tencent", "sina"))
chk("没有 provider 不标", W.source_note("", "tencent") == "")
chk("没有期望源也不标", W.source_note("sina", "") == "")
chk("认不出来的源名不标（宁可少说）", W.source_note("sina3", "tencent") == "")
chk("标出来的都是源自己的 label",
    all(W.source_note(p.key, "___") == p.label for p in P.PROVIDERS))

print("== 老板键解析 ==")
chk("Ctrl+Alt+H", W.parse_hotkey("Ctrl+Alt+H") == (W.MOD_CONTROL | W.MOD_ALT, ord("H")),
    W.parse_hotkey("Ctrl+Alt+H"))
chk("Ctrl+Shift+F1", W.parse_hotkey("Ctrl+Shift+F1") == (W.MOD_CONTROL | W.MOD_SHIFT, 0x70))
chk("Ctrl+Alt+`", W.parse_hotkey("Ctrl+Alt+`") == (W.MOD_CONTROL | W.MOD_ALT, 0xC0))
chk("大小写不敏感", W.parse_hotkey("ctrl+alt+h") == W.parse_hotkey("Ctrl+Alt+H"))
chk("裸 F9 放行", W.parse_hotkey("F9") == (0, 0x78), W.parse_hotkey("F9"))
chk("裸字母不放行", W.parse_hotkey("H") == (0, 0))
chk("空串不放行", W.parse_hotkey("") == (0, 0))
chk("中文键不放行", W.parse_hotkey("Ctrl+发") == (0, 0))
chk("乱写不放行", W.parse_hotkey("Ctrl++") == (0, 0))
chk("关闭显示成'关闭'", W.hotkey_label("") == "关闭")
chk("有值就原样显示", W.hotkey_label("Ctrl+Alt+H") == "Ctrl+Alt+H")
chk("默认老板键能注册", W.parse_hotkey(W.DEFAULT_BOSS_KEY)[1] != 0)
chk("预设里每个都能解析", all(W.parse_hotkey(s)[1] or s == "" for s in W.BOSS_KEY_PRESETS))

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
