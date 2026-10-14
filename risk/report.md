# 创作者/代币风险评分（③ 线）——离线验证与产品规格

**日期**：2026-10-14
**目标**：给 pump.fun 提供**上线 10 秒内可用的**风险分（跑路概率 / 毕业概率），
作为组件接进他们已有的界面（币页、Terminal、GO/直播审核、creator rewards），
而不是另做一个产品。

---

## 0. 一页结论

| 模型 | 目标 | 时间外 AUC | AP | Brier |
|---|---|---|---|---|
| 历史组（只看创建者过去行为） | 跑路 | 0.850（已知创建者子集 **0.923**） | 0.871 | 0.158 |
| 冷启动组（上线 10 秒特征） | 跑路 | 0.893 | 0.925 | 0.152 |
| 冷启动组 | 毕业 | **0.937** | 0.750 | 0.064 |
| **组合（历史 + 冷启动）** | **跑路** | **0.926** | 0.946 | 0.111 |
| **组合** | **毕业** | **0.945** | 0.754 | 0.063 |

**产品读法（组合模型，评估窗口 90,872 个币）**：

| 按风险分取 top | 精确率：这些币真的会跑路 | 覆盖：抓到全部跑路的比例 |
|---|---|---|
| 1% | **96.8%** | 1.6% |
| 5% | 98.1% | 8.0% |
| 10% | **98.3%** | 16.0% |

| 按毕业概率取 top | 精确率：这些币真的毕业 | 覆盖：抓到全部毕业的比例 |
|---|---|---|
| 1% | **100%** | 33.6% |
| 5% | 44.6%（基准 3.0%，**提升 15 倍**） | 74.9% |
| 10% | 24.2%（**8 倍**） | 81.3% |

> 一句话：**跑路可以提前标掉（top 10% 里 98% 会跑路），好币也能捞出来
> （top 1% 里 100% 真毕业）。**

---

## 1. 数据与方法

| | |
|---|---|
| 数据 | HF `pumpfun-launches` 全量：**746,208 个 classic 币**（2026-08-31 ~ 10-03，243,483 个创建者） |
| 标签 | `rugged`（300 秒内抽干/dev 砸盘，规则标签）与 `graduated`（真毕业） |
| 历史特征 | **扩张窗口**（只用该币之前的行为，无泄漏）：prior_n、prior_resolved、prior_rug_rate、prior_grad_rate、has_history |
| 冷启动特征 | 上线 10 秒内可得（干净窗口 204,456 行，覆盖 94.2%）：dev_share、dev_buy_sol、f10_insider_share、f10_bundle_wallets、f10_n_buys、f10_rs |
| 验证 | **按时间切分**（历史组：09-16 前训练 / 之后评估；冷启动与组合：10-01 前训练 / 10-01~10-03 评估） |
| 模型 | 标准化 + 逻辑回归（class_weight=balanced），可解释、可导出为纯 Python 评分 |

---

## 2. 特征贡献（组合模型跑路侧，标准化系数）

| 特征 | 系数 | 读法 |
|---|---|---|
| `dev_share` | **+4.90** | 创建者初始持仓比例越高，越危险（最强信号） |
| `dev_buy_sol` | **−7.94** | 创建者真金白银买得越多，越不危险 |
| `f10_rs` | −2.61 | 上线 10 秒曲线储备越高（真买盘），越安全 |
| `f10_insider_share` | +2.23 | 内部人占比越高越危险 |
| `prior_rug_rate` | +1.75 | 历史跑路率（**已知创建者 AUC 0.923 的主因**） |
| `has_history` | −1.12 | 有历史的老号比纯新号风险低（新号光环是真的） |
| `f10_n_buys` | +0.45 | 修正项 |
| `prior_n` / `prior_resolved` / `prior_grad_rate` | 小 | 辅助项 |

校准（跑路侧）：最低十分位 预测 1.6% / 实际 2.9%；最高十分位 预测 99.6% / 实际 98.3%。
两个极端桶都对得上，说明概率可以直接当阈值用。

---

## 3. 产品规格（拟）

**接口（示意）**

```
GET /v1/score/{mint}
→ 200 {
    "mint": "...",
    "as_of": "2026-10-14T09:00:00Z",
    "p_rug_300s": 0.97,          # 组合模型
    "p_graduation": 0.01,
    "flags": ["no_history", "dev_share_high"],
    "top_factors": [{"feature": "dev_share", "contribution": +2.1}, ...],
    "model_version": "risk-2026-10-14"
  }
```

- **延迟**：历史特征 = 一次 DB 查询（<10ms）；冷启动特征 = 读 bonding curve +
  dev 持仓（RPC，~100–500ms）。都在「上线 10 秒内」的窗口里。
- **接入点**（都解释为“排序/信誉/审核”，不是“劝退横幅”）：
  1. 币页/列表的质量标签与排序（Explore、Leaderboard、Hot callouts）
  2. Terminal 下单确认页的风险提示（可选开关）
  3. 创作者信誉与 rewards 资格
  4. GO bounty / 直播的主播-创建者交叉审核（用 `prior_rug_rate` + flags）
- **策略**：**标注而非拦截**——避免直接压低交易量；对平台是品牌/信任收益，
  对用户是知情权。
- **模型维护**：每周用最新 30 天重训（脚本已就绪），版本号随 `model.json` 走。

---

## 4. 边界（如实列出）

1. 评估窗口是 **10-01~10-03 三天**（冷启动特征只在 tape_replay 窗口完整）；
   历史组覆盖 34 天但特征更少。
2. `rugged` 是**规则标签**（抽干/dev 砸盘），不是法律意义的欺诈认定。
3. 冷启动特征依赖公开数据采集（`f10_*`）；拿到内部数据后可以换成更全的字段
   （真实持仓、资金图谱），AUC 预计更高。
4. 模型对**新玩法**（新捆绑手法）会退化——需要持续重训 + 漂移监控。

---

## 5. 下一步

- **在线原型 `score_service.py`**：读 `model.json` + 本地创作者历史库（由数据集构建）
  + Alchemy RPC 冷启动字段，暴露 `/v1/score/{mint}`，部署到 VPS（与报表页同机）。
- **历史库构建**：把 746k 行的创建者统计落成 SQLite（creator → prior_n / prior_rug_rate…），
  在线查询 O(1)。
- **与 ① 汇合**：同一个 VPS、同一套数据管道；报表页加一个「风险分演示」区块。

## 6. 复现

```bash
cd pumpfun/risk
../.venv/bin/python train_validate.py     # → facts.json + model.json
../.venv/bin/python score.py --features '{"dev_share":0.05, ...}'
```

---

## 7. 在线服务（已部署，2026-10-14）

```
https://team.stableflow.ai/risk/          # 演示页（Basic Auth 同报表页）
https://team.stableflow.ai/risk/score/{mint}   # JSON API
```

- `score_service.py`（OpenRC `pumpfun-risk`，端口 8090，Caddy `/risk/*` 反代）
- **冷启动特征已在线补齐**（对齐数据集口径的近似）：
  - 数据来源 1：**同机实时流数据库**（毫秒级，`early_stream`）——采集器新增
    `creator/user/is_buy/sol_amount/real_quote_reserves` 列（旧库自动 ALTER 迁移）；
  - 数据来源 2：RPC 兜底（创建交易 + 最早若干交易 + 前 20 大持有人）；
  - 字段：`dev_buy_sol`、`f10_n_buys`、`f10_bundle_wallets`、`f10_rs`、
    `f10_insider_share`、`dev_share`。
- **创建者历史热更新**：`update_history_from_stream.py` 每 15 分钟扫描成熟 mint
  （≥1 小时），按简化规则给出 `graduated_like`（峰值 ≥85 SOL）/
  `rug_like`（dev 300s 内卖出或跌破峰值 25%），写入 `stream_history.sqlite3`；
  评分时与数据集历史合并（`history_source: dataset+stream`）。
- 已知边界：迁移前的历史事件行缺 `creator` 列（覆盖随时间增长）；
  outcome 规则是简化版；在线概率尚未做回测校准。

---

## 8. 回填与在线回测（2026-10-14）

- **creator 回填**：迁移前的 15,375 个 mint 中回填 15,277 个
  （`backfill_creator.py`，64 mint/s；剩余 871 个链上找不到 curve）。
  期间发现并修复：`mint` 列缺索引导致长锁 → 已建 `idx_events_mint`；
  采集器与回填都加 `busy_timeout`。
- **在线回测**（`backtest_online.py`，425 个成熟且有结局的 mint）：
  - 基准：rug 77.4% / grad 22.8%
  - **AUC rug 0.72 / grad 0.49**；top10% rug 精确率 100%（基准已 77%，参考价值有限）
  - 差距原因：回测无法历史重建 `dev_share` 与 `f10_insider_share`
    （离线模型最强的两个特征）；已给采集器加 `token_amount` 列，
    后续可从「创建者首买 token 数 / 总量」重建部分 dev_share
  - 样本量小（流上线不到 6 小时），每日重跑更有意义
