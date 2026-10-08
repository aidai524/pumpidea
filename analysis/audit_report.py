"""把 report.md 里引用的数字逐个对回 facts.json。

为什么需要：报告是手写的（为了让文字连贯），而手写转抄数字是最容易出错的一环。
这个脚本把"报告里写的"与"算出来的"绑在一起，改一个就对不上。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
F = json.loads((ROOT / "analysis" / "facts.json").read_text())
W = F["stats"]["windows"]; w30, w7 = W["30d"], W["7d"]
BY = w30["by_kind"]; HF = F["hf"]; D = F["defillama"]; P = F["stats"]["pools"]
C = HF["creator_concentration"]["launches"]; V = HF["veteran"]; R = F["revenue"]

# 报告里写下的数字 → 从 facts.json 算出的期望值
CHECKS = {
    "30d 发币量":            (1156058, w30["launches"]),
    "7d 发币量":             (358000,  w7["launches"]),
    "30d 毕业数":            (23793,   w30["graduated"]),
    "名义毕业率 2.06%":      (2.06,    round(w30["graduation_rate"] * 100, 2)),
    "瞬时毕业数":            (13796,   w30["instant_graduations"]),
    "瞬时占比 58.0%":        (58.0,    round(w30["instant_share_of_graduations"] * 100, 1)),
    "有机毕业数":            (9997,    w30["organic_graduations"]),
    "有机毕业率 0.86%":      (0.86,    round(w30["organic_graduation_rate"] * 100, 2)),
    "毕业中位耗时 0.367s":   (0.367,   w30["median_s_to_graduation_all"]),
    "有机中位耗时 228.5s":   (228.5,   w30["median_s_to_graduation_organic"]),
    "300s 跑路数":           (667344,  w30["rugged_within_300s"]),
    "跑路率 57.7%":          (57.7,    round(w30["rug_within_300s_rate"] * 100, 1)),
    "创建者60s卖出数":       (584879,  w30["creator_sold_within_60s"]),
    "创建者60s占比 50.6%":   (50.6,    round(w30["creator_sold_within_60s_share"] * 100, 1)),
    "classic 发币":          (723695,  BY["classic"]["launches"]),
    "classic 毕业率 3.28%":  (3.28,    round(BY["classic"]["graduated"] / BY["classic"]["launches"] * 100, 2)),
    "classic 跑路 55.4%":    (55.4,    round(BY["classic"]["rug_within_300s_rate"] * 100, 1)),
    "mayhem 发币":           (302812,  BY["mayhem"]["launches"]),
    "mayhem 毕业率 0.017%":  (0.017,   round(BY["mayhem"]["graduated"] / BY["mayhem"]["launches"] * 100, 3)),
    "mayhem 跑路 87.9%":     (87.9,    round(BY["mayhem"]["rug_within_300s_rate"] * 100, 1)),
    "mayhem 60s 卖 69.1%":   (69.1,    round(BY["mayhem"]["creator_sold_within_60s_share"] * 100, 1)),
    "other_quote 发币":      (129531,  BY["other_quote"]["launches"]),
    "池子数 6545":           (6545,    P["full_pools"]),
    "池子跌90% 62.4%":       (62.4,    round(P["share_lost_90pct_in_30m"] * 100, 1)),
    "中位崩盘 475.3s":       (475.3,   P["median_s_to_collapse"]),
    "创建者总数":            (59631,   C["creators"]),
    "top1 发币 2627":        (2627,    C["top1"]),
    "top1000 占 35.55%":     (35.55,   C["top1000_share_pct"]),
    "半量创建者 3651":       (3651,    C["creators_for_half"]),
    "新建钱包毕业 6.82%":    (6.82,    V["by_prior_launches"]["0"]["graduation_rate_pct"]),
    "20+毕业 0.94%":         (0.94,    V["by_prior_launches"]["20+"]["graduation_rate_pct"]),
    "20+历史跑路 0.689":     (0.689,   V["by_prior_launches"]["20+"]["mean_prior_rugs"]),
    "抽样毕业 3.117%":       (3.117,   V["sampled_graduation_rate_pct"]),
    "未抽样毕业 2.992%":     (2.992,   V["unsampled_graduation_rate_pct"]),
    "抽样跑路 65.33%":       (65.33,   V["sampled_rug_rate_pct"]),
    "未抽样跑路 66.47%":     (66.47,   V["unsampled_rug_rate_pct"]),
    "peak_rs p50 2.01":      (2.008,   HF["peak_rs"]["launches"]["p50"]),
    "peak_rs p90 22.9":      (22.919,  HF["peak_rs"]["launches"]["p90"]),
    "peak_rs p99 85.0":      (85.005,  HF["peak_rs"]["launches"]["p99"]),
    "捆绑p50 1":             (1.0,     HF["bundling"]["p50"]),
    "零捆绑 41.4%":          (41.4,    HF["bundling"]["share_zero_pct"]),
    "≥5捆绑 14.4%":          (14.4,    HF["bundling"]["share_ge5_pct"]),
    "dev_share p50 1.74%":   (1.74,    round(HF["dev_share"]["p50"] * 100, 2)),
    "dev_share p99 79.3%":   (79.3,    round(HF["dev_share"]["p99"] * 100, 1)),
    "撞名毕业 98.6%":        (98.6,    round(w7["ticker_copies"]["sharing_ticker_share"] * 100, 1)),
    "同名中位 26":           (26,      w7["ticker_copies"]["median_other_mints_same_ticker"]),
    "标签召回 98.61%":       (98.61,   round(F["stats"]["label_check"]["recall"] * 100, 2)),
    "标签精确 99.98%":       (99.98,   round(F["stats"]["label_check"]["precision"] * 100, 2)),
    "发币端收入 39.3M":      (39.3,    round(D["launchpad"]["revenue"]["total30d"] / 1e6, 1)),
    "发币端费用 55.3M":      (55.3,    round(D["launchpad"]["fees"]["total30d"] / 1e6, 1)),
    "PumpSwap 收入 15.2M":   (15.2,    round(D["pumpswap"]["revenue"]["total30d"] / 1e6, 1)),
    "PumpSwap 费用 116.3M":  (116.3,   round(D["pumpswap"]["fees"]["total30d"] / 1e6, 1)),
    "合计收入 54.5M":        (54.5,    round(D["combined_30d"]["revenue"] / 1e6, 1)),
    "合计费用 171.6M":       (171.6,   round(D["combined_30d"]["fees"] / 1e6, 1)),
    "合计量 15.36B":         (15.36,   round(D["combined_30d"]["volume"] / 1e9, 2)),
    "发币端抽成 1.077%":     (1.077,   round(D["launchpad"]["revenue"]["total30d"] / D["launchpad"]["volume"]["total30d"] * 100, 3)),
    "PumpSwap 抽成 0.130%":  (0.130,   round(D["pumpswap"]["revenue"]["total30d"] / D["pumpswap"]["volume"]["total30d"] * 100, 3)),
    "SOL 价格 114.94":       (114.94,  R["sol_usd"]),
    "Σpeak_rs 586.9万":      (5869339, R["peak_rs_sum_sol_total"]),
    "毛下界 8.43M":          (8.43,    round(R["fee_floor_gross_usd"] / 1e6, 2)),
    "协议下界 6.41M":        (6.41,    round(R["fee_floor_protocol_usd"] / 1e6, 2)),
    "发币量周增幅 74.1%":    (74.1,    F["stats"]["trend"]["change"]["launches_pct"]),
    "毕业率变化 -0.477pp":   (-0.477,  F["stats"]["trend"]["change"]["graduation_rate_pp"]),
}

bad = []
for label, (in_report, computed) in CHECKS.items():
    # 相对容差：报告里的数字是四舍五入后写下的（5869339 vs 5869338.93）
    if isinstance(computed, (int, float)) and isinstance(in_report, (int, float)):
        ok = abs(in_report - computed) <= max(0.51, abs(computed) * 1e-4)
    else:
        ok = in_report == computed
    if not ok:
        bad.append((label, in_report, computed))

print(f"  核对 {len(CHECKS)} 项")
if bad:
    print(f"  ✗ {len(bad)} 项对不上：")
    for label, a, b in bad:
        print(f"      {label}: 报告写 {a}  算出来 {b}")
    sys.exit(1)
print("  ✅ 全部与 facts.json 一致")

# 再核对报告里出现的几个"手写句子里的数字"确实出现在报告文本里
text = (ROOT / "report.md").read_text()
for needle in ("1,156,058", "2.06%", "0.86%", "58.0%", "57.7%", "50.6%",
               "$54.5M", "$171.6M", "$15.36B", "1.077%", "0.130%",
               "35.55%", "3,651", "62.35%", "0.017%"):
    if needle not in text:
        print(f"  ⚠️ 报告正文里找不到 {needle}")
print("  报告正文引用检查完成")
