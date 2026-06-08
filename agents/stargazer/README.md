# Stargazer

云资源采集和监控代理服务

## 🚀 快速启动

### 开发环境

```bash
# 1. 启动 Worker（终端1）
python start_worker.py

# 2. 启动 Server（终端2）
python server.py
```

### 重要提示

1. **必须先启动 Worker，再启动 Server**
2. **Server 和 Worker 的 Redis 配置必须完全一致**
3. **同一台机器只运行一个 Worker 实例**（除非需要提高并发）
4. **任务完成后会自动清除标记，允许重复采集**

---

## 📋 配置说明

### 核心配置（.env）

```bash
# ============ Redis 配置 ============
# 关键：Server 和 Worker 必须一致
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# Redis 连接池配置（生产环境重要）
REDIS_SOCKET_TIMEOUT=5
REDIS_CONNECT_TIMEOUT=5
REDIS_MAX_RETRY=3

# ============ 任务队列配置 ============
# Worker 最大并发任务数（根据服务器性能调整）
TASK_MAX_JOBS=10

# 单个任务超时时间（秒）- 根据采集任务复杂度调整
TASK_JOB_TIMEOUT=300

# 任务失败重试次数
TASK_MAX_TRIES=3

# 任务结果保留时间（秒）
TASK_KEEP_RESULT=3600

# 健康检查间隔（秒）
HEALTH_CHECK_INTERVAL=30

# ============ NATS 配置 ============
NATS_SERVERS=nats://localhost:4222
NATS_USERNAME=your_nats_username
NATS_PASSWORD=your_nats_password
# NATS_PROTOCOL=tls
# NATS_TLS_CA_FILE=/path/to/ca.pem
```

### 网络拓扑发现契约

- `topology_protocols` 支持 `lldp`、`cdp`、`fdb`、`arp`，用于控制 Stargazer 构建事实时启用的协议集合。
- `topology_fallback_strategy` 是上游 CMDB 的消费策略参数，不由 Stargazer 解析；Stargazer 只负责保留原始 `network_topo` 并额外输出拓扑事实。
- Stargazer 对网络设备始终保留原始 `network_topo` 结果，并额外输出 `network_topology_facts`，不会覆盖原始拓扑。
- 下游 CMDB 会优先使用 `network_topology_facts` 建边，解析不了的链路再回退到 `network_topo`。

### 性能调优

#### 调整并发数

```bash
# 高性能服务器
TASK_MAX_JOBS=50

# 低性能服务器
TASK_MAX_JOBS=5
```

#### 调整超时时间

```bash
# VMware 采集可能需要更长时间
TASK_JOB_TIMEOUT=600
```

#### 多 Worker 实例

```bash
# 启动多个 Worker 进程以提高吞吐量
for i in {1..4}; do
    python start_worker.py &
done
```

---

## 🚢 生产环境部署

### 使用 Supervisor 管理进程（推荐）

#### 1. 安装 Supervisor

```bash
pip install supervisor
```

#### 2. 创建配置文件 `/etc/supervisor/conf.d/stargazer.conf`

```ini
[program:stargazer_worker]
command=/path/to/venv/bin/python /path/to/stargazer/start_worker.py
directory=/path/to/stargazer
user=your_user
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/stargazer/worker.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/path/to/venv/bin"

[program:stargazer_server]
command=/path/to/venv/bin/python /path/to/stargazer/server.py
directory=/path/to/stargazer
user=your_user
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/stargazer/server.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/path/to/venv/bin"
```

#### 3. 启动服务

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start stargazer_worker
sudo supervisorctl start stargazer_server
```

### 使用 Systemd 管理进程

#### 1. 创建 Worker 服务 `/etc/systemd/system/stargazer-worker.service`

```ini
[Unit]
Description=Stargazer ARQ Worker
After=network.target redis.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/stargazer
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python start_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2. 创建 Server 服务 `/etc/systemd/system/stargazer-server.service`

```ini
[Unit]
Description=Stargazer Sanic Server
After=network.target redis.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/stargazer
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 3. 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable stargazer-worker stargazer-server
sudo systemctl start stargazer-worker stargazer-server
sudo systemctl status stargazer-worker stargazer-server
```

---

## 🔍 常用命令

```bash
# 验证配置是否一致
python verify_config.py

# 检查 Redis 和队列状态
python check_redis_status.py

# 查找运行中的 Worker
ps aux | grep start_worker

# 清理旧的任务结果
python clean_old_results.py
```

---

## 📊 监控和维护

### 查看日志

```bash
# Supervisor
sudo supervisorctl tail -f stargazer_worker
sudo supervisorctl tail -f stargazer_server

# Systemd
sudo journalctl -u stargazer-worker -f
sudo journalctl -u stargazer-server -f
```

### 重启服务

```bash
# Supervisor
sudo supervisorctl restart stargazer_worker
sudo supervisorctl restart stargazer_server

# Systemd
sudo systemctl restart stargazer-worker
sudo systemctl restart stargazer-server
```

### 查看队列状态

```bash
# 连接 Redis 查看
redis-cli -h <host> -p <port> -a <password> -n <db>
> KEYS task:running:*    # 查看正在执行的任务
> ZCARD arq:queue        # 查看队列中的任务数
> KEYS arq:result:*      # 查看任务结果
```

### 监控指标

Redis 中的关键键：

- `task:running:{task_id}` - 正在执行的任务
- `arq:queue` - 待执行队列
- `arq:result:{task_id}` - 任务结果

### 清理旧数据

```bash
# 清理旧的任务结果（可选）
python clean_old_results.py
```

---

## 🎯 去重逻辑

- ✅ 任务正在执行时 → 拒绝重复入队
- ✅ 任务已完成 → 允许再次入队
- ✅ 自动清理标记（TTL=360秒）

---

## 🐛 故障排查

### Worker 无法接收任务

**症状**：Server 显示 `enqueue_job returned None`

**排查步骤**：
1. 检查 Worker 是否在运行
   ```bash
   ps aux | grep start_worker
   ```

2. 验证 Redis 配置是否一致
   ```bash
   python verify_config.py
   ```

3. 检查 Redis 连接
   ```bash
   python check_redis_status.py
   ```

4. 查看 Worker 日志是否有错误

### 任务重复执行

**原因**：多个 Worker 实例在运行

**解决方法**：
```bash
# 查找所有 Worker 进程
ps aux | grep start_worker

# 杀掉多余的进程
kill -9 <PID>

# 只保留一个 Worker 运行
```

### 任务无法再次入队

**原因**：运行标记没有被清除

**解决方法**：
```bash
# 手动清除运行标记
redis-cli -h <host> -p <port> -a <password> -n <db>
> DEL task:running:<task_id>

# 或使用脚本清理
python clean_old_results.py
```

### 常见问题速查表

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| enqueue_job 返回 None | Worker 未运行 | 检查 Worker 进程 |
| 任务不重复执行 | 标记未清除 | 查看日志确认清除标记 |
| 配置不一致 | Redis DB 不同 | 运行 verify_config.py |

---

## 🔒 安全建议

1. **使用环境变量**：不要在代码中硬编码密码
2. **限制 Redis 访问**：配置防火墙规则
3. **使用 TLS**：生产环境启用 Redis TLS
4. **日志脱敏**：不要在日志中输出密码
5. **定期更新依赖**：`pip install -U arq sanic`

---

## 💾 备份和恢复

### 备份配置

```bash
# 备份 .env 文件
cp .env .env.backup

# 备份 Redis 数据（如果需要）
redis-cli -h <host> -p <port> -a <password> BGSAVE
```

### 恢复

```bash
# 恢复配置
cp .env.backup .env

# 重启服务
sudo systemctl restart stargazer-worker stargazer-server
```

---

## 📚 项目结构

```
stargazer/
├── api/                    # API 路由
│   ├── collect.py         # 采集任务 API
│   ├── health.py          # 健康检查 API
│   └── monitor.py         # 监控指标 API
├── common/                # 公共模块
│   └── cmp/              # 云管平台集成
├── core/                  # 核心模块
│   ├── config.py         # 配置管理
│   ├── worker.py         # ARQ Worker 配置
│   ├── redis_config.py   # Redis 统一配置
│   └── task_queue.py     # 任务队列管理
├── plugins/               # 采集插件
│   ├── vmware_info.py    # VMware 采集
│   ├── aws_info.py       # AWS 采集
│   ├── aliyun_info.py    # 阿里云采集
│   └── ...               # 其他插件
├── tasks/                 # 任务处理
│   ├── collectors/       # 采集器
│   └── handlers/         # 任务处理器
├── server.py             # Sanic Server 入口
├── start_worker.py       # Worker 启动脚本
└── config.yml            # 应用配置
```

---

## 📄 许可证

[在此添加许可证信息]
