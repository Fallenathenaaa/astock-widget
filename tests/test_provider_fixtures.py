# -*- coding: utf-8 -*-
"""用**真实接口返回**跑解析 —— 接口改字段能立刻发现。

tests/fixtures/ 里存的是真实抓回来的响应（见 tools/capture_fixtures.py）。
这跟 test_market_core.py 里手写的样例是两回事：手写的样例是我按自己的理解拼的，
接口把字段挪一位照样通过，等于没测；真实响应挪一位这里就红。

**不联网**：http_get 被打桩成读文件。

价格、成交量每次都不一样，所以一条都不断言具体数值 —— 只断言结构：
代码对得上、名称不是数字、涨跌停价包住昨收、时间戳是 14 位……
这些才是"字段位置没漂移"的证据。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")

import providers as P  # noqa: E402

ok = fail = 0
skipped = []


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


def fixture(name):
    """读一份 fixture；没有就返回 None（让用例跳过，而不是假装通过）。"""
    p = os.path.join(FIX, name)
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def stub(text):
    """把 http_get 换成返回固定文本（按 gbk 编码回 bytes，和真实链路一致）。"""
    P.http_get = lambda url, timeout=5, headers=None: text.encode("gbk", "ignore")


_real_get = P.http_get

# 抓 fixture 时请求的就是这 5 只，顺序也一致
CODES = ["sh600519", "sz000001", "sh000001", "sz300750", "sh515220"]


def check_quotes(label, provider, fname):
    """两家源共用的结构检查。"""
    raw = fixture(fname)
    if raw is None:
        skipped.append(fname)
        print("  SKIP  %s（没有 fixture，先跑 tools/capture_fixtures.py）" % fname)
        return []
    stub(raw)
    try:
        rows = provider().quotes(CODES)
    finally:
        P.http_get = _real_get

    chk("%s：%d 只全部解析出来" % (label, len(CODES)),
        len(rows) == len(CODES), "%d 只，full=%s" % (len(rows), [r["full"] for r in rows]))

    by_full = {r["full"]: r for r in rows}
    for full in CODES:
        r = by_full.get(full)
        if r is None:
            chk("%s：%s 在返回里" % (label, full), False, "没解析出来")
            continue
        # 字段位置锁：接口要是把代码挪到别的下标，这里立刻红
        chk("%s：%s 的 code 与请求一致" % (label, full),
            r["code"] == full[2:], r["code"])
        # 名称不能是数字（说明名称和代码的下标搞反了）、不能带分隔符
        name = r["name"]
        chk("%s：%s 名称正常「%s」" % (label, full, name),
            bool(name) and not name.isdigit()
            and "~" not in name and "," not in name, name)
        chk("%s：%s 现价 / 昨收都是正数" % (label, full),
            r["price"] > 0 and r["prev"] > 0,
            (r["price"], r["prev"]))
        chk("%s：%s 涨跌停价包住昨收" % (label, full),
            r["limit_up"] > r["prev"] > r["limit_dn"] > 0,
            (r["limit_up"], r["prev"], r["limit_dn"]))
        chk("%s：%s 时间戳是 14 位" % (label, full),
            len(r["time"]) >= 8 and r["time"][:8].isdigit(), r["time"])
        chk("%s：%s 涨跌幅与价格自洽" % (label, full),
            abs(r["pct"] - (r["price"] - r["prev"]) / r["prev"] * 100) < 1e-6,
            (r["pct"], r["price"], r["prev"]))

    # ETF 是 3 位小数，普通股 2 位 —— 这是"基金自动识别"的回归防线
    etf = by_full.get("sh515220")
    if etf:
        chk("%s：ETF 报 3 位小数" % label, etf["decimals"] == 3, etf["decimals"])
    stock = by_full.get("sh600519")
    if stock:
        chk("%s：普通股报 2 位小数" % label, stock["decimals"] == 2, stock["decimals"])
        # 茅台在两家源里名字都一样，用它锁住"名称字段"的位置
        chk("%s：sh600519 解析出「贵州茅台」" % label,
            stock["name"] == "贵州茅台", stock["name"])
    return rows


print("== 腾讯行情（真实响应）==")
check_quotes("腾讯", P.TencentProvider, "tencent_quotes.txt")

print("== 新浪行情（真实响应）==")
check_quotes("新浪", P.SinaProvider, "sina_quotes.txt")


def check_search(label, provider, fname, want_full=None):
    raw = fixture(fname)
    if raw is None:
        skipped.append(fname)
        print("  SKIP  %s（没有 fixture）" % fname)
        return []
    stub(raw)
    try:
        items = provider().search(QUERY[fname], limit=8)
    finally:
        P.http_get = _real_get
    chk("%s：%s 有结果" % (label, fname), len(items) > 0, len(items))
    for it in items:
        chk("%s：%s 的代码是 6 位数字" % (label, it.get("full")),
            len(it.get("code", "")) == 6 and it["code"].isdigit(), it.get("code"))
        chk("%s：%s 在沪深京范围内" % (label, it.get("full")),
            bool(P.symbol_kind(it["full"])), it.get("full"))
        chk("%s：%s 名称不是空的" % (label, it.get("full")),
            bool(it.get("name")), it.get("name"))
    if want_full:
        chk("%s：%s 能搜到 %s" % (label, fname, want_full),
            any(it["full"] == want_full for it in items),
            [it["full"] for it in items])
    return items


# fixture 文件名 -> 抓的时候用的关键字
QUERY = {
    "tencent_search_name.txt": "贵州茅台",
    "sina_search_name.txt": "贵州茅台",
    "tencent_search_code.txt": "600519",
    "sina_search_code.txt": "600519",
    "tencent_search_pinyin.txt": "mt",
    "sina_search_pinyin.txt": "mt",
}

print("== 搜索：按中文名 ==")
check_search("腾讯", P.TencentProvider, "tencent_search_name.txt", "sh600519")
check_search("新浪", P.SinaProvider, "sina_search_name.txt", "sh600519")

print("== 搜索：按代码 ==")
check_search("腾讯", P.TencentProvider, "tencent_search_code.txt", "sh600519")
check_search("新浪", P.SinaProvider, "sina_search_code.txt", "sh600519")

print("== 搜索：按拼音缩写（这一路最容易混进别的东西）==")
t_py = check_search("腾讯", P.TencentProvider, "tencent_search_pinyin.txt")
s_py = check_search("新浪", P.SinaProvider, "sina_search_pinyin.txt")
# 搜 "mt" 会撞上「美泰 / 美团」这类同缩写标的。腾讯 t=all 会把 hk 港股、
# us 美股一起返回（现在改成了 t=gp，请求里就不会有了），新浪 type=12 是 B 股、
# 21/22 是场外基金 —— 不管接口给什么，过滤之后只能剩沪深京。
for label, items in (("腾讯", t_py), ("新浪", s_py)):
    if not items:
        continue
    chk("%s：搜 mt 没有混进非 A 股标的" % label,
        all(it["full"][:2] in ("sh", "sz", "bj") for it in items),
        [it["full"] for it in items])
    chk("%s：搜 mt 第一条就是贵州茅台" % label,
        items[0]["full"] == "sh600519",
        items[0]["full"] if items else None)

print("== fixture 本身是活的 ==")
have = sorted(f for f in os.listdir(FIX) if f.endswith(".txt")) if os.path.isdir(FIX) else []
chk("fixtures 目录里有东西", len(have) >= 2, have)
chk("行情 fixture 齐全",
    "tencent_quotes.txt" in have and "sina_quotes.txt" in have, have)
if not skipped:
    chk("所有 fixture 都用上了", True)
else:
    print("  SKIP  缺 %s" % ", ".join(skipped))

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
