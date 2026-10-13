#!/usr/bin/env python3
"""汇总流式费用事件：按天 × quote 资产聚合六条费用线 → 定价 → 日收入曲线。

数据源：runtime/stream.sqlite3（stream_collector.py 采集）。
价格：原生 SOL/WSOL → CoinGecko；USDC → 1；其他 → DexScreener（带缓存）。
精度：原生 SOL 与 WSOL 9 位、USDC 6 位、其他从链上 getMint 取 decimals（缓存）。

用法：
  python3 stream_report.py                 # 出日报表
  python3 stream_report.py --compare       # 附表与 DefiLlama 对比
  python3 stream_report.py --top 15        # 展示 top 资产
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import time
import urllib.request
from collections import defaultdict

from rpc import make_client

ROOT = pathlib.Path(__file__).resolve().parent
DB = ROOT / "runtime" / "stream.sqlite3"
TODAY = time.strftime("%Y-%m-%d")
PRICE_CACHE = ROOT / "data" / f"stream_prices_{TODAY}.json"
DEC_CACHE = ROOT / "data" / f"stream_decimals_{TODAY}.json"

NATIVE = "11111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LINES = ["protocol_fee", "creator_fee", "buyback_fee", "lp_fee",
         "cashback", "holder_rewards"]
TRADE_EVENTS = ("BuyEvent", "SellEvent", "TradeEvent")

HTTP = None


def get_json(url: str, timeout: int = 20) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pulse-audit/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def sol_price() -> float:
    d = get_json("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
    try:
        return float(d["solana"]["usd"])
    except Exception:  # noqa: BLE001
        return 0.0


def dex_price(mint: str, cache: dict) -> dict:
    """返回 {"price": float|None, "liq": float|None}；缓存同结构。"""
    if mint in cache:
        v = cache[mint]
        return v if isinstance(v, dict) else {"price": v, "liq": None}
    d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    out = {"price": None, "liq": None}
    if d and d.get("pairs"):
        best = max(d["pairs"], key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        try:
            out["price"] = float(best["priceUsd"])
        except (KeyError, TypeError, ValueError):
            out["price"] = None
        try:
            out["liq"] = float((best.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            out["liq"] = None
    cache[mint] = out
    time.sleep(0.25)
    return out


def mint_decimals(mint: str, cache: dict) -> int:
    if mint in cache:
        return cache[mint]
    dec = 9
    # 注意：Alchemy 不支持 getMint（400），用 getAccountInfo(jsonParsed)
    res = HTTP.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    try:
        dec = int(res["value"]["data"]["parsed"]["info"]["decimals"])
    except Exception:  # noqa: BLE001
        pass
    cache[mint] = dec
    return dec


def aggregate(con: sqlite3.Connection) -> dict:
    """去重后按 (day, mint) 聚合六条线。"""
    rows = con.execute(f"""
        SELECT day, quote_mint,
               sum(protocol_fee) protocol_fee, sum(creator_fee) creator_fee,
               sum(buyback_fee) buyback_fee, sum(lp_fee) lp_fee,
               sum(cashback) cashback, sum(holder_rewards) holder_rewards,
               count(*) n
        FROM (
          SELECT *, strftime('%Y-%m-%d', ts, 'unixepoch') AS day,
                 ROW_NUMBER() OVER (
                   PARTITION BY signature, name, COALESCE(pool, '')
                   ORDER BY rowid) AS rn
          FROM events
          WHERE ts > 0 AND quote_mint IS NOT NULL
            AND name IN ({','.join('?' * len(TRADE_EVENTS))})
        )
        WHERE rn = 1
        GROUP BY day, quote_mint
    """, TRADE_EVENTS).fetchall()
    out = {}
    for r in rows:
        out[(r["day"], r["quote_mint"])] = {k: (r[k] or 0.0) for k in LINES} | {"n": r["n"]}
    return out


def report(compare: bool, top: int, min_liq: float) -> None:
    if not DB.exists():
        raise SystemExit("没有 runtime/stream.sqlite3，先跑 run_stream.sh")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    agg = aggregate(con)
    prices = json.loads(PRICE_CACHE.read_text()) if PRICE_CACHE.exists() else {}
    decs = json.loads(DEC_CACHE.read_text()) if DEC_CACHE.exists() else {}
    sol = sol_price()

    def unit_usd(mint: str) -> tuple[float | None, bool]:
        """返回 (每个 raw unit 的 USD, 是否“流动性达标”)。"""
        if mint in (WSOL, NATIVE):
            return sol / 1e9, True   # 原生 SOL = lamports，WSOL 9 位小数
        if mint == USDC:
            return 1.0 / 1e6, True
        info = dex_price(mint, prices)
        if info["price"] is None:
            return None, False
        liq_ok = (info["liq"] or 0) >= min_liq
        return info["price"] / (10 ** mint_decimals(mint, decs)), liq_ok

    daily: dict[str, dict] = defaultdict(lambda: {k: 0.0 for k in LINES}
                                         | {"total": 0.0, "total_liq": 0.0, "n": 0,
                                            "unpriced_mints": set(), "illiquid_mints": set()})
    mint_usd: dict[str, float] = defaultdict(float)
    total_combos = len(agg)
    for i, ((day, mint), vals) in enumerate(agg.items(), 1):
        if i % 25 == 0:
            print(f"  定价中… {i}/{total_combos}", flush=True)
        cu, liq_ok = unit_usd(mint)
        daily[day]["n"] += vals["n"]
        if cu is None:
            daily[day]["unpriced_mints"].add(mint)
            continue
        if not liq_ok:
            daily[day]["illiquid_mints"].add(mint)
        for k in LINES:
            usd = vals[k] * cu
            daily[day][k] += usd
            daily[day]["total"] += usd
            mint_usd[mint] += usd
            if liq_ok:
                daily[day]["total_liq"] += usd

    print(f"价格基准：SOL ${sol:.2f}；覆盖 {len(agg)} 个 (day, mint) 组合\n")
    head = f"{'day':11} {'events':>8} {'protocol':>12} {'buyback':>12} {'creator':>12} {'lp':>12} {'rewards':>10} {'total':>12}"
    print(head)
    print("-" * len(head))
    for day in sorted(daily):
        d = daily[day]
        rew = d["cashback"] + d["holder_rewards"]
        print(f"{day:11} {d['n']:>8} {d['protocol_fee']:>12,.0f} {d['buyback_fee']:>12,.0f} "
              f"{d['creator_fee']:>12,.0f} {d['lp_fee']:>12,.0f} {rew:>10,.0f} "
              f"{d['total']:>12,.0f}")
        print(f"{'':11} {'':>8} 流动性≥${min_liq/1000:.0f}k 口径: "
              f"total ${d['total_liq']:,.0f}；未定价 {len(d['unpriced_mints'])}，"
              f"低流动性 {len(d['illiquid_mints'])} 种 mint")

    print(f"\nTop {top} quote 资产（按 USD）：")
    for m, usd in sorted(mint_usd.items(), key=lambda x: -x[1])[:top]:
        print(f"  {m[:20]:20} ${usd:,.2f}")

    if compare:
        for slug in ("pump.fun", "pumpswap"):
            d = get_json(f"https://api.llama.fi/summary/fees/{slug}?dataType=dailyRevenue")
            if d:
                print(f"\nDefiLlama {slug} revenue: 24h ${d['total24h']/1e6:.2f}M | "
                      f"7d ${d['total7d']/1e6:.2f}M | 30d ${d['total30d']/1e6:.2f}M")
        print("（我们的口径：protocol+buyback+creator+lp+cashback+holder；"
              "DefiLlama 的 revenue 只含协议留存）")

    PRICE_CACHE.write_text(json.dumps(prices, indent=1))
    DEC_CACHE.write_text(json.dumps(decs, indent=1))
    out = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sol_usd": sol,
        "daily": {day: {**{k: round(v, 2) for k, v in d.items()
                          if k not in ("unpriced_mints", "illiquid_mints")},
                        "unpriced_mints": len(d["unpriced_mints"]),
                        "illiquid_mints": len(d["illiquid_mints"])}
                  for day, d in sorted(daily.items())},
        "top_mints": [{"mint": m, "usd": round(u, 2)}
                      for m, u in sorted(mint_usd.items(), key=lambda x: -x[1])[:top]],
    }
    (ROOT / "stream_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n写了 {ROOT/'stream_report.json'}")


def main() -> None:
    global HTTP
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", action="store_true", help="附表与 DefiLlama 对比")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-liquidity", type=float, default=50000,
                    help="低于该流动性（USD）的 quote 资产计入“低流动性”口径")
    ap.add_argument("--rpc", help="覆盖 RPC（默认 .env 里的 ALCHEMY_RPC_URL）")
    args = ap.parse_args()
    HTTP = make_client(cli=args.rpc, rate=0.02)
    report(args.compare, args.top, args.min_liquidity)


if __name__ == "__main__":
    main()
