# AGENTS.md —— 项目约定（给未来的 agent / 接过手的人）

本仓库是 **pumpidea**：pump.fun 发币经济的独立研究与运营项目。
2026-10-16 从原研究仓库抽取为独立仓库（原因与代价见 `docs/decisions.md`）。

**先读 `docs/decisions.md`**，尤其是 WAL 事故那条 —— 它解释了为什么这里有些
看起来"多余"的约束。

---

## 1. 数据纪律（最重要）

- **`analysis/facts.json` 是报告数字的唯一来源。** 不要在任何地方手写数字。
  要改口径 → 改 `analysis/analyze.py` → 重跑 → `facts.json` 更新 → 报告跟着核。
- `analysis/audit_report.py` 会把 `report.md` 正文里的**字面量**逐个对回
  `facts.json`，对不上就 `exit(1)`。所以改报告数字而不改分析脚本会直接失败。
- **两个 `facts.json` 别混**：`analysis/facts.json`（主研究，1944 行）与
  `audit/facts.json`（三方收入对账，450 行）是两回事。
- 口径里有几个反直觉的坑，引用前必读 `report.md` §8.2：
  - `rugged` 与 `graduated` **不互斥**（9.9% 兼有）→ 跑路率 ≠ 1 − 毕业率
  - `rugged` 是**观察规则**，不是已验证的欺诈
  - 2026-09-27 前解码器漏约 48% 买单 → 涉时序分析只用之后 5 天
  - 数据集有 17 条已知缺陷（KI-01~17），见 `data/loopholetape_README.md`

## 2. 四条线的边界与端口

| 线 | 入口 | 形态 | 端口 |
|---|---|---|---|
| `analysis/` | `analyze.py` 等脚本 | **离线批处理**，产出 `report.md` + `facts.json`，**无 Web** | — |
| `audit/` | `stream_collector.py`（常驻）/ `serve_site.py` | 链上费用采集 + 只读报表页 | 8081 |
| `risk/` | `score_service.py` | 实时打分服务 | 8090 |
| `pulse/` | `collector.py` + `builder.py` + `site/` | 注意力引擎（采集→故事→卡片→站点） | 8790 |
| `web/` + `api/` | 统一站点（React + 薄 BFF） | 单一入口，消费 `/api/v1/*` | 待建 |

**四条线之间不共享代码**。唯一的交叉：`risk/` 复用 `analysis/` 的数据集口径，
并**只读消费** `audit/` 产出的 `stream.sqlite3`。

## 3. 凭据与配置

| 用途 | 位置 | 说明 |
|---|---|---|
| Solana RPC（`ALCHEMY_RPC_URL` 等） | `audit/.env` | **已 gitignore**。优先级：真实环境变量 > 本文件。留空则回退公共端点（单次可用，扇出 80 次调用会挂） |
| Web Basic Auth | `/etc/pumpfun-web.conf`（VPS） | `WEB_USER` / `WEB_PASS`，600，**不入库** |
| `TYPESAFE_API_KEY`（Jev 打分） | 本仓库根 `.env` | 抽取前曾读兄弟仓库 `platform/.env`，已改 |

**永远不要提交密钥。** `.gitignore` 已覆盖 `.env` / `*.key` / `secrets/`。

## 4. 部署拓扑

VPS：Linode LXC，Alpine + OpenRC，Caddy 路径路由（见 `audit/deploy/README.md`）。

```
/opt/pumpfun-stream/            代码
  runtime/ → /mnt/pumpidea/runtime   ← 软链到 100G Linode 卷（见 decisions.md）
  .env                          600
/etc/periodic/{15min,hourly,daily}/pumpfun-*   定时任务
/var/log/pumpfun-*.log
```

**新库位置**：`/mnt/pumpidea/runtime/stream.sqlite3`，经由软链访问，部署脚本路径不变。

## 5. 约定，以及它的例外

仓库默认 **"运行时零依赖"**：`platform/` 的前端只用 Tailwind CLI 构建，产物提交进仓库，
运行时不需要 node；pulse 的站点是纯 stdlib + 静态文件。

**`web/` 是有意的例外** —— 引入 React 是产品前端长期维护的取舍，理由与代价写在
`docs/decisions.md`。**除 web 之外，不要引入前端框架或构建期依赖。**

## 6. 运维红线（血换来的）

1. **SQLite WAL 必须被管理。** `journal_size_limit` 是**每连接**设置（存不进库），
   已写在 `audit/stream_collector.py`。**任何新增加的重查询/写库进程，先读
   `docs/decisions.md` 的 WAL 条，再决定要不要加锁、加超时、加窗口上限。**
2. **不要在写入中的 SQLite 上跑长时间只读分析。** 一个持有读快照的进程会
   **钉住 WAL 的 checkpoint 水位线**，WAL 因此永远无法重置、无限增长。
   重分析任务要么走增量、要么读快照副本。
3. **所有周期任务必须防重叠**（`mkdir` 原子锁，见 `/etc/periodic/*/pumpfun-*`）。
   重叠运行 = 读快照永续存在 = 上一条。
4. **保留策略与磁盘要一起算。** 原始事件约 8G/天；改保留期前先算盘。
5. `pumpfun-walwatch` 每 15 分钟记录 WAL 大小与 checkpoint 的 busy 读数 ——
   排查 WAL 异常时**先看 `/var/log/pumpfun-walwatch.log`**。

## 7. 本地开发

```bash
# analysis：需要 pandas + pyarrow（**不要**装进其他地方）
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r analysis/requirements.txt
./analysis/fetch_data.sh          # 142MB，幂等，无需 key
.venv/bin/python analysis/verify_data.py
.venv/bin/python analysis/analyze.py
.venv/bin/python analysis/make_dashboard.py    # 生成 analysis/site/index.html
```

数据集（142MB）**不在仓库里**，靠 `fetch_data.sh` 幂等重建（CC BY 4.0，无需 key）。
