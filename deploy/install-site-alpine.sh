#!/bin/sh
# 部署统一站点（BFF + 前端产物 + pulse 采集）到 Alpine/OpenRC。
# 幂等，可反复跑。用法：
#   sh deploy/install-site-alpine.sh [APP_DIR]        默认 /opt/pumpfun-stream
#
# 前置：仓库已在本机 checkout（脚本会把 api/ web/dist/ analysis/ pulse/ 同步到 APP_DIR），
#       并且下面的东西已经就位：
#         - audit/ 已由 audit/deploy/install-alpine.sh 部署（采集器 + 报表 + 周期任务）
#         - risk/ 已由 audit/deploy/install-risk-alpine.sh 部署（打分服务，:8090）
#         - /etc/pumpfun-web.conf 存在（risk 与 BFF 都读它）
#
# 为什么由 BFF 直接托管 SPA、而不是让 Caddy 指向一个静态目录：
# Caddy 跑在宿主机、代码在容器里，静态目录过不去。BFF 托管后**只有一个后端进程、
# 一个端口**，Caddy 只需一条反代。
set -eu

APP=${1:-/opt/pumpfun-stream}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PORT=${API_PORT:-8000}

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 前置检查
[ -f "$ROOT/api/app/main.py" ] || { echo "❌ 找不到 api/（在 $(pwd) 跑？）" >&2; exit 1; }
[ -f "$ROOT/web/dist/index.html" ] || {
  echo "❌ 缺少 web/dist —— 前端产物必须先在本地/CI 构建并提交" >&2
  echo "   cd web && npm ci && npm run build" >&2
  exit 1
}
[ -d "$APP" ] || { echo "❌ 安装目录不存在: $APP" >&2; exit 1; }
command -v sqlite3 >/dev/null 2>&1 || apk add --no-cache sqlite >/dev/null

# ---------------------------------------------------------------- 同步代码
say "同步 api / web / analysis / pulse 到 $APP"
rsync -a --delete \
  --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude '*.pyc' \
  --exclude .ruff_cache \
  "$ROOT/api/" "$APP/api/"

rsync -a --delete "$ROOT/web/dist/" "$APP/web/"

# analysis 只需要 facts.json 与脚本；数据目录 142MB 不在仓库里，不搬。
rsync -a --delete \
  --exclude data --exclude .venv --exclude __pycache__ --exclude '*.pyc' \
  "$ROOT/analysis/" "$APP/analysis/"

# pulse 的 runtime/ 与 site/data.json 是运行期产物，不能覆盖。
rsync -a \
  --exclude runtime --exclude .venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude 'site/data.json' --exclude 'site/cards' \
  "$ROOT/pulse/" "$APP/pulse/"

# ---------------------------------------------------------------- Python 环境
say "Python 依赖（装进共享 venv：$APP/.venv）"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -e "$APP/api"

# ---------------------------------------------------------------- BFF 配置
say "BFF 环境变量 → /etc/conf.d/pumpfun-api"
cat >/etc/conf.d/pumpfun-api <<CONF
# 上游产出物的位置。三条线各自写各自的文件，BFF 只读。
export PUMPIDEA_API_ANALYSIS_FACTS=$APP/analysis/facts.json
# 注意：audit/ 的内容被 install-alpine.sh 铺到了 $APP 根（stream_collector.py 就在
# 根上），所以 audit 的 facts.json 在 $APP/facts.json，不是 $APP/audit/facts.json。
export PUMPIDEA_API_AUDIT_FACTS=$APP/facts.json
export PUMPIDEA_API_AUDIT_REPORT=$APP/stream_report.json
export PUMPIDEA_API_PULSE_DATA=$APP/pulse/site/data.json
export PUMPIDEA_API_RISK_BASE_URL=http://127.0.0.1:8090
export PUMPIDEA_API_RISK_CREDS=/etc/pumpfun-web.conf
export PUMPIDEA_API_WEB_DIST=$APP/web
CONF

say "OpenRC 服务 pumpfun-api（127.0.0.1:${PORT}）"
cat >/etc/init.d/pumpfun-api <<SVC
#!/sbin/openrc-run
name="pumpfun-api"
description="pumpidea 薄 BFF + 前端静态托管"

command="$APP/.venv/bin/python"
command_args="-m uvicorn app.main:app --host 127.0.0.1 --port $PORT"
directory="$APP/api"
command_background=true
pidfile="/run/pumpfun-api.pid"
output_log="/var/log/pumpfun-api.log"
error_log="/var/log/pumpfun-api.log"
respawn_delay=5
supervisor=supervise-daemon

depend() {
    need net
    use pumpfun-risk
}
SVC
chmod +x /etc/init.d/pumpfun-api
rc-update add pumpfun-api default >/dev/null 2>&1 || true
rc-service pumpfun-api restart >/dev/null 2>&1 || rc-service pumpfun-api start

# ---------------------------------------------------------------- pulse
# pulse 是纯 stdlib，用系统 python3 就够，不必碰 venv。
if [ -f "$APP/pulse/collector.py" ]; then
  say "OpenRC 服务 pumpfun-pulse-collector / pumpfun-pulse-builder"

  cat >/etc/init.d/pumpfun-pulse-collector <<SVC
#!/sbin/openrc-run
name="pumpfun-pulse-collector"
description="pulse 采集（loopholetape 公开 API，30 秒/10 秒节奏）"
command="/usr/bin/python3"
command_args="collector.py"
directory="$APP/pulse"
command_background=true
pidfile="/run/pumpfun-pulse-collector.pid"
output_log="/var/log/pumpfun-pulse.log"
error_log="/var/log/pumpfun-pulse.log"
respawn_delay=10
supervisor=supervise-daemon
depend() { need net; }
SVC

  cat >/etc/init.d/pumpfun-pulse-builder <<SVC
#!/sbin/openrc-run
name="pumpfun-pulse-builder"
description="pulse 构建（每 30 秒重写 site/data.json）"
command="/usr/bin/python3"
command_args="builder.py --loop --every 30"
directory="$APP/pulse"
command_background=true
pidfile="/run/pumpfun-pulse-builder.pid"
output_log="/var/log/pumpfun-pulse.log"
error_log="/var/log/pumpfun-pulse.log"
respawn_delay=10
supervisor=supervise-daemon
depend() { need net; }
SVC

  chmod +x /etc/init.d/pumpfun-pulse-collector /etc/init.d/pumpfun-pulse-builder
  rc-update add pumpfun-pulse-collector default >/dev/null 2>&1 || true
  rc-update add pumpfun-pulse-builder default >/dev/null 2>&1 || true
  rc-service pumpfun-pulse-collector restart >/dev/null 2>&1 || rc-service pumpfun-pulse-collector start
  rc-service pumpfun-pulse-builder restart >/dev/null 2>&1 || rc-service pumpfun-pulse-builder start
fi

# ---------------------------------------------------------------- 记录版本
# VPS 上的源码是 rsync 过去的、不是 git checkout，所以它**不能自己 git log**。
# 不写一个版本文件的话，"线上跑的是哪个提交"就只存在于人的记忆里。
# 提交由**调用方**传入：部署常在远端执行，而远端那份源码是 rsync 过去的、
# 没有 .git，自己查不到。见 deploy/push-to-vps.sh。
COMMIT=${DEPLOY_COMMIT:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}
[ "$COMMIT" = unknown ] || [ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ] \
  || COMMIT="$COMMIT+dirty"
printf '%s\n' "$COMMIT" >"$APP/DEPLOYED_COMMIT"
say "部署版本 ${COMMIT}（写入 $APP/DEPLOYED_COMMIT）"

# ---------------------------------------------------------------- 自检
say "自检"
sleep 3
for s in pumpfun-api pumpfun-pulse-collector pumpfun-pulse-builder; do
  [ -x "/etc/init.d/$s" ] || continue
  printf '  %-28s %s\n' "$s" "$(rc-service "$s" status 2>&1 | head -1)"
done

printf '  GET /            → '
curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 "http://127.0.0.1:$PORT/" || true
printf '  GET /api/v1/health → '
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "http://127.0.0.1:$PORT/api/v1/health" || true
printf '  node 是否被装上（应为空）: '
command -v node || echo "（空 ✅）"

cat <<EOF

==> 完成。若要对外，在**宿主机**的 Caddyfile 里加（片段见 deploy/caddy/pumpidea.caddyfile）：

    handle_path /pumpfun/* { reverse_proxy <本机对内 IP>:$PORT }

然后 caddy validate && caddy reload。

上线前务必先看 docs/STATUS.md §5-1：**站点目前没有任何鉴权**，不要直接公网暴露。
EOF
