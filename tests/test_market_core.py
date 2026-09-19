# -*- coding: utf-8 -*-
"""行情核心：代码归一化 + 完整代码身份 + 解析鲁棒性。

这一组是 P0 里最要命那条的回归防线：
    股票的唯一身份是「带市场的完整代码」sh600519，不是 6 位 code。
sh000001（上证指数）和 sz000001（平安银行）的 6 位 code 都是 000001，
按 code 对号入座就会串股。

另外也盯着"按请求顺序补身份"这个老做法：接口漏返回一只、或者顺序变了，
后面全是错的。现在从响应的变量名里直接读身份。

不联网：http_get 被打桩。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


# ---------------------------------------------------------------- 代码归一化
print("== normalize_code：认得出 ==")
for raw, want in (
    ("sh600519", "sh600519"),
    ("SH600519", "sh600519"),
    ("600519", "sh600519"),
    ("600519.SH", "sh600519"),      # 交易所后缀是最明确的信号，必须最先认
    ("600519.SS", "sh600519"),
    ("000001.SZ", "sz000001"),      # 上证指数写法 → 深市，别被截成 000001 猜成沪市
    ("000001", "sz000001"),
    ("300750", "sz300750"),
    ("688981", "sh688981"),
    ("920189", "bj920189"),
    ("920189.BJ", "bj920189"),
    ("399001", "sz399001"),
    ("515220", "sh515220"),
    (" sh600519 ", "sh600519"),
    ("sh_600519", "sh600519"),
):
    got = W.normalize_code(raw)
    chk("%s -> %s" % (raw, want), got == want, got)

print("== normalize_code：认不出就 None，不猜 ==")
for raw in ("", "   ", "60051", "6005199", "abc", "600519.HK", "hk00700",
            "sh600519x", "123456.SHX", "000000", "999999", None):
    got = W.normalize_code(raw)
    chk("%r -> None" % (raw,), got is None, got)

print("== normalize_code：6 位纯数字的市场推断 ==")
for raw, want in (
    ("600000", "sh600000"), ("601398", "sh601398"), ("688111", "sh688111"),
    ("000002", "sz000002"), ("001979", "sz001979"), ("002594", "sz002594"),
    ("003816", "sz003816"), ("300059", "sz300059"), ("301269", "sz301269"),
    ("430047", "bj430047"), ("830799", "bj830799"), ("873169", "bj873169"),
):
    chk("%s -> %s" % (raw, want), W.normalize_code(raw) == want,
        W.normalize_code(raw))

print("== 只做沪深京 A 股 / 指数 / ETF，其它品种一律不收 ==")
# 这个产品不做 B 股、可转债、场外基金、港股、美股。
# 关键点：normalize_code 和搜索过滤必须共用同一套白名单（providers.symbol_kind），
# 否则会留下「搜索不给你选、但手输代码能加进去」的裂缝。
for raw, note in (
    ("900901", "沪 B 股"),
    ("200011", "深 B 股"),
    ("110055", "沪可转债"),
    ("123456", "深可转债"),
    ("501018", "沪老封闭式基金"),
    ("820001", "北交所 82 段（不存在）"),
):
    chk("%s（%s）-> None" % (raw, note), W.normalize_code(raw) is None,
        W.normalize_code(raw))
# 手输能加的，必须也是搜索会给的
for raw in ("600519", "000001", "300750", "688981", "920189",
            "sh000001", "sz399006", "bj899050", "515220", "159915", "161032"):
    full = W.normalize_code(raw)
    chk("%s 手输与搜索口径一致" % raw,
        full is not None and P.symbol_kind(full) != "", full)


# ---------------------------------------------------------------- 响应解析
def tencent_body(full, code, name, price, prev):
    """拼一条腾讯行情。f[1]名称 f[2]代码 f[3]现价 f[4]昨收 f[30]时间"""
    f = [""] * 50
    f[1], f[2], f[3], f[4] = name, code, str(price), str(prev)
    f[5], f[30], f[33], f[34], f[36] = str(prev), "20260918150000", \
        str(price), str(prev), "100"
    return 'v_%s="%s";' % (full, "~".join(f))


_real_get = P.http_get


def stub(text):
    P.http_get = lambda url, timeout=5, headers=None: text.encode("gbk", "ignore")


def stub_reset():
    P.http_get = _real_get


print("== 腾讯：身份从响应变量名来 ==")
raw = (tencent_body("sh600519", "600519", "贵州茅台", 1432.5, 1420.0)
       + tencent_body("sz000001", "000001", "平安银行", 11.32, 11.53)
       + tencent_body("sh000001", "000001", "上证指数", 3120.4, 3100.0))
stub(raw)
try:
    qs = P.TencentProvider().quotes(["sh600519", "sz000001", "sh000001"])
finally:
    stub_reset()
chk("拿到 3 条", len(qs) == 3, len(qs))
by_full = {q["full"]: q for q in qs}
chk("sh600519 是茅台", by_full.get("sh600519", {}).get("name") == "贵州茅台",
    by_full.get("sh600519", {}).get("name"))
chk("sz000001 是平安银行", by_full.get("sz000001", {}).get("name") == "平安银行",
    by_full.get("sz000001", {}).get("name"))
chk("sh000001 是上证指数", by_full.get("sh000001", {}).get("name") == "上证指数",
    by_full.get("sh000001", {}).get("name"))
# 致命的旧 bug：三个里有俩 code 都是 000001，按 code 存就会覆盖
chk("两个 000001 没互相覆盖", len({q["full"] for q in qs}) == 3)

print("== 响应顺序反了也不串股 ==")
raw2 = (tencent_body("sh000001", "000001", "上证指数", 3120.4, 3100.0)
        + tencent_body("sz000001", "000001", "平安银行", 11.32, 11.53)
        + tencent_body("sh600519", "600519", "贵州茅台", 1432.5, 1420.0))
stub(raw2)
try:
    qs2 = {q["full"]: q for q in P.TencentProvider().quotes(
        ["sh600519", "sz000001", "sh000001"])}
finally:
    stub_reset()
chk("反序返回仍各自归位",
    qs2["sh600519"]["name"] == "贵州茅台"
    and qs2["sz000001"]["name"] == "平安银行"
    and qs2["sh000001"]["name"] == "上证指数")

print("== 中间漏了一只，剩下的不能错位 ==")
# 请求 3 只，接口只回了第 1、3 只 —— 老做法按下标补会把它俩当成第 1、2 只
raw3 = (tencent_body("sh600519", "600519", "贵州茅台", 1432.5, 1420.0)
        + tencent_body("sh000001", "000001", "上证指数", 3120.4, 3100.0))
stub(raw3)
try:
    qs3 = {q["full"]: q for q in P.TencentProvider().quotes(
        ["sh600519", "sz000001", "sh000001"])}
finally:
    stub_reset()
chk("只返回 2 条", len(qs3) == 2, len(qs3))
chk("漏掉的那只不会顶替别人",
    qs3.get("sh600519", {}).get("name") == "贵州茅台"
    and qs3.get("sh000001", {}).get("name") == "上证指数"
    and "sz000001" not in qs3)

print("== 脏行直接跳过，不炸 ==")
dirty = ('v_sh600519="坏数据";'          # 字段不够 35 个
         + 'v_bad="xx";'                 # 变量名不合法
         + 'v_sz000001="%s";'
         % "~".join([""] * 40 + ["平安银行"])
         + tencent_body("sh600519", "600519", "贵州茅台", 1432.5, 1420.0)
         + "\n\n;")
# 上面那条 sz000001 昨收是空的 → make_quote 返回 None，整行作废
stub(dirty)
try:
    qs4 = P.TencentProvider().quotes(["sh600519", "sz000001"])
finally:
    stub_reset()
chk("脏数据不影响好的那只",
    len(qs4) == 1 and qs4[0]["full"] == "sh600519", qs4)

print("== 新浪：身份从 hq_str_ 变量名来 ==")


def sina_body(full, name, open_, prev, price, vol):
    f = [""] * 34
    f[0], f[1], f[2], f[3] = name, str(open_), str(prev), str(price)
    f[4], f[5], f[8] = str(price), str(prev), str(vol)
    f[30], f[31] = "2026-09-18", "15:00:00"
    return 'var hq_str_%s="%s";' % (full, ",".join(f))


raw5 = (sina_body("sh600519", "贵州茅台", 1420.0, 1420.0, 1432.5, 1000000)
        + sina_body("sz000001", "平安银行", 11.53, 11.53, 11.32, 2000000)
        + sina_body("sh000001", "上证指数", 3100.0, 3100.0, 3120.4, 3000000))
stub(raw5)
try:
    qs5 = {q["full"]: q for q in P.SinaProvider().quotes(
        ["sh600519", "sz000001", "sh000001"])}
finally:
    stub_reset()
chk("新浪也认完整代码",
    set(qs5) == {"sh600519", "sz000001", "sh000001"}, set(qs5))
chk("新浪名字对得上",
    qs5["sz000001"]["name"] == "平安银行"
    and qs5["sh000001"]["name"] == "上证指数")
# 新浪给的是股，腾讯给的是手，统一成手
chk("成交量换算成手", abs(qs5["sh600519"]["volume"] - 10000.0) < 1e-6,
    qs5["sh600519"]["volume"])

print("== 空请求不发网络 ==")
stub("")
try:
    chk("空列表返回空", P.TencentProvider().quotes([]) == [])
    chk("新浪空列表返回空", P.SinaProvider().quotes([]) == [])
finally:
    stub_reset()

print("== make_quote 的 full 是必填身份 ==")
chk("没 full → 废数据", P.make_quote("", "600519", "某某", 1.0, 10.0) is None)
chk("没 code → 废数据", P.make_quote("sh600519", "", "某某", 1.0, 10.0) is None)
chk("昨收 0 → 废数据", P.make_quote("sh600519", "600519", "某某", 1.0, 0) is None)
chk("名称空就用代码顶", P.make_quote("sh600519", "600519", "", 1.0, 10.0)["name"]
    == "600519")

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
