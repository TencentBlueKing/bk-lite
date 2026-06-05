## ADDED Requirements

### Requirement: OpsPilot 提供监控内置工具集

OpsPilot SHALL 提供一个名为 `monitor` 的内置 LLM 工具类别，用于统一暴露监控查询能力。

#### Scenario: 工具类别可被加载器发现
- **WHEN** `ToolsLoader` 接收到 `langchain:monitor` 工具服务 URL
- **THEN** 系统 SHALL 从 `monitor` 工具模块加载其已注册的监控工具
- **AND** 这些工具 SHALL 与现有内置工具一样进入可绑定的 LangChain 工具集合

#### Scenario: 工具元数据可被内置工具链路展示
- **WHEN** 系统构建内置工具元数据列表
- **THEN** 返回结果 SHALL 包含 `monitor` 工具类别及其子工具元数据
- **AND** 调用方 SHALL 能像选择 `mysql`、`redis`、`oracle`、`mssql` 一样选择 `monitor` 工具

### Requirement: 监控工具请求必须通过 Monitor RPC 接口转发

监控内置工具 SHALL 通过 `apps.rpc.monitor.MonitorOperationAnaRpc` 调用下游 Monitor NATS 接口，且 MUST NOT 直接调用 `apps.monitor` 的本地 service、model、utils 或 nats handler。

#### Scenario: 执行监控对象查询
- **WHEN** 用户调用任一监控查询工具
- **THEN** 系统 SHALL 通过 Monitor RPC 接口转发该请求到下游 NATS
- **AND** 工具层 SHALL 仅做参数整理、上下文补齐和结果包装

#### Scenario: 保持监控业务边界单一
- **WHEN** 监控工具需要访问对象、实例、指标或告警数据
- **THEN** 系统 SHALL 复用下游 Monitor NATS 已有的权限过滤、时间处理和查询逻辑
- **AND** 工具层 SHALL NOT 在本地重复实现同类监控业务逻辑

### Requirement: 监控工具支持对象、实例与指标发现

监控内置工具 SHALL 提供对象发现、实例发现和指标发现能力，使 LLM 能在无需原始查询表达式的情况下逐步定位监控目标。

#### Scenario: 列出监控对象
- **WHEN** 用户调用对象发现工具
- **THEN** 系统 SHALL 返回当前可用的监控对象列表
- **AND** 返回结果 SHALL 可用于后续实例查询和指标查询

#### Scenario: 列出监控对象实例
- **WHEN** 用户指定监控对象并调用实例查询工具
- **THEN** 系统 SHALL 返回该监控对象下当前用户可见的实例列表
- **AND** 返回结果 SHALL 受用户组织范围与权限过滤约束

#### Scenario: 列出对象级或实例级指标
- **WHEN** 用户指定监控对象或实例并调用指标发现工具
- **THEN** 系统 SHALL 返回与该对象或实例相关的指标列表
- **AND** 返回结果 SHALL 可用于后续指标数据查询

### Requirement: 监控工具支持指标数据查询

监控内置工具 SHALL 支持基于监控对象、实例和指标标识的指标数据查询，而不要求调用方直接提供底层原始查询表达式。

#### Scenario: 查询指标时序数据
- **WHEN** 用户指定监控对象、指标和时间范围并调用指标数据查询工具
- **THEN** 系统 SHALL 返回对应时间范围内的指标数据
- **AND** 系统 SHALL 允许按实例或维度进一步缩小查询范围

#### Scenario: 查询参数不完整
- **WHEN** 调用指标数据查询工具但缺少必要的对象、指标或时间范围参数
- **THEN** 系统 SHALL 返回明确的参数错误信息
- **AND** 系统 SHALL 不得静默降级为其他查询

### Requirement: 监控工具支持告警查询

监控内置工具 SHALL 提供活跃告警查询和历史告警异常段查询能力。

#### Scenario: 查询最新活跃告警
- **WHEN** 用户调用活跃告警查询工具
- **THEN** 系统 SHALL 返回最新的活跃告警列表
- **AND** 系统 SHALL 支持按监控对象、实例、级别或告警类型过滤结果

#### Scenario: 查询历史异常段
- **WHEN** 用户指定时间范围并调用告警异常段查询工具
- **THEN** 系统 SHALL 返回该时间范围内的异常段或告警分段数据
- **AND** 系统 SHALL 支持按实例、级别或告警类型过滤结果

### Requirement: 监控工具通过账号密码校验用户并支持显式组织参数

监控内置工具 SHALL 通过工具参数接收账号密码校验用户身份，并支持通过工具参数接收可选 `domain` 与前端选定的组织信息，以组装 Monitor RPC 所需的用户上下文。

#### Scenario: 使用账号密码和可选 domain 校验用户
- **WHEN** 工具调用提供 `username`、`password`，并可选提供 `domain`
- **THEN** 系统 SHALL 使用 `username + domain` 在用户表中查找对应用户；未提供 `domain` 时 SHALL 回退到默认 `domain.com`
- **AND** 系统 SHALL 校验该用户的密码哈希
- **AND** 仅在校验成功后发起后续 Monitor RPC 请求

#### Scenario: 使用前端选定组织执行查询
- **WHEN** 工具调用显式提供 `team_id`
- **THEN** 系统 SHALL 使用该组织标识组装 Monitor RPC 所需的用户上下文
- **AND** 后续 RPC 查询 SHALL 在该组织范围下执行

#### Scenario: 未显式提供组织时回退默认组织
- **WHEN** 工具调用未提供 `team_id`
- **THEN** 系统 SHALL 从用户所属组织中选择默认组织
- **AND** 后续 RPC 查询 SHALL 使用该默认组织执行

#### Scenario: 缺少用户上下文
- **WHEN** 工具调用缺少账号密码，或账号密码校验失败
- **THEN** 系统 SHALL 返回明确错误信息
- **AND** 系统 SHALL 不得发起匿名或未校验身份的 Monitor RPC 请求
