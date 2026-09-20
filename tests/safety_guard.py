# -*- coding: utf-8 -*-
"""「测试没碰用户的真实数据」这件事，要**开始前采样、结束后无条件比对**。

以前每个测试文件各写各的，两种写法都有问题：

写法一（总数不稳定）：

    REAL = 读一次真实 stocks.json（存在的话）
    ...跑测试...
    if REAL is None:
        print("SKIP ...")          <- 干净 checkout 少算一项
    else:
        chk("真实 stocks.json 原样", ...)

本机有 stocks.json 时总数是 910，干净 checkout 是 905 —— 同一个 commit
报出两个数字，回传证据就没法核对。测试总数必须是环境无关的稳定指标。

写法二（什么都没证明）：

    ...跑测试...
    _before = set(os.listdir(real_bak))    <- 跑完才采样
    chk("backups 没变", set(os.listdir(real_bak)) == _before)

拍完照片立刻和这张照片比，天然相等。它证明不了测试期间没动过 backups。

这个模块统一成：import 时（也就是测试跑起来之前）采样，末尾调用
`check_after(chk)` 无条件产生 3 项断言。有文件 / 没文件都算数，
"没有"本身就是一条要验的事实（干净 checkout 下不该冒出来）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

REAL_CFG = os.path.join(ROOT, "stocks.json")
REAL_BAK = os.path.join(ROOT, "backups")
REAL_LOGS = os.path.join(ROOT, "logs")


def _read(path):
    try:
        with io.open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _listing(path):
    """目录清单；目录不存在返回 None（和"存在但是空的"要区分开）。"""
    try:
        return sorted(os.listdir(path))
    except Exception:
        return None


# ---- 采样必须在 import 时发生，也就是测试真正开跑之前 ----
_cfg_before = _read(REAL_CFG)
_bak_before = _listing(REAL_BAK)
_logs_before = _listing(REAL_LOGS)


def check_after(chk):
    """在测试末尾调用，固定产生 3 项断言（两种环境项数相同）。"""
    if _cfg_before is None:
        chk("干净 checkout：真实 stocks.json 始终没被创建",
            not os.path.exists(REAL_CFG))
    else:
        chk("真实 stocks.json 内容一字未改", _read(REAL_CFG) == _cfg_before)
    if _bak_before is None:
        chk("干净 checkout：真实 backups/ 始终没被创建",
            not os.path.exists(REAL_BAK))
    else:
        chk("真实 backups/ 没多也没少文件", _listing(REAL_BAK) == _bak_before)
    if _logs_before is None:
        chk("干净 checkout：真实 logs/ 始终没被创建",
            not os.path.exists(REAL_LOGS))
    else:
        chk("真实 logs/ 没多也没少文件", _listing(REAL_LOGS) == _logs_before)
