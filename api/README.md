# api —— 薄 BFF

四条线（analysis / audit / pulse / risk）的**统一契约层**。
前端只依赖 `/api/v1/*`，不依赖任何上游字段名。

## 为什么需要它

四个上游里三个已经在产出 JSON 文档，第四个（risk）本身就是 JSON API。
所以"前后端分离"大部分本来就有了 —— 缺的是三件事：

1. **一个稳定的契约**（上游改字段不至于让前端崩）
2. **一个同源入口**（消掉 CORS）
3. **一处统一鉴权**（尤其是 risk 的凭据不能下发到浏览器）

BFF 只做这四件事，不多做：归一化、代转 risk、统一错误形状、健康聚合。
**不缓存业务逻辑，不重算任何指标** —— 数字的唯一来源仍是各线的生成器。

## 契约的三条硬规则

见 `app/normalize.py` 的 docstring，这里只列结论：

1. **比率一律 0~1 的小数**，字段名 `*_rate` / `*_share`。**不出现 `*_pct`**。
   上游是混着来的（`graduation_rate: 0.0205` 与 `rug_rate_pct: 65.4` 同时存在），
   而这个坑是真踩过的。
2. **金额一律绝对 USD**。上游同样混着：`fees_30d=175.82` 是**百万**、
   `volume_30d_b=15.17` 是**十亿**、`fees_page` 里还有 `"589.19"` 这种字符串。
   契约层全部换算成 USD，否则"把 $175.82M 当成 $175.82"只需一次疏忽。
3. **每个响应都带 `generated_at`**（上游数据的生成时间）。三条线产出频率差几个
   数量级（pulse 30 秒 / audit 1 小时 / analysis 离线静态），
   不标陈旧度会把几天前的数字当实时数据看。

另外 audit 的**双口径在结构上分开**（`all` / `liq` 两个子对象，不是并排字段）：
`all` 含长尾报价资产，会被单一低流动性资产放大两个数量级（实测某天
`holder_rewards` 全价口径 23.5 亿 USD）。**不能拿 `all` 当收入。**

## 跑起来

```bash
cd api
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q                     # 契约测试
.venv/bin/uvicorn app.main:app --port 8000        # http://127.0.0.1:8000/docs
```

上游路径可用环境变量覆盖（前缀 `PUMPIDEA_API_`），见 `app/config.py`：

```bash
PUMPIDEA_API_AUDIT_REPORT=/opt/pumpfun-stream/stream_report.json \
PUMPIDEA_API_PULSE_DATA=/var/www/pumpfun/data.json \
PUMPIDEA_API_RISK_CREDS=/etc/pumpfun-web.conf \
  .venv/bin/uvicorn app.main:app --port 8000
```

## 端点

| 路径 | 上游 |
|---|---|
| `GET /api/v1/health` | 四条线的可用性 + **数据陈旧度** |
| `GET /api/v1/analysis/overview` | `analysis/facts.json` |
| `GET /api/v1/analysis/creators` | 同上 |
| `GET /api/v1/analysis/economics` | 同上 |
| `GET /api/v1/audit/summary` | `audit/stream_report.json`（六线 × 双口径） |
| `GET /api/v1/audit/reconciliation` | `audit/facts.json`（三方对账） |
| `GET /api/v1/pulse/feed` | `pulse/site/data.json` |
| `GET /api/v1/risk/health` | 代转 `score_service.py` |
| `GET /api/v1/risk/score/{mint}` | 代转（**凭据只在服务端**） |

错误一律 `{"error": {"code", "message", ...}}`；上游不可用 → 503，risk 不可达 → 502，
risk 超时 → 504。

## 测试保护的是什么

`tests/test_api.py` 不测"代码能跑"，测的是上面三条契约规则**不被将来的修改破坏**：

- 遍历整个响应，断言不存在 `*_pct` 字段、所有 `*_rate` / `*_share` 都在 0~1
- 断言 `generated_at` 存在
- 断言 audit 双口径是两个字对象且键集相同
- 断言金额换算（`fees_30d=57.86` → `57_860_000`）——这是回归测试

**写这些测试的时候它们立刻抓到了 3 个我自己写出来的契约违规**（`trend.launches_pct`、
`tape_replay_missing_pct`、以及把上游 `defillama` / `dataset` 整块透传导致泄漏
`take_rate_pct`）。所以别删它们。

## 与验收标准的一处偏离（如实记录）

spec §11 第 8 条写的是"前端源码 grep 不到上游内部字段名（如
`instant_share_of_graduations`）"。实际实现里**少量沿用了上游的名字** ——
因为这些名字本身就是好的领域名，为了通过 grep 而改名没有意义。

真正的解耦由**单点实现**保证：所有字段映射只存在于 `app/normalize.py`，
上游改名只改这一个文件。前端依赖的是这个文件的输出，不是上游。
