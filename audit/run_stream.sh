#!/usr/bin/env bash
# 以 systemd 用户服务方式常驻流式采集（不受终端会话退出影响）。
#   ./run_stream.sh          启动/重启
#   ./run_stream.sh status   查看状态
#   ./run_stream.sh stop     停止
set -euo pipefail
cd "$(dirname "$0")"
UNIT=pumpfun-stream
VENV="${VENV:-../.venv/bin/python}"

case "${1:-start}" in
  stop)
    systemctl --user stop "$UNIT" 2>/dev/null || true
    echo "已停止 $UNIT"
    ;;
  status)
    systemctl --user status "$UNIT" --no-pager | head -20
    ;;
  *)
    systemctl --user stop "$UNIT" 2>/dev/null || true
    mkdir -p runtime
    systemd-run --user --unit="$UNIT" --collect \
      --working-directory="$PWD" \
      --property=StandardOutput=append:"$PWD/runtime/stream.log" \
      --property=StandardError=append:"$PWD/runtime/stream.log" \
      --property=Restart=on-failure --property=RestartSec=5 \
      "$VENV" stream_collector.py --log-every 300
    echo "已启动 ${UNIT}；查看：$0 status"
    ;;
esac
