#!/usr/bin/env python3
"""只读静态报表服务器（stdlib，带 Basic Auth）。

给 VPS 上的报表页用：不引入 nginx/busybox-extras，只需 python3。
凭据从 --creds 文件读取（KEY=VALUE 行，权限 600），不经过命令行参数（避免 ps 泄漏）。

用法：
  python3 serve_site.py --root /var/www/pumpfun --port 8080 --creds /etc/pumpfun-web.conf
"""
from __future__ import annotations

import argparse
import base64
import functools
import hmac
import http.server
import pathlib
import sys


def load_creds(path: str) -> tuple[str, str]:
    user, password = "pumpfun", ""
    p = pathlib.Path(path)
    if not p.exists():
        raise SystemExit(f"凭据文件不存在: {path}")
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
        raise SystemExit("凭据文件里没有 WEB_PASS")
    return user, password


class AuthHandler(http.server.SimpleHTTPRequestHandler):
    user = ""
    password = ""
    realm = "pumpfun-revenue"

    def _ok(self) -> bool:
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        try:
            u, p = base64.b64decode(h[6:]).decode().split(":", 1)
        except Exception:  # noqa: BLE001
            return False
        return hmac.compare_digest(u, self.user) and hmac.compare_digest(p, self.password)

    def _deny(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{self.realm}"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if not self._ok():
            self._deny()
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if not self._ok():
            self._deny()
            return
        super().do_HEAD()

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/var/www/pumpfun")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--creds", default="/etc/pumpfun-web.conf")
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()
    AuthHandler.user, AuthHandler.password = load_creds(args.creds)
    handler = functools.partial(AuthHandler, directory=args.root)
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as srv:
        print(f"serving {args.root} on {args.bind}:{args.port} (basic auth)", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
