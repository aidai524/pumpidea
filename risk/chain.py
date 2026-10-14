"""链上读取：bonding curve、创建者持仓、mint 供应、**早期特征**。

已适配两种 curve 布局：
  v1（旧，81 字节）/ v2（新，166 字节，带 quote_mint 与费率字段）。

早期特征（对齐数据集 f10_* 的口径，来自创建交易 + 最早若干交易的事件）：
  dev_buy_sol        创建者的第一笔买入（SOL）
  f10_n_buys         前 10 秒内的买入笔数
  f10_bundle_wallets 创建交易与紧接一笔里的不同买家数（捆绑近似）
  f10_rs             前 10 秒末的曲线储备（无则用当前储备）
  f10_insider_share  前 20 大持有人中非曲线/非池子地址的占比（近似）
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
for _cand in (ROOT.parent / "audit", ROOT.parent):
    if (_cand / "rpc.py").exists():
        sys.path.insert(0, str(_cand))
        break
from rpc import make_client  # noqa: E402

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
NATIVE = "11111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# ---- IDL（本地/部署两种目录布局都试） ----
_IDL_PATHS = [ROOT / "data" / "pump_idl.json",
              ROOT.parent / "data" / "pump_idl.json",
              ROOT.parent / "audit" / "data" / "pump_idl.json"]
_PUMP_IDL = None
for _p in _IDL_PATHS:
    if _p.exists():
        _PUMP_IDL = json.loads(_p.read_text())
        break
STREAM_DB_CANDIDATES = [
    pathlib.Path("/opt/pumpfun-stream/runtime/stream.sqlite3"),
    ROOT.parent / "audit" / "runtime" / "stream.sqlite3",
    ROOT.parent / "runtime" / "stream.sqlite3",
]
STREAM_DB = next((p for p in STREAM_DB_CANDIDATES if p.exists()), None)

EVENTS: dict[bytes, str] = {}
TYPES: dict[str, list] = {}
if _PUMP_IDL:
    for _e in _PUMP_IDL["events"]:
        EVENTS[bytes(_e["discriminator"])] = _e["name"]
    for _t in _PUMP_IDL["types"]:
        TYPES[_t["name"]] = ((_t.get("type") or {}).get("fields")) or []


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


def find_pda(seeds: list[bytes], program: bytes) -> str:
    for nonce in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([nonce]) + program
                           + b"ProgramDerivedAddress").digest()
        if not is_on_curve(h):
            return b58encode(h)
    raise RuntimeError("no PDA")


# ---- borsh（只覆盖事件需要的类型） ----
def _read(data: bytes, off: int, t):
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
        return int.from_bytes(data[off:off + 16], "little", signed=(t == "i128")), off + 16
    if t == "pubkey":
        return b58encode(data[off:off + 32]), off + 32
    if t == "string":
        n = int.from_bytes(data[off:off + 4], "little")
        return data[off + 4:off + 4 + n].decode("utf-8", "replace"), off + 4 + n
    fields = TYPES.get(t)
    if fields is not None:
        out, off2 = {}, off
        for f in fields:
            out[f["name"]], off2 = _read(data, off2, f["type"])
        return out, off2
    return None, off


def decode_pump_events(logs: list[str]) -> list[tuple[str, dict]]:
    out = []
    for line in logs or []:
        if not line.startswith("Program data: "):
            continue
        try:
            raw = base64.b64decode(line[len("Program data: "):]
                                   + "=" * (-(len(line) - 14) % 4))
        except Exception:  # noqa: BLE001
            continue
        name = EVENTS.get(raw[:8])
        if not name or name not in TYPES:
            continue
        val, _ = _read(raw, 8, name)
        if isinstance(val, dict):
            out.append((name, val))
    return out


def _u64(data: bytes, off: int) -> tuple[int, int]:
    return int.from_bytes(data[off:off + 8], "little"), off + 8


def decode_curve(data: bytes) -> dict | None:
    body = data[8:]
    try:
        if len(body) >= 158:
            vtr, off = _u64(body, 0)
            vqr, off = _u64(body, off)
            rtr, off = _u64(body, off)
            rqr, off = _u64(body, off)
            tts, off = _u64(body, off)
            complete = bool(body[off]); off += 1
            creator = b58encode(body[off:off + 32]); off += 32
            mayhem = bool(body[off]); off += 1
            cashback = bool(body[off]); off += 1
            qm = b58encode(body[off:off + 32])
            return {"layout": "v2", "real_token_reserves": rtr,
                    "real_quote_reserves": rqr, "token_total_supply": tts,
                    "complete": complete, "creator": creator, "mayhem": mayhem,
                    "cashback": cashback, "quote_mint": qm}
        if len(body) >= 73:
            vtr, off = _u64(body, 0)
            vsr, off = _u64(body, off)
            rtr, off = _u64(body, off)
            rsr, off = _u64(body, off)
            tts, off = _u64(body, off)
            complete = bool(body[off]); off += 1
            creator = b58encode(body[off:off + 32])
            return {"layout": "v1", "real_token_reserves": rtr,
                    "real_quote_reserves": rsr, "token_total_supply": tts,
                    "complete": complete, "creator": creator, "mayhem": False,
                    "cashback": False, "quote_mint": None}
    except Exception:  # noqa: BLE001
        return None
    return None


class Chain:
    def __init__(self, cli: str | None = None, rate: float = 0.02, workers: int = 6):
        self.client = make_client(cli=cli, rate=rate)
        self.workers = workers

    # ---------------- 基础读取 ----------------
    def _account(self, addr: str) -> bytes | None:
        info = self.client.call("getAccountInfo", [addr, {"encoding": "base64"}])
        try:
            return base64.b64decode(info["value"]["data"][0])
        except Exception:  # noqa: BLE001
            return None

    def curve(self, mint: str) -> dict | None:
        for seed in (b"bonding-curve", b"bonding-curve-v2"):
            addr = find_pda([seed, b58decode(mint)], b58decode(PUMP_PROGRAM))
            data = self._account(addr)
            if data:
                curve = decode_curve(data)
                if curve:
                    curve["curve_address"] = addr
                    return curve
        return None

    def dev_balance_raw(self, creator: str, mint: str) -> float:
        res = self.client.call("getTokenAccountsByOwner",
                               [creator, {"mint": mint}, {"encoding": "jsonParsed"}])
        total = 0.0
        try:
            for acc in res["value"]:
                total += float(acc["account"]["data"]["parsed"]["info"]
                               ["tokenAmount"]["amount"])
        except Exception:  # noqa: BLE001
            return 0.0
        return total

    def _tx(self, sig: str):
        return self.client.call("getTransaction",
                                [sig, {"encoding": "jsonParsed",
                                       "maxSupportedTransactionVersion": 0}])

    # ---------------- 早期特征（实时流数据库，毫秒级） ----------------
    def early_features_stream(self, mint: str) -> dict:
        if not STREAM_DB or not STREAM_DB.exists():
            return {"ok": False, "reason": "no_stream_db"}
        import sqlite3
        try:
            con = sqlite3.connect(f"file:{STREAM_DB}?mode=ro", uri=True, timeout=5)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT ts, name, is_buy, user, creator, sol_amount, real_quote_reserves "
                "FROM events WHERE mint=? AND program='curve' "
                "AND ts BETWEEN 1600000000 AND 2000000000 ORDER BY ts LIMIT 500",
                (mint,)).fetchall()
            con.close()
        except Exception as exc:  # 旧库缺列等
            return {"ok": False, "reason": f"stream_query_error: {exc}"}
        if not rows:
            return {"ok": False, "reason": "mint_not_in_stream"}
        t0 = min(r["ts"] for r in rows)
        creator = next((r["creator"] for r in rows if r["creator"]), None)
        buys, totals = [], {}
        rs = None
        for r in rows:
            if r["ts"] - t0 > 10:
                continue
            totals[r["ts"]] = totals.get(r["ts"], 0) + 1
            if r["is_buy"]:
                buys.append(r)
                if r["real_quote_reserves"]:
                    rs = r["real_quote_reserves"]
            if creator and r["user"] == creator and r["is_buy"] and "dev_buy" not in totals:
                totals["dev_buy"] = (r["sol_amount"] or 0) / 1e9
        first_two = sorted(totals.keys() - {"dev_buy"}, key=lambda x: x)[:2]
        bundle = {r["user"] for r in buys
                  if r["ts"] in first_two and r["user"] and r["user"] != creator}
        return {"ok": True, "source": "stream", "create_t0": t0, "creator": creator,
                "dev_buy_sol": totals.get("dev_buy"),
                "f10_n_buys": len(buys), "f10_bundle_wallets": len(bundle),
                "f10_rs": (rs / 1e9) if rs else None, "events": len(rows)}

    # ---------------- 早期特征（RPC 兜底） ----------------
    def early_features(self, mint: str, curve: dict, max_sigs: int = 60) -> dict:
        s = self.early_features_stream(mint)
        if s.get("ok"):
            return s
        return self._early_features_rpc(mint, curve, max_sigs)

    def _early_features_rpc(self, mint: str, curve: dict, max_sigs: int = 60) -> dict:
        """从创建交易 + 最早若干交易里提取 f10_*（近似数据集口径）。"""
        addr = curve.get("curve_address")
        if not addr:
            return {"ok": False, "reason": "no_curve_address"}
        sigs = self.client.call("getSignaturesForAddress", [addr, {"limit": 1000}]) or []
        if not sigs:
            return {"ok": False, "reason": "no_signatures"}
        if len(sigs) < max_sigs:          # 能拿到全部交易 → 创建交易也在其中
            window_complete = True
        else:                              # 只拿到最新 1000 笔，可能不覆盖上线
            window_complete = False
        oldest = sorted(sigs, key=lambda s: s.get("blockTime") or 0)[:max_sigs]
        with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
            txs = list(ex.map(lambda s: self._tx(s["signature"]), oldest))

        create_t0 = None
        creator = curve.get("creator")
        buys: list[dict] = []
        events_all: list[tuple[int, str, dict]] = []
        for tx in txs:
            if not tx:
                continue
            bt = tx.get("blockTime") or 0
            logs = (tx.get("meta") or {}).get("logs") or []
            for name, ev in decode_pump_events(logs):
                if name == "CreateEvent":
                    create_t0 = bt
                    creator = ev.get("creator") or creator
                events_all.append((bt, name, ev))
        if create_t0 is None and events_all:
            create_t0 = min(bt for bt, _, _ in events_all)
        if create_t0 is None:
            return {"ok": False, "reason": "no_create_event"}

        dev_buy_sol = None
        reserve_10s = None
        for bt, name, ev in sorted(events_all):
            if name != "TradeEvent":
                continue
            if bt - create_t0 > 10:
                continue
            if ev.get("is_buy"):
                buys.append(ev)
                if ev.get("user") == creator and dev_buy_sol is None:
                    dev_buy_sol = (ev.get("sol_amount") or ev.get("quote_amount") or 0) / 1e9
            rq = ev.get("real_quote_reserves") or ev.get("real_sol_reserves")
            if rq:
                reserve_10s = rq / 1e9

        # 捆绑近似：创建交易与紧接一笔里的不同买家
        buyers_early: set[str] = set()
        first_two_ts = sorted({bt for bt, _, _ in events_all})[:2]
        for bt, name, ev in events_all:
            if name == "TradeEvent" and ev.get("is_buy") and bt in first_two_ts:
                u = ev.get("user")
                if u and u != creator:
                    buyers_early.add(u)

        out = {
            "ok": True, "window_complete": window_complete,
            "create_t0": create_t0, "creator": creator,
            "dev_buy_sol": dev_buy_sol,
            "f10_n_buys": len(buys),
            "f10_bundle_wallets": len(buyers_early),
            "f10_rs": reserve_10s,
            "fetched_txs": len([t for t in txs if t]),
            "total_sigs": len(sigs),
        }
        return out

    def insider_share(self, mint: str, curve: dict, top: int = 20) -> float | None:
        """前 N 大持有人中的非曲线/非池子占比（近似 f10_insider_share）。"""
        res = self.client.call("getTokenLargestAccounts", [mint])
        if not res or "value" not in res:
            return None
        supply = curve.get("token_total_supply") or 0
        if not supply:
            return None
        holders = []
        for acc in res["value"][:top]:
            info = self.client.call("getAccountInfo",
                                    [acc["address"], {"encoding": "jsonParsed"}])
            try:
                owner = info["value"]["data"]["parsed"]["info"]["owner"]
            except Exception:  # noqa: BLE001
                continue
            amt = float(acc.get("amount") or 0)
            if owner in (curve.get("curve_address"), PUMP_PROGRAM):
                continue
            holders.append((owner, amt))
        if not holders:
            return 0.0
        return sum(a for _, a in holders) / supply

    # ---------------- 汇总 ----------------
    def snapshot(self, mint: str) -> dict:
        c = self.curve(mint)
        if not c:
            return {"ok": False, "reason": "curve_not_found"}
        out = {"ok": True, "curve": c}
        tts = c.get("token_total_supply") or 0
        bal = self.dev_balance_raw(c["creator"], mint)
        out["dev_share"] = (bal / tts) if tts else None
        out["f10_rs"] = (c.get("real_quote_reserves") or 0) / 1e9
        out["creator"] = c["creator"]
        out["complete"] = c["complete"]
        out["mayhem"] = bool(c.get("mayhem"))
        out["quote_mint"] = c.get("quote_mint")
        out["creator_token_balance_raw"] = bal
        try:
            early = self.early_features(mint, c)
            out["early"] = early
            if early.get("ok"):
                if early.get("f10_rs"):
                    out["f10_rs"] = early["f10_rs"]
                for k in ("dev_buy_sol", "f10_n_buys", "f10_bundle_wallets"):
                    if early.get(k) is not None:
                        out[k] = early[k]
        except Exception as exc:  # noqa: BLE001
            out["early"] = {"ok": False, "reason": f"error: {exc}"}
        try:
            ins = self.insider_share(mint, c)
            if ins is not None:
                out["f10_insider_share"] = ins
        except Exception:  # noqa: BLE001
            pass
        return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mint")
    ap.add_argument("--no-early", action="store_true")
    args = ap.parse_args()
    ch = Chain()
    if args.no_early:
        print(json.dumps(ch.curve(args.mint), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(ch.snapshot(args.mint), ensure_ascii=False, indent=1, default=str))
