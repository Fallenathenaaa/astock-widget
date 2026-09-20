# -*- coding: utf-8 -*-
"""配置自动备份：生成/去重/轮转/恢复/坏文件"""
"""配置自动备份验证。临时目录跑，绝不碰真实 stocks.json。"""
import io
import json
import os
import sys
import tempfile
import time

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


tmp = tempfile.mkdtemp(prefix="astock-bak-")
W.CONFIG_PATH = os.path.join(tmp, "stocks.json")


def write(d):
    with io.open(W.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=2))


def read():
    with io.open(W.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


print("== 1. 基础快照 ==")
write({"title": "A", "codes": ["sh600519"], "pos": [10, 20]})
p1 = W.snapshot_config()
chk("首次快照生成", bool(p1) and os.path.exists(p1), str(p1))
chk("快照落在配置同级的 backups/", os.path.basename(os.path.dirname(p1)) == "backups", p1)
with io.open(p1, encoding="utf-8") as f:
    chk("快照内容 = 当时配置", json.load(f)["title"] == "A")

print("== 2. 内容没变不重复存 ==")
chk("无变化 → 不存", W.snapshot_config() is None)

print("== 3. 只挪位置不算实质变化 ==")
write({"title": "A", "codes": ["sh600519"], "pos": [300, 400]})
chk("仅 pos 变化 → 不存", W.snapshot_config() is None)

print("== 4. 实质变化就存 ==")
write({"title": "A", "codes": ["sh600519", "sz000001"], "pos": [300, 400]})
p2 = W.snapshot_config()
chk("codes 变化 → 存", bool(p2) and p2 != p1)
chk("已存 2 份", len(W.list_snapshots()) == 2, str(W.list_snapshots()))

print("== 5. force 强制存 ==")
n0 = len(W.list_snapshots())
p3 = W.snapshot_config(force=True)
chk("force 一定存", bool(p3) and len(W.list_snapshots()) == n0 + 1)

print("== 6. list_snapshots 从新到旧 ==")
lst = W.list_snapshots()
chk("按生成时间倒序", lst == sorted(lst, key=W._snap_key, reverse=True), str(lst))
chk("最新的是刚才那份", os.path.basename(lst[0]) == os.path.basename(p3), lst[0])

print("== 7. 轮转：只留最近 N 份 ==")
W.BACKUP_KEEP = 4
for i in range(10):
    write({"title": "T%d" % i, "codes": ["sh600519"]})
    W.snapshot_config(force=True)
    time.sleep(0.01)
lst = W.list_snapshots()
chk("数量被裁到 BACKUP_KEEP=4", len(lst) == 4, str(len(lst)))
newest = json.load(io.open(lst[0], encoding="utf-8"))
chk("保留的是最新的（T9）", newest.get("title") == "T9", newest.get("title"))
oldest = json.load(io.open(lst[-1], encoding="utf-8"))
chk("最旧的是 T6", oldest.get("title") == "T6", oldest.get("title"))
W.BACKUP_KEEP = 30

print("== 8. 恢复 ==")
write({"title": "现在的", "codes": ["sh999999"], "positions": {}})
target = W.list_snapshots()[2]
with io.open(target, encoding="utf-8") as f:
    want = json.load(f)
chk("恢复成功", W.restore_snapshot(target) is True)
chk("内容已回滚", read().get("title") == want.get("title"), read().get("title"))
after = W.list_snapshots()
chk("覆盖前自动存了一份当前的", len(after) >= 5)
found = [p for p in after if json.load(io.open(p, encoding="utf-8")).get("title") == "现在的"]
chk("能找回被覆盖前的状态", bool(found))

print("== 9. 坏文件不能把配置写坏 ==")
bad = os.path.join(tmp, "backups", "stocks-bad.json")
with io.open(bad, "w", encoding="utf-8") as f:
    f.write("{ this is not json")
before = io.open(W.CONFIG_PATH, encoding="utf-8").read()
chk("坏快照被拒", W.restore_snapshot(bad) is False)
chk("配置未被破坏", io.open(W.CONFIG_PATH, encoding="utf-8").read() == before)
chk("不存在的路径也返回 False", W.restore_snapshot(os.path.join(tmp, "nope.json")) is False)

print("== 10. save_config 自动带快照 ==")
n0 = len(W.list_snapshots())
W.save_config({"title": "via save_config", "codes": ["sh600519"]})
chk("save_config 触发快照", len(W.list_snapshots()) == n0 + 1, str(len(W.list_snapshots())))

print("== 11. 真实配置没被碰 ==")
safety_guard.check_after(chk)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
