#!/usr/bin/env bash
# 在 VPS（Debian/Ubuntu，root 执行）上安装 pumpfun-stream 服务。
# 用法：sudo bash install.sh [安装目录，默认 /opt/pumpfun-stream]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-/opt/pumpfun-stream}"
USER_NAME=pumpstream
RETENTION_DAYS="${RETENTION_DAYS:-7}"

echo "==> 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync sqlite3 logrotate >/dev/null

echo "==> 创建服务用户 $USER_NAME"
id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$USER_NAME"

echo "==> 复制代码到 $DEST"
mkdir -p "$DEST"
rsync -a --delete \
  --exclude runtime --exclude '.venv' --exclude deploy \
  "$SRC"/ "$DEST"/
chown -R "$USER_NAME":"$USER_NAME" "$DEST"
mkdir -p "$DEST/runtime"
chown "$USER_NAME":"$USER_NAME" "$DEST/runtime"

echo "==> 建 venv 并装依赖"
sudo -u "$USER_NAME" python3 -m venv "$DEST/.venv"
sudo -u "$USER_NAME" "$DEST/.venv/bin/pip" install -q --upgrade pip
sudo -u "$USER_NAME" "$DEST/.venv/bin/pip" install -q -r "$DEST/requirements.txt" websockets

echo "==> 安装 systemd 服务"
cat > /etc/systemd/system/pumpfun-stream.service <<EOF
[Unit]
Description=pump.fun fee event stream collector
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$DEST
EnvironmentFile=$DEST/.env
Environment=PULSE_STORE_FIELDS=0
ExecStart=$DEST/.venv/bin/python stream_collector.py --log-every 300
Restart=always
RestartSec=5
StandardOutput=append:/var/log/pumpfun-stream.log
StandardError=append:/var/log/pumpfun-stream.log

[Install]
WantedBy=multi-user.target
EOF

echo "==> 安装保留策略（每天删 >${RETENTION_DAYS} 天 + VACUUM）"
cat > /usr/local/bin/pumpfun-stream-retention <<EOF
#!/bin/sh
DB=$DEST/runtime/stream.sqlite3
[ -f "\$DB" ] || exit 0
sqlite3 "\$DB" "DELETE FROM events WHERE ts < strftime('%s','now') - ${RETENTION_DAYS}*86400;"
sqlite3 "\$DB" "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"
EOF
chmod +x /usr/local/bin/pumpfun-stream-retention

cat > /etc/systemd/system/pumpfun-stream-retention.service <<EOF
[Unit]
Description=Prune old pump.fun stream events

[Service]
Type=oneshot
ExecStart=/usr/local/bin/pumpfun-stream-retention
EOF
cat > /etc/systemd/system/pumpfun-stream-retention.timer <<EOF
[Unit]
Description=Daily pump.fun stream retention

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/logrotate.d/pumpfun-stream <<EOF
/var/log/pumpfun-stream.log {
  daily
  rotate 7
  compress
  missingok
  notifempty
  copytruncate
}
EOF

touch /var/log/pumpfun-stream.log
chown "$USER_NAME":"$USER_NAME" /var/log/pumpfun-stream.log

systemctl daemon-reload
systemctl enable --now pumpfun-stream-retention.timer >/dev/null

echo
echo "==> 代码与依赖就绪。还差两步："
echo "  1) 写入 Alchemy 端点（600 权限）："
echo "     sudo -u $USER_NAME sh -c 'umask 077; echo ALCHEMY_RPC_URL=... > $DEST/.env'"
echo "  2) 启动："
echo "     sudo systemctl enable --now pumpfun-stream"
echo
echo "查看：sudo systemctl status pumpfun-stream && sudo journalctl -u pumpfun-stream -f"
