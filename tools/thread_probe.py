# -*- coding: utf-8 -*-
"""线程级 CPU 探针：看进程里到底是哪几个线程在烧 CPU，是不是只用了一个核。

用法：python tools/thread_probe.py [--pid PID] [--duration 90] [--interval 10]
如果进程里有一个线程吃满 100%（= 单核跑满），说明是单线程瓶颈；
如果总 CPU 很高但每个线程都不满，说明已经摊到多核了。
"""
import os
import sys
import time
import ctypes
import argparse
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TH32CS_SNAPTHREAD = 0x00000004
THREAD_QUERY_LIMITED_INFORMATION = 0x0800


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD)]


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD)]


def ft2ms(ft):
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 10000.0


def threads_of(pid):
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snap == ctypes.c_void_p(-1).value:
        return []
    try:
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(te)
        out = []
        if k32.Thread32First(snap, ctypes.byref(te)):
            while True:
                if te.th32OwnerProcessID == pid:
                    out.append(te.th32ThreadID)
                if not k32.Thread32Next(snap, ctypes.byref(te)):
                    break
        return out
    finally:
        k32.CloseHandle(snap)


def thread_times(tid):
    k32 = ctypes.windll.kernel32
    h = k32.OpenThread(THREAD_QUERY_LIMITED_INFORMATION, False, tid)
    if not h:
        return None
    try:
        c, e, k, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e),
                              ctypes.byref(k), ctypes.byref(u)):
            return ft2ms(k) + ft2ms(u)      # 内核态 + 用户态 = 总 CPU 毫秒
        return None
    finally:
        k32.CloseHandle(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=0, help="目标 PID，0 = 自动找挂件")
    ap.add_argument("--duration", type=float, default=90)
    ap.add_argument("--interval", type=float, default=10)
    a = ap.parse_args()

    pid = a.pid
    if not pid:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import widget as W
        h = W.find_widget_window(W.WIN_TITLE if hasattr(W, "WIN_TITLE") else "AShareWidget-Test")
        pid = W._window_pid(h) if h else 0
    if not pid:
        print("找不到挂件进程。用 --pid 指定。")
        return 1

    k32 = ctypes.windll.kernel32
    sys_mask = ctypes.c_ulonglong()
    proc_mask = ctypes.c_ulonglong()
    if k32.GetProcessAffinityMask(k32.GetCurrentProcess(),
                                  ctypes.byref(proc_mask), ctypes.byref(sys_mask)):
        pass
    ncpu = bin(sys_mask.value).count("1") or os.cpu_count() or 1

    print("目标 PID=%d   逻辑核=%d   采样 %.0fs / 每 %.0fs 一次" %
          (pid, ncpu, a.duration, a.interval))
    print("-" * 66)

    samples = []
    prev = {}
    t0 = time.time()
    next_at = t0 + a.interval
    while time.time() - t0 < a.duration:
        now = time.time()
        cur = {}
        for tid in threads_of(pid):
            ms = thread_times(tid)
            if ms is not None:
                cur[tid] = ms
        if prev:
            wall = (now - prev_t) * 1000.0
            deltas = {tid: cur[tid] - prev.get(tid, cur[tid])
                      for tid in cur}
            tot = sum(max(0.0, v) for v in deltas.values())
            samples.append((now - t0, wall, tot, dict(deltas)))
            top = sorted(deltas.items(), key=lambda x: -x[1])[:3]
            tops = "  ".join("T%d=%.2f%%" % (t, 100.0 * max(0.0, v) / wall)
                             for t, v in top)
            print("[%5.0fs] 进程CPU=%5.2f%%(1核基准)  线程数=%2d  最忙: %s" %
                  (now - t0, 100.0 * tot / wall, len(cur), tops))
        prev, prev_t = cur, now
        time.sleep(max(0.5, next_at - time.time()))
        next_at += a.interval

    if not samples:
        print("样本不足")
        return 1

    print("-" * 66)
    walls = [s[1] for s in samples]
    tots = [s[2] for s in samples]
    print("进程 CPU（单核=100%% 基准）: 均值 %.2f%%   峰值 %.2f%%   最低 %.2f%%" %
          (100.0 * sum(tots) / sum(walls),
           100.0 * max(t / w for _, w, t, _ in samples),
           100.0 * min(t / w for _, w, t, _ in samples)))
    print("进程 CPU（%d 核均摊）      : 均值 %.3f%%" %
          (ncpu, 100.0 * sum(tots) / (sum(walls) * ncpu)))

    # 每个线程的历史总贡献
    agg = {}
    for _, _, _, d in samples:
        for tid, v in d.items():
            agg[tid] = agg.get(tid, 0.0) + max(0.0, v)
    total_ms = sum(agg.values())
    print("\n各线程 CPU 贡献（%.0f 秒累计）：" % a.duration)
    for tid, v in sorted(agg.items(), key=lambda x: -x[1])[:8]:
        print("   线程 %-7d %8.0f ms  %5.1f%%  %s" %
              (tid, v, 100.0 * v / total_ms if total_ms else 0,
               "← 主线程（UI/重绘）" if v == max(agg.values()) else ""))

    peak = max(t / w for _, w, t, _ in samples)
    print("\n判定：", end="")
    if peak > 85:
        print("采样期间出现过接近单核跑满（%.0f%%），是单线程瓶颈。" % (peak * 100))
    else:
        print("全程峰值 %.2f%%（单核基准），没有任何线程吃满一个核 —— "
              "负载极低，用不着多核。" % (peak * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
