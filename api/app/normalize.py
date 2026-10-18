"""归一化：上游 JSON → `/api/v1` 契约。

**这是整个 BFF 存在的理由。** 前端只依赖本文件定义的形状，不依赖任何上游字段名。
上游改字段时只改这里；这里改形状时改 `CONTRACT_VERSION`。

三条必须遵守的规则（见 spec §7.3）：

1. **比率一律是 0~1 的小数**，字段名一律 `*_rate`。上游是混着来的 ——
   `graduation_rate: 0.0205`（小数）与 `rug_rate_pct: 65.4`（百分数）同时存在。
   混用两种量纲是现有代码里已经踩过的坑，契约层必须统一。
   需要百分数时由前端自己乘 100，后端不再产生 `*_pct`。
2. **每个响应都带 `generated_at`**（上游数据的生成时间，不是请求时间）。
   三条线的产出频率差几个数量级，不标陈旧度会误导。
3. **双口径必须在结构上分开**。audit 的 `all`（含长尾报价资产）会被单一
   低流动性资产放大两个数量级 —— 实测 2026-10-15 的 `holder_rewards` 全价口径
   是 23.5 亿 USD。所以不是把两套字段并排，而是分成 `all` / `liq` 两个子对象，
   让"混用"在类型上就做不到。
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "v1"

# 已知口径缺陷（与 report.md §8.2 保持一致）。前端必须把它显示出来 ——
# 这些数字的适用范围比"看起来"窄得多。
CAVEATS: list[dict[str, str]] = [
    {"key": "window", "title": "窗口只有 30~32 天",
     "detail": "不足以谈季节性，也不足以判断趋势是否持续"},
    {"key": "ki02", "title": "2026-09-27 前解码器漏约 48% 买单",
     "detail": "KI-02 —— 涉时序的分析只用 09-27 之后的 5 天"},
    {"key": "ki01", "title": "f10_* 在旧子集是非随机抽样",
     "detail": "KI-01 —— 干净窗口改为逐币重放 tape_replay，占 99.74%"},
    {"key": "ki13", "title": "rugged 与 graduated 不互斥",
     "detail": "KI-13 —— 9.9% 兼有，故「跑路率」≠ 1 − 毕业率"},
    {"key": "rug_rule", "title": "rugged 是观察规则，不是已验证欺诈",
     "detail": "多数是创建者在小曲线上砸自己的盘"},
    {"key": "mayhem", "title": "mayhem 占比与第三方差 3.5 倍",
     "detail": "本报告 26% vs 一份 2026-01 的 Dune 分析约 91%，更可能来自口径"},
    {"key": "floor", "title": "收入下界比实际低约 20 倍",
     "detail": "下界只含曲线净流入；它的用途是校验量级，不是估计值"},
    {"key": "dl", "title": "DefiLlama 的量与费口径不一致",
     "detail": "它的 PumpSwap 量会过滤刷量池，费用不过滤 —— 不要用量除费"},
]


# ------------------------------------------------------------------ 工具
def _num(v: Any) -> float | None:
    """转 float，None/非数字 → None。契约里用 None 表示"未知"，不用 0 ——
    0 和"没测到"是两件事，混起来会让平均值静默偏移。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_to_rate(v: Any) -> float | None:
    """上游的 `*_pct`（0~100）→ 契约的 0~1。"""
    x = _num(v)
    return None if x is None else round(x / 100.0, 6)


def _rate(v: Any) -> float | None:
    """上游本来就是 0~1 的比率。"""
    x = _num(v)
    return None if x is None else round(x, 6)


def _round(v: Any, nd: int = 4) -> float | None:
    x = _num(v)
    return None if x is None else round(x, nd)


# ------------------------------------------------------------------ analysis
def analysis_overview(facts: dict) -> dict:
    st = facts["stats"]
    w = st["windows"]["30d"]
    kinds = w.get("by_kind") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": st.get("generated_at"),
        "window": {
            "from": st["coverage"]["first_day"],
            "to": st["coverage"]["last_day"],
            "days": st["coverage"]["days"],
        },
        "kpis": {
            "launches": _num(w.get("launches")),
            "graduated": _num(w.get("graduated")),
            "graduation_rate": _rate(w.get("graduation_rate")),
            "organic_graduations": _num(w.get("organic_graduations")),
            "organic_graduation_rate": _rate(w.get("organic_graduation_rate")),
            "instant_graduations": _num(w.get("instant_graduations")),
            "instant_share_of_graduations": _rate(w.get("instant_share_of_graduations")),
            "rugged_within_300s": _num(w.get("rugged_within_300s")),
            "rug_rate_within_300s": _rate(w.get("rug_within_300s_rate")),
            "creator_sold_within_60s": _num(w.get("creator_sold_within_60s")),
            "creator_sold_within_60s_rate": _rate(w.get("creator_sold_within_60s_share")),
            "median_seconds_to_graduation": _num(w.get("median_s_to_graduation_all")),
            "median_seconds_to_graduation_organic":
                _num(w.get("median_s_to_graduation_organic")),
        },
        "by_kind": {
            k: {
                "launches": _num(v.get("launches")),
                "share_of_launches": _rate(v.get("share_of_launches")),
                "graduation_rate": _rate(v.get("graduation_rate")),
                "complete_on_chain_share": (
                    _rate(v.get("complete_share"))
                    if v.get("complete_share") is not None
                    else _rate((v.get("complete_on_chain") or 0) / v["launches"]
                               if v.get("launches") else None)),
                "rug_rate_within_300s": _rate(v.get("rug_within_300s_rate")),
                "creator_sold_within_60s_rate":
                    _rate(v.get("creator_sold_within_60s_share")),
            }
            for k, v in kinds.items()
        },
        "daily": [
            {
                "day": d["day"],
                "settling": bool(d.get("settling")),
                "launches": _num(d.get("launches")),
                "graduation_rate": _rate(d.get("graduation_rate")),
                "organic_graduation_rate": _rate(d.get("organic_graduation_rate")),
                "instant_share_of_graduations":
                    _rate(d.get("instant_share_of_graduations")),
                "rug_rate_within_300s": _rate(d.get("rug_within_300s_rate")),
                "creator_sold_within_60s_rate":
                    _rate(d.get("creator_sold_within_60s_share")),
            }
            for d in st.get("daily", [])
        ],
        "weekly": [
            {
                "from": x["from"],
                "to": x["to"],
                "launches_per_day": _round(x.get("launches"), 1),
                "graduation_rate": _rate(x.get("graduation_rate")),
                "organic_graduation_rate": _rate(x.get("organic_graduation_rate")),
                "instant_share_of_graduations":
                    _rate(x.get("instant_share_of_graduations")),
                "rug_rate_within_300s": _rate(x.get("rug_within_300s_rate")),
                "creator_sold_within_60s_rate":
                    _rate(x.get("creator_sold_within_60s_share")),
            }
            for x in st.get("trend", {}).get("weekly", [])
        ],
        "trend": {
            # 相对增长换成比率（0.741 = +74.1%）；pp = 百分点，是另一种量纲，保留
            "launches_growth": (
                round(_num(st.get("trend", {}).get("change", {}).get("launches_pct")) / 100.0, 6)
                if _num(st.get("trend", {}).get("change", {}).get("launches_pct")) is not None
                else None),
            "graduation_rate_pp":
                _num(st.get("trend", {}).get("change", {}).get("graduation_rate_pp")),
            "organic_graduation_rate_pp":
                _num(st.get("trend", {}).get("change", {}).get("organic_graduation_rate_pp")),
            "instant_share_pp":
                _num(st.get("trend", {}).get("change", {}).get("instant_share_pp")),
        },
        "label_check": {
            "recall": _rate(st["label_check"]["recall"]),
            "precision": _rate(st["label_check"]["precision"]),
            "n": _num(st["label_check"]["classic_sol_launches"]),
        },
        "pools": {
            "full_pools": _num(st.get("pools", {}).get("full_pools")),
            "share_lost_90pct_in_30m":
                _rate(st.get("pools", {}).get("share_lost_90pct_in_30m")),
            "median_seconds_to_collapse":
                _num(st.get("pools", {}).get("median_s_to_collapse")),
        },
        "caveats": CAVEATS,
    }


def analysis_creators(facts: dict) -> dict:
    hf = facts["hf"]
    conc = hf["creator_concentration"]["launches"]
    vet = hf["veteran"]
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": facts["stats"].get("generated_at"),
        "concentration": {
            "creators": _num(conc.get("creators")),
            "launches": _num(conc.get("launches")),
            "per_creator_mean": _round(conc.get("per_creator_mean"), 2),
            "top1": _num(conc.get("top1")),
            "top1_share": _pct_to_rate(conc.get("top1_share_pct")),
            "top10_share": _pct_to_rate(conc.get("top10_share_pct")),
            "top100_share": _pct_to_rate(conc.get("top100_share_pct")),
            "top1000_share": _pct_to_rate(conc.get("top1000_share_pct")),
            "creators_for_half": _num(conc.get("creators_for_half")),
            "creators_for_half_share": (
                _rate(conc["creators_for_half"] / conc["creators"])
                if conc.get("creators") else None),
        },
        # 上游是按 "0"/"1"/"2-4"/"5-19"/"20+" 做 key 的 dict，
        # 契约里改成列表 —— 顺序是语义的一部分，dict 在 JSON 里不保证顺序。
        "veteran_by_prior_launches": [
            {
                "bucket": k,
                "n": _num(v.get("n")),
                "graduation_rate": _pct_to_rate(v.get("graduation_rate_pct")),
                "rug_rate": _pct_to_rate(v.get("rug_rate_pct")),
                "mean_prior_rugs": _round(v.get("mean_prior_rugs"), 3),
                "mean_dev_share": _pct_to_rate(v.get("mean_dev_share_pct")),
                "mean_bundle_wallets": _round(v.get("mean_bundle_wallets"), 2),
            }
            for k, v in (vet.get("by_prior_launches") or {}).items()
        ],
        "veteran_sample": {
            "rows": _num(vet.get("rep_rows")),
            "tape_replay_rows": _num(vet.get("tape_replay_rows")),
            "tape_replay_missing_rate": _pct_to_rate(vet.get("tape_replay_missing_f10_pct")),
        },
        "bundling": {
            "n": _num(hf["bundling"].get("n")),
            "percentiles": {k: _num(hf["bundling"].get(k))
                            for k in ("p50", "p75", "p90", "p95", "p99")},
            "share_zero": _pct_to_rate(hf["bundling"].get("share_zero_pct")),
            "share_ge5": _pct_to_rate(hf["bundling"].get("share_ge5_pct")),
            "share_ge10": _pct_to_rate(hf["bundling"].get("share_ge10_pct")),
        },
        "dev_share_distribution": {
            "n": _num(hf["dev_share"].get("n")),
            "percentiles": {k: _rate(hf["dev_share"].get(k))
                            for k in ("p50", "p75", "p90", "p95", "p99")},
        },
        "peak_rs": {
            "n": _num(hf["peak_rs"]["launches"].get("n")),
            "percentiles": {k: _num(hf["peak_rs"]["launches"].get(k))
                            for k in ("p25", "p50", "p75", "p90", "p95", "p99")},
        },
        "tickers": {
            "unique": _num(hf["tickers"].get("unique")),
            "launches": _num(hf["tickers"].get("launches")),
            "mean_per_ticker": _round(hf["tickers"].get("mean_per_ticker"), 2),
            "top": [
                {
                    "ticker": t.get("ticker"),
                    "n": _num(t.get("n")),
                    "graduated": _num(t.get("graduated")),
                    "rug_rate": _pct_to_rate(t.get("rug_rate_pct")),
                }
                for t in hf["tickers"].get("top", [])
            ],
        },
    }


def analysis_economics(facts: dict) -> dict:
    dl = facts["defillama"]
    lp, ps, cmb = dl["launchpad"], dl["pumpswap"], dl["combined_30d"]
    rv = facts["revenue"]

    def block(x: dict) -> dict:
        vol = _num(x["volume"].get("total30d"))
        fee = _num(x["fees"].get("total30d"))
        rev = _num(x["revenue"].get("total30d"))
        return {
            "volume_usd": vol,
            "fees_usd": fee,
            "revenue_usd": rev,
            "revenue_rate": round(rev / vol, 6) if vol and rev is not None else None,
        }

    lp_b, ps_b, cmb_b = block(lp), block(ps), block(
        {"volume": {"total30d": cmb.get("volume")},
         "fees": {"total30d": cmb.get("fees")},
         "revenue": {"total30d": cmb.get("revenue")}})
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": facts["stats"].get("generated_at"),
        "structure": {"launchpad": lp_b, "pumpswap": ps_b, "combined": cmb_b},
        "mix": {
            "pumpswap_volume_share": (
                round(ps_b["volume_usd"] / cmb_b["volume_usd"], 6)
                if cmb_b["volume_usd"] else None),
            "pumpswap_revenue_share": (
                round(ps_b["revenue_usd"] / cmb_b["revenue_usd"], 6)
                if cmb_b["revenue_usd"] else None),
        },
        "fee_floor": {
            # 下界只含曲线净流入；用途是校验量级，不是估计值
            "window_days": _num(rv.get("days_covered")),
            "sum_peak_rs_sol": _num(rv.get("peak_rs_sum_sol_total")),
            "sol_usd": _num(rv.get("sol_usd")),
            "sol_usd_source": rv.get("sol_usd_source"),
            "volume_floor_usd": _num(rv.get("volume_floor_usd")),
            "fee_floor_gross_usd": _num(rv.get("fee_floor_gross_usd")),
            "fee_floor_protocol_usd": _num(rv.get("fee_floor_protocol_usd")),
            "note": rv.get("note"),
        },
        "caveats": [c for c in CAVEATS if c["key"] in ("floor", "dl", "window")],
    }


# ------------------------------------------------------------------ audit
_FEE_LINES = ("protocol_fee", "creator_fee", "buyback_fee",
              "lp_fee", "cashback", "holder_rewards")


def _fee_block(row: dict, suffix: str = "") -> dict:
    out = {k: _round(row.get(k + suffix), 2) for k in _FEE_LINES}
    out["total"] = _round(row.get("total" + suffix), 2)
    return out


def audit_summary(report: dict) -> dict:
    """六条费用线 × 双口径。

    双口径分在 `all` / `liq` 两个子对象里（不是并排字段）：
    `all` 含长尾报价资产，会被单一低流动性资产放大两个数量级 —— 实测
    2026-10-15 的 holder_rewards 全价口径是 23.5 亿 USD，而流动性达标口径同一天
    也是同一量级（说明那天确实有一个极端的报价资产）。**不能拿 `all` 当收入。**
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": report.get("as_of"),
        "sol_usd": _num(report.get("sol_usd")),
        "lines": list(_FEE_LINES),
        "health": {
            "events": _num(report.get("health", {}).get("events")),
            "first_ts": _num(report.get("health", {}).get("first_ts")),
            "last_ts": _num(report.get("health", {}).get("last_ts")),
            "last_age_s": _num(report.get("health", {}).get("last_age_s")),
            "last_10min_events": _num(report.get("health", {}).get("last_10min_events")),
        },
        "pricing_quality": {
            "mints_total": _num(report.get("total_mints")),
            "mints_chosen": _num(report.get("priced_mints")),
            "priced": _num(report.get("pricing_quality", {}).get("priced")),
            "major_quote": _num(report.get("pricing_quality", {}).get("major_quote")),
            "high_dispersion":
                _num(report.get("pricing_quality", {}).get("high_dispersion")),
            "min_liquidity_usd": _num(report.get("min_liquidity")),
        },
        "daily": [
            {
                "day": day,
                "all": _fee_block(row),
                "liq": _fee_block(row, "_liq"),
                "n_events": _num(row.get("n")),
                "unpriced_mints": _num(row.get("unpriced_mints")),
                "illiquid_mints": _num(row.get("illiquid_mints")),
            }
            for day, row in (report.get("daily") or {}).items()
        ],
        "hourly": [
            {"hour": r.get("hour"), "all": _fee_block(r), "liq": _fee_block(r, "_liq")}
            for r in report.get("hourly", [])
        ],
        "top_mints": [{"mint": m.get("mint"), "usd": _round(m.get("usd"), 2)}
                      for m in report.get("top_mints", [])],
        "defillama": report.get("defillama") or {},
        "official": report.get("official") or {},
        "caveats": [c for c in CAVEATS if c["key"] in ("dl",)],
    }


def _usd_m(v: Any) -> float | None:
    """上游的百万单位字段（`fees_30d` = 175.82 意思是 $175.82M）→ 绝对 USD。"""
    x = _num(v)
    return None if x is None else round(x * 1e6, 2)


def _usd_b(v: Any) -> float | None:
    """上游的十亿单位字段（`volume_30d_b` = 15.17）→ 绝对 USD。"""
    x = _num(v)
    return None if x is None else round(x * 1e9, 2)


def _num_text(v: Any) -> float | None:
    """上游有些字段是字符串形式的数字（抓取页面的产物）。"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _dl_block(x: dict) -> dict:
    """DefiLlama 三块的单位是混着来的：费用/收入是**百万**、交易量是**十亿**。

    契约里一律换成绝对 USD —— 否则前端每个字段都要自己记住量纲，
    而“把 $175.82M 当成 $175.82”是一个只需一次疏忽就会写进报告的错。
    """
    return {
        "fees_usd": _usd_m(x.get("fees_30d")),
        "revenue_usd": _usd_m(x.get("revenue_30d")),
        "volume_usd": _usd_b(x.get("volume_30d_b")),
        "take_rate": _pct_to_rate(x.get("take_rate_pct")),
    }


def _turnover_block(x: dict) -> dict:
    return {
        "from": x.get("from"),
        "to": x.get("to"),
        "days": _num(x.get("days")),
        "median_turnover_x": _round(x.get("median_x"), 2),
    }


def audit_reconciliation(facts: dict) -> dict:
    bu = facts.get("bottom_up", {})
    dl = facts.get("defillama") or {}
    ds = facts.get("dataset") or {}
    fp = facts.get("fees_page") or {}
    tv = facts.get("turnover") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": facts.get("loopholetape", {}).get("generated_at"),
        "as_of": facts.get("as_of"),
        "sol_usd": _num(facts.get("sol_usd")),
        "defillama": {
            "combined": {
                **_dl_block(dl.get("combined") or {}),
                "fees_7d_usd": _usd_m((dl.get("combined") or {}).get("fees_7d")),
                "revenue_7d_usd": _usd_m((dl.get("combined") or {}).get("revenue_7d")),
                "revenue_24h_usd": _usd_m((dl.get("combined") or {}).get("revenue_24h")),
                "revenue_1y_usd": _usd_m((dl.get("combined") or {}).get("revenue_1y")),
                "revenue_per_day_usd": _usd_m(
                    (dl.get("combined") or {}).get("revenue_per_day_30d_m")),
            },
            "curve": _dl_block(dl.get("curve") or {}),
            "pumpswap": _dl_block(dl.get("pumpswap") or {}),
            "combined_take_rate": _pct_to_rate(dl.get("take_rate_all_pct")),
        },
        "bottom_up": {
            "window": bu.get("window"),
            "sum_peak_rs_sol": _num(bu.get("peak_rs_classic_sum")),
            "fee_floor_gross_usd": _num(bu.get("fee_floor_gross_usd")),
            "fee_floor_protocol_usd": _num(bu.get("fee_floor_protocol_usd")),
            "dl_curve_fees_same_days_usd": _num(bu.get("dl_curve_fees_same_days")),
            "floor_vs_dl_fees_rate": _pct_to_rate(bu.get("floor_vs_dl_fees_pct")),
        },
        "turnover": {
            "definition": tv.get("definition"),
            "note": tv.get("note"),
            "pre_cut": _turnover_block(tv.get("pre_cut") or {}),
            "post_cut": _turnover_block(tv.get("post_cut") or {}),
        },
        "dataset": {
            "rows": _num(ds.get("rows")),
            "days": _num(ds.get("days")),
            "from": ds.get("from"),
            "to": ds.get("to"),
            "legacy_rows": _num(ds.get("legacy_rows")),
            "launches_rows": _num(ds.get("launches_rows")),
            "quote_assets": ds.get("quote_assets") or {},
            "custom_share": _pct_to_rate(ds.get("custom_share_pct")),
        },
        "official": {
            "scraped_at": fp.get("scraped_at"),
            "data_as_of": fp.get("data_as_of"),
            "annualized_revenue_usd": _usd_m(_num_text(fp.get("annualized_revenue_text"))),
            "daily_revenue_avg_usd": _usd_m(_num_text(fp.get("daily_avg_text"))),
            "bought_back_usd": _usd_m(_num_text(fp.get("bought_back_text"))),
            "burned_pump_usd": _usd_m(_num_text(fp.get("burned_pump_text"))),
            "daily_buyback_usd": _usd_m(_num_text(fp.get("daily_buyback_text"))),
            # 单位为千（与 stream_report 的 official.active_wallets_k 一致）
            "active_wallets_thousands": _num_text(fp.get("active_wallets_text")),
            "implied_daily_from_annualized_usd": _usd_m(
                fp.get("implied_daily_from_annualized_m")),
            "implied_daily_from_buyback_usd": _usd_m(
                fp.get("implied_daily_from_buyback_m")),
            "disclaimer": bool(fp.get("disclaimer")),
        },
        "caveats": CAVEATS,
    }


# ------------------------------------------------------------------ pulse
def pulse_feed(data: dict) -> dict:
    """pulse 的 data.json 已经是本项目自己的服务格式（`builder.py` 产出），
    所以这里只做轻微整理，不重命名 —— 重命名会让两份代码（站点与 SPA）各说一套话。
    """
    k = data.get("kpis") or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": data.get("generated_at"),
        "source_generated_at": data.get("source_generated_at"),
        "kpis": {
            "launches": _num(k.get("launches")),
            "graduations": _num(k.get("graduations")),
            "graduation_rate": _rate(k.get("graduation_rate")),
            "instant_bundles": _num(k.get("instant_bundles")),
            "instant_share": _rate(k.get("instant_share")),
            "organic_rate": _rate(k.get("organic_rate")),
            "pool_death_share": _rate(k.get("pool_death_share")),
            "median_collapse_s": _num(k.get("median_collapse_s")),
            "organic_median_s": _num(k.get("organic_median_s")),
            "window_from": k.get("window_from"),
            "window_to": k.get("window_to"),
        },
        "live": data.get("live") or {},
        "stories": data.get("stories") or [],
        "tape": data.get("tape") or [],
    }
