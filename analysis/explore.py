"""探索：哪些维度真能算、分布长什么样。"""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
pd.set_option("display.width", 200, "display.max_columns", 60)

new = pd.concat([pd.read_parquet(f) for f in sorted(DATA.glob("launches/*.parquet"))],
                ignore_index=True)
old = pd.concat([pd.read_parquet(f) for f in sorted(DATA.glob("launches_legacy/*.parquet"))],
                ignore_index=True)

print("=== 列清单（launches）===")
print("  " + "  ".join(sorted(new.columns)))
print(f"\n  n_trades 在 launches: {'n_trades' in new.columns}"
      f" / 在 legacy: {'n_trades' in old.columns}")

def kind(df):
    out = pd.Series("other_quote", index=df.index)
    sol = df["quote_asset"] == "sol"
    out[sol & (df["mayhem"] == 0)] = "classic"
    out[sol & (df["mayhem"] == 1)] = "mayhem_sol"
    return out

for label, df in (("launches(clean)", new), ("legacy", old)):
    df["kind"] = kind(df)
    print(f"\n=== {label}：结局列的可解析率 ===")
    for c in ("graduated", "rugged", "peak_rs", "rug_dt_s", "migrate_dt_s",
              "dev_share", "dev_buy_sol", "f10_bundle_wallets", "f10_rep_n"):
        if c in df.columns:
            nn = df[c].notna().mean()
            print(f"  {c:20} 非空 {nn:6.1%}")

print("\n=== 跑路分支（DRAIN vs DEV DUMP）===")
for label, df in (("launches(clean)", new), ("legacy", old)):
    sub = df[df["kind"] == "classic"]
    vc = sub["rug_branch_inferred"].value_counts(dropna=False)
    print(f"  {label}: {dict(vc.head(6))}")

print("\n=== peak_rs 分布（classic，SOL 计价）===")
for label, df in (("launches(clean)", new), ("legacy", old)):
    p = df.loc[df["kind"] == "classic", "peak_rs"].dropna()
    qs = p.quantile([.5, .75, .9, .95, .99, .999, 1.0]).round(3)
    print(f"  {label}: n={len(p):,}  " + "  ".join(f"p{int(q*1000)/10}={v}" for q, v in qs.items()))

print("\n=== 创建者集中度（clean 子集，classic）===")
c = new[new["kind"] == "classic"]
per = c.groupby("creator").size().sort_values(ascending=False)
print(f"  唯一创建者 {len(per):,}，发币 {len(c):,} → 人均 {len(c)/len(per):.2f}")
print(f"  top1 创建者发币 {per.iloc[0]:,} 个 = 总发币的 {per.iloc[0]/len(c):.2%}")
for n in (10, 100, 1000):
    print(f"  top{n:>5} 创建者占发币总量 {per.head(n).sum()/len(c):6.2%}")

print("\n=== 老手 vs 新手：f10_rep_n（此前已解析过的发币数）===")
s = c[c["f10_rep_n"].notna()]
print(f"  有该特征的行 {len(s):,}")
b = pd.cut(s["f10_rep_n"], [-1, 0, 1, 4, 19, 1e9],
           labels=["0 次(新号)", "1", "2-4", "5-19", "20+"])
t = s.groupby(b, observed=True).agg(发币数=("graduated", "size"),
                                    毕业率=("graduated", "mean"),
                                    跑路率=("rugged", "mean"),
                                    历史跑路数=("f10_rep_rug", "mean"))
print(t.to_string(float_format=lambda v: f"{v:.4f}"))

print("\n=== ticker 抄袭（clean 子集，仅统计）===")
sym = c["symbol"].str.upper().str.strip()
sym = sym[sym.str.len() > 0]
print(f"  唯一 ticker {sym.nunique():,} / 发币 {len(sym):,} → 每个 ticker 平均 {len(sym)/sym.nunique():.1f} 个币")
top = sym.value_counts().head(12)
print("  被发最多的 ticker：")
for t_, n_ in top.items():
    sub = c[sym == t_]
    print(f"    {t_:12} {n_:>6,} 个币   毕业 {int((sub['graduated']==1).sum()):>3}  跑路 {sub['rugged'].mean():6.1%}")
