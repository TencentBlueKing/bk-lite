### 说明
【BETA】基于脚本（JOB）在目标主机上发现 MongoDB 实例，读取 `mongod` 进程与配置文件，采集版本、端口与基础配置，标准化同步至 CMDB。采集为只读，不修改目标任何配置。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 兼容常见主流 MongoDB 版本；建议以实际部署版本为准。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **目标依赖**
   - 主机上运行有 `mongod` 进程，配置文件（默认 `/etc/mongod.conf`）可读。
   - `mongo` shell 是可选的：无 mongo shell 时仍可采集基础信息，仅 `database_role`（主/从角色，依赖 `rs.status()`）可能为空，不影响任务成功。
3. **采集权限**
   - 可读取 `mongod` 进程信息与配置文件即可；`mongo` shell 仅用于采集副本集角色，可选。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **MongoDB**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅 SSH 目标）
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

判断标准：端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP。
- **凭据**：为“未装 Agent”的目标准备 SSH 凭据。
- 设置超时与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB MongoDB 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要）。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**MongoDB（mongodb）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（`{ip}-mongodb-{port}`） |
| ip_addr | 主机内网 IP |
| port | MongoDB 监听端口 |
| version | MongoDB 版本（`mongod --version`） |
| bin_path | 可执行文件路径 |
| mongo_path | mongo 路径 |
| config | 配置文件路径（默认 `/etc/mongod.conf`） |
| fork | 是否以后台进程方式启动 |
| system_log | 系统日志配置 |
| db_path | 数据目录 |
| max_incoming_conn | 最大入站连接数 |
| database_role | 实例角色（`rs.status()`） |

> 补充说明：`database_role` 依赖 mongo shell 执行 `rs.status()`，shell 不可用或非副本集部署时可能为空；配置类字段在目标配置文件未配置对应项时可能为空。
