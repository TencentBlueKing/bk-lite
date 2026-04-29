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
