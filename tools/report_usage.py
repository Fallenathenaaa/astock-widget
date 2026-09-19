# -*- coding: utf-8 -*-
"""把 usage_report.csv 整理成人能读的 markdown 报告。

用法：python tools/report_usage.py [csv路径]
"""
import csv
import os
import sys
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CSV = os.path.join(ROOT, "tools", "usage_report.csv")
path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

if not os.path.exists(path):
    sys.exit("找不到 %s —— 先跑 tools/usage_sampler.py" % path)

rows = list(csv.DictReader(open(path, "r", encoding="utf-8")))
if not rows:
    sys.exit("CSV 是空的")

def col(k):
    return [float(r[k]) for r in rows]

def line(k):
    v = col(k)
    return v, statistics.mean(v), max(v), min(v), v[0], v[-1]

N = len(rows)
dur = float(rows[-1]["t"])
MB = 1048576.0

print("=" * 68)
print("  30 分钟系统占用报告")
print("=" * 68)
print("\n采样 %d 个点，跨度 %.0f 秒（%.0f 分钟），每 %.0f 秒一次" %
      (N, dur, dur / 60.0, dur / max(1, N - 1)))

print("\n## CPU\n")
print("| 指标 | 均值 | 峰值 | 最低 |")
print("|---|---|---|---|")
for k, lab in (("proc_cpu_pct_per_core", "进程 CPU（单核 = 100% 基准）"),
               ("proc_cpu_pct_of_active", "进程 CPU（全部可调度核均摊）"),
               ("sys_cpu_pct", "整机系统 CPU（所有核合计）")):
    v, a, mx, mn, f, l = line(k)
    print("| %s | %.3f%% | %.3f%% | %.3f%% |" % (lab, a, mx, mn))

print("\n## 内存\n")
print("| 指标 | 起始 | 结束 | 均值 | 峰值 | 变化 |")
print("|---|---|---|---|---|---|")
for k, lab in (("rss_mb", "工作集 RSS"), ("pagefile_mb", "提交内存 Pagefile")):
    v, a, mx, mn, f, l = line(k)
    print("| %s | %.1f MB | %.1f MB | %.1f MB | %.1f MB | %+.1f MB |"
          % (lab, f, l, a, mx, l - f))
v, a, mx, mn, f, l = line("page_faults_delta")
print("| 缺页次数（每采样点增量） | %.0f | %.0f | %.0f | %.0f | — |" % (f, l, a, mx))

print("\n## 内核对象 / 线程\n")
print("| 指标 | 起始 | 结束 | 均值 | 峰值 | 变化 | 判定 |")
print("|---|---|---|---|---|---|---|")
for k, lab, tol in (("handles", "句柄数", 60),
                    ("gdi", "GDI 对象", 30),
                    ("user", "USER 对象", 30),
                    ("threads", "线程数", 8)):
    v, a, mx, mn, f, l = line(k)
    drift = l - f
    verdict = "✅ 稳定" if abs(drift) <= tol else ("⚠️ +%.0f 疑似泄漏" % drift if drift > 0 else "✅ 回落")
    print("| %s | %.0f | %.0f | %.1f | %.0f | %+.0f | %s |" % (lab, f, l, a, mx, drift, verdict))

print("\n## 结论\n")
cpu_v, cpu_a, cpu_mx, _, _, _ = line("proc_cpu_pct_per_core")
rss_v, rss_a, rss_mx, rss_mn, rss_f, rss_l = line("rss_mb")
h_v, h_a, h_mx, h_mn, h_f, h_l = line("handles")
g_v, g_a, g_mx, g_mn, g_f, g_l = line("gdi")

print("- **CPU**：进程均值 %.3f%%（单核基准），峰值 %.3f%%。"
      % (cpu_a, cpu_mx))
if cpu_mx < 5:
    print("  峰值也只有单核的 %.2f%%，全程基本「挂着不动」。" % cpu_mx)
print("- **内存**：RSS 从 %.1f MB 到 %.1f MB（%+.1f MB），峰值 %.1f MB。"
      % (rss_f, rss_l, rss_l - rss_f, rss_mx))
if rss_l <= rss_f + 5:
    print("  结束时不高于起始值，没有持续增长 —— 无内存泄漏迹象。")
else:
    print("  ⚠️ 结束时比起始高 %.1f MB，需要更长时间观察。" % (rss_l - rss_f))
print("- **句柄**：%+.0f（%.0f → %.0f）%s" % (h_l - h_f, h_f, h_l,
      "，无泄漏。" if abs(h_l - h_f) <= 60 else "，⚠️ 超出正常波动。"))
print("- **GDI**：%+.0f（%.0f → %.0f）%s" % (g_l - g_f, g_f, g_l,
      "，无泄漏（GDI 泄漏是 Qt 程序最典型的毛病，这里没有）。" if abs(g_l - g_f) <= 30 else "，⚠️ 需关注。"))
print("\n完成。")
