#!/bin/sh
# 安装/更新 pumpfun 的周期任务（幂等，可反复跑）。
# 用法：sh install-periodic-alpine.sh [安装目录，默认 /opt/pumpfun-stream]
#
# 为什么单独一个脚本、而不是散在各 install-*.sh 里内联 heredoc：
# 这 4 个任务在 2026-10-15/16 两次 WAL 事故后**全部重写过**，而事故根因是
# 「调度层的形状」而不是某个函数的 bug —— 所以它们必须被当成一份可审阅的资产
# 放在仓库里，而不是每次重装时重新生成一遍。
#
# 事故根因（详见 docs/decisions.md 的 WAL 条）：重分析任务会持读快照，而读快照会
# **钉住 SQLite WAL 的 checkpoint 水位线**，让它永远无法重置、无限增长。实测证据：
# 读快照存在期间 `wal_checkpoint` 返回的 checkpointed 值冻结在 292387 长达 240 秒，
# 读者一退出立刻重置到 859。
#
# 所以下面每个任务的两个特征是**硬要求**，不是优化：
#   1) 防重叠（mkdir 原子锁）—— 一轮没跑完就跳过下一轮，绝不允许两轮并行
#   2) 有观测（walwatch 每 15 分钟记一行 WAL 大小与 checkpoint 读数）
# 另外 pumpfun-history 必须留在 **hourly** 表里：它单次要跑几分钟，跑 4 次/小时
# 既没用（min-age 本来就是 1 小时），又正是 WAL 失控的直接推手。
set -eu

APP=${1:-/opt/pumpfun-stream}
# 保留天数可配：RETENTION_DAYS=3 sh install-periodic-alpine.sh
RETENTION_DAYS=${RETENTION_DAYS:-7}
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/periodic

[ -d "$APP" ] || { echo "❌ 安装目录不存在: $APP" >&2; exit 1; }
[ -d "$SRC" ] || { echo "❌ 找不到脚本源: $SRC" >&2; exit 1; }

echo "==> 安装周期任务（APP=$APP）"

install_one() {
  name=$1
  dir=$2
  mkdir -p "$dir"
  sed -e "s|@APP@|$APP|g" -e "s|@RETENTION_DAYS@|$RETENTION_DAYS|g" \
      "$SRC/$name" >"$dir/$name"
  chmod 755 "$dir/$name"
  printf '  %-42s %sB\n' "$dir/$name" "$(wc -c <"$dir/$name" | tr -d ' ')"
}

install_one pumpfun-walwatch /etc/periodic/15min
install_one pumpfun-report /etc/periodic/hourly
install_one pumpfun-history /etc/periodic/hourly
install_one pumpfun-retention /etc/periodic/daily

# 旧版本把 history 放在 15 分钟表里。降频后如果两个位置都在，会同时跑两份 ——
# 那正是"读快照永续存在"的成因。
if [ -f /etc/periodic/15min/pumpfun-history ]; then
  rm -f /etc/periodic/15min/pumpfun-history
  echo "  ⚠️ 已移除旧的 /etc/periodic/15min/pumpfun-history（应在 hourly）"
fi

echo "==> 完成。确认 crond 在跑："
echo "    rc-service crond status"
echo "    首次部署后先看一轮日志：tail -f /var/log/pumpfun-walwatch.log"
