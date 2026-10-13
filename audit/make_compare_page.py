#!/usr/bin/env python3
"""用 facts.json 生成一张本地对照页：三方口径并排 + 日频差距图。

为什么需要：官方 fees.pump.fun 和 DefiLlama 都有 Cloudflare，截图/爬取不稳定；
而我们要展示的核心恰恰是"三方数字放一起看差在哪"。这里用公开数据自己画，
无外部依赖、可离线打开。
"""
from __future__ import annotations

import json
import pathlib
import xml.sax.saxutils as sax

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "site" / "index.html"
F = json.loads((ROOT / "facts.json").read_text())
D = F["daily"]

W, H, L, R, T, B = 1160, 360, 78, 24, 24, 56


def esc(s) -> str:
    return sax.escape(str(s))


def _x(i: int, n: int) -> float:
    return L + i * (W - L - R) / max(1, n - 1)


def bar_chart(values: list[float], labels: list[str], *, fmt, color: str,
              marker_idx: int | None = None, marker_text: str = "",
              y_max: float | None = None, line: list[float] | None = None,
              line_color: str = "#38bdf8", line_label: str = "") -> str:
    n = len(values)
    ymax = y_max or max(values) * 1.15 or 1
    band = (W - L - R) / n
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="ui-monospace,Menlo,monospace">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b0e13"/>')
    # grid
    for frac in (0, 0.5, 1):
        v = ymax * frac
        y = H - B - frac * (H - T - B)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}" '
                     f'stroke="#1c2432" stroke-dasharray="3 3"/>'
                     f'<text x="{L-8}" y="{y+4:.1f}" fill="#5d6a7a" font-size="12" '
                     f'text-anchor="end">{esc(fmt(v))}</text>')
    for i, v in enumerate(values):
        x = L + i * band + band * 0.2
        h = (v / ymax) * (H - T - B)
        parts.append(f'<rect x="{x:.1f}" y="{H-B-h:.1f}" width="{band*0.6:.1f}" '
                     f'height="{h:.1f}" fill="{color}" opacity="0.85"/>')
    if line:
        pts = " ".join(f"{_x(i, n):.1f},{H-B-(v/ymax)*(H-T-B):.1f}"
                       for i, v in enumerate(line))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{line_color}" '
                     f'stroke-width="2.5"/>')
    if marker_idx is not None:
        x = L + marker_idx * band + band / 2
        parts.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{H-B}" '
                     f'stroke="#f59e0b" stroke-dasharray="4 4"/>')
        parts.append(f'<text x="{x+6:.1f}" y="{T+16}" fill="#f59e0b" font-size="13">'
                     f'{esc(marker_text)}</text>')
    step = max(1, n // 12)
    for i in range(0, n, step):
        parts.append(f'<text x="{L+i*band+band/2:.1f}" y="{H-B+18}" fill="#5d6a7a" '
                     f'font-size="11" text-anchor="middle">{esc(labels[i][5:])}</text>')
    parts.append("</svg>")
    return "".join(parts)


days = [x["day"] for x in D]
dl_rev = [x["dl_curve_revenue"] or 0 for x in D]
floor = [x["fee_floor_protocol_usd"] or 0 for x in D]
custom = [x["custom_share_pct"] for x in D]
cut = next((i for i, d in enumerate(days) if d >= "2026-09-09"), None)

chart1 = bar_chart(dl_rev, days, fmt=lambda v: f"${v/1e6:.1f}M", color="#334155",
                   line=floor, line_color="#38bdf8")
chart2 = bar_chart(custom, days, fmt=lambda v: f"{v:.0f}%", color="#a78bfa",
                   marker_idx=cut, marker_text="custom pairs 上线 09-09",
                   y_max=max(custom) * 1.2)

C, B_, T_, P = (F["defillama"]["combined"], F["bottom_up"],
                F["turnover"], F["fees_page"])
gross_x = round(100 / B_["floor_vs_dl_fees_pct"], 1)

HTML = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pump.fun 收入口径对照</title>
<style>
 body{{margin:0;background:#07090d;color:#e8edf4;font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.6}}
 .wrap{{max-width:1240px;margin:0 auto;padding:28px 24px 60px}}
 h1{{font-size:20px;letter-spacing:2px}} h2{{font-size:14px;letter-spacing:3px;margin:34px 0 10px;color:#9aa6b6}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0}}
 .kpi{{background:#0e131b;border:1px solid #1b2431;border-radius:10px;padding:14px 16px}}
 .kpi .k{{color:#5d6a7a;font-size:11px;letter-spacing:1.5px}} .kpi .v{{font-size:22px;font-weight:800;margin-top:4px}}
 .kpi .h{{color:#5d6a7a;font-size:11px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;margin-top:8px}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #1b2431;vertical-align:top}}
 th{{color:#5d6a7a;font-weight:400;font-size:11px;letter-spacing:1.5px;text-transform:uppercase}}
 .legend{{color:#9aa6b6;font-size:12px;margin:6px 0}}
 .legend b{{color:#38bdf8}} .legend i{{color:#64748b;font-style:normal}}
 a{{color:#38bdf8}} .note{{color:#5d6a7a;font-size:12px}}
</style></head><body><div class="wrap">
<h1>pump.fun 收入口径对照 <span style="color:#5d6a7a;font-size:13px">public data · {esc(F['as_of'])}</span></h1>

<div class="kpis">
 <div class="kpi"><div class="k">官方年化（90d 均值）</div><div class="v">${esc(P['annualized_revenue_text'])}M</div>
   <div class="h">≈ ${esc(P['implied_daily_from_annualized_m'])}M/天</div></div>
 <div class="kpi"><div class="k">官方最新日回购 ÷ 50%</div><div class="v">${esc(P['implied_daily_from_buyback_m'])}M</div>
   <div class="h">隐含日收入（与 DL 30d 一致）</div></div>
 <div class="kpi"><div class="k">DefiLlama 30d 日收入</div><div class="v">${esc(C['revenue_per_day_30d_m'])}M</div>
   <div class="h">7d: ${esc(C['revenue_per_day_7d_m'])}M/天</div></div>
 <div class="kpi"><div class="k">自建下界 vs DL 曲线费用</div><div class="v">{esc(gross_x)}×</div>
   <div class="h">34 天周转倍数（毛下界口径）</div></div>
</div>

<h2>1) 官方日收入 vs 我们的独立下界</h2>
<div class="legend">灰柱 = DefiLlama 曲线日收入；<b>蓝线 = 我们的协议费下界（Σpeak_rs × 0.95%）</b>；
 <i>柱与线的距离 = 周转与盲区（中位 {T_['pre_cut']['median_x']}× → {T_['post_cut']['median_x']}×）</i></div>
{chart1}

<h2>2) 非 SOL（custom pairs）发币占比：缺口从这里开始</h2>
<div class="legend">紫柱 = 当天非 SOL 计价发币占比；09-09 跳升到 16.3%，之后 10~22%。
 <i>这正是官方看板自承认失真的区间，也是公开数据算不出金额的部分。</i></div>
{chart2}

<h2>3) 三方覆盖与盲区</h2>
<table>
<tr><th>来源</th><th>能看到</th><th>看不到</th></tr>
<tr><td><b>fees.pump.fun</b>（官方）</td>
 <td>年化收入、回购、销毁、活跃钱包</td>
 <td>自定义交易对的收入拆分（自承认失真）；口径细节（窗口/基数）</td></tr>
<tr><td><b>DefiLlama</b>（第三方）</td>
 <td>pump.fun / pumpswap 的日 fees/revenue/volume、历史序列</td>
 <td>发币级明细；quote 资产拆分；质量指标（有机/捆绑/跑路）</td></tr>
<tr><td><b>我们的预审计</b>（第三方独立方法）</td>
 <td>下界独立校验；非 SOL 占比与断点；质量基线；可复现的日频对账</td>
 <td>custom pairs 的费用金额、PumpSwap 明细、回购明细（需内部数据）</td></tr>
</table>

<h2>4) 原始来源（自己打开看）</h2>
<ul>
 <li>官方收入看板：<a href="https://fees.pump.fun/">fees.pump.fun</a></li>
 <li>官方费率文档：<a href="https://pump.fun/docs/fees">pump.fun/docs/fees</a></li>
 <li>DefiLlama pump.fun：<a href="https://defillama.com/protocol/pump.fun">defillama.com/protocol/pump.fun</a></li>
 <li>DefiLlama pumpswap：<a href="https://defillama.com/protocol/pumpswap">defillama.com/protocol/pumpswap</a></li>
 <li>第三方大盘：<a href="https://dune.com/browse/dashboards?q=pump.fun">Dune 上的 pump.fun 看板</a></li>
</ul>

<p class="note">全部数字来自 <code>pumpfun/audit/facts.json</code>；页面由
 <code>make_compare_page.py</code> 生成。DefiLlama 与 fees 页有 Cloudflare，
 本页是离线对照，不抓取实时。</p>
</div></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"写了 {OUT}")
