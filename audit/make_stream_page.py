#!/usr/bin/env python3
"""把 stream_report.json 渲染成一个静态 HTML 报表页（服务器 nginx 托管）。

只读、无 JS 依赖、暗色主题。含：
  - 口径说明（全价 vs 流动性达标）
  - 每日六条费用线表 + 柱状图
  - Top quote 资产
  - 与 DefiLlama 的对比（若 stream_report.py --compare 有数据）
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


def bars(items: list[tuple[str, float]], color: str, fmt) -> str:
    if not items:
        return "<p class='muted'>暂无数据</p>"
    w, h, pad = 1100, 240, 40
    mx = max(v for _, v in items) or 1
    bw = (w - pad * 2) / len(items)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="ui-monospace,Menlo,monospace">']
    for i, (label, v) in enumerate(items):
        bh = (v / mx) * (h - pad * 2)
        x = pad + i * bw + bw * 0.15
        y = h - pad - bh
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.7:.1f}" '
                   f'height="{bh:.1f}" fill="{color}" opacity=".85"/>')
        out.append(f'<text x="{x + bw*0.35:.1f}" y="{y-6:.1f}" fill="#9aa6b6" '
                   f'font-size="11" text-anchor="middle">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bw*0.35:.1f}" y="{h-pad+16:.1f}" fill="#5d6a7a" '
                   f'font-size="10" text-anchor="middle">{esc(label[5:])}</text>')
    out.append("</svg>")
    return "".join(out)


def build(report_path: pathlib.Path, out_path: pathlib.Path) -> None:
    R = json.loads(report_path.read_text())
    daily = R.get("daily", {})
    days = sorted(daily)
    total_liq = sum(d.get("total_liq", 0) for d in daily.values())
    total_all = sum(d.get("total", 0) for d in daily.values())
    last = daily[days[-1]] if days else {}
    chart = bars([(d, daily[d].get("total_liq", 0)) for d in days], "#38bdf8",
                 lambda v: f"${v/1000:.0f}k" if v >= 1000 else f"${v:.0f}")
    rows = "".join(
        "<tr>"
        f"<td>{esc(d)}</td><td class='r'>{daily[d].get('n', 0):,}</td>"
        + "".join(f"<td class='r'>${daily[d].get(k, 0):,.0f}</td>" for k, _ in LINES)
        + f"<td class='r'>${daily[d].get('total', 0):,.0f}</td>"
        f"<td class='r hl'>${daily[d].get('total_liq', 0):,.0f}</td>"
        f"<td class='r'>{daily[d].get('unpriced_mints', 0)}/{daily[d].get('illiquid_mints', 0)}</td>"
        "</tr>" for d in days)
    top_rows = "".join(
        f"<tr><td class='mono'>{esc(t['mint'])}</td><td class='r'>${t['usd']:,.0f}</td></tr>"
        for t in R.get("top_mints", []))
    dl = R.get("defillama") or {}
    dl_html = ""
    if dl:
        dl_html = "<h2>DefiLlama 对照（协议留存口径）</h2><table><tr><th>协议</th>" \
                  "<th class='r'>24h</th><th class='r'>7d</th><th class='r'>30d</th></tr>" + \
                  "".join(f"<tr><td>{esc(k)}</td>"
                          f"<td class='r'>${v.get('total24h',0)/1e6:,.2f}M</td>"
                          f"<td class='r'>${v.get('total7d',0)/1e6:,.2f}M</td>"
                          f"<td class='r'>${v.get('total30d',0)/1e6:,.2f}M</td></tr>"
                          for k, v in dl.items()) + "</table>"

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pump.fun 链上收入 · 实时报表</title>
<style>
 body{{margin:0;background:#07090d;color:#e8edf4;font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.6}}
 .wrap{{max-width:1200px;margin:0 auto;padding:26px 22px 60px}}
 h1{{font-size:19px;letter-spacing:2px}} h2{{font-size:13px;letter-spacing:3px;margin:30px 0 10px;color:#9aa6b6}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}}
 .kpi{{background:#0e131b;border:1px solid #1b2431;border-radius:10px;padding:14px 16px}}
 .kpi .k{{color:#5d6a7a;font-size:11px;letter-spacing:1.5px}} .kpi .v{{font-size:22px;font-weight:800;margin-top:4px}}
 .kpi .h{{color:#5d6a7a;font-size:11px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;margin-top:8px}}
 th,td{{padding:8px 9px;border-bottom:1px solid #1b2431;text-align:left;vertical-align:top}}
 th{{color:#5d6a7a;font-weight:400;font-size:11px;letter-spacing:1.2px;text-transform:uppercase}}
 .r{{text-align:right}} .hl{{color:#38bdf8;font-weight:700}} .mono{{font-size:12px}}
 .muted{{color:#5d6a7a}} .note{{color:#5d6a7a;font-size:12px;margin-top:18px}}
 svg{{width:100%;height:auto;background:#0b0e13;border:1px solid #1b2431;border-radius:10px}}
</style></head><body><div class="wrap">
<h1>pump.fun 链上一手收入 <span style="color:#5d6a7a;font-size:13px">
 public data · on-chain stream</span></h1>
<p class="muted">生成于 {esc(R.get('as_of'))} · 数据来自 VPS 上的 logsSubscribe 采集
（pump curve + pump AMM 事件）· SOL 参考价 ${R.get('sol_usd', 0):.2f}</p>

<div class="kpis">
 <div class="kpi"><div class="k">流动性达标口径（累计）</div><div class="v">${total_liq:,.0f}</div>
   <div class="h">quote 资产流动性 ≥ \$50k</div></div>
 <div class="kpi"><div class="k">全价口径（累计）</div><div class="v">${total_all:,.0f}</div>
   <div class="h">含长尾资产报价，可能失真</div></div>
 <div class="kpi"><div class="k">最新一天</div><div class="v">${last.get('total_liq', 0):,.0f}</div>
   <div class="h">{esc(days[-1]) if days else '—'} · {last.get('n', 0):,} 事件</div></div>
 <div class="kpi"><div class="k">六条线合计（全价）</div>
   <div class="v">{sum(last.get(k, 0) for k, _ in LINES):,.0f}</div>
   <div class="h">USD，最近一天</div></div>
</div>

<h2>每日收入（流动性达标口径）</h2>
{chart}

<h2>明细（USD）</h2>
<table><tr><th>日期</th><th class="r">事件</th>
{''.join(f'<th class="r">{n}</th>' for _, n in LINES)}
<th class="r">全价合计</th><th class="r">流动性合计</th><th class="r">未定价/低流动</th></tr>
{rows}</table>
<p class="note">口径说明：每条线按 quote 资产定价（原生 SOL/WSOL 用 CoinGecko，USDC=1，
其余用 DexScreener）。「流动性达标」只统计最优交易对流动性 ≥ $50k 的资产——
长尾资产报价可把全价口径放大一个数量级，两个数一起看才有意义。</p>

<h2>Top quote 资产（按 USD，全价口径）</h2>
<table><tr><th>mint</th><th class="r">金额</th></tr>{top_rows}</table>

{dl_html}
<p class="note">这是独立复算，不是 pump.fun 官方数据，也不构成投资建议。
协议费/回购/创作者/LP/返现/持币奖励六条线来自链上事件原始字段。</p>
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
