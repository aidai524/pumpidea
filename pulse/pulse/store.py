"""SQLite 存储层：Pulse demo 的单一事实源。

只用标准库。三张业务表：
  graduations  毕业事件（loopholetape /v1/graduations 的 rows，按 mint upsert）
  counts       每次毕业窗口的聚合数字（KPI 条）
  radar        实时候选（/v1/radar 的 top_rug_risk / top_graduation，按 mint 保最新）
  stats        每日统计快照（/v1/stats/pumpfun，低频）
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import time

RUNTIME = pathlib.Path(__file__).resolve().parent.parent / "runtime"

# 保留策略（2026-10-23 加的：pulse 库一度涨到 1.9G，全是 counts 的冗余快照）
COUNTS_KEEP = 200        # 只留最近 200 次 KPI 快照（站点只读最新一行）
RADAR_KEEP_DAYS = 7      # radar 只留最近 7 天还见过的代币

SCHEMA = """
CREATE TABLE IF NOT EXISTS graduations (
    mint TEXT PRIMARY KEY,
    symbol TEXT, name TEXT,
    launched_at TEXT, t0 REAL, graduated_at TEXT,
    seconds_to_graduation REAL, timing_seen INTEGER,
    label TEXT, label_text TEXT,
    peak_curve_sol REAL, mayhem INTEGER,
    ticker TEXT, ticker_copies INTEGER,
    pool_30m TEXT, open_pumpfun TEXT, record TEXT, record_json TEXT,
    first_seen REAL, last_seen REAL
);
CREATE TABLE IF NOT EXISTS counts (
    generated_at TEXT PRIMARY KEY, ts REAL, json TEXT
);
CREATE TABLE IF NOT EXISTS radar (
    mint TEXT, source TEXT,
    first_seen REAL, last_seen REAL, seen_count INTEGER,
    name TEXT, symbol TEXT, age_s REAL, rs_sol REAL, progress REAL,
    n_buys INTEGER, unique_buyers_60s INTEGER,
    top5_share REAL, dev_share REAL, p_rug REAL, p_grad REAL,
    flags TEXT, json TEXT,
    PRIMARY KEY (mint, source)
);
CREATE TABLE IF NOT EXISTS stats (
    generated_at TEXT PRIMARY KEY, ts REAL, json TEXT
);
CREATE INDEX IF NOT EXISTS idx_grad_launched ON graduations(t0 DESC);
CREATE INDEX IF NOT EXISTS idx_grad_label ON graduations(label);
"""


def db_path() -> pathlib.Path:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    return RUNTIME / "pulse.sqlite3"


def connect(*, readonly: bool = False) -> sqlite3.Connection:
    """打开 pulse.sqlite3。

    ⚠️ 2026-10-23 事故：`pumpfun-pulse-builder` 在 VPS 上反复因此挂掉——
    它读这个库的同时 collector 在写，SQLite 默认的 DELETE journal 模式下
    **读会被写挡住**，于是 `sqlite3.OperationalError: database is locked`，
    builder 崩了 5 次、超过 OpenRC 的 respawn 上限后**永久停止**，
    `site/data.json` 静默地停在 1 天前。

    两个修正：
      1. **只读者用 `mode=ro`**（builder 只读，没必要跟 collector 抢写锁）
      2. **超时从默认 5 秒提到 10 秒**（写入侧瞬时锁竞争不应立刻报错）
    另外这个库应该跑在 **WAL** 模式下（读不阻塞写、写不阻塞读），
    一次性切换：`sqlite3 pulse/runtime/pulse.sqlite3 "PRAGMA journal_mode=WAL;"`
    （不要写在 connect() 里——切 journal_mode 需要短暂排他锁，
     在 collector 正在写的时候执行会自己撞上「database is locked」。）
    """
    path = db_path()
    if readonly and path.exists():
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
        con.row_factory = sqlite3.Row
        return con
    con = sqlite3.connect(path, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------- 写入

def upsert_graduations(con: sqlite3.Connection, rows: list[dict]) -> int:
    ts = time.time()
    payload = []
    for r in rows:
        if not r.get("mint"):
            continue
        pool = r.get("pool_30m")
        open_on = r.get("open_on") or {}
        payload.append((
            r["mint"], r.get("symbol"), r.get("name"),
            r.get("launched_at"), r.get("t0"), r.get("graduated_at"),
            r.get("seconds_to_graduation"),
            1 if r.get("timing_seen") else 0,
            r.get("label"), r.get("label_text"),
            r.get("peak_curve_sol"), 1 if r.get("mayhem") else 0,
            r.get("ticker"), r.get("ticker_copies_launch_week"),
            json.dumps(pool, ensure_ascii=False) if pool else None,
            open_on.get("pumpfun"), r.get("record"), r.get("record_json"),
            ts, ts,
        ))
    con.executemany(
        """
        INSERT INTO graduations (mint,symbol,name,launched_at,t0,graduated_at,
            seconds_to_graduation,timing_seen,label,label_text,peak_curve_sol,mayhem,
            ticker,ticker_copies,pool_30m,open_pumpfun,record,record_json,first_seen,last_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(mint) DO UPDATE SET
            symbol=excluded.symbol, name=excluded.name,
            graduated_at=excluded.graduated_at,
            seconds_to_graduation=excluded.seconds_to_graduation,
            timing_seen=excluded.timing_seen,
            label=excluded.label, label_text=excluded.label_text,
            peak_curve_sol=excluded.peak_curve_sol, mayhem=excluded.mayhem,
            ticker=excluded.ticker, ticker_copies=excluded.ticker_copies,
            pool_30m=COALESCE(excluded.pool_30m, graduations.pool_30m),
            open_pumpfun=COALESCE(excluded.open_pumpfun, graduations.open_pumpfun),
            record=excluded.record, record_json=excluded.record_json,
            last_seen=excluded.last_seen
        """,
        payload,
    )
    con.commit()
    return len(payload)


def save_counts(con: sqlite3.Connection, data: dict) -> None:
    gen = data.get("generated_at")
    if not gen:
        return
    con.execute(
        "INSERT OR REPLACE INTO counts (generated_at, ts, json) VALUES (?,?,?)",
        (gen, data.get("t") or time.time(), json.dumps(data, ensure_ascii=False)),
    )
    # ⚠️ 每条 counts 存的是**整个 payload**（含全部 stories 与 tape），实测约 320KB/行。
    # builder 每 30 秒写一次 → **约 900MB/天**，而站点只读最新一行（latest_counts）。
    # 2026-10-23 在 VPS 上实测：1.9G 的库里 1.89G 全是这张表的冗余快照。
    # 不清理就必然把磁盘吃满 —— 这和 audit 的 WAL 是同一类问题：没有保留策略。
    con.execute(
        "DELETE FROM counts WHERE generated_at NOT IN "
        "(SELECT generated_at FROM counts ORDER BY ts DESC LIMIT ?)",
        (COUNTS_KEEP,),
    )
    # radar 同理：只保留最近还见过的代币（按 last_seen 剪枝）
    con.execute("DELETE FROM radar WHERE last_seen < ?",
                (time.time() - RADAR_KEEP_DAYS * 86400,))
    con.commit()


def upsert_radar(con: sqlite3.Connection, rows: list[dict], source: str) -> int:
    ts = time.time()
    payload = []
    for r in rows:
        if not r.get("mint"):
            continue
        probs = r.get("probabilities") or {}
        flags = r.get("flags") or []
        payload.append((
            r["mint"], source, ts, ts,
            r.get("name"), r.get("symbol"), r.get("age_s"), r.get("rs_sol"),
            r.get("progress"), r.get("n_buys"), r.get("unique_buyers_60s"),
            r.get("top5_share"), r.get("dev_share"),
            probs.get("rug_within_300s"), probs.get("true_graduation"),
            ",".join(flags), json.dumps(r, ensure_ascii=False),
        ))
    con.executemany(
        """
        INSERT INTO radar (mint,source,first_seen,last_seen,seen_count,name,symbol,
            age_s,rs_sol,progress,n_buys,unique_buyers_60s,top5_share,dev_share,
            p_rug,p_grad,flags,json)
        VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(mint,source) DO UPDATE SET
            last_seen=excluded.last_seen, seen_count=radar.seen_count+1,
            age_s=excluded.age_s, rs_sol=excluded.rs_sol, progress=excluded.progress,
            n_buys=excluded.n_buys, unique_buyers_60s=excluded.unique_buyers_60s,
            top5_share=excluded.top5_share, dev_share=excluded.dev_share,
            p_rug=excluded.p_rug, p_grad=excluded.p_grad, flags=excluded.flags,
            json=excluded.json
        """,
        payload,
    )
    con.commit()
    return len(payload)


def save_stats(con: sqlite3.Connection, data: dict) -> None:
    gen = data.get("generated_at")
    if not gen:
        return
    con.execute(
        "INSERT OR REPLACE INTO stats (generated_at, ts, json) VALUES (?,?,?)",
        (gen, data.get("t") or time.time(), json.dumps(data, ensure_ascii=False)),
    )
    con.commit()


# ------------------------------------------------------------- 读取

def _row_to_grad(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["pool_30m"] = json.loads(d["pool_30m"]) if d["pool_30m"] else None
    return d


def recent_graduations(con: sqlite3.Connection, limit: int = 400) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM graduations ORDER BY t0 DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_grad(r) for r in rows]


def latest_counts(con: sqlite3.Connection) -> dict | None:
    row = con.execute("SELECT json FROM counts ORDER BY ts DESC LIMIT 1").fetchone()
    return json.loads(row["json"]) if row else None


def latest_radar(con: sqlite3.Connection, source: str, limit: int = 12) -> list[dict]:
    col = "p_rug DESC" if source == "top_rug_risk" else "p_grad DESC"
    rows = con.execute(
        f"SELECT * FROM radar WHERE source=? ORDER BY {col} LIMIT ?",
        (source, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def stats_summary(con: sqlite3.Connection) -> dict | None:
    row = con.execute("SELECT json FROM stats ORDER BY ts DESC LIMIT 1").fetchone()
    return json.loads(row["json"]) if row else None
