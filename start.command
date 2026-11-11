#!/bin/bash
# 信号塔 · macOS 一键启动
# 双击本文件即可：启动本地服务并打开浏览器

cd "$(dirname "$0")" || exit 1

PORT=8787

# 端口被占用就先清理
if lsof -ti tcp:$PORT >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用，正在释放…"
  lsof -ti tcp:$PORT | xargs kill -9 2>/dev/null
  sleep 1
fi

echo "=========================================="
echo "  信号塔 · 前沿 AI / 时政 / 养生"
echo "  正在启动，首次抓取约需 1 分钟…"
echo "=========================================="

# 后台开浏览器
(sleep 3 && open "http://127.0.0.1:$PORT") &

# 前台跑服务，Ctrl+C 退出
python3 server.py

echo ""
echo "服务已停止。按任意键关闭窗口。"
read -n 1
