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

## 安全

- `.env` 权限 600，属主 `pumpstream`；**不要进 git**。
- 建议在 Alchemy 控制台为该 key 设额度上限；泄漏时单独吊销。
- VPS 只开 SSH；不需要 nginx/端口。
- 数据库是普通 SQLite 文件，`rsync` 时建议先 `sqlite3 db ".backup /tmp/x"` 或停服务几秒。
