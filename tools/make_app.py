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
APP = os.path.expanduser("~/Applications/信号塔.app")
DESKTOP = os.path.expanduser("~/Desktop/信号塔.app")

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

INFO_PLIST = ""  # 交给 osacompile 生成，不再手拼

# 双击后只做两件事：报个进度，然后把 refresh.sh 丢到后台。
# 项目路径烘死在这里——Finder 调起时 cwd 是 /，不能靠相对路径。
APPLESCRIPT = """on run
\tset proj to "__PROJECT__"
\tdo shell script "cd " & quoted form of proj & " && ST_FRESH_OPEN=1 ST_UI=1 ./refresh.sh >> build/refresh.log 2>&1 &"
end run
"""


def _plist_set(plist, key, value):
    """先 Set 再 Add——键存在与否都能落定，不用先查。"""
    for cmd in (f"Set :{key} {value}", f"Add :{key} string {value}"):
        r = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", cmd, plist],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return


def make_app(icns_path):
    """用 osacompile 生成真正的 applet。

    这里踩过坑：早前版本自己拼 bundle，把 bash 脚本当 CFBundleExecutable。
    命令行执行脚本没问题，但 Finder 双击时 LaunchServices 拿到的不是 Mach-O，
    app 直接起不来（spctl 也是 rejected）。osacompile 产出的 main 是系统编译的
    通用二进制，双击链路才正常，图标和名称再另外贴上去。
    """
    os.makedirs(os.path.dirname(APP), exist_ok=True)
    if os.path.isdir(APP):
        subprocess.run(["rm", "-rf", APP], check=True)

    src = APPLESCRIPT.replace("__PROJECT__", BASE)
    r = subprocess.run(["osacompile", "-o", APP, "-e", src],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! osacompile 失败：{r.stderr.strip()[:160]}")
        return False

    # 换成自己画的图标
    if icns_path and os.path.exists(icns_path):
        dst = os.path.join(APP, "Contents", "Resources", "applet.icns")
        with open(icns_path, "rb") as s, open(dst, "wb") as d:
            d.write(s.read())

    plist = os.path.join(APP, "Contents", "Info.plist")
    _plist_set(plist, "CFBundleName", "信号塔")
    _plist_set(plist, "CFBundleDisplayName", "信号塔")
    _plist_set(plist, "LSMinimumSystemVersion", "11.0")

    # 改过 Resources 就得重签，否则签名与内容对不上，Gatekeeper 直接拦
    subprocess.run(["rm", "-rf", os.path.join(APP, "Contents", "_CodeSignature")], check=False)
    sign = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", APP],
        capture_output=True, text=True,
    )
    if sign.returncode != 0:
        print(f"  ! 签名失败：{sign.stderr.strip()[:120]}")
    else:
        print("  已做 ad-hoc 签名")

    # 桌面上只放链接：iCloud 桌面同步会改写 .app 包，签名一破就打不开了
    subprocess.run(["ln", "-sfn", APP, DESKTOP], check=False)
    subprocess.run(["touch", APP], check=False)
    print(f"  应用 → {APP}")
    print(f"  桌面 → {DESKTOP}（指向上面的链接）")
    return True


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
    print("\n完成。双击桌面的「信号塔」，或项目里的「刷新.command」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
