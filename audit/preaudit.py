#!/usr/bin/env python3
"""pump.fun 预审计：公开数据能验证什么、不能验证什么。

三个独立来源：
  A. fees.pump.fun        他们自己的看板（含自承认的 custom pairs 口径 bug）
  B. DefiLlama            第三方费用/收入/交易量日序列
  C. HF 公开数据集        我们的自建估计：Σpeak_rs 是曲线净流入下界

产出 facts.json + 控制台摘要。报告只引用 facts.json。
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
AUD = ROOT / "data"
HF = ROOT.parent / "data"

SOL_USD = json.loads((AUD / "sol_price_2026-10-11.json").read_text())["solana"]["usd"]
FEES_PAGE = json.loads((AUD / "fees_pump_fun_2026-10-11.json").read_text())
STATS = json.loads((AUD / "stats_2026-10-11.json").read_text())
FEE_GROSS, FEE_PROTOCOL = 0.0125, 0.0095  # pump.fun/docs/fees


def llama(name: str) -> dict:
    return json.loads((AUD / f"{name}.json").read_text())


def daily(doc: dict) -> pd.Series:
    s = pd.Series({pd.Timestamp(ts, unit="s").date(): float(v)
                   for ts, v in doc["totalDataChart"]})
    return s.sort_index()


DL = {k: llama(k) for k in ("pumpfun_fees", "pumpfun_rev", "pumpswap_fees",
                            "pumpswap_rev", "pumpfun_vol", "pumpswap_vol")}
DLS = {k: daily(v) for k, v in DL.items()}

# ---------------------------------------------------------------- 数据集
cols = ["t0", "quote_asset", "mayhem", "peak_rs", "graduated",
        "curve_complete", "decoder_complete"]
new = pd.concat([pd.read_parquet(f, columns=cols)
                 for f in sorted((HF / "launches").glob("*.parquet"))], ignore_index=True)
old = pd.concat([pd.read_parquet(f, columns=cols)
                 for f in sorted((HF / "launches_legacy").glob("*.parquet"))], ignore_index=True)
new["subset"], old["subset"] = "launches", "legacy"
df = pd.concat([new, old], ignore_index=True)
df["date"] = pd.to_datetime(df["t0"], unit="s").dt.floor("D").dt.date
df["is_sol"] = df["quote_asset"].eq("sol")
df["is_custom"] = df["quote_asset"].isin(["usdc", "pyusd", "stock", "other"])
df["is_classic"] = df["is_sol"] & df["mayhem"].eq(0)
df["peak_classic"] = df["peak_rs"].where(df["is_classic"])

g = df.groupby("date").agg(
    launches=("t0", "size"),
    custom=("is_custom", "sum"),
    classic_launches=("is_classic", "sum"),
    peak_rs_classic=("peak_classic", "sum"),
    decoder_complete_rows=("decoder_complete", "sum"),
    new_rows=("subset", lambda s: int((s == "launches").sum())),
)
g["custom_share_pct"] = (g["custom"] / g["launches"] * 100).round(2)
g["fee_floor_gross_usd"] = g["peak_rs_classic"] * FEE_GROSS * SOL_USD
g["fee_floor_protocol_usd"] = g["peak_rs_classic"] * FEE_PROTOCOL * SOL_USD
g["dl_curve_revenue"] = DLS["pumpfun_rev"]
g["turnover_x"] = (g["dl_curve_revenue"] / g["fee_floor_protocol_usd"]).round(2)

F: dict = {"as_of": "2026-10-11", "sol_usd": SOL_USD,
           "dataset": {"rows": len(df), "days": len(g),
                       "from": str(g.index.min()), "to": str(g.index.max()),
                       "legacy_rows": int((df["subset"] == "legacy").sum()),
                       "launches_rows": int((df["subset"] == "launches").sum())}}

q = df["quote_asset"].value_counts(dropna=False)
F["dataset"]["quote_assets"] = {str(k): int(v) for k, v in q.items()}
F["dataset"]["custom_share_pct"] = round(df["is_custom"].mean() * 100, 2)

# 分割点：custom pairs 上线（新闻：2026-09-09/10 起其他资产加入）
CUT = pd.Timestamp("2026-09-09").date()
pre = g[g.index < CUT]["turnover_x"].dropna()
post = g[g.index >= CUT]["turnover_x"].dropna()
F["turnover"] = {
    "definition": "DefiLlama 曲线收入 ÷ (Σpeak_rs × 0.95% × SOL价)",
    "note": "下界只含曲线净流入；legacy 解码器缺口使 09-27 前低估",
    "pre_cut": {"from": str(pre.index.min()), "to": str(pre.index.max()),
                "median_x": float(pre.median()), "days": len(pre)},
    "post_cut": {"from": str(post.index.min()), "to": str(post.index.max()),
                 "median_x": float(post.median()), "days": len(post)},
}
F["daily"] = [{"day": str(d), "launches": int(r.launches),
               "custom_share_pct": float(r.custom_share_pct),
               "classic_launches": int(r.classic_launches),
               "peak_rs_classic": round(float(r.peak_rs_classic), 1),
               "fee_floor_protocol_usd": round(float(r.fee_floor_protocol_usd)),
               "dl_curve_revenue": (round(float(r.dl_curve_revenue))
                                    if pd.notna(r.dl_curve_revenue) else None),
               "turnover_x": (float(r.turnover_x)
                              if pd.notna(r.turnover_x) else None)}
              for d, r in g.iterrows()]

# ---------------------------------------------------------------- 三方口径
def m(x): return round(x / 1e6, 2)


combined = {
    "fees_30d": m(DL["pumpfun_fees"]["total30d"] + DL["pumpswap_fees"]["total30d"]),
    "revenue_30d": m(DL["pumpfun_rev"]["total30d"] + DL["pumpswap_rev"]["total30d"]),
    "volume_30d_b": round((DL["pumpfun_vol"]["total30d"] + DL["pumpswap_vol"]["total30d"]) / 1e9, 2),
    "fees_7d": m(DL["pumpfun_fees"]["total7d"] + DL["pumpswap_fees"]["total7d"]),
    "revenue_7d": m(DL["pumpfun_rev"]["total7d"] + DL["pumpswap_rev"]["total7d"]),
    "revenue_24h": m(DL["pumpfun_rev"]["total24h"] + DL["pumpswap_rev"]["total24h"]),
    "revenue_1y": m(DL["pumpfun_rev"]["total1y"] + DL["pumpswap_rev"]["total1y"]),
}
F["defillama"] = {
    "combined": combined,
    "curve": {"fees_30d": m(DL["pumpfun_fees"]["total30d"]),
              "revenue_30d": m(DL["pumpfun_rev"]["total30d"]),
              "volume_30d_b": round(DL["pumpfun_vol"]["total30d"] / 1e9, 2),
              "take_rate_pct": round(DL["pumpfun_rev"]["total30d"] / DL["pumpfun_vol"]["total30d"] * 100, 3)},
    "pumpswap": {"fees_30d": m(DL["pumpswap_fees"]["total30d"]),
                 "revenue_30d": m(DL["pumpswap_rev"]["total30d"]),
                 "volume_30d_b": round(DL["pumpswap_vol"]["total30d"] / 1e9, 2),
                 "take_rate_pct": round(DL["pumpswap_rev"]["total30d"] / DL["pumpswap_vol"]["total30d"] * 100, 3)},
}
F["defillama"]["combined"]["revenue_per_day_30d_m"] = round(combined["revenue_30d"] / 30, 3)
F["defillama"]["combined"]["revenue_per_day_7d_m"] = round(combined["revenue_7d"] / 7, 3)
F["defillama"]["take_rate_all_pct"] = round(
    combined["revenue_30d"] / (combined["volume_30d_b"] * 1000) * 100, 3)

F["fees_page"] = FEES_PAGE
F["fees_page"]["implied_daily_from_annualized_m"] = round(
    float(FEES_PAGE["annualized_revenue_text"]) / 365, 3)
F["fees_page"]["implied_daily_from_buyback_m"] = round(
    float(FEES_PAGE["daily_buyback_text"]) / 1000 / 0.5, 3)

# ---------------------------------------------------------------- 质量基线
sw = STATS["windows"]
F["loopholetape"] = {k: {kk: sw[k].get(kk) for kk in
                         ("days", "from", "to", "launches", "graduation_rate",
                          "instant_share_of_graduations", "organic_graduation_rate",
                          "rug_within_300s_rate", "creator_sold_within_60s_share")}
                     for k in ("7d", "30d")}
F["loopholetape"]["generated_at"] = STATS["generated_at"]

# 数据集窗口内，我们自己的加总
win = g[g["dl_curve_revenue"].notna()]
F["bottom_up"] = {
    "window": f"{win.index.min()}..{win.index.max()}",
    "peak_rs_classic_sum": round(float(win["peak_rs_classic"].sum()), 1),
    "fee_floor_gross_usd": round(float(win["fee_floor_gross_usd"].sum())),
    "fee_floor_protocol_usd": round(float(win["fee_floor_protocol_usd"].sum())),
    "dl_curve_fees_same_days": round(float(DLS["pumpfun_fees"].reindex(win.index).fillna(0).sum())),
    "dl_curve_revenue_same_days": round(float(win["dl_curve_revenue"].sum())),
}
F["bottom_up"]["floor_vs_dl_fees_pct"] = round(
    F["bottom_up"]["fee_floor_gross_usd"] / F["bottom_up"]["dl_curve_fees_same_days"] * 100, 2)

(ROOT / "facts.json").write_text(json.dumps(F, ensure_ascii=False, indent=1))
print(f"写了 {ROOT/'facts.json'}")
print("\n== 三方口径（30 天，百万美元）")
print(f"  DefiLlama 合计: 费用 {combined['fees_30d']}M 收入 {combined['revenue_30d']}M "
      f"量 {combined['volume_30d_b']}B")
print(f"  DefiLlama 日均收入: 30d {F['defillama']['combined']['revenue_per_day_30d_m']}M | "
      f"7d {F['defillama']['combined']['revenue_per_day_7d_m']}M")
print(f"  fees.pump.fun: 年化 {FEES_PAGE['annualized_revenue_text']}M → 日均 "
      f"{F['fees_page']['implied_daily_from_annualized_m']}M | 最新回购 "
      f"{FEES_PAGE['daily_buyback_text']}K → 隐含日均收入 "
      f"{F['fees_page']['implied_daily_from_buyback_m']}M")
print(f"  自建下界（{F['bottom_up']['window']}）: 毛费率下界 {F['bottom_up']['fee_floor_gross_usd']/1e6:.2f}M "
      f"（协议 {F['bottom_up']['fee_floor_protocol_usd']/1e6:.2f}M） vs DefiLlama 曲线费用同窗口 "
      f"{F['bottom_up']['dl_curve_fees_same_days']/1e6:.2f}M = 下界占 "
      f"{F['bottom_up']['floor_vs_dl_fees_pct']}%（DL 是下界的 {100/F['bottom_up']['floor_vs_dl_fees_pct']:.1f}×）")
print(f"\n== custom pairs")
print(f"  数据集非 SOL 占 {F['dataset']['custom_share_pct']}%；"
      f"quote 分布 {F['dataset']['quote_assets']}")
print(f"  周转倍数（DefiLlama 收入 ÷ 下界）: 09-09 前中位 {F['turnover']['pre_cut']['median_x']}×，"
      f"之后 {F['turnover']['post_cut']['median_x']}×")
