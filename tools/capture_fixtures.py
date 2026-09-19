# -*- coding: utf-8 -*-
"""抓一份真实接口返回，存成测试 fixture。

    python tools/capture_fixtures.py

为什么要这个：行情接口是第三方免费接口，**随时可能改字段顺序**，而且不会通知。
测试里用的样例响应是我手写的，接口改了照样通过 —— 那就等于没测。
存一份真实返回，接口一改字段，测试立刻红。

抓回来的是**公开行情数据**（股票名、价格、成交量），不含任何个人信息，
可以放心进仓库。

**这里不自己拼 URL**，而是直接调 provider 的方法、顺路把 http_get 收到的原始
响应截下来。self 拼 URL 会和 providers.py 里的漂移开 —— 之前 providers 已经
把腾讯搜索从 t=all 改成了 t=gp，脚本还在抓 t=all，fixture 就一直是旧的。

什么时候要重抓：
- 测试报「接口字段变了」
- 改了 providers.py 里的请求参数或品种范围
- 隔了很久（半年以上），确认接口还活着
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "tests", "fixtures")

import providers as P  # noqa: E402

# 覆盖各主要品种：沪市主板 / 深市主板 / 沪市指数 / 创业板 / 沪市 ETF
CODES = ["sh600519", "sz000001", "sh000001", "sz300750", "sh515220"]

# 三种输入方式。文件名用 ASCII（中文文件名在部分 CI 上会有编码麻烦）
SEARCH = [("name", "贵州茅台"), ("code", "600519"), ("pinyin", "mt")]

_real_get = P.http_get
_captured = {}


def spy(url, timeout=5, headers=None):
    """正常发请求，但把原始响应留一份。"""
    raw = _real_get(url, timeout=timeout, headers=headers)
    _captured[url] = raw
    return raw


def save(name, raw, decode):
    path = os.path.join(OUT, name)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(raw.decode(decode, errors="ignore"))
    print("  %-24s %6d bytes" % (name, len(raw)))
    return 1


n = 0
os.makedirs(OUT, exist_ok=True)
P.http_get = spy

try:
    # 行情：直接调 provider，URL 由 providers.py 决定
    _captured.clear()
    P.TencentProvider().quotes(CODES)
    for url, raw in _captured.items():
        n += save("tencent_quotes.txt", raw, "gbk")

    _captured.clear()
    P.SinaProvider().quotes(CODES)
    for url, raw in _captured.items():
        n += save("sina_quotes.txt", raw, "gbk")

    # 搜索：三个关键字各抓一份
    for slug, kw in SEARCH:
        _captured.clear()
        P.TencentProvider().search(kw)
        for url, raw in _captured.items():
            n += save("tencent_search_%s.txt" % slug, raw, "utf-8")

        _captured.clear()
        P.SinaProvider().search(kw)
        for url, raw in _captured.items():
            n += save("sina_search_%s.txt" % slug, raw, "gbk")
finally:
    P.http_get = _real_get

print("\n%d 份 fixture -> %s" % (n, os.path.relpath(OUT, ROOT)))
print("抓完记得跑：python run_tests.py")
