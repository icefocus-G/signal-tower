#!/bin/bash
# 信号塔 · 一键生成今天的内容
# 双击刷新.command（带终端进度）或双击 信号塔.app（无窗口，只弹通知）都会跑这个脚本。
#
# 做完的事：抓 21 个源 → 去重过滤 → 翻英文标题 → 生成 docs/offline.html → 打开浏览器。
# 不需要服务器、不需要端口，因为 offline.html 把数据内联在了页面里。

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

# GUI 启动时 PATH 很短，把常见的 Python 位置补回去
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

TTY=0
[ -t 1 ] && TTY=1

notify() {  # notify 标题 内容
  command -v osascript >/dev/null 2>&1 || return 0
  osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true
}

# 终端版直接打印；App 版被重定向到 docs/refresh.log，日志同样有内容
say() { echo "$@"; }

fail() {
  say "✗ $1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$1\" with title \"信号塔\" buttons {\"好\"} default button 1 with icon caution" >/dev/null 2>&1 || true
  fi
  exit 1
}

PY="$(command -v python3 || true)"
[ -n "$PY" ] || fail "找不到 python3。请先安装：xcode-select --install 或 brew install python3"

START=$(date +%s)
say "信号塔 · 开始抓取（$(date '+%H:%M:%S')）"
notify "信号塔" "开始抓取，请稍候…"

# 增量档：只翻标题，正文不预抓，通常十几秒到一分钟
OUT="$("$PY" build.py --out docs --articles 0 --translate title --max-age-hours 48 2>&1)"
CODE=$?

if [ $CODE -ne 0 ]; then
  say "$OUT"
  fail "抓取失败，详情见终端输出"
fi

printf '%s\n' "$OUT" | sed 's/^/  /'

# 从产物里读出条数，用于通知文案
SUMMARY="$("$PY" - <<'PY' 2>/dev/null
import json
try:
    m = json.load(open("docs/data/meta.json", encoding="utf-8"))
    cats = m.get("categories", {})
    parts = " · ".join(f"{v['label']} {v['count']}" for v in cats.values())
    print(f"{parts}|{m.get('totals',{}).get('sources_ok',0)}/{m.get('totals',{}).get('sources_total',0)}")
except Exception:
    print("|")
PY
)"
DETAIL="${SUMMARY%%|*}"
SOURCES="${SUMMARY##*|}"
ELAPSED=$(( $(date +%s) - START ))

say ""
say "✓ 完成（${ELAPSED}s）  ${DETAIL}  源 ${SOURCES} 在线"
say "  打开：$DIR/docs/offline.html"

notify "信号塔 · 已生成" "${DETAIL}　源 ${SOURCES} 在线　用时 ${ELAPSED}s"

[ "${ST_NO_OPEN:-0}" = "1" ] || open "$DIR/docs/offline.html"
