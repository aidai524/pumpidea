"""链上读取：bonding curve、创建者持仓、mint 供应。纯标准库 + 共享 rpc.py。

已适配两种 curve 布局：
  v1（旧，81 字节）：virtual_token_reserves / virtual_sol_reserves /
      real_token_reserves / real_sol_reserves / token_total_supply / complete / creator
  v2（新，166 字节）：…以 quote 命名，另有 quote_mint / 费率字段
"""
from __future__ import annotations

import base64
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
for _cand in (ROOT.parent / "audit", ROOT.parent):
    if (_cand / "rpc.py").exists():
        sys.path.insert(0, str(_cand))
        break
from rpc import make_client  # noqa: E402

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


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


def _u64(data: bytes, off: int) -> tuple[int, int]:
    return int.from_bytes(data[off:off + 8], "little"), off + 8


def decode_curve(data: bytes) -> dict | None:
    body = data[8:]  # 跳过 anchor discriminator
    try:
        if len(body) >= 158:  # v2
            vtr, off = _u64(body, 0)
            vqr, off = _u64(body, off)
            rtr, off = _u64(body, off)
            rqr, off = _u64(body, off)
            tts, off = _u64(body, off)
            complete = bool(body[off]); off += 1
            creator = b58encode(body[off:off + 32]); off += 32
            mayhem = bool(body[off]); off += 1
            cashback = bool(body[off]); off += 1
            quote_mint = b58encode(body[off:off + 32]); off += 32
            return {"layout": "v2", "virtual_token_reserves": vtr,
                    "virtual_quote_reserves": vqr, "real_token_reserves": rtr,
                    "real_quote_reserves": rqr, "token_total_supply": tts,
                    "complete": complete, "creator": creator, "mayhem": mayhem,
                    "cashback": cashback, "quote_mint": quote_mint}
        if len(body) >= 73:  # v1
            vtr, off = _u64(body, 0)
            vsr, off = _u64(body, off)
            rtr, off = _u64(body, off)
            rsr, off = _u64(body, off)
            tts, off = _u64(body, off)
            complete = bool(body[off]); off += 1
            creator = b58encode(body[off:off + 32])
            return {"layout": "v1", "virtual_token_reserves": vtr,
                    "virtual_quote_reserves": vsr, "real_token_reserves": rtr,
                    "real_quote_reserves": rsr, "token_total_supply": tts,
                    "complete": complete, "creator": creator, "mayhem": False,
                    "cashback": False, "quote_mint": None}
    except Exception:  # noqa: BLE001
        return None
    return None


class Chain:
    def __init__(self, cli: str | None = None, rate: float = 0.02):
        self.client = make_client(cli=cli, rate=rate)

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

    def snapshot(self, mint: str) -> dict:
        """返回评分所需的一手字段（缺失用 None）。"""
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
        return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("mint")
    args = ap.parse_args()
    print(json.dumps(Chain().snapshot(args.mint), ensure_ascii=False, indent=1))
