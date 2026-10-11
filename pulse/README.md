# Pulse — pump.fun 注意力引擎（demo）

> 这是给 pump.fun 技术外包提案用的 **可运行 demo**，不是又一个数据看板。
> 论点：pump.fun 每天 3~5 万个新币在抢同一批眼球，**注意力是唯一稀缺资源**。
> 我们把公开链上信号实时翻译成三样东西：**可看的内容、可发的卡片、可点的入口**。

## 演示什么

| 屏幕 | 是什么 | 对 pump.fun 的价值 |
|---|---|---|
| **Live Watch** | 实时「最接近毕业」与「跑路雷达」候选 | 把风险/机会变成可展示的动态 |
| **Story Wall** | 每事件一张自动生成的分享卡（1080×1080 SVG） | 官方社媒的内容供给，零人工 |
| **The Tape** | 毕业流水（瞬时捆绑 / 有机，池子首 30 分钟） | 可嵌入首页/币页的实时组件素材 |

卡片底部统一带 `watch on pump.fun →` CTA —— demo 里演示的漏斗是：
**卡片（社媒）→ 币页故事（落地）→ pump.fun（交易）**。

## 六类故事模板

| 模板 | 触发条件 | 例子（真实数据） |
|---|---|---|
| instant | 2 秒内毕业 | `NVIDIA` 11 ms |
| organic | 有机毕业 ≥30 分钟 | `XNS` 101 分钟 |
| stampede | 一周内同 ticker ≥30 个币 | `SI` 1,151 个 |
| death | 毕业后 30 分钟跌破开盘 15% | `Claude AI` −100% |
| rugwatch | 实时跑路概率 ≥40% 或带前科标记 | `ACCL` 82% |
| gradwatch | 实时毕业概率 ≥5% | 真实买家 60 秒内 101 人 |

## 怎么跑

```bash
cd pumpfun/pulse
./run.sh                 # 采集 + 构建 + 本地站点 → http://127.0.0.1:8790/
./run.sh --once          # 只跑一轮（做截图/离线演示）
```

只用 Python 标准库，不需要 venv（仓库里的 `pumpfun/.venv` 也能跑）。
默认节奏：radar 10 s / 毕业流 60 s / 日统计 30 min；站点每 30 s 重建，前端每 15 s 拉新。

## 数据从哪来

- [`loopholetape`](https://api.loopholetape.com) 公开免费端点：`/v1/radar`（5 s 刷新）、
  `/v1/graduations`（24h，5 分钟延迟）、`/v1/stats/pumpfun`
- 全部是**公开链上数据的独立抓取**，无需 key；付费端点（$0.005/币的风险查询）demo 不用

## 目录

```
pulse/
├── run.sh              一键起（采集 + 构建 + 站点）
├── collector.py        轮询实时源 → SQLite（runtime/）
├── builder.py          DB → 故事 → SVG 卡片 + site/data.json
├── pulse/
│   ├── store.py        SQLite 存储层
│   ├── sources.py      loopholetape 取数
│   ├── stories.py      六类故事模板 + 排序/去重
│   └── cards.py        1080×1080 SVG 卡片渲染
├── site/               纯静态前端（index.html / app.js / style.css）
└── runtime/            sqlite + 生成物（gitignore）
```

## 对提案的含义

- **演示时**：先放 Story Wall（一眼看懂内容供给）→ 现场开 collector 看新故事冒出来
  → 点一张卡进 pump.fun → 讲「这些全来自公开数据；接你们的内部流会更快更准」。
- **可外包的交付**：内容/卡片引擎（本 demo 的生产化）+ 前端组件（Live Watch / Tape）
  + 背后的实时管道与运维。
- **demo 里刻意留的钩子**：品牌名 `PULSE`、CTA、语言都是占位符，谈的时候换成他们想要的。

## 已知边界

- 第三方公开源，毕业流有 5 分钟延迟；radar 只有 top 候选（不是全量）。
- 币名/符号是创作者写的不可信文本（loopholetape KI-14）：已做控制字符过滤 + XML/HTML 转义。
- 这是研究/演示，不构成任何投资建议。
