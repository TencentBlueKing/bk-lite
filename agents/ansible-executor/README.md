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
cp config.example.yml config.yml
uv sync
uv run python main.py --config ./config.yml
```

## 打包为可执行程序（PyInstaller）

已内置 PyInstaller 打包支持，并且执行 ansible ad-hoc / playbook 时不再依赖外部 `ansible`、`ansible-playbook` 可执行文件，而是通过当前程序自身的内部 helper 子进程调用 `ansible-core`。

```bash
cd agents/ansible-executor
make package
```

产物目录：

```bash
dist/ansible-executor/
```

运行方式：

```bash
cp config.example.yml dist/ansible-executor/config.yml
./dist/ansible-executor/ansible-executor --config ./dist/ansible-executor/config.yml
```

说明：

- 推荐使用 `onedir` 产物，便于携带 ansible 运行时资源
- 推荐使用 `config.yml` 作为 sidecar 探针配置文件，便于排查与版本化管理
- 如果未显式传 `--config`，程序会自动查找当前目录或可执行文件同目录下的 `config.yml` / `config.yaml`
- 仍兼容环境变量注入；适合将敏感信息通过 sidecar 注入，再在 `config.yml` 中使用 `${ENV_VAR}` 引用
- 目标机器仍需具备 ansible 实际运行所需的系统环境，例如 SSH 能力、可访问的 inventory / playbook / 私钥文件等

推荐 sidecar 配置示例：

```yaml
nats:
  servers:
    - nats://127.0.0.1:4222
  username: ${NATS_USERNAME}
  password: ${NATS_PASSWORD}
  protocol: tls
  tls_ca_file: /etc/ansible-executor/ca.pem
  instance_id: default
  connect_timeout: 5

runtime:
  max_workers: 4
  callback_timeout: 10
  work_dir: /var/lib/ansible-executor/work
  state_db_path: /var/lib/ansible-executor/task_state.db

jetstream:
  namespace: bk.ans_exec
  max_deliver: 5
  ack_wait: 300
  backoff: [5, 15, 30, 60]
  dlq_subject: bk.ans_exec.tasks.dlq
```

兼容的环境变量模式仍保留，便于迁移，但不再推荐作为主配置方式。

## 任务执行可靠性

- JetStream 开启 `backoff` 时，服务会以 `backoff[0]` 作为实际 ack deadline，并据此计算 `in_progress()` 心跳频率
- 本地任务状态会记录 `execution_status`、`callback_status`、`lease_owner`、`lease_expires_at`、`heartbeat_at`、`execution_attempt`
- 当消息重复投递但旧 worker 的 lease 仍有效时，新 worker 不会重复执行同一 `task_id`
- callback 重试状态与执行状态分离，避免 callback 失败把原始执行结果错误覆盖

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
