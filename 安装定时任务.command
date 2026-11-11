#!/bin/bash
# 安装「信号塔」的每日定时任务（launchd）
#
# 作用：每天 07:00 在后台把当天的简报整理好，你点图标时秒开，不用等。
# 电脑关机或休眠错过的，开机唤醒后系统会补跑一次。
#
# 用法：双击本文件，或在终端里 ./安装定时任务.command

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="local.signaltower.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/build"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$DIR/refresh.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ST_NO_OPEN</key>
        <string>1</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$DIR/build/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/build/launchd.err</string>
</dict>
</plist>
PLIST_EOF

# 已经装过就先卸掉，避免 bootstrap 报 "already loaded"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  echo "✓ 定时任务已安装"
else
  # 老系统的写法，兜底
  launchctl load -w "$PLIST" 2>/dev/null
  echo "✓ 定时任务已安装（传统方式）"
fi

echo "  每天 07:00 后台生成 → $DIR/docs/offline.html"
echo "  查看是否在跑：launchctl list | grep signaltower"
echo "  卸掉它：launchctl bootout gui/$(id -u)/$LABEL"
