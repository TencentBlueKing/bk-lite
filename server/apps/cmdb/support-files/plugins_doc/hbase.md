### 说明
【BETA】基于脚本（JOB）在目标主机上发现 HBase Master 进程，解析启动参数与 `hbase-site.xml` 配置，采集版本、端口、安装路径、日志路径、Java 信息与关键运行参数，标准化同步至 CMDB。采集为只读，不修改目标任何配置。

> 当前仅发现并采集目标主机上**运行中的 HBase Master 实例**，不采集 RegionServer / Backup Master / 集群拓扑。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 面向 Linux 环境下的 HBase Master 实例发现；兼容常见主流 HBase 版本，建议以实际部署版本为准。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **目标依赖**
   - 主机上运行有 HBase Master 进程；已正确安装 Java，且配置 `JAVA_HOME`。可执行 `echo $JAVA_HOME`、`java -version` 确认。
3. **采集权限**
   - 可读取 `hbase-site.xml`，可执行 `hbase version`（依赖 `JAVA_HOME`）。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **HBase**，点击“新增任务”。

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
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB HBase 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要）。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**HBase（hbase）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（`{ip}-hbase-{port}`） |
| ip_addr | 主机内网 IP |
| port | HBase Master 服务端口（`hbase.master.port`，默认 `16000`） |
| version | HBase 版本（`hbase version`） |
| install_path | 安装路径 |
| log_path | 日志目录 |
| config_file | `hbase-site.xml` 配置文件绝对路径 |
| tmp_dir | 临时目录 |
| cluster_distributed | 是否分布式部署 |
| java_path | Java 可执行文件路径 |
| java_version | Java 版本 |

> 补充说明：当前脚本只发现本机运行中的 HBase Master 实例，不采集 RegionServer、Backup Master、ZooKeeper 拓扑或 HDFS 关系；若未找到 `hbase` 可执行文件，则本次采集返回空结果。
