"""读取上游 JSON 文档，带 mtime 缓存。

**为什么需要这个 module**：三条线的产出频率差几个数量级 ——

    pulse     每 30 秒重建一次
    audit     每小时重建一次
    analysis  离线静态，可能是几天前

所以每个响应都必须带数据的生成时间，让前端能把陈旧度显示出来。
不标出来的话，一个 3 天前的数字会被当成实时数据看。

缓存策略：按文件 mtime + size 失效。文件由各自的生成器**整体覆写**，
所以不存在读到半截的问题（覆写不是原子操作，但 JSON 解析失败只会让这一
个请求返回 503，不会污染缓存）。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any


class UpstreamError(Exception):
    """上游数据不可用（缺失、读不动、JSON 坏掉）。"""

    def __init__(self, code: str, message: str, *, source: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source


# path → (mtime_ns, size, parsed)
_CACHE: dict[pathlib.Path, tuple[int, int, Any]] = {}


def load(path: pathlib.Path, *, source: str) -> Any:
    """读一个 JSON 文档（带缓存）。不可用时抛 UpstreamError。"""
    p = pathlib.Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        raise UpstreamError(
            "upstream_missing",
            f"{source} 的产出文件不存在：{p}。"
            f"该线的生成器还没跑过，或路径配置不对",
            source=source) from None
    except OSError as exc:
        raise UpstreamError("upstream_unreadable", f"{source} 读不动：{exc}",
                            source=source) from None

    key = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(p)
    if hit and (hit[0], hit[1]) == key:
        return hit[2]

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # 生成器正在覆写时可能读到半截 —— 不缓存失败结果，下次再试
        raise UpstreamError("upstream_invalid", f"{source} 不是合法 JSON：{exc}",
                            source=source) from None

    _CACHE[p] = (st.st_mtime_ns, st.st_size, data)
    return data


def fresh_at(path: pathlib.Path) -> str | None:
    """文件的最后修改时间（ISO8601 UTC）。前端用它显示数据陈旧度。"""
    try:
        ts = pathlib.Path(path).stat().st_mtime
    except OSError:
        return None
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts, _dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
