### 说明
采集 Tomcat 的基础配置清单（版本、监听端口、CATALINA 路径、JVM 堆/非堆参数、日志路径与 Java 版本），标准化同步至 CMDB。本插件为 **JOB（SSH 脚本）** 类型，登录目标解析 `server.xml` 与 JVM 启动参数后退出，不修改任何配置。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
- 兼容官方 Tomcat 7.x - 11.x 版本（包括：8.5.x、9.0.x、10.1.x、11.0.x 等）。

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **采集账号与权限**
   - 能执行 `ps` 查看 Tomcat 进程。
   - 能读取 `$CATALINA_HOME/conf/server.xml`。
   - 能执行 `catalina.sh version`、`java -version`。
3. **目标依赖**
   - 目标已安装 Java，`CATALINA_HOME` 可访问。
   - Tomcat 已运行。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **Tomcat**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅 SSH 目标）
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

判断标准：端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP。
- **凭据**：为“未装 Agent”的目标准备 SSH 凭据。
- 设置超时（默认 60s）与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB 的 Tomcat 模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要）。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**Tomcat（tomcat）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名 |
| ip_addr | 主机 IP |
| port | 监听端口（`Connector`） |
| catalina_path | CATALINA 路径 |
| version | Tomcat 版本 |
| xms | JVM 初始堆大小 |
| xmx | JVM 最大堆大小 |
| max_perm_size | 最大非堆/元空间大小 |
| permsize | 初始非堆/元空间大小 |
| log_path | 主日志文件路径 |
| java_version | Java 版本 |

> 补充说明：`xms`、`xmx`、`max_perm_size`、`permsize` 仅在 JVM 启动参数中显式设置时才有值；`version`、`log_path` 在无法解析或对应文件不存在时可能为空。
