#!/usr/bin/env python3
"""给 fee_flows.json 里的长尾 quote 资产定价，输出 USD 收入估算。

价格来源：
  WSOL → CoinGecko SOL 价；USDC → 1；其余 mint → DexScreener 最优流动性交易对。
缓存写 data/dexscreener_prices_<date>.json（可复跑，不重复请求）。
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
FLOWS = ROOT / "fee_flows.json"
CACHE = ROOT / "data" / f"dexscreener_prices_{time.strftime('%Y-%m-%d')}.json"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def get_json(url: str, timeout: int = 20) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pulse-audit/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def dex_price(mint: str, cache: dict) -> float | None:
    if mint in cache:
        return cache[mint]
    d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    price = None
    if d and d.get("pairs"):
        best = max(d["pairs"], key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        try:
            price = float(best["priceUsd"])
        except (KeyError, TypeError, ValueError):
            price = None
    cache[mint] = price
    time.sleep(0.25)
    return price


def main() -> None:
    flows = json.loads(FLOWS.read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    sol_usd = float(flows.get("sol_usd") or 0)
    total_usd = 0.0
    by_role: dict[str, dict] = {}
    for role, data in flows["per_role"].items():
        role_usd = 0.0
        priced = unpriced = 0
        top: list[tuple[str, float, float | None, float]] = []
        for mint, qty in data["mints"].items():
            if mint == WSOL:
                p = sol_usd
            elif mint == USDC:
                p = 1.0
            else:
                p = dex_price(mint, cache)
            if p is None:
                unpriced += 1
                top.append((mint, qty, None, 0.0))
                continue
            priced += 1
            usd = qty * p
            role_usd += usd
            top.append((mint, qty, p, usd))
        total_usd += role_usd
        top.sort(key=lambda x: -x[3])
        by_role[role] = {"usd": role_usd, "priced_mints": priced,
                         "unpriced_mints": unpriced,
                         "top": [{"mint": m, "amount": q, "price_usd": p, "usd": u}
                                 for m, q, p, u in top[:8]]}
        print(f"{role}: ${role_usd:,.2f}（定价 {priced} / 未定价 {unpriced} 种）")
        for m, q, p, u in top[:4]:
            ptxt = f"${p:.6f}" if p is not None else "无价格"
            print(f"    {m[:16]}… {q:.2f} × {ptxt} = ${u:,.2f}")
    span = flows.get("span_s") or 0
    per_day = total_usd / span * 86400 if span else 0.0
    print(f"\n合计 ${total_usd:,.2f} / {span/60:.1f} 分钟 → 外推 ${per_day:,.0f}/天")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    (ROOT / "fee_flows_priced.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_flows": str(FLOWS.name), "span_s": span, "sol_usd": sol_usd,
        "total_usd": round(total_usd, 2), "per_day_usd": round(per_day, 0),
        "by_role": by_role, "price_cache": str(CACHE.name),
    }, ensure_ascii=False, indent=1))
    print(f"写了 {ROOT/'fee_flows_priced.json'}")


if __name__ == "__main__":
    main()
