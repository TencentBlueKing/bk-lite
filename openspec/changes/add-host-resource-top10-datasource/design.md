## Context

运营分析通过 `DataSourceAPIModel.rest_api` 调用 `GetNatsData`，再由 `monitor` NATS handler 查询 VictoriaMetrics。现有 `monitor/mm_query` 只适合通用单指标取值：它不负责组织权限、跨 Linux/Windows 指标归并、CMDB 主机信息补全，也不能正确表达“每台主机取最高文件系统后再排 Top10”。

主机采集当前存在两套指标名称。Linux 使用 `host_cpu_usage_percent`、`host_mem_used_percent` 和 `host_disk_used_percent`；Windows WMI 使用对应的 `_gauge` 指标。CPU、内存通常每主机一条序列；磁盘按文件系统产生多条序列，并携带 `mount/path/fstype` 或 `device/path/fstype` 标签。

该能力涉及监控查询、CMDB 可见性、主机采集配置和运营分析数据源配置，必须保证未授权主机不会进入响应或诊断信息。

## Goals / Non-Goals

**Goals:**

- 通过一个 `metric_type` 参数提供 CPU、内存和磁盘使用率 Top10。
- 在当前用户和当前组织可见的主机集合内计算排名。
- 统一 Linux 与 Windows 指标，并使用原始采样时间判断新鲜度。
- 对磁盘执行“每主机最高使用率文件系统，再排主机 Top10”。
- 返回同一组结构化行，同时供 `topN` 排行榜和 `table` 使用。
- 将领域逻辑放入可独立测试的服务，NATS handler 保持为薄适配层。

**Non-Goals:**

- 不支持调用方自定义 `limit`、主机列表、业务、分组、时间范围或聚合函数。
- 不新增历史平均值、最大值或趋势查询。
- 不修改通用 `monitor/mm_query` 契约。
- 不新增数据库表或迁移。
- 不新增排行榜或表格前端组件。

## Decisions

### 1. 使用专用 Monitor NATS 接口

新增 `monitor/get_host_resource_top`，入参仅包含必填的 `metric_type=cpu|memory|disk`。NATS handler 负责参数校验和标准 `{result, data, message}` 契约，具体查询和整形委托给独立的 `HostResourceTopService`。

选择该方案是因为监控模块已经拥有 VictoriaMetrics 访问能力，运营分析也已经通过 NATS 调用监控接口。备选方案是复用 `mm_query` 或让运营分析直接访问 VictoriaMetrics；前者无法处理多序列、权限和 CMDB 补全，后者会把监控存储细节耦合到运营分析。

### 2. 先确定授权主机集合，再计算 Top10

服务从注入的 `user_info` 中取得当前组织、用户、权限树和子组织开关，通过现有 CMDB 可见性规则得到授权主机集合、展示信息和采集周期。VictoriaMetrics 结果必须以该集合做精确白名单过滤，之后才能归并和排序。权限或 CMDB 查询失败时整个请求失败，禁止退化为全量主机。

若实现选择先查询较大的指标集合再在进程内过滤，原始未授权序列只能存在于本次服务调用的短期内存中，不得进入响应或普通日志。若授权主机数量与 VictoriaMetrics 查询能力允许，优先把经过安全转义的 `instance_id` 条件下推到查询层以降低扫描量；无论是否下推，服务端白名单过滤仍是强制边界。

### 3. 在服务层归一化跨平台指标

指标映射固定为：

| 类型 | Linux | Windows WMI |
|---|---|---|
| CPU | `host_cpu_usage_percent` | `host_cpu_usage_percent_gauge` |
| 内存 | `host_mem_used_percent` | `host_mem_used_percent_gauge` |
| 磁盘 | `host_disk_used_percent` | `host_disk_used_percent_gauge` |

每个候选值归一化为包含 `instance_id`、数值、原始采样时间和可选文件系统标签的内部记录。同一主机异常地同时存在 Linux 与 Windows 序列时，以原始采样时间较新的有效记录为准，而不是按操作系统设置固定优先级。

### 4. 动态新鲜度必须使用原始采样时间

每台主机的有效窗口为 `2 × collection_interval`。采集周期缺失、无法解析或非正数时按 5 分钟处理，即有效窗口为 10 分钟。监控查询必须保留最后一个实际样本的时间戳；查询执行时间不得替代采样时间。

CPU、内存先按新鲜度筛选再去重。磁盘先剔除过期文件系统序列，再为每台主机选择 `usage_percent` 最大的文件系统。若同一主机多个文件系统使用率相同，按规范化后的 `mount`、`path`、`fstype` 依次升序选取，以保证结果稳定。

### 5. 排名和响应使用统一结构化行

有效值必须是有限数字且位于闭区间 `[0, 100]`。服务按 `usage_percent` 降序排列；使用率相同时按 `display_name` 升序，再按 `instance_id` 升序。截取前 10 条后生成从 1 开始的 `rank`。

每行包含：

- `rank`
- `display_name`
- `usage_percent`
- `instance_id`
- `host_name`
- `ip`
- `metric_type`
- `mount`
- `path`
- `fstype`
- `sampled_at`

`display_name` 优先使用 `host_name (ip)`，然后依次回退到 `host_name`、`ip`、`instance_id`。CPU 和内存的文件系统字段为 `null`。时间使用带时区的 ISO 8601 字符串。

运营分析内置数据源声明 `chart_type: [topN, table]`，排行榜映射 `display_name` 与 `usage_percent`，表格通过 `field_schema` 使用完整行。数据源的 `metric_type` 是必填字符串选择参数，默认 `cpu`，并以 `componentSwitch: true` 提供 CPU、内存和磁盘三个静态选项。

### 6. 失败与可观测性保持最小暴露

非法参数、权限/CMDB失败和 VictoriaMetrics 失败返回标准失败契约；没有有效数据返回成功空数组。单条序列格式异常只丢弃该条，并记录数量、原因类别和指标类型等汇总信息。日志不得包含未授权主机标识、完整 PromQL、连接地址、凭据或异常堆栈响应。

## Risks / Trade-offs

- **[Risk] 磁盘即时序列基数较高，应用层归并可能增加延迟和内存。** → 在不削弱白名单复核的前提下下推授权实例过滤；只查询计算所需字段和时间窗口，并为候选序列数量设置可观测的合理边界。
- **[Risk] 主机 `instance_id` 与指标标签的格式不一致会导致合法主机被过滤。** → 复用监控模块现有实例 ID 解析/规范化规则，并覆盖 Linux、Windows 和复合实例 ID 测试。
- **[Risk] 不同采集周期导致一次查询需要覆盖不同时间窗口。** → 以授权主机中的最大有效窗口取得候选样本，再逐主机按自身窗口过滤；不得用全局窗口替代逐主机新鲜度判断。
- **[Risk] CMDB 主机信息缺失导致展示字段不完整。** → 只有能映射到授权实例的序列才可返回，展示名按明确顺序回退，缺失的可选展示字段保持空值。
- **[Trade-off] Top10 和新鲜度阈值首版不可由调用方配置。** → 保持接口最小且可预测；未来确有需求时通过独立变更扩展。

## Migration Plan

1. 增加服务及其单元测试，再接入薄 NATS handler。
2. 增加内置数据源定义和初始化测试，使现有初始化命令可幂等创建或更新该数据源。
3. 在包含 Linux、Windows、过期样本和多磁盘序列的测试环境验证权限范围及结果顺序。
4. 部署后通过数据源预览验证 `cpu`、`memory`、`disk` 三种参数以及 `topN`、`table` 两种组件。

回滚时移除或停用该内置数据源，并回退 NATS handler 与服务；由于没有数据库结构迁移，现有数据源和监控接口不受影响。

## Open Questions

- 无。接口范围、排名口径、跨平台兼容、新鲜度、响应结构和展示组件均已确认。
