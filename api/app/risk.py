"""risk 的反向代理 —— BFF 里唯一"真的转发"的部分。

为什么必须由服务端代转：`score_service.py` 用 Basic Auth 保护，而那套凭据在
`/etc/pumpfun-web.conf`（600）。如果让浏览器直连 8090，凭据就得下发到前端；
由 BFF 代转则**浏览器永远接触不到凭据**（见 spec §7.1）。

另一个原因：单次打分实测约 19 秒（要扇出约 80 次 RPC）。直连的话浏览器会
看到一个悬着的请求；经过 BFF 我们可以给它一个明确的超时与错误形状。
"""
from __future__ import annotations

import base64
import pathlib

import httpx

from .config import settings


def auth_header() -> dict[str, str]:
    """从 creds 文件读凭据。文件不存在 = risk 未开鉴权，不加头。"""
    p = pathlib.Path(settings.risk_creds)
    if not p.exists():
        return {}
    user, password = "pumpfun", ""
    for line in p.read_text().splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        if k == "WEB_USER":
            user = v
        elif k == "WEB_PASS":
            password = v
    if not password:
        return {}
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class RiskUnavailable(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def get(path: str) -> tuple[int, dict]:
    """转发到 risk 服务。返回 (状态码, JSON)。

    连不上 / 超时 → 抛 RiskUnavailable，由 main 统一映射成 502/504。
    """
    url = settings.risk_base_url.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=settings.risk_timeout) as c:
            r = await c.get(url, headers=auth_header())
    except httpx.TimeoutException as exc:
        raise RiskUnavailable(
            "upstream_timeout",
            f"risk 打分超时（{settings.risk_timeout:.0f}s）：{exc}") from None
    except httpx.HTTPError as exc:
        raise RiskUnavailable(
            "upstream_unreachable", f"连不上 risk 服务：{exc}") from None

    try:
        return r.status_code, r.json()
    except ValueError:
        raise RiskUnavailable(
            "upstream_invalid",
            f"risk 返回了非 JSON（HTTP {r.status_code}）") from None
