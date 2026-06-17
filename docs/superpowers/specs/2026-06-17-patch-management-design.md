# BK-Lite 补丁管理 P1 规格设计

- 日期：2026-06-17
- 状态：已确认，待实施计划
- 范围：Windows + Linux 服务器补丁管理 P1

## 1. 背景与目标

BK-Lite 新增独立补丁管理 app，目标是提供一个可落地的 P1 闭环：源配置、补丁库建档、扫描、双视角结果、安装、待重启闭环、通知与审计。

本设计参考 ManageEngine Patch Manager Plus 的核心闭环，但不照搬其 Agent 架构。Patch Manager Plus 的典型模式是厂商维护云端补丁知识库，客户侧 Server 同步补丁数据库，端点 Agent 负责扫描、下载、安装和回传；BK-Lite P1 不新增专用 Patch Agent，而是复用现有 Node NATS 与 Ansible 执行能力。

P1 明确覆盖：

- Windows 服务器 OS 安全补丁和管理员手工导入的通用补丁。
- Linux 服务器 OS 安全补丁和管理员手工导入的通用补丁。
- 补丁源配置、补丁库、扫描、安装、重启、通知、导出、操作审计。

P1 明确不做：

- Mac 补丁。
- 第三方应用补丁。
- 测试批准流程。
- 长期自动部署策略管理页面。
- 报表中心。
- 卸载或回滚补丁。
- 专用 Patch Agent。

## 2. 页面与菜单

新增前端子应用 `web/src/app/patch-manager`，顶层菜单为：

- 首页
- 补丁扫描
- 补丁安装
- 补丁库
- 目标管理
- 设置

### 首页

首页作为风险与待办入口，不做报表中心。展示：

- 高危缺失补丁数量。
- 受影响目标数量。
- 待重启目标数量。
- 失败安装任务。
- 最近扫描任务状态。
- 跳转到扫描、安装、补丁库、目标详情的快捷入口。

### 补丁扫描

用于创建和管理扫描任务：

- 支持手动扫描和周期扫描。
- 周期配置属于扫描任务本身，不做独立自动化策略页面。
- 扫描结果支持主机视角和补丁视角。
- 扫描结果支持按当前筛选条件导出 Excel。
- 扫描任务支持通知配置和通知日志。

### 补丁安装

用于创建和管理安装任务：

- 支持从补丁库、扫描结果主机视角、扫描结果补丁视角发起安装。
- 也支持在补丁安装页新建任务，自由选择补丁和目标。
- 创建任务时必须配置执行时间、超时时间、重启策略。
- 支持安装结果和重启结果追踪。
- 支持安装结果 Excel 导出。

### 补丁库

补丁库分为两个 tab。

Windows 补丁：

- 来源：Microsoft Update Catalog、WSUS、手工上传、扫描发现。
- 支持按 KB、CVE、关键词从 Microsoft Update Catalog 搜索，用户选择条目后平台自动下载补丁包入库。
- 支持从 WSUS 同步或导入补丁元数据和下载信息。
- 支持上传 `.msu`、`.cab`、`.exe`。
- 页面维护 KB、标题、CVE、严重级别、产品/OS、架构、适用范围、包状态等业务元数据。
- Windows 检测命令、安装命令和重启判断逻辑内置，不向用户展示或开放配置。

Linux 补丁：

- 来源：Linux 软件源、手工上传、扫描发现。
- 支持 yum/dnf/apt repo 元数据同步和包下载。
- 发行版名称不硬编码，由设置中的源配置提供。
- 页面维护包名、版本、发行版、系统版本、架构、repo 类型、CVE、严重级别、适用规则、检测规则、安装参数、包状态。
- 标准 yum/dnf/apt 源同步来的补丁使用平台默认逻辑；手工通用补丁允许管理员补检测规则和安装参数。

### 目标管理

补丁管理维护自己的目标，不复用 Job Target 表。

- 参考 Job 的目标管理体验。
- 只支持 Ansible 型目标。
- 维护主机、系统类型、Ansible 所需认证信息、组织归属、连通性状态。
- 执行任务时也可以选择 Node Manager 已纳管节点，但 Node 目标不复制进 PatchTarget。

### 设置

设置页只做补丁源配置，不做存储说明和下载安全配置。

Windows 源：

- Microsoft Update Catalog。
- WSUS。
- 代理信息，用于连接公网 Catalog。

Linux 源：

- 发行版名称。
- 系统版本。
- 架构。
- repo 类型：yum/dnf/apt。
- repo 地址。
- 启用状态。
- 连通性测试。

## 3. 核心数据模型

新增后端 app `server/apps/patch_mgmt`，拥有自有 models、serializers、views、services、tasks、urls、migrations。

### PatchSource

补丁源配置。

- Windows 类型：Microsoft Catalog、WSUS。
- Linux 类型：yum/dnf/apt repo。
- 用于搜索、同步、下载、建档。

### Patch

补丁主记录。

- 标题。
- OS 类型：Windows/Linux。
- 补丁类型：安全补丁/通用补丁。
- 严重级别。
- CVE。
- 来源。
- 包状态。
- 适用范围。
- 是否扫描发现待补全。

采用统一 Patch 主表，并为 Windows/Linux 建扩展 detail 表，以承载差异字段和约束。

### PatchPackage

补丁包文件记录。

- 文件名。
- 大小。
- hash。
- 下载来源。
- NATS S3/Object Storage object key。
- 下载状态。

补丁包统一存入平台已有 NATS S3/Object Storage。用户不配置存储位置。

### PatchTarget

补丁管理独立目标。

- 只支持 Ansible 型目标。
- 保存主机、系统类型、认证信息、组织归属、连通性状态。
- 凭据字段加密存储，参考 Job Target。

### PatchScanTask / PatchScanResult

扫描任务和扫描结果。

PatchScanTask：

- 名称。
- 目标范围。
- 手动/周期配置。
- 通知配置。
- 状态。
- 组织归属。

PatchScanResult：

- 任务。
- 目标。
- 补丁。
- 状态。
- 扫描时间。
- 失败阶段、exit code、stdout/stderr 摘要、错误消息。

扫描结果状态：

- `missing`：缺失。
- `installed`：已安装。
- `not_applicable`：不适用，例如 OS、架构、版本、包管理器类型不匹配。
- `failed`：扫描失败，例如连接失败、命令执行失败、解析失败、权限不足、超时。

### PatchInstallTask / PatchInstallResult

安装任务和安装结果。

PatchInstallTask：

- 补丁范围。
- 目标范围。
- 执行时间。
- 超时时间。
- 重启策略。
- 状态。
- 组织归属。

PatchInstallResult：

- 任务。
- 目标。
- 补丁。
- 安装状态。
- 重启状态。
- stdout/stderr 摘要。
- exit code。
- 错误阶段和错误消息。

安装结果状态：

- 等待执行。
- 执行中。
- 安装成功。
- 安装失败。
- 待重启。
- 已计划重启。
- 重启中。
- 重启失败。
- 完成。
- 已取消。

## 4. 扫描流程

扫描目标来源：

- PatchTarget 独立目标：走 Ansible 执行链路。
- Node Manager 目标：走 Node 提供的 NATS 执行链路。

扫描判断方式：

- Windows：内置 KB/HotFix、PowerShell、注册表/包信息查询逻辑；人工导入补丁仍使用平台内置 Windows 模板，不开放命令配置。
- Linux：优先通过 yum/dnf/apt 查询已安装、可更新、安全更新、包版本；手工通用补丁可使用补丁记录中的检测规则。

扫描建档：

- 扫描中发现补丁库不存在的补丁时，自动创建待补全 Patch 记录。
- 待补全记录等待管理员补包、规则或严重级别。

扫描结果：

- 每次扫描生成 PatchScanTask。
- 每台目标每个补丁生成 PatchScanResult。
- 支持主机视角：某台服务器缺哪些补丁。
- 支持补丁视角：某个补丁影响哪些服务器。
- 最新扫描结果用于首页风险视图，历史扫描任务保留可追溯。

Excel 导出：

- 主机视角导出：目标、IP、OS、补丁、状态、严重级别、CVE、扫描时间、失败原因。
- 补丁视角导出：补丁、KB/包名、严重级别、影响目标、目标状态、扫描时间、失败原因。
- 导出受当前筛选条件影响。

扫描通知：

- PatchScanTask 保存 `notice`、`notice_type_ids`、`notice_users`、`notice_logs`。
- 通知配置参考 monitor 告警策略。
- 通知触发点：
  - 扫描任务完成。
  - 扫描任务失败。
  - 发现高危/严重缺失补丁。
  - 扫描结果中失败目标数超过阈值。
- 失败目标阈值在扫描任务通知配置中设置；未设置时，存在任一失败目标即触发失败目标通知。
- 通知内容包含任务名称、扫描范围、缺失补丁数、高危缺失数、失败目标数、跳转链接。
- 通知人列表必须按当前用户授权组织收口。

## 5. 安装与重启流程

安装任务创建时必须配置：

- 一个或多个补丁。
- 一个或多个目标。
- 执行时间：立即执行或指定时间。
- 超时时间。
- 重启策略：不重启、安装后立即重启、指定时间重启。

执行链路：

- Node Manager 目标：走 Node 提供的 NATS 执行链路。
- PatchTarget 独立目标：走 Ansible 执行链路，底层仍使用 Node 的 Ansible 执行节点。
- PatchInstallTask 自己维护任务状态、目标结果、日志和重启状态，不经过 Job。

安装流程：

1. 到达执行时间后，任务进入执行中。
2. 平台按目标 OS、补丁包和内置/配置规则生成安装动作。
3. 执行前校验补丁包已入库、hash 可用、目标适用、目标可达。
4. 平台将补丁包从 NATS S3/Object Storage 分发到执行节点或目标可访问位置。
5. 通过 NATS/Ansible 执行安装。
6. 收集目标级 stdout/stderr/exit code。
7. 安装后执行检测规则，确认是否安装成功。
8. 根据检测结果和重启需求进入完成、失败、待重启或已计划重启。

Windows 安装：

- `.msu`、`.cab`、`.exe` 使用平台内置安装模板。
- 检测命令、安装命令、重启判断不向用户展示或开放配置。
- 重启判断基于安装返回码、pending reboot 状态、Windows 更新状态。

Linux 安装：

- 标准 yum/dnf/apt 补丁使用平台默认安装逻辑。
- 手工通用补丁可配置检测规则和安装参数。

重启流程：

- 不需要重启：安装结果完成。
- 需要重启 + 策略为不重启：结果进入待重启。
- 需要重启 + 策略为立即重启：执行重启，成功后完成，失败则重启失败。
- 需要重启 + 策略为指定时间：结果进入已计划重启，到点后执行重启。
- 待重启或已计划重启期间，用户可以改为立即重启或重新指定重启时间。
- 重启后再次执行检测规则，确认补丁状态闭环。

安装结果导出：

- 安装任务结果支持 Excel 导出。
- 字段包含任务、补丁、目标、安装状态、重启状态、执行时间、exit code、失败原因。

## 6. 执行日志与进度

P1 复用 job_mgmt 已有 NATS/JetStream 流式日志设计思想，但使用 patch_mgmt 自己的 subject。

使用 subject：

- `patch.scan.{task_id}.{target_key}`
- `patch.install.{task_id}.{target_key}`

目标级 stdout/stderr 实时写入任务日志，页面显示目标级执行进度。失败时保留：

- 失败阶段。
- exit code。
- stdout/stderr 摘要。
- 错误消息。

## 7. 权限与审计

菜单权限建议：

- 首页：View。
- 补丁扫描：View、Add、Edit、Delete、Execute、Export。
- 补丁安装：View、Add、Cancel、Restart、Export。
- 补丁库：View、Add、Edit、Delete、Download、Import。
- 目标管理：View、Add、Edit、Delete、Test。
- 设置：View、Edit、Test。

数据权限：

- PatchTarget、PatchScanTask、PatchInstallTask 都带 `team` 字段。
- 用户只能查看和操作授权组织范围内的目标和任务。
- 从 Node Manager 选择目标时，按当前用户授权组织过滤。
- 通知人列表按授权范围收口。

操作日志：

- 不在 patch_mgmt 中自建审计表。
- 关键动作统一写入平台 `system_mgmt` 操作日志机制。
- 记录范围：
  - 新增/编辑/删除补丁。
  - 下载/导入补丁包。
  - 新增/编辑/删除/测试目标。
  - 创建/取消扫描任务。
  - 创建/取消安装任务。
  - 立即重启/指定重启时间。
  - 修改补丁源设置。

安全边界：

- 凭据字段加密存储。
- 补丁包执行前必须校验包状态为已入库。
- Windows 命令模板内置，不接受前端临时命令直传。
- Linux 手工补丁的检测规则和安装参数只来自补丁库配置，不接受安装任务临时命令。
- 任务执行只允许作用于当前用户授权目标。

## 8. 测试与验收

### 后端测试

覆盖 `server/apps/patch_mgmt`：

- Windows/Linux 补丁建档、导入、状态流转。
- Windows Catalog/WSUS 结果解析 mock。
- Linux yum/apt repo 元数据解析 mock。
- 扫描发现自动生成待补全记录。
- PatchPackage 写入 NATS S3/Object Storage 的服务层 mock。
- 独立 Ansible 目标扫描。
- Node NATS 目标扫描。
- `missing / installed / not_applicable / failed` 状态判断。
- 周期扫描调度。
- 扫描结果主机视角/补丁视角查询。
- 扫描结果 Excel 导出。
- 扫描通知配置、通知触发、通知日志。
- 执行时间调度。
- 包状态校验。
- Windows 内置检测/安装模板选择。
- Linux 默认 yum/apt 安装与手工补丁规则。
- 安装结果状态流转。
- 待重启、计划重启、立即重启、重启失败。
- 安装结果 Excel 导出。
- team 数据权限。
- Node 目标授权过滤。
- 通知人授权范围收口。
- 操作写入 `system_mgmt` 操作日志。

### 前端测试

覆盖 `web/src/app/patch-manager`：

- 6 个菜单可访问：首页、补丁扫描、补丁安装、补丁库、目标管理、设置。
- 补丁库 Windows/Linux tab 展示正确。
- 扫描任务创建、周期配置、结果双视角、导出入口。
- 安装任务创建、执行时间、重启策略、待重启操作。
- 目标管理 Ansible 目标表单和连通性测试。
- 设置页 Windows/Linux 源配置。
- 权限按钮隐藏或禁用。

### 最小验收场景

1. 配置一个 Linux repo 源，导入或同步一个 Linux 补丁。
2. 从 Microsoft Catalog 搜索一个 Windows KB，下载入库。
3. 创建一个 Ansible 独立目标，测试连通成功。
4. 执行一次扫描任务，得到缺失、已安装、不适用、失败中的至少两类结果。
5. 导出扫描结果 Excel。
6. 扫描任务完成后发送通知，并记录通知日志。
7. 从扫描结果发起安装任务，指定未来执行时间。
8. 安装完成后目标进入待重启，用户手动触发立即重启。
9. 重启后结果完成，首页风险和待重启数量更新。
10. 导出安装结果 Excel。
11. 所有关键操作可在平台 system 操作日志中查询。

### 门禁命令

- 后端：`cd server && make test`，或至少运行 `apps/patch_mgmt` 相关 pytest。
- 前端：`cd web && pnpm lint && pnpm type-check`。
- 不做全仓格式化，只格式化触及文件。

## 9. 参考资料

- ManageEngine Patch Manager Plus 产品页：https://www.manageengine.cn/patch-management/
- ManageEngine Patch Manager Plus 功能页：https://www.manageengine.cn/patch-management/features.html
- ManageEngine Patch Manager Plus 帮助中心：https://www.manageengine.cn/patch-management/help.html
- Patch Management Architecture：https://www.manageengine.com/patch-management/help/patch-management-architecture.html
- Manual Patch Deployment：https://www.manageengine.com/patch-management/help/deploy-patches-manually.html
