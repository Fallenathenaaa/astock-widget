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

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


def response(n):
    """造一条只有 n 个字段的腾讯响应。

    字段位置照真实接口排（0=市场标识、1=名称、2=代码、3=现价、4=昨收…）。
    """
    f = ["0"] * n
    f[0] = "1"
    f[1] = "贵州茅台"
    f[2] = "600519"
    f[3] = "1257.12"        # 现价
    f[4] = "1266.98"        # 昨收
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
chk("成交量取不到 → 0（不是 IndexError）", q["volume"] == 0.0, q["volume"])
chk("涨跌停取不到 → 按板块推算", q["limit_up"] > 0 and q["limit_dn"] > 0,
    (q["limit_up"], q["limit_dn"]))
chk("涨跌幅照样算得出来", abs(q["pct"] + 0.78) < 0.01, q["pct"])

P.http_get = FakeGet(response(50))
q = P.TencentProvider().quotes(["sh600519"])[0]
chk("长度够了成交量还是 0（我们没填）", q["volume"] == 0.0, q["volume"])

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
