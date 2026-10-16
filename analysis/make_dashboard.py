#!/usr/bin/env python3
"""用 analysis/facts.json 生成一块只读仪表盘 → analysis/site/index.html。

为什么需要：主研究（analysis/）的交付物是 Markdown 报告，是四条线里唯一没有
网页形态的一条；pulse / audit / risk 都有页面。这里把 facts.json 里**已经算好**
的数字渲染成页，供快速浏览与核对。

原则：
  * **只读 facts.json，不重算任何指标** —— 数字的唯一来源仍是 analyze.py。
  * 无第三方依赖（stdlib + 内联 SVG），可离线打开。
  * 视觉沿用 audit 页面的既有配色与字体（ui-monospace + 深色），四条线保持一致。

用法：python3 analysis/make_dashboard.py
"""
from __future__ import annotations

import json
import pathlib
import xml.sax.saxutils as sax

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "site" / "index.html"

F = json.loads((ROOT / "facts.json").read_text())

ST = F["stats"]
W30, W7 = ST["windows"]["30d"], ST["windows"]["7d"]
TR, DAILY, POOLS = ST["trend"], ST["daily"], ST["pools"]
LABEL, DEFS = ST["label_check"], ST["definitions"]
DL, RV, HF = F["defillama"], F["revenue"], F["hf"]
LP, PS, CMB = DL["launchpad"], DL["pumpswap"], DL["combined_30d"]
BIK = W30["by_kind"]


# ---------------------------------------------------------------- 格式化
def esc(s) -> str:
    return sax.escape(str(s))


def num(x, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def pct(x, d: int = 2) -> str:
    return f"{x * 100:.{d}f}%"


def usd(x) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= div:
            return f"${x / div:.2f}{suf}"
    return f"${x:,.0f}"


def secs(x) -> str:
    return f"{x:,.0f}s" if x >= 1 else f"{x:.2f}s"


# ---------------------------------------------------------------- 图表
def dual_chart(points: list[dict], *, bar_fmt, line_fmt, caption: str,
               W: int = 1240, H: int = 340, L: int = 84, R: int = 84,
               T: int = 34, B: int = 58) -> str:
    """柱（左轴，供给量）+ 折线（右轴，比率）。两个量纲不同，各自一条轴。"""
    n = len(points)
    bar_max = max(p["bar"] for p in points) * 1.12 or 1
    line_max = max(p["line"] for p in points) * 1.30 or 1
    ph = H - T - B
    band = (W - L - R) / n
    yb = lambda v: H - B - (v / bar_max) * ph
    yl = lambda v: H - B - (v / line_max) * ph

    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="ui-monospace,Menlo,monospace" role="img">',
         f'<rect width="{W}" height="{H}" style="fill:var(--surface)"/>']
    for f in (0.0, 0.5, 1.0):
        y = yb(bar_max * f)
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" '
                 f'style="stroke:var(--line)" stroke-dasharray="3 3"/>')
        o.append(f'<text x="{L - 10}" y="{y + 4:.1f}" font-size="11" text-anchor="end" '
                 f'style="fill:var(--dim)">{esc(bar_fmt(bar_max * f))}</text>')
        o.append(f'<text x="{W - R + 10}" y="{y + 4:.1f}" font-size="11" '
                 f'style="fill:var(--accent)">{esc(line_fmt(line_max * f))}</text>')
    for i, p in enumerate(points):
        x = L + i * band + band * 0.22
        h = (p["bar"] / bar_max) * ph
        o.append(f'<rect x="{x:.1f}" y="{H - B - h:.1f}" width="{band * 0.56:.1f}" '
                 f'height="{h:.1f}" rx="1.5" style="fill:var(--bar)" opacity="0.9"/>')
    pts = " ".join(f"{L + i * band + band / 2:.1f},{yl(p['line']):.1f}"
                   for i, p in enumerate(points))
    o.append(f'<polyline points="{pts}" fill="none" style="stroke:var(--accent)" '
             f'stroke-width="2.4" stroke-linejoin="round"/>')
    step = max(1, n // 12)
    for i in range(0, n, step):
        o.append(f'<text x="{L + i * band + band / 2:.1f}" y="{H - B + 20}" font-size="11" '
                 f'text-anchor="middle" style="fill:var(--dim)">'
                 f'{esc(points[i]["label"][5:])}</text>')
    o.append(f'<text x="{L}" y="{T - 12}" font-size="11" style="fill:var(--dim)">{esc(caption)}</text>')
    o.append(f'<rect x="{L}" y="{T - 24}" width="10" height="10" rx="2" style="fill:var(--bar)"/>')
    o.append(f'<text x="{L + 16}" y="{T - 15}" font-size="11" style="fill:var(--dim)">柱＝每日发币量（左轴）</text>')
    o.append(f'<line x1="{L + 190}" y1="{T - 19}" x2="{L + 212}" y2="{T - 19}" '
             f'style="stroke:var(--accent)" stroke-width="2.4"/>')
    o.append(f'<text x="{L + 220}" y="{T - 15}" font-size="11" style="fill:var(--dim)">线＝有机毕业率（右轴）</text>')
    o.append("</svg>")
    return "".join(o)


def mini_bar(value: float, maximum: float, color: str) -> str:
    w = min(100.0, (value / maximum) * 100) if maximum else 0
    return (f'<span class="track"><span class="fill" style="width:{w:.1f}%;'
            f'background:{color}"></span></span>')


def kpi(k: str, v: str, hint: str = "", tone: str = "") -> str:
    cls = f' kpi {tone}' if tone else " kpi"
    return (f'<div class="{cls.strip()}"><div class="k">{esc(k)}</div>'
            f'<div class="v">{esc(v)}</div>'
            f'<div class="h">{esc(hint)}</div></div>')


def row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


# ---------------------------------------------------------------- 派生（只做除法，不重算口径）
lp_vol, lp_fee, lp_rev = LP["volume"]["total30d"], LP["fees"]["total30d"], LP["revenue"]["total30d"]
ps_vol, ps_fee, ps_rev = PS["volume"]["total30d"], PS["fees"]["total30d"], PS["revenue"]["total30d"]
ps_vol_share, ps_rev_share = ps_vol / CMB["volume"], ps_rev / CMB["revenue"]
lp_rate, ps_rate = lp_rev / lp_vol, ps_rev / ps_vol

# 图表数据
chart1 = dual_chart(
    [{"label": d["day"], "bar": d["launches"], "line": d["organic_graduation_rate"]} for d in DAILY],
    bar_fmt=lambda v: f"{v / 1000:,.0f}k", line_fmt=lambda v: f"{v * 100:.1f}%",
    caption="30 天：供给与真实质量反向",
)

# kind 占比条
kind_rows = []
for key, zh, tone in (("classic", "classic（SOL 计价、非 mayhem）", "var(--accent)"),
                      ("mayhem", "mayhem 模式", "var(--bad)"),
                      ("other_quote", "其他计价资产", "var(--violet)"),
                      ("quote_not_established", "计价未确认", "var(--dim)")):
    k = BIK.get(key) or {}
    la = k.get("launches", 0)
    kind_rows.append(
        f'<div class="kindline"><span class="kindname">{esc(zh)}</span>'
        f'<span class="kindbar"><i style="width:{la / W30["launches"] * 100:.1f}%;'
        f'background:{tone}"></i></span>'
        f'<span class="kindnum">{num(la)}　{la / W30["launches"] * 100:.1f}%</span></div>')
kind_block = "".join(kind_rows)

# 老手 vs 新手
vet_rows = "".join(
    row([esc(k), num(v["n"]), f'{v["graduation_rate_pct"]:.2f}%', f'{v["rug_rate_pct"]:.2f}%',
         "—" if v["mean_prior_rugs"] is None else f'{v["mean_prior_rugs"]:.2f}',
         f'{v["mean_dev_share_pct"]:.2f}%'])
    for k, v in HF["veteran"]["by_prior_launches"].items())

# 分位分布
def dist_rows(d: dict, fmt, unit: str) -> str:
    mx = max(d[k] for k in ("p50", "p75", "p90", "p95", "p99"))
    return "".join(
        row([k, fmt(d[k]) + unit, mini_bar(d[k], mx, "var(--violet)")])
        for k in ("p25", "p50", "p75", "p90", "p95", "p99") if k in d)


peak_rows = dist_rows(HF["peak_rs"]["launches"], lambda v: f"{v:,.2f}", " SOL")
bundle_rows = dist_rows(HF["bundling"], lambda v: f"{v:,.0f}", " 个")
dev_rows = dist_rows(HF["dev_share"], lambda v: f"{v * 100:.2f}", "%")

# ticker 榜
ticker_rows = "".join(
    row([esc(t["ticker"]), num(t["n"]), num(t["graduated"]), f'{t["rug_rate_pct"]:.1f}%'])
    for t in HF["tickers"]["top"][:8])

# 缺口
CAVEATS = [
    ("窗口只有 30~32 天", "不足以谈季节性，也不足以判断趋势是否持续"),
    ("2026-09-27 前解码器漏约 48% 买单", "KI-02 —— 涉时序的分析只用 09-27 之后的 5 天"),
    ("f10_* 在旧子集是非随机抽样", "KI-01 —— 干净窗口（09-27 起）改为逐币重放 tape_replay，占 99.74%"),
    ("rugged 与 graduated 不互斥", "KI-13 —— 9.9% 兼有，故「跑路率」≠ 1 − 毕业率"),
    ("rugged 是观察规则，非已验证欺诈", "多数是创建者在小曲线上砸自己的盘"),
    ("mayhem 占比与第三方差 3.5 倍", "本报告 26% vs 一份 2026-01 的 Dune 分析约 91%，更可能来自口径"),
    ("收入下界比实际低约 20 倍", "下界只含曲线净流入；它的用途是校验量级，不是估计值"),
    ("DefiLlama 的量与费口径不一致",   "它的 PumpSwap 量会过滤刷量池，费用不过滤 —— 不要用量除费"),
]
caveat_items = "".join(f"<li><b>{esc(a)}</b> —— {esc(b)}</li>" for a, b in CAVEATS)

# ---------------------------------------------------------------- 样式（仅此一套词汇表）
CSS = """
:root{
  --bg:#07090d; --surface:#0e131b; --line:#1b2431;
  --ink:#e8edf4; --dim:#5d6a7a; --sub:#9aa6b6;
  --accent:#38bdf8; --violet:#a78bfa; --amber:#f59e0b;
  --good:#22c55e; --bad:#ff4d6d; --bar:#334155;
  --r-card:12px; --r-ctl:8px;
  --sp1:4px; --sp2:8px; --sp3:12px; --sp4:16px; --sp6:24px; --sp8:32px; --sp12:48px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.65}
.wrap{max-width:1280px;margin:0 auto;padding:var(--sp8) var(--sp6) 64px}
header{border-bottom:1px solid var(--line);padding-bottom:var(--sp6);margin-bottom:var(--sp8)}
h1{font-size:22px;letter-spacing:2px;margin:0 0 var(--sp2)}
.sub{color:var(--sub);font-size:12px}
.sub b{color:var(--ink);font-weight:600}
h2{font-size:13px;letter-spacing:3px;color:var(--sub);font-weight:600;
  margin:var(--sp12) 0 var(--sp3);padding-bottom:var(--sp2);border-bottom:1px solid var(--line)}
h2 span{color:var(--dim);letter-spacing:1px;font-weight:400;margin-left:var(--sp2)}
.note{color:var(--dim);font-size:12px;margin:var(--sp2) 0 var(--sp3)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--sp3);margin:var(--sp4) 0}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);padding:var(--sp4)}
.kpi .k{color:var(--dim);font-size:11px;letter-spacing:1.5px}
.kpi .v{font-size:22px;font-weight:600;margin-top:var(--sp1);letter-spacing:-0.5px}
.kpi .h{color:var(--dim);font-size:11px;margin-top:var(--sp1)}
.kpi.bad .v{color:var(--bad)} .kpi.good .v{color:var(--good)} .kpi.amber .v{color:var(--amber)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:var(--sp3);margin:var(--sp3) 0}
svg{display:block;width:100%;height:auto}
table{width:100%;border-collapse:collapse;margin-top:var(--sp2)}
th,td{text-align:left;padding:var(--sp2) var(--sp3);border-bottom:1px solid var(--line)}
th{color:var(--dim);font-size:11px;letter-spacing:1.5px;font-weight:400}
tr:last-child td{border-bottom:0}
td{font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:var(--sp3)}
.track{display:inline-block;width:110px;height:6px;background:var(--bg);
  border-radius:99px;overflow:hidden;vertical-align:middle;margin-left:var(--sp2)}
.track .fill{display:block;height:100%}
.kindline{display:flex;align-items:center;gap:var(--sp3);padding:var(--sp2) 0}
.kindname{flex:0 0 240px;font-size:12px}
.kindbar{flex:1;height:10px;background:var(--bg);border-radius:99px;overflow:hidden}
.kindbar i{display:block;height:100%}
.kindnum{flex:0 0 150px;text-align:right;color:var(--sub);font-size:12px;
  font-variant-numeric:tabular-nums}
.callout{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--amber);
  border-radius:var(--r-ctl);padding:var(--sp3) var(--sp4);margin:var(--sp3) 0;font-size:13px}
.callout b{color:var(--amber)}
ul.caveats{margin:var(--sp2) 0 0;padding-left:var(--sp6);color:var(--sub);font-size:12px}
ul.caveats li{margin:var(--sp2) 0}
ul.caveats b{color:var(--ink);font-weight:600}
footer{color:var(--dim);font-size:11px;border-top:1px solid var(--line);
  margin-top:var(--sp12);padding-top:var(--sp4)}
a{color:var(--accent);text-decoration:none}
"""

# ---------------------------------------------------------------- 组装
HTML = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pump.fun 发币经济 · 全量链上观察</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
  <h1>pump.fun 发币经济 · 全量链上观察</h1>
  <div class="sub">
    窗口 <b>{esc(ST['coverage']['first_day'])} ~ {esc(ST['coverage']['last_day'])}</b>
    （{ST['coverage']['days']} 天）·
    数据集 <b>{num(HF['rows']['total'])} 行</b>（{HF['columns']} 列）·
    标签校验 召回 <b>{LABEL['recall'] * 100:.2f}%</b> / 精确 <b>{LABEL['precision'] * 100:.2f}%</b>
    （{num(LABEL['classic_sol_launches'])} 个 classic）·
    本页所有数字来自 <b>analysis/facts.json</b>，不手写
  </div>
</header>

<h2>一页速览</h2>
<div class="kpis">
  {kpi("30 天新发代币", num(W30["launches"]), f"日均 {num(W30['launches'] / W30['days'])}")}
  {kpi("名义毕业率", pct(W30["graduation_rate"]), f"毕业 {num(W30['graduated'])} 个")}
  {kpi("有机毕业率", pct(W30["organic_graduation_rate"]), "扣除机器人捆绑后的真实值", "bad")}
  {kpi("瞬时(捆绑)毕业占毕业", pct(W30["instant_share_of_graduations"], 1), f"{num(W30['instant_graduations'])} 个 2 秒内完成", "amber")}
  {kpi("300 秒内被判跑路", pct(W30["rug_within_300s_rate"], 1), f"{num(W30['rugged_within_300s'])} 个")}
  {kpi("创建者 60 秒内卖出", pct(W30["creator_sold_within_60s_share"], 1), f"{num(W30['creator_sold_within_60s'])} 个")}
  {kpi("30 天净收入", usd(CMB["revenue"]), f"用户付费 {usd(CMB['fees'])}", "good")}
  {kpi("30 天交易量", usd(CMB["volume"]), f"隐含综合费率 {pct(CMB['implied_blended_fee_rate'])}")}
  {kpi("发币端抽成率", pct(lp_rate, 3), "高毛利：曲线 1.25% 中的协议部分", "good")}
  {kpi("PumpSwap 量占比", pct(ps_vol_share, 1), f"但只贡献 {pct(ps_rev_share, 1)} 的收入", "amber")}
</div>

<div class="callout">
  <b>结构错配</b>：PumpSwap 的交易量是发币曲线的 <b>{ps_vol / lp_vol:.1f} 倍</b>，
  但留给平台的收入只有发币端的 <b>{ps_rev / lp_rev:.2f} 倍</b> ——
  因为它的协议分成只有 0.05%（曲线是 0.95%）。<b>{pct(ps_vol_share, 0)} 的量只换来 {pct(ps_rev_share, 0)} 的收入。</b>
</div>

<h2>规模与节奏 <span>supply ↑ / quality ↓</span></h2>
<div class="panel">{chart1}</div>
<div class="grid2">
  <div><table>
    <tr><th>周（UTC）</th><th>发币/日</th><th>名义毕业率</th><th>有机毕业率</th><th>捆绑占毕业</th><th>300s 跑路率</th></tr>
    {"".join(row([esc(w["from"][5:]), num(w["launches"], 0), pct(w["graduation_rate"]), pct(w["organic_graduation_rate"]), pct(w["instant_share_of_graduations"], 1), pct(w["rug_within_300s_rate"], 1)]) for w in TR["weekly"])}
  </table>
  <div class="note">首周 → 末周：发币量 <b>+{TR['change']['launches_pct']}%</b>，
  名义毕业率 <b>{TR['change']['graduation_rate_pp']}pp</b>，
  捆绑占毕业 <b>{TR['change']['instant_share_pp']}pp</b>。
  供给在猛涨，成功率在跌 —— 零成本创建意味着边际进入者永远是最差的那一批。</div>
  </div>
  <div><table>
    <tr><th>结局（30 天）</th><th>数量</th><th>口径</th></tr>
    {row(["真毕业", num(W30["graduated"]), "曲线吃满 85 SOL 或见迁移"])}
    {row(["其中瞬时(捆绑)毕业", num(W30["instant_graduations"]), "发币 2 秒内完成，中位耗时 " + secs(W30["median_s_to_graduation_all"])])}
    {row(["其中有机毕业", num(W30["organic_graduations"]), "中位耗时 " + secs(W30["median_s_to_graduation_organic"])])}
    {row(["曲线峰值 p50", f"{HF['peak_rs']['launches']['p50']:.2f} SOL", "一半的币整个生命周期没超过它"])}
    {row(["毕业后 30 分钟跌 90%+", pct(POOLS["share_lost_90pct_in_30m"], 1), f"{num(POOLS['full_pools'])} 个池，中位崩盘 {secs(POOLS['median_s_to_collapse'])}"])}
  </table>
  <div class="note">捆绑与有机的中位耗时差
  <b>{W30['median_s_to_graduation_organic'] / W30['median_s_to_graduation_all']:.0f} 倍</b>
  —— 0.367 秒意味着币还没被人看见就已经走完曲线。</div>
  </div>
</div>

<h2>三种发币模式 <span>不要混算</span></h2>
<div class="panel">{kind_block}
  <table>
    <tr><th>模式</th><th>发币</th><th>名义毕业率</th><th>链上标 complete</th><th>300s 跑路率</th><th>创建者 60s 卖出</th></tr>
    {row(["classic", num(BIK["classic"]["launches"]), pct(BIK["classic"]["graduation_rate"]), f"{BIK['classic']['complete_on_chain'] / BIK['classic']['launches'] * 100:.2f}%", pct(BIK["classic"]["rug_within_300s_rate"], 1), pct(BIK["classic"]["creator_sold_within_60s_share"], 1)])}
    {row(["mayhem", num(BIK["mayhem"]["launches"]), pct(BIK["mayhem"]["graduated"] / BIK["mayhem"]["launches"], 3), pct(BIK["mayhem"]["complete_share"]), pct(BIK["mayhem"]["rug_within_300s_rate"], 1), pct(BIK["mayhem"]["creator_sold_within_60s_share"], 1)])}
    {row(["other_quote", num(BIK["other_quote"]["launches"]), "不可比（非 SOL 计价）", pct(BIK["other_quote"]["complete_share"]), "—", pct(BIK["other_quote"]["creator_sold_within_60s_share"], 1)])}
  </table>
  <div class="note">
    mayhem 占发币量 {pct(BIK['mayhem']['share_of_launches'], 1)}，毕业率比 classic 低
    <b>{(BIK['classic']['graduation_rate'] / (BIK['mayhem']['graduated'] / BIK['mayhem']['launches'])):.0f} 倍</b>。
    <b>「链上标 complete」与「毕业」是两回事</b> —— 引用 mayhem 成功率前必须确认用的是哪个定义。
    逐日占比全程 {HF['mayhem_by_day']['share_pct_min']}%~{HF['mayhem_by_day']['share_pct_max']}%，
    均值 {HF['mayhem_by_day']['share_pct_mean']}%，没有趋势。
  </div>
</div>

<h2>谁在发币 <span>工厂，不是社区</span></h2>
<div class="grid2">
  <div class="panel">
    <div class="note">创建者集中度（classic 子集，{num(HF['creator_concentration']['launches']['launches'])} 个币）</div>
    <table>
      {row(["唯一创建者", num(HF["creator_concentration"]["launches"]["creators"])])}
      {row(["人均发币", f"{HF['creator_concentration']['launches']['per_creator_mean']:.2f} 个"])}
      {row(["发币最多的单个钱包", f"{num(HF['creator_concentration']['launches']['top1'])} 个"])}
      {row(["top 1000 创建者", pct(HF["creator_concentration"]["launches"]["top1000_share_pct"] / 100, 2)])}
      {row(["占一半发币量所需创建者", f"{num(HF['creator_concentration']['launches']['creators_for_half'])} 人"])}
    </table>
    <div class="note">即全部创建者的
      <b>{HF['creator_concentration']['launches']['creators_for_half'] / HF['creator_concentration']['launches']['creators'] * 100:.1f}%</b>
      发了一半的币。</div>
  </div>
  <div class="panel">
    <div class="note">按创建者历史发币数分层（重放特征，{num(HF['veteran']['rep_rows'])} 行）</div>
    <table>
      <tr><th>此前发过</th><th>币数</th><th>毕业率</th><th>跑路率</th><th>历史均跑路</th><th>均 dev_share</th></tr>
      {vet_rows}
    </table>
    <div class="note"><b>反直觉：职业发币者的成功率更低。</b>新钱包是职业发币者的
      <b>{HF['veteran']['by_prior_launches']['0']['graduation_rate_pct'] / HF['veteran']['by_prior_launches']['20+']['graduation_rate_pct']:.1f} 倍</b>。
      而那批「发过 20+ 次」的地址平均已跑路
      <b>{HF['veteran']['by_prior_launches']['20+']['mean_prior_rugs']:.2f} 次</b>，仍在持续发币。</div>
  </div>
</div>

<div class="grid2">
  <div class="panel">
    <div class="note">发币首分钟的捆绑钱包数（{num(HF['bundling']['n'])} 行）</div>
    <table><tr><th>分位</th><th>钱包数</th><th></th></tr>{bundle_rows}</table>
    <div class="note">零捆绑 <b>{HF['bundling']['share_zero_pct']}%</b>，
      ≥5 个 <b>{HF['bundling']['share_ge5_pct']}%</b>，≥10 个 <b>{HF['bundling']['share_ge10_pct']}%</b>。</div>
  </div>
  <div class="panel">
    <div class="note">创建者首分钟持仓占比 dev_share（{num(HF['dev_share']['n'])} 行）</div>
    <table><tr><th>分位</th><th>占比</th><th></th></tr>{dev_rows}</table>
    <div class="note">中位 <b>{HF['dev_share']['p50'] * 100:.2f}%</b>，但 p99 达
      <b>{HF['dev_share']['p99'] * 100:.1f}%</b> —— 尾部有一批人开局就握着八成。</div>
  </div>
</div>

<div class="grid2">
  <div class="panel">
    <div class="note">曲线储备峰值 peak_rs（SOL，上限 85）</div>
    <table><tr><th>分位</th><th>SOL</th><th></th></tr>{peak_rows}</table>
  </div>
  <div class="panel">
    <div class="note">被发最多的 ticker（{num(HF['tickers']['unique'])} 个不同 ticker / {num(HF['tickers']['launches'])} 个币）</div>
    <table><tr><th>ticker</th><th>币数</th><th>毕业</th><th>跑路率</th></tr>{ticker_rows}</table>
    <div class="note">平均每个 ticker 出现 <b>{HF['tickers']['mean_per_ticker']:.2f} 次</b> —— 代币名称已基本丧失信息量。</div>
  </div>
</div>

<h2>钱去哪了</h2>
<div class="grid2">
  <div class="panel">
    <table>
      <tr><th>30 天</th><th>交易量</th><th>用户付费</th><th>平台净收入</th><th>抽成率</th></tr>
      {row(["发币曲线（bonding curve）", usd(lp_vol), usd(lp_fee), usd(lp_rev), pct(lp_rate, 3)])}
      {row(["PumpSwap（毕业后）", usd(ps_vol), usd(ps_fee), usd(ps_rev), pct(ps_rate, 3)])}
      {row(["<b>合计</b>", f"<b>{usd(CMB['volume'])}</b>", f"<b>{usd(CMB['fees'])}</b>", f"<b>{usd(CMB['revenue'])}</b>", f"<b>{pct(CMB['revenue'] / CMB['volume'], 3)}</b>"])}
    </table>
  </div>
  <div class="panel">
    <div class="note">量与收入的倒挂</div>
    <div class="kindline"><span class="kindname">交易量占比</span>
      <span class="kindbar"><i style="width:{ps_vol_share * 100:.1f}%;background:var(--bar)"></i></span>
      <span class="kindnum">PumpSwap {pct(ps_vol_share, 0)}</span></div>
    <div class="kindline"><span class="kindname">净收入占比</span>
      <span class="kindbar"><i style="width:{ps_rev_share * 100:.1f}%;background:var(--amber)"></i></span>
      <span class="kindnum">PumpSwap {pct(ps_rev_share, 0)}</span></div>
    <div class="note">一笔交易的钱怎么分（当前费率）</div>
    <table>
      {row(["曲线上用户付 1.25%", "0.30% → 创建者<br>0.95% → pump.fun"])}
      {row(["PumpSwap 用户付 0.30%", "0.05% → 创建者<br>0.20% → LP<br>0.05% → pump.fun"])}
    </table>
  </div>
</div>

<div class="panel">
  <div class="note">独立校验：不依赖任何第三方，只用公开链上数据把量级钉住</div>
  <table>
    {row(["Σ peak_rs（32 天，SOL）", f"{num(RV['peak_rs_sum_sol_total'])} SOL"])}
    {row(["按 SOL 价换算", f"{usd(RV['volume_floor_usd'])}（@ ${RV['sol_usd']}/SOL，{esc(RV['sol_usd_source'])}）"])}
    {row(["曲线毛手续费下界", usd(RV["fee_floor_gross_usd"])])}
    {row(["其中协议分成下界", usd(RV["fee_floor_protocol_usd"])])}
    {row(["对比实际 30 天费用", f"{usd(CMB['fees'])}（<b>{CMB['fees'] / RV['fee_floor_protocol_usd']:.0f} 倍</b>）"])}
  </table>
  <div class="note">{esc(RV["note"])}。差距不是错误，而是「同一笔钱在曲线上被反复买卖了多少次」的度量。</div>
</div>

<h2>已知缺口 <span>读任何结论前先读这里</span></h2>
<ul class="caveats">{caveat_items}</ul>

<footer>
  数据来源：loopholetape 日统计 API 与 HF 数据集 <i>pump.fun launches with outcomes</i>（CC BY 4.0）、
  DefiLlama（pump.fun / pumpswap）、pump.fun 官方文档 docs/fees、CoinGecko（SOL ${RV['sol_usd']}）。
  <br>口径与推导见 <b>report.md</b>，数字来源见 <b>analysis/facts.json</b>（由 analyze.py 生成）。
  本页由 <b>analysis/make_dashboard.py</b> 生成，只读 facts.json，不重算指标。
</footer>
</div></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"写了 {OUT}（{len(HTML) / 1024:.1f} KB）")
