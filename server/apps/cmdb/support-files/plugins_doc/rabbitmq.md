### 说明
采集 RabbitMQ 的基础配置清单（版本、各协议端口、节点名、日志/配置路径、已启用插件文件与 Erlang 版本），标准化同步至 CMDB。本插件为 **JOB（SSH 脚本）** 类型，登录目标调用 `rabbitmqctl status` 解析后退出，不修改任何配置。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 兼容官方 RabbitMQ 3.6.x 到 4.0.x 版本（包括：3.8.x、3.9.x、3.10.x、3.12.x、4.0.x 等）。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **采集账号与权限**
   - 能执行 `rabbitmqctl status`（通常需以 RabbitMQ 运行用户或 root 身份执行，且 `~/.erlang.cookie` 可读）。
   - **Erlang Cookie 权限**：执行 `rabbitmqctl status` 需读取 `~/.erlang.cookie`（通常仅 RabbitMQ 运行用户可读）。RabbitMQ 一般以 `rabbitmq` 用户启动，建议采集凭据填该用户，或用 root；否则可能取不到数据。
   - 能读取 `/proc/<pid>/environ`、`/proc/<pid>/cmdline`。
3. **目标依赖**
   - 目标上 `rabbitmqctl` 可执行，RabbitMQ 已启动。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **RabbitMQ**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅 SSH 目标）
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

判断标准：端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP。
- **凭据**：为“未装 Agent”的目标准备 SSH 凭据。注意账号需满足执行 `rabbitmqctl status` 的权限要求（见前置要求）。
- 设置超时（默认 60s）与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB 的 RabbitMQ 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要）。建议使用能执行 `rabbitmqctl status` 的账号。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**RabbitMQ（rabbitmq）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名 |
| ip_addr | 主机 IP |
| port | 主监听端口 |
| allport | 各协议端口汇总 |
| node_name | 节点名称（集群标识） |
| log_path | 日志文件路径 |
| conf_path | 配置文件路径 |
| version | RabbitMQ 版本 |
| enabled_plugin_file | 已启用插件文件路径 |
| erlang_version | Erlang 运行环境版本 |

> 补充说明：各字段均依赖 `rabbitmqctl status` 输出及进程环境变量/启动参数解析，无法解析到时可能为空。
