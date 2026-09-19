# -*- coding: utf-8 -*-
"""发版前三路扫描：文件名 / 文件内容 / 全部 commit message。

    python tools/privacy_scan.py

只扫**会被发布出去的东西** —— 文件清单取 `git ls-files`（已入库的），
本机那些 gitignore 掉的私有文件（LOCAL-NOTES.md、stocks.json、backups/）
天然不在范围内。以前按目录 walk 扫过一次，把没入库的本地笔记里的
`C:\\Users\\...` 报出来，白紧张一场。

查两类东西：

1) 隐私 —— token、本机用户目录、邮箱、手机号、身份证、私钥
2) 彩蛋名 —— **文件名**里不能出现节日字眼。代码按约定保留，但名字要中性，
   否则等于在仓库主页上挂了块牌子

关于"彩蛋"二字：commit message 里只查「节日彩蛋」。光是"彩蛋"命中不了 ——
收盘彩蛋是 v1.2.0 起的公开功能，README / 右键菜单 / 截图里都写着，
把它算成泄漏只会让人不敢写正常提交信息。

退出码 0 = 零命中，非 0 = 有命中（可以直接挂 CI）。
"""
import io
import os
import re
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRIVACY = [
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained token"),
    (r"AKIA[0-9A-Z]{16}", "AWS key"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI key"),
    (r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]+", "本机用户目录"),
    (r"/(?:Users|home)/[a-z][a-z0-9._-]*/", "本机用户目录(posix)"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "邮箱"),
    # 行情 fixture 里的股本 / 成交额也是 11 位数字，但被 ~ 包着，真号码不会
    (r"(?<![0-9~])1[3-9]\d{9}(?![0-9~])", "手机号"),
    (r"(?<!\d)\d{17}[\dXx](?!\d)", "身份证"),
    (r"BEGIN (?:RSA |OPENSSH |EC |DSA |)PRIVATE KEY", "私钥"),
]

FESTIVAL_NAME = [
    r"festival", r"holiday", r"midautumn", r"mid_autumn", r"mid-autumn",
    r"spring", r"national", r"lantern", r"xiaonian", r"yearend", r"year_end",
    r"christmas", r"halloween", r"thanks", r"valentine",
    r"中秋", r"春节", r"国庆", r"元宵", r"小年", r"年末",
    r"圣诞", r"万圣", r"感恩", r"情人", r"konami",
]

TEXT_EXT = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".bat", ".sh",
            ".toml", ".cfg", ".ini", ".csv"}
PLAIN_NAMES = {".gitignore", ".gitattributes", "LICENSE", "Makefile", "Dockerfile"}


def tracked_files():
    """git ls-files：已入库的文件 = 会被发布出去的文件。"""
    r = subprocess.run(["git", "ls-files"], cwd=ROOT,
                       capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return []
    return [p.strip().replace("\\", "/") for p in r.stdout.splitlines() if p.strip()]


def commit_messages():
    """全部 commit message。

    CI 上如果 checkout 没带 `fetch-depth: 0`，这里只能拿到 1 条 —— 那"扫描全部
    commit message"就是句空话。所以 main() 里会顺带报个数，只有 1 条直接失败。
    """
    r = subprocess.run(["git", "log", "--format=%H%x09%s%x09%b"], cwd=ROOT,
                       capture_output=True, encoding="utf-8", errors="replace")
    return r.stdout or ""


def commit_count():
    r = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=ROOT,
                       capture_output=True, encoding="utf-8", errors="replace")
    try:
        return int((r.stdout or "0").strip())
    except ValueError:
        return 0


def scan():
    """返回命中列表 [(类型, 位置, 片段)]。"""
    hits = []
    files = tracked_files()

    for rel in files:
        low = rel.lower()
        for pat in FESTIVAL_NAME:
            if re.search(pat, low):
                hits.append(("文件名-彩蛋", rel, pat))
        for pat, why in PRIVACY:
            if re.search(pat, rel, re.I):
                hits.append(("文件名-隐私:" + why, rel, pat))

    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        if ext not in TEXT_EXT and os.path.basename(rel) not in PLAIN_NAMES:
            continue
        full = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            continue
        try:
            txt = io.open(full, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for pat, why in PRIVACY:
            for m in re.finditer(pat, txt):
                line = txt[:m.start()].count("\n") + 1
                hits.append(("内容-隐私:" + why, "%s:%d" % (rel, line),
                             m.group()[:40]))

    msgs = commit_messages()
    for pat, why in PRIVACY:
        for m in re.finditer(pat, msgs, re.I):
            hits.append(("commit-隐私:" + why, "git log", m.group()[:40]))
    for pat in FESTIVAL_NAME + [r"节日\s*彩蛋"]:
        for m in re.finditer(pat, msgs, re.I):
            hits.append(("commit-彩蛋", "git log", m.group()[:40]))

    return files, hits


def main():
    files, hits = scan()
    n = commit_count()
    print("扫描 %d 个已入库文件 + %d 条 commit message" % (len(files), n))
    if n <= 1:
        # 浅克隆（CI 的 checkout 没带 fetch-depth: 0）会走到这里
        print("!! 只看到 %d 条 commit —— 大概率是浅克隆，"
              "「全部 commit message」不成立。给 checkout 加 fetch-depth: 0" % n)
        return 1
    if hits:
        print("命中 %d 处：" % len(hits))
        for kind, where, what in hits:
            print("   [%s] %s  -> %r" % (kind, where, what))
        return 1
    print("零命中：隐私（token / 本机路径 / 邮箱 / 手机 / 身份证 / 私钥）"
          "+ 彩蛋文件名 全部干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
