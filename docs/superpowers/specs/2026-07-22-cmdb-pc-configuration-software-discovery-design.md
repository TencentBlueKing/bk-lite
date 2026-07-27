# CMDB PC 配置与软件发现设计

日期：2026-07-22

状态：设计已确认，待用户文档评审

## 1. 背景

企业版 CMDB 需要新增 PC 配置与安装软件发现能力。PC 是新的配置采集对象，首版只覆盖 Windows 与 macOS；Agent、WinRM、WMI、SSH 只是连接或执行方式，不是四种独立采集产品。

现有代码已经具备可复用的配置采集主干：

```text
CMDB CollectModels
  → NodeParams / Telegraf HTTP 输入
  → Stargazer /api/collect/collect_info
  → ARQ Worker
  → CollectionService / PluginExecutor
  → NATS / VictoriaMetrics
  → CMDB 插件格式化与 Graph 写入
```

相关现状如下：

- `agents/stargazer/plugins/script_executor.py` 的 `SSHPlugin` 已按节点信息分流到 `local.execute` 或 `ssh.execute`。
- `agents/stargazer/tasks/collectors/host_collector.py` 已通过 `ansible_adhoc` 和 Ansible Executor 支持 WinRM。
- `agents/stargazer/tasks/collectors/host_wmi_collector.py` 已支持 WMI/DCOM，但当前用于监控采集。
- `server/apps/cmdb/node_configs/base.py` 与 `NodeParamsFactory` 已提供统一任务下发入口。
- `server/apps/cmdb/collection/metrics_cannula.py` 和 `common.py` 当前按 `inst_name` 对账，但清理粒度是任务与模型，无法表达单台 PC 的完整/部分快照。
- `server/apps/cmdb/collection/change_records.py` 当前只记录自动采集的新增和更新，删除实例没有变更记录。
- `server/apps/cmdb/support-files/model_config.xlsx` 已存在 `pc` 模型，但没有安装软件字段或 `pc_software` 模型。

本设计在现有主干内新增 PC 专用采集插件和逐 PC 快照对账，不新增协议服务、调度系统、NATS Subject 或结果存储链路。

## 2. 目标

1. 通过 WinRM 采集 Windows PC 配置、硬件和系统级安装软件。
2. 通过 SSH 采集 macOS PC 配置、硬件和系统级安装软件。
3. Windows 与 macOS 统一写入 `pc` 和 `pc_software` 模型。
4. 使用稳定的 `inst_name` 对 PC 和软件实例进行幂等对账。
5. 软件升级只更新版本；完整快照可以安全识别卸载，部分或失败快照不得误删。
6. 严格保护人工资产字段，不因自动采集覆盖资产管理员维护的数据。
7. 一台 PC 同一时间只由一个权威采集任务写入和执行删除。
8. 前端复用现有配置采集抽屉、基础表单、凭据池和高级设置交互。
9. 所有远程脚本必须只读、内置、版本化并具备资源边界。

## 3. 非目标

- Linux 和实际对应的鸿蒙 OS 场景。
- Agent 本地采集。
- WMI/DCOM 采集。
- 协议自动探测、失败降级和自动切换。
- 同一任务混合 Windows 与 macOS。
- 用户级软件、Windows Store/AppX、补丁、驱动和系统组件。
- macOS 系统应用、`pkgutil` 历史收据、开发依赖和用户私有应用。
- 软件许可证、授权合规、漏洞扫描、使用频率和进程监控。
- 用户自定义 PowerShell 或 Shell。
- 自动抢占权威采集任务。
- 全面重构通用 JOB/SSH 执行器。

## 4. 已选方案

采用单一 PC 插件与 PC 专用编排采集器：

```text
一个 PC 配置采集入口
一个 PCNodeParams
一个 pc/plugin.yml
一个 PCInventoryCollector
两份内置只读脚本
```

执行分支：

```text
Windows
  → pc_windows_discover.ps1
  → PCInventoryCollector
  → 既有 ansible_adhoc
  → Ansible Executor / WinRM

macOS
  → pc_macos_discover.sh
  → PCInventoryCollector
  → 既有 SSHPlugin
  → ssh.execute
```

两个分支都属于脚本采集，任务 `driver_type` 保持 `job`。`PCInventoryCollector` 只负责选择既有连接执行能力和统一输出，不实现新的 WinRM/SSH 客户端。

### 4.1 不采用的方案

不拆成 `pc_windows`、`pc_macos` 两种 CMDB 模型。两者都是 PC，仅操作系统不同；拆分会与现有 `model_id + driver_type` 注册、状态查询和对象树语义冲突。

不在首版把 `SSHPlugin` 全面改造成通用 RemoteScriptExecutor。该重构会扩大到现有主机、中间件和数据库插件，回归面超过 PC 需求范围。

不直接复用监控 HostCollector 的指标结果。Windows 分支复用其底层 `ansible_adhoc`/WinRM 执行能力，但 PC 插件使用自己的只读脚本、结构化输出和快照语义。

## 5. 任务粒度与协议

一个采集任务只能选择一种目标 OS：

| 目标 OS | 固定连接方式 | 脚本类型 |
|---|---|---|
| Windows | WinRM | PowerShell |
| macOS | SSH | Shell |

选择 OS 后连接方式自动锁定，用户不再单独选择协议。任务创建后 OS 不可直接修改；需要变更时复制并创建新任务。

一个任务可以包含多台同类型 PC，目标继续复用现有配置采集的 IP 范围或已有资产选择。Windows 与 macOS 的结果都写入同一个 `pc` 与 `pc_software` 模型。

## 6. PC 身份

CMDB 继续使用 `inst_name` 作为 PC 实例唯一标识和对账键，不新增另一套 `device_uid` 主身份。

生成规则：

```text
Windows：WIN-<标准化 Win32_ComputerSystemProduct.UUID>
macOS：  MAC-<标准化 IOPlatformUUID>
```

UUID 无效时回退设备序列号：

```text
Windows：WIN-SN-<标准化 BIOS SerialNumber>
macOS：  MAC-SN-<标准化 Serial Number>
```

标准化规则：

- 去除首尾空白、包围 UUID 的花括号和不可见字符。
- UUID 转为大写并保留连字符。
- 序列号转为大写，规范内部空白。
- 拒绝全零 UUID、空值和已知厂商默认占位值。
- UUID 和序列号都无效时返回 `PC_IDENTITY_INVALID`，不创建或更新 PC。

IP、主机名和用户名都是可变属性，不参与 `inst_name`：

```text
inst_name      = WIN-4C4C4544-0038-...
host_name      = FINANCE-PC-01
ip_addr        = 192.168.1.56
logged_in_user = DOMAIN\lisi
```

## 7. 数据模型

### 7.1 `pc`

保留现有人工资产字段。自动采集字段如下：

| 字段 ID | 含义 | 更新来源 |
|---|---|---|
| `inst_name` | PC 唯一实例名 | OS 前缀与稳定硬件身份 |
| `host_name` | 系统主机名 | PowerShell/Shell |
| `ip_addr` | 本次实际连接 IP | 任务目标 |
| `os_type` | `windows` 或 `macos` | 任务与脚本 |
| `os_name` | 操作系统名称 | 系统信息 |
| `os_version` | 系统版本 | 系统信息 |
| `os_build` | 系统构建号 | 系统信息 |
| `architecture` | x64、arm64 等 | 系统信息 |
| `hardware_uuid` | 原始硬件 UUID | CIM/IOPlatformUUID |
| `serial_number` | 设备序列号 | BIOS/Apple Hardware |
| `brand` | 厂商 | 复用现有字段 |
| `device_model` | 设备型号 | 系统信息 |
| `cpu` | CPU 摘要 | 复用现有字段 |
| `men` | 内存字节数 | 复用现有字段，不在本次重命名 |
| `disk` | 磁盘容量摘要 | 复用现有字段 |
| `logged_in_user` | 当前登录账号 | 系统会话信息 |
| `last_collect_time` | 最近成功或部分成功时间 | CMDB 对账器 |

快照控制字段不作为长期普通资产字段展示。任务与采集系统继续负责执行状态和错误详情。

### 7.2 字段所有权

自动采集严格使用白名单，只更新上一节定义的采集字段。

以下人工资产字段不得被自动采集覆盖：

- 资产编号、组织、部门。
- 资产使用人、领用时间和存放位置。
- 采购时间、采购成本、使用年限和到期时间。
- 资产价值、备注、资产状态和外观盘点信息。

资产使用人与当前登录账号必须分离：

```text
user           = 人工维护的资产使用人
logged_in_user = 自动采集的当前登录账号
```

新发现 PC 只写采集字段；已有 PC 只提交白名单字段，不使用空对象全量覆盖实例。

### 7.3 `pc_software`

每个已安装软件是一条独立实例：

| 字段 ID | 含义 |
|---|---|
| `inst_name` | 软件实例唯一标识 |
| `name` | 软件名称 |
| `version` | 当前版本 |
| `publisher` | 发布者/厂商 |
| `software_key` | 规范化稳定标识 |
| `product_id` | Windows ProductCode/卸载键或 macOS Bundle/Package ID |
| `install_location` | 安装位置，可为空 |
| `install_date` | 安装日期，可为空 |
| `architecture` | x86、x64、arm64、universal，可为空 |
| `source` | `windows_registry`、`macos_application` 等来源 |
| `last_collect_time` | 最近发现时间 |

软件稳定标识：

```text
Windows：normalized(name) + normalized(publisher)
macOS：优先 Bundle Identifier；缺失时 normalized(name) + normalized(publisher)
```

软件实例名输入：

```text
PC.inst_name + 软件稳定标识
```

使用固定规范化版本计算 SHA-256，并取前 32 位大写十六进制：

```text
SW-8F6A1D93C2E741B76BB57AC50F25D182
```

版本号不参与唯一标识。同一 PC 上软件升级只更新 `version`，不删除旧实例后新建。

### 7.4 PC 与软件关系

定义：

```text
pc 1:N pc_software
关系含义：安装软件
```

完整软件清单不存入 PC 的 JSON/文本属性。PC 详情通过关联查询展示“安装软件”页签，可以计算 `software_count`，但该计数不是第二份软件清单权威数据。

每个 `pc_software` 实例只属于一台 PC。删除差集必须从当前 PC 的关联软件集合计算，不得按整个任务或整个模型清理。

## 8. 软件采集范围

### 8.1 Windows

通过只读 PowerShell 读取：

```text
HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall
HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall
```

仅保留 `DisplayName` 非空的系统级用户可见应用，规范化名称、发布者和版本后去重。

排除：

- `SystemComponent=1`。
- Windows Update、KB 补丁和语言包。
- 驱动程序、卸载子组件和附属记录。
- Windows Store/AppX 系统包。
- 用户私有注册表软件。

禁止使用 `Win32_Product`，避免触发 MSI 一致性检查或修复安装。

### 8.2 macOS

通过只读 Shell 扫描：

```text
/Applications/*.app
/Applications/Utilities/*.app
```

从 `Info.plist` 提取应用名、短版本、构建版本、Bundle Identifier、安装位置和可用架构信息。

排除：

- `/System/Applications` 内置系统应用。
- Framework、Extension、Driver。
- `pkgutil --pkgs` 历史安装收据。
- Homebrew formula、Python/npm 等开发依赖。
- `/Users/*/Applications` 用户私有应用。

首版仅承诺稳定的系统级用户可见应用完整快照。

## 9. 统一采集输出协议

Windows 与 macOS 脚本统一返回：

```json
{
  "success": true,
  "snapshot_status": "complete",
  "snapshot_id": "5ea76c94-3e87-4b37-a4e2-13099c3f8305",
  "result": {
    "pc": [
      {
        "inst_name": "WIN-4C4C4544-0038-5910-8058-C4C04F433632",
        "host_name": "FINANCE-PC-01",
        "ip_addr": "192.168.1.56",
        "os_type": "windows",
        "hardware_uuid": "4C4C4544-0038-5910-8058-C4C04F433632",
        "software_snapshot_status": "complete",
        "snapshot_id": "5ea76c94-3e87-4b37-a4e2-13099c3f8305",
        "software_expected_count": 1,
        "software_error_count": 0
      }
    ],
    "pc_software": [
      {
        "inst_name": "SW-8F6A1D93C2E741B76BB57AC50F25D182",
        "pc_inst_name": "WIN-4C4C4544-0038-5910-8058-C4C04F433632",
        "snapshot_id": "5ea76c94-3e87-4b37-a4e2-13099c3f8305",
        "software_key": "google chrome|google llc",
        "name": "Google Chrome",
        "version": "127.0.6533.89",
        "publisher": "Google LLC",
        "source": "windows_registry"
      }
    ]
  }
}
```

### 9.1 快照状态

| 状态 | PC 写入 | 软件新增/更新 | 软件删除 |
|---|---|---|---|
| `complete` | 是 | 是 | 通过安全门后按清理策略执行 |
| `partial` | 有效字段 | 是 | 否 |
| `failed` | 否 | 否 | 否 |

PC 基础信息成功但软件命令或部分记录失败时返回 `partial`。身份无法确认、连接失败或整体输出非法时返回 `failed`。

完整空快照必须明确返回：

```text
software_snapshot_status = complete
software_expected_count = 0
pc_software = []
```

它表示成功发现零个软件，不表示缺失输出。

### 9.2 完整性安全门

CMDB 只有在以下条件全部满足时，才把快照视为可删除：

- PC 与所有软件记录的 `snapshot_id` 一致。
- 实际软件记录数等于 `software_expected_count`。
- `software_error_count == 0`。
- 每条软件的 `pc_inst_name` 等于当前 PC。
- PC 与软件实例名合法且快照内无冲突。
- 当前任务是权威任务。
- 快照新于最近已应用结果。

任何条件不满足都自动降级为 `partial`，只新增和更新，不删除。该规则防止 NATS、VictoriaMetrics 或查询窗口丢失记录后发生误删。

快照 ID、数量和错误计数属于对账控制元数据，由格式化器和对账器消费，不作为普通 PC 资产字段长期展示。

## 10. CMDB 逐 PC 对账

新增 PC 专用快照对账单元。它复用现有 VM 查询、插件格式化、GraphClient 和关联能力，但按单台 PC 组织写入和删除，不把该语义默认强加给其他插件。

每台 PC 独立处理：一台成功、部分或失败不得影响同一任务中的其他 PC。

安全顺序：

```text
1. 校验PC身份、快照和来源
2. 创建或更新PC白名单字段
3. 新增或更新软件实例
4. 建立PC与软件关系
5. 验证所有写入和关联成功
6. 满足完整性安全门后计算当前PC差集
7. 按清理策略删除已卸载软件
8. 写入删除变更记录
```

删除必须在新增、更新和关联之后。任一软件写入或关联失败时，本台 PC 降级为部分成功，不进入删除阶段。

图写入不假设跨多次操作天然原子。删除失败时保留旧软件、记录部分成功并在下次完整快照继续幂等重试；允许短期多一条陈旧软件，不允许丢失真实软件。

### 10.1 清理策略

继续复用现有表单和任务字段：

- `immediately`：完整且通过安全门时立即删除差集；完整空快照可清空当前 PC 软件。
- `after_expiration`：本次不立即删除，按现有过期策略在连续未发现达到配置天数后处理。
- `no_cleanup`：不删除，只新增和更新。

PC 任务默认选择 `immediately`。无论用户选择何种策略，`partial` 和 `failed` 都不允许删除。

### 10.2 删除审计

现有自动采集变更记录需要补齐删除成功记录：

- 操作类型：删除实例。
- 场景：自动采集。
- 模型：`pc_software`。
- `before_data`：删除前软件属性。
- 关联 PC、任务 ID 和快照 ID。
- 原因：完整快照中已不存在，判定为已卸载。
- 操作人：`system`。

只有图删除成功后才写成功审计。删除失败写任务错误，不伪造成功记录。

### 10.3 旧结果保护

同一任务现有单飞机制可以减少重叠执行，但对账仍需比较采集时间。旧于或等于最近已应用结果的延迟快照按幂等结果忽略，不覆盖新数据。

## 11. 权威采集任务

每台 PC 同一时间只有一个权威采集任务能够写入和执行软件删除。

首次发现：第一个成功识别 `inst_name` 的任务建立来源绑定。可以复用系统 `collect_task`、`collect_time` 作为当前来源与最近应用时间，必要的移交状态保存在受控服务端数据中，不作为人工资产字段。

其他任务发现相同 PC：返回 `SOURCE_TASK_CONFLICT`，不更新 PC、软件或关系。

显式移交：

```text
1. 管理员授权新任务接管
2. 新任务执行采集但暂不删除
3. 身份与完整快照校验通过
4. 将权威来源切换到新任务
5. 新任务应用快照并取得后续删除权限
6. 旧任务再次命中时返回来源冲突
```

新任务失败或部分成功时不切换，不影响旧来源与已有数据。

## 12. 前端设计

PC 发现入口位于现有自动发现/配置采集页面。必须复用现有抽屉和 `BaseTaskForm` 的结构与交互：

```text
基础设置
  任务名称
  操作系统（PC新增）
  扫描周期
  所属组织
  接入点
  IP范围 / 选择资产

连接凭据
  Windows WinRM 或 macOS SSH（PC新增差异）

高级设置
  超时时间
  数据清理策略

页脚
  测试 / 确定 / 取消
```

不得另造摘要侧栏、新任务框架或与其他配置采集不一致的操作顺序。

### 12.1 Windows WinRM 凭据

| 字段 | 默认值 |
|---|---|
| 用户名 | 无，支持域、本地和 UPN 表达 |
| 密码 | 无，加密保存 |
| 端口 | 5986 |
| 传输 | HTTPS |
| 认证 | NTLM，首版固定 |
| 服务端证书校验 | 默认关闭并展示安全提示 |

允许显式切换 HTTP/5985，但必须提示仅用于受控可信网络。

### 12.2 macOS SSH 凭据

底层 NATS SSH 执行器已支持密码、私钥和密码短语。上层 PC 表单、NodeParams 和执行适配需要透传既有能力：

- 用户名和端口，默认 22。
- 密码认证。
- PEM 私钥认证。
- 可选私钥密码短语。

凭据池继续复用现有多凭据机制。目标仅在明确认证失败时尝试下一组；网络不可达不盲目遍历全部凭据。日志和 API 不得输出秘密内容。

### 12.3 连接测试

测试按钮复用 PC 的实际 WinRM/SSH 链路执行最小只读身份命令：

- 验证网络和认证。
- 获取 OS、硬件 UUID 或序列号。
- 不执行完整软件扫描。
- 不写入 CMDB。
- 返回设备系统和生成的 PC `inst_name`，失败时返回分类错误。

## 13. 资源与安全边界

| 约束 | 默认/上限 |
|---|---|
| 连接测试超时 | 15 秒 |
| 单台脚本执行超时 | 默认 120 秒，范围 30～300 秒 |
| 单台输出最大值 | 10 MB |
| 单台软件最大条数 | 5000 |
| 单个软件字段最大长度 | 1024 字符 |

超过限制不得截断后伪装完整快照；应返回部分或失败，并禁止删除。

脚本必须随插件发布、版本固定、只读执行。禁止用户提供任意命令，禁止注册表写入、文件删除、软件安装/卸载/修复和系统配置修改。

凭据继续使用现有加密和环境注入机制；密码、私钥、密码短语、完整请求头不得进入日志、错误响应、VictoriaMetrics 或变更记录。

## 14. 错误模型

| 错误码 | 含义 | 写入策略 |
|---|---|---|
| `TARGET_UNREACHABLE` | 目标不可达 | 不写入 |
| `WINRM_AUTH_FAILED` | WinRM 认证失败 | 不写入 |
| `WINRM_TLS_FAILED` | WinRM TLS/证书失败 | 不写入 |
| `SSH_AUTH_FAILED` | SSH 认证失败 | 不写入 |
| `SSH_KEY_INVALID` | 私钥或密码短语无效 | 不写入 |
| `SCRIPT_TIMEOUT` | 脚本超时 | 失败或部分成功 |
| `PC_IDENTITY_INVALID` | 无法生成稳定身份 | 不写入 |
| `SCRIPT_OUTPUT_INVALID` | 输出格式非法 | 不写入 |
| `SOFTWARE_PARTIAL` | 部分软件无法解析 | 更新但不删除 |
| `SNAPSHOT_COUNT_MISMATCH` | 软件数量不一致 | 更新但不删除 |
| `SOURCE_TASK_CONFLICT` | 非权威任务命中 PC | 不写入 |
| `STALE_SNAPSHOT` | 旧结果延迟到达 | 幂等忽略 |
| `CMDB_WRITE_PARTIAL` | 软件或关系写入失败 | 保留旧软件，不删除 |

任务详情按目标展示完整成功、部分成功、失败和来源冲突，并显示软件数量与新增、升级、卸载统计。整体状态按全部目标结果聚合，不隐藏部分失败。

## 15. 测试策略

实现遵循 TDD，先写失败测试，再完成最小实现。触及代码覆盖率不低于 75%。

### 15.1 脚本与规范化测试

- Windows/macOS 正常 UUID 和序列号回退。
- UUID 与序列号均无效。
- Windows 32/64 位注册表重复项去重。
- Windows 系统组件、补丁、驱动和 AppX 过滤。
- macOS Bundle ID 和缺失回退。
- 软件名称、发布者和版本缺失。
- 空软件清单、Unicode、中文和特殊字符。
- 软件条数、字段长度和总输出边界。
- 静态检查确认无写注册表、删除、安装、卸载和任意命令拼接。

### 15.2 Stargazer 测试

- Windows 路由到既有 WinRM/Ansible Executor。
- macOS 路由到既有 SSH executor。
- macOS 密码、私钥和密码短语透传。
- OS 与协议非法组合被拒绝。
- complete、partial、failed 转换和数量元数据。
- 凭据脱敏、超时与资源限制。
- 现有 NATS Subject 和队列路径保持不变。

### 15.3 CMDB 对账测试

- 首次创建与相同 `inst_name` 幂等更新。
- IP、主机名和登录用户变化不产生新 PC。
- 人工资产字段零覆盖。
- 软件升级只更新版本。
- 不同 PC 的相同软件互不冲突。
- 完整快照按策略删除，完整空快照清理当前 PC。
- partial、failed、数量不一致和写入失败均不删除。
- 删除只影响当前 PC，失败可重试。
- 软件删除成功生成变更记录。
- 旧快照不覆盖新结果。
- 权威任务冲突和安全移交。
- `immediately`、`after_expiration`、`no_cleanup` 三种策略。

### 15.4 前端测试

- OS 正确锁定 WinRM/SSH，任务不能混合 OS。
- Windows/macOS 凭据字段联动。
- OS 编辑不可变，凭据脱敏回填。
- IP/资产选择、周期、组织、接入点和高级设置复用既有行为。
- 连接测试不写 CMDB。
- 错误码转换为可理解中文信息。

## 16. 真实环境验收

### 16.1 Windows

至少使用一台 Windows 10/11 PC：

1. WinRM HTTPS/5986 + NTLM 成功。
2. 若发布 HTTP 支持，补测 HTTP/5985。
3. 硬件、系统和 HKLM 32/64 位应用字段正确。
4. 安装测试软件后出现新增记录。
5. 升级后只更新版本。
6. 卸载后完整快照按策略删除并生成审计。
7. 错误密码、端口阻断、WinRM 关闭时不修改 CMDB。

### 16.2 macOS

至少使用一台 Intel 或 Apple Silicon macOS：

1. SSH 密码认证成功。
2. SSH 私钥与可选密码短语成功。
3. 硬件、系统和 `/Applications` 应用字段正确。
4. 安装、升级、卸载测试 `.app` 正确收敛。
5. 错误凭据、SSH 关闭和脚本超时时不误删。

若只具备一种 Mac 架构，另一架构必须在发布说明中标记未验证，不得用模拟测试冒充真实验收。

## 17. 验收标准

- Windows WinRM 与 macOS SSH 均有真实环境证据。
- 重复采集不产生重复 PC 或软件实例。
- 软件升级、卸载、完整空快照和部分失败语义正确。
- 所有失败和部分快照均无误删。
- 人工资产字段零覆盖。
- 权威任务冲突与移交正确。
- 密码、私钥和密码短语不出现在 API、日志、指标和审计中。
- 远程脚本对目标 PC 只读且满足资源边界。
- Server、Web、Stargazer 对应测试和质量门禁通过。
- 真实采集失败不会导致目标 PC 崩溃、配置变化或数据丢失。

## 18. 回滚

- PC 插件入口可通过企业版能力注册或功能开关停用，停用后不再创建新任务或下发配置。
- 停止任务不删除已发现的 PC、软件或人工资产数据。
- 回滚 Stargazer 插件不修改现有 WinRM、SSH、NATS 和其他采集插件链路。
- 已写入的 `pc_software` 与关联属于有效历史数据，回滚时不自动批量删除。
- 若立即清理出现异常，可先将任务清理策略切换为 `no_cleanup`，保留新增和更新能力并停止删除。

## 19. 实施边界总结

```text
一个“PC发现”入口
一个任务一种OS
Windows固定WinRM
macOS固定SSH
一个pc模型
一个pc_software模型
PC通过1:N关系展示安装软件
inst_name使用OS前缀+稳定硬件身份
完整快照通过安全门后按策略清理
部分或失败快照绝不删除
一个PC只有一个权威采集任务
前端复用现有配置采集表单
```
