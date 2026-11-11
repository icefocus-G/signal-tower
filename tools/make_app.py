# -*- coding: utf-8 -*-
"""
生成「信号塔.app」——一个能双击的 macOS 应用图标。

双击它 = 抓取今天的内容 + 打开页面。不需要服务器、不需要端口。

用法：
    python3 tools/make_app.py

产物：
    信号塔.app           （放在仓库根目录，可拖到 Dock 或桌面）
    build/icon.icns      （图标，纯手绘，不依赖任何图形库）
"""
import os
import struct
import subprocess
import sys
import zlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(BASE, "build")
APP = os.path.join(BASE, "信号塔.app")

SIZE = 1024

BG = (17, 21, 28, 255)          # 深底
BAR = (245, 247, 250, 255)      # 白条
BEACON = (240, 90, 70, 255)     # 顶部红点


# ---------------- 极简绘图 ----------------

def new_canvas():
    return [[(0, 0, 0, 0)] * SIZE for _ in range(SIZE)]


def put(px, x, y, c):
    if 0 <= x < SIZE and 0 <= y < SIZE:
        px[y][x] = c


def rounded_rect(px, x0, y0, x1, y1, r, c):
    """圆角矩形，坐标含端点，逐像素判定。"""
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            cx = min(max(x, x0 + r), x1 - r)
            cy = min(max(y, y0 + r), y1 - r)
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= r * r:
                put(px, x, y, c)


def disc(px, cx, cy, r, c, aa=True):
    for y in range(cy - r - 1, cy + r + 2):
        for x in range(cx - r - 1, cx + r + 2):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 <= r * r:
                put(px, x, y, c)
            elif aa and d2 <= (r + 1) ** 2:
                # 一圈半透明，边缘不至于太硬
                put(px, x, y, (c[0], c[1], c[2], 120))


def write_png(path, px):
    raw = bytearray()
    for row in px:
        raw.append(0)  # filter: none
        for p in row:
            raw.extend(p)
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def draw_icon():
    px = new_canvas()
    # 底板：macOS 图标留白约 10%，圆角约 20%
    m, r = 100, 200
    rounded_rect(px, m, m, SIZE - m, SIZE - m, r, BG)

    # 三根递增的信号柱
    bottom = 760
    bars = [(330, 130), (462, 230), (594, 340)]
    for x, h in bars:
        rounded_rect(px, x, bottom - h, x + 76, bottom, 38, BAR)

    # 最高柱顶上的信标（压在柱顶上，不悬空）
    disc(px, 632, 414, 50, BEACON)

    write_png(os.path.join(BUILD, "icon_1024.png"), px)
    return px


def make_icns():
    os.makedirs(BUILD, exist_ok=True)
    draw_icon()
    iconset = os.path.join(BUILD, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    src = os.path.join(BUILD, "icon_1024.png")
    # iconutil 要求的固定命名
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            side = base * scale
            name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(
                ["sips", "-z", str(side), str(side), src, "--out", os.path.join(iconset, name)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    icns = os.path.join(BUILD, "icon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    print(f"  图标 → build/icon.icns ({os.path.getsize(icns)//1024} KB)")
    return icns


# ---------------- 应用包 ----------------

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>信号塔</string>
    <key>CFBundleDisplayName</key><string>信号塔</string>
    <key>CFBundleIdentifier</key><string>local.signaltower.refresh</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIconFile</key><string>icon</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSBackgroundOnly</key><false/>
</dict>
</plist>
"""

LAUNCHER = """#!/bin/bash
# 双击图标时由 Finder 调起：没有终端，用系统通知反馈进度。
# 日志写在 build/ 下，因为 build.py 会整个重建 docs/，放那里会被删掉。
cd "$(dirname "$0")/../../.." || exit 1
mkdir -p build
exec ./refresh.sh >>"build/refresh.log" 2>&1
"""


def make_app(icns_path):
    if os.path.isdir(APP):
        subprocess.run(["rm", "-rf", APP], check=True)
    macos = os.path.join(APP, "Contents", "MacOS")
    res = os.path.join(APP, "Contents", "Resources")
    os.makedirs(macos, exist_ok=True)
    os.makedirs(res, exist_ok=True)

    with open(os.path.join(APP, "Contents", "Info.plist"), "w", encoding="utf-8") as f:
        f.write(INFO_PLIST)

    launch = os.path.join(macos, "launch")
    with open(launch, "w", encoding="utf-8") as f:
        f.write(LAUNCHER)
    os.chmod(launch, 0o755)

    if icns_path and os.path.exists(icns_path):
        with open(icns_path, "rb") as s, open(os.path.join(res, "icon.icns"), "wb") as d:
            d.write(s.read())

    # 让 Finder 立刻刷新图标缓存
    subprocess.run(["touch", APP], check=False)
    print(f"  应用 → {APP}")


def main():
    os.makedirs(BUILD, exist_ok=True)
    print("生成信号塔.app")
    icns = make_icns()
    make_app(icns)

    # 顺带给终端用户一个双击入口
    cmd = os.path.join(BASE, "刷新.command")
    with open(cmd, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\ncd \"$(dirname \"$0\")\" && exec ./refresh.sh\n")
    os.chmod(cmd, 0o755)
    os.chmod(os.path.join(BASE, "refresh.sh"), 0o755)
    print(f"  终端版 → 刷新.command")
    print("\n完成。双击「信号塔.app」或「刷新.command」即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
