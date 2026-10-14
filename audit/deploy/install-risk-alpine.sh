#!/bin/sh
# Alpine/OpenRC 部署风险评分服务（③ 线）。假设 risk/ 已 rsync 到 $APP_DIR/risk。
set -eu
APP_DIR="${APP_DIR:-/opt/pumpfun-stream}"
DEST="$APP_DIR/risk"
PORT="${RISK_PORT:-8090}"

[ -f "$DEST/score_service.py" ] || { echo "缺 $DEST/score_service.py（先 rsync risk/）"; exit 1; }
[ -f "$DEST/history.sqlite3" ] || { echo "缺 $DEST/history.sqlite3（本地跑 build_history_db.py 后 rsync）"; exit 1; }

echo "==> OpenRC 服务 pumpfun-risk（:$PORT）"
cat > /etc/init.d/pumpfun-risk <<SVC
#!/sbin/openrc-run
name="pumpfun-risk"
description="pump.fun real-time risk scoring service"

command="$APP_DIR/.venv/bin/python"
command_args="score_service.py --port $PORT --creds /etc/pumpfun-web.conf"
directory="$DEST"
command_background=true
pidfile="/run/pumpfun-risk.pid"
output_log="/var/log/pumpfun-risk.log"
error_log="/var/log/pumpfun-risk.log"
respawn_delay=5
supervisor=supervise-daemon

depend() {
    need net
}
SVC
chmod +x /etc/init.d/pumpfun-risk
rc-update add pumpfun-risk default >/dev/null 2>&1 || true
rc-service pumpfun-risk restart >/dev/null 2>&1 || rc-service pumpfun-risk start

echo "==> 完成。若要挂到现有 Caddy（80/443）："
echo "   在 Caddyfile 的 catch-all 之前插入："
echo "     redir /risk /risk/ permanent"
echo "     handle_path /risk/* { reverse_proxy 172.18.0.1:$PORT }"
echo "   然后 caddy validate && caddy reload（见 deploy/README.md）"
