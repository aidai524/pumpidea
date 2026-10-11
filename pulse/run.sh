#!/usr/bin/env bash
# 一键起 Pulse demo：采集 + 构建 + 静态站点。
#   ./run.sh              持续跑，按 Ctrl-C 全停
#   ./run.sh --once       只跑一轮采集和构建（做截图/离线演示用）
set -euo pipefail
cd "$(dirname "$0")"

PY="${PY:-python3}"
PORT="${PORT:-8790}"
mkdir -p runtime

cleanup() {
  for pid in "${COLLECT_PID:-}" "${BUILD_PID:-}" "${SERVER_PID:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if [ "${1:-}" = "--once" ]; then
  "$PY" collector.py --once
  "$PY" builder.py
  echo "静态站已生成：site/（用 make serve 或 python3 -m http.server --directory site 起）"
  exit 0
fi

"$PY" collector.py &
COLLECT_PID=$!
"$PY" builder.py --loop --every 30 &
BUILD_PID=$!
"$PY" -m http.server "$PORT" --directory site --bind 127.0.0.1 &
SERVER_PID=$!

echo "Pulse 运行中 → http://127.0.0.1:${PORT}/  (Ctrl-C 停止)"
wait "$SERVER_PID"
