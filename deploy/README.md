# deploy —— 站点部署

统一站点由三部分组成，全部跑在 pumpfun 那台机器上：

| 组件 | 服务名 | 监听 | 说明 |
|---|---|---|---|
| BFF（含 SPA 托管） | `pumpfun-api` | `127.0.0.1:8000` | `api/` + `web/dist/` |
| pulse 采集 | `pumpfun-pulse-collector` | — | 调 loopholetape 公开 API |
| pulse 构建 | `pumpfun-pulse-builder` | — | 每 30 秒重写 `site/data.json` |

## 部署顺序

```bash
# 1) 链上采集 + 报表 + 周期任务（含 WAL 看门狗）
sh audit/deploy/install-alpine.sh /opt/pumpfun-stream
sh audit/deploy/install-periodic-alpine.sh /opt/pumpfun-stream

# 2) 打分服务
APP_DIR=/opt/pumpfun-stream sh audit/deploy/install-risk-alpine.sh

# 3) 报表页
sh audit/deploy/install-web-alpine.sh

# 4) 统一站点（本目录）
sh deploy/install-site-alpine.sh /opt/pumpfun-stream
```

## 为什么由 BFF 托管 SPA

Caddy 跑在宿主机、代码在容器里，静态目录过不去。让 BFF 托管之后**只有一个后端进程、
一个端口**，Caddy 只需一条反代（片段见 `caddy/pumpidea.caddyfile`）。

前端构建时 `base=/pumpfun/`，所以资源的绝对路径自带前缀；Caddy 用
`handle_path /pumpfun/*` 剥掉它，两边正好对上。

## VPS 上不装 node

`web/dist` 由 CI 构建后提交进仓库（`docs/decisions.md`），部署只 rsync 产物。
部署脚本最后会打印 `command -v node` 的结果 —— **必须为空**。

## 上线前必读

`docs/STATUS.md` §5-1：**站点目前没有鉴权**。不要直接公网暴露。
