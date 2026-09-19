# -*- coding: utf-8 -*-
"""乱码检测器：找出截图里「字体缺字」渲染出来的空心方块（□ / ▯）。

原理：字体缺失时 Qt 会把中文画成一个**空心矩形** —— 外框一圈亮像素，
中间全是背景色。正常汉字笔画饱满，不会是这种规整的空心框。

用法：python tools/detect_garbled.py [图片或目录...]
输出每张图的疑似方块数和占比，超过阈值就判「乱码」。
"""
import os
import sys
from collections import deque
from PIL import Image

# 判据：连通块要满足这些条件才算「空心方块」
MIN_SIDE = 5          # 最小边长（太小是噪点）
MAX_SIDE = 44         # 最大边长（太大是 UI 元素不是字）
RATIO_LO, RATIO_HI = 0.72, 1.38   # 宽高比要接近正方形
RING_MIN = 0.55       # 外圈亮像素密度 ≥ 这个才算有边框
CORE_MAX = 0.38       # 内部亮像素密度 ≤ 这个才算空心
BORDER = 2            # 取几像素当「外圈」


def analyse(path, thresh=130):
    im = Image.open(path).convert("L")
    w, h = im.size
    px = im.load()
    fg = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            if px[x, y] > thresh:
                fg[row + x] = 1

    seen = bytearray(w * h)
    blocks = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not fg[i] or seen[i]:
                continue
            # BFS 找一个连通块
            seen[i] = 1
            q = deque([(x, y)])
            pts = []
            while q:
                cx, cy = q.popleft()
                pts.append((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            j = ny * w + nx
                            if fg[j] and not seen[j]:
                                seen[j] = 1
                                q.append((nx, ny))
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bw = max(xs) - min(xs) + 1
            bh = max(ys) - min(ys) + 1
            if not (MIN_SIDE <= bw <= MAX_SIDE and MIN_SIDE <= bh <= MAX_SIDE):
                continue
            if not (RATIO_LO <= bw / float(bh) <= RATIO_HI):
                continue
            # 外圈 vs 内部
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            if bw <= 2 * BORDER + 1 or bh <= 2 * BORDER + 1:
                continue
            ring = core = 0
            ring_n = core_n = 0
            for py in range(y0, y1 + 1):
                for pxx in range(x0, x1 + 1):
                    k = py * w + pxx
                    v = fg[k]
                    on_edge = (pxx - x0 < BORDER or x1 - pxx < BORDER
                               or py - y0 < BORDER or y1 - py < BORDER)
                    if on_edge:
                        ring += v
                        ring_n += 1
                    else:
                        core += v
                        core_n += 1
            if ring_n == 0 or core_n == 0:
                continue
            ring_d = ring / float(ring_n)
            core_d = core / float(core_n)
            if ring_d >= RING_MIN and core_d <= CORE_MAX:
                blocks.append((x0, y0, bw, bh, round(core_d, 2)))
    return blocks, (w, h)


def main():
    args = sys.argv[1:] or ["screenshots"]
    files = []
    for a in args:
        if os.path.isdir(a):
            files += [os.path.join(a, f) for f in sorted(os.listdir(a))
                      if f.lower().endswith((".png", ".jpg"))]
        else:
            files.append(a)

    print("疑似空心方块（字体缺字）检测")
    print("=" * 72)
    bad = []
    for p in files:
        try:
            blocks, size = analyse(p)
        except Exception as e:
            print("  ERR  %-40s %s" % (os.path.basename(p), e))
            continue
        n = len(blocks)
        name = os.path.basename(p)
        if n >= 3:
            flag = "乱码!"
            bad.append((n, name))
        elif n >= 1:
            flag = "可疑"
        else:
            flag = "OK"
        print("  %-6s %-42s %3d 个  %s" % (flag, name, n, size))

    print("=" * 72)
    if bad:
        print("\n判定为乱码的图（疑似方块 >= 3 个）：")
        for n, name in sorted(bad, reverse=True):
            print("   %-42s %d 个" % (name, n))
    else:
        print("\n没有发现乱码。")


if __name__ == "__main__":
    main()