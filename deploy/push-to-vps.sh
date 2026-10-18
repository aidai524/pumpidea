#!/bin/sh
# 从本机把仓库推到 VPS 并在远端执行站点部署。用法：
#   sh deploy/push-to-vps.sh [user@host] [APP_DIR]
#   默认 root@103.3.62.56  /opt/pumpfun-stream
#
# 为什么需要这个包装：部署脚本在远端执行，而远端那份源码是 rsync 过去的、
# **没有 .git**，所以它自己查不到"部署的是哪个提交"。提交号必须在**调用方**
# 取好再传进去 —— 否则线上版本就只存在于人的记忆里（我第一次就是这么踩的，
# 结果 DEPLOYED_COMMIT 里写的是 unknown）。
set -eu

HOST=${1:-root@103.3.62.56}
APP=${2:-/opt/pumpfun-stream}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SRC=/tmp/pumpidea-src

COMMIT=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)
[ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ] || COMMIT="$COMMIT+dirty"

echo "==> 同步到 $HOST:${SRC}（版本 ${COMMIT}）"
rsync -a --delete \
  --exclude '.git' --exclude 'node_modules' --exclude '.venv' --exclude '__pycache__' \
  --exclude 'data/launches' --exclude 'data/launches_legacy' \
  --exclude 'data/graduation_pools' \
  --exclude 'runtime' --exclude '*.sqlite3' --exclude '*.tsbuildinfo' \
  -e "ssh" "$ROOT/" "$HOST:$SRC/"

echo "==> 在远端部署"
ssh "$HOST" "DEPLOY_COMMIT=$COMMIT sh $SRC/deploy/install-site-alpine.sh $APP"
