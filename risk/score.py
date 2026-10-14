#!/usr/bin/env python3
"""纯 Python 评分器：读 model.json，按特征算概率（无依赖，可嵌服务）。

用法：
  from score import load, score
  m = load("model.json")
  score(m, {"prior_n": 0, "prior_resolved": 0, "prior_rug_rate": 0.0,
            "prior_grad_rate": 0.0, "has_history": 0,
            "dev_share": 0.05, "dev_buy_sol": 1.2,
            "f10_insider_share": 0.1, "f10_bundle_wallets": 2,
            "f10_n_buys": 5, "f10_rs": 1.5})   # → 0.97…
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib


def load(path: str | pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text())


def score(model: dict, features: dict) -> float:
    z = model["intercept"]
    for name, mean, scale, coef in zip(model["features"], model["mean"],
                                       model["scale"], model["coef"]):
        v = features.get(name)
        if v is None:
            v = mean                      # 缺失按训练均值中性处理
        z += coef * ((float(v) - mean) / (scale or 1.0))
    z = max(-60.0, min(60.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def explain(model: dict, features: dict, top: int = 3) -> list[dict]:
    parts = []
    for name, mean, scale, coef in zip(model["features"], model["mean"],
                                       model["scale"], model["coef"]):
        v = features.get(name)
        if v is None:
            continue
        parts.append({"feature": name, "value": v,
                      "contribution": round(coef * ((float(v) - mean) / (scale or 1.0)), 3)})
    parts.sort(key=lambda x: -abs(x["contribution"]))
    return parts[:top]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(pathlib.Path(__file__).parent / "model.json"))
    ap.add_argument("--features", required=True, help="JSON 字符串")
    args = ap.parse_args()
    m = load(args.model)
    f = json.loads(args.features)
    print(f"P(rug within 300s) = {score(m, f):.4f}")
    for e in explain(m, f):
        print(f"  {e['feature']:22} = {e['value']:<12} 贡献 {e['contribution']:+.3f}")
