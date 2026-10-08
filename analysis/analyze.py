"""pump.fun 研究的全部计算。输出一份 JSON，报告只消费它、不再自己算。

三个数据源各司其职，**不混用**：
  stats API   → 总体比率（分母是全量发币，无抽样偏差）
  DefiLlama   → 手续费与协议收入（权威第三方口径）
  HF 数据集   → 分布与创建者行为（**有抽样偏差，必须带注**，见 KI-01）
"""
import json, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "analysis" / "facts.json"
SOL_USD = json.loads((DATA / "sol_price.json").read_text())["solana"]["usd"]
F = {}

# ---------------------------------------------------------------- 1. stats API
S = json.loads((DATA / "stats_2026-10-08.json").read_text())
F["stats"] = {"generated_at": S["generated_at"], "coverage": S["coverage"],
              "provenance": S["provenance"], "label_check": S["label_check"],
              "windows": {}, "pools": S["pools"], "definitions": S["definitions"]}
for w in ("7d", "30d"):
    d = S["windows"][w]
    # 有些键只在某些窗口出现（ticker_copies 只在 30d），所以容错取
    F["stats"]["windows"][w] = {k: d.get(k) for k in (
        "days", "from", "to", "launches", "graduated", "graduation_rate",
        "instant_graduations", "instant_share_of_graduations",
        "organic_graduations", "organic_graduation_rate",
        "median_s_to_graduation_all", "median_s_to_graduation_organic",
        "rugged_within_300s", "rug_within_300s_rate",
        "creator_sold_within_60s", "creator_sold_within_60s_share",
        "by_kind", "ticker_copies")}
days = pd.DataFrame(S["days"])
days["day"] = pd.to_datetime(days["day"])
F["stats"]["daily"] = [
    {k: (r[k] if not isinstance(r[k], (pd.Timestamp,)) else r[k].strftime("%Y-%m-%d"))
     for k in ("day", "settling", "launches", "graduated", "graduation_rate",
               "instant_share_of_graduations", "organic_graduation_rate",
               "rug_within_300s_rate", "creator_sold_within_60s_share")}
    for r in days.to_dict("records")]

# 趋势：**必须按时间升序**算 —— API 返回的 days 是倒序（最新在前），
# 按原顺序比"首 7 日 vs 末 7 日"会把方向读反。（写这一版时差点写反。）
_asc = sorted(F["stats"]["daily"], key=lambda x: x["day"])
def _avg(xs, k):
    return sum(x[k] for x in xs) / len(xs)
F["stats"]["trend"] = {
    "order": "ascending",
    "first_week": _asc[0]["day"], "last_week": _asc[-1]["day"],
    "weekly": [
        {"from": w[0]["day"], "to": w[-1]["day"],
         **{k: round(_avg(w, k), 6) for k in (
             "launches", "graduation_rate", "organic_graduation_rate",
             "instant_share_of_graduations", "rug_within_300s_rate",
             "creator_sold_within_60s_share")}}
        for w in (_asc[i:i + 7] for i in range(0, len(_asc) - len(_asc) % 7, 7))],
}
_fw, _lw = _asc[:7], _asc[-7:]
F["stats"]["trend"]["change"] = {
    "launches_pct": round((_avg(_lw, "launches") / _avg(_fw, "launches") - 1) * 100, 1),
    "graduation_rate_pp": round((_avg(_lw, "graduation_rate") - _avg(_fw, "graduation_rate")) * 100, 3),
    "organic_graduation_rate_pp": round((_avg(_lw, "organic_graduation_rate") - _avg(_fw, "organic_graduation_rate")) * 100, 3),
    "instant_share_pp": round((_avg(_lw, "instant_share_of_graduations") - _avg(_fw, "instant_share_of_graduations")) * 100, 2),
}

# ---------------------------------------------------------------- 2. DefiLlama
for slug, key in (("pump.fun", "launchpad"), ("pumpswap", "pumpswap")):
    for kind in ("fees", "revenue"):
        d = json.loads((DATA / f"defillama_{kind}_{slug}.json").read_text())
        F.setdefault("defillama", {}).setdefault(key, {})[kind] = {
            "total24h": d["total24h"], "total7d": d["total7d"],
            "total30d": d["total30d"], "total1y": d["total1y"],
            "totalAllTime": d.get("totalAllTime"),
            "chart": d["totalDataChart"][-45:],   # [ts_seconds, value]
        }

# 交易量（与费用同源，用于算隐含费率）
F.setdefault("defillama", {})
for slug, key in (("pump.fun", "launchpad"), ("pumpswap", "pumpswap")):
    f = DATA / f"defillama_volume_{slug}.json"
    if f.exists():
        d = json.loads(f.read_text())
        F["defillama"][key]["volume"] = {
            "total24h": d.get("total24h"), "total30d": d.get("total30d"),
            "totalAllTime": d.get("totalAllTime")}
_v = [F["defillama"][k]["volume"]["total30d"] for k in ("launchpad", "pumpswap")
      if "volume" in F["defillama"][k]]
_f = [F["defillama"][k]["fees"]["total30d"] for k in ("launchpad", "pumpswap")]
if _v and _f:
    F["defillama"]["combined_30d"] = {
        "volume": sum(_v), "fees": sum(_f),
        "revenue": sum(F["defillama"][k]["revenue"]["total30d"]
                       for k in ("launchpad", "pumpswap")),
        "implied_blended_fee_rate": round(sum(_f) / sum(_v), 5)}

# ---------------------------------------------------------------- 3. HF 数据集
def kind_of(df):
    out = pd.Series("other_quote", index=df.index)
    sol = df["quote_asset"] == "sol"
    out[sol & (df["mayhem"] == 0)] = "classic"
    out[sol & (df["mayhem"] == 1)] = "mayhem_sol"
    return out

new = pd.concat([pd.read_parquet(f) for f in sorted(DATA.glob("launches/*.parquet"))],
                ignore_index=True)
old = pd.concat([pd.read_parquet(f) for f in sorted(DATA.glob("launches_legacy/*.parquet"))],
                ignore_index=True)
for df in (new, old):
    df["kind"] = kind_of(df)
    df["day"] = pd.to_datetime(df["t0"], unit="s").dt.floor("D")

hf = {}
hf["rows"] = {"launches": len(new), "legacy": len(old), "total": len(new) + len(old)}
hf["columns"] = len(new.columns)
hf["kind_share"] = {
    "launches": (new["kind"].value_counts(normalize=True) * 100).round(2).to_dict(),
    "legacy": (old["kind"].value_counts(normalize=True) * 100).round(2).to_dict(),
}

# 结局：两个子集分开报，因为 legacy 的解码器不完整（KI-02）
outcomes = {}
for label, df in (("launches", new), ("legacy", old)):
    c = df[df["kind"] == "classic"]
    resolved = c[c["rugged"].notna()]
    outcomes[label] = {
        "classic_launches": len(c),
        "graduated": int((c["graduated"] == 1).sum()),
        "graduation_rate_pct": round((c["graduated"] == 1).mean() * 100, 4),
        "rug_resolved_n": len(resolved),
        "rugged_pct_of_resolved": round(resolved["rugged"].mean() * 100, 2),
        "rugged_not_graduated_n": int((c["rugged_not_graduated"] == 1).sum()),
        "unresolved_pct": round(c["rugged"].isna().mean() * 100, 2),
        "branch": {k: int(v) for k, v in
                   c["rug_branch_inferred"].value_counts(dropna=False).items()},
    }
hf["outcomes"] = outcomes

# peak_rs 分布：曲线上限 85 SOL
dist = {}
for label, df in (("launches", new), ("legacy", old)):
    p = df.loc[df["kind"] == "classic", "peak_rs"].dropna()
    dist[label] = {"n": len(p), **{f"p{int(q*100)}": round(float(p.quantile(q)), 3)
                                   for q in (.25, .5, .75, .9, .95, .99)},
                   "max": round(float(p.max()), 3),
                   "above_cap_n": int((p > 85.1).sum())}
hf["peak_rs"] = dist

# 创建者集中度
conc = {}
for label, df in (("launches", new), ("legacy", old)):
    c = df[df["kind"] == "classic"]
    per = c.groupby("creator").size().sort_values(ascending=False)
    conc[label] = {
        "creators": len(per), "launches": len(c),
        "per_creator_mean": round(len(c) / len(per), 2),
        "top1": int(per.iloc[0]), "top1_share_pct": round(per.iloc[0] / len(c) * 100, 2),
        "top10_share_pct": round(per.head(10).sum() / len(c) * 100, 2),
        "top100_share_pct": round(per.head(100).sum() / len(c) * 100, 2),
        "top1000_share_pct": round(per.head(1000).sum() / len(c) * 100, 2),
        "creators_for_half": int((per.cumsum() / len(c)).searchsorted(0.5)),
    }
hf["creator_concentration"] = conc

# 老手 vs 新手（**有抽样偏差**，KI-01）
veteran = {}
c = new[new["kind"] == "classic"]
# 用 f10_age 判"是否被抽样" —— 快照存在才算抽样。
# 不能用 f10_rep_n 非空：抽样了但快照缺 rep 字段的行也会是 null（KI-01）。
sampled = c[c["f10_age"].notna()]
unsampled = c[c["f10_age"].isna()]
veteran["sampled_rows"] = len(sampled)
veteran["sampled_share_of_classic_pct"] = round(len(sampled) / len(c) * 100, 2)
veteran["sampled_graduation_rate_pct"] = round((sampled["graduated"] == 1).mean() * 100, 3)
veteran["sampled_rug_rate_pct"] = round(sampled["rugged"].mean() * 100, 2)
veteran["unsampled_rows"] = len(unsampled)
veteran["unsampled_graduation_rate_pct"] = round(
    (unsampled["graduated"] == 1).mean() * 100, 3)
veteran["unsampled_rug_rate_pct"] = round(unsampled["rugged"].mean() * 100, 2)
# 老手分层只在**有 rep 数据**的行上做（这是该列的定义域）
s = sampled[sampled["f10_rep_n"].notna()]
veteran["rep_rows"] = len(s)
b = pd.cut(s["f10_rep_n"], [-1, 0, 1, 4, 19, 1e9],
           labels=["0", "1", "2-4", "5-19", "20+"])
g = s.groupby(b, observed=True).agg(
    n=("graduated", "size"), grad=("graduated", "mean"), rug=("rugged", "mean"),
    prior_rugs=("f10_rep_rug", "mean"), dev_share=("f10_dev_share", "mean"),
    bundle=("f10_bundle_wallets", "mean"))
veteran["by_prior_launches"] = {
    str(i): {"n": int(r.n), "graduation_rate_pct": round(r.grad * 100, 2),
             "rug_rate_pct": round(r.rug * 100, 2),
             "mean_prior_rugs": round(r.prior_rugs, 3) if pd.notna(r.prior_rugs) else None,
             "mean_dev_share_pct": round(r.dev_share * 100, 2) if pd.notna(r.dev_share) else None,
             "mean_bundle_wallets": round(r.bundle, 2) if pd.notna(r.bundle) else None}
    for i, r in g.iterrows()}
hf["veteran"] = veteran

# ticker 抄袭
sym = c.assign(sym=c["symbol"].fillna("").str.upper().str.strip())
sym = sym[sym["sym"].str.len() > 0]
vc = sym["sym"].value_counts()
hf["tickers"] = {
    "unique": int(vc.size), "launches": int(len(sym)),
    "mean_per_ticker": round(len(sym) / vc.size, 2),
    "top": [{"ticker": t, "n": int(n),
             "graduated": int(sym.loc[sym["sym"] == t, "graduated"].sum()),
             "rug_rate_pct": round(float(sym.loc[sym["sym"] == t, "rugged"].mean() * 100), 1)}
            for t, n in vc.head(15).items()],
}

# dev_share / 捆绑钱包 分布
b2 = c["f10_bundle_wallets"].dropna()
hf["bundling"] = {"n": len(b2), **{f"p{int(q*100)}": float(b2.quantile(q))
                                   for q in (.5, .75, .9, .95, .99)},
                  "share_zero_pct": round((b2 == 0).mean() * 100, 1),
                  "share_ge5_pct": round((b2 >= 5).mean() * 100, 1),
                  "share_ge10_pct": round((b2 >= 10).mean() * 100, 1)}
d2 = c["dev_share"].dropna()
hf["dev_share"] = {"n": len(d2), **{f"p{int(q*100)}": float(d2.quantile(q))
                                    for q in (.5, .75, .9, .95, .99)}}

# 收入下界：Σ peak_rs 是"买入净流入"的下界 → ×1% 为曲线手续费的下界
peak_sum = {label: float(df.loc[df["kind"] == "classic", "peak_rs"].sum())
            for label, df in (("launches", new), ("legacy", old))}
# Σ peak_rs 是"买入**净流入**"的下界（每格的峰值储备 ≤ 该格累计买入），
# 所以 1% × Σ peak_rs 是**曲线手续费的下界**。它远低于真实值，因为：
#   - 只算净流入，不含卖出，也不含同一笔钱反复买卖的周转
#   - 完全不含毕业后的 PumpSwap 交易（而那才是现在的大头）
# 但它不需要信任任何第三方，可以独立校验 DefiLlama 的量级。
FEE_GROSS = 0.0125      # 曲线毛费率（创作者 0.30% + 协议 0.95%）
FEE_PROTOCOL = 0.0095   # 曲线里属于 pump.fun 的那一份
# 来源：pump.fun/docs/fees（2026-05-20 更新）；PumpSwap 协议分成只有 0.05%
peak_total = sum(peak_sum.values())
F["revenue"] = {
    "sol_usd": SOL_USD, "sol_usd_source": "CoinGecko 2026-10-08",
    "peak_rs_sum_sol": peak_sum, "peak_rs_sum_sol_total": peak_total,
    "days_covered": 32,
    "fee_gross": FEE_GROSS, "fee_protocol": FEE_PROTOCOL,
    "volume_floor_usd": round(peak_total * SOL_USD),
    "fee_floor_gross_usd": round(peak_total * FEE_GROSS * SOL_USD),
    "fee_floor_protocol_usd": round(peak_total * FEE_PROTOCOL * SOL_USD),
    "note": ("下界 = 费率 × Σ peak_rs；只含曲线的**买入净流入**，"
             "不含卖出侧、不含同一笔钱反复买卖的周转、不含毕业后的 PumpSwap"),
}

F["hf"] = hf
OUT.write_text(json.dumps(F, ensure_ascii=False, indent=1, default=str))
print(f"写了 {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
