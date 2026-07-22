# 2026 06 05 Add Monitor Rpc Llm Tools

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-monitor-rpc-llm-tools/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 的内置工具目前缺少面向监控场景的 LLM 工具，导致用户无法通过统一的工具调用链探索监控对象、指标、实例和告警。现在补齐这部分能力，可以让监控问答复用现有 Monitor NATS 接口与权限逻辑，同时避免在工具层直接耦合 `apps.monitor` 的本地实现。

## What Changes

- 新增一组面向监控场景的 OpsPilot LLM 内置工具，用于发现监控对象、查询监控实例、列出指标、拉取指标数据和查看告警信息。
- 工具实现统一通过 `apps.rpc.monitor.MonitorOperationAnaRpc` 调用 Monitor NATS 接口，不直接调用 `apps.monitor` 下的 service、model 或 nats handler。
- 在工具加载与元数据暴露链路中注册新的 `monitor` 工具类别，使其能像现有 `mysql`、`redis`、`oracle`、`mssql` 工具一样被加载和展示。
- 监控工具通过工具参数接收账号、密码和可选 `domain`，并可选接收前端通过 team 接口选择后的组织参数；工具层先校验用户身份，再以该用户和选定组织模拟执行 RPC 查询。

## Capabilities

### New Capabilities
- `monitor-rpc-llm-tools`: 提供基于 Monitor RPC/NATS 的监控内置工具能力，覆盖监控对象、实例、指标、指标数据和告警查询。

### Modified Capabilities

None.

## Impact

- `server/apps/opspilot/metis/llm/tools/`: 新增 `monitor` 工具包及其公共辅助逻辑。
- `server/apps/opspilot/metis/llm/tools/tools_loader.py`: 注册并暴露新的 `monitor` 工具类别。
- `server/apps/opspilot/services/builtin_tools.py` 与相关工具元数据链路：新增 monitor 内置工具展示与子工具元数据。
- `server/apps/rpc/monitor.py`: 作为工具层唯一的监控数据访问入口被复用。
- `server/apps/monitor/nats/`: 现有 Monitor NATS 接口成为工具层下游依赖，无需在工具层直接连接 `apps.monitor` 本地实现。

## Implementation Decisions

## Context

OpsPilot 当前已经提供 `mysql`、`redis`、`oracle`、`mssql` 等内置 LLM 工具，但缺少统一的监控工具入口。监控域已有可复用的 Monitor NATS 接口，以及 `apps.rpc.monitor.MonitorOperationAnaRpc` 这一层 RPC 包装，因此本次设计的关键约束不是“如何实现监控逻辑”，而是“如何在不直接耦合 `apps.monitor` 本地实现的前提下，把现有监控能力稳定暴露给 LLM 工具层”。

这个变更会同时影响 `server/apps/opspilot/metis/llm/tools/`、工具加载器、内置工具元数据，以及工具运行时上下文传递链路，因此属于跨模块改动。另一个重要背景是，监控 NATS 接口已经包含权限、对象过滤、实例过滤、时间范围处理和告警查询等规则，工具层不应复制这些逻辑，而应复用现有 RPC/NATS 边界。

## Goals / Non-Goals

**Goals:**
- 为 OpsPilot 提供一组可被 LLM 调用的监控内置工具，覆盖监控对象、实例、指标、指标数据和告警查询。
- 监控工具统一通过 `MonitorOperationAnaRpc` 调用下游 Monitor NATS 接口，不直接调用 `apps.monitor` 的 service、model、utils 或 nats handler。
- 监控工具与现有内置工具保持一致的组织方式、加载方式和元数据暴露方式，能够被 `ToolsLoader` 和内置工具展示链路识别。
- 通过工具参数接收 `username`、`password`、可选 `domain` 和可选 `team_id`，校验用户后组装 RPC 所需的用户上下文。

**Non-Goals:**
- 不新增新的 Monitor 业务能力，不修改现有 NATS handler 的业务语义。
- 不在工具层直接访问 VictoriaMetrics、数据库或 `apps.monitor` 的内部服务。
- 不在本次变更中引入写操作类监控工具，范围仅限查询类工具。
- 不重构现有 MySQL、Redis、Oracle、MSSQL 工具的组织方式。

## Decisions

### 1. 采用“LLM Tool -> RPC -> NATS”单一路径

监控工具层的唯一数据访问入口使用 `apps.rpc.monitor.MonitorOperationAnaRpc`。这样可以把工具层严格限定为 adapter：负责接收 LLM 参数、补齐运行时上下文、调用 RPC、包装返回值，而不承担监控业务逻辑。

选择这一方案而不直接调用 `apps.monitor` 本地接口，原因是：
- 复用已有权限、过滤、分页和时间处理逻辑，避免逻辑分叉。
- 保持监控能力对外暴露边界一致，减少工具层对内部模块结构的耦合。
- 与用户要求一致，明确禁止工具层直接连接 `apps.monitor` 本地实现。

备选方案是工具层直接 import `apps.monitor.nats.monitor` 或 service 层方法，但这会复制 NATS 暴露边界、增加耦合，并让权限与过滤逻辑分散到多个入口，因此不采用。

### 2. 工具包按监控域拆分，而不是每个 RPC 一个文件

工具目录采用 `monitor/__init__.py + objects.py + metrics.py + alerts.py + utils.py` 的组织方式。这样更接近现有 `mysql`、`oracle` 等工具包的聚合风格，也能让对象发现、指标查询、告警查询分别收敛在稳定的边界内。

选择按域拆分，而不是“每个 RPC 方法一个文件”，原因是：
- LLM 工具面对的是任务语义，而不是底层接口清单。
- 同类工具会共享上下文解析、返回格式和命名约束，按域聚合更便于维护。
- 后续若需要从 1:1 RPC 暴露逐步演进为更高层的任务型工具，按域拆分更容易承接。

备选方案是每个工具单独一个文件，但会造成文件碎片化，且与仓库现有工具目录风格不一致，因此不采用。

### 3. 首期工具以查询类能力为主，并优先暴露高频场景

设计优先覆盖以下几类查询：
- 监控对象发现
- 监控对象实例查询
- 对象/实例指标发现
- 指标数据查询
- 最新活跃告警查询
- 历史告警异常段查询

首期不把底层原始查询能力作为默认入口，尤其不优先暴露等价于 `query`、`query_range` 的原始 PromQL 风格接口。原因是这些接口对 LLM 的参数正确率要求更高，也更容易绕开对象、实例和指标的语义边界。

备选方案是直接 1:1 暴露全部 RPC 方法，但这会把模型引向底层查询表达式和参数细节。设计上仍可保留后续扩展空间，但首期优先保障高频问答可用性。

### 4. 通过账号密码校验用户，并允许显式选择组织

监控工具的公共辅助层通过工具参数接收 `username`、`password`、可选 `domain` 和可选 `team_id`。工具在调用 Monitor RPC 前，先按 `username + domain` 查询用户表并使用密码哈希校验用户身份；校验通过后，再基于用户所属组织或显式传入的 `team_id` 组装 `user_info`，以该用户身份模拟执行 Monitor RPC。

选择这种方式，而不是直接依赖运行时 `user_id` 注入，原因是：
- 当前需求明确要求工具调用时由用户输入账号密码进行身份校验。
- Monitor NATS 下游依赖 `user_info.team` 和 `user_info.user`，工具层需要显式控制模拟身份。
- `team_id` 可由前端先通过现有 team 接口选择，再作为工具参数传入，比在工具层自行做组织选择更符合现有前后端职责分工。

备选方案是完全沿用 `configurable.user_id` 的隐式上下文模式，但这与当前需求不符，也不利于前端在工具调用前显式选择组织，因此不采用。

### 5. 监控工具作为新的内置工具类别接入现有加载链路

`tools_loader.py` 需要增加 `monitor` 类别，内置工具元数据链路需要像现有数据库工具一样暴露 monitor 的构造参数和子工具元数据。这样监控工具可以通过现有 `langchain:<tool_name>` 机制被选择、加载和展示，而不需要单独增加一套工具发现协议。

备选方案是只在代码层硬编码加载 monitor 工具，不进入内置工具元数据体系，但这会让前端配置与服务端加载方式失配，因此不采用。

## Risks / Trade-offs

- [Risk] `MonitorOperationAnaRpc` 与 NATS handler 的参数语义较底层，直接映射到工具参数时可能不够自然。 → Mitigation: 首期优先暴露高频查询场景，工具命名与说明按任务语义组织，必要时在工具层做轻量参数整理，但不复制业务规则。
- [Risk] 工具层与现有数据库工具不同，新增了一种基于 RPC 的内置工具模式。 → Mitigation: 把 RPC 调用、上下文解析和结果包装集中在 `monitor/utils.py`，将新模式限制在 monitor 包内，避免扩散到其他工具域。
- [Risk] 若下游 Monitor NATS 接口返回格式不稳定，工具层会直接受影响。 → Mitigation: 工具层统一包装成功/失败响应，并在设计中保持“透传下游语义、只做最小适配”的原则，减少额外转换。
- [Risk] `design` 完成后，`tasks` 仍依赖 `specs`，若 capability 要求定义不够清晰，后续任务拆分会不稳定。 → Mitigation: 在接下来的 `specs` artifact 中把 capability 范围明确到查询类监控工具行为与边界，不把实现细节塞进 spec。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-23
```

## Capability Deltas

### monitor-rpc-llm-tools

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

## Work Checklist

## 1. Monitor 工具公共层

- [x] 1.1 新增 `server/apps/opspilot/metis/llm/tools/monitor/` 目录及 `__init__.py`、`utils.py` 基础结构
- [x] 1.2 在 `monitor/utils.py` 中实现账号密码校验与组织解析，统一获取用户对象和默认/显式组织信息
- [x] 1.3 在 `monitor/utils.py` 中封装 `MonitorOperationAnaRpc` 调用入口，统一组装 `user_info` 和通用错误/成功返回结构

## 2. 监控查询工具实现

- [x] 2.1 在 `monitor/objects.py` 中实现监控对象发现工具，并通过 RPC 调用下游 Monitor NATS 接口
- [x] 2.2 在 `monitor/objects.py` 中实现监控对象实例查询工具，并使用账号密码校验后的用户与组织参数发起 RPC 查询
- [x] 2.3 在 `monitor/metrics.py` 中实现对象级指标发现工具，并通过 RPC 返回可查询指标列表
- [x] 2.4 在 `monitor/metrics.py` 中实现实例级指标发现工具，并支持基于实例筛选指标
- [x] 2.5 在 `monitor/metrics.py` 中实现指标数据查询工具，并支持时间范围、实例和维度参数透传
- [x] 2.6 在 `monitor/alerts.py` 中实现活跃告警查询工具，并支持常见过滤条件透传
- [x] 2.7 在 `monitor/alerts.py` 中实现历史告警异常段查询工具，并支持时间范围和过滤条件透传

## 3. 工具注册与元数据接入

- [x] 3.1 在 `monitor/__init__.py` 中汇总导出监控工具函数与构造参数元数据
- [x] 3.2 更新 `server/apps/opspilot/metis/llm/tools/tools_loader.py`，注册 `monitor` 工具类别并确保 `langchain:monitor` 可被发现
- [x] 3.3 更新 `server/apps/opspilot/services/builtin_tools.py`，将 `monitor` 作为新的内置工具类别暴露，并生成子工具元数据

## 4. 验证

- [x] 4.1 检查监控工具在缺少用户上下文、参数不完整和 RPC 异常时返回明确错误信息
- [x] 4.2 验证监控工具不会直接调用 `apps.monitor` 本地实现，而是统一通过 `MonitorOperationAnaRpc` 发起请求
- [x] 4.3 执行受影响模块的最小验证命令，确认工具加载与静态检查通过
