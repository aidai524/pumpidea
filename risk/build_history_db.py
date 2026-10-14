#!/usr/bin/env python3
"""把 HF 数据集落成创作者历史库（SQLite），供在线评分 O(1) 查询。

输出 risk/history.sqlite3：
  creators(creator PK, n, resolved, rugs, grads, rug_rate, grad_rate,
           first_t0, last_t0, last_rug_t0)
"""
from __future__ import annotations

import pathlib
import sqlite3

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
DB = ROOT / "history.sqlite3"


def main() -> None:
    cols = ["creator", "t0", "rugged", "graduated", "quote_asset", "mayhem"]
    frames = []
    for sub in ("launches_legacy", "launches"):
        for f in sorted((DATA / sub).glob("*.parquet")):
            frames.append(pd.read_parquet(f, columns=cols))
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["quote_asset"] == "sol") & (df["mayhem"] == 0)]
    df["resolved"] = df["rugged"].notna()
    df["rug"] = df["rugged"].fillna(0).astype(int)
    df["grad"] = df["graduated"].fillna(0).astype(int)
    df["last_rug_t0"] = df["t0"].where(df["rug"] == 1)

    g = df.groupby("creator").agg(
        n=("t0", "size"), resolved=("resolved", "sum"),
        rugs=("rug", "sum"), grads=("grad", "sum"),
        first_t0=("t0", "min"), last_t0=("t0", "max"),
        last_rug_t0=("last_rug_t0", "max"))
    g["rug_rate"] = (g["rugs"] / g["resolved"].where(g["resolved"] > 0, 1)).round(4)
    g["grad_rate"] = (g["grads"] / g["resolved"].where(g["resolved"] > 0, 1)).round(4)

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE creators(
          creator TEXT PRIMARY KEY, n INTEGER, resolved INTEGER,
          rugs INTEGER, grads INTEGER, rug_rate REAL, grad_rate REAL,
          first_t0 INTEGER, last_t0 INTEGER, last_rug_t0 INTEGER);
        CREATE INDEX idx_rug_rate ON creators(rug_rate);
    """)
    g.reset_index().to_sql("creators", con, if_exists="append", index=False)
    con.commit()
    n = con.execute("select count(*) from creators").fetchone()[0]
    size = DB.stat().st_size / 1e6
    print(f"写了 {DB}：{n:,} 个创建者，{size:.1f} MB")
    print(g[["n", "resolved", "rug_rate"]].describe().round(2).to_string())


if __name__ == "__main__":
    main()
