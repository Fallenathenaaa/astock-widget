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

print("== 布尔值：字符串也要按字面意思算 ==")
# 以前是 bool(v)：非空字符串全是 True，于是配置里写 "false" 反而变成 True ——
# 用户在菜单里关掉的开关，重启后又自己开了。
chk('"false" → False', W.validate_config({"click_through": "false"})["click_through"] is False)
chk('"true" → True', W.validate_config({"click_through": "true"})["click_through"] is True)
chk('"FALSE" 大小写都认', W.validate_config({"spark": "FALSE"})["spark"] is False)
chk('" true " 带空格也认', W.validate_config({"spark": " true "})["spark"] is True)
chk("0 → False", W.validate_config({"locked": 0})["locked"] is False)
chk("1 → True", W.validate_config({"locked": 1})["locked"] is True)
chk('"0" → False', W.validate_config({"locked": "0"})["locked"] is False)
chk("认不出来的退回默认", W.validate_config({"click_through": "maybe"})["click_through"]
    == W.DEFAULT_CONFIG["click_through"])
chk("2 不是合法布尔，退回默认", W.validate_config({"spark": 2})["spark"]
    == W.DEFAULT_CONFIG["spark"])
chk("None 退回默认", W.validate_config({"spark": None})["spark"]
    == W.DEFAULT_CONFIG["spark"])
chk("真布尔原样", W.validate_config({"spark": False})["spark"] is False)

print("== 持仓逐条校验 ==")
chk("正常持仓保留",
    W.validate_config({"positions": {"sh600519": {"cost": 1250.0, "shares": 100}}})
    ["positions"] == {"sh600519": {"cost": 1250.0, "shares": 100.0}},
    W.validate_config({"positions": {"sh600519": {"cost": 1250.0, "shares": 100}}})["positions"])
# 这几种以前都能一路带到 UI，画盈亏时 pos.get(...) 直接崩
for bad in ["oops", 123, None, []]:
    out = W.validate_config({"positions": {"sh600519": bad}})["positions"]
    chk("坏条目 %r 被丢掉" % (bad,), out == {}, out)
for bad_cost in ["nan", "inf", "-inf", -10, 0, "abc", None, True]:
    out = W.validate_config({"positions": {"sh600519": {"cost": bad_cost}}})["positions"]
    chk("成本 %r 不收" % (bad_cost,), out == {}, out)
for bad_shares in ["abc", -100, "nan", "inf"]:
    out = W.validate_config(
        {"positions": {"sh600519": {"cost": 10.0, "shares": bad_shares}}})["positions"]
    chk("股数 %r 不当股数用" % (bad_shares,),
        out == {"sh600519": {"cost": 10.0}}, out)
chk("没填股数也能留着（只算百分比）",
    W.validate_config({"positions": {"sh600519": {"cost": 10.0}}})["positions"]
    == {"sh600519": {"cost": 10.0}})
chk("代码不合法整条丢掉",
    W.validate_config({"positions": {"hk00700": {"cost": 10.0}}})["positions"] == {})
chk("坏的不连累好的",
    W.validate_config({"positions": {"sh600519": {"cost": 10.0},
                                     "sz000001": "oops"}})["positions"]
    == {"sh600519": {"cost": 10.0}})
chk("整个 positions 不是 dict → 空",
    W.validate_config({"positions": "oops"})["positions"] == {})
chk("代码会归一化成完整代码",
    W.validate_config({"positions": {"600519": {"cost": 10.0}}})["positions"]
    == {"sh600519": {"cost": 10.0}},
    W.validate_config({"positions": {"600519": {"cost": 10.0}}})["positions"])

print("== worker 停机等待能盖住一次完整降级 ==")
# 单个源超时 5 秒；自动降级最坏要把两个源都试一遍。等的时间盖不住这个，
# 就是在线程还在收数据的时候硬杀 —— Qt 会打 "Destroyed while thread is still running"。
f = W.Fetcher()
s = W.Searcher()
worst = P.HTTP_TIMEOUT * 1000 * len(P.PROVIDERS)
chk("HTTP 超时是 5 秒", P.HTTP_TIMEOUT == 5, P.HTTP_TIMEOUT)
chk("不止一个源（所以真会降级）", len(P.PROVIDERS) > 1, len(P.PROVIDERS))
chk("Fetcher 等待 ≥ 两个源都超时", f.WORKER_WAIT_MS >= worst,
    (f.WORKER_WAIT_MS, worst))
chk("Searcher 等待 ≥ 两个源都超时", s.WORKER_WAIT_MS >= worst,
    (s.WORKER_WAIT_MS, worst))
chk("还留了解析/建连接的余量", f.WORKER_WAIT_MS - worst >= 1000,
    f.WORKER_WAIT_MS - worst)
chk("不再是旧的单源 6500", f.WORKER_WAIT_MS != 6500, f.WORKER_WAIT_MS)
f._stop = True
s._stop = True

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
