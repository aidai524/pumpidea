#!/usr/bin/env bash
# 下载 pump.fun 研究用的公开数据集（全部无需 key、CC BY 4.0）。
#
# 来源：loopholetape/pumpfun-launches（HuggingFace）
#   记录方用自己的 Yellowstone gRPC 流抓 pump.fun 程序事件，一格一 mint，
#   并给出结局标签（graduated / rugged 及其时刻）。
#   许可 CC BY 4.0，引用见 README。
#
# 两组子集**必须分开用**（见 KNOWN_ISSUES KI-02）：
#   launches        2026-09-27 起，解码器完整 → 买入派生特征（捆绑钱包、峰值）可信
#   launches_legacy 2026-09-26 止，解码器漏了约 48% 的买单 → 只能用于总量/结局/毕业标签
set -euo pipefail
BASE="https://huggingface.co/datasets/loopholetape/pumpfun-launches/resolve/main"
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/data"

mkdir -p "$OUT/launches" "$OUT/launches_legacy" "$OUT/graduation_pools"

fetch() {  # fetch <repo 相对路径> <本地目录>
  local rel="$1" dir="$2" name; name="$(basename "$rel")"
  if [ -s "$dir/$name" ]; then echo "  已有 $name"; return; fi
  printf "  %-34s " "$name"
  curl -fsSL --retry 3 --max-time 300 "$BASE/$rel" -o "$dir/$name" \
    && echo "$(wc -c < "$dir/$name" | tr -d ' ') 字节" \
    || { echo "失败"; return 1; }
}

for d in 2026-09-27 2026-09-28 2026-09-29 2026-09-30 2026-10-01; do
  fetch "data/launches/$d.parquet" "$OUT/launches"
done
for d in $(seq -f "2026-09-%02g" 1 26) 2026-08-31; do
  fetch "data/launches_legacy/$d.parquet" "$OUT/launches_legacy" || true
done
fetch "data/graduation_pools/graduation_pools.parquet" "$OUT/graduation_pools"

echo
du -sh "$OUT"/* | sed 's/^/  /'
