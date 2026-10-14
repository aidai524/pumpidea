#!/usr/bin/env python3
"""汇总流式费用事件：日/小时 × quote 资产 → 定价 → 双口径报告（JSON + CSV）。

定价策略（为小时级任务优化）：
  - 持久缓存 data/price_cache.json / decimals_cache.json（mint 级，价格 24h 过期）
  - 只给事件数 top-N 的 mint 定价（默认 600），长尾记为 unpriced
  - 并发抓取（默认 8 线程 + 全局限速）

口径：all = 全部可定价；liq = 最优交易对流动性 ≥ min_liquidity。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import pathlib
import sqlite3
import threading
import time
import urllib.request
from collections import defaultdict

from rpc import make_client

ROOT = pathlib.Path(__file__).resolve().parent
DB = ROOT / "runtime" / "stream.sqlite3"
PRICE_CACHE = ROOT / "data" / "price_cache.json"
DEC_CACHE = ROOT / "data" / "decimals_cache.json"
PRICE_TTL = 86400

NATIVE = "11111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
FIXED = {NATIVE, WSOL, USDC}
LINES = ["protocol_fee", "creator_fee", "buyback_fee", "lp_fee",
         "cashback", "holder_rewards"]
TRADE_EVENTS = ("BuyEvent", "SellEvent", "TradeEvent")
TS_MIN, TS_MAX = 1_600_000_000, 2_000_000_000
HTTP = None
PRICES: dict[str, dict] = {}
DECS: dict[str, int] = {}
_lock = threading.Lock()
_last_req = [0.0]


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


def _throttle(rate: float) -> None:
    with _lock:
        wait = rate - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


MAJOR_QUOTES = {WSOL, USDC, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}  # SOL/USDC/USDT


def _wmedian(samples: list[tuple[float, float]]) -> float:
    """按流动性加权的价格中位数。"""
    samples = sorted(samples)
    total = sum(w for _, w in samples) or 1.0
    acc = 0.0
    for price, w in samples:
        acc += w
        if acc >= total / 2:
            return price
    return samples[-1][0]


def fetch_price(mint: str) -> dict:
    """定价 v2：top5 交易对按流动性加权中位数，偏好主流计价对，记录离散度。"""
    d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    out = {"price": None, "liq": None, "pairs": 0, "major": False, "dispersion": None}
    if not (d and d.get("pairs")):
        return out

    def liq_usd(p):
        try:
            return float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    pairs = sorted(d["pairs"], key=liq_usd, reverse=True)[:5]
    usable = []
    for p in pairs:
        try:
            price = float(p["priceUsd"])
        except (KeyError, TypeError, ValueError):
            continue
        quote = ((p.get("quoteToken") or {}).get("address") or "")
        usable.append((price, max(liq_usd(p), 1.0), quote in MAJOR_QUOTES))
    if not usable:
        return out
    majors = [u for u in usable if u[2]]
    chosen = majors or usable
    out["price"] = _wmedian([(pr, w) for pr, w, _ in chosen])
    out["liq"] = max(liq_usd(p) for p in pairs)
    out["pairs"] = len(usable)
    out["major"] = bool(majors)
    prices = [pr for pr, _, _ in chosen]
    if min(prices) > 0:
        out["dispersion"] = round(max(prices) / min(prices), 2)
    return out


def fetch_decimals(mint: str) -> int:
    res = HTTP.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    try:
        return int(res["value"]["data"]["parsed"]["info"]["decimals"])
    except Exception:  # noqa: BLE001
        return 9


def prepare(mints: list[str], workers: int, rate: float) -> None:
    """并发补齐价格/精度缓存（mint 级一次）。"""
    now = int(time.time())
    for m in FIXED:
        PRICES.setdefault(m, {"price": None, "liq": None, "at": 0})
    todo_p = [m for m in mints if m not in FIXED
              and (m not in PRICES or now - PRICES[m].get("at", 0) > PRICE_TTL)]
    todo_d = [m for m in mints if m not in DECS]

    def work(m: str):
        _throttle(rate)
        return m, fetch_price(m), fetch_decimals(m)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for m, price, dec in ex.map(work, todo_p):
            PRICES[m] = {**price, "at": now}
            DECS.setdefault(m, dec)
            done += 1
            if done % 50 == 0:
                print(f"  抓取价格/精度 {done}/{len(todo_p)}", flush=True)
    for m in todo_d:
        DECS.setdefault(m, 9)
    if todo_p:
        print(f"  新抓取 {len(todo_p)} 个 mint 的价格", flush=True)


def unit_usd(mint: str, sol: float) -> tuple[float | None, bool]:
    """返回 (每个 raw unit 的 USD, 是否流动性达标)。"""
    if mint in (WSOL, NATIVE):
        return sol / 1e9, True
    if mint == USDC:
        return 1.0 / 1e6, True
    info = PRICES.get(mint) or {}
    if info.get("price") is None:
        return None, False
    return info["price"] / (10 ** DECS.get(mint, 9)), (info.get("liq") or 0) >= MIN_LIQ[0]


MIN_LIQ = [50000.0]


def aggregate(con: sqlite3.Connection, period_fmt: str) -> list[sqlite3.Row]:
    cols = ", ".join(f"total({k}) {k}" for k in LINES)
    return con.execute(f"""
        SELECT period, quote_mint, {cols}, count(*) n
        FROM (
          SELECT *, strftime(?, ts, 'unixepoch') AS period,
                 ROW_NUMBER() OVER (
                   PARTITION BY signature, name, COALESCE(pool, '')
                   ORDER BY rowid) AS rn
          FROM events
          WHERE ts BETWEEN ? AND ? AND quote_mint IS NOT NULL
            AND name IN ({','.join('?' * len(TRADE_EVENTS))})
        )
        WHERE rn = 1
        GROUP BY period, quote_mint
    """, (period_fmt, TS_MIN, TS_MAX, *TRADE_EVENTS)).fetchall()


def accumulate(rows, sol: float) -> dict:
    out: dict[str, dict] = defaultdict(
        lambda: {k: 0.0 for k in LINES}
        | {f"{k}_liq": 0.0 for k in LINES}
        | {"total": 0.0, "total_liq": 0.0, "n": 0,
           "unpriced_mints": set(), "illiquid_mints": set()})
    for r in rows:
        cu, liq_ok = unit_usd(r["quote_mint"], sol)
        d = out[r["period"]]
        d["n"] += r["n"]
        if cu is None:
            d["unpriced_mints"].add(r["quote_mint"])
            continue
        if not liq_ok:
            d["illiquid_mints"].add(r["quote_mint"])
        for k in LINES:
            usd = (r[k] or 0.0) * cu
            d[k] += usd
            d["total"] += usd
            if liq_ok:
                d[f"{k}_liq"] += usd
                d["total_liq"] += usd
    return out


def health(con: sqlite3.Connection) -> dict:
    n, mn, mx = con.execute(
        "SELECT count(*), min(ts), max(ts) FROM events WHERE ts BETWEEN ? AND ?",
        (TS_MIN, TS_MAX)).fetchone()
    now = int(time.time())
    recent = con.execute("SELECT count(*) FROM events WHERE ts > ?", (now - 600,)).fetchone()[0]
    return {"events": n, "first_ts": mn, "last_ts": mx,
            "last_age_s": (now - mx) if mx else None,
            "last_10min_events": recent}


def write_csv(path: pathlib.Path, daily: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "events"] + LINES + ["total"]
                   + [f"{k}_liq" for k in LINES] + ["total_liq",
                     "unpriced_mints", "illiquid_mints"])
        for day in sorted(daily):
            d = daily[day]
            w.writerow([day, d["n"]]
                       + [round(d[k], 2) for k in LINES] + [round(d["total"], 2)]
                       + [round(d[f"{k}_liq"], 2) for k in LINES]
                       + [round(d["total_liq"], 2),
                          len(d["unpriced_mints"]), len(d["illiquid_mints"])])


def report(compare: bool, top: int, min_liq: float, max_mints: int,
           workers: int, rate: float) -> None:
    if not DB.exists():
        raise SystemExit("没有 runtime/stream.sqlite3，先跑 run_stream.sh")
    MIN_LIQ[0] = min_liq
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    PRICES.update(json.loads(PRICE_CACHE.read_text()) if PRICE_CACHE.exists() else {})
    DECS.update(json.loads(DEC_CACHE.read_text()) if DEC_CACHE.exists() else {})
    sol = sol_price()

    daily_rows = aggregate(con, "%Y-%m-%d")
    hourly_rows = aggregate(con, "%Y-%m-%dT%H:00")
    counts: dict[str, int] = defaultdict(int)
    for r in daily_rows + hourly_rows:
        counts[r["quote_mint"]] += r["n"]
    chosen = sorted(counts, key=lambda m: -counts[m])[:max_mints]
    prepare(chosen, workers, rate)

    daily = accumulate(daily_rows, sol)
    hourly = accumulate(hourly_rows, sol)
    h = health(con)
    print(f"价格基准：SOL ${sol:.2f}；{len(daily)} 天 / {len(hourly)} 小时；"
          f"事件 {h['events']:,}（最新 {h['last_age_s']}s 前）；"
          f"定价 mint {len(chosen)}/{len(counts)}")
    head = (f"{'period':21} {'events':>9} {'protocol':>11} {'buyback':>11} "
            f"{'creator':>11} {'lp':>11} {'total':>12} {'liquid':>12}")
    print(head)
    print("-" * len(head))
    for day in sorted(daily):
        d = daily[day]
        print(f"{day:21} {d['n']:>9} {d['protocol_fee']:>11,.0f} {d['buyback_fee']:>11,.0f} "
              f"{d['creator_fee']:>11,.0f} {d['lp_fee']:>11,.0f} {d['total']:>12,.0f} "
              f"{d['total_liq']:>12,.0f}")

    official = None
    try:
        from fetch_official import load_or_fetch
        official = load_or_fetch()
    except Exception:  # noqa: BLE001
        official = None
    if official and official.get("annualized_revenue_m"):
        print(f"  官方看板: 年化 ${official['annualized_revenue_m']}M"
              f"（日均 ${official['daily_avg_m']}M）| 最新日回购 "
              f"${official['daily_buyback_k']}K | 数据截至 {official.get('data_as_of')}")

    # 其他收入线：fee 程序（social/donation/sweep 等）活动计数（IDL 事件无字段）
    fee_events = {r[0]: r[1] for r in con.execute(
        "SELECT name, count(*) FROM events WHERE program='fees' AND ts BETWEEN ? AND ? "
        "GROUP BY name ORDER BY count(*) DESC", (TS_MIN, TS_MAX)).fetchall()}
    if fee_events:
        print(f"  其他收入线活动：{fee_events}")

    # 定价质量：主流计价对比例 / 离散度 / 未定价
    priced = [m for m in chosen if (PRICES.get(m) or {}).get("price") is not None]
    pricing_quality = {
        "chosen": len(chosen), "priced": len(priced),
        "major_quote": sum(1 for m in priced if (PRICES.get(m) or {}).get("major")),
        "high_dispersion": sum(1 for m in priced
                               if ((PRICES.get(m) or {}).get("dispersion") or 0) > 3),
    }
    print(f"  定价质量：{pricing_quality['priced']}/{len(chosen)} 可定价，"
          f"{pricing_quality['major_quote']} 来自主流计价对，"
          f"{pricing_quality['high_dispersion']} 离散>3×")

    dl_cmp: dict = {}
    if compare:
        for slug in ("pump.fun", "pumpswap"):
            d = get_json(f"https://api.llama.fi/summary/fees/{slug}?dataType=dailyRevenue")
            if d:
                dl_cmp[slug] = {k: d.get(k) for k in ("total24h", "total7d", "total30d")}
                print(f"  DefiLlama {slug}: 24h ${d['total24h']/1e6:.2f}M | "
                      f"7d ${d['total7d']/1e6:.2f}M | 30d ${d['total30d']/1e6:.2f}M")

    def clean(o):
        if isinstance(o, set):
            return len(o)
        raise TypeError

    mint_usd: dict[str, float] = defaultdict(float)
    for r in daily_rows:
        cu, _ = unit_usd(r["quote_mint"], sol)
        if cu is None:
            continue
        for k in LINES:
            mint_usd[r["quote_mint"]] += (r[k] or 0.0) * cu

    out = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sol_usd": sol, "min_liquidity": min_liq, "health": h,
        "priced_mints": len(chosen), "total_mints": len(counts),
        "daily": {d: json.loads(json.dumps(v, default=clean))
                  for d, v in sorted(daily.items())},
        "hourly": [{"hour": k, **json.loads(json.dumps(v, default=clean))}
                   for k, v in sorted(hourly.items())],
        "top_mints": [{"mint": m, "usd": round(u, 2)}
                      for m, u in sorted(mint_usd.items(), key=lambda x: -x[1])[:top]],
        "defillama": dl_cmp,
        "official": official,
        "pricing_quality": pricing_quality,
        "fee_events": fee_events,
    }
    PRICE_CACHE.write_text(json.dumps(PRICES, indent=1))
    DEC_CACHE.write_text(json.dumps(DECS, indent=1))
    (ROOT / "stream_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    write_csv(ROOT / "stream_report.csv", daily)
    print(f"写了 {ROOT/'stream_report.json'} 和 {ROOT/'stream_report.csv'}")


def main() -> None:
    global HTTP
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-liquidity", type=float, default=50000)
    ap.add_argument("--max-mints", type=int, default=600, help="最多给多少个 mint 定价")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=0.12, help="外部价格请求最小间隔秒")
    ap.add_argument("--rpc", help="覆盖 RPC（默认 .env 里的 ALCHEMY_RPC_URL）")
    args = ap.parse_args()
    HTTP = make_client(cli=args.rpc, rate=0.02)
    report(args.compare, args.top, args.min_liquidity, args.max_mints,
           args.workers, args.rate)


if __name__ == "__main__":
    main()
