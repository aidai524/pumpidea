#!/usr/bin/env python3
"""Pulse 采集器：轮询公开实时源，落 SQLite。

  radar        每 10s（源每 5s 刷新）
  graduations  每 60s（源 5 分钟延迟，24h 窗口，最多 200 行）
  stats        每 30min（KPI 底数）

默认循环；--once 跑一轮。任何单个源失败都不会中断循环。
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pulse import sources, store  # noqa: E402


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def poll_radar(con) -> int:
    d = sources.fetch_radar()
    n = store.upsert_radar(con, d.get("top_rug_risk") or [], "top_rug_risk")
    n += store.upsert_radar(con, d.get("top_graduation") or [], "top_graduation")
    return n


def poll_graduations(con) -> int:
    d = sources.fetch_graduations()
    n = store.upsert_graduations(con, d.get("rows") or [])
    store.save_counts(con, d)
    return n


def poll_stats(con) -> int:
    store.save_stats(con, sources.fetch_stats())
    return 1


def one_cycle(con, do_radar=True, do_grads=True, do_stats=False) -> None:
    for name, fn, enabled in (
        ("radar", poll_radar, do_radar),
        ("graduations", poll_graduations, do_grads),
        ("stats", poll_stats, do_stats),
    ):
        if not enabled:
            continue
        try:
            n = fn(con)
            log(f"{name}: {n} 行")
        except Exception:  # noqa: BLE001 采集循环不能死
            log(f"{name}: 失败\n{traceback.format_exc(limit=2)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pulse collector")
    ap.add_argument("--once", action="store_true", help="跑一轮就退出")
    ap.add_argument("--radar-every", type=int, default=10)
    ap.add_argument("--grads-every", type=int, default=60)
    ap.add_argument("--stats-every", type=int, default=1800)
    args = ap.parse_args()

    con = store.connect()
    if args.once:
        one_cycle(con, do_stats=True)
        return

    log(f"开始采集（DB={store.db_path()}）")
    last = {"radar": 0.0, "grads": 0.0, "stats": 0.0}
    while True:
        now = time.time()
        one_cycle(
            con,
            do_radar=now - last["radar"] >= args.radar_every,
            do_grads=now - last["grads"] >= args.grads_every,
            do_stats=now - last["stats"] >= args.stats_every,
        )
        now = time.time()
        for k, every in (("radar", args.radar_every),
                         ("grads", args.grads_every),
                         ("stats", args.stats_every)):
            if now - last[k] >= every:
                last[k] = now
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
