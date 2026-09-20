# -*- coding: utf-8 -*-
"""截断 / 缺字段的接口响应不能把解析打崩。

腾讯那条行情是一个 `~` 分隔的长字符串。网络抖一下、接口改版、或者行情商
临时少给几个字段，长度就会变。以前解析里写的是 `if len(f) < 35: continue`
紧接着又取 `f[36]` —— 长度正好 35 或 36 时当场 IndexError，整只股票消失
（异常冒到线程里，表现是"这一轮什么都没刷新"，很难查）。

这里把 35/36/37/48/49 这几个边界长度都喂进去，确认不抛异常。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import providers as P  # noqa: E402
import market_clock  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


def response(n, volume="123456", price="1257.12"):
    """造一条只有 n 个字段的腾讯响应。

    字段位置照真实接口排（0=市场标识、1=名称、2=代码、3=现价、4=昨收…）；
    长度够得着 f[36] 就填上成交量，模拟真实响应。想造"成交量这一列不存在"
    的截断响应就传长度 36（`response(36)` 最后一个下标是 35）。

    volume 传 "0" 可以造"明确给了 0"的场景 —— 和"没给"是两回事。
    """
    f = ["0"] * n
    f[0] = "1"
    f[1] = "贵州茅台"
    f[2] = "600519"
    f[3] = price            # 现价
    f[4] = "1266.98"        # 昨收
    if n > 36:
        f[36] = volume      # 成交量（手）
    if n > 48:
        # 涨跌停价：腾讯直接在响应里给，新浪不给（那边只能按板块推算）
        f[47], f[48] = "1393.68", "1140.28"
    return ('v_sh600519="' + "~".join(f) + '";').encode("gbk", errors="ignore")


_real_get = P.http_get


class FakeGet:
    """替换 http_get，吐出指定长度的响应。"""

    def __init__(self, payload):
        self.payload = payload

    def __call__(self, url, timeout=None, headers=None):
        return self.payload


print("== 各个边界长度都不崩 ==")
for n in (30, 34, 35, 36, 37, 40, 47, 48, 49, 50):
    P.http_get = FakeGet(response(n))
    try:
        out = P.TencentProvider().quotes(["sh600519"])
        crashed = None
    except Exception as e:
        out = None
        crashed = "%s: %s" % (type(e).__name__, e)
    chk("长度 %d 不抛异常" % n, crashed is None, crashed or "")
    if n >= 35:
        chk("长度 %d 解析出一条" % n,
            isinstance(out, list) and len(out) == 1 and out[0]["full"] == "sh600519",
            (crashed, out if not isinstance(out, list) else len(out)))
    else:
        # 连名字代码价格都凑不齐，本来就该跳过
        chk("长度 %d 直接跳过（不产生半条数据）" % n, out == [], out)

print("== 缺的字段按缺省处理，不是崩 ==")
P.http_get = FakeGet(response(36))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("成交量取不到 → None（不是 IndexError，也不是 0）", q["volume"] is None, q["volume"])
chk("涨跌停取不到 → 按板块推算", q["limit_up"] > 0 and q["limit_dn"] > 0,
    (q["limit_up"], q["limit_dn"]))
chk("涨跌幅照样算得出来", abs(q["pct"] + 0.78) < 0.01, q["pct"])

P.http_get = FakeGet(response(50))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("长度够了成交量照常解析", q["volume"] == 123456.0, q["volume"])

print("== 成交量「没给」≠「给了 0」==")
# 盘中（已开盘）才需要区分这两者：盘前成交量本来就是 0 且不判停牌
_real_started = market_clock.has_session_started
market_clock.has_session_started = lambda *a, **k: True

P.http_get = FakeGet(response(36))       # 根本没有成交量这一列
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("缺成交量 → 不判停牌（价格照常显示）", q["status"] != P.HALT, q["status"])
chk("缺成交量 → 状态是正常", q["status"] == P.NORMAL, q["status"])

P.http_get = FakeGet(response(50, volume="0"))   # 明确给了 0
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("成交量明确为 0 → 判停牌", q["status"] == P.HALT, q["status"])

P.http_get = FakeGet(response(50, volume="888"))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("成交量 > 0 → 正常", q["status"] == P.NORMAL, q["status"])
market_clock.has_session_started = _real_started

print("== 新浪缺成交量同样不判停牌 ==")
market_clock.has_session_started = lambda *a, **k: True
# 成交量那一列留空 = 接口没给；下面 _sina_full 是同一个响应但成交量有值
_sina_head = ('hq_str_sh600519="贵州茅台,1257.120,1266.980,1257.120,'
              '1260.000,1250.000,1257.120,1257.120,')
_sina_tail = (',0.000,0.000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,'
              '2026-09-18,15:00:00,00";')
_sina_line = _sina_head + "" + _sina_tail          # 成交量列为空
_sina_full = _sina_head + "12345600" + _sina_tail  # 成交量有值（股）
# 现价正好顶到「按板块推算出来的涨停价」：主板 10%，1266.98 * 1.1 = 1393.68
_sina_at_limit = _sina_head.replace("1266.980,1257.120,", "1266.980,1393.680,") + \
    "12345600" + _sina_tail
P.http_get = FakeGet(_sina_line.encode("gbk", errors="ignore"))
out = P.SinaProvider().quotes(["sh600519"])
chk("新浪成交量列为空 → volume 是 None", len(out) == 1 and out[0]["volume"] is None,
    out[0]["volume"] if out else out)
chk("新浪成交量列为空 → 不判停牌", out and out[0]["status"] != P.HALT,
    out[0]["status"] if out else out)
market_clock.has_session_started = _real_started

print("== 畸形成交量也算「没给」，不是 0 ==")
# 接口偶尔会塞占位符（"--" 真实见过）。那个字段读不出来，跟"成交量是 0"
# 是两回事 —— 当 0 处理就会判成停牌，把一只正常交易的股票显示成 --。
market_clock.has_session_started = lambda *a, **k: True
# 负成交量也是坏数据，不是"零成交"
for bad in ["-1", "-0.5", "-1e9"]:
    P.http_get = FakeGet(response(50, volume=bad))
    q = P.TencentProvider().quotes(["sh600519"])[0]
    chk("成交量 %r → None（负数无效）" % bad, q["volume"] is None, q["volume"])
    chk("成交量 %r → 不判停牌" % bad, q["status"] != P.HALT, q["status"])
for bad in ["abc", "--", "nan", "inf", "-inf", "1e999", "null", "N/A", "None"]:
    P.http_get = FakeGet(response(50, volume=bad))
    q = P.TencentProvider().quotes(["sh600519"])[0]
    chk("成交量 %r → None（不是 0）" % bad, q["volume"] is None, q["volume"])
    chk("成交量 %r → 不判停牌" % bad, q["status"] != P.HALT, q["status"])
P.http_get = FakeGet(response(50, volume="0"))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("明确给了 0 才算 0", q["volume"] == 0.0, q["volume"])
chk("明确给了 0 才判停牌", q["status"] == P.HALT, q["status"])
P.http_get = FakeGet(response(50, volume="888"))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("正常成交量照常解析", q["volume"] == 888.0, q["volume"])
# 新浪同理
P.http_get = FakeGet((_sina_head + "abc" + _sina_tail).encode("gbk", errors="ignore"))
out = P.SinaProvider().quotes(["sh600519"])
chk("新浪畸形成交量 → None", out and out[0]["volume"] is None,
    out[0]["volume"] if out else out)
chk("新浪畸形成交量 → 不判停牌", out and out[0]["status"] != P.HALT,
    out[0]["status"] if out else out)
market_clock.has_session_started = _real_started

print("== 每一条行情都带着自己的来源 ==")
P.http_get = FakeGet(response(50))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("腾讯给的数据标着 tencent", q["provider"] == "tencent", q["provider"])
chk("腾讯给了涨跌停价 → 不是推算", q["limit_estimated"] is False, q["limit_estimated"])
P.http_get = FakeGet(_sina_full.encode("gbk", errors="ignore"))
q = P.SinaProvider().quotes(["sh600519"])[0]
chk("新浪给的数据标着 sina", q["provider"] == "sina", q["provider"])
chk("新浪没给涨跌停价 → 标成推算", q["limit_estimated"] is True, q["limit_estimated"])

print("== 推算的涨跌停价不产生权威徽标 ==")
# 新浪不给涨跌停价，只能按板块算。那个值是近似规则，不能拿去当判据 ——
# 否则用户看到的是一个看起来确定的「涨停」，实际是我们估的。
P.http_get = FakeGet(_sina_at_limit.encode("gbk", errors="ignore"))
q = P.SinaProvider().quotes(["sh600519"])[0]
chk("新浪顶到推算涨停价 → 标成 estimated", q["limit_estimated"] is True)
chk("新浪顶到推算涨停价 → 不判涨停", q["status"] != P.LIMIT_UP, q["status"])
chk("新浪顶到推算涨停价 → 状态是正常", q["status"] == P.NORMAL, q["status"])
# 腾讯直接给涨跌停价，那是接口数据，照常判
P.http_get = FakeGet(response(50, price="1393.68"))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("腾讯顶到接口给的涨停价 → 不是 estimated", q["limit_estimated"] is False)
chk("腾讯顶到接口给的涨停价 → 判涨停", q["status"] == P.LIMIT_UP, q["status"])
# 跌停同理
P.http_get = FakeGet(response(50, price="1140.28"))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("腾讯顶到接口给的跌停价 → 判跌停", q["status"] == P.LIMIT_DN, q["status"])

print("== 乱码 / 空响应 ==")
for name, payload in [("空", b""), ("只有分号", b";"),
                      ("不是 v_ 开头", b'x_sh600519="1~x";'),
                      ("变量名为空", b'v_="1~x";')]:
    P.http_get = FakeGet(payload)
    try:
        out = P.TencentProvider().quotes(["sh600519"])
        err = None
    except Exception as e:
        out, err = None, "%s: %s" % (type(e).__name__, e)
    chk("%s 不崩" % name, err is None, err or "")
    chk("%s 返回空列表" % name, out == [], out)

P.http_get = _real_get
print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
