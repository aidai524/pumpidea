"""分享卡片：纯标准库生成 1080×1080 SVG。

为什么用 SVG 而不是截图：零依赖、可直接当图发（浏览器/矢量工具可转 PNG）、
文字永远清晰。卡片是「内容墙」的供货单元：一事件一张，底部留 CTA。
"""
from __future__ import annotations

import pathlib

from .stories import clean, esc

W = H = 1080
BG = "#0a0c10"
PANEL = "#11151d"
LINE = "#1e2634"
MUTED = "#6b7480"
TEXT = "#e8edf4"
SUB = "#aab4c2"
FONT = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'Liberation Mono', monospace")


def _wrap(text: str, width: int = 46, max_lines: int = 2) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and sum(len(x) for x in lines) < len(text):
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def render_card(s: dict) -> str:
    accent = s["accent"]
    kicker = esc(s["kicker"], 24)
    title = esc(s["title"], 22)
    value = esc(s["value"], 14)
    label = esc(s["label"], 60)
    sub_lines = _wrap(clean(s["sub"], 140), 46, 2)

    vlen = len(value)
    vsize = 168 if vlen <= 6 else max(92, 168 - (vlen - 6) * 14)
    tlen = len(title)
    tsize = 82 if tlen <= 14 else max(54, 82 - (tlen - 14) * 3)
    sub_tspans = "".join(
        f'<tspan x="64" dy="{0 if i == 0 else 46}">{esc(l, 60)}</tspan>'
        for i, l in enumerate(sub_lines))

    stats_svg = []
    for i, (k, v) in enumerate(s["stats"][:3]):
        x = 64 + i * 336
        stats_svg.append(
            f'<text x="{x}" y="884" fill="{MUTED}" font-size="24" '
            f'letter-spacing="2">{esc(k, 22).upper()}</text>'
            f'<text x="{x}" y="944" fill="{TEXT}" font-size="46" '
            f'font-weight="700">{esc(v, 22)}</text>')
    stats_svg = "".join(stats_svg)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect x="0" y="0" width="14" height="{H}" fill="{accent}"/>
  <rect x="64" y="64" width="952" height="952" rx="28" fill="none" stroke="{LINE}"/>
  <circle cx="118" cy="128" r="9" fill="{accent}"/>
  <text x="150" y="140" fill="{TEXT}" font-family="{FONT}" font-size="38" font-weight="800" letter-spacing="8">PULSE</text>
  <text x="1016" y="138" text-anchor="end" fill="{accent}" font-family="{FONT}" font-size="26" font-weight="700" letter-spacing="3">{kicker}</text>
  <line x1="64" y1="196" x2="1016" y2="196" stroke="{LINE}"/>
  <text x="64" y="470" fill="{TEXT}" font-family="{FONT}" font-size="{vsize}" font-weight="800" letter-spacing="-2">{value}</text>
  <text x="64" y="536" fill="{SUB}" font-family="{FONT}" font-size="36">{label}</text>
  <text x="64" y="668" fill="{accent}" font-family="{FONT}" font-size="{tsize}" font-weight="800">“{title}”</text>
  <text x="64" y="762" fill="{SUB}" font-family="{FONT}" font-size="34">{sub_tspans}</text>
  <rect x="64" y="824" width="952" height="1" fill="{LINE}"/>
  {stats_svg}
  <rect x="64" y="972" width="952" height="0" fill="none"/>
  <text x="64" y="1016" fill="{MUTED}" font-family="{FONT}" font-size="24" letter-spacing="1">PUBLIC ON-CHAIN DATA · NOT FINANCIAL ADVICE</text>
  <text x="1016" y="1016" text-anchor="end" fill="{accent}" font-family="{FONT}" font-size="24" font-weight="700">watch on pump.fun →</text>
</svg>
'''


def write_cards(site_dir: pathlib.Path, stories: list[dict]) -> None:
    out = site_dir / "cards"
    out.mkdir(parents=True, exist_ok=True)
    for s in stories:
        (out / f"{s['id']}.svg").write_text(render_card(s), encoding="utf-8")
