# -*- coding: utf-8 -*-
"""
信号塔 · 整理进度窗
====================
双击图标后弹一个小窗，四条进度走完，页面自动打开。

这里只负责"看得见"——真正的活还是 build.py 在干。
读它的 stdout，按 `[n/4]` 标记推进度条，最后报个条数收工。

用法（由 refresh.sh 调起）：
    python3 tools/progress_ui.py
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(BASE, "docs", "offline.html")

TOTAL = 4
STAGES = {
    1: "抓取各个站点…",
    2: "去重 · 过滤 · 打分…",
    3: "翻译英文标题…",
    4: "生成页面…",
}

BG = "#11151c"
FG = "#f5f7fa"
DIM = "#8b97a8"
ACCENT = "#f05a46"
OK = "#4ade80"


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.done = False

        root.title("信号塔")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.geometry("460x186")
        self._center()
        # 盖在其它窗口上面，不然用户根本注意不到它在跑
        root.attributes("-topmost", True)

        tk.Label(root, text="正在整理今天的简报", bg=BG, fg=FG,
                 font=("PingFang SC", 16, "bold")).pack(pady=(24, 2))
        self.stage = tk.Label(root, text="准备中…", bg=BG, fg=DIM,
                              font=("PingFang SC", 12))
        self.stage.pack()

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("ST.Horizontal.TProgressbar",
                        troughcolor="#1c2230", background=ACCENT,
                        bordercolor="#1c2230", lightcolor=ACCENT,
                        darkcolor=ACCENT, thickness=10)
        self.bar = ttk.Progressbar(root, length=380, mode="determinate",
                                   maximum=TOTAL, style="ST.Horizontal.TProgressbar")
        self.bar.pack(pady=18)

        self.foot = tk.Label(root, text="", bg=BG, fg="#5c6878",
                             font=("PingFang SC", 10))
        self.foot.pack()

    def _center(self):
        self.root.update_idletasks()
        w, h = 460, 186
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")

    # ---------- 干活 ----------

    def start(self):
        threading.Thread(target=self._work, daemon=True).start()
        self.root.after(120, self._poll)

    def _work(self):
        cmd = [sys.executable, "-u", "build.py", "--out", "docs",
               "--articles", "0", "--translate", "title", "--max-age-hours", "48"]
        try:
            p = subprocess.Popen(
                cmd, cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=dict(os.environ, PYTHONUNBUFFERED="1"),
            )
            for line in p.stdout:
                self.q.put(("line", line.rstrip()))
            self.q.put(("done", p.wait()))
        except Exception as e:                      # noqa: BLE001
            self.q.put(("error", f"{type(e).__name__}: {e}"))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "line":
                    self._on_line(payload)
                elif kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._fail(payload)
        except queue.Empty:
            pass
        if not self.done:
            self.root.after(120, self._poll)

    def _on_line(self, line):
        s = line.strip()
        if not s:
            return
        if s.startswith("[") and "/" in s.split("]", 1)[0]:
            head, _, rest = s.partition("]")
            try:
                n = int(head[1:].split("/")[0])
            except ValueError:
                return
            self.bar["value"] = max(0, min(n, TOTAL))
            self.stage.config(text=STAGES.get(n, "处理中…"))
            self.foot.config(text=rest.strip()[:56])
            return
        self.foot.config(text=s[:56])

    def _finish(self, code):
        self.done = True
        if code != 0:
            self._fail("构建失败，详情见 build/refresh.log")
            return

        detail = ""
        try:
            with open(os.path.join(BASE, "docs", "data", "meta.json"), encoding="utf-8") as f:
                m = json.load(f)
            cats = m.get("categories", {})
            detail = " · ".join(f"{v['label']} {v['count']}" for v in cats.values())
        except Exception:                           # noqa: BLE001
            pass

        self.bar["value"] = TOTAL
        self.stage.config(text="✓ 整理完成，正在打开…", fg=OK)
        self.foot.config(text=detail)

        if os.path.exists(PAGE) and os.environ.get("ST_NO_OPEN") != "1":
            subprocess.Popen(["open", PAGE])
        self.root.after(1300, self.root.destroy)

    def _fail(self, msg):
        self.done = True
        self.stage.config(text="✗ " + msg, fg="#f87171")
        self.root.after(5000, self.root.destroy)


def main():
    try:
        root = tk.Tk()
    except Exception as e:                          # noqa: BLE001
        print(f"无法显示进度窗：{e}", file=sys.stderr)
        return 1
    app = App(root)
    app.start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
