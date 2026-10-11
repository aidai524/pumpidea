"""取数层：loopholetape 的公开端点。只用标准库，失败不炸采集循环。

端点（2026-10-10 实测可用，无需 key）：
  /v1/radar        实时候选：top_graduation / top_rug_risk，refresh_s=5
  /v1/graduations  最近 24h（最多 200 行）真实毕业 + 聚合 counts
  /v1/stats/pumpfun 每日统计快照
付费端点（demo 不用）：/v1/mint/{mint} $0.005、/v1/check/mint/{mint}
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "https://api.loopholetape.com"
UA = "pulse-demo/0.1 (+local research; contact: analysis repo)"


def get_json(path: str, timeout: int = 30, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            BASE + path, headers={"User-Agent": UA, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {path} 失败: {last}")


def fetch_radar() -> dict:
    d = get_json("/v1/radar")

    return d.get("data") or {}


def fetch_graduations() -> dict:
    d = get_json("/v1/graduations")

    return d.get("data") or {}


def fetch_stats() -> dict:
    return get_json("/v1/stats/pumpfun")
