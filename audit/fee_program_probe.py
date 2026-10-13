#!/usr/bin/env python3
"""A1+A2：pump_fees 程序侦察——PDA 推导 + 指令分类 + 资金流采样/聚合。

已确认的机制（官方 SDK 4.0.0 源码 + 链上交易双向验证）：
  - 每笔交易从 8 个 normal 收款地址随机选 1 个收「协议费」，
    从 8 个 buyback 地址随机选 1 个收「回购费」；
  - 两者都以 **quote 资产**支付（SOL 池 = WSOL；自定义交易对 = 任意 SPL token）；
  - 于是收入碎片化在几十万个 token 账户上（实测单地址 25.7~57.1 万个 ATA）。

子命令：
  derive   从 IDL seeds 推导 PDA（纯 Python ed25519 校验）并链上验证
  scan     拉费用程序交易，按 IDL 判别码分类指令（含 inner instructions）
  trades   拉 AMM 交易，聚合 24 个收款地址的 quote 资产入账并外推

RPC 端点：--rpc / ALCHEMY_RPC_URL / SOLANA_RPC_URL / .env
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import hashlib
import json
import pathlib
import time
import urllib.request
from collections import defaultdict

from rpc import make_client

ROOT = pathlib.Path(__file__).resolve().parent
IDL = json.loads((ROOT / "data" / "pump_fees_idl.json").read_text())
PROG = IDL["address"]
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

NORMAL = ["62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV", "7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ",
          "7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX", "9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz",
          "AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY", "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM",
          "FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz", "G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP"]
BUYBACK = ["5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD", "9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7",
           "GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL", "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR",
           "5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6", "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL",
           "5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD", "A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"]
RECIPIENTS = set(NORMAL + BUYBACK)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

CLIENT = None  # 由 main 注入


# ------------------------------------------------------------------ 基础
def b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + n.to_bytes((n.bit_length() + 7) // 8, "big")


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + (out or "")


_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)


def is_on_curve(b: bytes) -> bool:
    if len(b) != 32:
        return False
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    y2 = y * y % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    x2 = u * pow(v, _P - 2, _P) % _P
    if x2 == 0:
        return True
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    return (x * x - x2) % _P == 0


def find_pda(seeds: list[bytes], program: bytes) -> tuple[str, int]:
    for nonce in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([nonce]) + program
                           + b"ProgramDerivedAddress").digest()
        if not is_on_curve(h):
            return b58encode(h), nonce
    raise RuntimeError("no PDA")


def disc_of(name: str) -> bytes:
    return hashlib.sha256(("global:" + name).encode()).digest()[:8]


def _keys(tx: dict) -> list[str]:
    return [k.get("pubkey") if isinstance(k, dict) else k
            for k in (tx.get("transaction") or {}).get("message", {}).get("accountKeys", [])]


def _program_instructions(tx: dict) -> list[tuple[str, list, bytes]]:
    out, keys = [], _keys(tx)
    meta = tx.get("meta") or {}
    msg = (tx.get("transaction") or {}).get("message") or {}

    def walk(ixs):
        for ix in ixs:
            pid = ix.get("programId")
            if not pid and "programIdIndex" in ix:
                i = ix["programIdIndex"]
                pid = keys[i] if i < len(keys) else None
            if pid == PROG and ix.get("data"):
                raw = base64.b64decode(ix["data"] + "=" * (-len(ix["data"]) % 4))
                out.append((raw[:8].hex(),
                            [keys[a] if isinstance(a, int) and a < len(keys) else a
                             for a in ix.get("accounts", [])],
                            raw[8:]))
    walk(msg.get("instructions", []))
    for g in (meta.get("innerInstructions") or []):
        walk(g.get("instructions", []))
    return out


def _fetch_txs(sigs: list[dict], workers: int) -> list[dict]:
    out: list[dict] = []

    def one(s):
        return CLIENT.call("getTransaction", [s["signature"],
                                              {"encoding": "jsonParsed",
                                               "maxSupportedTransactionVersion": 0}])
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(one, sigs):
            if r:
                out.append(r)
    return out


# ------------------------------------------------------------------ 子命令
def cmd_derive() -> None:
    program = b58decode(PROG)
    ok = sum(1 for ix in IDL["instructions"]
             if bytes(ix["discriminator"]) == disc_of(ix["name"]))
    print(f"IDL 校验: {ok}/{len(IDL['instructions'])} 判别码 == sha256(global:name)")
    seeds: list[tuple[str, list[bytes]]] = [
        ("fee_program_global", [b"fee-program-global"]),
        ("event_authority", [b"__event_authority"]),
        ("fee_config", [b"fee_config"]),
        ("donation_fee_pda.base", [b"donation-fee-pda"]),
    ]
    for ix in IDL["instructions"]:
        for acc in ix.get("accounts", []):
            pda = acc.get("pda")
            if not pda:
                continue
            const = [s for s in pda.get("seeds", []) if s.get("kind") == "const"
                     and s.get("value")]
            if const and acc["name"] not in [n for n, _ in seeds]:
                seeds.append((acc["name"], [bytes(const[0]["value"])]))
    out = {}
    for name, sd in seeds:
        addr, nonce = find_pda(sd, program)
        info = CLIENT.call("getAccountInfo", [addr, {"encoding": "base64"}])
        exists = bool(info and info.get("value"))
        out[name] = {"address": addr, "nonce": nonce, "on_chain": exists}
        print(f"  {name:26} {addr}  nonce={nonce}  链上存在={exists}")
    (ROOT / "fee_pdas.json").write_text(json.dumps(
        {"program": PROG, "method": "sha256(seeds+nonce+program+PDA) off-curve",
         "pdas": out}, ensure_ascii=False, indent=1))
    print(f"写了 {ROOT/'fee_pdas.json'}")


def _sigs(addr: str, limit: int) -> list[dict]:
    """分页拉签名（RPC 单次上限 1000）。"""
    out: list[dict] = []
    before = None
    while len(out) < limit:
        opts: dict = {"limit": min(1000, limit - len(out))}
        if before:
            opts["before"] = before
        page = CLIENT.call("getSignaturesForAddress", [addr, opts]) or []
        if not page:
            break
        out.extend(page)
        before = page[-1]["signature"]
    return out[:limit]


def cmd_scan(txs: int, workers: int) -> None:
    disc = {bytes(ix["discriminator"]).hex(): ix["name"] for ix in IDL["instructions"]}
    sigs = _sigs(PROG, txs)
    counts: dict[str, int] = defaultdict(int)
    for tx in _fetch_txs(sigs, workers):
        for h, _, _ in _program_instructions(tx):
            counts[disc.get(h, "UNKNOWN:" + h)] += 1
    print(f"拉取 {len(sigs)} 笔签名，成功解析 {sum(counts.values())} 条费用程序指令")
    for name, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {n:5}  {name}")
    (ROOT / "fee_scan.json").write_text(json.dumps(
        {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "sigs": len(sigs), "counts": dict(counts)}, ensure_ascii=False, indent=1))


def _sol_price() -> float:
    try:
        req = urllib.request.Request(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            headers={"User-Agent": "pulse-audit/0.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return float(json.loads(r.read())["solana"]["usd"])
    except Exception:  # noqa: BLE001
        return 0.0


def _inflows(tx: dict) -> list[tuple[str, str, float]]:
    """返回一笔交易里所有流向 24 个收款地址的正向 token 变化。"""
    meta = tx.get("meta") or {}
    pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or [])}
    out = []
    for b in (meta.get("postTokenBalances") or []):
        p = pre.get(b["accountIndex"], {"uiTokenAmount": {"uiAmountString": "0"},
                                        "owner": b.get("owner")})
        try:
            d = (float(b["uiTokenAmount"]["uiAmountString"] or 0)
                 - float(p["uiTokenAmount"]["uiAmountString"] or 0))
        except (TypeError, ValueError):
            continue
        owner = b.get("owner") or p.get("owner")
        if d > 0 and owner in RECIPIENTS:
            out.append((owner, b.get("mint"), d))
    return out


def cmd_trades(per_address: int, workers: int) -> None:
    """扫 24 个收款地址的交易（去重），聚合 quote 资产入账并外推。

    Alchemy 对程序地址的签名索引为空，所以从收款地址入口扫；同一笔交易可能
    被多个地址引用，用签名去重。normal 与 buyback 各拿一份，数值应大致相等。
    """
    sigs: dict[str, str] = {}
    for a in NORMAL + BUYBACK:
        for s in _sigs(a, per_address):
            sigs.setdefault(s["signature"], a)
    todo = [{"signature": k} for k in sigs]
    print(f"收款地址签名去重后 {len(todo)} 笔，开始拉取…", flush=True)

    sol_usd = _sol_price()
    per = defaultdict(lambda: {"count": 0, "mints": defaultdict(float)})
    times: list[int] = []
    priced_usd = 0.0
    unpriced_usd_mints: dict[str, float] = defaultdict(float)
    for tx in _fetch_txs(todo, workers):
        flows = _inflows(tx)
        if not flows:
            continue
        bt = tx.get("blockTime") or 0
        if bt:
            times.append(bt)
        for owner, mint, delta in flows:
            role = "buyback" if owner in BUYBACK else "normal"
            per[role]["count"] += 1
            per[role]["mints"][mint] += delta
            if mint == WSOL and sol_usd:
                priced_usd += delta * sol_usd
            elif mint == USDC:
                priced_usd += delta
            else:
                unpriced_usd_mints[mint] += delta

    span = (max(times) - min(times)) if len(times) > 1 else 0
    rate = (priced_usd / span) if span > 0 else 0.0
    print(f"命中含入账的交易 {sum(d['count'] for d in per.values())} 条，"
          f"采样窗口 {span/60:.1f} 分钟（{len(times)} 笔有时戳）")
    for role, d in per.items():
        top = sorted(d["mints"].items(), key=lambda x: -x[1])[:6]
        print(f"  {role:8}: {d['count']} 笔，涉及 {len(d['mints'])} 种 quote 资产")
        for m, v in top:
            tag = " (WSOL)" if m == WSOL else (" (USDC)" if m == USDC else "")
            print(f"      {str(m)[:16]}… +{v:.6f}{tag}")
    print(f"  可定价入账（WSOL×${sol_usd:.0f} + USDC）: ${priced_usd:.4f}"
          f" → 外推 ${rate*86400:,.0f}/天（±采样误差）")
    print(f"  不可定价 quote 资产种类: {len(unpriced_usd_mints)}（只统计数量，无法估值）")
    (ROOT / "fee_flows.json").write_text(json.dumps({
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "per_address": per_address, "unique_txs": len(todo),
        "span_s": span, "sol_usd": sol_usd,
        "per_role": {k: {"count": v["count"],
                         "mints": {str(m): round(x, 9)
                                   for m, x in sorted(v["mints"].items(),
                                                      key=lambda x: -x[1])}}
                     for k, v in per.items()},
        "unpriced_mint_count": len(unpriced_usd_mints),
        "priced_usd": round(priced_usd, 4),
        "priced_usd_per_day": round(rate * 86400, 2),
    }, ensure_ascii=False, indent=1))


def main() -> None:
    global CLIENT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", help="覆盖 RPC 端点（默认读 ALCHEMY_RPC_URL / .env）")
    ap.add_argument("--rate", type=float, default=0.02, help="最小请求间隔秒")
    ap.add_argument("--workers", type=int, default=12)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("derive")
    sp = sub.add_parser("scan")
    sp.add_argument("--txs", type=int, default=60)
    sp = sub.add_parser("trades")
    sp.add_argument("--per-address", type=int, default=200,
                    help="每个收款地址取样签名数（去重后拉交易）")
    args = ap.parse_args()
    CLIENT = make_client(cli=args.rpc, rate=args.rate)
    if args.cmd == "derive":
        cmd_derive()
    elif args.cmd == "scan":
        cmd_scan(args.txs, args.workers)
    elif args.cmd == "trades":
        cmd_trades(args.per_address, args.workers)


if __name__ == "__main__":
    main()
