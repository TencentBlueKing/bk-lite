## Why

运营分析目前缺少一个可复用的数据源，用于在当前组织权限范围内统一查看主机 CPU、内存和磁盘使用率 Top10。现有通用指标查询接口不能完成跨 Linux/Windows 指标归并、主机权限过滤、磁盘按主机归并以及同时适配排行榜和表格的数据整形。

## What Changes

- 新增 `monitor/get_host_resource_top` NATS 数据源接口，通过 `metric_type=cpu|memory|disk` 选择资源类型并固定返回 Top10。
- 同时支持 Linux 与 Windows 主机指标，并按原始采样时间选择最新有效值。
- 仅在当前用户、当前组织可见的主机范围内排名；权限或 CMDB 查询失败时禁止退化为全量查询。
- CPU、内存按主机排名；磁盘先为每台主机选择使用率最高的有效文件系统，再进行主机 Top10 排名。
- 按主机采集周期实施动态新鲜度校验，默认周期为 5 分钟，并过滤过期、非法及越界指标。
- 新增一个运营分析内置数据源定义，声明 `topN` 与 `table` 两种图表类型，并提供可切换的指标类型参数及完整字段 schema。
- 返回统一结构化行，使排行榜通过字段映射消费 `display_name` 与 `usage_percent`，表格消费完整主机、磁盘及采样时间字段。

## Capabilities

### New Capabilities

- `host-resource-top10-datasource`: 定义受组织权限约束、跨 Linux/Windows、具备动态新鲜度校验的主机 CPU、内存和磁盘使用率 Top10 数据源及其排行榜/表格响应契约。

### Modified Capabilities

- 无。

## Impact

- 后端监控 NATS 接口与独立的主机资源排名服务。
- VictoriaMetrics 即时/最近样本查询及 Linux、Windows 指标名称兼容。
- CMDB 主机可见性、主机元数据与采集周期读取。
- 运营分析内置数据源初始化配置、参数定义、图表类型和字段 schema。
- 相关服务单元测试、NATS 契约测试和数据源初始化测试。
- 不包含数据库结构变更，也不改变现有通用 `monitor/mm_query` 接口。
