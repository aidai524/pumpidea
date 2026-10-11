"""故事引擎：把链上信号翻译成可发布的内容单元。

每个故事是一个 dict，站点与卡片渲染器都消费同一份结构：
  type/kicker/title/value/label/sub/stats/link/record/accent

六类模板（全部来自免费实时源，见 sources.py）：
  instant   瞬时捆绑毕业 —— 机器人眨眼完成一次毕业
  organic   有机毕业     —— 真实成交把曲线填满
  stampede  ticker 踩踏  —— 一周内几百个同名币
  death     死亡时钟     —— 毕业后 30 分钟跌掉九成
  rugwatch  实时跑路预警 —— radar 上的高危新币
  gradwatch 实时毕业概率 —— radar 上的真实需求
"""
from __future__ import annotations

import datetime as dt
import re
import xml.sax.saxutils as sax

ACCENTS = {
    "instant": "#ff4d6d",
    "organic": "#22c55e",
    "stampede": "#a78bfa",
    "death": "#ef4444",
    "rugwatch": "#f59e0b",
    "gradwatch": "#38bdf8",
}


# ---------------------------------------------------------------- 文本工具

def clean(text: str | None, cap: int = 42) -> str:
    """创作者写的文本是不可信输入（KI-14）：去掉控制字符、压空白、截断。"""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > cap:
        s = s[: cap - 1] + "…"
    return s


def esc(text: str | None, cap: int = 42) -> str:
    return sax.escape(clean(text, cap))


def humanize_seconds(v: float | None) -> str:
    if v is None:
        return "—"
    if v < 0.0005:
        return "<1 ms"
    if v < 1:
        return f"{max(1, round(v * 1000))} ms"
    if v < 90:
        return f"{v:.2f} s".rstrip("0").rstrip(".")
    if v < 3600:
        return f"{v / 60:.1f} min"
    if v < 86400:
        return f"{v / 3600:.1f} h"
    return f"{v / 86400:.1f} d"


def clock_utc(ts: float | None) -> str:
    if not ts:
        return "—"
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H:%M:%S UTC")


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _base(story_type: str, mint: str, *, title: str, value: str, label: str,
          sub: str, stats: list[tuple[str, str]], link: str | None,
          record: str | None, ts: float | None) -> dict:
    return {
        "id": f"{story_type}-{mint[:10]}",
        "type": story_type,
        "kicker": {
            "instant": "INSTANT BUNDLE",
            "organic": "ORGANIC SURVIVOR",
            "stampede": "TICKER STAMPEDE",
            "death": "DEATH CLOCK",
            "rugwatch": "RUG ALERT · LIVE",
            "gradwatch": "ON WATCH · LIVE",
        }[story_type],
        "title": clean(title),
        "value": value,
        "label": label,
        "sub": sub,
        "stats": stats,
        "link": link or f"https://pump.fun/coin/{mint}",
        "record": record,
        "accent": ACCENTS[story_type],
        "ts": ts,
        "mint": mint,
    }


# ---------------------------------------------------------------- 六类模板

def story_instant(rows: list[dict], limit: int = 4) -> list[dict]:
    out, seen_tickers = [], set()
    cand = [r for r in rows if r.get("label") == "instant_bundle"
            and r.get("timing_seen") and r.get("seconds_to_graduation") is not None]
    cand.sort(key=lambda r: r["seconds_to_graduation"])
    for r in cand:
        t = (r.get("ticker") or "").upper()
        if t in seen_tickers:
            continue
        seen_tickers.add(t)
        secs = r["seconds_to_graduation"]
        out.append(_base(
            "instant", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=humanize_seconds(secs),
            label="from launch to migration",
            sub="Created, filled and migrated in one bundle — nobody outside it could trade.",
            stats=[
                ("Peak curve", f"{r.get('peak_curve_sol') or 0:.2f} SOL"),
                ("Same ticker / week", str(r.get("ticker_copies") or 0)),
                ("Launched", clock_utc(r.get("t0"))),
            ],
            link=(r.get("open_pumpfun")), record=r.get("record"), ts=r.get("t0")))
        if len(out) >= limit:
            break
    return out


def story_organic(rows: list[dict], limit: int = 3, min_seconds: float = 1800) -> list[dict]:
    out, seen_tickers = [], set()
    cand = [r for r in rows if r.get("label") == "organic"
            and (r.get("seconds_to_graduation") or 0) >= min_seconds]
    cand.sort(key=lambda r: -r["seconds_to_graduation"])
    for r in cand:
        t = (r.get("ticker") or "").upper()
        if t in seen_tickers:
            continue
        seen_tickers.add(t)
        out.append(_base(
            "organic", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=humanize_seconds(r["seconds_to_graduation"]),
            label="of real demand before graduation",
            sub="No bundle: the curve was filled by the open market, one buy at a time.",
            stats=[
                ("Peak curve", f"{r.get('peak_curve_sol') or 0:.2f} SOL"),
                ("Same ticker / week", str(r.get("ticker_copies") or 0)),
                ("Launched", clock_utc(r.get("t0"))),
            ],
            link=r.get("open_pumpfun"), record=r.get("record"), ts=r.get("t0")))
        if len(out) >= limit:
            break
    return out


def story_stampede(rows: list[dict], limit: int = 3, min_copies: int = 30) -> list[dict]:
    out = []
    cand = [r for r in rows if (r.get("ticker_copies") or 0) >= min_copies]
    cand.sort(key=lambda r: -r["ticker_copies"])
    for r in cand:
        out.append(_base(
            "stampede", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=str(r["ticker_copies"]),
            label="mints launched with this ticker in one week",
            sub="Copying a name at industrial scale — the ticker is a template, not a brand.",
            stats=[
                ("Time to graduate", humanize_seconds(r.get("seconds_to_graduation"))),
                ("Label", "instant bundle" if r.get("label") == "instant_bundle" else "organic"),
                ("Launched", clock_utc(r.get("t0"))),
            ],
            link=r.get("open_pumpfun"), record=r.get("record"), ts=r.get("t0")))
        if len(out) >= limit:
            break
    return out


def story_death(rows: list[dict], limit: int = 3) -> list[dict]:
    out = []
    cand = []
    for r in rows:
        po = r.get("pool_30m") or {}
        pv = po.get("price_vs_open")
        if pv is None or pv > 0.15:
            continue
        cand.append((pv, r, po))
    cand.sort(key=lambda x: x[0])
    for pv, r, po in cand[:limit]:
        drop = (1 - pv) * 100
        collapse = po.get("collapsed_after_s")
        if collapse:
            value = humanize_seconds(collapse)
            label = "from the pool opening to the −90% crash"
            sub = f"Down {drop:.0f}% at the 30-minute mark."
        else:
            value = f"-{drop:.0f}%"
            label = "within 30 minutes of the pool opening"
            sub = "Still bleeding at the 30-minute mark."
        out.append(_base(
            "death", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=value,
            label=label,
            sub=sub,
            stats=[
                ("Open reserve", f"{po.get('open_reserve_sol') or 0:.1f} SOL"),
                ("Reserve at 30m", f"{po.get('reserve_sol_at_30m') or 0:.1f} SOL"),
                ("Trades", f"{po.get('trades') or 0:,}"),
            ],
            link=r.get("open_pumpfun"), record=r.get("record"), ts=r.get("t0")))
    return out


def story_rugwatch(rows: list[dict], limit: int = 4) -> list[dict]:
    out = []
    cand = [r for r in rows if (r.get("p_rug") or 0) >= 0.4
            or "serial_rugger_creator" in (r.get("flags") or "")]
    cand.sort(key=lambda r: -(r.get("p_rug") or 0))
    for r in cand:
        flags = [f for f in (r.get("flags") or "").split(",") if f]
        sub = ("Flagged: " + ", ".join(f.replace("_", " ") for f in flags)
               if flags else "Early concentration and buy pressure look synthetic.")
        out.append(_base(
            "rugwatch", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=pct(r.get("p_rug")),
            label="live model: rug within 300 s",
            sub=sub,
            stats=[
                ("Age", humanize_seconds(r.get("age_s"))),
                ("Curve reserve", f"{r.get('rs_sol') or 0:.2f} SOL"),
                ("Buyers in 60s", str(r.get("unique_buyers_60s") or 0)),
            ],
            link=None, record=None, ts=r.get("last_seen")))
        if len(out) >= limit:
            break
    return out


def story_gradwatch(rows: list[dict], limit: int = 3) -> list[dict]:
    out = []
    cand = [r for r in rows if (r.get("p_grad") or 0) >= 0.05]
    cand.sort(key=lambda r: -(r.get("p_grad") or 0))
    for r in cand:
        out.append(_base(
            "gradwatch", r["mint"],
            title=r.get("symbol") or r.get("name") or "?",
            value=pct(r.get("p_grad")),
            label="live model: true graduation odds",
            sub=(f"{r.get('n_buys') or 0} buys · "
                 f"{r.get('unique_buyers_60s') or 0} unique buyers in the first 60 s"),
            stats=[
                ("Age", humanize_seconds(r.get("age_s"))),
                ("Curve reserve", f"{r.get('rs_sol') or 0:.2f} SOL"),
                ("Top-5 share", pct(r.get("top5_share"))),
            ],
            link=None, record=None, ts=r.get("last_seen")))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- 汇总

def build_stories(grads: list[dict], radar_grad: list[dict],
                  radar_rug: list[dict]) -> list[dict]:
    """生成内容墙：类型交错，保证第一屏好看。"""
    groups = [
        story_instant(grads, 4),
        story_rugwatch(radar_rug, 3),
        story_organic(grads, 3),
        story_stampede(grads, 3),
        story_death(grads, 3),
        story_gradwatch(radar_grad, 2),
    ]
    # 交错排列
    wall: list[dict] = []
    i = 0
    while any(i < len(g) for g in groups):
        for g in groups:
            if i < len(g):
                wall.append(g[i])
        i += 1
    # 同一 mint 只留一张
    seen, deduped = set(), []
    for s in wall:
        if s["mint"] in seen:
            continue
        seen.add(s["mint"])
        deduped.append(s)
    return deduped
