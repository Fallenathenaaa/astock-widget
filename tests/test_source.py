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
chk("乱字段不炸", P.make_quote("sh600519", "600519", "某某", "abc", "10.0")["price"] == 0.0)

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
