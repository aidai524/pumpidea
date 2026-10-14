#!/usr/bin/env python3
"""创作者/代币风险评分：训练与时间外验证（可复现）。

特征分两组：
  HIST（历史组）—— 只用**该币之前**的创建者行为（扩张窗口，无泄漏）：
       prior_n / prior_resolved / prior_rug_rate / prior_grad_rate / has_history
  COLD（冷启动组）—— 上线 10 秒内可得：dev_share / dev_buy_sol /
       f10_insider_share / f10_bundle_wallets / f10_n_buys / f10_rs

训练两个目标：rug（300 秒内跑路）与 graduated（真毕业）。
验证按时间切分（行为类问题不能用随机切分）。

输出：
  facts.json  全部指标（报告只消费它）
  model.json  纯 Python 可用的逻辑回归系数（供在线评分）
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
OUT = ROOT / "facts.json"

HIST = ["prior_n", "prior_resolved", "prior_rug_rate", "prior_grad_rate", "has_history"]
COLD = ["dev_share", "dev_buy_sol", "f10_insider_share", "f10_bundle_wallets",
        "f10_n_buys", "f10_rs"]
F = {}


def load() -> pd.DataFrame:
    cols = ["t0", "creator", "rugged", "graduated", "quote_asset", "mayhem",
            "dev_share", "dev_buy_sol", "f10_insider_share", "f10_bundle_wallets",
            "f10_n_buys", "f10_rs", "peak_rs"]
    new = pd.concat([pd.read_parquet(f, columns=cols)
                     for f in sorted((DATA / "launches").glob("*.parquet"))],
                    ignore_index=True)
    old = pd.concat([pd.read_parquet(f, columns=cols)
                     for f in sorted((DATA / "launches_legacy").glob("*.parquet"))],
                    ignore_index=True)
    df = pd.concat([old, new], ignore_index=True)
    df = df[(df["quote_asset"] == "sol") & (df["mayhem"] == 0)].copy()
    df = df.sort_values("t0").reset_index(drop=True)
    df["day"] = pd.to_datetime(df["t0"], unit="s").dt.floor("D")
    return df


def add_history(df: pd.DataFrame) -> pd.DataFrame:
    """扩张窗口的创建者历史（只用当前行之前的）。"""
    g = df.groupby("creator", sort=False)
    is_res = df["rugged"].notna()
    rug0 = df["rugged"].fillna(0)
    grad0 = df["graduated"].fillna(0)
    df["prior_n"] = g.cumcount()
    df["prior_resolved"] = g["rugged"].transform(lambda s: s.notna().cumsum()) - is_res
    df["prior_rugs"] = g[rug0.name].transform(lambda s: s.cumsum()) - rug0
    df["prior_grads"] = g[grad0.name].transform(lambda s: s.cumsum()) - grad0
    df["prior_rug_rate"] = np.where(df["prior_resolved"] > 0,
                                    df["prior_rugs"] / df["prior_resolved"], 0.0)
    df["prior_grad_rate"] = np.where(df["prior_resolved"] > 0,
                                     df["prior_grads"] / df["prior_resolved"], 0.0)
    df["has_history"] = (df["prior_n"] > 0).astype(int)
    return df


def fit_eval(train: pd.DataFrame, eval_: pd.DataFrame, feats: list[str],
             target: str) -> dict:
    tr = train.dropna(subset=feats + [target])
    ev = eval_.dropna(subset=feats + [target])
    if len(tr) < 500 or len(ev) < 200:
        return {"n_train": len(tr), "n_eval": len(ev), "note": "样本不足"}
    pipe = Pipeline([("sc", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=3000, class_weight="balanced"))])
    pipe.fit(tr[feats], tr[target].astype(int))
    p = pipe.predict_proba(ev[feats])[:, 1]
    y = ev[target].astype(int).to_numpy()
    sc, lr = pipe.named_steps["sc"], pipe.named_steps["lr"]
    out = {
        "n_train": int(len(tr)), "n_eval": int(len(ev)),
        "base_rate_eval": round(float(y.mean()), 4),
        "auc": round(float(roc_auc_score(y, p)), 4),
        "ap": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "calibration": [],
        "capture": [],
        "model": {"features": feats,
                  "mean": [round(float(x), 6) for x in sc.mean_],
                  "scale": [round(float(x), 6) for x in sc.scale_],
                  "coef": [round(float(x), 6) for x in lr.coef_[0]],
                  "intercept": round(float(lr.intercept_[0]), 6)},
    }
    d = pd.DataFrame({"p": p, "y": y})
    d["bin"] = pd.qcut(d["p"], 10, duplicates="drop")
    for b, gg in d.groupby("bin", observed=True):
        out["calibration"].append({"bucket": str(b),
                                   "pred": round(float(gg["p"].mean()), 3),
                                   "actual": round(float(gg["y"].mean()), 3),
                                   "n": int(len(gg))})
    for q in (0.01, 0.05, 0.10, 0.20):
        k = max(1, int(len(d) * q))
        top = d.nlargest(k, "p")
        out["capture"].append({"top_pct": q * 100, "launches": k,
                               "capture_pct": round(float(top["y"].sum() / y.sum() * 100), 1),
                               "precision_pct": round(float(top["y"].mean() * 100), 1)})
    return out


def main() -> None:
    df = add_history(load())
    F["dataset"] = {"rows_classic": int(len(df)),
                    "days": [str(df["day"].min().date()), str(df["day"].max().date())],
                    "creators": int(df["creator"].nunique())}

    # ---- 历史组：全窗口，按时间切
    cut = pd.Timestamp("2026-09-16")
    F["history_model"] = {}
    for target in ("rugged", "graduated"):
        F["history_model"][target] = fit_eval(
            df[df["day"] < cut], df[df["day"] >= cut], HIST, target)
    # 已知创作者子集（有历史的人）——与全量的差异说明“新号”部分靠冷启动特征补
    F["history_model"]["rugged_known_creators"] = fit_eval(
        df[df["day"] < cut],
        df[(df["day"] >= cut) & (df["has_history"] == 1)], HIST, "rugged")

    # ---- 冷启动组：干净窗口（f10 完整），窗口内按时间切
    clean = df[df["day"] >= pd.Timestamp("2026-09-27")].copy()
    cut2 = pd.Timestamp("2026-10-01")
    F["cold_model"] = {"rows_clean": int(len(clean)),
                       "f10_coverage_pct": round(float(clean["f10_rs"].notna().mean() * 100), 2)}
    for target in ("rugged", "graduated"):
        F["cold_model"][target] = fit_eval(
            clean[clean["day"] < cut2], clean[clean["day"] >= cut2], COLD, target)

    # ---- 组合模型：干净窗口，历史 + 冷启动
    F["combined_model"] = {}
    feats = HIST + COLD
    for target in ("rugged", "graduated"):
        F["combined_model"][target] = fit_eval(
            clean[clean["day"] < cut2], clean[clean["day"] >= cut2], feats, target)

    # ---- 导出可部署模型（rug + graduation）
    import time as _t
    payload = {
        "version": "risk-" + _t.strftime("%Y-%m-%d"),
        "trained_at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        "features": F["combined_model"]["rugged"]["model"]["features"],
        "rug": F["combined_model"]["rugged"]["model"],
        "graduation": F["combined_model"]["graduated"]["model"],
        "metrics": {t: {k: F["combined_model"][t][k]
                        for k in ("auc", "ap", "brier", "base_rate_eval")}
                    for t in ("rugged", "graduated")},
    }
    (ROOT / "model.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    OUT.write_text(json.dumps(F, ensure_ascii=False, indent=1))
    print(f"写了 {OUT} 和 {ROOT/'model.json'}")
    for name, block in (("history", F["history_model"]), ("cold", F["cold_model"]),
                        ("combined", F["combined_model"])):
        for tgt, r in block.items():
            if isinstance(r, dict) and "auc" in r:
                print(f"  {name:9} {tgt:10} AUC={r['auc']:.3f} AP={r['ap']:.3f} "
                      f"Brier={r['brier']:.3f} base={r['base_rate_eval']:.3f} n={r['n_eval']:,}")


if __name__ == "__main__":
    main()
