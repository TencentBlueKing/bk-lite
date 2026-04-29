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
