# -*- coding: utf-8 -*-
"""配置 schema 校验 + 原子写入 + worker 停机超时。

`stocks.json` 是给用户手改的。JSON 能解析不等于能用：
`"interval": -1`、`"ui_scale": "abc"`、`"codes": "sh600519"`（写成字符串）
这些以前会一路带到 UI 上，轻则排版错乱，重则绘制时抛异常。
校验的底线是：**认不出来就退回默认，绝不能让程序起不来。**

另外盯着两件事：
- 写配置必须是原子的（写 tmp + os.replace），写一半断电不能留下半个文件
- 退出时等线程的时间必须 > HTTP 超时，否则"停止"其实是"硬杀"
"""
import io
import os
import sys
import copy
import json
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
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


tmp = tempfile.mkdtemp(prefix="astock-cfg-")
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")


def write(text):
    with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(text)


print("== 合法配置原样保留 ==")
good = copy.deepcopy(W.DEFAULT_CONFIG)
good["title"] = "我的盯盘"
good["codes"] = ["sh600519", "sz000001"]
good["interval"] = 5
out = W.validate_config(good)
chk("标题保留", out["title"] == "我的盯盘", out["title"])
chk("自选股保留", out["codes"] == ["sh600519", "sz000001"], out["codes"])
chk("刷新间隔保留", out["interval"] == 5, out["interval"])

print("== 类型错了退回默认 ==")
bad = {
    "title": 12345,                 # 数字当标题
    "interval": "abc",              # 字符串当间隔
    "ui_scale": "abc",
    "show_index": "yes",            # 字符串当 bool
    "codes": {"a": 1},              # 字典当列表
    "positions": "nonsense",
    "pos": "here",
    "locked": 0,
}
out = W.validate_config(bad)
chk("数字标题转成字符串", isinstance(out["title"], str), out["title"])
chk("坏 interval 退回默认", out["interval"] == W.DEFAULT_CONFIG["interval"],
    out["interval"])
chk("坏 ui_scale 退回默认", out["ui_scale"] == W.DEFAULT_CONFIG["ui_scale"],
    out["ui_scale"])
chk("非空字符串当 bool = True", out["show_index"] is True)
chk("0 当 bool = False", out["locked"] is False)
chk("坏 codes 退回默认", out["codes"] == W.DEFAULT_CONFIG["codes"], out["codes"])
chk("坏 positions 变空字典", out["positions"] == {}, out["positions"])
chk("坏 pos 变 None", out["pos"] is None, out["pos"])

print("== 取值越界要夹住 ==")
out = W.validate_config({"bg_alpha": 99999})
chk("bg_alpha 夹到 255", out["bg_alpha"] == 255, out["bg_alpha"])
out = W.validate_config({"bg_alpha": -5})
chk("bg_alpha 夹到 0", out["bg_alpha"] == 0, out["bg_alpha"])
out = W.validate_config({"alert_pct": -3})
chk("负阈值夹到 0", out["alert_pct"] == 0.0, out["alert_pct"])
out = W.validate_config({"effect_pct": -1})
chk("负彩蛋阈值夹到 0", out["effect_pct"] == 0.0, out["effect_pct"])

print("== 可选值集合 ==")
for v in (1, 3, 5, 10, 30):
    chk("interval=%s 合法" % v, W.validate_config({"interval": v})["interval"] == v)
chk("interval=7 不在集合里 → 退回默认",
    W.validate_config({"interval": 7})["interval"] == W.DEFAULT_CONFIG["interval"])
chk("ui_scale=0.5 不在集合里 → 退回默认",
    W.validate_config({"ui_scale": 0.5})["ui_scale"] == W.DEFAULT_CONFIG["ui_scale"])

print("== 自选股去重 / 截断 / 去空 ==")
out = W.validate_config({"codes": ["sh600519", "sh600519", "sz000001", "", None]})
chk("重复只留一次", out["codes"] == ["sh600519", "sz000001"], out["codes"])
out = W.validate_config({"codes": ["1", "2", "3", "4", "5", "6", "7"]})
chk("最多 5 只", len(out["codes"]) == 5, out["codes"])
chk("非字符串被剔除",
    all(isinstance(c, str) for c in out["codes"]), out["codes"])

print("== pos 必须是两个数 ==")
chk("合法 pos 保留", W.validate_config({"pos": [10, 20]})["pos"] == [10, 20])
chk("三个数不要", W.validate_config({"pos": [1, 2, 3]})["pos"] is None)
chk("字符串不要", W.validate_config({"pos": ["1", "2"]})["pos"] is None)
chk("null 就是 null", W.validate_config({"pos": None})["pos"] is None)

print("== 不认识的东西 / 脏输入不炸 ==")
out = W.validate_config({"no_such_key": 1, "another": [1, 2]})
chk("多余键被丢掉", "no_such_key" not in out and "another" not in out)
chk("键集合和默认一致", set(out) == set(W.DEFAULT_CONFIG), set(out) ^ set(W.DEFAULT_CONFIG))
for junk in (None, [], "hello", 42, 3.14):
    try:
        r = W.validate_config(junk)
        chk("传入 %r 不炸且返回完整配置" % (junk,),
            isinstance(r, dict) and set(r) == set(W.DEFAULT_CONFIG))
    except Exception as e:
        chk("传入 %r 不炸且返回完整配置" % (junk,), False, repr(e))

print("== 深拷贝：不能共用可变子对象 ==")
a = W.validate_config(W.DEFAULT_CONFIG)
b = W.validate_config(W.DEFAULT_CONFIG)
a["codes"].append("sh601318")
a["positions"]["sh600519"] = {"cost": 1.0}
chk("两次校验不共用 codes", "sh601318" not in b["codes"], b["codes"])
chk("两次校验不共用 positions", b["positions"] == {}, b["positions"])
chk("DEFAULT_CONFIG 本身没被污染",
    "sh601318" not in W.DEFAULT_CONFIG["codes"]
    and W.DEFAULT_CONFIG["positions"] == {},
    (W.DEFAULT_CONFIG["codes"], W.DEFAULT_CONFIG["positions"]))

print("== load_config：坏了也不崩 ==")
write("{ this is not json")
cfg = W.load_config()
chk("坏 JSON 退回默认，不抛异常", cfg["title"] == W.DEFAULT_CONFIG["title"])
write("")
cfg = W.load_config()
chk("空文件退回默认", cfg["title"] == W.DEFAULT_CONFIG["title"])
write(json.dumps({"title": "好的", "interval": "坏值"}, ensure_ascii=False))
cfg = W.load_config()
chk("部分字段坏 → 只坏的那项回默认",
    cfg["title"] == "好的" and cfg["interval"] == W.DEFAULT_CONFIG["interval"],
    (cfg["title"], cfg["interval"]))

print("== 原子写入 ==")
W.atomic_write_text(W.CONFIG_PATH, json.dumps({"title": "atomic"}, ensure_ascii=False))
chk("内容写对了",
    json.loads(io.open(W.CONFIG_PATH, encoding="utf-8").read())["title"] == "atomic")
chk("没有留下 .tmp 残留",
    not os.path.exists(W.CONFIG_PATH + ".tmp")
    and not any(f.endswith(".tmp") for f in os.listdir(tmp)), os.listdir(tmp))
# 在同一路径上反复写，中途留下的临时文件不能污染目录
for i in range(5):
    W.atomic_write_text(W.CONFIG_PATH, json.dumps({"title": "t%d" % i}))
chk("反复写后只剩一个配置文件",
    sorted(os.listdir(tmp)) == ["stocks.json"], os.listdir(tmp))

print("== worker 停机等待 > HTTP 超时 ==")
# HTTP 超时 5 秒；等的时间比它短，就是在线程还在收数据的时候硬杀
f = W.Fetcher()
s = W.Searcher()
chk("Fetcher 等待 ≥ 6 秒", f.WORKER_WAIT_MS >= 6000, f.WORKER_WAIT_MS)
chk("Searcher 等待 ≥ 6 秒", s.WORKER_WAIT_MS >= 6000, s.WORKER_WAIT_MS)
chk("HTTP 超时是 5 秒", P.http_get.__defaults__[0] == 5,
    P.http_get.__defaults__)
chk("等待时间 = 超时 + 余量",
    f.WORKER_WAIT_MS >= P.http_get.__defaults__[0] * 1000,
    (f.WORKER_WAIT_MS, P.http_get.__defaults__[0]))
f._stop = True
s._stop = True

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
