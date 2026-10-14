# pump.fun 费用流采集器 —— VPS 部署

**目标**：在服务器上 7×24 跑 `stream_collector.py`，不受本机休眠/开关机影响。
最小规格：**1 vCPU / 1GB RAM / 100GB 磁盘**（Debian 12 或 Ubuntu 22.04+）。
不需要开放任何入站端口——采集器只主动向外连 Alchemy WebSocket。

## 一次性部署（在 VPS 上执行）

```bash
# 1) 把代码拷上去（本地执行；runtime/ 不要拷）
cd pumpfun/audit
rsync -av --exclude runtime --exclude '.venv' \
      ./ user@VPS:/tmp/pumpfun-stream/

# 2) 在 VPS 上安装（root）
ssh user@VPS
sudo bash /tmp/pumpfun-stream/deploy/install.sh

# 3) 写入 Alchemy 端点（建议用单独 key，配好额度上限）
sudo -u pumpstream sh -c 'umask 077; cat > /opt/pumpfun-stream/.env <<EOF
ALCHEMY_RPC_URL=https://solana-mainnet.g.alchemy.com/v2/<KEY>
PULSE_STORE_FIELDS=0
EOF'

# 4) 启动
sudo systemctl enable --now pumpfun-stream
sudo systemctl status pumpfun-stream --no-pager
sudo journalctl -u pumpfun-stream -f
```

## 日常运维

```bash
sudo systemctl restart pumpfun-stream        # 重启
sudo journalctl -u pumpfun-stream --since "1 hour ago"
sudo tail -f /var/log/pumpfun-stream.log

# 看数据量/最新事件
sudo -u pumpstream /opt/pumpfun-stream/.venv/bin/python \
  /opt/pumpfun-stream/stream_collector.py --report
```

保留策略：安装脚本会装一个每天跑的 **retention timer**（默认保留 7 天，删除后 VACUUM）。

## 数据拉回本地

```bash
# 本地执行（增量；分析在本地做）
rsync -av --progress user@VPS:/opt/pumpfun-stream/runtime/stream.sqlite3 \
      pumpfun/audit/runtime/vps_stream.sqlite3
```

## 为什么用 `PULSE_STORE_FIELDS=0`

事件表里 `fields` JSON 列占空间大头（实测 ~18GB/天）。服务器只存分析需要的列
（六条费用线、pool/mint、时间戳），体积可降一个量级；原始 JSON 需要时可随时重采。

## Alpine / OpenRC（LXC 容器）

如果 VPS 是 Alpine（无 systemd），用 `install-alpine.sh`：

```bash
# 本地：先装 rsync（服务器上也需要，首次手动 apk add rsync sqlite python3 py3-pip）
rsync -a --exclude runtime --exclude .venv \
      -e "ssh -i ~/.ssh/id_ed25519" ./ root@VPS:/tmp/pumpfun-stream/

# VPS 上：
sh /tmp/pumpfun-stream/deploy/install-alpine.sh /opt/pumpfun-stream
rc-update add pumpfun-stream default && rc-service pumpfun-stream start
rc-service pumpfun-stream status && tail -f /var/log/pumpfun-stream.log
```

OpenRC 服务带 `supervisor=supervise-daemon` + `respawn_delay=5`（崩溃自动拉起），
保留策略在 `/etc/periodic/daily/pumpfun-retention`（busybox crond 默认执行）。

> 踩过的坑：`.env` 最后一行若没有换行符，追加 `PULSE_STORE_FIELDS=0` 会粘到
> `ALCHEMY_RPC_URL` 的值后面 → URL 被污染 → Alchemy 返回 401。脚本已做换行保护。

## 安全

- `.env` 权限 600，属主 `pumpstream`；**不要进 git**。
- 建议在 Alchemy 控制台为该 key 设额度上限；泄漏时单独吊销。
- VPS 只开 SSH；不需要 nginx/端口。
- 数据库是普通 SQLite 文件，`rsync` 时建议先 `sqlite3 db ".backup /tmp/x"` 或停服务几秒。


## Web 报表页（Alpine，只读）

```bash
# 服务器上（代码已同步到 /opt/pumpfun-stream）：
sh /opt/pumpfun-stream/deploy/install-web-alpine.sh
# 输出会打印访问 URL、用户名和随机密码（凭据存 /etc/pumpfun-web.conf，600）
```

- 用 stdlib `serve_site.py`（Basic Auth，默认 8080），**不碰 80/443**（那通常是别的应用）；
- `/etc/periodic/hourly/pumpfun-report` 每小时自动重建：拉数 → 定价 → 生成 `index.html`；
- 查看日志：`tail -f /var/log/pumpfun-report.log`；
- 改密码：改 `/etc/pumpfun-web.conf` 后 `rc-service pumpfun-web restart`。

> 加密提醒：Basic Auth 走 HTTP 时凭据是明文（仅适合临时演示）。要长期用请加域名 +
> TLS，或只在 SSH 隧道里访问：`ssh -L 8080:127.0.0.1:8080 root@VPS`。


## 挂到现有 Caddy 反代下（走 80/443 + HTTPS）

如果服务器的 80/443 已被别的应用占用（例如 Plane 自带 Caddy），**不要抢端口**，
往它的 Caddyfile 加一条路径路由即可（以 Plane 为例，实测通过）：

1. Caddyfile 在宿主机 `/root/plane-selfhost/plane-app/Caddyfile.ai`
   （只读挂载进 `plane-app-proxy-1` 容器）；先备份。
2. 在 `reverse_proxy /* web:3000` **之前**插入：
   ```caddyfile
   redir /pumpfun /pumpfun/ permanent
   handle_path /pumpfun/* {
       reverse_proxy 172.18.0.1:8080   # docker 网关 IP → 宿主机 8080
   }
   ```
   （`handle_path` 优先级高于 catch-all 的 `reverse_proxy /*`；172.18.0.1 用
   `docker network inspect <net> -f '{{(index .IPAM.Config 0).Gateway}}'` 查。）
3. 校验 + 热加载（不重启容器、不断服务）：
   ```bash
   docker exec plane-app-proxy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
   docker exec plane-app-proxy-1 caddy reload  --config /etc/caddy/Caddyfile --adapter caddyfile
   ```
4. 访问 `https://<SITE_ADDRESS>/pumpfun/`（现有站点的自动 HTTPS 一并生效）。

**风险评分服务（③ 线）**同理，另加一段：

```caddyfile
redir /risk /risk/ permanent
handle_path /risk/* {
    reverse_proxy 172.18.0.1:8090
}
```

服务端部署：`sh deploy/install-risk-alpine.sh`（需要先把 `risk/` rsync 到 `/opt/pumpfun-stream/risk/`，
含本地生成的 `history.sqlite3`）。访问 `https://<SITE_ADDRESS>/risk/` 是演示页。
5. **回滚**：恢复备份的 Caddyfile 再 reload；Plane 升级若覆盖该文件，按上面重加。
