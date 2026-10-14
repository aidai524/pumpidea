#!/usr/bin/env python3
"""回填迁移前事件的 creator 列：按 mint 读 bonding curve，批量 UPDATE。

只补 creator（其余旧列无法从链上恢复历史值）；服务运行时也能跑，
短事务 + busy timeout，避免和采集器抢锁。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from chain import Chain  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stream-db", default="/opt/pumpfun-stream/runtime/stream.sqlite3")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=0.015)
    args = ap.parse_args()

    con = sqlite3.connect(args.stream_db, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    mints = [r[0] for r in con.execute(
        "SELECT DISTINCT mint FROM events WHERE creator IS NULL AND mint IS NOT NULL")]
    print(f"待回填 mint：{len(mints):,}", flush=True)
    chain = Chain(rate=args.rate)

    def lookup(m):
        try:
            c = chain.curve(m)
            return m, (c or {}).get("creator")
        except Exception:  # noqa: BLE001
            return m, None

    done = found = 0
    batch: list[tuple[str, str]] = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for m, creator in ex.map(lookup, mints):
            done += 1
            if creator:
                batch.append((creator, m))
            if len(batch) >= 200:
                con.executemany(
                    "UPDATE events SET creator=? WHERE mint=? AND creator IS NULL", batch)
                con.commit()
                found += len(batch)
                batch.clear()
            if done % 500 == 0:
                el = time.time() - t0
                rate = done / el if el else 0
                print(f"  {done:,}/{len(mints):,} 已找到 {found:,} "
                      f"({rate:.1f} mint/s，预计剩 {(len(mints)-done)/max(rate,0.1)/60:.1f} 分钟)",
                      flush=True)
    if batch:
        con.executemany("UPDATE events SET creator=? WHERE mint=? AND creator IS NULL", batch)
        con.commit()
        found += len(batch)
    left = con.execute("SELECT count(DISTINCT mint) FROM events "
                       "WHERE creator IS NULL AND mint IS NOT NULL").fetchone()[0]
    print(f"完成：处理 {done:,}，回填 {found:,}，仍缺 {left:,}，用时 {(time.time()-t0)/60:.1f} 分钟")


if __name__ == "__main__":
    main()
