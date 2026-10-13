#!/usr/bin/env python3
"""A1+A2：pump_fees 程序侦察——PDA 推导 + 指令分类 + 资金流采样。

已确认的机制（来自官方 SDK 源码 + 链上交易）：
  - 每笔交易：从 8 个 normal 收款地址随机选 1 个收「协议费」，
    从 8 个 buyback 地址随机选 1 个收「回购费」；
  - 两者都以 **quote 资产** 支付（SOL 池 = WSOL；自定义交易对 = 任意 SPL token）；
  - 于是每个收款地址都有海量 token 账户（实测 25~57 万个/地址），
    收入碎片化在几十万 quote mint 上——这正是官方看板在 custom pairs 后失真的结构原因。

本脚本：
  derive   —— 从 IDL 的 seeds 推导 PDA（纯 Python ed25519 校验），并链上验证存在
  scan     —— 拉费用程序交易，按 IDL 判别码分类指令（含 inner instructions）
  trades   —— 拉 AMM 交易，统计收款地址的 token 入账（quote 资产维度）

用法：
  python fee_program_probe.py derive
  python fee_program_probe.py scan --txs 30
  python fee_program_probe.py trades --txs 8
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

ROOT = pathlib.Path(__file__).resolve().parent
IDL = json.loads((ROOT / "data" / "pump_fees_idl.json").read_text())
PROG = IDL["address"]
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
RPC = "https://api.mainnet-beta.solana.com"

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
    """ed25519 解压缩校验：PDA 要求哈希不在曲线上。"""
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


def rpc(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(RPC, data=body,
                                 headers={"Content-Type": "application/json"})
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            if "error" in d and "429" in str(d["error"]):
                time.sleep(1.5 * (a + 1))
                continue
            return d.get("result")
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (a + 1))
    return None


def disc_of(name: str) -> bytes:
    return hashlib.sha256(("global:" + name).encode()).digest()[:8]


# ------------------------------------------------------------------ derive
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
    # IDL 里显式写出的 pda seeds（取第一个常量种子）
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
        info = rpc("getAccountInfo", [addr, {"encoding": "base64"}])
        exists = bool(info and info.get("value"))
        out[name] = {"address": addr, "nonce": nonce, "on_chain": exists}
        print(f"  {name:26} {addr}  nonce={nonce}  链上存在={exists}")
    (ROOT / "fee_pdas.json").write_text(json.dumps(
        {"program": PROG, "method": "sha256(seeds+nonce+program+PDA) off-curve",
         "pdas": out}, ensure_ascii=False, indent=1))
    print(f"写了 {ROOT/'fee_pdas.json'}")


# ------------------------------------------------------------------ 通用扫描
def _program_instructions(tx: dict, keys: list[str]) -> list[tuple[str, list[str], bytes]]:
    out = []
    meta = tx.get("meta") or {}
    msg = (tx.get("transaction") or {}).get("message") or {}

    def walk(ixs):
        for ix in ixs:
            pid = ix.get("programId")
            if not pid and "programIdIndex" in ix:
                pid = keys[ix["programIdIndex"]] if ix["programIdIndex"] < len(keys) else None
            if pid == PROG and ix.get("data"):
                raw = base64.b64decode(ix["data"] + "=" * (-len(ix["data"]) % 4))
                accs = [keys[a] if isinstance(a, int) and a < len(keys) else a
                        for a in ix.get("accounts", [])]
                out.append((raw[:8].hex(), accs, raw[8:]))
    walk(msg.get("instructions", []))
    for g in (meta.get("innerInstructions") or []):
        walk(g.get("instructions", []))
    return out


def cmd_scan(txs: int) -> None:
    disc = {bytes(ix["discriminator"]).hex(): ix["name"] for ix in IDL["instructions"]}
    sigs = rpc("getSignaturesForAddress", [PROG, {"limit": txs}]) or []
    counts: dict[str, int] = {}
    parsed = 0
    for s in sigs:
        tx = rpc("getTransaction", [s["signature"],
                                    {"encoding": "jsonParsed",
                                     "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        keys = [k.get("pubkey") if isinstance(k, dict) else k
                for k in (tx.get("transaction") or {}).get("message", {}).get("accountKeys", [])]
        for h, accs, _ in _program_instructions(tx, keys):
            name = disc.get(h, "UNKNOWN:" + h)
            counts[name] = counts.get(name, 0) + 1
        parsed += 1
    print(f"拉取 {len(sigs)} 笔签名，成功解析 {parsed} 笔")
    for name, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {name}")
    (ROOT / "fee_scan.json").write_text(json.dumps(
        {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "sigs": len(sigs), "parsed": parsed, "counts": counts},
        ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ 资金流
def cmd_trades(txs: int) -> None:
    """拉 AMM 交易，统计 24 个收款地址的 token 入账（quote 维度）。"""
    sigs = rpc("getSignaturesForAddress", [AMM, {"limit": txs}]) or []
    rows = []
    for s in sigs:
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed",
                                                     "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        meta = tx.get("meta") or {}
        pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or [])}
        for b in (meta.get("postTokenBalances") or []):
            p = pre.get(b["accountIndex"], {"uiTokenAmount": {"uiAmountString": "0"},
                                            "owner": b.get("owner")})
            try:
                delta = (float(b["uiTokenAmount"]["uiAmountString"] or 0)
                         - float(p["uiTokenAmount"]["uiAmountString"] or 0))
            except (TypeError, ValueError):
                continue
            owner = b.get("owner") or p.get("owner")
            if delta > 0 and owner in RECIPIENTS:
                rows.append({"tx": s["signature"], "owner": owner,
                             "role": "buyback" if owner in BUYBACK else "normal",
                             "mint": b.get("mint"), "delta": delta})
    print(f"AMM 交易 {len(sigs)} 笔，收款地址 token 入账 {len(rows)} 条")
    for r in rows[:12]:
        print(f"  {r['role']:8} {r['owner'][:10]}… mint={str(r['mint'])[:10]}… +{r['delta']:.6f}")
    (ROOT / "fee_flows.json").write_text(json.dumps(
        {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "txs": len(sigs), "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("derive")
    sp = sub.add_parser("scan")
    sp.add_argument("--txs", type=int, default=30)
    sp = sub.add_parser("trades")
    sp.add_argument("--txs", type=int, default=8)
    args = ap.parse_args()
    if args.cmd == "derive":
        cmd_derive()
    elif args.cmd == "scan":
        cmd_scan(args.txs)
    else:
        cmd_trades(args.txs)
