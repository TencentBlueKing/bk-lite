### 说明
基于脚本（PowerShell）采集 Windows IIS 的版本、站点与应用绑定端口、应用程序池、虚拟目录与物理路径等信息，并标准化同步至 CMDB。采集为只读，不修改目标任何配置。

> **【BETA / 未测试】** 本插件尚未经过完整环境验证，字段解析逻辑可能与你的实际部署存在差异，请在生产使用前先小范围试采并核对结果。

### 执行方式
本插件**仅适用于 Windows**，为 **JOB（PowerShell 脚本）** 类型，经 WinRM/Agent 执行（WinRM 是 Windows 远程管理协议，作用类似 Linux 的 SSH）：

| 目标情况 | 执行方式 | 是否需要凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行 PowerShell 采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **远程回退**：经 WinRM 连入目标执行 PowerShell 脚本 | 需要 |

> 一句话：装了 Agent 的 Windows 机器零凭据即可采集；未装的依赖你填写的账号经 WinRM 远程采集。

### 版本兼容性
- 适用于以 PowerShell 方式可识别的 Windows IIS 实例；不同 Windows/IIS 版本的注册表项与配置写法可能有差异，请以实际试采结果为准。

### 前置要求
1. **平台**
   - 仅 Windows。
2. **网络与连通**
   - 远程目标：接入点到目标的 WinRM 端口连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
3. **采集账号与权限（仅远程时需要）**
   - `appcmd.exe` 可用，通常位于 `C:\Windows\System32\inetsrv\`。
   - 可读取注册表 IIS 相关项，版本号读取自注册表 `HKLM\SOFTWARE\Microsoft\InetStp`（通常需要管理员权限）。
4. **目标依赖**
   - 目标已安装并启用 IIS。
   - PowerShell 5+。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **IIS**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅远程目标）
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 5985`

判断标准：WinRM 端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP 段（支持 CIDR、逗号分隔、区间）。
- **凭据**：为“未装 Agent”的目标准备管理员凭据（可配置多组，逐个轮试并记录命中）。
- 设置超时与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB 对应模型下应能查询到实例。

### 凭据字段说明
- `username`：登录用户名（仅远程目标需要），需具备读取 IIS 配置与注册表的管理员权限。
- `password`：上述账号的密码。落库自动加密，下发时注入，不写入明文配置文件。
- `port`：连接端口（WinRM，默认 `5985`）。

### 采集内容
| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名 |
| ip_addr | 主机内网 IP |
| port | 站点绑定的 HTTP 端口 |
| version | IIS 版本（注册表 InetStp） |
| website | 站点名称 |
| webapp | 应用程序名称 |
| virdir | 虚拟目录 |
| apppool | 应用程序池 |
| apppool_count | 应用程序池数量 |
| webapp_count | 应用程序数量 |
| phys_path | 物理路径 |
| configfile | 配置文件路径（`applicationHost.config`） |
| max_concur_connect | 最大并发连接数 |
| server_name | 服务器名称 |

> 补充说明：当 `appcmd.exe` 不可用、或无权读取注册表/配置时，相关字段可能为空。本插件为 **BETA / 未测试**，请核对结果后再投入使用。
