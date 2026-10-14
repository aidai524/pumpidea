#!/usr/bin/env python3
"""用实时流数据更新创建者历史（补数据集 7 天延迟之外的缺口）。

只处理「已成熟」的 mint（首见时间早于 min_age），用简化规则给结果：
  graduated_like = 曲线储备峰值 ≥ 85 SOL
  rug_like       = 创建者 300 秒内卖出（dev dump）或储备跌破峰值 25%（drain）

输出独立 SQLite（默认 risk/stream_history.sqlite3），不写采集库避免锁竞争；
评分服务会把「数据集历史 + 流历史」合并。

用法（VPS 上由 periodic 调用）：
  python3 update_history_from_stream.py --stream-db /opt/.../stream.sqlite3
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import time

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_STREAM = pathlib.Path("/opt/pumpfun-stream/runtime/stream.sqlite3")
CURVE_COMPLETE_SOL = 85.0
DRAIN_MIN_PEAK_SOL = 5.0

SQL = """
WITH ranked AS (
  SELECT mint, ts, real_quote_reserves, is_buy, user, creator,
         ROW_NUMBER() OVER (PARTITION BY mint ORDER BY ts DESC) AS rn_desc
  FROM events
  WHERE program = 'curve' AND mint IS NOT NULL AND ts > ?
)
SELECT mint,
       min(ts) AS t0,
       max(real_quote_reserves) AS peak_raw,
       max(CASE WHEN is_buy = 0 AND user = creator THEN ts END) AS dev_sell_ts,
       max(CASE WHEN rn_desc = 1 THEN real_quote_reserves END) AS last_raw,
       max(creator) AS creator
FROM ranked
GROUP BY mint
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stream-db", default=str(DEFAULT_STREAM))
    ap.add_argument("--out", default=str(ROOT / "stream_history.sqlite3"))
    ap.add_argument("--days", type=float, default=3.0, help="只回看最近 N 天")
    ap.add_argument("--min-age", type=float, default=3600.0, help="首见超过 N 秒才算成熟")
    args = ap.parse_args()

    since = int(time.time() - args.days * 86400)
    now = int(time.time())
    src = sqlite3.connect(f"file:{args.stream_db}?mode=ro", uri=True, timeout=10)
    src.row_factory = sqlite3.Row
    rows = src.execute(SQL, (since,)).fetchall()
    src.close()

    out = sqlite3.connect(args.out + ".tmp")
    out.executescript("""
      DROP TABLE IF EXISTS mint_outcomes;
      CREATE TABLE mint_outcomes(
        mint TEXT PRIMARY KEY, creator TEXT, first_ts INTEGER, peak_sol REAL,
        last_sol REAL, graduated_like INTEGER, rug_like INTEGER,
        dev_sell_ts INTEGER, updated_at INTEGER);
      DROP TABLE IF EXISTS creators_stream;
      CREATE TABLE creators_stream(
        creator TEXT PRIMARY KEY, n INTEGER, resolved INTEGER,
        rugs INTEGER, grads INTEGER, updated_at INTEGER);
    """)
    now = int(time.time())
    n = closed = 0
    for r in rows:
        if not r["creator"] or (r["t0"] or 0) > now - args.min_age:
            continue
        peak = (r["peak_raw"] or 0) / 1e9
        last = (r["last_raw"] or 0) / 1e9
        grad = 1 if peak >= CURVE_COMPLETE_SOL else 0
        dev_dump = bool(r["dev_sell_ts"]) and (r["dev_sell_ts"] - r["t0"] <= 300)
        drain = peak >= DRAIN_MIN_PEAK_SOL and last <= 0.25 * peak and not grad
        rug = 1 if (dev_dump or drain) else 0
        out.execute("INSERT OR REPLACE INTO mint_outcomes VALUES(?,?,?,?,?,?,?,?,?)",
                    (r["mint"], r["creator"], r["t0"], round(peak, 4), round(last, 4),
                     grad, rug, r["dev_sell_ts"], now))
        n += 1
        closed += 1 if (grad or rug) else 0
    out.execute("""
      INSERT INTO creators_stream
      SELECT creator, count(*),
             sum(CASE WHEN graduated_like=1 OR rug_like=1 THEN 1 ELSE 0 END),
             sum(rug_like), sum(graduated_like), ?
      FROM mint_outcomes GROUP BY creator
    """, (now,))
    out.commit()
    n_creators = out.execute("select count(*) from creators_stream").fetchone()[0]
    out.close()
    os.replace(args.out + ".tmp", args.out)
    print(f"{args.out}: mint {n:,}（结算 {closed:,}），创建者 {n_creators:,}；"
          f"窗口最近 {args.days} 天，成熟 {args.min_age:.0f}s")


if __name__ == "__main__":
    main()
