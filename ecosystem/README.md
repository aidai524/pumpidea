# pump.fun 生态侦察

**日期**：2026-10-11
**目的**：为「给 pump.fun 做技术外包」找到真实切入点——先弄清他们自己做了什么、谁在给他们供货、以及生态里已经有哪些二级产品。
**方法**：只使用公开来源——pump.fun 站点/公开 API/footer 外链、Google News 检索、出版商盘点文章、GitHub 目录。**没有内部信息**。日期均为报道日期；部分未能打开原文的条目在来源里标注。

---

## 0. 一句话结论

**pump.fun 正在纵向整合：把「交易/数据/内容」产品买进来变自研，把「基础设施」留在外面采购。**
过去 12 个月的收购：Kolscan（2025-07）、Padre（2025-10）、Vyper（2026-02）——交易终端与钱包追踪已经从第三方工具变成自家的 Terminal。真正还在「外包」的是视频、存储、入金、链上标签、隐私出入金这类底层能力。

对我们的含义：**不要卖他们已经内化的东西（终端、直播、发现页）；也不要只卖「数据+风控」（loopholetape / Bubblemaps / Arkham / Nansen 都在做）。** 可卖的是「插进他们现有界面的质量层」和对他们业务的独立审计——但这要和他们的收入结构小心对齐（另文再议）。

---

## 1. pump.fun 自己的产品栈（公开页面实测，2026-10-11）

| 类别 | 产品 | 状态 |
|---|---|---|
| 核心 | 发币曲线、PumpSwap、$PUMP（回购销毁看板 `fees.pump.fun`） | 自研 |
| 玩法 | Mayhem（agent 交易）、Holder rewards、Custom pairs（代币化股票，93 个 ticker）、Charity Coins、BOOST、Callouts、GO Bounty | 自研 |
| 注意力 | Live 直播、Explore/Discover、Feed、Leaderboard（Traders/Squads/Rewards/Best callouts） | 自研 |
| 交易 | Terminal（原 Padre，整合 Vyper），链上标签来自 **Arkham** | 收购+自研 |
| 内容渠道 | Medium 博客、Telegram 技术更新、X / TikTok / Instagram / YouTube | 自营 |
| 移动端 | 官方 App（页面提示「Pump is better on mobile」） | 自研 |

**他们公开承认的一个数据问题**（`fees.pump.fun`）：「自定义交易对上线后，费用看板不再正确反映收入和回购，将尽快修复」——这是最自然的审计/对账切入点。

---

## 2. 谁在给 pump.fun 供货（外包 / 合作 / 收购）

### 2.1 已被收购（曾经的第三方产品，现已内化）

| 产品 | 领域 | 时间 | 备注 |
|---|---|---|---|
| **Kolscan** | 钱包追踪 / KOL 跟踪 | 2025-07-11 | 首次收购，被描述为「eyes gamified trading」 |
| **Padre** | 多链交易终端 | 2025-10-24 | 收购后代币 -80%，承诺补偿；现品牌为 **Terminal** |
| **Vyper** | 跨链交易终端 | 2026-02-05 | 独立产品关停，用户迁移到 Terminal |

### 2.2 基础设施与集成供应商（当前仍在合作）

| 类别 | 提供方 | 做什么 | 时间/证据 |
|---|---|---|---|
| 视频直播 | **Mux** | 直播推流与缩略图（页面直接引用 `stream.mux.com` / `image.mux.com`） | 站点源码 |
| 元数据存储 | **Pinata**（IPFS） | 币的图片/元数据（`pump.mypinata.cloud`） | 站点源码 |
| 元数据存储 | **Irys**（Arweave） | 元数据网关（`gateway.irys.xyz`） | 站点源码 |
| 法币入金 | **MoonPay** | 即时买币；2026-03 扩到 9 条链跨链入金 | 2025-11-04 / 2026-03-11 PR |
| 链上地址标签 | **Arkham** | Terminal 集成 31 亿地址标签 | 2026-09-10 |
| 隐私出入金 | **Houdini**（SOL Strategies 旗下） | Terminal 的私有充值/提现 | 2026-07-16 |
| 上币合作 | **MEXC** | Meme+ 每周上币 | 2025-09-08 |
| CDN/静态资源 | jsDelivr、Amazon S3 | 前端依赖与图片 | 站点源码 |

### 2.3 投资/生态基金（Pump Fund，2026-01 成立）

- **$3M「Build in Public」hackathon**：12 个项目各 $25 万 / $10M 估值，按市场牵引力选（不靠评委）。
- **Pumpcade**（直播原生预测市场）：2026-04-02 由 Pump.fun 领投 $1M pre-seed，Foundation Capital 等参与；用官方 API + 确定性数据源自动结算。
- **PumpMarket**（预测市场）：2026-02-26 参加该 hackathon 的公开项目，是否与 Pumpcade 为同一团队未证实。

> 含义：pump.fun 对生态团队有两种关系——**收购**（产品面）和**投资**（Pump Fund）。「被投资」也是一条可能的合作路径。

---

## 3. pump.fun 生态的二级衍生产品（第三方）

### 3.1 交易终端 / 狙击 / 跟单

| 产品 | 备注 |
|---|---|
| GMGN.ai | AI 扫描、跟单、狙击（Binance/AMBCrypto 盘点常客） |
| Axiom Trade | 一体化 Solana 交易；2026-02 曾被 ZachXBT 指控员工内幕交易 |
| BullX / Bullx NEO | 多链；2026-06 暂停 meme 交易工具但保留钱包 |
| Photon | 轻量网页狙击 |
| Trojan | Solana 狙击 + 跟单 + 安全审计 |
| Maestro / Banana Gun / BONKbot | 老牌 Telegram bot |
| Sigma / MevX / Blazing / Bloom Bot / Sniperoo | 新一代 bot（费用 0.5%–1%） |
| AddUp / Cryptohopper / TradeSanta / Cornix / Fluxbot | 更偏策略/自动化的 bot |

### 3.2 量能 / 做市 / 捆绑工具

Boost Legends、Hummingbot、Jupiter Volume Bot、ARBProtocol、**Panda Bundler**、DexLift（包含 Solana volume bot）。这类工具直接制造我们报告里的「捆绑毕业」现象。

### 3.3 分析 / 风控

| 产品 | 备注 |
|---|---|
| **loopholetape** | 我们的数据供应商：radar（实时 P(毕业)/P(跑路)）、毕业 feed、ticker 页、按次风险查询（$0.005）、MCP |
| **Bubblemaps** | 持币集中度可视化；多次公开点名 pump.fun 上代币与 KOL |
| **Arkham** | 地址标签（已进 Terminal） |
| Nansen / Dune / Birdeye / DexScreener | 通用链上数据 |
| Kolscan | 已被 pump.fun 收购 |
| RugCheck / Solsniffer | 社区常用一键风险检查（在本环境未独立验证活跃度） |

### 3.4 直播 / 预测 / 互动

- pump.fun 官方直播生态：streamers（2025-09 起出现「两天赚 15 万美元」的案例）、GO Bounties（2026-06 因危险任务被批）。
- **Pumpcade**：直播内嵌预测市场（Pump.fun 领投）。
- Livestream 历史：2024-11 因争议下架；2025-04 对 5% 用户重启；2025-09 全面爆发；2026-05 出现严重社会事件（有主播涉暴力犯罪）——**内容审核是这门生意的长期风险点**。

### 3.5 跨链仿盘 / 竞品平台（`awesome-pump` 目录 33 项精选）

DAOs.fun、vvaifu.fun、news2pump.fun、Virtuals（Base）、meme.cooking（NEAR）、clank.fun、Emojicoin（Aptos）、hop.fun（Sui）、Uptos、Time.fun 等。
同链直接竞争：**FOMO**（2026-08/09 用 $20K 签约 + $30K/月挖 pump.fun 用户）、**StonkFun**（2026-09 单日收入超过 pump.fun）、**Pons**（Robinhood Chain，被 Uniswap 收购）、MemeToro、AlphaSwap、Noxa.fi、Raydium LaunchLab（支持任意交易对）。

---

## 4. 风险与法律时间线（影响我们的切入点）

| 时间 | 事件 |
|---|---|
| 2024-11 | 直播功能因内容争议下架 |
| 2025-07 | RICO 修正案诉讼（含 Solana Labs、Jito） |
| 2025-12 | MEV 集体诉讼：吹哨人泄露 5,000+ 内部聊天；前员工因 $2M 欺诈被判 6 年 |
| 2026-03 | 疑似闪电贷攻击，交易暂停；攻击者在伦敦被捕 |
| 2026-06 | GO Bounty 任务引发舆论危机，代币单周跌 11.7% |
| 2026-08 | FOMO 平台高价挖角用户 |
| 2026-10-11 | Bubblemaps 指控 pump.fun 上的 KOL 通过 49 次推广获利 $12.5 万 |

---

## 5. 对我们 pitch 的含义（初步，未定稿）

| 观察 | 推论 |
|---|---|
| 终端/数据/内容都被内化或收购 | 不要卖「另一个终端/看板/直播」 |
| 基建仍靠外部（Mux/Pinata/MoonPay/Arkham/Houdini） | 我们若做基建差异不大，除非有独特能力 |
| 质量/风控层没有出现在产品里（无 organic/bundle、无 creator 前科） | 仍是最可能的楔子，但必须绑到他们的收入/留存上 |
| 他们自己承认费用看板数据不准 | 「独立数据审计」是最自然的约见话题 |
| Pump Fund 在投生态团队 | 除了外包，还有「被投资/共建」的路径 |
| 数据/风控赛道拥挤（loopholetape/Bubblemaps/Arkham/Nansen） | 纯信号没有护城河；差异化在**产品形态**和**分发位置** |

**待定**：下一轮研究聚焦哪条线——(a) 质量/信任层的产品方案，(b) 费用看板/收入数据审计，(c) Pump Fund 路径，还是 (d) 其他。等主方向确认后再写下一份文档。

---

## 6. 主要来源

- pump.fun 站点与公开 API（2026-10-11 抓取：首页、`/live`、`/explore`、`/leaderboard`、`/mayhem`、币页、`fees.pump.fun`、`frontend-api-v3.pump.fun`）
- Cointelegraph, *Pump.fun Expands Trading Infrastructure With Vyper Acquisition*, 2026-02-06
- CoinDesk / Yahoo Finance, *Pump.fun Makes Its Acquisition, Buys Wallet Tracker Kolscan*, 2025-07-11
- Yahoo Finance / The Defiant, *Pump.fun Acquires Padre Trading Terminal*, 2025-10-24
- The Block, *Pump.fun launches new investment arm for funding startups*, 2026-01-19
- Tekedia, *Pump.fun's Build in Public Hackathon Boosts its Ecosystem Activity*, 2026-02-28
- Tekedia, *Pumpcade Announces An Oversubscribed $1M Pre-seed Round Led by Pump.fun*, 2026-04-03
- PR Newswire, *MoonPay Integrates with Pump.fun…*, 2025-11-04；*MoonPay Launches New Funding Options…*, 2026-03-11
- KuCoin News, *Pump.fun Trading Terminal Integrates Arkham's 3.1 Billion Address Tags*, 2026-09-10
- TradingView, *Houdini Partners with Pump.Fun's Terminal…*, 2026-07-16
- GlobeNewswire, *MEXC Expands Partnership with pump fun…*, 2025-09-08
- Cryptonews, *6 Best Solana Sniper Bots in 2026*；*Best Meme Coin Trading Bots in 2026*；*Best Solana Volume Trading Bots in 2026*
- AMBCrypto, *Top 11 Telegram trading bots…September 2026*
- GitHub `PotLock/awesome-pump`（33 项跨链目录，`app/data/projects.json`）
- 其他（Bubblemaps/KOL、FOMO 挖角、StonkFun、闪贷攻击、MEV 诉讼、直播争议）来自 Google News 检索到的多源报道，标题与日期见正文
