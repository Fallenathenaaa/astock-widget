# -*- coding: utf-8 -*-
"""配置损坏自动回滚：损坏恢复/全坏/全新安装"""
"""配置损坏自动回滚验证。临时目录，不碰真实配置。"""
import io
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import widget as W  # noqa: E402
import safety_guard  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


tmp = tempfile.mkdtemp(prefix="astock-recover-")
real_cfg = os.path.join(os.path.dirname(os.path.abspath(W.__file__)), "stocks.json")
# 不读真实配置：干净 clone 里没有 stocks.json，读了就假失败
REAL = None
if os.path.exists(real_cfg):
    with io.open(real_cfg, encoding="utf-8") as f:
        REAL = f.read()
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")


def write(text):
    with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(text)


GOOD = {"title": "好的配置", "codes": ["sh600519", "sz000001"],
        "positions": {"sh600519": {"cost": 1250.0, "shares": 100}}}

print("== 1. 正常配置照旧 ==")
write(json.dumps(GOOD, ensure_ascii=False))
W._recovered_from = None
cfg = W.load_config()
chk("正常读取", cfg["title"] == "好的配置" and cfg["codes"] == GOOD["codes"])
chk("没触发恢复", W._recovered_from is None)

print("== 2. 配置损坏 → 从备份捞 ==")
W.snapshot_config(force=True)          # 先把好的这份存档
write('{ "title": "坏在这儿了", ')      # 截断的 JSON
W._recovered_from = None
cfg = W.load_config()
chk("读坏后自动恢复", cfg.get("title") == "好的配置", str(cfg.get("title")))
chk("自选股捞回来了", cfg.get("codes") == GOOD["codes"], str(cfg.get("codes")))
chk("持仓也捞回来了", (cfg.get("positions") or {}).get("sh600519", {}).get("cost") == 1250.0)
chk("记录了恢复来源", bool(W._recovered_from), str(W._recovered_from))
chk("坏文件原样保留（没被覆盖）",
    io.open(W.CONFIG_PATH, encoding="utf-8").read().startswith('{ "title": "坏在这儿了"'))

print("== 3. 备份也全坏 → 退回默认，不崩 ==")
for p in W.list_snapshots():
    with io.open(p, "w", encoding="utf-8") as f:
        f.write("not json at all")
W._recovered_from = None
cfg = W.load_config()
chk("返回默认配置", cfg.get("title") == W.DEFAULT_CONFIG["title"], str(cfg.get("title")))
chk("没假报恢复来源", W._recovered_from is None)

print("== 4. 坏配置不进备份（不占备份位） ==")
before = len(W.list_snapshots())
W.snapshot_config(force=True)
chk("坏 JSON 快照被拒", len(W.list_snapshots()) == before, str(len(W.list_snapshots())))

print("== 5. 挑最近的一份好的 ==")
write(json.dumps({"title": "新的好", "codes": ["sh999999"]}, ensure_ascii=False))
W.snapshot_config(force=True)
write('{"broken": ')
W._recovered_from = None
cfg = W.load_config()
chk("坏快照被跳过，用好的那份", cfg.get("title") in ("新的好", "好的配置"), str(cfg.get("title")))
chk("来源指向一份能解析的快照",
    bool(W._recovered_from) and os.path.exists(W._recovered_from), str(W._recovered_from))

print("== 6. 文件不存在时不去翻备份（全新安装） ==")
os.remove(W.CONFIG_PATH)
W._recovered_from = None
cfg = W.load_config()
chk("返回默认配置", cfg.get("title") == W.DEFAULT_CONFIG["title"])
chk("没去翻备份", W._recovered_from is None)

print("== 7. 真实配置未被改动 ==")
safety_guard.check_after(chk)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
