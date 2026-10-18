"""BFF 的配置。

所有上游路径都可覆盖 —— 因为本地开发、VPS 部署、测试三处的文件位置不同。
环境变量前缀 `PUMPIDEA_API_`，也读 `api/.env`。
"""
from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict

# api/app/config.py → api/ → 仓库根
REPO = pathlib.Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PUMPIDEA_API_", env_file=".env", extra="ignore")

    # ---- 上游文件（三条线产出的 JSON 文档）----
    analysis_facts: pathlib.Path = REPO / "analysis" / "facts.json"
    audit_report: pathlib.Path = REPO / "audit" / "stream_report.json"
    audit_facts: pathlib.Path = REPO / "audit" / "facts.json"
    pulse_data: pathlib.Path = REPO / "pulse" / "site" / "data.json"

    # ---- risk 是唯一需要反向代理的真服务 ----
    # 凭据只在服务端读取，浏览器永远拿不到（见 spec §7.1）
    risk_base_url: str = "http://127.0.0.1:8090"
    risk_creds: pathlib.Path = pathlib.Path("/etc/pumpfun-web.conf")
    # 单次打分实测约 19 秒（要扇出 ~80 次 RPC），超时必须宽于它
    risk_timeout: float = 60.0

    # ---- 静态前端 ----
    # 若该目录存在，BFF 直接托管 SPA（单进程单端口，Caddy 只需一条反代）。
    # 生产环境由 CI 构建后提交到这里；本地开发通常用 vite(5173) 而不是它。
    web_dist: pathlib.Path = REPO / "web" / "dist"
    serve_web: bool = True

    # 契约版本。改了归一化口径就跟着改，前端据此判断兼容性。
    contract_version: str = "v1"


settings = Settings()
