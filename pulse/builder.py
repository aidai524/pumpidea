#!/usr/bin/env python3
"""Pulse 构建器：DB → 故事 → SVG 卡片 + site/data.json。

站点是纯静态的：app.js 每 15s 拉一次 data.json。builder --loop 持续重建，
所以采集到的新事件最多几十秒后就出现在页面上。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pulse import cards, store, stories  # noqa: E402

SITE = pathlib.Path(__file__).resolve().parent / "site"


def _radar_row(r: dict) -> dict:
    flags = [f for f in (r.get("flags") or "").split(",") if f]
    return {
        "mint": r["mint"],
        "symbol": stories.clean(r.get("symbol") or r.get("name") or "?", 24),
        "age": stories.humanize_seconds(r.get("age_s")),
        "reserve_sol": round(r.get("rs_sol") or 0, 2),
        "n_buys": r.get("n_buys"),
        "unique_buyers_60s": r.get("unique_buyers_60s"),
        "top5_share": round((r.get("top5_share") or 0) * 100, 1),
        "p_rug": round((r.get("p_rug") or 0) * 100, 1),
        "p_grad": round((r.get("p_grad") or 0) * 100, 1),
        "flags": flags,
    }


def _tape_row(r: dict) -> dict:
    pool = r.get("pool_30m") or {}
    return {
        "mint": r["mint"],
        "symbol": stories.clean(r.get("symbol") or r.get("name") or "?", 24),
        "label": r.get("label"),
        "seconds": stories.humanize_seconds(r.get("seconds_to_graduation")),
        "when": stories.clock_utc(r.get("t0")),
        "copies": r.get("ticker_copies") or 0,
        "peak_sol": round(r.get("peak_curve_sol") or 0, 2),
        "price_vs_open": (round(pool["price_vs_open"] * 100)
                          if pool.get("price_vs_open") is not None else None),
        "link": r.get("open_pumpfun") or f"https://pump.fun/coin/{r['mint']}",
    }


def build() -> pathlib.Path:
    con = store.connect()
    grads = store.recent_graduations(con, 500)
    raw = store.latest_counts(con) or {}
    counts = raw.get("counts") or {}
    radar_grad = store.latest_radar(con, "top_graduation", 12)
    radar_rug = store.latest_radar(con, "top_rug_risk", 12)

    wall = stories.build_stories(grads, radar_grad, radar_rug)
    cards.write_cards(SITE, wall)

    kpis = {
        "launches": counts.get("launches"),
        "graduations": counts.get("true_graduations"),
        "graduation_rate": counts.get("graduation_rate"),
        "instant_bundles": counts.get("instant_bundles"),
        "instant_share": counts.get("instant_share_of_graduations"),
        "organic_rate": counts.get("organic_graduation_rate"),
        "pool_death_share": counts.get("share_lost_90pct_in_30m"),
        "median_collapse_s": counts.get("median_s_to_collapse"),
        "organic_median_s": counts.get("median_s_to_graduation_organic"),
        "window_from": (raw.get("window") or {}).get("from"),
        "window_to": (raw.get("window") or {}).get("to"),
    }

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_generated_at": raw.get("generated_at"),
        "kpis": kpis,
        "live": {
            "graduation": [_radar_row(r) for r in radar_grad],
            "rug": [_radar_row(r) for r in radar_rug],
        },
        "stories": wall,
        "tape": [_tape_row(r) for r in grads[:60]],
    }
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return SITE / "data.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="Pulse builder")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--every", type=int, default=30)
    args = ap.parse_args()
    while True:
        out = build()
        print(f"[{time.strftime('%H:%M:%S')}] 写了 {out}", flush=True)
        if not args.loop:
            return
        time.sleep(args.every)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
