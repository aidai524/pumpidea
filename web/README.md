# web —— 统一前端

单一入口的 React SPA，消费 `api/` 暴露的 `/api/v1` 契约。

## 定位

四个视图（总览 / 研究 / 收入对账 / 注意力 / 打分）从四个互不相连的页面/端口
收敛成一个站点。**这是本仓库唯一有意偏离"运行时零依赖"约定的地方** ——
理由与代价写在 `docs/decisions.md`。

## 跑起来

```bash
cd web
npm ci
npm run dev        # http://127.0.0.1:5173，/api 代理到 BFF(8000)
npm run build      # → dist/（CI 会构建并提交，见 spec §10.2）
```

先起 BFF：`cd ../api && .venv/bin/uvicorn app.main:app --port 8000`。

## 三条设计约束

0. **`tokens.css` 里的 `source(none)` + `@source` 不能删**。Tailwind v4 默认
   自动探测内容源，会扫到 **`dist/` 里上一次的构建产物**并把压缩 bundle 里的
   class 候选也算进去 —— 实测让 CSS 从 12,470 字节虚增到 15,086，且产物不可复现
   （有没有 dist 会得到不同结果）。因为本项目把 `dist/` 提交进仓库，这个陷阱
   每次构建都会触发。
1. **token 只有一个源**：`src/styles/tokens.css` 的 `@theme`。
   这套值不是新设计的，是照抄现有三个静态页的配色与字体 —— 项目已有词汇表时
   必须用它（两套词汇表比任何一套都糟）。组件里**不要出现十六进制颜色**。
2. **不引第三方图表库**：`BarLineChart` 是从 `analysis/make_dashboard.py` 的
   手写 SVG 移植的。现有两张图够用，echarts/recharts 会带来第二套视觉语言。
3. **不重算任何业务口径**：比率是 0~1、金额是绝对 USD（后端契约已统一），
   前端只做显示格式化（`src/lib/format.ts`）。

## 数据新鲜度

顶栏每个徽标显示**各自来源的数据年龄**。这不是装饰：三条线的产出频率差几个
数量级（pulse 10 秒 / audit 几分钟 / analysis 是离线静态，实测 age ≈ 1.8 天），
不标出来就会把几天前的分析当实时数据看。

## 路由与部署

生产部署在 Caddy 的 `/pumpfun/` 下，所以：

- `vite.config.ts` 里 `base` 在 production 为 `/pumpfun/`
- `BrowserRouter basename={import.meta.env.BASE_URL}` 必须与之一致
- API 路径用 `BASE_URL` 拼接：dev → `/api/v1/...`（vite proxy）；
  prod → `/pumpfun/api/v1/...`（Caddy `handle_path` 剥掉前缀后到 BFF）
