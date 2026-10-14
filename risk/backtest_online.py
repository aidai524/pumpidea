#!/usr/bin/env python3
"""在线评分回测：用实时流的早期特征 + 先验历史，对成熟 mint 打分并与结局比对。

防泄漏：
  - 只用该 mint 首见时间**之前**的创建者历史（数据集历史天然更早；流历史按 first_ts < t0 过滤）
  - 早期特征只取前 10 秒的事件
结局：stream_history 的简化标签（graduated_like / rug_like）。
输出 backtest_facts.json。
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sqlite3
import time

ROOT = pathlib.Path(__file__).resolve().parent
MODEL = json.loads((ROOT / "model.json").read_text())


def sigmoid(z: float) -> float:
    z = max(-60.0, min(60.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def score(model: dict, feats: dict) -> float:
    z = model["intercept"]
    for name, mean, scale, coef in zip(model["features"], model["mean"],
                                       model["scale"], model["coef"]):
        v = feats.get(name)
        if v is None:
            v = mean
        z += coef * ((float(v) - mean) / (scale or 1.0))
    return sigmoid(z)


def early_features(con: sqlite3.Connection, mint: str) -> dict | None:
    rows = con.execute(
        "SELECT ts, is_buy, user, creator, sol_amount, real_quote_reserves, token_amount "
        "FROM events WHERE mint=? AND program='curve' "
        "AND ts BETWEEN 1600000000 AND 2000000000 ORDER BY ts LIMIT 500",
        (mint,)).fetchall()
    if not rows:
        return None
    t0 = min(r[0] for r in rows)
    creator = next((r[3] for r in rows if r[3]), None)
    buys, dev_buy, reserve = [], None, None
    creator_tokens = 0.0
    per_ts: dict[int, int] = {}
    for ts, is_buy, user, _c, sol, rq, tok in rows:
        if ts - t0 > 10:
            continue
        per_ts[ts] = per_ts.get(ts, 0) + 1
        if is_buy:
            buys.append((ts, user))
            if rq:
                reserve = rq
            if creator and user == creator and dev_buy is None:
                dev_buy = (sol or 0) / 1e9
            if creator and user == creator and tok:
                creator_tokens += tok
    first_two = sorted(per_ts)[:2]
    bundle = {u for ts, u in buys if ts in first_two and u and u != creator}
    # dev_share 历史重建：创建者前 10 秒买入的 token / 总供应（1e15 raw）
    dev_share_est = (creator_tokens / 1e15) if creator_tokens else None
    return {"t0": t0, "creator": creator, "dev_buy_sol": dev_buy,
            "dev_share_est": dev_share_est,
            "f10_n_buys": len(buys), "f10_bundle_wallets": len(bundle),
            "f10_rs": (reserve / 1e9) if reserve else None}


def history(ds: sqlite3.Connection, outcomes: sqlite3.Connection,
            creator: str, t0: int) -> dict:
    n = resolved = rugs = grads = 0
    row = ds.execute("SELECT n,resolved,rugs,grads FROM creators WHERE creator=?",
                     (creator,)).fetchone()
    if row:
        n, resolved, rugs, grads = row
    row = outcomes.execute(
        "SELECT count(*), sum(CASE WHEN graduated_like=1 OR rug_like=1 THEN 1 ELSE 0 END),"
        " sum(rug_like), sum(graduated_like) FROM mint_outcomes "
        "WHERE creator=? AND first_ts < ?", (creator, t0)).fetchone()
    if row and row[0]:
        n += row[0]
        resolved += row[1] or 0
        rugs += row[2] or 0
        grads += row[3] or 0
    return {"prior_n": n, "prior_resolved": resolved,
            "prior_rug_rate": (rugs / resolved) if resolved else 0.0,
            "prior_grad_rate": (grads / resolved) if resolved else 0.0,
            "has_history": 1 if n else 0}


def auc(y: list[int], p: list[float]) -> float | None:
    pos = [x for x, t in zip(p, y) if t == 1]
    neg = [x for x, t in zip(p, y) if t == 0]
    if not pos or not neg:
        return None
    wins = sum(1 for a in pos for b in neg if a > b) + 0.5 * sum(
        1 for a in pos for b in neg if a == b)
    return wins / (len(pos) * len(neg))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stream-db", default="/opt/pumpfun-stream/runtime/stream.sqlite3")
    ap.add_argument("--outcomes", default=str(ROOT / "stream_history.sqlite3"))
    ap.add_argument("--dataset", default=str(ROOT / "history.sqlite3"))
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部成熟 mint")
    args = ap.parse_args()

    live = sqlite3.connect(f"file:{args.stream_db}?mode=ro", uri=True, timeout=30)
    ds = sqlite3.connect(f"file:{args.dataset}?mode=ro", uri=True, timeout=30)
    oc = sqlite3.connect(f"file:{args.outcomes}?mode=ro", uri=True, timeout=30)
    for c in (live, ds, oc):
        c.execute("PRAGMA busy_timeout=20000")
    mints = [r[0] for r in oc.execute(
        "SELECT mint FROM mint_outcomes WHERE graduated_like=1 OR rug_like=1")]
    if args.limit:
        mints = mints[:args.limit]
    print(f"成熟且有结局的 mint：{len(mints):,}", flush=True)

    rows = []
    for i, mint in enumerate(mints, 1):
        if i % 200 == 0:
            print(f"  {i}/{len(mints)}", flush=True)
        ef = early_features(live, mint)
        if not ef:
            continue
        label = oc.execute("SELECT rug_like, graduated_like FROM mint_outcomes WHERE mint=?",
                           (mint,)).fetchone()
        feats = {**history(ds, oc, ef["creator"], ef["t0"]),
                 "dev_share": ef.get("dev_share_est"),
                 **{k: ef[k] for k in ("dev_buy_sol", "f10_n_buys",
                                       "f10_bundle_wallets", "f10_rs")}}
        rows.append({"mint": mint, "p_rug": score(MODEL["rug"], feats),
                     "p_grad": score(MODEL["graduation"], feats),
                     "rug": label[0], "grad": label[1],
                     "n_buys": ef["f10_n_buys"], "dev_buy_sol": ef["dev_buy_sol"]})
    live.close(); ds.close(); oc.close()

    n = len(rows)
    if not n:
        print("没有可用样本（可能成熟 mint 还太少）")
        return
    y_rug = [r["rug"] for r in rows]
    p_rug = [r["p_rug"] for r in rows]
    y_grad = [r["grad"] for r in rows]
    p_grad = [r["p_grad"] for r in rows]
    facts = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": n, "base_rug": sum(y_rug) / n, "base_grad": sum(y_grad) / n,
        "auc_rug": auc(y_rug, p_rug), "auc_grad": auc(y_grad, p_grad),
        "note": "样本来自实时流上线后的成熟 mint；当前样本量偏小，明日起更有意义",
    }
    for q in (0.10, 0.20):
        k = max(1, int(n * q))
        top = sorted(rows, key=lambda r: -r["p_rug"])[:k]
        facts[f"top{int(q*100)}pct_rug_precision"] = sum(r["rug"] for r in top) / k
    (ROOT / "backtest_facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    print(json.dumps(facts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
