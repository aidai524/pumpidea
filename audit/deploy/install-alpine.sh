#!/bin/sh
# Alpine/OpenRC 版安装（LXC 容器适用；systemd 版见 install.sh）。
# 用法：sh install-alpine.sh [安装目录，默认 /opt/pumpfun-stream]
set -eu

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-/opt/pumpfun-stream}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

echo "==> 安装依赖（apk）"
apk add --no-cache python3 py3-pip rsync sqlite >/dev/null

echo "==> 同步代码到 $DEST"
mkdir -p "$DEST/runtime"
rsync -a --delete --exclude runtime --exclude .venv --exclude deploy \
      "$SRC"/ "$DEST"/

echo "==> venv + 依赖"
[ -d "$DEST/.venv" ] || python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -q --upgrade pip
"$DEST/.venv/bin/pip" install -q websockets

echo "==> 环境文件（若源目录带 .env 则复制，否则生成模板）"
if [ -f "$SRC/.env" ]; then
  install -m 600 "$SRC/.env" "$DEST/.env"
else
  [ -f "$DEST/.env" ] || {
    printf 'ALCHEMY_RPC_URL=\n' > "$DEST/.env"
    chmod 600 "$DEST/.env"
  }
fi
# 服务器上默认不存 fields JSON（体积降一个量级）
if ! grep -q '^PULSE_STORE_FIELDS=' "$DEST/.env"; then
  # 注意：.env 最后一行可能没有换行符，直接 echo >> 会把变量粘到值上
  [ -n "$(tail -c1 "$DEST/.env" 2>/dev/null)" ] && echo >> "$DEST/.env"
  echo 'PULSE_STORE_FIELDS=0' >> "$DEST/.env"
fi

echo "==> OpenRC 服务"
cat > /etc/init.d/pumpfun-stream <<EOF
#!/sbin/openrc-run
name="pumpfun-stream"
description="pump.fun fee event stream collector"

command="$DEST/.venv/bin/python"
command_args="stream_collector.py --log-every 300"
command_user="root"
directory="$DEST"
pidfile="/run/pumpfun-stream.pid"
command_background=true
output_log="/var/log/pumpfun-stream.log"
error_log="/var/log/pumpfun-stream.log"
respawn_delay=5
supervisor=supervise-daemon

depend() {
    need net
    after firewall
}

start_pre() {
    if [ -f /etc/conf.d/pumpfun-stream ]; then
        set -a
        . /etc/conf.d/pumpfun-stream
        set +a
    fi
}
EOF
chmod +x /etc/init.d/pumpfun-stream

# 环境变量入口（ALCHEMY_RPC_URL / PULSE_STORE_FIELDS）
if [ ! -f /etc/conf.d/pumpfun-stream ]; then
  sed -n 's/^\(ALCHEMY_RPC_URL\|PULSE_STORE_FIELDS\)=.*/\0/p' "$DEST/.env" \
      > /etc/conf.d/pumpfun-stream 2>/dev/null || true
  chmod 600 /etc/conf.d/pumpfun-stream
fi
# OpenRC 的 conf.d 不导出变量本身，这里把变量显式 export
if ! grep -q '^export ' /etc/conf.d/pumpfun-stream 2>/dev/null; then
  sed -i 's/^\(ALCHEMY_RPC_URL\|PULSE_STORE_FIELDS\)=/export \1=/' /etc/conf.d/pumpfun-stream 2>/dev/null || true
fi
grep -q 'PULSE_STORE_FIELDS' /etc/conf.d/pumpfun-stream 2>/dev/null || \
  echo 'export PULSE_STORE_FIELDS=0' >> /etc/conf.d/pumpfun-stream

echo "==> 周期任务（保留 / 报表 / 历史 / WAL 看门狗 —— 全部带防重叠锁）"
# 这些任务在 2026-10-15/16 两次 WAL 事故后重写过，形状是硬要求。
# 源码在 deploy/periodic/，安装器是 deploy/install-periodic-alpine.sh。
RETENTION_DAYS="$RETENTION_DAYS" sh "$SRC/deploy/install-periodic-alpine.sh" "$DEST"

echo "==> 日志轮转（每周，>100MB 截断）"
cat > /etc/periodic/weekly/pumpfun-logrotate <<EOF
#!/bin/sh
F=/var/log/pumpfun-stream.log
[ -f "\$F" ] || exit 0
SIZE=\$(wc -c < "\$F" 2>/dev/null || echo 0)
[ "\$SIZE" -gt 104857600 ] && : > "\$F"
exit 0
EOF
chmod +x /etc/periodic/weekly/pumpfun-logrotate

# crond 默认可能在跑；确保开机启动
rc-update add crond default >/dev/null 2>&1 || true

echo
echo "==> 完成。检查 .env 后启动："
echo "    grep -q ALCHEMY_RPC_URL $DEST/.env && rc-update add pumpfun-stream default && rc-service pumpfun-stream start"
echo "    状态：rc-service pumpfun-stream status"
echo "    日志：tail -f /var/log/pumpfun-stream.log"
