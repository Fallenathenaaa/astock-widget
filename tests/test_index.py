# -*- coding: utf-8 -*-
"""指数条的身份绑定：名字必须跟 full code 走，不能跟返回顺序走。

以前是按位置取的（第 0 个叫上证、第 1 个叫深证），接口漏返回一只或者顺序变了，
"深证 +1.2%" 就挂到"上证"那一格上了 —— 而 sh000001（上证指数）和 sz000001
（平安银行）的 6 位代码都是 000001，看 code 也分不出来。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def idx(full, pct):
    return {"full": full, "code": full[2:], "name": full, "pct": pct,
            "price": 0.0, "prev": 0.0, "change": 0.0, "decimals": 2,
            "time": "20260918150000", "status": "normal"}


SH, SZ, CYB = "sh000001", "sz399001", "sz399006"


def names(slots):
    return [s[0] for s in slots]


def pcts(slots):
    return [s[1] for s in slots]


print("== 正常顺序 ==")
s = W.index_slots([idx(SH, 1.11), idx(SZ, -2.22), idx(CYB, 3.33)])
chk("三格名字对得上", names(s) == ["上证", "深证", "创业板"], names(s))
chk("三格涨幅对得上", pcts(s) == [1.11, -2.22, 3.33], pcts(s))

print("== 反着返回 ==")
s = W.index_slots([idx(CYB, 3.33), idx(SZ, -2.22), idx(SH, 1.11)])
chk("名字仍按 code 归位", names(s) == ["上证", "深证", "创业板"], names(s))
chk("涨幅不会串位", pcts(s) == [1.11, -2.22, 3.33], pcts(s))

print("== 漏返回 ==")
s = W.index_slots([idx(SZ, -2.22), idx(CYB, 3.33)])
chk("缺上证 → 上证那格是 None", s[0] == ("上证", None), s[0])
chk("深证还在自己那格", s[1] == ("深证", -2.22), s[1])
chk("创业板不顶上去", s[2] == ("创业板", 3.33), s[2])

s = W.index_slots([idx(SH, 1.11), idx(CYB, 3.33)])
chk("缺深证 → 深证那格是 None", s[1] == ("深证", None), s[1])
chk("创业板不顶上去", s[2] == ("创业板", 3.33), s[2])

print("== 只返回创业板 ==")
s = W.index_slots([idx(CYB, 3.33)])
chk("只有创业板有数", pcts(s) == [None, None, 3.33], pcts(s))

print("== 边界 ==")
chk("一个都没有 → 三格全空", pcts(W.index_slots([])) == [None, None, None])
chk("传 None 不崩", pcts(W.index_slots(None)) == [None, None, None])
chk("重复返回同一只只算一次",
    pcts(W.index_slots([idx(SH, 1.0), idx(SH, 9.9)])) == [1.0, None, None],
    pcts(W.index_slots([idx(SH, 1.0), idx(SH, 9.9)])))
chk("不认识的 code 不会挤进三格",
    pcts(W.index_slots([idx("sh600519", 5.0)])) == [None, None, None])
chk("缺 pct 字段不崩",
    pcts(W.index_slots([{"full": SH}])) == [None, None, None])

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
