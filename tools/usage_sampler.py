# -*- coding: utf-8 -*-
"""挂件长时间占用采样：CPU / RSS / 线程 / 句柄 / GDI / 系统总 CPU。

    python tools/usage_sampler.py --pid <PID> --duration 1800 --interval 30

输出：
    tools/usage_report.csv    —— 每个采样点一行
    tools/usage_report.json   —— 汇总（均值/峰值）
"""
import argparse, csv, json, os, statistics, sys, time, ctypes
from ctypes import wintypes

u32, k32, p32 = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.psapi

k32.GetProcessTimes.argtypes = [wintypes.HANDLE,
    ctypes.POINTER(wintypes.LARGE_INTEGER), ctypes.POINTER(wintypes.LARGE_INTEGER),
    ctypes.POINTER(wintypes.LARGE_INTEGER), ctypes.POINTER(wintypes.LARGE_INTEGER)]
k32.GetProcessTimes.restype = wintypes.BOOL

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]
p32.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
p32.GetProcessMemoryInfo.restype = wintypes.BOOL
k32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
k32.GetProcessHandleCount.restype = wintypes.BOOL
u32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
u32.GetGuiResources.restype = wintypes.DWORD
k32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.LARGE_INTEGER),
    ctypes.POINTER(wintypes.LARGE_INTEGER), ctypes.POINTER(wintypes.LARGE_INTEGER)]
k32.GetSystemTimes.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]

TH32CS_SNAPTHREAD = 0x04
class TE(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD)]
k32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(TE)]
k32.Thread32First.restype = wintypes.BOOL
k32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(TE)]
k32.Thread32Next.restype = wintypes.BOOL
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.GetProcessAffinityMask.argtypes = [wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
k32.GetProcessAffinityMask.restype = wintypes.BOOL

def open_proc(pid):
    return k32.OpenProcess(0x1010, False, pid)

def proc_times(h):
    ct = et = kt = ut = wintypes.LARGE_INTEGER()
    k32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut))
    return kt.value + ut.value

def proc_mem(h):
    c = PMC(); c.cb = ctypes.sizeof(c)
    p32.GetProcessMemoryInfo(h, ctypes.byref(c), ctypes.sizeof(c))
    return c.WorkingSetSize, c.PeakWorkingSetSize, c.PagefileUsage, c.PageFaultCount

def proc_threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    n = 0
    if snap and snap != wintypes.HANDLE(-1).value:
        te = TE(); te.dwSize = ctypes.sizeof(te)
        if k32.Thread32First(snap, ctypes.byref(te)):
            while True:
                if te.th32OwnerProcessID == pid:
                    n += 1
                if not k32.Thread32Next(snap, ctypes.byref(te)):
                    break
        k32.CloseHandle(snap)
    return n

def proc_handles(h):
    n = wintypes.DWORD(); k32.GetProcessHandleCount(h, ctypes.byref(n)); return n.value

def proc_gui(h):
    return u32.GetGuiResources(h, 0), u32.GetGuiResources(h, 1)

def sys_cpu():
    idle = kernel = user = wintypes.LARGE_INTEGER()
    k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    return kernel.value + user.value - idle.value

def affinity_active_cores(h):
    pa = sa = ctypes.c_size_t()
    if k32.GetProcessAffinityMask(h, ctypes.byref(pa), ctypes.byref(sa)):
        return bin(pa.value).count("1")
    return os.cpu_count() or 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--duration", type=float, default=1800.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage_report.csv"))
    args = ap.parse_args()

    h = open_proc(args.pid)
    if not h:
        sys.exit("can't open pid %d" % args.pid)

    ncore_active = affinity_active_cores(h)
    print("目标 PID=%d  可调度核数=%d  总核数=%d" % (args.pid, ncore_active, os.cpu_count() or 1), flush=True)

    t0 = time.time(); cpu0 = proc_times(h); sys0 = sys_cpu()
    rows = []
    try:
        while True:
            time.sleep(args.interval)
            t1 = time.time(); cpu1 = proc_times(h); sys1 = sys_cpu()
            ws, peak_ws, pf, pfc = proc_mem(h)
            elapsed = t1 - t0
            rows.append(dict(
                t=round(elapsed, 1),
                proc_cpu_pct_per_core=round(100.0 * (cpu1 - cpu0) / (t1 - t0) / 1e7, 2),
                proc_cpu_pct_of_active=round(100.0 * (cpu1 - cpu0) / (t1 - t0) / 1e7 / ncore_active, 2),
                sys_cpu_pct=round(100.0 * (sys1 - sys0) / (t1 - t0) / 1e7, 2),
                rss_mb=round(ws / 1048576, 2),
                peak_rss_mb=round(peak_ws / 1048576, 2),
                pagefile_mb=round(pf / 1048576, 2),
                page_faults_delta=pfc,
                threads=proc_threads(args.pid),
                handles=proc_handles(h),
                gdi=proc_gui(h)[0], user=proc_gui(h)[1]))
            cpu0 = cpu1; sys0 = sys1
            r = rows[-1]
            print("[%4d/%4ds] cpu=%5.1f%%(%d核均) sys=%5.1f%% rss=%5.1fMB threads=%d handles=%d gdi=%d user=%d"
                  % (elapsed, int(args.duration), r["proc_cpu_pct_of_active"], ncore_active,
                     r["sys_cpu_pct"], r["rss_mb"], r["threads"], r["handles"], r["gdi"], r["user"]),
                  flush=True)
            if elapsed >= args.duration:
                break
    finally:
        k32.CloseHandle(h)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if rows:
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        keys = ["proc_cpu_pct_per_core", "proc_cpu_pct_of_active", "sys_cpu_pct",
                "rss_mb", "peak_rss_mb", "pagefile_mb", "threads", "handles", "gdi", "user", "page_faults_delta"]
        summary = {"pid": args.pid, "samples": len(rows),
                   "interval_s": args.interval, "duration_s": args.duration,
                   "schedulable_cores": ncore_active}
        for k in keys:
            v = [r[k] for r in rows]
            summary[k + "_avg"] = round(statistics.mean(v), 3)
            summary[k + "_max"] = round(max(v), 3)
        out_json = args.out.rsplit(".", 1)[0] + ".json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print("\n=== 汇总 ===")
        for k, v in summary.items():
            print("  %-30s  %s" % (k, v))
        print("\nCSV  -> %s\nJSON -> %s" % (args.out, out_json))

if __name__ == "__main__":
    main()
