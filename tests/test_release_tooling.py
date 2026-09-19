# -*- coding: utf-8 -*-
"""发版工具本身的行为：tag 从哪来、半途而废怎么收场。

以前 `python tools/release_tag.py v9.9.9` 能发一个和 APP_VERSION 完全对不上的
tag（界面写着 v2.1.2、Release 挂着 v9.9.9）；建 tag 成功、建 Release 失败会
留下孤儿 tag，而脚本只会说"tag 已存在"然后退出 —— 这个版本就再也发不出去了。

这里把四种远端状态都灌进去，确认：
  没发过      -> 建 tag + 建 Release
  发全了      -> 拒绝，什么都不碰
  只有 tag    -> 只补建 Release（续完上次）
  tag 指别的  -> 拒绝（不能挪已发布的 tag）

不发网络请求：http 整个换成假的实现。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import release_check as RC  # noqa: E402
import release_tag as RT  # noqa: E402
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


HEAD = "a" * 40          # 假想中的远端 main HEAD
OTHER = "b" * 40


class FakeAPI:
    """按路径返回假响应的 http()。顺手记下每一次调用。"""

    def __init__(self, tag_sha=None, release=True, runs=None, jobs=None,
                 ref_status=200):
        self.tag_sha = tag_sha          # None = 404 不存在
        self.release = release
        self.runs = runs if runs is not None else []
        self.jobs = jobs if jobs is not None else []
        self.ref_status = ref_status
        self.calls = []

    def __call__(self, method, path, body=None, token="", retries=3):
        self.calls.append((method, path, body))
        if method == "GET" and "/git/refs/heads/main" in path:
            return 200, {"object": {"sha": HEAD}}
        if method == "GET" and "/git/refs/tags/" in path:
            if self.tag_sha is None:
                return 404, {"message": "Not Found"}
            if self.ref_status != 200:
                return self.ref_status, {"message": "boom"}
            return 200, {"object": {"sha": self.tag_sha}}
        if method == "GET" and "/releases/tags/" in path:
            return (200, {"id": 1}) if self.release else (404, {"message": "Not Found"})
        if method == "GET" and "/actions/runs?" in path:
            return 200, {"workflow_runs": self.runs}
        if method == "GET" and "/jobs?" in path:
            return 200, {"jobs": self.jobs}
        if method == "POST" and path.endswith("/git/refs"):
            return 201, {"ref": body["ref"]}
        if method == "POST" and path.endswith("/releases"):
            return 201, {"draft": False, "tag_name": body["tag_name"],
                         "html_url": "https://example.invalid/r/1"}
        return 404, {"message": "unexpected path " + path}


def run_main(argv, api):
    """跑一次 release_tag.main()，返回 (退出码, 退出信息)。正常结束退出码是 0。"""
    old_http, old_token, old_argv = RT.http, RT.get_token, sys.argv
    old_sleep = RT.time.sleep
    RT.http = api
    RT.get_token = lambda: "fake-token"
    RT.time.sleep = lambda s: None       # 别真的等 5×3 秒
    try:
        rc = RT.main(argv)
        return rc or 0, ""
    except SystemExit as e:
        return 1, str(e)
    finally:
        RT.http, RT.get_token = old_http, old_token
        RT.time.sleep = old_sleep


def posted(api, kind):
    """统计发出去的写操作：kind = "tag" / "release"。"""
    if kind == "tag":
        return [c for c in api.calls
                if c[0] == "POST" and c[1].endswith("/git/refs")]
    return [c for c in api.calls if c[0] == "POST" and c[1].endswith("/releases")]


print("== tag 名只有一个真相源：widget.py 的 APP_VERSION ==")
chk("tag_name(版本号) == APP_VERSION",
    RC.tag_name(RC.read_version()) == W.APP_VERSION,
    (RC.tag_name(RC.read_version()), W.APP_VERSION))
chk("版本号形如 vX.Y.Z",
    re.fullmatch(r"v\d+\.\d+\.\d+", RC.read_version()) is not None,
    RC.read_version())
# 以前可以 `release_tag.py v9.9.9`，于是能发一个和 APP_VERSION 对不上的 tag
rc, msg = run_main(["v9.9.9", "--no-preflight"], FakeAPI())
chk("命令行指定 tag 一律拒绝", rc == 1 and "不接受命令行" in msg, msg)
api = FakeAPI()
run_main(["v9.9.9", "--no-preflight"], api)
chk("被拒绝时一个写操作都没发", not posted(api, "tag") and not posted(api, "release"))

print("== 四种远端状态 ==")
# 1) 没发过：建 tag + 建 Release
api = FakeAPI(tag_sha=None, release=False,
              runs=[{"name": "test", "status": "completed",
                     "conclusion": "success", "id": 7}])
rc, msg = run_main(["--no-preflight"], api)
chk("没发过 → 成功", rc == 0, msg)
chk("没发过 → 建了 tag", len(posted(api, "tag")) == 1, posted(api, "tag"))
chk("没发过 → 建了 Release", len(posted(api, "release")) == 1, posted(api, "release"))
chk("tag 指向远端 HEAD",
    posted(api, "tag")[0][2]["sha"] == HEAD, posted(api, "tag"))
chk("Release 非草稿",
    posted(api, "release")[0][2]["draft"] is False, posted(api, "release"))

# 2) 发全了：拒绝，什么都不碰
api = FakeAPI(tag_sha=HEAD, release=True)
rc, msg = run_main(["--no-preflight"], api)
chk("已发布 → 拒绝", rc == 1 and "已经存在" in msg, msg)
chk("已发布 → 一个写操作都没发",
    not posted(api, "tag") and not posted(api, "release"))

# 3) 孤儿 tag（上次建了 tag 没建成 Release）：只补建 Release
api = FakeAPI(tag_sha=HEAD, release=False)
rc, msg = run_main(["--no-preflight"], api)
chk("只有 tag → 补建成功", rc == 0, msg)
chk("只有 tag → 不再建 tag（tag 不能挪）", not posted(api, "tag"), posted(api, "tag"))
chk("只有 tag → 只建 Release", len(posted(api, "release")) == 1, posted(api, "release"))

# 4) tag 指向别的 commit：拒绝（那可能是已经发出去的旧版本）
api = FakeAPI(tag_sha=OTHER, release=False)
rc, msg = run_main(["--no-preflight"], api)
chk("tag 指别的 commit → 拒绝", rc == 1 and "另一个 commit" in msg, msg)
chk("tag 指别的 commit → 不动它",
    not posted(api, "tag") and not posted(api, "release"))

print("== 查不清的时候不许动手 ==")
api = FakeAPI(tag_sha=OTHER, release=False, ref_status=500)
rc, msg = run_main(["--no-preflight"], api)
chk("tag 状态查不清 → 拒绝", rc == 1 and "查不清" in msg, msg)
chk("tag 状态查不清 → 一个写操作都没发",
    not posted(api, "tag") and not posted(api, "release"))

print("== --dry-run 什么都不能改 ==")
api = FakeAPI(tag_sha=None, release=False)
rc, msg = run_main(["--dry-run", "--no-preflight"], api)
chk("dry-run 正常结束", rc == 0, msg)
chk("dry-run 一个写操作都没发",
    not posted(api, "tag") and not posted(api, "release"), api.calls)

print("== Actions 的结论 ==")
def verdict_with(runs, jobs=()):
    old = RT.http
    RT.http = FakeAPI(runs=runs, jobs=list(jobs))
    try:
        return RT.ci_verdict(HEAD, "t")
    finally:
        RT.http = old


chk("全绿 → success",
    verdict_with([{"name": "test", "status": "completed",
                   "conclusion": "success", "id": 1}])[0] == "success")
chk("还在跑 → pending",
    verdict_with([{"name": "test", "status": "in_progress", "id": 1}])[0] == "pending")
chk("红了 → failure",
    verdict_with([{"name": "test", "status": "completed",
                   "conclusion": "failure", "id": 1}],
                 jobs=[{"name": "test (3.14)", "conclusion": "failure"}])[0] == "failure")
chk("红了会把红掉的 job 点出来",
    "3.14" in verdict_with([{"name": "test", "status": "completed",
                             "conclusion": "failure", "id": 1}],
                           jobs=[{"name": "test (3.14)", "conclusion": "failure"}])[1])
chk("没记录 → unknown（不拦，但要说清楚）",
    verdict_with([])[0] == "unknown")
# Actions 红了必须挡住发版
api = FakeAPI(tag_sha=None, release=False,
              runs=[{"name": "test", "status": "completed",
                     "conclusion": "failure", "id": 1}],
              jobs=[{"name": "test (3.14)", "conclusion": "failure"}])
rc, msg = run_main(["--no-preflight"], api)
chk("Actions 红了 → 拒绝发版", rc == 1 and "红的" in msg, msg)
chk("Actions 红了 → 连 tag 都不建", not posted(api, "tag"), posted(api, "tag"))
# 只是还没跑过：提醒，但不拦
api = FakeAPI(tag_sha=None, release=False, runs=[])
rc, msg = run_main(["--no-preflight"], api)
chk("CI 还没跑 → 不拦但建得下去", rc == 0, msg)

print("== move_tag 不该再出现（已发布的 tag 不许挪） ==")
chk("tools/ 里没有 move_tag.py",
    not os.path.exists(os.path.join(ROOT, "tools", "move_tag.py")))
rt_src = open(os.path.join(ROOT, "tools", "release_tag.py"), encoding="utf-8").read()
chk("release_tag 里没有改 ref 的 PATCH（= 挪 tag）",
    "PATCH" not in rt_src, "出现了 PATCH")

print()
print("%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
