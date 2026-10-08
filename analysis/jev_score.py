"""按段位喂 Jev 打分。

**与 stableflow 用的同一套方法**：每个段算一组状态量 → 问模型 4 个结构化问题
（tier 选择 / evidence 分数 / conc_risk 概率 / fee_headroom 概率）→ 汇总。

**一处刻意改动**：原 rubric 的 fee_headroom 问的是"能否承受 0.05% 费率"，
那个数字是为跨链 swap 业务写的；pump.fun 的费率是 1.25%，问 0.05% 没有意义。
所以这一问改成"能否在**当前水平之上**再加 0.25 个百分点而不显著损失量"。
其余三问逐字保留。
"""
from __future__ import annotations

import json, os, pathlib, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
F = json.loads((ROOT / "analysis" / "facts.json").read_text())

KEY = None
env = ROOT.parent / "platform" / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if line.startswith("TYPESAFE_API_KEY="):
            KEY = line.split("=", 1)[1].strip()
if not KEY:
    raise SystemExit("没有 TYPESAFE_API_KEY（在 platform/.env 里）")
EP = "https://api.typesafe.ai/v1/systemone"

QUESTIONS = {
    "tier": {
        "type": "choice",
        "instructions": ("Classify this segment of a Solana memecoin launchpad "
                         "business and pick the single best action."),
        "criteria": {
            "core": "large and reliable: invest to defend and deepen",
            "grow": "rising momentum with acceptable reliability: invest to expand",
            "fix": ("material volume but reliability is clearly below the service "
                    "average: fix engineering quality before spending on growth"),
            "watch": "small, flat, or ambiguous: monitor only",
            "exit": ("declining with no recovery path, or negligible volume: "
                     "deprioritize"),
        },
    },
    "evidence": {
        "type": "score",
        "instructions": ("How strong is the evidence for this call given 32 days of "
                         "on-chain data? The window is shorter than a year, so treat "
                         "confidence accordingly."),
        "criteria": ["no evidence", "weak", "moderate", "strong", "very strong"],
    },
    "conc_risk": {
        "type": "noul",
        "instructions": ("Is this segment dangerously dependent on a single creator, "
                         "wallet cluster, or counterparty?"),
    },
    # 唯一改过的一问，理由见模块 docstring
    "fee_headroom": {
        "type": "noul",
        "instructions": ("Could pump.fun raise its take rate by 0.25 percentage "
                         "points on this segment without a large volume loss? "
                         "(current: 1.25% on the bonding curve)"),
    },
}

NOTE = ("failure_rate_pct is the share of launches flagged as a rug "
        "(drain or dev dump) within 300s. graduation_rate_pct counts true "
        "graduations; instant_graduations completed within 2s of launch and are "
        "bundles, not organic demand.")

def ctx():
    return {"business": "Solana memecoin launchpad (pump.fun)",
            "period_utc": "2026-08-31 to 2026-10-07",
            "note": NOTE,
            "service_average_graduation_rate_pct": 2.06,
            "service_average_rug_within_300s_pct": 57.7}

# 每段的状态量全部来自 facts.json，不手写数字
w30 = F["stats"]["windows"]["30d"]; w7 = F["stats"]["windows"]["7d"]
byk = w30["by_kind"]; hf = F["hf"]; v = hf["veteran"]
d = F["defillama"]; pools = F["stats"]["pools"]
tk = w7["ticker_copies"]

def seg(name, launches, **kw):
    s = {**ctx(), "segment": name, "launches": launches}
    s.update({k: val for k, val in kw.items() if val is not None})
    return {"name": name, "state": s}

SEGMENTS = [
    seg("classic launches (SOL-quoted, not mayhem)", byk["classic"]["launches"],
        share_of_launches_pct=round(byk["classic"]["share_of_launches"] * 100, 2),
        graduation_rate_pct=round(byk["classic"]["graduated"] / byk["classic"]["launches"] * 100, 3),
        failure_rate_pct=round(byk["classic"]["rug_within_300s_rate"] * 100, 2),
        creator_sold_within_60s_pct=round(byk["classic"]["creator_sold_within_60s_share"] * 100, 2),
        volume_30d_usd=d["launchpad"]["volume"]["total30d"],
        fee_rate_pct=1.25),
    seg("mayhem-mode launches (pump.fun agent trades them)", byk["mayhem"]["launches"],
        share_of_launches_pct=round(byk["mayhem"]["share_of_launches"] * 100, 2),
        graduation_rate_pct=round(byk["mayhem"]["graduated"] / byk["mayhem"]["launches"] * 100, 4),
        chain_complete_pct=round(byk["mayhem"]["complete_share"] * 100, 2),
        failure_rate_pct=round(byk["mayhem"]["rug_within_300s_rate"] * 100, 2),
        creator_sold_within_60s_pct=round(byk["mayhem"]["creator_sold_within_60s_share"] * 100, 2),
        note_on_fees="agent pays no protocol fee; other traders' fees go to an insurance fund"),
    seg("other-quote launches (USDC/PYUSD/tokenized stocks)", byk["other_quote"]["launches"],
        share_of_launches_pct=round(byk["other_quote"]["share_of_launches"] * 100, 2),
        chain_complete_pct=round(byk["other_quote"]["complete_share"] * 100, 2),
        creator_sold_within_60s_pct=round(byk["other_quote"]["creator_sold_within_60s_share"] * 100, 2)),
    seg("first-time creators (0 prior launches)", v["by_prior_launches"]["0"]["n"],
        graduation_rate_pct=v["by_prior_launches"]["0"]["graduation_rate_pct"],
        failure_rate_pct=v["by_prior_launches"]["0"]["rug_rate_pct"],
        mean_bundle_wallets=v["by_prior_launches"]["0"]["mean_bundle_wallets"]),
    seg("serial creators (20+ prior launches)", v["by_prior_launches"]["20+"]["n"],
        graduation_rate_pct=v["by_prior_launches"]["20+"]["graduation_rate_pct"],
        failure_rate_pct=v["by_prior_launches"]["20+"]["rug_rate_pct"],
        mean_prior_rugs=v["by_prior_launches"]["20+"]["mean_prior_rugs"],
        mean_bundle_wallets=v["by_prior_launches"]["20+"]["mean_bundle_wallets"]),
    seg("graduated pools on PumpSwap (first 30 min)", pools["full_pools"],
        lost_90pct_in_30min_pct=round(pools["share_lost_90pct_in_30m"] * 100, 2),
        median_seconds_to_collapse=pools["median_s_to_collapse"],
        survivors_above_open_pct=round(pools["survivors_ending_above_open_share"] * 100, 2),
        volume_30d_usd=d["pumpswap"]["volume"]["total30d"],
        fee_rate_pct=0.30,
        protocol_take_pct=0.05),
    seg("instant (bundled) graduations", w30["instant_graduations"],
        share_of_all_graduations_pct=round(w30["instant_share_of_graduations"] * 100, 2),
        median_seconds_to_graduation=w30["median_s_to_graduation_all"]),
    seg("organic graduations", w30["organic_graduations"],
        graduation_rate_pct=round(w30["organic_graduation_rate"] * 100, 3),
        median_seconds_to_graduation=w30["median_s_to_graduation_organic"]),
    seg("ticker-copied launches", tk["launches_with_ticker"],
        organic_graduates_sharing_ticker_pct=round(tk["sharing_ticker_share"] * 100, 2),
        median_other_mints_same_ticker=tk["median_other_mints_same_ticker"],
        distinct_tickers=tk["distinct_tickers"]),
    seg("top-1000 creators (by launch count)", int(F["hf"]["creator_concentration"]["launches"]["launches"] * F["hf"]["creator_concentration"]["launches"]["top1000_share_pct"] / 100),
        creators=1000,
        share_of_all_launches_pct=F["hf"]["creator_concentration"]["launches"]["top1000_share_pct"],
        note="6.1% of creators produce half of all launches"),
]

def ask(state):
    body = json.dumps({"model": "jev-latest", "state": state, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(EP, data=body, headers={
        "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["answers"]
        except Exception as e:
            if a == 3:
                raise
            print(f"    重试 {a+1}: {e}")
            time.sleep(2)

out = []
for i, s in enumerate(SEGMENTS, 1):
    print(f"  [{i}/{len(SEGMENTS)}] {s['name'][:52]}")
    a = ask(s["state"])
    out.append({**s, "answers": a})
    print(f"        tier={a.get('tier',{}).get('choice')}  "
          f"evidence={a.get('evidence',{}).get('score')}  "
          f"conc={a.get('conc_risk',{}).get('noul')}  "
          f"fee={a.get('fee_headroom',{}).get('noul')}")

(ROOT / "analysis" / "jev_segments.json").write_text(
    json.dumps({"questions": QUESTIONS, "segments": out}, ensure_ascii=False, indent=1))
print(f"\n  ✅ 写了 analysis/jev_segments.json（{len(out)} 段）")
