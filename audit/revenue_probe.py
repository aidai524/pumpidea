#!/usr/bin/env python3
"""链上直读 pump.fun 费用收款地址的流水（一手数据，不经过任何第三方）。

地址来源：pump-fun/pump-public-docs `docs/FEE_RECIPIENTS.md`（24 个公开地址）。
方法：对每个地址拉签名 → 拉交易 → 用 pre/postBalances 的差值算入账/扫出。
     balance delta 不依赖任何程序解析，直接度量"钱有没有进这个账户"。

用法：
  python revenue_probe.py --snapshot                 # 只读 24 个地址余额（秒级）
  python revenue_probe.py --hours 6 --sample 80      # 每地址最多采样 80 笔
  python revenue_probe.py --addresses normal --hours 3

说明：公共 RPC 限速且有历史窗口；采样模式会按"采样时段"外推全天，结果标注
extrapolated=true。生产化要么用付费 RPC 全量扫，要么自建 Geyser 流。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import time
from collections import defaultdict

from rpc import make_client

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "revenue_probe.json"
CLIENT = None

NORMAL = ["62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV",
          "7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ",
          "7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX",
          "9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz",
          "AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY",
          "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM",
          "FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz",
          "G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP"]
MAYHEM = ["GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS",
          "4budycTjhs9fD6xw62VBducVTNgMgJJ5BgtKq7mAZwn6",
          "8SBKzEQU4nLSzcwF4a74F2iaUDQyTfjGndn6qUWBnrpR",
          "4UQeTP1T39KZ9Sfxzo3WR5skgsaP6NZa87BAkuazLEKH",
          "8sNeir4QsLsJdYpc9RZacohhK1Y5FLU3nC5LXgYB4aa6",
          "Fh9HmeLNUMVCvejxCtCL2DbYaRyBFVJ5xrWkLnMH6fdk",
          "463MEnMeGyJekNZFQSTUABBEbLnvMTALbT6ZmsxAbAdq",
          "6AUH3WEHucYZyC61hqpqYUWVto5qA5hjHuNQ32GNnNxA"]
BUYBACK = ["5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD",
           "9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7",
           "GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL",
           "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR",
           "5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6",
           "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL",
           "5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD",
           "A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"]
GROUPS = {"normal": NORMAL, "mayhem": MAYHEM, "buyback": BUYBACK}

def rpc(method: str, params: list):
    return CLIENT.call(method, params)


def balance(addr: str) -> float:
    return rpc("getBalance", [addr])["value"] / 1e9


def signatures(addr: str, before: str | None = None, limit: int = 1000) -> list[dict]:
    opts: dict = {"limit": limit}
    if before:
        opts["before"] = before
    return rpc("getSignaturesForAddress", [addr, opts])


def tx_delta(addr: str, sig: str) -> tuple[float, int, int] | None:
    """返回 (净变化 SOL, blockTime, 交易费?)。None = 拉不到。"""
    res = rpc("getTransaction", [sig, {"encoding": "jsonParsed",
                                       "maxSupportedTransactionVersion": 0}])
    if not res:
        return None
    meta = res.get("meta") or {}
    msg = (res.get("transaction") or {}).get("message") or {}
    keys = [k.get("pubkey") if isinstance(k, dict) else k
            for k in msg.get("accountKeys", [])]
    if addr not in keys:
        return None
    i = keys.index(addr)
    pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
    if i >= len(pre) or i >= len(post):
        return None
    bt = res.get("blockTime") or 0
    return (post[i] - pre[i]) / 1e9, int(bt), int(meta.get("fee") or 0)


def probe_address(addr: str, hours: float, sample: int, workers: int) -> dict:
    cutoff = time.time() - hours * 3600
    sigs: list[dict] = []
    before = None
    while len(sigs) < sample:
        page = signatures(addr, before=before, limit=min(1000, sample - len(sigs)))
        if not page:
            break
        sigs.extend(page)
        before = page[-1]["signature"]
        if (page[-1].get("blockTime") or 0) < cutoff:
            break
    sigs = [s for s in sigs if (s.get("blockTime") or 0) >= cutoff][:sample]
    if not sigs:
        return {"address": addr, "txs": 0, "inflow_sol": 0.0, "outflow_sol": 0.0,
                "span_s": 0, "span_from": None, "span_to": None,
                "per_day_inflow_sol": None, "extrapolated": False}
    events = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(tx_delta, addr, s["signature"]): s for s in sigs}
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except Exception:  # noqa: BLE001
                r = None
            if r:
                events.append(r)
    inflow = sum(d for d, _, _ in events if d > 0)
    outflow = -sum(d for d, _, _ in events if d < 0)
    times = [bt for _, bt, _ in events if bt]
    span = (max(times) - min(times)) if times else 0
    per_day = (inflow / span * 86400) if span > 0 else None
    return {
        "address": addr, "txs": len(events),
        "inflow_sol": round(inflow, 6), "outflow_sol": round(outflow, 6),
        "net_sol": round(inflow - outflow, 6),
        "span_s": span,
        "span_from": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(min(times))) if times else None,
        "span_to": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(times))) if times else None,
        "per_day_inflow_sol": round(per_day, 1) if per_day else None,
        "extrapolated": True,
        "daily": _daily(events),
    }


def _daily(events: list[tuple[float, int, int]]) -> dict:
    out: dict[str, dict] = defaultdict(lambda: {"inflow_sol": 0.0, "outflow_sol": 0.0,
                                                "txs": 0})
    for d, bt, _ in events:
        day = time.strftime("%Y-%m-%d", time.gmtime(bt))
        if d > 0:
            out[day]["inflow_sol"] += d
        else:
            out[day]["outflow_sol"] += -d
        out[day]["txs"] += 1
    return {k: {kk: round(vv, 6) if isinstance(vv, float) else vv
                for kk, vv in v.items()} for k, v in sorted(out.items())}


def main() -> None:
    ap = argparse.ArgumentParser(description="pump.fun fee recipients on-chain probe")
    ap.add_argument("--snapshot", action="store_true", help="只读余额")
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--sample", type=int, default=80, help="每地址最多采样交易数")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rpc", help="覆盖 RPC 端点（默认读 ALCHEMY_RPC_URL / .env）")
    ap.add_argument("--rate", type=float, default=0.02, help="最小请求间隔秒")
    ap.add_argument("--addresses", choices=["all", *GROUPS], default="all")
    args = ap.parse_args()
    global CLIENT
    CLIENT = make_client(cli=args.rpc, rate=args.rate)

    groups = GROUPS if args.addresses == "all" else {args.addresses: GROUPS[args.addresses]}
    result: dict = {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "method": "balance delta (pre/postBalances) on published fee recipients",
                    "hours": args.hours, "sample_per_address": args.sample,
                    "addresses": {}, "totals": {}}

    for gname, addrs in groups.items():
        rows = []
        t0 = time.time()
        for i, a in enumerate(addrs, 1):
            bal = balance(a)
            if args.snapshot:
                rows.append({"address": a, "balance_sol": round(bal, 3)})
                print(f"  [{gname} {i}/8] {a[:10]}… {bal:,.1f} SOL")
                continue
            r = probe_address(a, args.hours, args.sample, args.workers)
            r["balance_sol"] = round(bal, 3)
            rows.append(r)
            print(f"  [{gname} {i}/8] {a[:10]}… bal={bal:,.1f} SOL  采样 {r['txs']} 笔  "
                  f"入账 {r['inflow_sol']:.4f}  扫出 {r['outflow_sol']:.4f}  "
                  f"外推/天 {r['per_day_inflow_sol']}")
        result["addresses"][gname] = rows
        if not args.snapshot:
            result["totals"][gname] = {
                "balance_sol": round(sum(x["balance_sol"] for x in rows), 1),
                "inflow_sol": round(sum(x["inflow_sol"] for x in rows), 4),
                "outflow_sol": round(sum(x["outflow_sol"] for x in rows), 4),
                "per_day_inflow_sol": round(sum(x["per_day_inflow_sol"] or 0
                                                for x in rows), 1),
                "txs": sum(x["txs"] for x in rows),
            }
        else:
            result["totals"][gname] = {"balance_sol":
                                       round(sum(x["balance_sol"] for x in rows), 1)}
        print(f"  → {gname}: {time.time()-t0:.0f}s\n")

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"写了 {OUT}")
    if not args.snapshot:
        for g, t in result["totals"].items():
            print(f"  {g:8}: 采样入账 {t['inflow_sol']:.3f} SOL，"
                  f"外推 {t['per_day_inflow_sol']:,.0f} SOL/天 "
                  f"≈ ${t['per_day_inflow_sol']*109:,.0f}/天（按 $109/SOL）")


if __name__ == "__main__":
    main()
