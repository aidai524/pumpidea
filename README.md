# pump.fun 发币经济研究

对 Solana 上最大 memecoin 发币平台 pump.fun 的**全量链上观察**，覆盖 2026-08-31 ~ 2026-10-07。

**结论见 [`report.md`](./report.md)。** 这里只写怎么复现、数据从哪来、以及为什么这么做。

## 一句话摘要

30 天 1,156,058 个新代币，名义毕业率 2.06%，但其中 **58% 是 2 秒内完成的机器人捆绑**，真实有机毕业率 **0.86%**；一半的币作者在 60 秒内就卖了自己那份；平台 30 天净收入 **$54.5M**，而**量的 76% 跑在一个只抽 0.05% 的产品上**。

## 数据从哪来

| 用途 | 来源 | 许可 / 费用 |
|---|---|---|
| 总体比率、日序列 | [loopholetape 日统计 API](https://api.loopholetape.com/stats/pumpfun) | 免费、无 key |
| 分布与创建者行为 | [loopholetape/pumpfun-launches](https://huggingface.co/datasets/loopholetape/pumpfun-launches)（1,082,101 行 × 43 列） | CC BY 4.0 |
| 费用 / 收入 / 交易量 | DefiLlama（`pump.fun` + `pumpswap`） | 免费 API |
| 费率机制 | pump.fun 官方文档 `docs/fees` | — |
| SOL 价格 | CoinGecko | 免费 |

**没有付任何费用。** treg 的 catalog 里没有 Solana/pump.fun 相关端点（搜过 7 个关键词，全空），所以这条研究不走 treg。

## 怎么复现

```bash
cd pumpfun

# 1. 建分析环境（pandas + pyarrow；**不要**装到 platform/ 里，
#    平台刻意不依赖 pandas，它的段位统计是 SQL 写的）
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r analysis/requirements.txt

# 2. 下载数据集（约 145 MB，无需 key）
./analysis/fetch_data.sh

# 3. 核对数据与文档声明是否一致（行数、列数、毕业率）
.venv/bin/python analysis/verify_data.py

# 4. 重算全部数字 → analysis/facts.json
.venv/bin/python analysis/analyze.py

# 5. 逐段喂 Jev 打分（10 次调用，需要 TYPESAFE_API_KEY）
.venv/bin/python analysis/jev_score.py
```

报告里的**每一个数字都来自 `analysis/facts.json`**，不手写。要改口径就改 `analyze.py`，然后报告里的引用点需要跟着核。

## 目录

```
pumpfun/
├── report.md          报告（交付物）
├── README.md          本文件
├── data/              下载的数据 + 第三方快照（见 report.md §8.3）
└── analysis/
    ├── requirements.txt
    ├── fetch_data.sh  下载（幂等，已有则跳过）
    ├── verify_data.py 完整性核对
    ├── explore.py     探索
    ├── analyze.py     全部计算 → facts.json
    ├── jev_score.py   段位打分 → jev_segments.json
    ├── facts.json     ★ 报告消费的唯一数字来源
    └── jev_segments.json
```

## 五个必须知道的方法论约束

写任何基于这份数据的结论前，先读 `report.md` §8.2。最短版：

1. **窗口只有 30~32 天**，不足以谈季节性或年度趋势
2. **`f10_*` 的抽样偏差只属于旧子集**——干净窗口（09-27 起）里它是逐币重放（`tape_replay`，占 99.74%），不是抽样；窗口内缺失的 6.6% 是 `create_lag_s > 1`，且缺失组的结局与完整组几乎一致
3. **2026-09-27 之前解码器漏了约 48% 的买单**，所以涉及时序的分析只用 09-27 之后的 5 天
4. **`rugged` 与 `graduated` 不互斥**（9.9% 兼有），"跑路率"不能算成 `1 − 毕业率`
5. **`rugged` 是观察规则，不是已验证的欺诈**——多数是创建者在小曲线上砸自己的盘

## 与平台（`../platform/`）的关系

**没有关系，这是刻意的。** 平台的分析层是为跨链 swap 定制的：`order_record` 表的字段是 `from_chain`/`to_chain`/`symbol`/`volume`，分段逻辑（`app/analysis/segments.py`）写死了四个"走廊"形状的分段键。pump.fun 的分析单元是**代币与创建者**，装不进那个模子。

要把它接进平台，需要新表 + 新分段模块 + 新任务 kind —— 那是一次架构改动（要写 spec），不是给现有流程打个补丁。本目录是独立的研究，不依赖平台运行，也不影响它。

## 引用

```
loopholetape, "pump.fun launches with outcomes", 2026,
https://huggingface.co/datasets/loopholetape/pumpfun-launches  (CC BY 4.0)
```
