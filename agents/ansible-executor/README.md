# ansible-executor

基于 Python 的轻量 NATS RPC 服务，用于执行 ansible ad-hoc 命令与 playbook。

## 设计目标

- 与现有 `server/apps/rpc/executor.py` 调用风格保持一致（`{namespace}.{instance_id}`）
- 保持最小实现：仅提供 ansible 场景所需 RPC
- 默认不改动现有 `nats-executor`，作为独立服务并行存在

## RPC Subject

- `ansible.adhoc.{instance_id}`：执行 ansible ad-hoc
- `ansible.playbook.{instance_id}`：执行 ansible-playbook
- `ansible.task.query.{instance_id}`：查询任务状态

## 请求/响应契约

请求体遵循现有 RPC 载荷：

```json
{
  "args": [
    {
      "inventory": "127.0.0.1,",
      "hosts": "all",
      "module": "ping",
      "module_args": "",
      "extra_vars": {
        "k": "v"
      },
      "execute_timeout": 60
    }
  ],
  "kwargs": {}
}
```

响应体与 `nats_client.request` 兼容：

```json
{
  "success": true,
  "result": "...",
  "instance_id": "default"
}
```

失败时：

```json
{
  "success": false,
  "result": "...",
  "error": "...",
  "instance_id": "default"
}
```

## 快速启动

```bash
cd agents/ansible-executor
cp .env.example .env
uv sync
uv run python main.py
```

关键 NATS 配置（支持 TLS CA）：

```bash
# NATS 地址（可多个，逗号分隔）
NATS_SERVERS=nats://localhost:4222
# NATS 认证用户名/密码（无认证可留空）
NATS_USERNAME=your_nats_username
NATS_PASSWORD=your_nats_password
# NATS_PROTOCOL=tls
# NATS_TLS_CA_FILE=/path/to/ca.pem
# RPC 实例后缀（subject 中使用）
NATS_INSTANCE_ID=default
# NATS 建连超时（秒）
NATS_CONNECT_TIMEOUT=5
# 执行 worker 并发数
ANSIBLE_MAX_WORKERS=4
# 回调 RPC 超时（秒）
ANSIBLE_CALLBACK_TIMEOUT=10
# 临时工作目录（任务文件落盘位置）
ANSIBLE_WORK_DIR=/tmp/ansible-executor
# JetStream 命名空间（其余 stream/subject 默认从这里派生）
ANSIBLE_JS_NAMESPACE=bk.ans_exec
# 任务最大重投递次数
ANSIBLE_JS_MAX_DELIVER=5
# ACK 等待时长（秒）
ANSIBLE_JS_ACK_WAIT=300
# 重试退避策略（秒）
ANSIBLE_JS_BACKOFF=5,15,30,60
# 死信队列 subject
ANSIBLE_DLQ_SUBJECT=bk.ans_exec.tasks.dlq
# 本地任务状态库路径
ANSIBLE_STATE_DB_PATH=/tmp/ansible-executor/task_state.db
```

## Docker（可选）

```bash
cd agents/ansible-executor
docker build -t bklite/ansible-executor -f support-files/Dockerfile .
```

## 目录结构（参考 stargazer 分层）

```text
ansible-executor/
├── core/
│   └── config.py
├── service/
│   ├── ansible_runner.py
│   └── nats_service.py
├── support-files/
│   ├── Dockerfile
│   ├── service.conf
│   └── startup.sh
└── main.py
```
