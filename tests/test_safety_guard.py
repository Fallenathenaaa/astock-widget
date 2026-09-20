# -*- coding: utf-8 -*-
"""safety_guard 的采样能力本身要经得起验证。

它对外声明的是「真实 backups / logs 没被修改」。如果只比文件名，
某个既有 backup 被覆盖写、某个 log 被追加 —— 文件没多也没少，
只看 listdir 完全看不出来，那这个声明就是空的。

所以这里直接验 `_digest()`：文件数不变、但内容变了，必须能检出。
"""
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import safety_guard as SG  # noqa: E402

ok = fail = 0


def chk(n, c, x=""):
    global ok, fail
    if c:
        ok += 1
        print("  PASS  %s" % n)
    else:
        fail += 1
        print("  FAIL  %s   %s" % (n, x))


def write(path, text):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


tmp = tempfile.mkdtemp(prefix="astock-guard-")

print("== 目录不存在 / 空目录 ==")
chk("不存在的目录 → None",
    SG._digest(os.path.join(tmp, "no-such-dir")) is None)
empty = os.path.join(tmp, "empty")
os.makedirs(empty)
chk("空目录 → {}（不是 None，要能区分）", SG._digest(empty) == {})

print("== 内容变化必须能检出 ==")
d = os.path.join(tmp, "bak")
os.makedirs(d)
write(os.path.join(d, "a.json"), '{"title": "one"}')
before = SG._digest(d)

# 关键用例：文件数不变，只改内容
write(os.path.join(d, "a.json"), '{"title": "TWO"}')
after = SG._digest(d)
chk("文件数没变但内容变了 → digest 不同", before != after, (before, after))
chk("但文件名清单是一样的（说明 listdir 抓不到）",
    sorted(os.listdir(d)) == sorted(before) == sorted(after))

# 改回原样应该又相同
write(os.path.join(d, "a.json"), '{"title": "one"}')
chk("改回原样 → digest 又相同", SG._digest(d) == before)

print("== 增删文件也要能检出 ==")
write(os.path.join(d, "b.json"), "{}")
chk("新增文件 → digest 不同", SG._digest(d) != before)
os.remove(os.path.join(d, "b.json"))
chk("删掉之后 → 又相同", SG._digest(d) == before)

print("== 追加写也要能检出 ==")
with io.open(os.path.join(d, "a.json"), "a", encoding="utf-8") as f:
    f.write("\n// appended")
chk("追加内容 → digest 不同", SG._digest(d) != before)

print("== _read 也要能检出内容变化 ==")
f1 = os.path.join(tmp, "cfg.json")
write(f1, "AAA")
b = SG._read(f1)
write(f1, "BBB")
chk("文件内容变了 → _read 结果不同", SG._read(f1) != b)
chk("读不存在的文件 → None", SG._read(os.path.join(tmp, "nope")) is None)

print("== check_after 的项数必须和环境无关 ==")
# 这个项目在这上面栽过两次：断言写进 if 分支里，于是"有真实文件"和
# "没有真实文件"产生不同项数 —— 本机和干净 checkout 报出两个总数，
# 回传证据就没法核对。这里把项数钉死。
seen = []


def counting_chk(name, cond, extra=""):
    seen.append(name)


SG.check_after(counting_chk)
chk("check_after 固定产生 5 项（config 1 + backups 2 + logs 2）",
    len(seen) == 5, len(seen))
chk("两种分支下项数都一样（不看目录存不存在）",
    all(("backups" in n) for n in seen[1:3]) and all(("logs" in n) for n in seen[3:5]),
    seen)

print("== 真实路径常量指向仓库根 ==")
chk("REAL_CFG 在仓库根下", os.path.dirname(SG.REAL_CFG) == ROOT, SG.REAL_CFG)
chk("REAL_BAK 在仓库根下", os.path.dirname(SG.REAL_BAK) == ROOT)
chk("REAL_LOGS 在仓库根下", os.path.dirname(SG.REAL_LOGS) == ROOT)

shutil.rmtree(tmp, ignore_errors=True)
print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
