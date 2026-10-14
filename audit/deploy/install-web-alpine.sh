#!/bin/sh
# Alpine 只读报表页：busybox httpd + Basic Auth + 定时重建。
# 不占用 80/443（那里通常是别的应用），默认 8080。
# 用法：sh install-web-alpine.sh [站点目录，默认 /var/www/pumpfun]
set -eu

DEST="${1:-/var/www/pumpfun}"
APP_DIR="${APP_DIR:-/opt/pumpfun-stream}"
USER_NAME="${WEB_USER:-pumpfun}"
PORT="${WEB_PORT:-8080}"
PASS="${WEB_PASS:-$(head -c 9 /dev/urandom | base64 | tr -d '/+=' | cut -c1-12)}"

echo "==> 清理之前可能装的 nginx 配置（不影响其它服务）"
rc-service nginx stop >/dev/null 2>&1 || true
rc-update del nginx default >/dev/null 2>&1 || true
rm -f /etc/nginx/http.d/pumpfun.conf 2>/dev/null || true

echo "==> 目录与凭据"
mkdir -p "$DEST"
printf 'WEB_USER=%s\nWEB_PASS=%s\nWEB_PORT=%s\n' "$USER_NAME" "$PASS" "$PORT" \
  > /etc/pumpfun-web.conf
chmod 600 /etc/pumpfun-web.conf

# 确保部署了 serve_site.py（本次同步时可能还是旧版）
[ -f "$APP_DIR/serve_site.py" ] || { echo "缺 $APP_DIR/serve_site.py（先 rsync 代码）"; exit 1; }

echo "==> OpenRC 服务（stdlib serve_site.py，零额外依赖）"
cat > /etc/init.d/pumpfun-web <<EOF
#!/sbin/openrc-run
name="pumpfun-web"
description="pumpfun static revenue report"

command="$APP_DIR/.venv/bin/python"
command_args="serve_site.py --root $DEST --port $PORT --creds /etc/pumpfun-web.conf"
directory="$APP_DIR"
command_background=true
pidfile="/run/pumpfun-web.pid"
output_log="/var/log/pumpfun-web.log"
error_log="/var/log/pumpfun-web.log"
respawn_delay=5
supervisor=supervise-daemon

depend() {
    need net
}
EOF
chmod +x /etc/init.d/pumpfun-web
rc-update add pumpfun-web default >/dev/null 2>&1 || true
rc-service pumpfun-web restart >/dev/null 2>&1 || rc-service pumpfun-web start

echo "==> 定时重建（每小时：拉数 → 定价 → 出页）"
cat > /etc/periodic/hourly/pumpfun-report <<EOF
#!/bin/sh
APP=$APP_DIR
OUT=$DEST
cd "\$APP" || exit 0
PY="\$APP/.venv/bin/python"
[ -x "\$PY" ] || PY=python3
\$PY stream_report.py --compare --top 15 >/var/log/pumpfun-report.log 2>&1
\$PY make_stream_page.py --report "\$APP/stream_report.json" --out "\$OUT/index.html" >>/var/log/pumpfun-report.log 2>&1
EOF
chmod +x /etc/periodic/hourly/pumpfun-report
rc-update add crond default >/dev/null 2>&1 || true

echo "==> 后台生成第一版页面（首次定价约数分钟）"
cd "$APP_DIR"
PY=".venv/bin/python"; [ -x "$PY" ] || PY=python3
nohup sh -c "$PY stream_report.py --compare --top 15 >/var/log/pumpfun-report.log 2>&1 && \
             $PY make_stream_page.py --report stream_report.json --out '$DEST/index.html' >>/var/log/pumpfun-report.log 2>&1 && \
             echo DONE >>/var/log/pumpfun-report.log" >/dev/null 2>&1 &

echo
echo "==> 完成"
echo "  访问：http://<VPS_IP>:$PORT/"
echo "  用户名：$USER_NAME    密码：$PASS"
echo "  （凭据在 /etc/pumpfun-web.conf，600 权限）"
