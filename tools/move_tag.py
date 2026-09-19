# -*- coding: utf-8 -*-
"""把版本 tag 挪到指定 commit，并保住对应的 Release 不掉草稿。

    export GH_TOKEN=<token>
    python tools/move_tag.py                 # tag 用 widget.py 里的版本号，commit 用本地 HEAD
    python tools/move_tag.py v2.1.1          # 指定 tag
    python tools/move_tag.py --sha <sha>     # 指定 commit
    python tools/move_tag.py --dry-run       # 只打印要做什么

版本号不改、只是把同一个版本的内容换成最新代码时，就得挪 tag（v2.1.0 指着的
commit 变了，但版本号还是 v2.1.0）。

★ 这活儿有个坑：**DELETE 已发布的 tag，对应的 Release 会立刻变成草稿**
（draft=True，网址变成 `releases/tag/untagged-xxxxx`，对外就是"发布没了"）。
所以下面四步必须在**同一个脚本里连着跑**：
    取 release id → 删 tag → 建 tag → 立刻 PATCH 回来
拆开跑，中间崩了就留下一个草稿 Release。

另外推完的瞬间 GitHub 还没收敛，GET release 会来一个 404 —— 取 id 那步
带重试，不然脚本直接挂在这儿，看着像"release 不见了"。

Release 正文从仓库根目录的 `.release_body.md` 读（本机草稿，已 gitignore）。
文件不存在就只挪 tag、不动正文。
"""
import io
import os
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from push_github import http, get_token, OWNER, REPO  # noqa: E402
from release_check import read_version, tag_name  # noqa: E402

BODY_FILE = os.path.join(ROOT, ".release_body.md")
DRY_RUN = "--dry-run" in sys.argv


def remote_head(token):
    """远端 main 的 HEAD。

    ★ 不能用本地 `git rev-parse HEAD` 代替：push_github.py 是在服务端现建
    commit 的，时间戳跟本地不一样，**sha 就不同**（本地 4b6e956e vs 远端
    95af9505，内容和 message 完全一样）。拿本地 sha 去建 tag 会 422
    "Object does not exist" —— 那个对象在 GitHub 上根本不存在。
    """
    code, ref = http("GET", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO),
                     token=token)
    return ref.get("object", {}).get("sha", "") if code == 200 else ""


def release_id(tag, token):
    """带重试地取 release id —— 刚推完的瞬间会 404（GitHub 还没收敛）。"""
    for i in range(6):
        code, rel = http("GET", "/repos/%s/%s/releases/tags/%s" % (OWNER, REPO, tag),
                         token=token)
        if code == 200 and rel.get("id"):
            return rel["id"]
        if code != 404:
            print("  取 release 失败：%s %s" % (code, rel.get("message", "")))
            return None
        print("  取 release -> 404（可能刚推完还没收敛），3s 后重试（第 %d/6 次）" % (i + 1))
        time.sleep(3)
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sha = ""
    if "--sha" in sys.argv:
        sha = sys.argv[sys.argv.index("--sha") + 1]
    tag = args[0] if args else tag_name(read_version())
    if not tag:
        sys.exit("读不到版本号（widget.py 里的 APP_VERSION）")
    token = get_token()
    if not sha:
        sha = remote_head(token)
    if not sha:
        sys.exit("读不到远端 main 的 HEAD，用 --sha 指定一个 commit")
    print("tag:    %s" % tag)
    print("commit: %s" % sha)

    rid = release_id(tag, token)
    print("release id: %s" % (rid or "(还没有这个 release)"))

    body = ""
    if os.path.isfile(BODY_FILE):
        body = io.open(BODY_FILE, encoding="utf-8").read()
        print("正文：   %s（%d 字）" % (os.path.basename(BODY_FILE), len(body)))

    if DRY_RUN:
        print("\n--dry-run：什么都没改。真跑会依次："
              "DELETE 旧 tag -> POST 新 tag -> PATCH release（draft=false）")
        return 0

    # 顺序不能变：先记住 id，删建之后立刻 PATCH 回去
    code, _ = http("DELETE", "/repos/%s/%s/git/refs/tags/%s" % (OWNER, REPO, tag),
                   token=token)
    print("删旧 tag -> %s" % code)

    code, out = http("POST", "/repos/%s/%s/git/refs" % (OWNER, REPO),
                     {"ref": "refs/tags/" + tag, "sha": sha}, token=token)
    print("建新 tag -> %s" % code)
    if code not in (200, 201):
        sys.exit("建 tag 失败：%s" % out.get("message"))

    if rid is None:
        print("没有对应的 release，只挪了 tag。"
              "要发版的话去网页上建一个，或者先跑一遍 push 再回来。")
        return 0

    patch = {"tag_name": tag, "draft": False, "prerelease": False}
    if body:
        patch["body"] = body
    code, out = http("PATCH", "/repos/%s/%s/releases/%s" % (OWNER, REPO, rid),
                     patch, token=token)
    print("PATCH release -> %s" % code)
    if code != 200:
        sys.exit("PATCH 失败：%s" % out.get("message"))

    print("draft=%s  tag=%s" % (out.get("draft"), out.get("tag_name")))
    print(out.get("html_url"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
