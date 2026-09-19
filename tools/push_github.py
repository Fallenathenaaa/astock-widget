# -*- coding: utf-8 -*-
"""把本地文件推到 GitHub（走 api.github.com，绕过代理对 github.com:443 的封锁）。

流程：
  1. git ls-files 拿文件清单
  2. 对每个文件 POST /git/blobs（base64）→ 拿 blob SHA
  3. POST /git/trees 把 blob 拼成树 → tree SHA
  4. POST /git/commits（parent=远端 main, tree=新树）→ commit SHA
  5. PATCH /git/refs/heads/main 指向新 commit（**非 force**）

用法：
    export GH_TOKEN=<token>
    python tools/push_github.py "commit message"
    python tools/push_github.py "commit message" --dry-run    # 只演练，不写远端

安全约定（别改回去）：
  - token **只**从环境变量 GH_TOKEN 读。以前会从 git remote URL 里抠，那等于把
    明文 token 落在 .git/config 里，一不小心就被打包带出去。
  - PATCH 用 force=False。真需要覆盖历史时手动改，脚本默认不背这个锅。
  - 提交前一刻重新读一次远端 HEAD，和我们 commit 的 parent 比对。中间要是
    有人推了新提交，直接放弃 —— 否则就是静默覆盖别人的改动。

版本号一律从 widget.py 读（release_check.read_version），**不在这里另写一份**：
三处各写各的必然会对不上（README 曾经写着 v1.4.6 而代码已经是 v1.4.7）。
"""
import os
import sys
import base64
import json
import time
import urllib.request
import urllib.error
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from release_check import read_version, tag_name  # noqa: E402

OWNER = "Fallenathenaaa"
REPO = "astock-widget"
BRANCH = "main"
API = "https://api.github.com"

DRY_RUN = "--dry-run" in sys.argv


def _should_retry(code, payload):
    """哪些失败值得重试。

    服务端错误和限流不用说。400 一般是我们的锅，不该重试 —— 但实测建 blob
    时会偶发 400 "malformed request"，同一个文件隔一秒重发就 201 了，那是
    链路上的抖动不是请求的问题。所以只对带这个词样的 400 网开一面。
    """
    if code in (429, 500, 502, 503, 504):
        return True
    if code == 400 and isinstance(payload, dict):
        return "malformed" in str(payload.get("message", "")).lower()
    return False


def http(method, path, body=None, token="", retries=3):
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            API + path,
            method=method,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "astock-widget-push",
            })
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except Exception:
                payload = {}
            if attempt < retries and _should_retry(e.code, payload):
                wait = 2 * attempt
                print("  %s %s -> %s，%ds 后重试（第 %d/%d 次）"
                      % (method, path, e.code, wait, attempt + 1, retries))
                time.sleep(wait)
                continue
            return e.code, payload
        except Exception as e:
            if attempt < retries:
                wait = 2 * attempt
                print("  %s %s -> %s，%ds 后重试（第 %d/%d 次）"
                      % (method, path, e, wait, attempt + 1, retries))
                time.sleep(wait)
                continue
            return 0, {"message": str(e)}
    return 0, {"message": "重试次数用尽"}


def get_token():
    """只从环境变量读 token。

        export GH_TOKEN=<你的 token>       # bash
        set GH_TOKEN=<你的 token>          # cmd

    不再从 git remote URL 里抠：那是明文落在 .git/config，风险太大。
    """
    env = os.environ.get("GH_TOKEN", "").strip()
    if env:
        return env
    sys.exit("没有 GH_TOKEN。请先 export GH_TOKEN=<token> 再运行。\n"
             "（token 需要 repo 权限：Contents 读写）")


def remote_head(token):
    code, ref = http("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH),
                     token=token)
    if code != 200:
        sys.exit("拿不到远端 %s：%s %s" % (BRANCH, code, ref))
    return ref["object"]["sha"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    msg_path = args[0] if args else None
    if msg_path and os.path.exists(msg_path):
        with open(msg_path, encoding="utf-8") as f:
            msg = f.read()
    elif args:
        msg = args[0]
    else:
        # 不猜：本地 git 历史可能和远端对不上（这台机器上就丢过一次 .git），
        # 用 git log 里的旧消息推上去是错得更彻底。
        sys.exit("必须给一句 commit message：\n"
                 "    python tools/push_github.py \"fix: ...\"")

    token = get_token()
    ver = read_version()
    print("repo:    %s/%s   branch: %s" % (OWNER, REPO, BRANCH))
    # 版本号从 widget.py 读：推上去的是什么版本，一眼对得上
    print("version: %s   (tag: %s)" % (ver or "(读不到)", tag_name(ver)))
    if DRY_RUN:
        print("*** DRY RUN：只演练，不会写远端 ***")

    parent_sha = remote_head(token)
    print("远端 HEAD: %s" % parent_sha)

    files = subprocess.check_output(["git", "ls-files"], cwd=ROOT).decode().splitlines()
    if not files:
        sys.exit("git ls-files 是空的 —— 什么都没推，八成是目录不对")
    print("本地文件: %d 个" % len(files))

    blobs = {}
    t0 = time.time()
    for i, path in enumerate(files, 1):
        full = os.path.join(ROOT, path)
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception as e:
            sys.exit("读 %s 失败：%s" % (path, e))
        if DRY_RUN:
            blobs[path] = ""
            continue
        code, r = http("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO),
                       {"content": base64.b64encode(data).decode(),
                        "encoding": "base64"}, token)
        if code != 201:
            sys.exit("blob 失败 %s: %s %s" % (path, code, r))
        blobs[path] = r["sha"]
        if i % 10 == 0 or i == len(files):
            print("  blobs: %d/%d  (%.1fs)" % (i, len(files), time.time() - t0))

    if DRY_RUN:
        print("tree:    (dry-run，跳过建树)")
        print("commit:  (dry-run，跳过)")
        print("\n--- commit message ---\n%s" % msg)
        print("--- 共 %d 个文件 ---" % len(files))
        print("dry-run 结束，远端未被修改。")
        return

    tree_entries = [{"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]}
                    for p in files]
    code, tree = http("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
                      {"base_tree": parent_sha, "tree": tree_entries}, token)
    if code != 201:
        sys.exit("建树失败：%s %s" % (code, tree))
    tree_sha = tree["sha"]
    print("tree:    %s" % tree_sha)

    code, commit = http("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO),
                        {"message": msg, "tree": tree_sha, "parents": [parent_sha]},
                        token)
    if code != 201:
        sys.exit("建 commit 失败：%s %s" % (code, commit))
    commit_sha = commit["sha"]
    print("commit:  %s" % commit_sha)

    # 提交前一刻再看一眼远端：中途有人推过就停手，绝不静默覆盖
    now_sha = remote_head(token)
    if now_sha != parent_sha:
        sys.exit("远端在我们干活期间变了：%s -> %s\n"
                 "已放弃更新（commit %s 已建好但没挂上去，可手动处理）。"
                 % (parent_sha, now_sha, commit_sha))

    code, r = http("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH),
                   {"sha": commit_sha, "force": False}, token)
    if code != 200:
        sys.exit("更新 %s 失败：%s %s" % (BRANCH, code, r))
    print("%s -> %s OK" % (BRANCH, commit_sha[:8]))
    print("https://github.com/%s/%s/commit/%s" % (OWNER, REPO, commit_sha))


if __name__ == "__main__":
    main()
