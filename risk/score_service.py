#!/usr/bin/env python3
"""在线风险评分服务（③ 线原型）。

  GET /                → 演示页（输入 mint，实时打分）
  GET /score/{mint}    → JSON：P(跑路 300s) / P(毕业) / flags / 贡献因子
  GET /health          → 健康检查

数据：model.json（离线训练）+ history.sqlite3（创建者历史）+ Alchemy RPC（curve/dev 持仓）。
部署：监听 8090，由 Caddy 以 /risk/* 路径反代（handle_path 会去掉前缀）。
"""
from __future__ import annotations

import argparse
import base64
import functools
import hmac
import http.server
import json
import pathlib
import sqlite3
import sys
import threading
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from chain import Chain  # noqa: E402
from score import explain, score  # noqa: E402

MODELS = json.loads((ROOT / "model.json").read_text())
TRAINED_AT = MODELS.get("trained_at")
CURVE_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 20
_lock = threading.Lock()


class Scorer:
    def __init__(self, db: pathlib.Path, rpc: str | None):
        self.chain = Chain(cli=rpc)
        self.db = sqlite3.connect(db, check_same_thread=False)
        self.db.row_factory = sqlite3.Row

    def history(self, creator: str) -> dict:
        row = self.db.execute(
            "SELECT n, resolved, rugs, grads, rug_rate, grad_rate, last_rug_t0 "
            "FROM creators WHERE creator=?", (creator,)).fetchone()
        if not row:
            return {"prior_n": 0, "prior_resolved": 0, "prior_rug_rate": 0.0,
                    "prior_grad_rate": 0.0, "has_history": 0}
        r = dict(row)
        return {"prior_n": r["n"], "prior_resolved": r["resolved"],
                "prior_rug_rate": r["rug_rate"] or 0.0,
                "prior_grad_rate": r["grad_rate"] or 0.0,
                "has_history": 1 if r["n"] else 0,
                "known_rugs": r["rugs"], "known_grads": r["grads"]}

    def snapshot(self, mint: str) -> dict:
        now = time.time()
        with _lock:
            if mint in CURVE_CACHE and now - CURVE_CACHE[mint][0] < CACHE_TTL:
                return CURVE_CACHE[mint][1]
        snap = self.chain.snapshot(mint)
        with _lock:
            CURVE_CACHE[mint] = (now, snap)
        return snap

    def score(self, mint: str) -> dict:
        snap = self.snapshot(mint)
        if not snap.get("ok"):
            return {"ok": False, "mint": mint, "reason": snap.get("reason")}
        creator = snap["creator"]
        hist = self.history(creator)
        feats = {**hist, "dev_share": snap.get("dev_share"),
                 "f10_rs": snap.get("f10_rs")}
        # 冷启动里依赖交易流的字段暂无在线来源 → 缺失，模型按均值处理
        for k in ("dev_buy_sol", "f10_insider_share", "f10_bundle_wallets", "f10_n_buys"):
            feats.setdefault(k, None)
        rug = score(MODELS["rug"], feats)
        grad = score(MODELS["graduation"], feats)
        flags = []
        if not hist["has_history"]:
            flags.append("no_history")
        if (snap.get("dev_share") or 0) >= 0.10:
            flags.append("dev_share_high")
        if hist["prior_resolved"] >= 3 and hist["prior_rug_rate"] >= 0.8:
            flags.append("serial_rugger")
        if snap.get("mayhem"):
            flags.append("mayhem")
        if snap.get("complete"):
            flags.append("curve_complete")
        if snap.get("quote_mint") not in (None, "11111111111111111111111111111111",
                                          "So11111111111111111111111111111111111111112"):
            flags.append("non_sol_quote")
        return {
            "ok": True, "mint": mint, "creator": creator,
            "p_rug_300s": round(rug, 4), "p_graduation": round(grad, 4),
            "flags": flags,
            "top_factors": explain(MODELS["rug"], feats, top=4),
            "inputs": {"dev_share": None if feats["dev_share"] is None
                       else round(feats["dev_share"], 5),
                       "curve_sol": round(feats["f10_rs"] or 0, 3),
                       **{k: hist[k] for k in ("prior_n", "prior_resolved",
                                               "prior_rug_rate")}},
            "curve": {"layout": snap["curve"]["layout"],
                      "real_quote_reserves_sol": round(feats["f10_rs"] or 0, 3),
                      "token_total_supply": snap["curve"]["token_total_supply"],
                      "curve_address": snap["curve"].get("curve_address")},
            "model_version": MODELS.get("version"), "scored_at": int(time.time()),
        }


DEMO_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pump.fun 风险评分 · demo</title>
<style>
 body{margin:0;background:#07090d;color:#e8edf4;font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.6}
 .wrap{max-width:900px;margin:0 auto;padding:28px 22px}
 h1{font-size:18px;letter-spacing:2px} input{background:#0e131b;border:1px solid #1b2431;color:#e8edf4;
 padding:10px 12px;width:70%;border-radius:8px;font-family:inherit} button{background:#38bdf8;border:0;
 padding:10px 18px;border-radius:8px;font-weight:700;cursor:pointer;font-family:inherit}
 .card{background:#0e131b;border:1px solid #1b2431;border-radius:12px;padding:18px;margin-top:18px}
 .big{font-size:38px;font-weight:800} .sub{color:#9aa6b6;font-size:12px}
 .flag{display:inline-block;background:#3b1d24;color:#ff4d6d;border-radius:6px;padding:2px 8px;margin:2px;font-size:12px}
 .flag.ok{background:#12301f;color:#22c55e}
 table{width:100%;border-collapse:collapse;margin-top:8px} td,th{border-bottom:1px solid #1b2431;padding:6px 8px;text-align:left}
 th{color:#5d6a7a;font-size:11px;letter-spacing:1px} .muted{color:#5d6a7a}
</style></head><body><div class="wrap">
<h1>pump.fun 新币风险评分 <span class="muted" style="font-size:12px">model {version} · trained {trained}</span></h1>
<p class="muted">输入任意 mint，实时读链（bonding curve + 创建者持仓 + 历史）+ 模型打分。</p>
<p><input id="mint" placeholder="mint address (…pump)" value="{example}"> <button onclick="go()">评分</button></p>
<div id="out"></div>
<script>
async function go(){{
  const m=document.getElementById('mint').value.trim();
  const out=document.getElementById('out'); out.innerHTML='<p class="muted">读取链上…</p>';
  try{{
    const r=await fetch('score/'+encodeURIComponent(m)); const d=await r.json();
    if(!d.ok){{ out.innerHTML='<div class="card">无法评分：'+ (d.reason||'unknown') +'</div>'; return; }}
    const flags=(d.flags||[]).map(f=>`<span class="flag ${{['no_history'].includes(f)?'':'ok'}}">${{f}}</span>`).join('');
    const factors=(d.top_factors||[]).map(f=>`<tr><td>${{f.feature}}</td><td>${{f.value}}</td><td>${{f.contribution>0?'+':''}}${{f.contribution}}</td></tr>`).join('');
    out.innerHTML=`<div class="card">
      <div class="big" style="color:${{d.p_rug_300s>0.5?'#ff4d6d':'#22c55e'}}">${{(d.p_rug_300s*100).toFixed(1)}}%</div>
      <div class="sub">300 秒内跑路概率（${{d.model_version}}）· 毕业概率 ${{(d.p_graduation*100).toFixed(1)}}%</div>
      <p>${{flags||'<span class="flag ok">no flags</span>'}}</p>
      <table><tr><th>曲线储备</th><th>dev_share</th><th>历史发币</th><th>历史跑路率</th></tr>
      <tr><td>${{d.curve.real_quote_reserves_sol}} SOL</td><td>${{d.inputs.dev_share}}</td>
      <td>${{d.inputs.prior_n}}</td><td>${{d.inputs.prior_rug_rate}}</td></tr></table>
      <table><tr><th>贡献因子</th><th>值</th><th>系数×z</th></tr>${{factors}}</table>
      <p class="muted">creator ${{d.creator}}</p></div>`;
  }}catch(e){{ out.innerHTML='<div class="card">请求失败：'+e+'</div>'; }}
}}
</script></div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    scorer: Scorer = None            # type: ignore[assignment]
    user = ""
    password = ""
    realm = "pumpfun-risk"

    def _ok(self) -> bool:
        if not self.password:
            return True
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        try:
            u, p = base64.b64decode(h[6:]).decode().split(":", 1)
        except Exception:  # noqa: BLE001
            return False
        return hmac.compare_digest(u, self.user) and hmac.compare_digest(p, self.password)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not self._ok():
            self.send_response(401)
            self.send_header("WWW-Authenticate", f'Basic realm="{self.realm}"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (DEMO_PAGE.replace("{version}", str(MODELS.get("version")))
                    .replace("{trained}", str(TRAINED_AT))
                    .replace("{example}", DEMO_MINT[0]))
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif path == "/health":
            self._send(200, json.dumps({"ok": True, "model": MODELS.get("version"),
                                        "cache": len(CURVE_CACHE)}).encode(),
                       "application/json")
        elif path.startswith("/score/"):
            mint = urllib.parse.unquote(path[len("/score/"):]).strip()
            if not mint:
                self._send(400, b'{"ok":false,"reason":"missing mint"}', "application/json")
                return
            try:
                result = self.scorer.score(mint)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "mint": mint, "reason": f"error: {type(exc).__name__}: {exc}"}
            code = 200 if result.get("ok") else 404
            self._send(code, json.dumps(result, ensure_ascii=False).encode(),
                       "application/json")
        else:
            self._send(404, b'{"ok":false,"reason":"not found"}', "application/json")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


DEMO_MINT = ["FgYrixb7ditkeWGoJiYTZDe3ygLmbz9SxEawzyiEpump"]


def load_creds(path: str) -> tuple[str, str]:
    p = pathlib.Path(path)
    if not p.exists():
        return "", ""
    user, password = "pumpfun", ""
    for line in p.read_text().splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        k, v = line.strip().split("=", 1)
        if k == "WEB_USER":
            user = v
        elif k == "WEB_PASS":
            password = v
    return user, password


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--creds", default="/etc/pumpfun-web.conf")
    ap.add_argument("--rpc", help="覆盖 RPC（默认 .env / ALCHEMY_RPC_URL）")
    ap.add_argument("--example", default=DEMO_MINT[0])
    args = ap.parse_args()
    DEMO_MINT[0] = args.example
    Handler.user, Handler.password = load_creds(args.creds)
    Handler.scorer = Scorer(ROOT / "history.sqlite3", args.rpc)
    handler = functools.partial(Handler)
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as srv:
        print(f"risk service on {args.bind}:{args.port} "
              f"(auth={'on' if Handler.password else 'off'}, model={MODELS.get('version')})",
              flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
