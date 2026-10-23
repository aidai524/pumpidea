# 项目状态与交接（STATUS）

> **这份文件的用途**：让另一个人 / 另一台机器能在 15 分钟内接手，不用重读对话。
> 每次阶段性推进后请更新它 —— 尤其是第 2 节（当前进度）与第 6 节（未完成）。
>
> 最后更新：2026-10-18

---

## 0. 一句话现状

四条线（analysis / audit / pulse / risk）已收进独立仓库 `pumpidea`；
**统一站点（BFF + React）已部署到 VPS 并通过端到端验收**。
**还差：Caddy 路由（需宿主机访问权）与登录鉴权（P5）。**

> ⚠️ 一个正在恶化的点：audit 的每小时报表任务已经**跑不完**了（见 §5-2）。

| 项 | 值 |
|---|---|
| 仓库 | `git@github.com:aidai524/pumpidea.git`，分支 `main` |
| VPS | `103.3.62.56`（Alpine LXC，root 可 SSH 免密） |
| 站点代码 | `api/`（FastAPI BFF）+ `web/`（React SPA） |
| 契约版本 | `/api/v1`（`api/app/normalize.py` 里的 `CONTRACT_VERSION`） |

---

## 0.1 线上跑的是哪个提交

VPS 上的源码是 **rsync 过去的、不是 git checkout**，所以它**不能自己 `git log`**。
为此部署脚本会把提交号写进 `$APP/DEPLOYED_COMMIT`：

```bash
cat /opt/pumpfun-stream/DEPLOYED_COMMIT      # 例：83b6991（末尾 +dirty = 有未提交改动）
```

提交号由**调用方**传入（远端那份源码没有 `.git`，自己查不到）。用一键脚本即可：

```bash
sh deploy/push-to-vps.sh        # rsync + 远端部署 + 写入 DEPLOYED_COMMIT
```

### 怎么判断"要不要重新部署"

```bash
# 把上次部署的提交号和当前 HEAD 比一下，只看运行中的代码路径
git diff --name-only <上次部署提交>..HEAD -- api web pulse audit deploy
```

只改了 `docs/` 就不用部署。

---

## 1. 换一台机器继续做（按顺序执行）

### 1.1 拿代码

```bash
git clone git@github.com:aidai524/pumpidea.git
cd pumpidea
```

> 数据集（142MB）与所有运行期数据库**不在仓库里**（`.gitignore` 排除），
> 靠下面各自的方式重建。仓库里只有代码、文档、`dist/` 构建产物和已算好的
> `facts.json`。

### 1.2 读三份文档（在写任何代码之前）

```bash
cat AGENTS.md                    # 项目约定与运维红线（必读，尤其第 1、6 节）
cat docs/decisions.md            # 决策日志，含 WAL 事故的完整根因链
cat docs/superpowers/specs/2026-10-16-pumpidea-design.md   # 设计文档（16 节）
```

### 1.3 analysis（离线研究管线）

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r analysis/requirements.txt

./analysis/fetch_data.sh                  # 142MB，幂等，无需 API key
.venv/bin/python analysis/verify_data.py  # 核对行数/列数/毕业率
.venv/bin/python analysis/analyze.py      # → analysis/facts.json
.venv/bin/python analysis/make_dashboard.py   # → analysis/site/index.html
```

`analysis/jev_score.py` 需要 `TYPESAFE_API_KEY`（写在本仓库根 `.env`），
不跑这一步不影响其它任何东西 —— `jev_segments.json` 已签入。

### 1.4 api（薄 BFF）

```bash
cd api
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q             # 8 个契约测试，应全绿
.venv/bin/uvicorn app.main:app --port 8000
```

BFF 需要三条线的产出物。**刚 clone 下来时 audit/pulse 的产出物不存在**
（它们是运行期产物），所以 `/audit/*` 与 `/pulse/*` 会返回 503 ——
这是预期行为，不是坏了。让它们有数据的两条路：

1. 从 VPS 拉：`scp root@103.3.62.56:/opt/pumpfun-stream/stream_report.json audit/`
2. 或用环境变量指到任意一份本地副本（见 `api/app/config.py`）

### 1.5 web（React SPA）

```bash
cd web
npm ci
npm run dev          # http://127.0.0.1:5173，/api 代理到 BFF(8000)
npm run build        # → dist/（CI 会构建并提交，见 spec §10.2）
```

### 1.6 本地把四个服务都起起来（可选，用于对照旧页面）

| 服务 | 命令 | 端口 |
|---|---|---|
| pulse | `./pulse/run.sh` | 8790 |
| audit 页 | `python3 audit/serve_site.py --root "$PWD/audit/site" --port 8081 --creds /tmp/creds.conf` | 8081 |
| risk | `python3 risk/score_service.py --port 8090 --creds /tmp/creds.conf` | 8090 |
| analysis 页 | `python3 audit/serve_site.py --root "$PWD/analysis/site" --port 8082 --creds /tmp/creds.conf` | 8082 |
| **BFF** | `cd api && .venv/bin/uvicorn app.main:app --port 8000` | 8000 |
| **SPA** | `cd web && npm run dev` | 5173 |

凭据文件格式（`serve_site.py` / `score_service.py` / BFF 的 risk 代理都读它）：

```
WEB_USER=demo
WEB_PASS=demo-pumpfun
```

> ⚠️ 不要用 `http://user:pass@127.0.0.1:8090/` 这种把凭据写进 URL 的形式 ——
> 浏览器会拒绝页面内的 `fetch()`（`Request cannot be constructed from a URL
> that includes credentials`）。用浏览器弹出的鉴权框。

---

## 2. 当前进度

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| **P1** | 抽取为独立仓库 `pumpidea`（保留 25 个原始提交的历史） | ✅ | `git log`；原仓库零写入 |
| **P0** | 项目记忆：`AGENTS.md` + `docs/decisions.md` | ✅ | 两个文件均签入 |
| **P2** | 薄 BFF：`/api/v1` 9 个端点 | ✅ | 8 个契约测试全绿；本地四路端到端 200 |
| **P3** | React 前端：5 个路由 | ✅ | `tsc` 零错误；`vite build` 通过；浏览器实测 5 路由无错误 |
| **P4** | CI + 部署到 VPS | ✅ 部署完成（Caddy 路由待宿主机访问权） | 见 §3.1 验收记录 |
| **P5** | 账号（登录 + 会话 + 限流） | ❌ 未做 | 权限分级另有推迟，见 §6 |
| **P6** | 存储与保留（先聚合后丢弃） | ❌ 未做 | 设计见 spec §14 |

### 已完成的关键数字（供回归对照）

- `analysis/facts.json`：30 天 **1,156,058** 个新币；名义毕业率 **2.06%**，有机 **0.86%**；
  瞬时捆绑占毕业 **58.0%**；30 天净收入 **$54.5M**
- `web/dist`：JS 339KB / **gzip 107KB**，CSS 12.5KB
- risk 单次打分：**约 18 秒**（要扇出约 80 次链上 RPC）
- VPS 采集库：**4800 万+ 行**，WAL 稳态 **256MB**（`journal_size_limit` 封顶）

---

## 3. VPS 上现在跑着什么

```
103.3.62.56  (Alpine LXC, OpenRC)
├── /opt/pumpfun-stream/              代码（由 rsync 部署）
│   ├── .env                          600，含 ALCHEMY_RPC_URL / PULSE_STORE_FIELDS=0
│   ├── runtime → /mnt/pumpidea/runtime     ← 软链到 100G Linode 卷
│   └── risk/stream_history.sqlite3
├── /mnt/pumpidea/                    97.9G 卷，已写入 /etc/fstab（nofail）
└── /var/log/pumpfun-*.log
```

| 服务 / 任务 | 说明 |
|---|---|
| `pumpfun-stream` | 链上费用流采集（WebSocket，订阅 3 个程序） |
| `pumpfun-web` | 只读报表页，端口 8080，Basic Auth |
| `pumpfun-risk` | 打分服务，端口 8090，Basic Auth |
| `/etc/periodic/15min/pumpfun-walwatch` | **WAL 看门狗**：每 15 分钟记 WAL 大小 / 可用空间 / checkpoint 读数 |
| `/etc/periodic/hourly/pumpfun-report` | 报表重建（带防重叠锁） |
| `/etc/periodic/hourly/pumpfun-history` | 创建者历史增量更新（带防重叠锁） |
| `/etc/periodic/daily/pumpfun-retention` | 删 >7 天原始事件 + checkpoint（带锁，空间不足时跳过 VACUUM） |

**这 4 个周期任务的源码在 `audit/deploy/periodic/`，安装器是
`audit/deploy/install-periodic-alpine.sh`。** 之前它们只存在于服务器上，
现已收进仓库 —— 重装时用安装器，不要手写。

Caddy 已在用（既有 Plane 部署的），路径路由约定见 `audit/deploy/README.md`：

```
handle_path /pumpfun/* { reverse_proxy 172.18.0.1:8080 }   # 报表页
handle_path /risk/*    { reverse_proxy 172.18.0.1:8090 }   # 打分服务
```

`/pumpfun/` 与 `/pumpfun/api/*` 的站点路由**尚未配置**（属于 P4）。

### 3.1 站点部署验收记录（2026-10-18）

```
pumpfun-api                 started   127.0.0.1:8000（BFF + SPA 托管）
pumpfun-pulse-collector     started
pumpfun-pulse-builder       started

GET /                        200   → SPA（含 id="root"）
GET /analysis                200   → SPA 深链回落
GET /api/v1/health           200   → 四路全 ok，pulse age ≈ 11s
GET /api/v1/{analysis/*,audit/summary,audit/reconciliation,pulse/feed}  全 200
GET /api/v1/risk/score/<mint> 200  → 约 18 秒
WAL 稳定 256MB（journal_size_limit 封顶），checkpoint log≈checkpointed
```

部署踩到并已修的两个坑（都已进仓库）：

1. `audit/` 的内容被 `install-alpine.sh` 铺到 `$APP` **根**（`stream_collector.py`
   就在根上），所以 audit 的 `facts.json` 在 `$APP/facts.json`，
   **不是** `$APP/audit/facts.json`。
2. 周期报表脚本原来用 `>"$LOG"`，**每次运行都清空日志** —— 39 小时没成功却只剩
   3 行日志。已改成追加写并记录 rc；失败时不再重建页面（否则旧 JSON 会被渲染成
   刚更新过）。

---

### 3.2 三次「静默停摆」与各自的根因（都修了，但教训要记住）

| # | 时间 | 现象 | 根因 | 修正 |
|---|---|---|---|---|
| 1 | 10-15 / 10-16 | WAL 涨到 33.5G / 35.5G 打满磁盘 | 长读快照钉住 checkpoint 水位线 | 迁库到 100G 卷 + `journal_size_limit` + 防重叠锁 + history 降频 |
| 2 | 10-19 16:27 → 10-23 03:10 | **3.5 天没写进一行事件** | Alchemy WS 握手被拒（`InvalidStatus`）—— 具体 HTTP 状态码**没被记下来**，所以无法断定是 429 配额还是别的 | 看门狗已加「**数据陈旧度**」告警（`age=` 与 30 分钟阈值） |
| 3 | 10-22 02:22 → 10-23 03:14 | pulse 的 `data.json` 停在 1 天前 | builder 读库时被 collector 的写挡住（`database is locked`）→ 崩 5 次超 OpenRC respawn 上限 → **永久停止** | builder 改 `mode=ro` 打开 + 超时 10s + 库切 WAL（读不再挡写） |

> **共同的教训：进程活着 ≠ 数据在涨。**
> 三次都出现过「`rc-service status` 显示 started，但数据不动」，而当时**没有任何东西
> 盯"数据不涨"**。看门狗的 `age=` 就是补这个洞 —— 它是这三次事故换来的最贵一行代码。

**顺带修掉的膨胀源**：pulse 的 `counts` 表每次快照存**整个 payload**（约 320KB/行），
builder 每 30 秒写一次 → **约 900MB/天**。实测 1.9G 的库里 1.89G 全是它
（`freelist=0`，所以不是空洞，是真数据）。已加保留策略（counts 留 200 条、
radar 留 7 天），一次性清理回收 **1.75GB**。

---

## 4. 排查手册（踩过的）

| 症状 | 先看什么 |
|---|---|
| 采集器停了 / 数据不涨 | `/var/log/pumpfun-stream.log` + `rc-service pumpfun-stream status` |
| 磁盘快满 | `df -h / /mnt/pumpidea`；`ls -lh /mnt/pumpidea/runtime` |
| WAL 异常增大 | **`/var/log/pumpfun-walwatch.log`**（一行一个观测点） |
| 报表页 404 / 空白 | `/var/log/pumpfun-report.log`（是否 `database is locked`） |
| 打分很慢或超时 | risk 服务是否在跑；`/api/v1/health` 里 risk 的 `status_code` |
| BFF 某一路 503 | 该路上游的产出文件不存在 —— 看返回里的 `error.code` 与 `path` |

**WAL 的一个反直觉点**：`PRAGMA wal_checkpoint` 返回 `busy=0` **不代表水位线在前进**。
要看 `log` 与 `checkpointed` 两个数：若 `log` 远大于 `checkpointed` 且
`checkpointed` 不动，说明有**长读快照**钉住了它。完整机制见 `docs/decisions.md`。

---

## 5. 接下来要做什么

> 2026-10-18 重写过一次：上一版把**已完成**的 P4 混在待办里，编号也重复了
> （1,2,3,2,3,4,5）。这种情况会让交接文档失去可信度 —— 所以下面明确分成
> 「已完成 / 立即 / 上线前 / 之后 / 待你决定」五块。

### 5.1 已完成（不要重做）

- P1 抽取 · P0 记忆 · P2 BFF · P3 前端 · **P4 CI + 部署**
- 看门狗与防重叠锁**已写回仓库**（`audit/deploy/periodic/` +
  `audit/deploy/install-periodic-alpine.sh`）——这条之前是欠账，已清
- 站点已部署并在 VPS 上通过端到端验收（见 §3.1）

### 5.2 立即做：修 audit 报表任务（数据正在变旧）

**这是当前唯一在持续产生错误状态的事**：报表页每小时"重建"一次，但底下的
JSON 停在 2026-10-16 15:08。

| 项 | 内容 |
|---|---|
| 现象 | 每小时都被自己的防重叠锁跳过：`上一轮仍在运行，跳过本轮` |
| 根因 | `stream_report.py` 对**全部**原始事件做日/小时聚合；库从 2800 万行涨到 **4900 万行**后单次 >1 小时 |
| 证据 | 手动跑 5 分 50 秒仍未完成（CPU 仅 2 分 10 秒，全是 I/O），同时把 WAL 的 `checkpointed` 钉在 376 帧不动 |
| 第一步 | **给聚合查询加时间窗口**（保留期本来就是 7 天）——小改动、立刻恢复数据更新 |
| 正解 | 增量聚合（= P6） |

### 5.3 上线前必须

1. **P5 账号**（登录 + 会话 + 限流）。现在**所有 `/api/v1/*` 都是公开的**，
   包括失败率与创建者集中度 —— 在 P5 之前**不要公网暴露**
   （`deploy/caddy/pumpidea.caddyfile` 里预留了 basicauth 作为过渡）。
2. **Caddy 路由**：`handle_path /pumpfun/*` 还没加进去。我没有宿主机权限，
   需要人工在宿主机 `caddy validate && caddy reload`（片段已写好）。

### 5.4 之后

3. **P6 存储与保留**：聚合结果表 + 原始事件保留改 48h（spec §14）。
4. **权限分级（`viewer` 隔离）**：推迟了。在给外部合作方发账号**之前**必须完成。
5. **WS 重连日志要打出 HTTP 状态码**：现在只写 `InvalidStatus`，无法区分 429（配额）/
   401（密钥）/ 5xx（上游故障）—— 10-19 那次断流 3.5 天，正是因为分不清。
6. **systemd/Debian 部署路径未同步加固**：`install.sh` 还是老版本（内联 retention
   + systemd timer，没有 walwatch、没有防重叠锁）。生产用的是 Alpine 路径。

### 5.5 需要你决定

| 问题 | 背景 |
|---|---|
| VPS 上的 `nodejs`/`npm` 要不要卸掉？ | 是镜像自带的 apk 包（v24，7 月 30 日装，被 npm 依赖），**不是我们装的**。验收项「`which node` 为空」因此不过；但意图（站点不需要 node 就能跑）已满足。卸掉约省 55MB。 |
| **Alchemy 要不要升级配额？** | 10-19 的 3.5 天断流最可能是月度 CU 配额耗尽（WS 握手被拒）。当前 HTTP RPC 返回 200，说明额度已恢复或只是瞬时限制。免费档在高流量下会反复触发 —— 要么升级，要么降低订阅范围（现在订阅了 **3 个程序**的全部日志）。 |
| 报表任务"只聚合最近 N 天"这个口径能不能接受？ | 作为 5.2 第一步的临时缓解。代价：更早的历史日数据不再更新（现有页面只展示保留期内的数据，影响有限）。 |

---

## 6. 已知风险（如实记录）

| 风险 | 说明 |
|---|---|
| **未鉴权** | 见 §5-1。这是当前最大的风险，不要公网暴露 |
| WAL 事故可能复发 | 根因已定位到机制（读快照钉住水位线）并加固，但**最初触发条件仍未完全确认**。walwatch 的意义就是在复发时留下证据 |
| `dist/` 可能与源码漂移 | P4 之前没有 CI 守卫 |
| 一份 spec 与实现有一处偏离 | 前端**沿用**了少量上游字段名（如 `instant_share_of_graduations`），真正的解耦由 `api/app/normalize.py` 单点保证。详见 `api/README.md` 末节 |
| analysis 数据会变旧 | 它是离线静态产物（实测 age ≈ 1.8 天）。站点顶栏已经显示各自的数据年龄，**不要**把这个显示去掉 |
