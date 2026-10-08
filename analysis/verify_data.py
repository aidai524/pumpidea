"""核对下载的数据与数据集文档声明是否一致。

为什么要先做这一步：整个报告的分母（发币量）来自这批文件，
如果行数对不上文档，后面所有比率都不可信。文档里给了每个文件的行数与 sha256。
"""
import hashlib, json, pathlib, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

EXPECTED = {                      # 文档「Launch kinds」/「Files in this release」声明
    "launches_rows": 222_893,
    "launches_classic": 139_375,
    "launches_mayhem_sol": 60_386,
    "legacy_rows": 859_208,
    "legacy_classic": 541_752,
    "legacy_mayhem_sol": 230_802,
    "graduation_pools_rows": 10_149,
    "total_launches": 1_082_101,   # 222,893 + 859,208
}

def load(pattern):
    files = sorted(DATA.glob(pattern))
    if not files:
        sys.exit(f"没有文件匹配 {pattern} —— 先跑 analysis/fetch_data.sh")
    frames = [pd.read_parquet(f) for f in files]
    return pd.concat(frames, ignore_index=True), files

def kind(df):
    out = pd.Series("other_quote", index=df.index)
    sol = df["quote_asset"] == "sol"
    out[sol & (df["mayhem"] == 0)] = "classic"
    out[sol & (df["mayhem"] == 1)] = "mayhem_sol"
    out[df["quote_asset"].isna()] = "quote_not_established"
    return out

print("=== launches（解码器完整子集，2026-09-27 起）===")
new, nf = load("launches/*.parquet")
k = kind(new)
print(f"  文件 {len(nf)} 个，行数 {len(new):,}（文档声明 {EXPECTED['launches_rows']:,}）")
for name, exp in (("classic", EXPECTED["launches_classic"]),
                  ("mayhem_sol", EXPECTED["launches_mayhem_sol"])):
    got = int((k == name).sum())
    print(f"  {name:20} {got:>9,}  文档 {exp:>9,}  {'✓' if got == exp else '✗ 不一致'}")
print(f"  columns = {len(new.columns)}（文档声明 43）")
print(f"  decoder_complete==1 的行: {int((new['decoder_complete'] == 1).sum()):,}（文档 222,273）")

print("\n=== launches_legacy（解码器不完整子集，至 2026-09-26）===")
old, of = load("launches_legacy/*.parquet")
ko = kind(old)
print(f"  文件 {len(of)} 个，行数 {len(old):,}（文档声明 {EXPECTED['legacy_rows']:,}）")
for name, exp in (("classic", EXPECTED["legacy_classic"]),
                  ("mayhem_sol", EXPECTED["legacy_mayhem_sol"])):
    got = int((ko == name).sum())
    print(f"  {name:20} {got:>9,}  文档 {exp:>9,}  {'✓' if got == exp else '✗ 不一致'}")

print(f"\n  两子集合计 {len(new) + len(old):,}（文档声明 {EXPECTED['total_launches']:,}）")

print("\n=== 文档给的列（用于后面分析的关键列是否都在）===")
need = ["mint","creator","t0","launched_at","symbol","mayhem","quote_asset","graduated",
        "rugged","rug_dt_s","rug_branch_inferred","rugged_not_graduated","peak_rs",
        "terminal_rs","migrate_dt_s","dev_share","dev_buy_sol","dev_first_sell_dt_s",
        "n_trades","decoder_complete","f10_bundle_wallets","f10_dev_share","f10_n_buys",
        "f10_insider_share","f10_rep_n","f10_rep_rug","f10_rep_grad","features_basis"]
missing = [c for c in need if c not in new.columns]
print(f"  关键列缺失: {missing or '无 ✓'}")

print("\n=== 复核文档的毕业率（classic, launches 子集）===")
classic = new[k == "classic"]
g = classic["graduated"]
print(f"  classic 行数 {len(classic):,}，graduated=1 {int((g == 1).sum()):,}，"
      f"null {int(g.isna().sum()):,}")
print(f"  毕业率 {(g == 1).sum() / len(classic):.4%}（文档 3.11%）")
