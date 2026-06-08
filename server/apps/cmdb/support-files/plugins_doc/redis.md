### 说明
基于脚本（JOB）在目标主机上发现 Redis 实例，采集版本、端口与关键配置（含主从/拓扑识别），标准化同步至 CMDB。采集为只读，不修改目标任何配置。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 兼容常见主流 Redis 版本；`username`（ACL 账号）需 Redis 6+ 支持，建议以实际部署版本为准。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **目标依赖**
   - 主机已启动 Redis，安装目录可读，目标主机存在 `redis-cli`。
   - 多实例需分别监听独立端口。
3. **采集权限**
   - 脚本通过 `redis-cli` 执行 `PING` / `INFO` / `CONFIG GET` / `CLUSTER` / `SENTINEL` 等只读命令。
   - 若 Redis 启用了 `requirepass` 或 ACL，需提供对应口令（密码经 `REDISCLI_AUTH` 环境变量注入，不写入命令行明文）。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **Redis**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅 SSH 目标）
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

判断标准：端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP。
- **凭据**：为“未装 Agent”的目标准备 SSH 凭据；如 Redis 有访问控制，填写 Redis 端口与口令（及 ACL 用户名）。
- 设置超时与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB Redis 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：Redis ACL 登录用户名（可选，Redis 6+ 支持）。
- `password`：Redis 访问口令。落库自动加密，下发时以环境变量（`REDISCLI_AUTH`）注入，不写入明文配置文件或命令行。
- `port`：Redis 监听端口，默认 `6379`。

### 采集内容
**Redis（redis）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（`{ip}-redis-{port}`） |
| ip_addr | 主机内网 IP |
| port | Redis 监听端口 |
| version | Redis 版本 |
| install_path | 安装路径（进程可执行文件父目录） |
| max_conn | 最大连接数（`CONFIG GET maxclients`） |
| max_mem | 限制最大内存（`CONFIG GET maxmemory`，0 表示未限制） |
| database_role | 实例角色（master / slave，来自 `INFO replication`） |
| topo_mode | 拓扑模式：standalone / replication / sentinel / cluster |
| cluster_uuid | 集群标识 |
| slaves | 从节点列表（master 时） |
| master | 主节点地址（slave 时） |

> 补充说明：`slaves` 仅在实例为 master 时有值，`master` 仅在实例为 slave 时有值；拓扑相关字段依赖 `CLUSTER` / `SENTINEL` 命令返回，单机部署时 `topo_mode` 为 `standalone`，集群外字段可能为空。
