#!/usr/bin/env python3
"""用实时流数据更新创建者历史（补数据集 7 天延迟之外的缺口）。

⚠️ 2026-10-16 重写 —— 旧版是 WAL 事故的根因之一，改之前请读完这一段。

旧版每轮执行 `WHERE ts > now - 3 天` 的**全表扫描 + 窗口函数**，把整张 events
表过一遍（实测单次 >5 分钟，其中 CPU 仅 19 秒，其余全是读 11GB 的 I/O 等待）。
而它被 cron 每 15 分钟调一次，于是形成：

    读快照几乎永续存在 → WAL checkpoint 被钉住 → WAL 永远无法重置
    → 无限增长（实测 ~6GB/小时）→ 磁盘打满 → 采集器 disk I/O error 死掉数小时

两次事故（10-15 的 33.5G、10-16 的 35.5G）由此而来。直接证据：读快照存在期间
`PRAGMA wal_checkpoint` 返回的 checkpointed 值**冻结在 292387 长达 240 秒**，
读者一退出立刻重置到 859。

现在的做法是**增量**：

    1. 只在窄窗口（--discover-hours）内发现「新出现的 mint」→ 写入 pending_mints
    2. 每轮只处理 pending 里 due_at 到期的（= 首见已超过 --min-age）
    3. 每个 mint 的聚合走 idx_events_mint **单独查**，不再全表排序
    4. 每轮处理量有上限（--max-per-run），保证运行时长的上界
    5. 结算后不删除，而是把 due_at 推后 --revisit-hours（在 --revisit-window
       之内），所以 mint 仍会被**定期重新分类**（毕业后状态会跟上），
       不像「只算一次」那样冻结在 1 小时时的判断

输出独立 SQLite（默认 risk/stream_history.sqlite3），不写采集库，避免锁竞争。
评分服务读其中的 creators_stream(n, resolved, rugs, grads)。

用法（VPS 上由 periodic 调用）：
  python3 update_history_from_stream.py --stream-db /opt/.../stream.sqlite3
一次性回填更早的历史可以调大窗口：
  python3 update_history_from_stream.py --discover-hours 72
"""
from __future__ import annotations

import argparse
import pathlib
import sqlite3
import time

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_STREAM = pathlib.Path("/opt/pumpfun-stream/runtime/stream.sqlite3")
CURVE_COMPLETE_SOL = 85.0
DRAIN_MIN_PEAK_SOL = 5.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_mints(
  mint TEXT PRIMARY KEY, first_seen INTEGER, due_at INTEGER);
CREATE INDEX IF NOT EXISTS idx_pending_due ON pending_mints(due_at);

CREATE TABLE IF NOT EXISTS mint_outcomes(
  mint TEXT PRIMARY KEY, creator TEXT, first_ts INTEGER, peak_sol REAL,
  last_sol REAL, graduated_like INTEGER, rug_like INTEGER,
  dev_sell_ts INTEGER, updated_at INTEGER);

CREATE TABLE IF NOT EXISTS creators_stream(
  creator TEXT PRIMARY KEY, n INTEGER, resolved INTEGER,
  rugs INTEGER, grads INTEGER, updated_at INTEGER);
"""

# 单个 mint 的全部事件。窗口函数只跑这一个 mint 的行，走 idx_events_mint，
# 代价与该 mint 的事件数成正比 —— 这是与旧版全表排序最本质的区别。
PER_MINT_SQL = """
SELECT min(ts) AS t0,
       max(real_quote_reserves) AS peak_raw,
       max(CASE WHEN is_buy = 0 AND user = creator THEN ts END) AS dev_sell_ts,
       max(CASE WHEN rn = 1 THEN real_quote_reserves END) AS last_raw,
       max(creator) AS creator
FROM (
  SELECT ts, real_quote_reserves, is_buy, user, creator,
         ROW_NUMBER() OVER (ORDER BY ts DESC) AS rn
  FROM events
  WHERE mint = ? AND program = 'curve'
)
"""


def migrate(con: sqlite3.Connection) -> None:
    """旧库的 pending_mints 没有 due_at 列（如果从更早的版本升上来）。"""
    cols = {r[1] for r in con.execute("PRAGMA table_info(pending_mints)")}
    if cols and "due_at" not in cols:
        con.execute("ALTER TABLE pending_mints ADD COLUMN due_at INTEGER")
        con.execute("UPDATE pending_mints SET due_at = first_seen")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stream-db", default=str(DEFAULT_STREAM))
    ap.add_argument("--out", default=str(ROOT / "stream_history.sqlite3"))
    ap.add_argument("--discover-hours", type=float, default=2.0,
                    help="发现新 mint 的窗口（必须 > cron 间隔，默认 2 小时）")
    ap.add_argument("--min-age", type=float, default=3600.0,
                    help="首见超过 N 秒才结算（默认 1 小时）")
    ap.add_argument("--revisit-hours", type=float, default=6.0,
                    help="结算后再过 N 小时重新分类（默认 6 小时）")
    ap.add_argument("--revisit-window", type=float, default=48.0,
                    help="首见在 N 小时内才继续重访；更早的永久落定（默认 48 小时）")
    ap.add_argument("--max-per-run", type=int, default=1000,
                    help="每轮最多结算多少个 mint（实测 ~0.33s/mint，1000 ≈ 5.5 分钟，
                          这就是读快照的时长上界）")
    args = ap.parse_args()

    now = int(time.time())
    out = sqlite3.connect(args.out, timeout=30)
    out.executescript(SCHEMA)
    migrate(out)

    # ---- 1) 发现新 mint（窄窗口，走 idx_events_ts）----
    src = sqlite3.connect(f"file:{args.stream_db}?mode=ro", uri=True, timeout=30)
    src.execute("PRAGMA query_only=1")           # 明确只读，不给采集器添锁
    since = int(now - args.discover_hours * 3600)
    # ⛔ INDEXED BY 是必须的，不要删。
    # 不加时 SQLite 为了方便 GROUP BY 免排序，会选 idx_events_mint —— 那等于**顺着
    # mint 索引扫全表**（实测: 4800 万行 → 分钟级，而且全程持读快照，把 WAL 的
    # checkpoint 水位线钉死 —— 正是这个 bug 在 2026-10-16 重演了一次事故）。
    # 加上后走 idx_events_ts 的时间范围扫描 + 临时 B 树分组：实测 1 小时窗口 0 秒。
    # 验证方法：EXPLAIN QUERY PLAN 必须看到 “SEARCH events USING INDEX idx_events_ts”。
    found = src.execute("""
        SELECT mint, min(ts) FROM events INDEXED BY idx_events_ts
        WHERE program = 'curve' AND mint IS NOT NULL AND ts > ?
        GROUP BY mint
    """, (since,)).fetchall()
    out.executemany(
        "INSERT OR IGNORE INTO pending_mints(mint, first_seen, due_at) VALUES(?,?,?)",
        [(m, t, (t or now) + int(args.min_age)) for m, t in found])

    # ---- 2) 取出到期的候选（有上限）----
    due = out.execute(
        "SELECT mint FROM pending_mints WHERE due_at IS NOT NULL AND due_at <= ? "
        "ORDER BY due_at LIMIT ?", (now, args.max_per_run)).fetchall()

    n = closed = 0
    for (mint,) in due:
        r = src.execute(PER_MINT_SQL, (mint,)).fetchone()
        if not r:
            out.execute("DELETE FROM pending_mints WHERE mint=?", (mint,))
            continue
        t0, peak_raw, dev_sell_ts, last_raw, creator = r
        if not creator:
            # creator 还没回填到（backfill_creator.py 未跑到）—— 下轮再来，别落定错的结论
            out.execute("UPDATE pending_mints SET due_at=? WHERE mint=?",
                        (now + 600, mint))
            continue
        peak = (peak_raw or 0) / 1e9
        last = (last_raw or 0) / 1e9
        grad = 1 if peak >= CURVE_COMPLETE_SOL else 0
        dev_dump = bool(dev_sell_ts) and (dev_sell_ts - (t0 or 0) <= 300)
        drain = peak >= DRAIN_MIN_PEAK_SOL and last <= 0.25 * peak and not grad
        rug = 1 if (dev_dump or drain) else 0
        out.execute("INSERT OR REPLACE INTO mint_outcomes VALUES(?,?,?,?,?,?,?,?,?)",
                    (mint, creator, t0, round(peak, 4), round(last, 4),
                     grad, rug, dev_sell_ts, now))
        if t0 and t0 > now - args.revisit_window * 3600:
            out.execute("UPDATE pending_mints SET due_at=? WHERE mint=?",
                        (now + int(args.revisit_hours * 3600), mint))
        else:
            out.execute("DELETE FROM pending_mints WHERE mint=?", (mint,))
        n += 1
        closed += 1 if (grad or rug) else 0

    # ---- 3) 重建创建者汇总（只读本地表，很快）----
    out.execute("DELETE FROM creators_stream")
    out.execute("""
        INSERT INTO creators_stream
        SELECT creator, count(*),
               sum(CASE WHEN graduated_like=1 OR rug_like=1 THEN 1 ELSE 0 END),
               sum(rug_like), sum(graduated_like), ?
        FROM mint_outcomes GROUP BY creator
    """, (now,))
    out.commit()

    n_creators = out.execute("select count(*) from creators_stream").fetchone()[0]
    n_pending = out.execute("select count(*) from pending_mints").fetchone()[0]
    n_total = out.execute("select count(*) from mint_outcomes").fetchone()[0]
    out.close()
    src.close()
    print(f"{args.out}: 发现 {len(found):,}，结算 {n:,}（{closed:,} 有结局）；"
          f"累计 mint {n_total:,}，创建者 {n_creators:,}，待到期 {n_pending:,}")
    if len(due) >= args.max_per_run:
        print(f"  ⚠️ 本轮达到上限 {args.max_per_run}，剩余留待下一轮")


if __name__ == "__main__":
    main()
