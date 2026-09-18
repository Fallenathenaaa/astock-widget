# -*- coding: utf-8 -*-
"""把本地 main 分支推到 GitHub（走 api.github.com，绕过 github.com:443 代理封）。

流程：
  1. git ls-files 拿文件清单
  2. 对每个文件 POST /git/blobs（base64）→ 拿 blob SHA
  3. POST /git/trees 把 blob 拼成树 → tree SHA
  4. POST /git/commits（parent=远端 main, tree=新树）→ commit SHA
  5. PATCH /git/refs/heads/main 指向新 commit

用法：python tools/push_github.py [commit_message]
      （token 从 git remote URL 里自动取，不需要单独给）
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
os.chdir(ROOT)

OWNER = "Fallenathenaaa"
REPO = "astock-widget"
BRANCH = "main"
API = "https://api.github.com"


def http(method, path, body=None, token=""):
    req = urllib.request.Request(
        API + path,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "astock-widget-push",
        })
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    else:
        data = None
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def get_token():
    out = subprocess.check_output(["git", "remote", "get-url", "origin"]).decode().strip()
    if "@" not in out:
        sys.exit("remote URL 不带 token")
    return out.split("//", 1)[1].split("@", 1)[0]


def main():
    token = get_token()
    print("repo: %s/%s   branch: %s" % (OWNER, REPO, BRANCH))

    code, ref = http("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH), token=token)
    if code != 200:
        sys.exit("拿不到远端 main：%s %s" % (code, ref))
    parent_sha = ref["object"]["sha"]
    print("远端 HEAD:  %s" % parent_sha)

    files = subprocess.check_output(["git", "ls-files"], cwd=ROOT).decode().splitlines()
    print("本地文件: %d 个" % len(files))

    blobs = {}
    t0 = time.time()
    for i, path in enumerate(files, 1):
        full = os.path.join(ROOT, path)
        try:
            data = open(full, "rb").read()
        except Exception as e:
            sys.exit("读 %s 失败：%s" % (path, e))
        b64 = base64.b64encode(data).decode()
        code, r = http("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO),
                       {"content": b64, "encoding": "base64"}, token)
        if code != 201:
            sys.exit("blob 失败 %s: %s %s" % (path, code, r))
        blobs[path] = r["sha"]
        if i % 10 == 0 or i == len(files):
            print("  blobs: %d/%d  (%.1fs)" % (i, len(files), time.time() - t0))

    tree_entries = [{"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]}
                    for p in files]
    code, tree = http("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
                      {"base_tree": parent_sha, "tree": tree_entries}, token)
    if code != 201:
        sys.exit("建树失败：%s %s" % (code, tree))
    tree_sha = tree["sha"]
    print("tree:    %s" % tree_sha)

    msg_path = sys.argv[1] if len(sys.argv) > 1 else None
    if msg_path and os.path.exists(msg_path):
        msg = open(msg_path, encoding="utf-8").read()
    elif len(sys.argv) > 1:
        msg = sys.argv[1]
    else:
        msg = subprocess.check_output(
            ["git", "log", "-1", "--format=%s%n%n%b"], cwd=ROOT).decode().strip()

    code, commit = http("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO),
                        {"message": msg, "tree": tree_sha, "parents": [parent_sha]}, token)
    if code != 201:
        sys.exit("建 commit 失败：%s %s" % (code, commit))
    commit_sha = commit["sha"]
    print("commit:  %s" % commit_sha)

    code, r = http("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH),
                   {"sha": commit_sha, "force": True}, token)
    if code != 200:
        sys.exit("更新 main 失败：%s %s" % (code, r))
    print("main -> %s OK" % commit_sha[:8])
    print("https://github.com/%s/%s/commit/%s" % (OWNER, REPO, commit_sha))


if __name__ == "__main__":
    main()