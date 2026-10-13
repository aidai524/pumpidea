#!/usr/bin/env python3
"""流式采集 pump.fun 费用事件：logsSubscribe + Anchor 事件解析 → SQLite。

为什么不需要逐笔拉交易：AMM 的 Buy/SellEvent 与 curve 的 TradeEvent 里
直接带 protocol/creator/buyback/lp/cashback/holder 费用与收款地址；
事件的判别码 = sha256("event:"+name)[:8]（两个程序 87/87 验证通过）。

用法：
  python3 stream_collector.py                 # 一直跑
  python3 stream_collector.py --minutes 30    # 跑 30 分钟
  python3 stream_collector.py --report        # 汇总已采集事件

WebSocket 端点：ALCHEMY_WS_URL，或从 ALCHEMY_RPC_URL 把 https 换成 wss。
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import pathlib
import signal
import sqlite3
import time

import websockets

from rpc import load_env, make_client

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
DB = RUNTIME / "stream.sqlite3"

AMM = json.loads((ROOT / "data" / "pump_amm_idl.json").read_text())
PUMP = json.loads((ROOT / "data" / "pump_idl.json").read_text())
PROGRAMS = [AMM["address"], PUMP["address"]]

# 事件判别码 -> (program, event name)
EVENTS: dict[bytes, tuple[str, str]] = {}
TYPES: dict[tuple[str, str], list] = {}
for _idl in (AMM, PUMP):
    for _e in _idl["events"]:
        EVENTS[bytes(_e["discriminator"])] = (_idl["address"], _e["name"])
    for _t in _idl["types"]:
        _fields = ((_t.get("type") or {}).get("fields")) or []
        TYPES[(_idl["address"], _t["name"])] = _fields

ACCOUNT_DISC = {(p, name): hashlib.sha256(("account:" + name).encode()).digest()[:8]
                for p, name in ([(AMM["address"], t["name"]) for t in AMM["types"]]
                                + [(PUMP["address"], t["name"]) for t in PUMP["types"]])}

HTTP = make_client(rate=0.02)
SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  signature TEXT, program TEXT, name TEXT, slot INTEGER, ts INTEGER,
  pool TEXT, mint TEXT, quote_mint TEXT, quote_amount INTEGER,
  protocol_fee INTEGER, creator_fee INTEGER, buyback_fee INTEGER,
  lp_fee INTEGER, cashback INTEGER, holder_rewards INTEGER, fields TEXT,
  collected_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS pools(
  pool TEXT PRIMARY KEY, base_mint TEXT, quote_mint TEXT,
  base_decimals INTEGER, quote_decimals INTEGER, first_seen INTEGER
);
"""


# ------------------------------------------------------------------ borsh
def read_type(data: bytes, off: int, t, program: str):
    if isinstance(t, dict):
        if "vec" in t:
            n = int.from_bytes(data[off:off + 4], "little")
            off += 4
            items = []
            for _ in range(n):
                v, off = read_type(data, off, t["vec"], program)
                items.append(v)
            return items, off
        if "option" in t:
            flag = data[off]
            off += 1
            if flag == 0:
                return None, off
            return read_type(data, off, t["option"], program)
        if "defined" in t:
            return read_type(data, off, t["defined"], program)
        if "array" in t:
            elem, n = t["array"]
            items = []
            for _ in range(n):
                v, off = read_type(data, off, elem, program)
                items.append(v)
            return items, off
        return None, off
    if t in ("u8", "i8", "bool"):
        v = data[off]
        return (bool(v) if t == "bool" else v), off + 1
    if t in ("u16", "i16"):
        return int.from_bytes(data[off:off + 2], "little"), off + 2
    if t in ("u32", "i32"):
        return int.from_bytes(data[off:off + 4], "little"), off + 4
    if t in ("u64", "i64"):
        return int.from_bytes(data[off:off + 8], "little"), off + 8
    if t in ("u128", "i128"):
        return int.from_bytes(data[off:off + 16], "little",
                             signed=(t == "i128")), off + 16
    if t == "pubkey":
        return base58(data[off:off + 32]), off + 32
    if t == "string":
        n = int.from_bytes(data[off:off + 4], "little")
        return data[off + 4:off + 4 + n].decode("utf-8", "replace"), off + 4 + n
    if t == "bytes":
        n = int.from_bytes(data[off:off + 4], "little")
        return base64.b64encode(data[off + 4:off + 4 + n]).decode(), off + 4 + n
    fields = TYPES.get((program, t))
    if fields is not None:
        out = {}
        off2 = off
        for f in fields:
            out[f["name"]], off2 = read_type(data, off2, f["type"], program)
        return out, off2
    return None, off


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + (out or "")


def decode_event(program: str, name: str, raw: bytes) -> dict | None:
    fields = TYPES.get((program, name))
    if fields is None:
        return None
    out, _ = read_type(raw, 8, name, program)
    return out if isinstance(out, dict) else None


# ------------------------------------------------------------------ 池子
POOL_CACHE: dict[str, tuple] = {}


def pool_mints(pool: str) -> tuple | None:
    if pool in POOL_CACHE:
        return POOL_CACHE[pool]
    info = HTTP.call("getAccountInfo", [pool, {"encoding": "base64"}])
    if not info or not info.get("value"):
        return None
    data = base64.b64decode(info["value"]["data"][0])
    if data[:8] != ACCOUNT_DISC[(AMM["address"], "Pool")]:
        return None
    fields = TYPES[(AMM["address"], "Pool")]
    obj, _ = read_type(data, 8, "Pool", AMM["address"])
    res = (obj.get("base_mint"), obj.get("quote_mint"),
           obj.get("base_mint_decimals", 9), obj.get("quote_mint_decimals", 9))
    POOL_CACHE[pool] = res
    return res


# ------------------------------------------------------------------ 事件落库
SQLITE_MAX = 2 ** 63 - 1


def _num(v):
    """u64/i128 会超出 SQLite INTEGER；超出就用 float。"""
    if v is None or isinstance(v, float):
        return v
    return int(v) if abs(v) <= SQLITE_MAX else float(v)


def normalize(program: str, name: str, ev: dict, sig: str, slot: int) -> dict:
    is_amm = program == AMM["address"]
    ts = int(ev.get("timestamp") or time.time())
    if not (1_600_000_000 <= ts <= 2_000_000_000):   # 年 2020~2033，之外视为脏数据
        ts = int(time.time())
    row = {"signature": sig, "program": "amm" if is_amm else "curve",
           "name": name, "slot": slot, "ts": ts,
           "pool": ev.get("pool"), "mint": ev.get("mint"), "quote_mint": ev.get("quote_mint"),
           "quote_amount": _num(ev.get("quote_amount") or ev.get("quote_amount_in")
                                or ev.get("quote_amount_out") or ev.get("sol_amount")),
           "protocol_fee": _num(ev.get("protocol_fee", ev.get("fee"))),
           "creator_fee": _num(ev.get("coin_creator_fee", ev.get("creator_fee"))),
           "buyback_fee": _num(ev.get("buyback_fee")), "lp_fee": _num(ev.get("lp_fee")),
           "cashback": _num(ev.get("cashback")),
           "holder_rewards": _num(ev.get("holder_rewards")),
           "fields": json.dumps({k: v for k, v in ev.items() if not isinstance(v, dict)},
                                ensure_ascii=False)}
    if is_amm and row["pool"]:
        pm = pool_mints(row["pool"])
        if pm:
            row["mint"], row["quote_mint"] = pm[0], pm[1]
    return row


def parse_logs(con: sqlite3.Connection, sig: str, slot: int, logs: list[str],
               pending: list) -> int:
    n = 0
    for line in logs:
        if not line.startswith("Program data: "):
            continue
        try:
            raw = base64.b64decode(line[len("Program data: "):])
        except Exception:  # noqa: BLE001
            continue
        hit = EVENTS.get(raw[:8])
        if not hit:
            continue
        program, name = hit
        ev = decode_event(program, name, raw)
        if not ev:
            continue
        pending.append(normalize(program, name, ev, sig, slot))
        n += 1
    return n


FLUSH_EVERY = 50


def flush(con: sqlite3.Connection, pending: list) -> None:
    if not pending:
        return
    con.executemany(
        """INSERT INTO events(signature,program,name,slot,ts,pool,mint,quote_mint,
             quote_amount,protocol_fee,creator_fee,buyback_fee,lp_fee,cashback,
             holder_rewards,fields,collected_at)
           VALUES(:signature,:program,:name,:slot,:ts,:pool,:mint,:quote_mint,
             :quote_amount,:protocol_fee,:creator_fee,:buyback_fee,:lp_fee,:cashback,
             :holder_rewards,:fields,:collected_at)""",
        [{**r, "collected_at": int(time.time())} for r in pending])
    for r in pending:
        if r["pool"] and r["pool"] in POOL_CACHE:
            b, q, bd, qd = POOL_CACHE[r["pool"]]
            con.execute("INSERT OR REPLACE INTO pools VALUES(?,?,?,?,?,?)",
                        (r["pool"], b, q, bd, qd, int(time.time())))
    con.commit()
    pending.clear()


# ------------------------------------------------------------------ 订阅
def ws_url() -> str:
    load_env()
    import os
    u = os.environ.get("ALCHEMY_WS_URL") or os.environ.get("SOLANA_WS_URL") or ""
    if u:
        return u
    rpc_url = os.environ.get("ALCHEMY_RPC_URL") or os.environ.get("SOLANA_RPC_URL") or ""
    if rpc_url:
        return rpc_url.replace("https://", "wss://").replace("http://", "ws://")
    raise SystemExit("没有 WS 端点：设置 ALCHEMY_WS_URL 或 ALCHEMY_RPC_URL")


async def collector(minutes: float, log_every: int) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.commit()
    pending: list = []
    stop_at = time.time() + minutes * 60 if minutes else 0
    total = 0
    started = time.time()
    backoff = 1
    while True:
        if stop_at and time.time() > stop_at:
            break
        try:
            async with websockets.connect(ws_url(), ping_interval=20,
                                          max_size=2 ** 24) as ws:
                subs: dict[int, str] = {}
                for i, prog in enumerate(PROGRAMS, start=1):
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                        "params": [{"mentions": [prog]}, {"commitment": "confirmed"}]}))
                print(f"[{time.strftime('%H:%M:%S')}] 已连接，订阅 {len(PROGRAMS)} 个程序",
                      flush=True)
                while True:
                    if stop_at and time.time() > stop_at:
                        break
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    msg = json.loads(raw)
                    if "method" in msg and msg["method"] == "logsNotification":
                        val = msg["params"]["result"]["value"]
                        if val.get("err"):
                            continue
                        total += parse_logs(con, val.get("signature", ""),
                                            msg["params"]["result"].get("context", {}).get("slot", 0),
                                            val.get("logs") or [], pending)
                        if len(pending) >= FLUSH_EVERY:
                            flush(con, pending)
                    if log_every and time.time() - started >= log_every:
                        flush(con, pending)
                        print(f"[{time.strftime('%H:%M:%S')}] 事件 {total}"
                              f"（DB {con.execute('select count(*) from events').fetchone()[0]}）",
                              flush=True)
                        started = time.time()
            backoff = 1
        except Exception as exc:  # noqa: BLE001
            flush(con, pending)
            print(f"[{time.strftime('%H:%M:%S')}] 连接中断（{type(exc).__name__}），"
                  f"{backoff}s 后重连", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
    flush(con, pending)
    print(f"结束：共解析事件 {total}，DB {con.execute('select count(*) from events').fetchone()[0]} 条")


# ------------------------------------------------------------------ 汇总
def report() -> None:
    if not DB.exists():
        raise SystemExit("还没有 stream.sqlite3")
    con = sqlite3.connect(DB)
    rows = con.execute("""SELECT program, name, quote_mint, count(*),
                                 sum(protocol_fee), sum(creator_fee),
                                 sum(buyback_fee), sum(lp_fee), sum(cashback),
                                 sum(holder_rewards)
                          FROM events WHERE ts > 0
                          GROUP BY program, name, quote_mint
                          ORDER BY count(*) DESC LIMIT 30""").fetchall()
    print(f"{'program':7} {'event':22} {'quote_mint':14} {'n':>7} "
          f"{'protocol':>14} {'creator':>14} {'buyback':>14}")
    for r in rows:
        print(f"{r[0]:7} {r[1]:22} {str(r[2])[:12]:14} {r[3]:>7} "
              f"{(r[4] or 0):>14} {(r[5] or 0):>14} {(r[6] or 0):>14}")
    total = con.execute("select count(*) from events").fetchone()[0]
    span = con.execute("select max(ts)-min(ts) from events").fetchone()[0]
    print(f"\n事件总数 {total}，时间跨度 {span or 0}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=float, default=0, help="0 = 一直跑")
    ap.add_argument("--log-every", type=int, default=60)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        report()
        return
    try:
        asyncio.run(collector(args.minutes, args.log_every))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
