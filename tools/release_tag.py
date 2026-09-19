# -*- coding: utf-8 -*-
"""给当前版本**新建**一个 tag 和 Release。已经存在就直接拒绝。

    export GH_TOKEN=<token>
    python tools/release_tag.py                 # tag 用 widget.py 里的版本号
    python tools/release_tag.py v2.1.2          # 也可以显式指定
    python tools/release_tag.py --dry-run       # 只打印要做什么

★ 为什么没有"移动 tag"这个功能：
已经发出去的版本就该永久指着同一个 commit。v2.1.0 下载到的代码，昨天是这份、
明天还是这份 —— 别人拿着旧链接回去验证，看到的必须还是当时的东西。
内容要更新就发新版本号（v2.1.1、v2.1.2…），不要把同一个 tag 挪来挪去
（挪已发布的 tag 还会让对应 Release 变成草稿，网址变成 untagged-xxxxx）。

所以这个脚本只做加法：tag 已存在 → 报错退出，什么都不改。
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

    ★ 不能用本地 `git rev-parse HEAD`：push_github.py 是在服务端现建 commit 的，
    时间戳不同所以 sha 也不同（本地 4b6e956e vs 远端 95af9505，内容一样）。
    """
    code, ref = http("GET", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO),
                     token=token)
    return ref.get("object", {}).get("sha", "") if code == 200 else ""


def tag_exists(tag, token):
    """这个 tag 在远端有没有。刚推完的瞬间可能 404，多问几次。"""
    for i in range(6):
        code, _ = http("GET", "/repos/%s/%s/git/refs/tags/%s" % (OWNER, REPO, tag),
                       token=token)
        if code == 200:
            return True
        if code != 404:
            print("  查 tag 失败：HTTP %s" % code)
            return True                  # 查不清就当存在，宁可不动
        if i < 5:
            time.sleep(3)
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tag = args[0] if args else tag_name(read_version())
    if not tag:
        sys.exit("读不到版本号（widget.py 里的 APP_VERSION）")

    token = get_token()
    sha = remote_head(token)
    if not sha:
        sys.exit("读不到远端 main 的 HEAD")

    print("tag:    %s" % tag)
    print("commit: %s" % sha)

    if tag_exists(tag, token):
        sys.exit("tag %s 已经存在了。\n"
                 "发过版的 tag 不该再动 —— 请升版本号（改 widget.py 里的 "
                 "APP_VERSION）再发。" % tag)

    body = ""
    if os.path.isfile(BODY_FILE):
        body = io.open(BODY_FILE, encoding="utf-8").read()
        print("正文：   %s（%d 字）" % (os.path.basename(BODY_FILE), len(body)))
    else:
        print("正文：   （没有 %s，Release 会是个空的）"
              % os.path.basename(BODY_FILE))

    if DRY_RUN:
        print("\n--dry-run：什么都没改。真跑会依次：POST 新 tag -> POST 新 Release")
        return 0

    code, out = http("POST", "/repos/%s/%s/git/refs" % (OWNER, REPO),
                     {"ref": "refs/tags/" + tag, "sha": sha}, token=token)
    print("建 tag -> %s" % code)
    if code not in (200, 201):
        sys.exit("建 tag 失败：%s" % out.get("message"))

    code, out = http("POST", "/repos/%s/%s/releases" % (OWNER, REPO),
                     {"tag_name": tag, "name": tag, "draft": False,
                      "prerelease": False, "body": body}, token=token)
    print("建 Release -> %s" % code)
    if code not in (200, 201):
        sys.exit("建 Release 失败：%s" % out.get("message"))

    print("draft=%s  tag=%s" % (out.get("draft"), out.get("tag_name")))
    print(out.get("html_url"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
