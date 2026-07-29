### 说明

PC 发现插件用于采集 Windows / macOS 个人电脑的基础配置、操作系统信息和系统级安装软件，并同步到 CMDB：

- PC 基础信息写入 `pc` 模型；
- 安装软件写入 `pc_software` 模型；
- 软件通过 `install_on` 关系关联到对应 PC。

采集过程为**只读**，不会安装、卸载或启动软件，不会修改注册表、文件和系统配置。

> 当前产品边界：同一台 PC 只应配置在一个 PC 采集任务中。请避免多个任务的 IP 范围重叠。

---

### 执行方式

本插件为 **JOB（脚本）** 类型，任务实际在所选接入点上执行：

| PC 操作系统 | 连接方式 | 默认端口 | 采集脚本 |
| :--- | :--- | :--- | :--- |
| Windows | WinRM | `5986/HTTPS` | PowerShell |
| macOS | SSH | `22` | Shell + 系统内置命令 |

一个任务只能采集一种操作系统，任务创建后不能在 Windows 和 macOS 之间切换。如需采集两种系统，请分别创建两个任务。

### “同步最新结果”是什么意思

任务列表中的 **同步最新结果** 会查询采集器已经上报到平台的最新 PC 快照，并将其同步到 CMDB；它**不会立即发起一轮新的 WinRM / SSH 远程采集**。

建议操作顺序：

1. 保存任务，等待采集器按配置完成远程采集并上报；
2. 在列表的“数据上报时间”确认已有新数据；
3. 点击“同步最新结果”，或等待任务按周期自动同步；
4. 如果提示“未发现 PC 最新上报结果”，请先检查远程连接、凭据、采集周期和数据上报时间。

---

### 前置要求

#### 通用要求

1. 接入点节点正常在线，并能够访问目标 PC。
2. 目标 IP 范围只包含当前任务所选操作系统。
3. 目标防火墙允许对应的 WinRM 或 SSH 端口。
4. PC 的硬件 UUID 或整机序列号至少有一个有效值，否则无法生成稳定资产身份。UUID
   必须是标准 `8-4-4-4-12` 十六进制格式；格式异常或属于全零、全 `F` 占位值时，
   系统自动回退整机序列号。

#### Windows

1. 目标已启用 WinRM。
2. 推荐使用 `5986/HTTPS`；仅在受信网络中使用 `5985/HTTP`。
3. 账号需具备远程 WinRM 登录、读取 CIM/WMI 信息以及读取 HKLM Uninstall 注册表项的权限。
4. PowerShell 版本建议为 5.1 或更高。

接入点连通性自测：

```bash
nc -vz <pc_ip> 5986
```

Windows PowerShell 自测：

```powershell
Test-NetConnection <pc_ip> -Port 5986
```

#### macOS

1. 在“系统设置 → 通用 → 共享”中开启“远程登录”。
2. SSH 账号需被允许远程登录。
3. 普通账号通常可以读取本插件需要的硬件、系统和 `/Applications` 应用信息，无需 sudo。

接入点连通性自测：

```bash
nc -vz <pc_ip> 22
```

---

### 创建任务

#### 步骤 1：进入操作入口

1. 进入“CMDB → 管理 → 自动发现”。
2. 选择“主机逻辑主机 → PC 发现”。
3. 点击“新增任务”。

#### 步骤 2：选择操作系统和目标

- **操作系统**：选择 Windows 或 macOS；
- **IP 范围**：填写目标 IP、CIDR 或 IP 区间；
- **接入点**：选择能够访问目标 PC 的节点；
- **超时时间**：单台 PC 建议配置为 `120` 秒，可按网络情况调整；
- **采集周期**：根据资产更新频率设置。

#### 步骤 3：填写凭据

可配置多组凭据，系统按顺序尝试；命中成功后会优先复用。

**Windows WinRM**

| 字段 | 说明 |
| :--- | :--- |
| username | Windows 本地账号、域账号或 UPN，例如 `DOMAIN\user` |
| password | 登录密码，入库加密，下发时通过环境变量注入 |
| port | HTTPS 默认 `5986`；HTTP 默认 `5985` |
| scheme | 推荐 `https` |
| transport | 当前使用 `ntlm` |
| certValidation | 是否校验 HTTPS 证书；生产环境建议开启 |

> 使用 HTTP 会明文传输认证信息，只建议用于隔离且受信的网络。关闭证书校验可能受到中间人攻击。

**macOS SSH**

| 字段 | 说明 |
| :--- | :--- |
| username | 允许远程登录的 macOS 用户 |
| port | SSH 端口，默认 `22` |
| authType | 密码或 PEM 私钥，二选一 |
| password | 密码认证时填写 |
| private_key | 私钥认证时填写 PEM 格式私钥 |
| passphrase | 私钥受密码保护时填写 |

凭据秘密不会写入 VictoriaMetrics 标签或节点参数 headers。

#### 步骤 4：测试连接

在保存前点击“测试连接”：

- 测试只读取 PC 身份信息；
- 不扫描安装软件；
- 不写入 CMDB；
- 成功后再保存任务。

---

### PC 采集内容

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 稳定实例名，优先由硬件 UUID 生成，无效时回退序列号 |
| host_name | PC 主机名 |
| ip_addr | 本次任务实际连接的目标 IP |
| os_type | `windows` 或 `macos` |
| os_name | 操作系统名称 |
| os_version | 操作系统版本 |
| os_build | 系统构建版本 |
| architecture | 系统架构 |
| hardware_uuid | 规范化硬件 UUID（标准 `8-4-4-4-12` 十六进制格式） |
| serial_number | BIOS / 整机序列号 |
| brand | 设备厂商 |
| device_model | 设备型号 |
| cpu | CPU 型号 |
| men | 物理内存总容量（字节） |
| disk | 本地磁盘总容量（字节） |
| logged_in_user | 当前登录用户 |
| last_collect_time | 最新快照的数据上报时间 |

`asset_code`、使用人、位置等人工维护字段不在采集白名单中，不会被 PC 发现覆盖。

---

### 安装软件采集内容

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 软件稳定实例名 |
| name | 软件名称 |
| version | 软件版本 |
| publisher | 发布者；macOS 可能为空 |
| software_key | 软件稳定标识 |
| product_id | Windows 产品/注册表键或 macOS Bundle ID |
| install_location | 安装路径 |
| install_date | 安装日期；来源未提供时为空 |
| architecture | 软件架构 |
| source | `windows_registry` 或 `macos_application` |
| last_collect_time | 最新快照的数据上报时间 |

Windows 读取 HKLM 的 64 位和 32 位 Uninstall 视图，并排除系统组件、KB 补丁、语言包和驱动。

macOS 只扫描：

- `/Applications`
- `/Applications/Utilities`

不会扫描用户目录、`/System/Applications` 或安装收据。

---

### 软件清理规则

软件删除受完整快照安全门保护：

1. 快照状态必须为 `complete`；
2. 软件错误数必须为 `0`；
3. 实际软件条数必须与快照声明条数一致；
4. 软件实体和 `install_on` 关联必须全部写入成功。

只有满足以上条件，系统才会按所选清理策略处理已经不在最新快照中的软件。

| 清理策略 | 行为 |
| :--- | :--- |
| 不清理 | 仅新增和更新，不自动删除软件 |
| 立即清理 | 只对当前 PC 的关联软件做差集删除 |
| 过期清理 | 超过配置天数后清理该任务下的过期软件 |

部分快照不会删除软件。删除任务只删除调度和节点配置，不会级联删除已经写入 CMDB 的 PC 或软件资产。

---

### 任务状态

| 状态 | 含义 |
| :--- | :--- |
| 成功 | 所有 PC 快照完整且 CMDB 写入成功 |
| 部分成功 | 存在 partial 快照，或部分 PC / 软件写入失败 |
| 失败 | 所有目标失败，或没有查询到任何 PC 最新快照 |

完整的“零软件”快照是合法结果：它表示该 PC 当前没有可识别的系统级安装软件。

---

### 常见问题

#### 连接测试失败

- `TARGET_UNREACHABLE`：检查接入点到目标 IP/端口的路由和防火墙；
- `WINRM_AUTH_FAILED`：检查 Windows 用户名、密码和远程登录权限；
- `WINRM_TLS_FAILED`：检查 HTTPS 证书、主机名和证书校验设置；
- `SSH_AUTH_FAILED`：检查 macOS 用户、密码或允许远程登录的用户列表；
- `SSH_KEY_INVALID`：检查私钥 PEM 内容和密码短语；
- `SCRIPT_TIMEOUT`：检查网络延迟，适当增加单台超时；
- `PC_IDENTITY_INVALID`：硬件 UUID 与序列号均无效，需先修复设备固件身份信息；
- `SCRIPT_OUTPUT_INVALID`：目标脚本输出异常，请检查系统命令是否可用并查看 Stargazer 日志。

#### 点击“同步最新结果”后没有新资产

1. 查看“数据上报时间”是否更新；
2. 确认采集周期已经到达；
3. 检查接入点与 Stargazer 是否在线；
4. 检查任务 IP 范围、操作系统和凭据是否匹配；
5. 先执行“测试连接”排除连通与认证问题。

#### 软件没有被删除

这是安全保护的预期行为。快照为 partial、软件计数不一致或关联写入失败时，系统宁可保留旧软件，也不会执行可能误删数据的差集清理。
