#!/usr/bin/env python3
"""把 stream_report.json 渲染成静态 HTML 报表页（服务器托管）。

内容：健康状态 / KPI / 小时级图 / 全价与流动性两张明细表 / Top 资产 / DefiLlama 对照。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import xml.sax.saxutils as sax

ROOT = pathlib.Path(__file__).resolve().parent
LINES = [("protocol_fee", "协议费"), ("creator_fee", "创作者"),
         ("buyback_fee", "回购"), ("lp_fee", "LP"),
         ("cashback", "返现"), ("holder_rewards", "持币奖励")]


def esc(s) -> str:
    return sax.escape(str(s))


def bars(items: list[tuple[str, float]], label_fmt, fmt, color="#38bdf8",
         width: int = 1160, height: int = 260) -> str:
    if not items:
        return "<p class='muted'>暂无数据</p>"
    pad_l, pad_r, pad_t, pad_b = 70, 16, 26, 42
    mx = max(v for _, v in items) or 1
    bw = (width - pad_l - pad_r) / len(items)
    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="ui-monospace,Menlo,monospace">']
    for frac in (0, .5, 1):
        y = height - pad_b - frac * (height - pad_t - pad_b)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                   f'stroke="#1c2432" stroke-dasharray="3 3"/>'
                   f'<text x="{pad_l-8}" y="{y+4:.1f}" fill="#5d6a7a" font-size="11" '
                   f'text-anchor="end">{esc(fmt(mx*frac))}</text>')
    for i, (label, v) in enumerate(items):
        h = (v / mx) * (height - pad_t - pad_b)
        x = pad_l + i * bw + bw * 0.15
        y = height - pad_b - h
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.7:.1f}" '
                   f'height="{h:.1f}" fill="{color}" opacity=".85"/>')
        if len(items) <= 30 or i % max(1, len(items)//24) == 0:
            out.append(f'<text x="{x+bw*0.35:.1f}" y="{height-pad_b+15:.1f}" '
                       f'fill="#5d6a7a" font-size="10" text-anchor="middle">'
                       f'{esc(label_fmt(label))}</text>')
    out.append("</svg>")
    return "".join(out)


def table(days: list[str], daily: dict, caliber: str) -> str:
    suffix = "" if caliber == "all" else "_liq"
    head = "".join(f"<th class='r'>{n}</th>" for _, n in LINES)
    rows = []
    for d in days:
        v = daily[d]
        cells = "".join(f"<td class='r'>${v.get(k + suffix, 0):,.0f}</td>" for k, _ in LINES)
        rows.append(f"<tr><td>{esc(d)}</td><td class='r'>{v.get('n',0):,}</td>{cells}"
                    f"<td class='r hl'>${v.get('total'+suffix, 0):,.0f}</td>"
                    f"<td class='r'>{v.get('unpriced_mints',0)}/{v.get('illiquid_mints',0)}</td></tr>")
    return (f"<table><tr><th>日期</th><th class='r'>事件</th>{head}"
            f"<th class='r'>合计</th><th class='r'>未定价/低流动</th></tr>" + "".join(rows) + "</table>")


def build(report_path: pathlib.Path, out_path: pathlib.Path) -> None:
    R = json.loads(report_path.read_text())
    daily, hourly = R.get("daily", {}), R.get("hourly", [])
    days = sorted(daily)
    total_liq = sum(daily[d].get("total_liq", 0) for d in days)
    total_all = sum(daily[d].get("total", 0) for d in days)
    last = daily[days[-1]] if days else {}
    h = R.get("health", {})
    age = h.get("last_age_s")
    age_txt = "刚刚" if age is not None and age < 120 else (
        f"{age/60:.0f} 分钟前" if age is not None else "—")
    ok = age is not None and age < 900
    dot = "#22c55e" if ok else "#f59e0b"

    chart = bars([(x["hour"], x.get("total_liq", 0)) for x in hourly[-72:]],
                 lambda s: s[11:16], lambda v: f"${v/1000:.0f}k" if v >= 1000 else f"${v:.0f}")
    all_table = table(days, daily, "all")
    liq_table = table(days, daily, "liq")

    top_rows = "".join(
        f"<tr><td class='mono'>{esc(t['mint'])}</td><td class='r'>${t['usd']:,.0f}</td></tr>"
        for t in R.get("top_mints", []))
    fee_events = R.get("fee_events") or {}
    fee_html = ""
    if fee_events:
        fee_html = ("<h2>其他收入线活动（fee 程序事件，计数）</h2><table><tr><th>事件</th>"
                    "<th class='r'>次数</th></tr>"
                    + "".join(f"<tr><td>{esc(k)}</td><td class='r'>{v:,}</td></tr>"
                              for k, v in fee_events.items())
                    + "</table><p class='note'>social / donation / buyback sweep 等事件"
                      "在公开 IDL 里没有金额字段，暂时只能计活动量，无法折算 USD。</p>")

    off = R.get("official") or {}
    off_html = ""
    if off.get("annualized_revenue_m") is not None:
        last_day = days[-1] if days else None
        ld = daily.get(last_day, {}) if last_day else {}
        ours_rev = ld.get("protocol_fee_liq", 0) + ld.get("buyback_fee_liq", 0)
        ours_buy = ld.get("buyback_fee_liq", 0)
        off_html = ("<h2>官方看板对照（fees.pump.fun）</h2><table>"
                    "<tr><th></th><th class='r'>官方</th><th class='r'>我们（流动性口径）</th></tr>"
                    f"<tr><td>收入（日均 / 最新日）</td>"
                    f"<td class='r'>${off.get('daily_avg_m', 0)}M / 天</td>"
                    f"<td class='r'>${ours_rev:,.0f}（{esc(last_day)}，未满一天）</td></tr>"
                    f"<tr><td>回购（最新日）</td>"
                    f"<td class='r'>${off.get('daily_buyback_k', 0)}K</td>"
                    f"<td class='r'>${ours_buy:,.0f}</td></tr>"
                    f"<tr><td>年化收入 / 累计回购 / 已销毁</td>"
                    f"<td class='r'>${off.get('annualized_revenue_m', 0)}M / "
                    f"${off.get('bought_back_m', 0)}M / {off.get('burned_pump_b', 0)}B $PUMP</td>"
                    f"<td class='r'>—</td></tr></table>"
                    f"<p class='note'>官方口径为协议留存（数据截至 {esc(off.get('data_as_of'))}）；"
                    + ("官方自述：custom pairs 后看板不准确。"
                       if off.get("disclaimer") else "")
                    + "我们的数字是六条线的流动性达标口径，两者定义不同，仅作量级对照。</p>")

    dl = R.get("defillama") or {}
    dl_html = ""
    if dl:
        dl_html = ("<h2>DefiLlama 对照（协议留存口径）</h2><table><tr><th>协议</th>"
                   "<th class='r'>24h</th><th class='r'>7d</th><th class='r'>30d</th></tr>"
                   + "".join(f"<tr><td>{esc(k)}</td>"
                             f"<td class='r'>${v.get('total24h',0)/1e6:,.2f}M</td>"
                             f"<td class='r'>${v.get('total7d',0)/1e6:,.2f}M</td>"
                             f"<td class='r'>${v.get('total30d',0)/1e6:,.2f}M</td></tr>"
                             for k, v in dl.items()) + "</table>")

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pump.fun 链上收入 · 实时报表</title>
<style>
 body{{margin:0;background:#07090d;color:#e8edf4;font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.6}}
 .wrap{{max-width:1240px;margin:0 auto;padding:26px 22px 60px}}
 h1{{font-size:19px;letter-spacing:2px}} h2{{font-size:13px;letter-spacing:3px;margin:30px 0 10px;color:#9aa6b6}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}}
 .kpi{{background:#0e131b;border:1px solid #1b2431;border-radius:10px;padding:14px 16px}}
 .kpi .k{{color:#5d6a7a;font-size:11px;letter-spacing:1.5px}} .kpi .v{{font-size:22px;font-weight:800;margin-top:4px}}
 .kpi .h{{color:#5d6a7a;font-size:11px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;margin-top:8px}}
 th,td{{padding:8px 9px;border-bottom:1px solid #1b2431;text-align:left;vertical-align:top}}
 th{{color:#5d6a7a;font-weight:400;font-size:11px;letter-spacing:1.2px;text-transform:uppercase}}
 .r{{text-align:right}} .hl{{color:#38bdf8;font-weight:700}} .mono{{font-size:12px}}
 .muted{{color:#5d6a7a}} .note{{color:#5d6a7a;font-size:12px;margin-top:14px}}
 svg{{width:100%;height:auto;background:#0b0e13;border:1px solid #1b2431;border-radius:10px}}
 .dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
 a{{color:#38bdf8}}
</style></head><body><div class="wrap">
<h1>pump.fun 链上一手收入 <span style="color:#5d6a7a;font-size:13px">public data · on-chain stream</span></h1>
<p class="muted"><span class="dot" style="background:{dot}"></span>
采集器最新事件 {esc(age_txt)} · 近 10 分钟 {h.get('last_10min_events', 0):,} 条 ·
累计 {h.get('events', 0):,} 条 · 页面生成 {esc(R.get('as_of'))} · SOL ${R.get('sol_usd', 0):.2f} ·
<a href="stream_report.csv">下载 CSV</a></p>

<div class="kpis">
 <div class="kpi"><div class="k">流动性达标（累计）</div><div class="v">${total_liq:,.0f}</div>
   <div class="h">quote 资产流动性 ≥ ${R.get('min_liquidity', 50000):,.0f}</div></div>
 <div class="kpi"><div class="k">全价口径（累计）</div><div class="v">${total_all:,.0f}</div>
   <div class="h">含长尾资产报价，可能失真</div></div>
 <div class="kpi"><div class="k">最新一天（达标）</div><div class="v">${last.get('total_liq', 0):,.0f}</div>
   <div class="h">{esc(days[-1]) if days else '—'} · {last.get('n', 0):,} 事件</div></div>
 <div class="kpi"><div class="k">最新一天（全价）</div><div class="v">${last.get('total', 0):,.0f}</div>
   <div class="h">六条线合计</div></div>
</div>

<h2>小时级收入（流动性达标口径，最近 72 小时）</h2>
{chart}

<h2>明细 · 全价口径（USD）</h2>
{all_table}
<p class="note">「未定价/低流动」列显示 未定价 mint 数 / 低流动性 mint 数。全价口径用于观察资金构成，不宜直接当收入。</p>

<h2>明细 · 流动性达标口径（USD）</h2>
{liq_table}
<p class="note">只统计最优交易对流动性 ≥ ${R.get('min_liquidity', 50000):,.0f} 的 quote 资产。
原生 SOL/WSOL 用 CoinGecko，USDC=1，其余用 DexScreener（top5 交易对按流动性加权中位数；
偏好 SOL/USDC/USDT 计价对）。定价质量：{esc((R.get('pricing_quality') or {}).get('priced'))}/
{esc((R.get('pricing_quality') or {}).get('chosen'))} 可定价，
{esc((R.get('pricing_quality') or {}).get('major_quote'))} 来自主流计价对，
{esc((R.get('pricing_quality') or {}).get('high_dispersion'))} 个离散&gt;3×。</p>

<h2>Top quote 资产（按 USD，全价口径）</h2>
<table><tr><th>mint</th><th class="r">金额</th></tr>{top_rows}</table>

{dl_html}
{off_html}
{fee_html}
<p class="note">这是独立复算，不是 pump.fun 官方数据，也不构成投资建议。</p>
</div></body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"写了 {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(ROOT / "stream_report.json"))
    ap.add_argument("--out", default=str(ROOT / "site" / "index.html"))
    args = ap.parse_args()
    build(pathlib.Path(args.report), pathlib.Path(args.out))


if __name__ == "__main__":
    main()
