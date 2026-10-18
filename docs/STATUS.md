# 项目状态与交接（STATUS）

> **这份文件的用途**：让另一个人 / 另一台机器能在 15 分钟内接手，不用重读对话。
> 每次阶段性推进后请更新它 —— 尤其是第 2 节（当前进度）与第 6 节（未完成）。
>
> 最后更新：2026-10-18

---

## 0. 一句话现状

四条线（analysis / audit / pulse / risk）已收进独立仓库 `pumpidea`，
**统一站点的后端（BFF）与前端（React）都已写完并本地验证通过**；
线上那台 VPS 正在稳定采集（WAL 事故已修复并加固）。
**站点还没部署到 VPS，也还没有任何鉴权。**

| 项 | 值 |
|---|---|
| 仓库 | `git@github.com:aidai524/pumpidea.git`，分支 `main` |
| VPS | `103.3.62.56`（Alpine LXC，root 可 SSH 免密） |
| 站点代码 | `api/`（FastAPI BFF）+ `web/`（React SPA） |
| 契约版本 | `/api/v1`（`api/app/normalize.py` 里的 `CONTRACT_VERSION`） |

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
| **P4** | CI + 部署到 VPS | ❌ **未做** | — |
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

## 5. 未完成（按优先级）

1. **P5 账号** —— 现在**所有 `/api/v1/*` 都是公开的**，包括失败率与创建者集中度。
   **在 P5 完成前不要把站点暴露到公网。**
2. **P4 CI + 部署** —— 包括：
   - CI 构建 `web/dist` 并提交；**必须带一条"dist 是否与源码同步"的断言**
     （否则改了源码忘了重新构建，线上就是旧页面）
   - Caddy 加 `/pumpfun/`（SPA）与 `/pumpfun/api/*`（BFF）
   - BFF 的 OpenRC 服务单元
   - 验收：`which node` 在 VPS 上为空
3. **P6 存储与保留** —— 聚合结果表 + 原始事件保留改 48h；设计见 spec §14。
   现在盘还够（卷剩 ~75G），但按 spec 的磁盘账，7 天 × 8G/天 + Plane 27G
   在原盘上是装不下的。
4. **权限分级（`viewer` 隔离）** —— 推迟了（`docs/decisions.md`）。在给外部
   合作方发账号**之前**必须完成。
5. **systemd 版（Debian）部署路径未同步加固** —— `install.sh` 还是老版本
   （内联 retention + systemd timer，没有 walwatch、没有防重叠锁）。
   生产用的是 Alpine 路径，但这条不一致是个坑。

---

## 6. 已知风险（如实记录）

| 风险 | 说明 |
|---|---|
| **未鉴权** | 见 §5-1。这是当前最大的风险，不要公网暴露 |
| WAL 事故可能复发 | 根因已定位到机制（读快照钉住水位线）并加固，但**最初触发条件仍未完全确认**。walwatch 的意义就是在复发时留下证据 |
| `dist/` 可能与源码漂移 | P4 之前没有 CI 守卫 |
| 一份 spec 与实现有一处偏离 | 前端**沿用**了少量上游字段名（如 `instant_share_of_graduations`），真正的解耦由 `api/app/normalize.py` 单点保证。详见 `api/README.md` 末节 |
| analysis 数据会变旧 | 它是离线静态产物（实测 age ≈ 1.8 天）。站点顶栏已经显示各自的数据年龄，**不要**把这个显示去掉 |
