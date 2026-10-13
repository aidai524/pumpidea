"""共享 RPC 客户端：优先付费端点，公共端点兜底。

端点解析顺序：
  1. --rpc 命令行
  2. 环境变量 ALCHEMY_RPC_URL / SOLANA_RPC_URL / RPC_URL
  3. pumpfun/audit/.env（gitignored）里的同名变量
  4. 公共 https://api.mainnet-beta.solana.com

用法：
  from rpc import Rpc, make_client
  client = make_client(cli=args.rpc, rate=args.rate)
  client.call("getBalance", [addr])
"""
from __future__ import annotations

import json
import os
import pathlib
import random
import threading
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
PUBLIC = "https://api.mainnet-beta.solana.com"


def load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def resolve_endpoints(cli: str | None = None) -> list[str]:
    load_env()
    eps: list[str] = []
    for name in ("ALCHEMY_RPC_URL", "SOLANA_RPC_URL", "RPC_URL"):
        v = os.environ.get(name)
        if v and v not in eps:
            eps.append(v)
    if cli and cli not in eps:
        eps.insert(0, cli)
    if not eps:
        eps.append(PUBLIC)
    return eps


class Rpc:
    def __init__(self, endpoints: list[str], *, rate: float = 0.0,
                 timeout: int = 30, retries: int = 5):
        self.endpoints = endpoints
        self.rate = rate            # 最小请求间隔（秒）；0 = 不限制
        self.timeout = timeout
        self.retries = retries
        self._lock = threading.Lock()
        self._last = 0.0
        self._rr = 0
        self.calls = 0

    def call(self, method: str, params: list):
        for attempt in range(self.retries):
            with self._lock:
                wait = self.rate - (time.time() - self._last)
                if wait > 0:
                    time.sleep(wait)
                ep = self.endpoints[self._rr % len(self.endpoints)]
                self._rr += 1
                self._last = time.time()
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}).encode()
            req = urllib.request.Request(ep, data=body, headers={
                "Content-Type": "application/json", "User-Agent": "pulse-audit/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    d = json.loads(r.read())
                self.calls += 1
                if "error" in d:
                    msg = str(d["error"]).lower()
                    if "429" in msg or "rate" in msg or "limit" in msg:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return None
                return d.get("result")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == self.retries - 1:
                    return None
                time.sleep(0.8 * (attempt + 1) + random.random())
        return None


def make_client(cli: str | None = None, rate: float = 0.0) -> Rpc:
    return Rpc(resolve_endpoints(cli), rate=rate)
