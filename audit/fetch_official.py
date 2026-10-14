#!/usr/bin/env python3
"""抓取并解析官方 fees.pump.fun 看板数字（公开页面，无 API）。

输出 data/fees_page_<date>.json：
  annualized_revenue_m / daily_avg_m / bought_back_m / burned_pump_b /
  daily_buyback_k / active_wallets_k / data_as_of / disclaimer
供 stream_report 与报表页做「官方 vs 我们」对照；失败不致命（返回 None）。
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
URL = "https://fees.pump.fun/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; Firefox/126.0)"}
DISCLAIMER = "does not correctly reflect the revenue and buyback"


def fetch_html(timeout: int = 30) -> str | None:
    try:
        req = urllib.request.Request(URL, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def parse(html: str) -> dict:
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"\s+", " ", t)

    def num(pat, cast=float):
        m = re.search(pat, t)
        try:
            return cast(m.group(1)) if m else None
        except (TypeError, ValueError):
            return None

    return {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "annualized_revenue_m": num(r"Annualized revenue \$([\d.]+)M"),
        "daily_avg_m": num(r"≈ \$([\d.]+)M / day"),
        "bought_back_m": num(r"Total bought back and burnt \$([\d.]+)M"),
        "burned_pump_b": num(r"([\d.]+)B \$PUMP burned"),
        "daily_buyback_k": num(r"USD spent per day \$([\d.]+)K latest"),
        "active_wallets_k": num(r"Solana ([\d.]+)K excl"),
        "data_as_of": (re.search(r"Data as of ([\w ]{3,8})", t).group(1).strip()
                       if re.search(r"Data as of ([\w ]{3,8})", t) else None),
        "disclaimer": DISCLAIMER in t,
        "source": URL,
    }


def load_or_fetch(max_age_s: float = 6 * 3600) -> dict | None:
    """优先读今天的缓存；过期则重抓（失败回退旧缓存）。"""
    today = time.strftime("%Y-%m-%d")
    path = DATA / f"fees_page_{today}.json"
    if path.exists():
        try:
            d = json.loads(path.read_text())
            if time.time() - path.stat().st_mtime < max_age_s and d.get("annualized_revenue_m"):
                return d
        except Exception:  # noqa: BLE001
            pass
    html = fetch_html()
    if html:
        d = parse(html)
        if d.get("annualized_revenue_m"):
            DATA.mkdir(exist_ok=True)
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1))
            return d
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            pass
    # 兜底：用最近一个缓存文件
    for f in sorted(DATA.glob("fees_page_*.json"), reverse=True):
        try:
            return json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
    return None


if __name__ == "__main__":
    d = load_or_fetch(max_age_s=0)
    print(json.dumps(d, ensure_ascii=False, indent=1))
