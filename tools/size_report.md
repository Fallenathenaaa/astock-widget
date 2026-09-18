# 自身体积报告

> 生成时间：2026-09-18 23:29

==============================================================
体积报告  根目录：G:\workbuddyinternationalmeet\2026-09-18-10-12-56\astock-widget
==============================================================

## 主程序

| 项目 | 数值 |
|---|---|
| `widget.py` 源文件 | 113.4 KB（2891 行） |
| ├ 有效代码行 | 2437 行 |
| ├ 注释行 | 110 行（4%） |
| └ 空行 | 344 行 |
| 编译字节码 `__pycache__/widget.cpython-313.pyc` | 170.9 KB（运行缓存，可删） |

## 目录

| 目录 | 大小 | 文件数 | 说明 |
|---|---|---|---|
| `tests/` | 30.4 KB | 7 | 回归测试，日常运行不需要 |
| `tools/` | 35.0 KB | 10 | 体积/占用/预览图脚本 |
| `screenshots/` | 1274.8 KB | 38 | 文档配图，只给 README 看 |
| `.git/` | 3536.1 KB | 130 | 版本历史 |

## 真正跑起来需要的

- `widget.py` 113.4 KB + `stocks.json` 0.5 KB = **113.9 KB**
- 不算 PySide6 运行时（那是环境依赖，不是本项目的体积）

## 各文件行数

| 文件 | 行数 | 说明 |
|---|---|---|
| `widget.py` | 2891 | 主程序 |
| `run_tests.py` | 65 | 测试运行器 |
| `demo.py` | 99 | 演示脚本 |
| `tests/__init__.py` | 0 | 测试 |
| `tests/test_backup.py` | 122 | 测试 |
| `tests/test_crash.py` | 122 | 测试 |
| `tests/test_festival.py` | 153 | 测试 |
| `tests/test_recover.py` | 96 | 测试 |
| `tests/test_regress.py` | 188 | 测试 |
| `tests/test_snap.py` | 108 | 测试 |
| `tools/measure_size.py` | 148 | 工具 |
| `tools/report_usage.py` | 90 | 工具 |
| `tools/selfcheck.py` | 130 | 工具 |
| `tools/shot_festivals.py` | 53 | 工具 |
| `tools/size_report.md` | 4 | 工具 |
| `tools/thread_probe.py` | 168 | 工具 |
| `tools/usage_report.csv` | 61 | 工具 |
| `tools/usage_report.json` | 29 | 工具 |
| `tools/usage_report.md` | 47 | 工具 |
| `tools/usage_sampler.py` | 169 | 工具 |

## 运行时内存

| 指标 | 数值 |
|---|---|
| 当前工作集 RSS | 122.4 MB |
| 峰值工作集 | 123.7 MB |
| 提交内存 Pagefile | 59.2 MB |
| 峰值提交内存 | 59.4 MB |
| 缺页次数 | 93133 |

完成。
