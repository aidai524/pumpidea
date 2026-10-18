"""pumpidea 的薄 BFF —— `/api/v1` 契约的唯一实现。

职责只有四件（见 spec §7.1），不多做：
  1. 把三份 JSON 文档归一化成稳定字段（前端不感知上游内部结构）
  2. 服务端持有 risk 的凭据（浏览器不接触）
  3. 统一的错误形状
  4. 上游可用性聚合（`/health`）

**不做**：缓存业务逻辑、重算任何指标、写任何数据。数字的唯一来源仍是各线的生成器。

鉴权在 P5 之前不做 —— 现在所有端点都是公开的。
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import docs, normalize, risk
from .config import REPO, settings

app = FastAPI(
    title="pumpidea API",
    version=normalize.CONTRACT_VERSION,
    description="四条线（analysis / audit / pulse / risk）的统一契约层。",
)

P = "/api/v1"


# ------------------------------------------------------------------ 错误形状
def _err(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    body = {"error": {"code": code, "message": message, **extra}}
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(docs.UpstreamError)
async def _on_upstream(_: Request, exc: docs.UpstreamError) -> JSONResponse:
    return _err(503, exc.code, exc.message, source=exc.source)


@app.exception_handler(risk.RiskUnavailable)
async def _on_risk(_: Request, exc: risk.RiskUnavailable) -> JSONResponse:
    status = 504 if exc.code == "upstream_timeout" else 502
    return _err(status, exc.code, exc.message, source="risk")


@app.exception_handler(HTTPException)
async def _on_http(_: Request, exc: HTTPException) -> JSONResponse:
    return _err(exc.status_code, "http_error", str(exc.detail))


# ------------------------------------------------------------------ 索引
# 注意路径是 /api/v1 而**不是** / —— "/" 必须留给 SPA，否则站点根会返回 JSON。
@app.get(P)
def index() -> dict:
    return {
        "service": "pumpidea-api",
        "contract_version": normalize.CONTRACT_VERSION,
        "endpoints": [
            f"{P}/health",
            f"{P}/analysis/overview", f"{P}/analysis/creators", f"{P}/analysis/economics",
            f"{P}/audit/summary", f"{P}/audit/reconciliation",
            f"{P}/pulse/feed",
            f"{P}/risk/health", f"{P}/risk/score/{{mint}}",
        ],
        "openapi": "/docs",
        "spa": "/ (由 BFF 托管 web/dist)",
    }


# ------------------------------------------------------------------ analysis
@app.get(f"{P}/analysis/overview")
def analysis_overview() -> dict:
    return normalize.analysis_overview(
        docs.load(settings.analysis_facts, source="analysis"))


@app.get(f"{P}/analysis/creators")
def analysis_creators() -> dict:
    return normalize.analysis_creators(
        docs.load(settings.analysis_facts, source="analysis"))


@app.get(f"{P}/analysis/economics")
def analysis_economics() -> dict:
    return normalize.analysis_economics(
        docs.load(settings.analysis_facts, source="analysis"))


# ------------------------------------------------------------------ audit
@app.get(f"{P}/audit/summary")
def audit_summary() -> dict:
    return normalize.audit_summary(
        docs.load(settings.audit_report, source="audit"))


@app.get(f"{P}/audit/reconciliation")
def audit_reconciliation() -> dict:
    return normalize.audit_reconciliation(
        docs.load(settings.audit_facts, source="audit"))


# ------------------------------------------------------------------ pulse
@app.get(f"{P}/pulse/feed")
def pulse_feed() -> dict:
    return normalize.pulse_feed(docs.load(settings.pulse_data, source="pulse"))


# ------------------------------------------------------------------ risk
@app.get(f"{P}/risk/health")
async def risk_health() -> dict:
    status, body = await risk.get("/health")
    return {"contract_version": normalize.CONTRACT_VERSION,
            "upstream_status": status, "risk": body}


@app.get(f"{P}/risk/score/{{mint}}")
async def risk_score(mint: str) -> Any:
    """透传打分。上游 404 = 这个 mint 没有曲线账户（不是我们的错），
    也按统一错误形状返回，让前端只有一种错误处理路径。"""
    mint = mint.strip()
    if not mint:
        raise HTTPException(status_code=400, detail="mint 不能为空")
    status, body = await risk.get(f"/score/{mint}")
    if status == 200 and body.get("ok"):
        return body
    return _err(
        status if status >= 400 else 502,
        str(body.get("reason") or "score_failed"),
        f"无法为 {mint} 打分：{body.get('reason') or '未知原因'}",
        mint=mint)


# ------------------------------------------------------------------ health
@app.get(f"{P}/health")
def health() -> dict:
    """四个上游的可用性与**数据陈旧度**。

    三条线的产出频率差几个数量级（pulse 30 秒 / audit 1 小时 /
    analysis 离线静态），不显示陈旧度会把几天前的数字当实时数据看。
    """
    now = int(time.time())

    def probe(path, source, ts_from_doc=None) -> dict:
        try:
            doc = docs.load(path, source=source)
        except docs.UpstreamError as exc:
            return {"source": source, "ok": False,
                    "error": {"code": exc.code, "message": exc.message},
                    "path": str(path)}
        generated_at = None
        if ts_from_doc:
            generated_at = ts_from_doc(doc)
        return {
            "source": source, "ok": True,
            "path": str(path),
            "generated_at": generated_at,
            "file_mtime": docs.fresh_at(path),
            "age_seconds": (now - int(path.stat().st_mtime)) if path.exists() else None,
        }

    sources = [
        probe(settings.analysis_facts, "analysis",
              lambda d: d.get("stats", {}).get("generated_at")),
        probe(settings.audit_report, "audit", lambda d: d.get("as_of")),
        probe(settings.pulse_data, "pulse", lambda d: d.get("generated_at")),
    ]

    # risk 是唯一需要发网络请求的上游，同步探一次就够。
    import httpx
    try:
        r = httpx.get(settings.risk_base_url.rstrip("/") + "/health",
                      headers=risk.auth_header(), timeout=5.0)
        sources.append({"source": "risk", "ok": r.status_code == 200,
                        "url": settings.risk_base_url, "status_code": r.status_code})
    except httpx.HTTPError as exc:
        sources.append({"source": "risk", "ok": False,
                        "error": {"code": "upstream_unreachable", "message": str(exc)},
                        "url": settings.risk_base_url})

    return {
        "contract_version": normalize.CONTRACT_VERSION,
        "checked_at": now,
        "ok": all(s.get("ok") for s in sources),
        "sources": sources,
    }


# ------------------------------------------------------------------ 静态前端
class SpaFiles(StaticFiles):
    """托管 SPA：文件不存在时回落到 index.html（否则刷新深链会 404）。

    Caddy 用 `handle_path /pumpfun/*` 剥掉前缀，所以这里看到的就是 `/`、`/analysis`
    这种路径；前端构建时 base=/pumpfun/，资源的绝对路径由浏览器带着前缀请求，
    再被 Caddy 剥掉 —— 两边是对上的。
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


# 挂载必须放在最后：先让上面的 /api/v1/* 路由匹配，剩下的才交给静态文件。
if settings.serve_web and settings.web_dist.is_dir():
    app.mount("/", SpaFiles(directory=settings.web_dist, html=True), name="web")
