"""契约测试。

这些测试保护的不是"代码能跑"，而是**契约的三个承诺**（见 normalize.py 的 docstring）：

1. 比率一律 0~1 的小数，且不出现 `*_pct` 字段
2. 每个响应都带 `generated_at`
3. audit 的双口径在结构上分开（`all` / `liq`），不可能被混用

analysis 的测试用**仓库里真实的 facts.json**（它是签入的），audit/pulse 因为
是运行期产物，用结构化 fixture。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import main, normalize
from app.config import REPO, settings

client = TestClient(main.app)


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def audit_report(tmp_path, monkeypatch):
    """按服务器上 stream_report.json 的真实结构造一份。"""
    report = {
        "as_of": "2026-10-16T15:08:05Z",
        "sol_usd": 105.55,
        "min_liquidity": 50000,
        "health": {"events": 100, "first_ts": 1, "last_ts": 2,
                   "last_age_s": 9, "last_10min_events": 5},
        "priced_mints": 600, "total_mints": 6257,
        "pricing_quality": {"chosen": 600, "priced": 285,
                            "major_quote": 285, "high_dispersion": 54},
        "daily": {
            "2026-10-15": {
                "protocol_fee": 1.0, "creator_fee": 2.0, "buyback_fee": 3.0,
                "lp_fee": 4.0, "cashback": 5.0, "holder_rewards": 6.0,
                "protocol_fee_liq": 0.1, "creator_fee_liq": 0.2,
                "buyback_fee_liq": 0.3, "lp_fee_liq": 0.4,
                "cashback_liq": 0.5, "holder_rewards_liq": 0.6,
                "total": 21.0, "total_liq": 2.1, "n": 10,
                "unpriced_mints": 1, "illiquid_mints": 2,
            }
        },
        "hourly": [],
        "top_mints": [{"mint": "x", "usd": 1.5}],
        "defillama": {}, "official": {},
    }
    p = tmp_path / "stream_report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(settings, "audit_report", p)
    return report


@pytest.fixture
def pulse_data(tmp_path, monkeypatch):
    p = tmp_path / "data.json"
    p.write_text(json.dumps({
        "generated_at": "2026-10-16T15:00:00Z",
        "source_generated_at": "2026-10-16T14:59:00Z",
        "kpis": {"launches": 100, "graduations": 2, "graduation_rate": 0.02,
                 "instant_bundles": 1, "instant_share": 0.5,
                 "organic_rate": 0.01, "pool_death_share": 0.6,
                 "median_collapse_s": 500.0, "organic_median_s": 480.0,
                 "window_from": "a", "window_to": "b"},
        "live": {"graduation": [], "rug": []},
        "stories": [], "tape": [],
    }), encoding="utf-8")
    monkeypatch.setattr(settings, "pulse_data", p)
    return p


# ------------------------------------------------------------------ 契约不变量
def _walk(obj, path="$"):
    """遍历所有 (路径, 键, 值)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def assert_contract_invariants(payload: dict, *, name: str) -> None:
    # 1) 不出现 * _pct 字段（量纲统一为 0~1）
    bad = [(p, k) for p, k, _ in _walk(payload) if k.endswith("_pct")]
    assert not bad, f"{name}: 契约里不应出现 *_pct 字段：{bad}"

    # 2) 所有 *_rate / *_share 是 0~1 或 None
    for p, k, v in _walk(payload):
        if (k.endswith("_rate") or k.endswith("_share")) and isinstance(v, (int, float)):
            assert isinstance(v, (int, float)), f"{name}: {p}.{k} 不是数字：{v!r}"
            assert 0.0 <= v <= 1.0, f"{name}: {p}.{k} 越界（应为 0~1）：{v}"

    # 3) 必须带 generated_at
    assert "generated_at" in payload, f"{name}: 缺少 generated_at"


# ------------------------------------------------------------------ analysis
def test_analysis_overview_contract():
    r = client.get("/api/v1/analysis/overview")
    assert r.status_code == 200, r.text
    d = r.json()
    assert_contract_invariants(d, name="analysis/overview")

    # 核心数字必须落地（用真实 facts.json）
    k = d["kpis"]
    assert k["launches"] == 1156058
    assert k["graduation_rate"] == pytest.approx(0.020581, abs=1e-6)
    assert k["organic_graduation_rate"] == pytest.approx(0.008647, abs=1e-6)
    # 结构性承诺：30 天日序列完整
    assert len(d["daily"]) == 30
    assert len(d["weekly"]) == 4
    # 已知缺口必须随响应下发
    assert len(d["caveats"]) >= 5


def test_analysis_creators_and_economics():
    for path in ("/api/v1/analysis/creators", "/api/v1/analysis/economics"):
        r = client.get(path)
        assert r.status_code == 200, r.text
        assert_contract_invariants(r.json(), name=path)

    creators = client.get("/api/v1/analysis/creators").json()
    # 上游是 dict（key "0"/"1"/"2-4"...），契约必须是**有序列表**
    buckets = [b["bucket"] for b in creators["veteran_by_prior_launches"]]
    assert buckets == ["0", "1", "2-4", "5-19", "20+"], buckets

    eco = client.get("/api/v1/analysis/economics").json()
    # 量在 PumpSwap、收入在曲线的倒挂，必须能算出来
    assert eco["mix"]["pumpswap_volume_share"] > 0.7
    assert eco["mix"]["pumpswap_revenue_share"] < 0.4


# ------------------------------------------------------------------ audit
def test_audit_dual_caliber_is_structurally_separated(audit_report):
    r = client.get("/api/v1/audit/summary")
    assert r.status_code == 200, r.text
    d = r.json()
    assert_contract_invariants(d, name="audit/summary")

    day = d["daily"][0]
    # 双口径是两个字对象，不是并排字段 —— 混用在类型上做不到
    assert set(day["all"]) == set(day["liq"])
    assert day["all"]["protocol_fee"] == pytest.approx(1.0)
    assert day["liq"]["protocol_fee"] == pytest.approx(0.1)
    assert day["all"]["total"] == pytest.approx(21.0)
    assert day["liq"]["total"] == pytest.approx(2.1)
    # 六条费用线齐全
    assert d["lines"] == ["protocol_fee", "creator_fee", "buyback_fee",
                          "lp_fee", "cashback", "holder_rewards"]


def test_audit_reconciliation_contract():
    r = client.get("/api/v1/audit/reconciliation")
    assert r.status_code == 200, r.text
    d = r.json()
    assert_contract_invariants(d, name="audit/reconciliation")

    # 单位陷阱回归测试：上游 `fees_30d=57.86` 是**百万**、`volume_30d_b=4.02` 是**十亿**。
    # 契约必须统一成绝对 USD —— 否则前端会把 $57.86M 当成 $57.86。
    curve = d["defillama"]["curve"]
    assert curve["fees_usd"] == pytest.approx(57.86e6, rel=1e-6), curve
    assert curve["volume_usd"] == pytest.approx(4.02e9, rel=1e-6), curve
    assert curve["take_rate"] == pytest.approx(0.01021, abs=1e-6), curve
    # 字符串形式的数字也要变成真数字
    assert d["official"]["annualized_revenue_usd"] == pytest.approx(589.19e6, rel=1e-6)
    assert d["dataset"]["custom_share"] == pytest.approx(0.0997, abs=1e-6)


# ------------------------------------------------------------------ pulse
def test_pulse_feed_contract(pulse_data):
    r = client.get("/api/v1/pulse/feed")
    assert r.status_code == 200, r.text
    d = r.json()
    assert_contract_invariants(d, name="pulse/feed")
    assert d["kpis"]["graduation_rate"] == pytest.approx(0.02)


# ------------------------------------------------------------------ 错误形状
def test_missing_upstream_gives_unified_error(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pulse_data", tmp_path / "nope.json")
    r = client.get("/api/v1/pulse/feed")
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "upstream_missing"
    assert "pulse" in body["error"]["source"]


def test_invalid_json_gives_unified_error(tmp_path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(settings, "pulse_data", p)
    r = client.get("/api/v1/pulse/feed")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_invalid"


def test_health_lists_all_four_sources(audit_report, pulse_data):
    r = client.get("/api/v1/health")
    assert r.status_code == 200, r.text
    d = r.json()
    names = {s["source"] for s in d["sources"]}
    assert names == {"analysis", "audit", "pulse", "risk"}
    # 陈旧度必须给出（analysis 是离线静态，可能很旧）
    for s in d["sources"]:
        assert "ok" in s
