# -*- coding: utf-8 -*-
"""给当前版本**新建**一个 tag 和 Release。已经发布过就直接拒绝。

    export GH_TOKEN=<token>
    python tools/release_tag.py                 # tag 只能来自 widget.py 的 APP_VERSION
    python tools/release_tag.py --dry-run       # 只打印要做什么
    python tools/release_tag.py --no-preflight  # 跳过本地发版检查（不建议）

★ 为什么没有"移动 tag"这个功能：
已经发出去的版本就该永久指着同一个 commit。v2.1.0 下载到的代码，昨天是这份、
明天还是这份 —— 别人拿着旧链接回去验证，看到的必须还是当时的东西。
内容要更新就发新版本号（v2.1.1、v2.1.2…），不要把同一个 tag 挪来挪去
（挪已发布的 tag 还会让对应 Release 变成草稿，网址变成 untagged-xxxxx）。

★ tag 名不接受命令行参数：
以前可以 `python tools/release_tag.py v9.9.9`，于是能发一个和 widget.py 里
APP_VERSION 完全对不上的 tag —— 界面"关于"写着 v2.1.2、Release 挂着 v9.9.9，
下载回去的人根本不知道自己拿到的是什么。版本号只有一个真相源：APP_VERSION。

★ 先查状态再动手（幂等）：
建 tag 成功、建 Release 失败会留下一个孤儿 tag；老版本遇到孤儿 tag 只会说
"tag 已存在"然后退出，于是这个版本**永远发不出去**（又不能挪 tag）。
现在会先看四个状态，孤儿就只补建 Release，把半途而废的那次续完。
"""
import io
import os
import re
import sys
import time
import subprocess

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from push_github import http, get_token, OWNER, REPO  # noqa: E402
from release_check import read_version, tag_name  # noqa: E402

BODY_FILE = os.path.join(ROOT, ".release_body.md")
PY = sys.executable

# 发版门槛只认这个 workflow —— 对应 .github/workflows/test.yml 里的 `name:`
# 改了 workflow 的名字，这里要跟着改（宁可显式，不要"随便找一个 run"）
TEST_WORKFLOW = "test"


def remote_head(token):
    """远端 main 的 HEAD。

    ★ 不能用本地 `git rev-parse HEAD`：push_github.py 是在服务端现建 commit 的，
    时间戳不同所以 sha 也不同（本地 4b6e956e vs 远端 95af9505，内容一样）。
    """
    code, ref = http("GET", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO),
                     token=token)
    return ref.get("object", {}).get("sha", "") if code == 200 else ""


def tag_sha(tag, token, retry_on_404=False):
    """远端这个 tag 指向哪个 commit；不存在返回 ""，查不清返回 None。

    retry_on_404 只在**我们刚 POST 完 tag** 时才需要：GitHub 的 ref 有一小段
    收敛时间，立刻查可能还 404。

    发版之前（还没写任何东西）404 就是不存在，绝不多等 —— 那 15 秒既没意义，
    又白白把「读到 main SHA」到「真正打 tag」之间的 TOCTOU 窗口拉长。
    """
    tries = 6 if retry_on_404 else 1
    for i in range(tries):
        code, out = http("GET", "/repos/%s/%s/git/refs/tags/%s" % (OWNER, REPO, tag),
                         token=token)
        if code == 200:
            return out.get("object", {}).get("sha", "")
        if code == 404:
            if retry_on_404 and i < tries - 1:
                time.sleep(3)          # 刚推完的瞬间可能还查不到
                continue
            return ""
        print("  查 tag 失败：HTTP %s" % code)
        return None                    # 查不清 ≠ 不存在，别乱建
    return ""


def confirm_main(sha, token, when):
    """把远端 main 和发版开始时读到的 SHA 对一遍，变了就停止。

    从「读到 main = A」到「真正 POST tag」之间隔着查 tag、查 Release、读正文、
    查 CI 好几步。这中间另一个 push 可能把 main 推到 B。不复核的话脚本会自己
    制造出一个不一致：

        main = B，但 v2.1.3 tag 打在 A 上

    Release 看起来是"最新版"，实际不是当前 main。push_github.py 提交前一刻
    会重读 remote HEAD，发版这一步也得一样。
    """
    now = remote_head(token)
    if not now:
        sys.exit("%s：读不到远端 main 的 HEAD" % when)
    if now != sha:
        sys.exit("%s：main 已经变了\n    %s（开始时）-> %s（现在）\n"
                 "重跑一次发版流程 —— tag 只能打在当前的 main 上。" % (when, sha, now))
    return now


def release_exists(tag, token):
    """这个 tag 对应的 Release 有没有建好。"""
    code, _ = http("GET", "/repos/%s/%s/releases/tags/%s" % (OWNER, REPO, tag),
                   token=token)
    if code == 200:
        return True
    if code == 404:
        return False
    print("  查 Release 失败：HTTP %s（按「存在」处理，宁可不动）" % code)
    return True


def ci_verdict(sha, token):
    """远端这个 commit 的 Actions 跑完了没有、过了没有。

    返回 (结论, 说明)。查不到就返回 ("unknown", ...)：**网络问题不该挡住发版**，
    但要明确说出来，让人自己去看一眼。
    """
    code, out = http("GET", "/repos/%s/%s/actions/runs?head_sha=%s&per_page=50"
                     % (OWNER, REPO, sha), token=token)
    if code != 200:
        return "unknown", "查不到 Actions 记录（HTTP %s）" % code
    # 只认 TEST_WORKFLOW。今天仓库里只有它一个，所以「找不到就退到任意 run」
    # 看起来无害 —— 但将来多了 docs / lint / screenshot / release 之类，
    # 拿一个不相干的 workflow 的结论当发版门槛，而且很难被发现。找不到就说找不到。
    runs = [r for r in out.get("workflow_runs", [])
            if r.get("name") == TEST_WORKFLOW]
    if not runs:
        return "unknown", "没找到 %s workflow 在这个 commit 上的运行记录" % TEST_WORKFLOW
    run = runs[0]
    if run.get("status") != "completed":
        return "pending", "Actions 还在跑（%s）" % run.get("status")
    if run.get("conclusion") == "success":
        return "success", "Actions 全绿"
    # 挂了就把红掉的 job 点出来，省得再去网页上翻
    bad = []
    code2, jobs = http("GET", "/repos/%s/%s/actions/runs/%s/jobs?per_page=50"
                       % (OWNER, REPO, run.get("id")), token=token)
    if code2 == 200:
        bad = [j.get("name") for j in jobs.get("jobs", [])
               if j.get("conclusion") not in (None, "success", "skipped")]
    return "failure", "Actions 红了：%s" % ("、".join(str(b) for b in bad)
                                        or run.get("conclusion"))


def preflight():
    """发版前把"发出去才发现"的那类问题挡在本地。不过就不许往后走。"""
    print("== 发版检查 ==")
    r = subprocess.run([PY, "tools/release_check.py"], cwd=ROOT,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("\n发版检查没过，先修好再发。"
                 "（确认无误非要发，加 --no-preflight）")
    print()


def main(argv=None):
    """argv 默认取 sys.argv[1:]。参数在函数里解析（不在 import 时），
    这样测试可以直接塞一组 argv 进来，不用去改进程的命令行。"""
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    dry_run = "--dry-run" in argv
    no_preflight = "--no-preflight" in argv

    extra = [a for a in argv if not a.startswith("--")]
    if extra:
        sys.exit("不接受命令行指定 tag 名（收到：%s）。\n"
                 "tag 必须等于 widget.py 里的 APP_VERSION —— 想换版本号就改那里，"
                 "别在这儿另起一套。" % " ".join(extra))

    ver = read_version()
    tag = tag_name(ver)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag or ""):
        sys.exit("读到的版本号不像 vX.Y.Z：%r（widget.py 里的 APP_VERSION）" % ver)

    if not no_preflight:
        preflight()

    token = get_token()
    sha = remote_head(token)
    if not sha:
        sys.exit("读不到远端 main 的 HEAD")

    print("tag:    %s（来自 widget.py 的 APP_VERSION）" % tag)
    print("commit: %s" % sha)

    have_tag = tag_sha(tag, token)
    if have_tag is None:
        sys.exit("tag 状态查不清，不敢动手。")

    if have_tag:
        if have_tag != sha:
            sys.exit("tag %s 已经指向另一个 commit（%s）。\n"
                     "发过的 tag 不该再动 —— 请升 APP_VERSION 发新版本。" % (tag, have_tag))
        if release_exists(tag, token):
            sys.exit("tag %s 和它的 Release 都已经存在了。\n"
                     "这个版本发过了。要更新内容就升 APP_VERSION 再发。" % tag)
        # 半途而废留下的孤儿 tag：上次建了 tag 没建成 Release，这次续上
        print("\n发现孤儿 tag：%s 已经指向当前 commit，但 Release 没建成。"
              "\n只补建 Release，不动 tag。" % tag)
    else:
        print("tag 还不存在，会新建。")

    body = ""
    if os.path.isfile(BODY_FILE):
        body = io.open(BODY_FILE, encoding="utf-8").read()
        print("正文：   %s（%d 字）" % (os.path.basename(BODY_FILE), len(body)))
    else:
        print("正文：   （没有 %s，Release 会是个空的）"
              % os.path.basename(BODY_FILE))

    verdict, why = ci_verdict(sha, token)
    print("CI：     %s（%s）" % (verdict, why))
    if verdict == "failure":
        sys.exit("\n这个 commit 的 Actions 是红的，修好再发。")
    if verdict != "success":
        print("         注意：没能确认 Actions 是绿的，建议自己去网页上看一眼。")

    if dry_run:
        print("\n--dry-run：什么都没改。真跑会%s"
              % ("只 POST 新 Release（tag 已经有了）" if have_tag
                 else "依次 POST 新 tag -> POST 新 Release"))
        print("（真跑时还会在写之前再核一次 main 是不是还是 %s）" % sha[:8])
        return 0

    # ★ 写之前最后再确认一次 main 没变。上面这一串查询可能花了不少时间，
    # 这期间另一个 push 完全来得及把 main 推走。
    confirm_main(sha, token, "建 tag 前")

    if not have_tag:
        code, out = http("POST", "/repos/%s/%s/git/refs" % (OWNER, REPO),
                         {"ref": "refs/tags/" + tag, "sha": sha}, token=token)
        print("建 tag -> %s" % code)
        if code not in (200, 201):
            sys.exit("建 tag 失败：%s\n"
                     "（如果这里失败而 Release 也没建，下次重跑会自动续上）"
                     % out.get("message"))
        # tag 建完之后才需要容忍 eventual consistency：刚写的 ref 可能还查不到
        wrote = tag_sha(tag, token, retry_on_404=True)
        if wrote and wrote != sha:
            sys.exit("刚建好的 tag 指向 %s，不是我们想要的 %s —— 停下，"
                     "别再往下建 Release。" % (wrote, sha))

    # 建 Release 之前再核一次：tag 那一步之后 main 也可能已经动了
    confirm_main(sha, token, "建 Release 前")

    code, out = http("POST", "/repos/%s/%s/releases" % (OWNER, REPO),
                     {"tag_name": tag, "name": tag, "draft": False,
                      "prerelease": False, "body": body}, token=token)
    print("建 Release -> %s" % code)
    if code not in (200, 201):
        sys.exit("建 Release 失败：%s\n"
                 "（tag %s 已经建好了，重跑这个脚本会只补建 Release）"
                 % (out.get("message"), tag))

    print("draft=%s  tag=%s" % (out.get("draft"), out.get("tag_name")))
    print(out.get("html_url"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
