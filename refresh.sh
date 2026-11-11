#!/bin/bash
# 信号塔 · 生成今天的简报
#
# 三个入口共用这一个脚本，靠环境变量区分：
#   双击 App        ST_FRESH_OPEN=1 ST_UI=1   今天已有就秒开，没有就弹进度窗
#   双击 .command   什么都不设                 终端里跑完整流程
#   launchd 定时     ST_SKIP_FRESH=1 ST_NO_OPEN=1   今天已有就静默退出
#
# 做完的事：抓 21 个源 → 去重过滤 → 翻英文标题 → 生成 docs/offline.html。
# 不需要服务器、不需要端口，因为 offline.html 把数据内联在了页面里。

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

# GUI 启动时 PATH 很短，把常见的 Python 位置补回去
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

say() { echo "$@"; }

notify() {  # notify 标题 内容
  command -v osascript >/dev/null 2>&1 || return 0
  osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true
}

fail() {
  say "✗ $1"
  # 后台跑的时候别弹窗，用户不在电脑前也没意义
  if [ "${ST_NO_OPEN:-0}" != "1" ] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$1\" with title \"信号塔\" buttons {\"好\"} default button 1 with icon caution" >/dev/null 2>&1 || true
  fi
  exit 1
}

# ---- 并发锁 ----
# 开机瞬间 RunAtLoad 与 9:05 的定时可能同时醒，抓两遍没必要，还会互相踩文件。
LOCK="/tmp/signaltower.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$LOCK_AGE" -gt 900 ]; then          # 超过 15 分钟当作上次异常退出的残锁
    rm -rf "$LOCK" 2>/dev/null
    mkdir "$LOCK" 2>/dev/null || true
  else
    say "已有一次整理在进行中，本次跳过"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# 每日任务没装就顺手装一次——装失败也不耽误这次生成
PLIST="$HOME/Library/LaunchAgents/local.signaltower.daily.plist"
if [ ! -f "$PLIST" ] && ! launchctl list 2>/dev/null | grep -q signaltower; then
  bash "$DIR/安装定时任务.command" >/dev/null 2>&1 || true
fi

PY="$(command -v python3 || true)"
[ -n "$PY" ] || fail "找不到 python3。请先安装：xcode-select --install 或 brew install python3"

START=$(date +%s)
PAGE="$DIR/docs/offline.html"

# 今天的产物算不算"新鲜"：同一天，且不超过 12 小时
is_fresh() {
  [ -f "$PAGE" ] || return 1
  DAY="$(date -r "$PAGE" '+%Y-%m-%d' 2>/dev/null || echo '')"
  AGE=$(( $(date +%s) - $(stat -f %m "$PAGE" 2>/dev/null || echo 0) ))
  [ "$DAY" = "$(date '+%Y-%m-%d')" ] && [ "$AGE" -lt 43200 ]
}

# ---- 定时任务：今天已经有了就什么都不做 ----
if [ "${ST_SKIP_FRESH:-0}" = "1" ] && is_fresh; then
  say "✓ 今天 $(date -r "$PAGE" '+%H:%M') 已生成过，跳过"
  exit 0
fi

# ---- 双击 App：今天已经有了就直接打开，别让用户干等 ----
if [ "${ST_FRESH_OPEN:-0}" = "1" ] && is_fresh; then
  say "✓ 今天 $(date -r "$PAGE" '+%H:%M') 已整理好，直接打开（不再重抓）"
  notify "信号塔" "今天 $(date -r "$PAGE" '+%H:%M') 的简报已就绪"
  [ "${ST_NO_OPEN:-0}" = "1" ] || open "$PAGE"
  exit 0
fi

# ---- 真要现抓：App 双击走图形进度窗 ----
if [ "${ST_UI:-0}" = "1" ]; then
  rmdir "$LOCK" 2>/dev/null            # 交给进度窗，锁先放掉
  exec "$PY" tools/progress_ui.py
fi

say "信号塔 · 开始抓取（$(date '+%H:%M:%S')）"
[ "${ST_NO_OPEN:-0}" = "1" ] || notify "信号塔" "开始整理今天的简报，请稍候…"

# 增量档：只翻标题，正文不预抓，通常十几秒
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
say "  打开：$PAGE"

notify "信号塔 · 已生成" "${DETAIL}　源 ${SOURCES} 在线　用时 ${ELAPSED}s"

[ "${ST_NO_OPEN:-0}" = "1" ] || open "$PAGE"
