# pumpidea —— 独立仓库抽取 + 统一前端 设计文档

**日期**：2026-10-16
**状态**：待评审
**前置**：本 spec 位于 `analysis/pumpfun/docs/` 下，抽取时会随 `pumpfun/` 一起进入新仓库
**后继**：本 spec 批准后进入 `writing-plans`，由其产出实现计划

---

## 1. 背景

`/Users/joe/Any/analysis` 这个仓库从"产品需求的研究与分析"起步，因此同时装着两条互不相干的研究线：

- `stableflow-swap/` + `platform/` + `lib/` + `scripts/` + `projects.yaml` —— Stableflow 跨链 swap 线（平台是它的运行时）
- `pumpfun/` —— pump.fun 发币经济研究线（**刻意不接平台**，见 `pumpfun/README.md:76`）

pumpfun 这条线已经长出四条子线（analysis / audit / risk / pulse），共 25 个提交、89 个文件，并且已经产生了**独立的运营现实**：一台 VPS 上常驻着流程采集、报表页与打分服务（`audit/deploy/README.md`），WAL 曾撑到 33.5G 把磁盘打满。

它已经不再适合待在一个"研究仓库"的子目录里。同时，四条线的对外形态是四个**互不相连的页面/服务**（8790 / 8081 / 8090 / 8082），没有统一入口，没有一个可长期维护的前端。

本设计要解决两件事，且顺序不可颠倒：

1. **抽取**：把 `pumpfun/` 拆成独立仓库 `pumpidea`，保留完整历史，并把这期间产生的**决策与项目记忆**一起带过去。
2. **统一站点**：在**新仓库**里做一个单一入口的站点 —— React 前端 + 薄 BFF 接口层 + 完整用户与权限。

### 1.1 为什么必须先抽取再做 web

web 会引入全新的顶层（`web/`、`api/`、CI 配置）。若先在现仓库做，抽取时所有路径、CI、`dist/` 都要重来。而现在抽取只需修 3 处引用（§5.3）。这是本次设计里唯一一处"先做元工作"的取舍。

---

## 2. 目标 / 非目标

### 目标

| # | 目标 | 可验证的判据 |
|---|---|---|
| G1 | `pumpidea` 成为独立仓库 | 新仓库里 `git log --oneline \| wc -l` ≥ 25，且历史里能看到 pumpfun 的全部提交 |
| G2 | 本次会话的决策不再只存在于对话里 | `docs/decisions.md` 覆盖 §6.2 列出的 5 条决策 |
| G3 | 未来 agent 接手不再需要重读对话 | `AGENTS.md` 存在且覆盖 §6.1 的全部条目 |
| G4 | 单一入口访问四个服务 | 浏览器打开一个域名，`/api/v1/*` 可取到四份数据 |
| G5 | 前端与后端解耦 | 前端源码中**不出现**任何服务的内部字段路径；只依赖 §7 的契约 |
| G6 | 账号（登录 + 会话） | 未登录被拒；登录后可见全部视图（**权限分级本次不做**，§8.3） |
| G7 | VPS 上不装 node | 部署只 rsync 静态产物 + 重启 BFF |

### 非目标（明确不做）

- **不把 analysis 的离线管线搬上 VPS**。它需要 142MB 数据集 + pandas（`pumpfun/README.md` 的复现步骤），继续在本地跑；BFF 只负责把**已签入的 `facts.json`** 发出去。
- **不合并进 `platform/`**。`pumpfun/README.md:76` 明确写了 pumpfun 与 platform"没有关系，这是刻意的"（platform 的分析单元是跨链 swap 的走廊，装不进「代币/创建者」这个模子）。本次只**借鉴**它的权限模式与设计语言，不共享代码库。
- **不改动原仓库**（见 §5.2）。
- **不做实时推送**（WebSocket / SSE）。四个视图用轮询即可（pulse 现有实现就是轮询 `data.json`）。
- **不做多租户**。本产品只有一个项目（pump.fun），不需要 platform 那套 `Membership` / `Project` 隔离。

---

## 3. 范围与阶段

| 阶段 | 内容 | 产出 |
|---|---|---|
| **P0** | 落记忆 | `AGENTS.md`、`docs/decisions.md`（写在新仓库；见 §6.4 的时序） |
| **P1** | 抽取 | 新仓库 `pumpidea`，含完整历史；修 3 处引用 |
| **P2** | BFF + 契约 | `/api/v1/*` 可独立验证（用 curl 即可验收） |
| **P3** | 前端 | 四个视图 + 统一导航 + 设计 token |
| **P4** | CI + 部署 | CI 构建 `dist/`；Caddy 路由；VPS 起来 |
| **P5** | 账号 | 登录 + 会话 + 限流（**权限分级推迟**，§8.3） |
| **P6** | 存储与保留（**不阻塞上线**） | 原始事件只留滚动窗口，聚合永久（见 §14） |

**执行顺序说明**：上表按依赖编号，**实际执行顺序是 P1 → P0 → P2 → P3 → P4 → P5**；**P6 在其后，且与 P2/P3 无依赖**（原因见 §14.4）。记忆文件（§6.1 / §6.2）必须写在**新仓库**里（原仓库冻结不动），所以抽取必须先发生。§15 的实施顺序与此一致。

P2 与 P3 之间以 §7 的契约为界，可以并行（契约先冻结）。

---

## 4. 硬约束

### 4.1 技术栈

**后端 BFF** —— 与 `platform/` 同栈，直接复用其已验证的模式，不引入新范式：

```
fastapi / uvicorn[standard]
sqlalchemy>=2.0 / alembic / psycopg[binary]     # 用户与会话表
argon2-cffi                                      # 口令散列（platform 同款）
pydantic-settings / python-multipart / jinja2
```

**前端** —— 这是本仓库**唯一一次有意偏离**"运行时零依赖"约定（`platform/package.json` 与根 `.gitignore` 都写着这条）。偏离的理由必须留在 `docs/decisions.md`：

```
vite + react + typescript
tailwindcss v4（与 platform 同版本、同 token 来源）
@tanstack/react-query（轮询与缓存；避免手写状态机）
```

**图表**：不引第三方图表库。把现有 `analysis/make_dashboard.py` 里手写的内联 SVG 图表**提取成 React 组件**（`web/src/components/charts/`）。理由：现有两张图（双轴柱线图、占比条）已够用，引 echarts/recharts 会带来第二套视觉语言与一个重依赖。

### 4.2 设计 token：**只有一套**

`pumpfun` 现有三个页面（audit 的对照页、risk 的 demo 页、`analysis/site`）已经在用同一套深色 + `ui-monospace` 的配色。前端**必须沿用这一套**，并把它们写成唯一的 token 源（`web/src/styles/tokens.css` 导出 CSS 变量，Tailwind 主题从同一处取）。

> ui-craft 的规则：项目已有词汇表时**必须用它**；两套词汇表比任何一套都糟。这条是本设计的硬约束，不是建议。

### 4.3 Ladder 声明（一行）

```
spacing(padding/margin/gap): 4 8 12 16 24 32 48 64
尺寸 >48px(卡片/侧栏/列宽): 继续走同一套 ladder，即 96 192 256 384 512
尺寸 ≤48px(头像/控件高/图标框): 不判断
字号: 11 12 13 14 18 22（数据密集后台，不需要 4xl 以上）
字重: 每屏最多 3 个（400 正文 / 600 强调 / 800 数值）
圆角: 2 个（卡片 12 / 控件 8）
阴影: 不用阴影，用 1px 边框（沿用现有三页的既有做法）
```

最后一条是有意的：现有三页全部用 `border:1px solid var(--line)` 表达层级，没有一处阴影。前端保持一致。

### 4.4 构建产物

`web/dist/` **由 CI 构建并提交**（延续仓库既有约定"产物提交进仓库"）。VPS 上不装 node —— 部署只 rsync 静态产物。

---

## 5. P1 · 抽取

### 5.1 目标形态

```
pumpidea/
├── AGENTS.md                    ← P0 新增
├── README.md                    ← 改 §5.3-2
├── report.md                    ← 原样
├── docs/
│   ├── decisions.md             ← P0 新增
│   └── superpowers/specs/2026-10-16-pumpidea-design.md   ← 本文件
├── analysis/  audit/  risk/  pulse/  ecosystem/  data/
├── web/                         ← P3 新增
└── api/                         ← P2 新增
```

### 5.2 机制：**零写入原仓库**

原仓库按约定**冻结不动**（不改任何已跟踪文件、不新增提交）。做法是：

```bash
# 1) 在现仓库切出一个只含 pumpfun 历史的分支（不 checkout、不改工作区）
git subtree split -P pumpfun -b standalone        # 需 brew install git-subtree
# 或零依赖退路：
git filter-branch --subdirectory-filter pumpfun -- --all

# 2) 推到新远端
# 3) 新仓库里补上"未提交也没法随历史走"的部分（见 5.2.1）
```

`git subtree split` 只能带走**已提交**的内容。当前工作区有三项未提交（`git status --porcelain -- pumpfun/`）：

| 项 | 状态 | 处理 |
|---|---|---|
| `risk/score_service.py` | 已改未提交（两处既有 bug 的修复） | 在新仓库**重新应用**并作为新提交 |
| `analysis/make_dashboard.py` | 未跟踪（新文件） | **复制**进新仓库后提交 |
| `analysis/site/index.html` | 未跟踪（生成物） | **复制**进新仓库后提交 |

**5.2.1 为什么不在原仓库先提交**

提交会改动原仓库（新增提交 = 改 `.git` 状态），与"不动了"冲突。而在新仓库重新应用这三项，代价是三分钟，收益是原仓库**一个字节都没变**，且新仓库的第一条额外提交可以写成一条清晰的说明：

```
fix(risk): 修 HTML 模板花括号语法错误 + 历史库缺失时优雅降级
feat(analysis): facts.json 驱动的只读仪表盘
```

### 5.3 抽取时必须修的三处引用

| # | 位置 | 现状 | 改为 |
|---|---|---|---|
| 1 | `analysis/jev_score.py` | `env = ROOT.parent / "platform" / ".env"` 读 `TYPESAFE_API_KEY` | 仓库内路径（`ROOT.parent / ".env"`），并在 README 说明该键的作用 |
| 2 | `README.md:76` | 一节讲「与平台（`../platform/`）的关系」 | 改为「本项目独立；与 platform 无代码依赖」，保留"为什么刻意分离"的理由 |
| 3 | 根 `.gitignore` 的 10 条 pumpfun 规则 | 带 `pumpfun/` 前缀 | 移入新仓库 `.gitignore`，去掉前缀 |

第 1 条是**唯一的代码级耦合**（另两处是文档与配置）。抽取后 `pumpidea` 内不得出现任何指向兄弟仓库的路径。

### 5.4 数据不随仓库走（这是设计，不是遗漏）

`data/launches/`、`data/launches_legacy/`、`data/graduation_pools/`（共 142MB）被 gitignore，靠 `analysis/fetch_data.sh` 幂等重建（CC BY 4.0，无需 key）。抽取**不搬运**它们；新仓库照旧 `./analysis/fetch_data.sh` 即可。同样不搬运的还有各线的运行时产物（`*/runtime/`、`stream_report.json`、`history.sqlite3` 等，均在 `.gitignore` 内）。

### 5.5 验收

- 新仓库 `git log --oneline | wc -l` ≥ 25，且 `git log --oneline -- analysis/` 能看到 pumpfun 的原始提交
- `grep -rn "\.\./platform" pumpidea/` 零命中（文档与代码皆然）
- `./analysis/fetch_data.sh` 在新仓库可重跑（幂等）

---

## 6. P0 · 记忆

### 6.1 `AGENTS.md`（新增，给未来的 agent）

必须覆盖：

1. **数据纪律**：`analysis/facts.json` 是报告数字的**唯一来源**，不得手算；`analysis/audit_report.py` 会把 `report.md` 里的字面量与 facts.json 对账，不一致即失败。改口径要改 `analyze.py` 再重跑，不要改数字。
2. **四个服务的边界与端口**：pulse 8790（采集+构建+静态站）/ audit 8081（只读报表页）/ risk 8090（打分服务）/ BFF 8000（站点接口）。
3. **凭据位置**：`audit/.env`（`ALCHEMY_RPC_URL` 等，被 gitignore）/ `/etc/pumpfun-web.conf`（Basic Auth）。**不得入库**。
4. **部署拓扑**：VPS 上 Alpine/OpenRC，Caddy 路径路由（`audit/deploy/README.md`）。
5. **约定与其例外**：仓库默认"运行时零依赖"；`web/` 是**有意的例外**，理由见 `decisions.md`。
6. **已知缺陷指针**：数据集 17 条 KI（`data/loopholetape_README.md`）；`rugged` 是观察规则不是欺诈认定；`rugged` 与 `graduated` 不互斥。
7. **运维红线**：SQLite WAL 必须被管理（见 `decisions.md` 的 WAL 条），加任何写库进程前先读它。

### 6.2 `docs/decisions.md`（新增，决策日志）

按时间**倒序**记录，每条含：日期 / 决定 / 理由 / 代价。必须包含这 5 条（它们目前**只存在于对话里**）：

| # | 决定 | 必须写下的理由与代价 |
|---|---|---|
| D-a | 统一站点采用 **React SPA + 薄 BFF** | 代价：引入 node 工具链与一套前端范式，**偏离**仓库"运行时零依赖"约定。理由：产品前端要长期维护、会长大 |
| D-b | **不并入 `platform/`**，独立成 `pumpidea` | 理由：`README.md:76` 的刻意分离仍然成立；代价：登录/权限要自己带一套（见 §8） |
| D-c | **WAL 事故**：33.55G 的 WAL 一次性落盘，回收约 31G | 完整根因链与加固方案（见 §6.3）|
| D-d | `risk/score_service.py` 两处既有 bug 的修复 | 花括号（非 f-string 里写了 f-string 转义）导致整段脚本语法错误、按钮静默无反应；历史库缺失时报 `no such table` 而非可读提示 |
| D-e | 从 `analysis` 抽取的**代价** | `jev_score.py` 曾依赖 `../platform/.env`；抽取时改仓库内路径 |
| D-f | **存储分层**：JSON 是服务格式不是存储；P6 走「先聚合、后丢弃」，**不换数据库引擎** | 理由与磁盘账见 §14。代价：要重做保留策略并把运维职责落到一个地方 |

### 6.3 WAL 事故的记录要点（本设计中最有价值的一条记忆）

**现象**：`stream.sqlite3-wal` 涨到 **33.55G**，磁盘 78.3G 打满 100%，采集器 `sqlite3.OperationalError: disk I/O error` 崩溃，停摆 3.4 小时。

**复发（2026-10-16）**：修复后仅约 7 小时，WAL 又涨到 **35.5G**、磁盘再次 100%、采集器再次 `disk I/O error` 死掉约 **16 小时**。**→ 不加固就会一直重演。**

**复发时的处置**（比第一次好，因为有了新卷）：新增 100G Linode 卷 → 在副本上 checkpoint 验证无误后才删源 → 把库迁到 `/mnt/pumpidea`（根盘释放 46.4G）→ 软链回 `/opt/pumpfun-stream/runtime`（部署脚本路径未改）→ 装 WAL 看门狗。

**一个重要的实测纠正**：稳态是**健康的** —— 迁移后实测 WAL 稳定在 **4MB**、`wal_checkpoint(PASSIVE)` 返回 **`0|N|N`（busy=0）**。所以那 35.5G 是**失控阶段**的速率，不是正常速率（不可据此算容量）。两次失控的共同点是「磁盘先接近满」，但**第一次爆发时磁盘本来是空的** —— 故**确切触发点仍未确认**，这正是看门狗要记录的东西。

**根因链**（三层叠加，缺一不会发生）：

1. 库是 WAL 模式，但**代码里没有任何地方设置或管理它**（`grep journal_mode /opt/pumpfun-stream` 零命中）。WAL 模式一旦设定就永久记在库头里。
2. **WAL 文件大小是高水位**，只有 `wal_checkpoint(TRUNCATE)` 才会缩回。默认的自动 checkpoint 只把页搬进主库，不缩文件。
3. 唯一的 checkpoint 藏在每日保留脚本里，而它几乎注定失败：
   - `wal_checkpoint(TRUNCATE)` 遇读写冲突**立即返回 busy=1 而不等待** → 采集器在持续写入时它静默空转；
   - 脚本无 `set -e`、无日志 → 失败无声；
   - `VACUUM` 需约 2× 库大小的空闲空间，近满盘时必失败；
   - 保留期 7 天，头一周 `DELETE` 删不到东西 → 本来就没有空间被回收。

**修复与加固**（已实施 + 待实施）：

- 已完成：停机 → 清出外部空间（Docker 构建缓存 6.8G + `/root` 缓存 1.6G）→ `PRAGMA wal_checkpoint(TRUNCATE)`（48.9s，`0|0|0` 完整成功）→ WAL 由 **33.55G 降到 96MB**，磁盘可用由 3.7G 变 34.6G（**回收约 31G**），`20634840` 行数据零丢失。**判据**：动手前确认 WAL 最大页号（1,920,784）**小于** DB 现有页数（2,054,431）→ 落盘是原地覆盖、文件不增长，才敢在只剩 3.7G 时执行。
- 待实施：① `PRAGMA journal_size_limit`（**一行即可防住复发**）；② 加 WAL 大小的看门狗任务（含显式日志与 busy 重试，必要时短暂停采集）；③ 保留脚本加 `set -e` 与日志，空间不足时跳过 `VACUUM`。
- **这三项要同时写回 `audit/deploy/install-*.sh`**，否则下次重装又回到老样子。

### 6.4 会话历史（d 档）

pi 的会话归档按 **cwd 路径**命名：`~/.pi/agent/sessions/--Users-joe-Any-analysis--/`。项目一移动**不会自动关联**。

计划：复制为 `--Users-joe-Any-pumpidea--` 后**实测**能否被识别。**这一条是不确定的**，所以同时必须有一份**不依赖 pi 内部格式**的兜底：把本会话的关键决策导出为人可读的 `docs/decisions.md`（即 §6.2，本来就要做）。

> 时序说明：§6.1 / §6.2 的文件写在**新仓库**（P0 与 P1 谁先无强依赖，但都必须在新仓库里落定）。本 spec 自身因为要随抽取走，暂放在 `pumpfun/docs/` 下。

---

## 7. P2 · API 契约（薄 BFF）

### 7.1 为什么需要 BFF

四个上游里三个已经在产出 JSON 文档（`facts.json` / `stream_report.json` / `data.json`），第四个（risk）本身就是 JSON API。**所以"前后端分离"大部分已经存在** —— 缺的是：一个稳定且版本化的契约、一个同源入口、一处统一鉴权。

BFF 的职责**只有四件**，不多做：

1. 把三份文档**归一化**成稳定字段（前端不感知上游的内部结构）
2. 服务端持有 risk 的凭据（浏览器**不接触** `/etc/pumpfun-web.conf`）
3. 统一的错误形状与鉴权
4. 上游可用性聚合（`/health`）

### 7.2 端点

| 方法 | 路径 | 上游 | 说明 |
|---|---|---|---|
| GET | `/api/v1/health` | 全部 | 四个上游的可用性与最后更新时间 |
| GET | `/api/v1/analysis/overview` | `analysis/facts.json` | 归一化 KPI + 30 天日序列 + 周度对比 + 已知缺口 |
| GET | `/api/v1/analysis/creators` | 同上 | 创建者集中度、老手分层、捆绑与 dev_share 分布 |
| GET | `/api/v1/analysis/economics` | 同上 | 收入结构、抽成率、下界校验 |
| GET | `/api/v1/audit/summary` | `audit/stream_report.json` | 六条费用线（协议/创作者/回购/LP/返现/持币奖励）× 双口径（全价 / 流动性达标） |
| GET | `/api/v1/audit/reconciliation` | `audit/facts.json` | 三方口径对照 + 周转倍数 |
| GET | `/api/v1/pulse/feed` | `pulse/site/data.json` | `live` / `stories` / `tape` / `kpis` |
| GET | `/api/v1/risk/score/{mint}` | `risk/score_service.py` | 透传；服务端带凭据 |
| GET | `/api/v1/risk/health` | 同上 | |

### 7.3 契约纪律

- **版本前缀 `/api/v1`**，上游结构变化时前端不动。
- **归一化字段名由 BFF 定义**，例如上游的 `graduation_rate`（0-1 小数）在契约里一律为 `graduation_rate`（0-1），`*_pct` 一律为百分数 —— **混用两种量纲是现有代码里已经存在的坑**（`facts.json` 里同时有 `graduation_rate: 0.0205` 和 `rug_rate_pct: 65.4`），契约层必须统一并在文档里写明。
- 每个响应带 `generated_at`（上游数据的生成时间），前端必须显示数据陈旧度 —— 因为 pulse 是 30 秒级、audit 是小时级、analysis 是**离线静态**，三者的新鲜度差几个数量级，**不标出来会误导**。
- 错误形状统一为 `{"error": {"code": "...", "message": "..."}}`。

### 7.4 已知约束

- **analysis 是离线的**：`facts.json` 是签入的静态文件，BFF 不做任何计算。前端必须把"数据截止 2026-10-08"显示在页面上。
- **risk 单次打分约 19 秒**（一次要扇出约 80 次 RPC）。BFF 必须设超时并给前端一个明确的"正在读取链上"状态，不能让它悬着。

---

## 8. P5 · 账号与权限（**本次只做账号**，权限分级推迟）

### 8.1 复用 platform 已验证的模式

`platform/app/perms.py` 的核心设计值得原样照搬，连注释里的原则一起：

> **角色 → 权限集合的唯一映射处。** 权限字符串统一从 `Perm` 取，不在别处写裸字符串 —— 写错的权限名不报错，只会静默变成"无权限"，隔离测试抓不到。

**本次范围**：只复用它的**认证**部分（口令 / 会话）。上面这套 `Perm` 映射**推迟到需要时再做**（见 §8.3），理由见 §12。

### 8.2 数据模型（较 platform 大幅简化）

本产品**单项目、无租户**，因此砍掉 `Membership` / `Project`：

```
app_user(id, email, password_hash, role, is_active, created_at)
auth_session(id, user_id, token_hash, created_at, expires_at, last_seen_at)
audit_log(id, user_id, action, target, at, meta)     -- 登录、导出、权限变更
```

- `role` 列**先建好但不使用**（以后加权限时不必再改一次表结构，默认全为 `admin`）
- 口令：`argon2-cffi`（platform 同款）
- 会话：**HttpOnly + Secure + SameSite=Lax** 的 cookie，服务端存 `token_hash`（不存明文 token）
- 迁移：Alembic

### 8.3 权限分级：**本次不做**（设计保留，不是废弃）

> **推迟原因**：先把账号跑通，少一次交付面（用户选择「简单点」）。下面的边界设计留给下一次。

> ⚠️ **必要的克制**：在权限落地之前，**不要给外部合作方发账号** —— 因为没有 `viewer` 隔离，拿到账号就能看到全部视图（含失败率与创建者集中度）。

三个角色的权限按**视图**切：

| 角色 | 能力 | 关键约束 |
|---|---|---|
| `viewer` | pulse 全量；risk 打分；analysis 的**概览与公开结论**；audit 的**公开对账** | **看不到**：创建者集中度、老手分层、失败率明细、audit 的内部口径与差异归因 |
| `analyst` | 上述全部 + 分析的全部区段 + audit 的内部字段 | 内部使用 |
| `admin` | 上述全部 + 用户与权限管理 + 审计日志 | |

`viewer` 的边界不是随意划的，它直接来自仓库既有的判断——`analysis/README.md`（根 README）写着：平台侧的 `viewer`（外部合作方）**看不到分析结论，因为里面含失败率与单客户集中度**。这里是同一个原则在新产品上的落地。

**实现要求**：权限检查必须落在 **BFF 的响应组装层**，而不是"前端隐藏区块"。前端隐藏不是权限。

### 8.4 认证细节

- 登录页 `/login`，失败限流（照搬 `platform/app/ratelimit.py` 的思路）
- 所有 `/api/v1/*` 默认拒绝，白名单放行 `health` 与 `login`
- 登出即失效服务端会话
- CSRF：写操作要求同源 + 自定义头（本产品的写操作只有用户管理）

---

## 9. P3 · 前端

### 9.1 路由与页面

```
/login
/                  → 总览（四线状态、数据新鲜度、入口）
/analysis          → 研究仪表盘（把现有 analysis/site 的内容组件化）
/audit             → 收入口径对照（把现有 audit 对照页组件化）
/pulse             → 注意力引擎（live / stories / tape）
/risk              → 打分（输入 mint → 结果，含"读取链上…"状态）
/admin/users       → 用户与权限（admin）
```

### 9.2 组件复用

现有三个页面的共性元素必须抽成组件，而不是各写一遍：

- `KpiCard`（现有三页都有）
- `DataTable`（12 张表 → 一个组件）
- `BarLineChart`（`make_dashboard.py` 的双轴图 → React 组件）
- `ShareBar` / `StackedBar`（占比条）
- `AppShell`（统一导航 + 数据新鲜度指示）

### 9.3 与现有生成器的关系

**保留** `analysis/make_dashboard.py`、`audit/make_compare_page.py`、`audit/make_stream_page.py` 与 `pulse/builder.py`。理由：

- audit 的静态页是**给对方的交付物**（可离线打开、可发邮件），不是调试产物
- pulse 的 `builder.py` 同时产出 `data.json` —— **它现在是前端的数据源**

因此本设计的定位是：**静态页继续作为交付物存在，SPA 是内部与外部共用的操作台**。两者读同一份 JSON，不会数字打架。

> 顺带修一个既有隐患：`make_stream_page.py` 与 `make_compare_page.py` **默认都往 `site/index.html` 写**，互相覆盖。新仓库里给它们不同的默认文件名。

---

## 10. P4 · 部署与 CI

### 10.1 拓扑（复用现有 Caddy）

```
Caddy（现有，80/443 + 自动 TLS）
  /pumpfun/        → web/dist（静态）
  /pumpfun/api/*   → api:8000（BFF，OpenRC 服务）
  （risk 8090 不再直接对外；只由 BFF 服务端调用）
```

### 10.2 CI

- 触发：`web/**` 或 `api/**` 变更
- 步骤：`npm ci` → `vite build` → **把 `web/dist/` 提交回主分支** → 部署时 rsync 到 VPS
- VPS 上**不装 node**（硬约束 G7）

### 10.3 资源（必须如实记账）

VPS 现状：**3.9G RAM / 78.3G 磁盘（刚回收后剩 34.5G）**，上面已有 Plane（Docker，16 容器、27.3G 镜像）。本设计新增：

| 新增 | 成本 |
|---|---|
| BFF 进程 | ~100MB RAM |
| Postgres（用户表） | ~200MB RAM；**已决定：独立实例**（不复用 Plane 的，理由见 §12） |
| 静态产物 | ~1MB |
| **pulse 采集器常驻** | **这是最重的一项** —— pulse 现在是本地 demo，要上 VPS 才能让 `/pulse` 有真数据 |

**一笔必须先算的磁盘账**（§14.3 详算）：audit 的原始事件约 **8G/天**，而现状保留 **7 天 → 常驻 56G**；叠加 Plane 已占的 27.3G，**总需 ≈83G > 78.3G 磁盘** —— 也就是说**除了 WAL，这块盘还有第二颗雷**。P6 的目标就是拆掉它（原始 48h + 聚合永久 ≈ 17G）。

---

## 11. 验收标准

| # | 判据 |
|---|---|
| 1 | `pumpidea` 存在，历史含 pumpfun 的 ≥25 个提交；对其 grep `../platform` 零命中 |
| 2 | `AGENTS.md` 与 `docs/decisions.md` 存在，§6.1 / §6.2 的条目齐全 |
| 3 | 一个域名入口可访问四个视图；`/api/v1/health` 显示四个上游状态与新鲜度 |
| 4 | 未登录访问 `/api/v1/analysis/overview` 返回 401 |
| 5 | 登录后能访问全部视图；**登出后会话立即失效**（curl 直连验证，不依赖前端） |
| 6 | `/risk` 页能对真实 mint 出分，且过程中显示"读取链上…" |
| 7 | VPS 上 `which node` 不存在，站点仍可访问 |
| 8 | 前端源码 grep 不到上游内部字段名（如 `instant_share_of_graduations`） |
| 9 | **（P6）** 原始事件常驻 ≤ 20G；聚合结果永久保留且可重建日/小时六线；保留策略在部署脚本里且有日志 |

---

## 12. 决定与待定

### 已决定

- 抽取优先于 web（§1.1）
- 新仓库名 `pumpidea`；原仓库冻结、**零写入**（§5.2）
- 薄 BFF + `/api/v1` 契约（§7）
- 前端 React + TS + Vite + Tailwind v4，**与 platform 共用设计 token**，但**不并入 platform**（§4.2、§8.1）
- 登录为**完整用户 + 三角色 RBAC**，权限落在 BFF 而非前端（§8）
- CI 构建 `dist/` 并提交；VPS 不装 node（§10.2）
- 不引第三方图表库（§4.1）
- **存储分层**：三个 JSON 保持 JSON；原始事件只留滚动窗口、聚合永久；**P6 不换数据库引擎**（§14）
- **账号先行、权限推迟**：P5 只做登录 + 会话 + 限流；三角色 RBAC 推迟（§8.3）。代价：**外部合作方在此之前不能发账号**（无 `viewer` 隔离）

### 本轮已定（原「待你拍板」三项）

1. **远端** = `git@github.com:aidai524/pumpidea.git`；项目名统一为 **`pumpidea`**（原 `pumpfun-more` 已全文替换）
2. **Postgres** = **独立一个**（不复用 Plane 的实例）—— 它要承载高频流数据，需要自己的保留策略、备份与调优，不应绑死在别人的 compose 里
3. **pulse 采集器上 VPS** = **要**（`/pulse` 页因此有实时数据；磁盘成本已计入 §10.3）

### 仍待定

1. **P6 的滚动窗口取多长** —— 我建议「原始 48h + 聚合永久」，上线后按实际磁盘再调

---

## 13. 风险

| 风险 | 应对 |
|---|---|
| 会话历史搬不过去（§6.4 不确定） | 已有兜底：决策一律落 `decisions.md`，不依赖 pi 内部格式 |
| WAL 事故复发 | §6.3 的三项加固必须**同时写回仓库的部署脚本**，否则重装即复发 |
| VPS 资源（刚满过一次盘） | 部署前先确认 `df`；Postgres 与 pulse 采集器的常驻成本要计入（§10.3） |
| **保留窗口 × 体量本身就是第二颗雷** | 7 天 × 8G/天 = 56G（+ Plane 27G > 78G 磁盘）。P6 把它拆掉（§14.3）；**在 P6 交付前，部署前必须重新核算磁盘** |
| 前端成为第二套设计语言 | 硬约束 §4.2：token 只有一个源，且照抄现有三页的配色 |
| 契约与上游漂移 | 契约测试：BFF 的响应字段对拍 `facts.json` / `stream_report.json` 的既有键 |

---

## 14. 存储与保留（P6：先聚合、后丢弃）

### 14.1 先纠正一个前提：我们没有在用 JSON 当存储

四条线的**存储现在就已经是 SQLite**（代码里有 12 处 `sqlite3.connect`）。那三个 JSON 全部是**生成脚本写出来的产出物**：

| JSON | 谁写 | 体量 | 性质 |
|---|---|---|---|
| `analysis/facts.json` | `analyze.py:283` | **40KB** | 离线批处理的**产物**，有 provenance 链，`audit_report.py` 拿它对账 `report.md` |
| `audit/stream_report.json` | `stream_report.py:346` | 小 | **服务格式**（视图） |
| `pulse/site/data.json` | `builder.py:91` | 小 | **服务格式**（视图） |

所以「JSON 存储不太行」这个判断，**问题不在 JSON 上**。真正的四个问题是：

1. 存储被切成 **4 个互不相通的 SQLite 文件**（`pulse.sqlite3` / `stream.sqlite3` / `history.sqlite3` / `stream_history.sqlite3`）→ 跳线 join 只能 `ATTACH`
2. **并发写**：SQLite + WAL + 多写者，正是本次事故的土壤
3. **运维职责没有归属**：WAL / 保留 / checkpoint 散在三个部署脚本里，没人负责
4. **体量**：audit 流 **20.6M 行 / 24h / 7.8G**，约 **8G/天**

### 14.2 决定：分层，不一刀切

| 数据 | 决定 |
|---|---|
| `facts.json`（含 audit 的） | **保持 JSON**。它是带 provenance 的批处理产物；放进 DB 只会增加同步问题，零收益 |
| `stream_report.json` / `data.json` | **保持 JSON**。它们是**服务格式**，BFF 读的就是它们。是「视图」，不是「存储」 |
| `stream.sqlite3`（原始事件） | **保留，但只留滚动窗口**（§14.3） |
| 聚合结果（日 + 小时 × 六线） | **永久保留**（体量小几个数量级） |

**为什么不换 Postgres 引擎**：换引擎会让体量**更大**（行头 / 索引 / TOAST 开销），而这块盘刚刚被打满过；而且它解决不了「要留 7 天 × 8G」这个算术问题。**先把该丢的丢掉，再谈引擎。**

### 14.3 P6 的做法：先聚合、后丢弃

`stream_report.py` **已经**算出了日 + 小时两套六线聚合。所以只需把「原始事件」的保留期从 7 天压到 48 小时，聚合结果永久保留：

```
原始事件 events：滚动保留 48 小时    ← 8G/天 → 常驻约 16G
聚合结果（日 + 小时 × 六线）：永久    ← 小几个数量级
```

**磁盘账**（这块盘只有 78.3G，Plane 已占 27.3G）：

| 方案 | 常驻占用 | 结论 |
|---|---|---|
| 现状：原始事件留 7 天 | **7 × 8G = 56G** | 叠加 Plane 的 27G ≈ **83G > 78.3G → 本来就装不下** |
| P6：原始 48h + 聚合永久 | **≈ 17G** | 有充足余量 |

> 换句话说：**「7 天保留 × 原始事件」本身就是第二颗雷**（除了 WAL 之外）。本设计把它拆掉。

### 14.4 为什么 P6 不阻塞上线

**因为 BFF 就是边界。** 前端只认 `/api/v1/*`——后端的数据来自 JSON 文件、SQLite 还是 Postgres，**前端一行都不用改**。所以：

- P2 / P3 照原样（BFF 读 JSON）先把站建起来
- P6 单独做，改的只是「BFF 从哪里读」与「原始事件留多久」

### 14.5 P6 必须一起交付的四件

1. **保留策略写进部署脚本**（`audit/deploy/install-*.sh`），并带 `set -e` 与日志 —— 否则就是 §6.3 那次静默失败的重演
2. **`PRAGMA journal_size_limit`**（§6.3 的加固项），与保留策略一起落地
3. **WAL 看门狗写回部署脚本** —— 已在服务器安装（`/etc/periodic/15min/pumpfun-walwatch`，日志 `/var/log/pumpfun-walwatch.log`，每 15 分钟记录 WAL 大小 / 可用空间 / checkpoint 的 busy 读数），但**尚未进仓库**；不写回则重装即丢
4. **运维归属**：把 WAL / 保留 / 备份明确到一个任务与一个日志文件，而不是散在三个脚本里

---

## 15. 附：实施顺序（供 writing-plans 参考）

```
P1 抽取
  1. brew install git-subtree（或改用 filter-branch）
  2. git subtree split -P pumpfun -b standalone
  3. 推送到新远端；在本地 clone 出 pumpidea
  4. 复制三项未提交内容（make_dashboard.py / site/ / score_service.py 的改动）并提交
  5. 修三处引用（jev_score 密钥路径 / README ../platform / .gitignore）
  6. 验收：历史条数、grep 零命中、fetch_data.sh 幂等

P0 记忆（在新仓库完成）
  7. 写 AGENTS.md
  8. 写 docs/decisions.md（含 §6.3 的 WAL 全案）
  9. 实测会话归档能否被 pi 识别；不能则只保留 decisions.md 作为记忆载体

P2 BFF
 10. api/ 骨架 + 配置 + Alembic 初始迁移
 11. 三个只读端点（analysis/audit/pulse）+ health（**先不做鉴权**，先用 curl 验收）
 12. risk 透传（服务端带凭据）+ 超时与错误形状
 13. 契约测试

P3 前端
 14. Vite + TS + Tailwind v4 骨架；tokens.css（唯一 token 源）
 15. AppShell + 路由 + 数据新鲜度指示
 16. 组件：KpiCard / DataTable / BarLineChart（从 make_dashboard.py 的 SVG 移植）
 17. 四个视图逐个接 `/api/v1`

P4 CI + 部署
 18. CI：vite build → 提交 dist/
 19. Caddy 两条路由；BFF 的 OpenRC 服务
 20. VPS 验收（含 `which node` 为空）

P5 账号（权限分级推迟）
 21. app_user / auth_session 表 + Alembic 迁移（role 列先建好但不使用）
 22. 登录/登出 + argon2 校验 + 会话 cookie + 登录失败限流
 23. /api/v1/* 默认拒绝 + 白名单（health / login）；按验收标准 5 用 curl 验证
 24. （推迟）Perm 唯一映射表 + 三角色 + BFF 响应层过滤 —— 需要时再开

P6 存储与保留（不阻塞 P2/P3）
 25. 聚合结果表（日 + 小时 × 六线）+ 写入幂等
 26. 原始事件保留改为 48h 滚动；写回 audit/deploy/install-*.sh（set -e + 日志）
 27. 同时落地 PRAGMA journal_size_limit；把 WAL 看门狗一并写回部署脚本
 28. 上线前重算磁盘账（验收：原始事件常驻 ≤ 20G）
```

---

## 16. 附：本 spec 未覆盖的事（下一篇再谈）

- 用户管理界面（`/admin/users`）的具体交互
- 数据导出（把某个视图导成 CSV/PDF 给外部）
- 告警（WAL/磁盘/上游失联）—— §6.3 只讲了加固，没讲通知渠道
- stableflow 线的归置（原仓库转型为 stableflow 专属后，是否也走同样的抽取）
