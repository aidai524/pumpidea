#!/usr/bin/env python3
"""汇总流式费用事件：日/小时 × quote 资产 → 定价 → 双口径报告（JSON + CSV）。

定价策略（为小时级任务优化）：
  - 持久缓存 data/price_cache.json / decimals_cache.json（mint 级，价格 24h 过期）
  - 只给事件数 top-N 的 mint 定价（默认 600），长尾记为 unpriced
  - 并发抓取（默认 8 线程 + 全局限速）

口径：all = 全部可定价；liq = 最优交易对流动性 ≥ min_liquidity。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import pathlib
import shutil
import sqlite3
import threading
import time
import urllib.request
from collections import defaultdict

from rpc import make_client

ROOT = pathlib.Path(__file__).resolve().parent
DB = ROOT / "runtime" / "stream.sqlite3"
PRICE_CACHE = ROOT / "data" / "price_cache.json"
DEC_CACHE = ROOT / "data" / "decimals_cache.json"
# 小时桶缓存（转 USD 之前的原始费用和）。有了它，每轮只重算最近一段窗口，
# 而不是把整个保留期重算一遍 —— 见 buckets() 的说明。
AGG_CACHE = ROOT / "data" / "agg_cache.json"
PRICE_TTL = 86400
RECOMPUTE_HOURS = 48.0

NATIVE = "11111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
FIXED = {NATIVE, WSOL, USDC}
LINES = ["protocol_fee", "creator_fee", "buyback_fee", "lp_fee",
         "cashback", "holder_rewards"]
TRADE_EVENTS = ("BuyEvent", "SellEvent", "TradeEvent")
# 聚合窗口，由 set_window() 在 report() 里按 --days 设定。
# 默认与保留期一致（deploy/periodic/pumpfun-retention 的 @RETENTION_DAYS@）。
# 这个窗口是**守卫**，不是提速手段：保留期正常时库里本来就只有 7 天数据，窗口
# 等于全表。它的用处是保留任务一旦失效、库无限增长时，聚合成本仍有上界。
RETENTION_DAYS = 7.0
TS_MIN, TS_MAX = 1_600_000_000, 2_000_000_000
HTTP = None
PRICES: dict[str, dict] = {}
DECS: dict[str, int] = {}
_lock = threading.Lock()
_last_req = [0.0]


def get_json(url: str, timeout: int = 20) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pulse-audit/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def sol_price() -> float:
    d = get_json("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
    try:
        return float(d["solana"]["usd"])
    except Exception:  # noqa: BLE001
        return 0.0


def _throttle(rate: float) -> None:
    with _lock:
        wait = rate - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


MAJOR_QUOTES = {WSOL, USDC, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}  # SOL/USDC/USDT


def _wmedian(samples: list[tuple[float, float]]) -> float:
    """按流动性加权的价格中位数。"""
    samples = sorted(samples)
    total = sum(w for _, w in samples) or 1.0
    acc = 0.0
    for price, w in samples:
        acc += w
        if acc >= total / 2:
            return price
    return samples[-1][0]


def fetch_price(mint: str) -> dict:
    """定价 v2：top5 交易对按流动性加权中位数，偏好主流计价对，记录离散度。"""
    d = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    out = {"price": None, "liq": None, "pairs": 0, "major": False, "dispersion": None}
    if not (d and d.get("pairs")):
        return out

    def liq_usd(p):
        try:
            return float((p.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    pairs = sorted(d["pairs"], key=liq_usd, reverse=True)[:5]
    usable = []
    for p in pairs:
        try:
            price = float(p["priceUsd"])
        except (KeyError, TypeError, ValueError):
            continue
        quote = ((p.get("quoteToken") or {}).get("address") or "")
        usable.append((price, max(liq_usd(p), 1.0), quote in MAJOR_QUOTES))
    if not usable:
        return out
    majors = [u for u in usable if u[2]]
    chosen = majors or usable
    out["price"] = _wmedian([(pr, w) for pr, w, _ in chosen])
    out["liq"] = max(liq_usd(p) for p in pairs)
    out["pairs"] = len(usable)
    out["major"] = bool(majors)
    prices = [pr for pr, _, _ in chosen]
    if min(prices) > 0:
        out["dispersion"] = round(max(prices) / min(prices), 2)
    return out


def fetch_decimals(mint: str) -> int:
    res = HTTP.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    try:
        return int(res["value"]["data"]["parsed"]["info"]["decimals"])
    except Exception:  # noqa: BLE001
        return 9


def prepare(mints: list[str], workers: int, rate: float) -> None:
    """并发补齐价格/精度缓存（mint 级一次）。"""
    now = int(time.time())
    for m in FIXED:
        PRICES.setdefault(m, {"price": None, "liq": None, "at": 0})
    todo_p = [m for m in mints if m not in FIXED
              and (m not in PRICES or now - PRICES[m].get("at", 0) > PRICE_TTL)]
    todo_d = [m for m in mints if m not in DECS]

    def work(m: str):
        _throttle(rate)
        return m, fetch_price(m), fetch_decimals(m)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for m, price, dec in ex.map(work, todo_p):
            PRICES[m] = {**price, "at": now}
            DECS.setdefault(m, dec)
            done += 1
            if done % 50 == 0:
                print(f"  抓取价格/精度 {done}/{len(todo_p)}", flush=True)
    for m in todo_d:
        DECS.setdefault(m, 9)
    if todo_p:
        print(f"  新抓取 {len(todo_p)} 个 mint 的价格", flush=True)


def unit_usd(mint: str, sol: float) -> tuple[float | None, bool]:
    """返回 (每个 raw unit 的 USD, 是否流动性达标)。"""
    if mint in (WSOL, NATIVE):
        return sol / 1e9, True
    if mint == USDC:
        return 1.0 / 1e6, True
    info = PRICES.get(mint) or {}
    if info.get("price") is None:
        return None, False
    return info["price"] / (10 ** DECS.get(mint, 9)), (info.get("liq") or 0) >= MIN_LIQ[0]


MIN_LIQ = [50000.0]


def set_window(days: float) -> None:
    global TS_MIN, TS_MAX
    now = int(time.time())
    TS_MIN = now - int(days * 86400)
    TS_MAX = now + 3600          # 留 1 小时余量：容忍轻微时钟漂移


def temp_dir(con: sqlite3.Connection) -> pathlib.Path:
    """把排序溢出的临时文件放到**和库同一个卷**上，并返回实际生效的目录。

    2026-10-19 02:06 的事故：去重排序的临时文件写到了根分区（42GB 空闲），
    6 分钟写满，报 `database or disk is full` —— 而库在 /mnt 的大卷上（70GB 空闲）。
    SQLite 默认的临时目录（/var/tmp → /usr/tmp → /tmp）全在根分区。

    **必须用 PRAGMA**：环境变量 `SQLITE_TMPDIR` 在本机与 VPS 上都没生效
    （实测：设了它之后 `df /` 仍在 4.5GB/分钟地涨，`df /mnt` 不动）。
    PRAGMA 是全局状态（不是每连接），所以开连接后立即设一次，并回读校验。
    """
    d = DB.parent / ".tmp"
    try:
        d.mkdir(parents=True, exist_ok=True)
        con.execute("PRAGMA temp_store_directory = '%s'" % str(d).replace("'", "''"))
    except (OSError, sqlite3.Error):
        pass
    got = con.execute("PRAGMA temp_store_directory").fetchone()
    return pathlib.Path(got[0]) if got and got[0] else pathlib.Path("/tmp")


def aggregate(con: sqlite3.Connection, ts_from: int | None = None,
              ts_to: int | None = None) -> list[dict]:
    """聚合出**小时件**（原始费用和，未转 USD）。窗口可指定。

    成本全在那次 `ROW_NUMBER()` 的去重排序上（不是读盘：实测盘读 255MB/s，
    22GB 扫两遍只要 ~3 分钟；而近 24h 的 1200 万行做一次去重排序要 2.8 分钟），
    而且库里有 46% 是重复行。三处针对它的改动：

      1. 只扫一遍（原来日/小时各排一次序）。
      2. 子查询**不用 `*`**：临时排序记录只带用到的列。带 `*` 时 5700 万行
         的临时文件会写到几十 GB —— 2026-10-19 02:06 那一轮就是这样把根分区
         写满、报 `database or disk is full` 的。
      3. 默认只算最近 `RECOMPUTE_HOURS`（见 `buckets()`），不重算整个窗口。

    去重仍在分桶之前做（`rn=1` 在子查询里）。
    """
    cols = ", ".join(f"total({k}) {k}" for k in LINES)
    keep = ", ".join(("signature", "name", "COALESCE(pool, '') AS pool", "ts",
                      "quote_mint", *LINES))
    rows = con.execute(f"""
        SELECT period, quote_mint, {cols}, count(*) n
        FROM (
          SELECT {keep},
                 strftime('%Y-%m-%dT%H:00', ts, 'unixepoch') AS period,
                 ROW_NUMBER() OVER (
                   PARTITION BY signature, name, COALESCE(pool, '')
                   ORDER BY rowid) AS rn
          FROM events
          WHERE ts BETWEEN ? AND ? AND quote_mint IS NOT NULL
            AND name IN ({','.join('?' * len(TRADE_EVENTS))})
        )
        WHERE rn = 1
        GROUP BY period, quote_mint
    """, (TS_MIN if ts_from is None else ts_from,
          TS_MAX if ts_to is None else ts_to, *TRADE_EVENTS)).fetchall()
    return [{"period": r["period"], "quote_mint": r["quote_mint"],
             **{k: r[k] for k in LINES}, "n": r["n"]} for r in rows]


def _hour_key(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:00", time.gmtime(ts))


def _load_cache() -> dict | None:
    try:
        d = json.loads(AGG_CACHE.read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("hours"), dict) else None


def buckets(con: sqlite3.Connection) -> tuple[list[dict], list[dict], dict]:
    """小时桶 → 日桶（日 = 小时之和），**只重算最近一段窗口**。

    为什么需要这个：全窗口聚合实测 45~50 分钟，而调度是每小时一次 —— 任务
    80% 的时间都在持读快照，WAL 因此拿不到 checkpoint 的机会（见 decisions.md）。
    而走之前重算的单窗口在这里没有任何价值：历史小时除非重跑否则不会变。

    做法：小时桶缓存在 `data/agg_cache.json`（`小时 → {quote_mint: [费用…, n]}`，
    是**转 USD 之前**的原始和，所以价格基准始终是本次运行的那一个，不会混）。
    每轮只重算最近 `RECOMPUTE_HOURS`（48h，外加 1h 重叠），更早的小时直接用缓存；
    缓存缺失、过期或没盖到窗口起点 → 回落到全窗口（慢路径，会写在日志里）。

    代价（必须知道）：去重是在每个查询内部完成的，所以**跨重算边界（相差一个月）、
    同一 (signature, name, pool) 的重复行**理论上会被两边各计一次。实际上重复行
    是同一笔交易的两次写入、时间戳相同，相差不到一小时；用 1 小时重叠把这个风险
    推到「同一签名跨过一个整点」这种情形上。
    """
    now = int(time.time())
    recent_from = max(
        TS_MIN, ((now - int(RECOMPUTE_HOURS * 3600)) // 3600) * 3600)
    overlap_from = max(TS_MIN, recent_from - 3600)

    cache = _load_cache()
    hours: dict[str, dict[str, list]] | None = None
    mode = "全窗口（缓存缺失 / 过期 / 没盖到窗口起点）"
    # 缓存的「起点」该与谁比？比窗口起点（TS_MIN）是错的：库里往往没有
    # 7 天数据（保留期是 7 天，但采集从 N 天前才开始），此时缓存永远"盖不到
    # 窗口起点"，每轮都回落全窗口 —— 2026-10-19 第一版就栽在这里（库只有
    # 4.9 天，于是缓存建好了却从来没用上）。正确的问题是：**比库里最早的数据
    # 还早吗**。min(ts) 走 idx_events_ts，是一次索引查找。
    db_min = con.execute("SELECT min(ts) FROM events").fetchone()[0] or TS_MIN
    floor_hour = _hour_key(max(TS_MIN, db_min))
    if cache:
        age_s = now - int(cache.get("saved_at") or 0)
        cached = cache["hours"]
        if age_s <= int(RECOMPUTE_HOURS * 3600) and cached and min(cached) <= floor_hour:
            hours = {h: v for h, v in cached.items() if h < _hour_key(overlap_from)}
            mode = f"增量（重算最近 {RECOMPUTE_HOURS:g}h）"

    recent = aggregate(con, TS_MIN if hours is None else overlap_from, TS_MAX)
    if hours is None:
        hours = {}
    for row in recent:
        hours.setdefault(row["period"], {})[row["quote_mint"]] = [
            row[k] for k in LINES] + [row["n"]]

    # 窗口向前滑动时把掉出去的小时剪掉，缓存不会无限长。
    first_hour = _hour_key(TS_MIN)
    hours = {h: v for h, v in hours.items() if h >= first_hour}
    AGG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    AGG_CACHE.write_text(json.dumps({"saved_at": now, "hours": hours},
                                    ensure_ascii=False))

    hourly_rows: list[dict] = []
    days: dict[tuple[str, str], dict] = {}
    for h in sorted(hours):
        for qm, vals in hours[h].items():
            hourly_rows.append({"period": h, "quote_mint": qm,
                                **{k: vals[i] for i, k in enumerate(LINES)},
                                "n": int(vals[-1])})
            key = (h[:10], qm)
            d = days.get(key)
            if d is None:
                d = days[key] = {"period": key[0], "quote_mint": qm,
                                 **{k: 0.0 for k in LINES}, "n": 0}
            for i, k in enumerate(LINES):
                d[k] += vals[i] or 0.0
            d["n"] += int(vals[-1])
    info = {"mode": mode, "recompute_hours": RECOMPUTE_HOURS,
            "recomputed_from": recent_from, "hours": len(hours),
            "rows": len(hourly_rows)}
    return list(days.values()), hourly_rows, info


def accumulate(rows, sol: float) -> dict:
    out: dict[str, dict] = defaultdict(
        lambda: {k: 0.0 for k in LINES}
        | {f"{k}_liq": 0.0 for k in LINES}
        | {"total": 0.0, "total_liq": 0.0, "n": 0,
           "unpriced_mints": set(), "illiquid_mints": set()})
    for r in rows:
        cu, liq_ok = unit_usd(r["quote_mint"], sol)
        d = out[r["period"]]
        d["n"] += r["n"]
        if cu is None:
            d["unpriced_mints"].add(r["quote_mint"])
            continue
        if not liq_ok:
            d["illiquid_mints"].add(r["quote_mint"])
        for k in LINES:
            usd = (r[k] or 0.0) * cu
            d[k] += usd
            d["total"] += usd
            if liq_ok:
                d[f"{k}_liq"] += usd
                d["total_liq"] += usd
    return out


def health(con: sqlite3.Connection) -> dict:
    # ⛔ INDEXED BY 不是装饰：不加时同一个 count 实测 78s，加了 4.7s（60M 行）。
    # 这条查询在每轮报表里只跑一次，但 78s 里大段时间持有读快照。
    n, mn, mx = con.execute(
        "SELECT count(*), min(ts), max(ts) FROM events INDEXED BY idx_events_ts "
        "WHERE ts BETWEEN ? AND ?", (TS_MIN, TS_MAX)).fetchone()
    now = int(time.time())
    recent = con.execute("SELECT count(*) FROM events WHERE ts > ?", (now - 600,)).fetchone()[0]
    return {"events": n, "first_ts": mn, "last_ts": mx,
            "last_age_s": (now - mx) if mx else None,
            "last_10min_events": recent}


def write_csv(path: pathlib.Path, daily: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "events"] + LINES + ["total"]
                   + [f"{k}_liq" for k in LINES] + ["total_liq",
                     "unpriced_mints", "illiquid_mints"])
        for day in sorted(daily):
            d = daily[day]
            w.writerow([day, d["n"]]
                       + [round(d[k], 2) for k in LINES] + [round(d["total"], 2)]
                       + [round(d[f"{k}_liq"], 2) for k in LINES]
                       + [round(d["total_liq"], 2),
                          len(d["unpriced_mints"]), len(d["illiquid_mints"])])


def report(compare: bool, top: int, min_liq: float, max_mints: int,
           workers: int, rate: float, days: float = RETENTION_DAYS) -> None:
    if not DB.exists():
        raise SystemExit("没有 runtime/stream.sqlite3，先跑 run_stream.sh")
    t_start = time.time()
    set_window(days)
    MIN_LIQ[0] = min_liq
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    tmp = temp_dir(con)
    # 排序是这条查询的唯一瓶颈（实测：24h 的 1200 万行做一次去重排序 2.8 分钟）。
    # 默认 cache_size 只有 8MB，1100 万条排序记录会被切成上千个临时 run 再多趟归并，
    # 归并的读写量随趟数指数上涨 —— 这是「45 分钟」的真正来源。
    # 256MB 页缓存 + 2 个排序工作线程（机器只有 2 核）把 run 数压下来。
    con.execute("PRAGMA cache_size = -262144")
    con.execute("PRAGMA threads = 2")
    print(f"临时目录 {tmp}（{shutil.disk_usage(tmp).free / 2**30:.1f} GiB 空闲）", flush=True)
    PRICES.update(json.loads(PRICE_CACHE.read_text()) if PRICE_CACHE.exists() else {})
    DECS.update(json.loads(DEC_CACHE.read_text()) if DEC_CACHE.exists() else {})
    sol = sol_price()

    daily_rows, hourly_rows, binfo = buckets(con)
    t_agg = time.time() - t_start
    # 只按小时桶统计（日桶是小时之和，两边相加会重复计一遍）。
    # 用途只是给 top-N 定价排优先级，所以排序口径不受影响。
    counts: dict[str, int] = defaultdict(int)
    for r in hourly_rows:
        counts[r["quote_mint"]] += r["n"]
    chosen = sorted(counts, key=lambda m: -counts[m])[:max_mints]
    prepare(chosen, workers, rate)
    t_price = time.time() - t_start - t_agg

    daily = accumulate(daily_rows, sol)
    hourly = accumulate(hourly_rows, sol)
    t_a = time.time()
    h = health(con)
    t_health = time.time() - t_a
    print(f"价格基准：SOL ${sol:.2f}；{len(daily)} 天 / {len(hourly)} 小时；"
          f"事件 {h['events']:,}（最新 {h['last_age_s']}s 前）；"
          f"定价 mint {len(chosen)}/{len(counts)}")
    # 分段耗时必须进日志：WAL 风险取决于这个任务持读快照多久，
    # 没这行就只能靠猜（曾经把 I/O 当瓶颈，实际是去重排序）。
    # ⚠️ 这里不能打 t_meta：它在下面的元信息阶段才赋值（第 ~491 行），
    # 提前引用会 UnboundLocalError —— 2026-10-23 实测就是它在最后一步崩掉，
    # 导致 stream_report.json 三个月没更新（聚合和定价其实都跑完了）。
    # 元信息耗时仍然写进 JSON 的 elapsed_s.meta，只是不打这一行。
    print(f"窗口 {days:g} 天（{TS_MIN}..{TS_MAX}）｜聚合 {t_agg:.1f}s，"
          f"定价 {t_price:.1f}s，health {t_health:.1f}s"
          f"｜{binfo['mode']}，小时桶 {binfo['hours']}，"
          f"从 {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime(binfo['recomputed_from']))} 起重算",
          flush=True)
    head = (f"{'period':21} {'events':>9} {'protocol':>11} {'buyback':>11} "
            f"{'creator':>11} {'lp':>11} {'total':>12} {'liquid':>12}")
    print(head)
    print("-" * len(head))
    for day in sorted(daily):
        d = daily[day]
        print(f"{day:21} {d['n']:>9} {d['protocol_fee']:>11,.0f} {d['buyback_fee']:>11,.0f} "
              f"{d['creator_fee']:>11,.0f} {d['lp_fee']:>11,.0f} {d['total']:>12,.0f} "
              f"{d['total_liq']:>12,.0f}")

    t_m = time.time()   # 元信息段：官方看板 + fee 程序计数 + DefiLlama
    official = None
    try:
        from fetch_official import load_or_fetch
        official = load_or_fetch()
    except Exception:  # noqa: BLE001
        official = None
    if official and official.get("annualized_revenue_m"):
        print(f"  官方看板: 年化 ${official['annualized_revenue_m']}M"
              f"（日均 ${official['daily_avg_m']}M）| 最新日回购 "
              f"${official['daily_buyback_k']}K | 数据截至 {official.get('data_as_of')}")

    # 其他收入线：fee 程序（social/donation/sweep 等）活动计数（IDL 事件无字段）。
    # 只统计最近 24h：没有 (program, ts) 索引时，按 program 过滤要扫整个窗口的
    # 行 —— 实测这一条占了「聚合完成之后」那 4.5 分钟里的大头。
    # 这些是活动计数、不是收入，24h 窗口足够说明"这条线还在动"。
    fee_from = max(TS_MIN, int(time.time()) - 24 * 3600)
    fee_events = {r[0]: r[1] for r in con.execute(
        "SELECT name, count(*) FROM events INDEXED BY idx_events_ts "
        "WHERE program='fees' AND ts BETWEEN ? AND ? "
        "GROUP BY name ORDER BY count(*) DESC", (fee_from, TS_MAX)).fetchall()}
    if fee_events:
        print(f"  其他收入线活动（近 24h）：{fee_events}")

    # 定价质量：主流计价对比例 / 离散度 / 未定价
    priced = [m for m in chosen if (PRICES.get(m) or {}).get("price") is not None]
    pricing_quality = {
        "chosen": len(chosen), "priced": len(priced),
        "major_quote": sum(1 for m in priced if (PRICES.get(m) or {}).get("major")),
        "high_dispersion": sum(1 for m in priced
                               if ((PRICES.get(m) or {}).get("dispersion") or 0) > 3),
    }
    print(f"  定价质量：{pricing_quality['priced']}/{len(chosen)} 可定价，"
          f"{pricing_quality['major_quote']} 来自主流计价对，"
          f"{pricing_quality['high_dispersion']} 离散>3×")

    dl_cmp: dict = {}
    if compare:
        for slug in ("pump.fun", "pumpswap"):
            d = get_json(f"https://api.llama.fi/summary/fees/{slug}?dataType=dailyRevenue")
            if d:
                dl_cmp[slug] = {k: d.get(k) for k in ("total24h", "total7d", "total30d")}
                print(f"  DefiLlama {slug}: 24h ${d['total24h']/1e6:.2f}M | "
                      f"7d ${d['total7d']/1e6:.2f}M | 30d ${d['total30d']/1e6:.2f}M")

    t_meta = time.time() - t_m

    def clean(o):
        if isinstance(o, set):
            return len(o)
        raise TypeError

    mint_usd: dict[str, float] = defaultdict(float)
    for r in daily_rows:
        cu, _ = unit_usd(r["quote_mint"], sol)
        if cu is None:
            continue
        for k in LINES:
            mint_usd[r["quote_mint"]] += (r[k] or 0.0) * cu

    out = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {"days": days, "from": TS_MIN, "to": TS_MAX},
        "aggregation": binfo,
        "elapsed_s": {"aggregate": round(t_agg, 1),
                       "pricing": round(t_price, 1),
                       "health": round(t_health, 1),
                       "meta": round(t_meta, 1),
                       "total": round(time.time() - t_start, 1)},
        "sol_usd": sol, "min_liquidity": min_liq, "health": h,
        "priced_mints": len(chosen), "total_mints": len(counts),
        "daily": {d: json.loads(json.dumps(v, default=clean))
                  for d, v in sorted(daily.items())},
        "hourly": [{"hour": k, **json.loads(json.dumps(v, default=clean))}
                   for k, v in sorted(hourly.items())],
        "top_mints": [{"mint": m, "usd": round(u, 2)}
                      for m, u in sorted(mint_usd.items(), key=lambda x: -x[1])[:top]],
        "defillama": dl_cmp,
        "official": official,
        "pricing_quality": pricing_quality,
        "fee_events": fee_events,
        "fee_events_window_h": 24,
    }
    PRICE_CACHE.write_text(json.dumps(PRICES, indent=1))
    DEC_CACHE.write_text(json.dumps(DECS, indent=1))
    (ROOT / "stream_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    write_csv(ROOT / "stream_report.csv", daily)
    print(f"写了 {ROOT/'stream_report.json'} 和 {ROOT/'stream_report.csv'}")


def main() -> None:
    global HTTP, RECOMPUTE_HOURS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-liquidity", type=float, default=50000)
    ap.add_argument("--max-mints", type=int, default=600, help="最多给多少个 mint 定价")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=0.12, help="外部价格请求最小间隔秒")
    ap.add_argument("--days", type=float, default=RETENTION_DAYS,
                    help="聚合窗口天数，默认与保留期一致（"
                         f"{RETENTION_DAYS:g}）——低于保留期会少算，高于保留期没有数据")
    ap.add_argument("--recompute-hours", type=float, default=RECOMPUTE_HOURS,
                    help="每轮重算多少小时（更早的沿用缓存；默认 "
                         f"{RECOMPUTE_HOURS:g}，必须 ≥ 调度间隔且 > 采集可能的断线时长）")
    ap.add_argument("--rpc", help="覆盖 RPC（默认 .env 里的 ALCHEMY_RPC_URL）")
    args = ap.parse_args()
    RECOMPUTE_HOURS = args.recompute_hours
    HTTP = make_client(cli=args.rpc, rate=0.02)
    report(args.compare, args.top, args.min_liquidity, args.max_mints,
           args.workers, args.rate, args.days)


if __name__ == "__main__":
    main()
