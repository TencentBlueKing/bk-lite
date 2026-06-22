### 说明
【BETA】基于脚本（JOB）在目标主机上发现 Elasticsearch 实例，读取 `elasticsearch.yml` 与进程信息，采集版本、端口与关键配置，标准化同步至 CMDB。采集为只读，不修改目标任何配置。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 兼容常见主流 Elasticsearch 版本；建议以实际部署版本为准。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **目标依赖**
   - 主机上运行有 Elasticsearch 进程，已正确安装 Java。可在目标执行 `java -version` 确认；脚本依赖 Java 解析 ES 的 jar 包获取版本，若无 Java 则 `version` 字段可能为空（不影响其他字段）。
3. **采集权限**
   - 可读取 `elasticsearch.yml` 配置文件与进程信息。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **Elasticsearch**，点击“新增任务”。

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
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB Elasticsearch 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要）。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**Elasticsearch（es）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（`{ip}-es-{port}`） |
| ip_addr | 主机内网 IP |
| port | HTTP 端口（`http.port`，默认 `9200`） |
| version | ES 版本（从 `lib/elasticsearch-*.jar` 解析） |
| install_path | 安装路径 |
| conf_path | 配置文件路径 |
| java_path | Java 可执行文件路径 |
| java_version | Java 版本 |
| cluster_name | 集群名称 |
| node_name | 节点名称 |
| is_master | 是否为 master 节点 |
| data_path | 数据目录 |
| log_path | 日志目录 |

> 补充说明：配置类字段在目标 `elasticsearch.yml` 未配置对应项时可能为空；`version` 依赖从 `lib/elasticsearch-*.jar` 文件名解析，若安装目录结构不符则可能为空。
