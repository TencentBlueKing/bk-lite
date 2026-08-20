# 运营分析统一筛选支持列表型下拉

Status: implemented

## Completion Evidence

- 统一筛选 `stringList`：`web/scripts/ops-analysis-unified-filter-input-test.ts` 通过
- 画布筛选动态选项源进入分享/报表/YAML 依赖：`test_named_option_datasources.py`、`test_export_and_viewsets.py`
- 监控主机列表 / 趋势折叠 / 快照无健康字段 / Top10 `instance_ids`：`apps/monitor/tests/test_host_dashboard*.py`、`test_host_resource_top_handler.py`
- 内置数据源登记：`test_host_dashboard_datasource_definitions.py`、`test_host_resource_top_datasource_definition.py`
- 非内置主机综合画布样例：`test_host_comprehensive_dashboard_yaml.py`

## Problem Statement

看板搭建者需要在画布顶部放一个可自定义选项源的下拉，选中的对象要一次性传给多个组件。第一期典型场景是「从监控中心已有主机里多选，下面的趋势和 KPI 按这批主机刷新」；后续还会有机房、业务、设备等同类下拉。

现在统一筛选只能绑标量 `string` / `timeRange` / `dateRange`，筛选值不能是 ID 列表。3D 机房那种组件内切换只能改当前一张卡，不能驱动整页。把每个组件都做成各自的下拉，状态会对不齐，以后每多一个场景都要再发明一次同步。

## Solution

在现有统一筛选上增加一等参数类型 `stringList`：选项源仍可静态或指向另一个数据源，控件可以是单选或多选，**请求里始终传数组**。单选是长度为 1 的列表，多选是多条；空列表按「不传该参数」处理。

组件继续用同 key + 同 type 绑定。只影响单张卡的切换（Top10 换指标、3D 机房换当前机房）继续走组件内 `componentSwitch`，不升成公共筛选。

同期打通主机看板取数（不含健康主机 KPI）：监控提供主机列表、按所选主机的时序、资源快照（均值/最高值）以及可按 `instance_ids` 收窄的 Top10；运营分析登记为数据源，供画布绑定 `instance_ids`。

## User Stories

1. 作为看板搭建者，我希望把数据源里标记为筛选的 `stringList` 参数提升为画布统一下拉，并指定静态或动态选项源，从而不必为每个场景写死控件。
2. 作为看板搭建者，我希望多个组件绑定同一个 `stringList` 筛选项，从而改一次选择，所有绑定组件用同一批 ID 重新查询。
3. 作为看板使用者，我希望在筛选栏里单选或多选对象（例如多台监控主机），从而按所选范围看图，而不是逐张卡片改参数。
4. 作为数据源配置者，我希望用空 `chart_type` 的列表接口给下拉提供选项（值字段 + 展示字段），从而选项列表与出图查询分离，并继续受下游权限过滤。
5. 作为看板使用者，我希望清空选择后绑定组件不再带上该参数，从而与现有空字符串筛选行为一致，而不是传空数组冒充「选了零台」。
6. 作为大屏或报表使用者，我希望仪表盘、大屏、报表上已经存在的统一筛选栏都能使用这种列表下拉，从而同一套筛选语义不按画布类型分叉。
7. 作为看板搭建者，我希望用监控主机列表做下拉选项，并把 CPU/内存/磁盘趋势、Top10、负载、流量、磁盘 IO、进程和均值/最高值 KPI 绑到同一批 `instance_ids`，从而按所选主机看图。不展示健康/异常主机数。

## Implementation Decisions

- 扩展现有统一筛选，不新增场景控制器组件，不把 `componentSwitch` 做成全页控制器。
- 新增可绑定参数类型 `stringList`。扫描、绑定匹配仍是 **key + type** 严格相等；`string` 与 `stringList` 不能互相绑定。
- `FilterValue` 增加 `(string | number)[]`。`stringList` 的运行时值和默认值必须是数组；禁止把逗号拼接字符串当作列表契约。
- 单选控件也产出 `[id]`，不多做「长度为 1 时自动拆成标量」。需要标量的接口继续用 `string`，或在自己的 NATS 处理函数里取列表。
- 空数组、`null`、未选：绑定生效时 **省略该参数**，与当前空字符串筛选一致。不要传 `[]` 给下游，除非后续单独约定「空列表表示全量」——本期不做全量语义。
- 选项源复用现有 `inputConfig`：`select` + `static` / `dynamic`（`sourceRef.rest_api` + `valueField` / `labelField`）。动态源沿用「只出列表、不出图」的数据源形态，如机房列表。
- 多选是 `select` 的 `mode=multiple`（或等价配置），不是新的 filter type。筛选项或数据源 `inputConfig` 可声明是否多选；未声明多选的 `stringList` 仍传长度为 0 或 1 的数组。
- 可选 `maxCount`：未配置则本规格不设平台硬顶。主机看板等消费者以后自己配上限，不在本变更里拍死数字。
- 请求组装继续走现有参数优先级：固定参数 > 统一筛选 > 组件私有参数 > 数据源默认。`stringList` 只改变值形状，不改变优先级。
- 画布筛选定义上的动态选项源，必须纳入分享、报表、YAML 依赖收集，不能只扫描组件数据源参数。否则预览/PDF/分享会缺下拉选项。
- YAML 导入导出带上筛选项的 `type=stringList`、`inputConfig` 和默认数组；运行时选中值仍不写入导出文件。
- 实际运行路径以仪表盘/大屏/报表正在使用的统一筛选实现为准，并保持平行家族实现行为一致，避免一处能多选、另一处仍是标量。
- 数据源参数表允许 `stringList` 且可标为 `filter`。现有 `string` / `timeRange` / `dateRange` 行为不变。
- `componentSwitch` 保持组件私有、单值；不得用它同步多张卡。3D 机房继续用当前机房下拉，直到有第二张卡需要同一间机房时，再把 `server_room_id` 提成统一筛选（届时用 `string` 或 `stringList` 由该接口契约决定，不在本期改 3D 接口）。
- 主机查询数据源共用 `instance_ids`（`stringList` + `filter`）。选项源 `monitor/get_host_instance_list` 只出列表，字段 `instance_id` / `display_name`，权限与现有监控实例可见范围一致。
- 趋势图一律按主机出线。一张图一个指标：CPU、内存、磁盘使用率、5 分钟负载、入流量、出流量、磁盘 IO 使用率、磁盘写入延迟、磁盘读速率、磁盘写速率、阻塞进程、僵尸进程。网卡按主机求和，磁盘使用率/IO 使用率/写入延迟按主机取最大，读写速率按主机求和。不把负载 1/5/15 或读写叠成第二维度。
- `monitor/get_host_metric_range` 入参为 `instance_ids`、`metric_type`、时间范围；返回折线可直接消费的 `{display_name: [[timestamp, value], ...]}`。未选主机则不下发该参数，接口按空选择处理为无序列，不退化为全量。
- `monitor/get_host_resource_snapshot` 返回所选主机的 `host_count`、`avg_cpu`、`avg_memory`、`avg_disk`、`max_cpu`、`max_cpu_host`、`max_memory`、`max_memory_host`。不做健康/异常台数。
- 现有 `get_host_resource_top` 增加可选 `instance_ids`，只在所选且已授权主机里排名；未传则保持组织内授权全量，兼容旧画布。
- 不在本期做内置主机综合大屏 YAML；搭建者用上述数据源自行铺画布。

## Testing Decisions

只测外部行为：扫描得到 `stringList`、绑定后请求带上数组、清空则省略、单选也是单元素数组、动态选项能填满下拉、未绑定组件不受影响。不测 React 内部 state 命名。

优先接缝：

- 现有统一筛选请求脚本（参数合并、空值省略、绑定开关）
- 数据源可绑定类型契约测试
- 动态选项加载（`sourceRef` 解析、权限失败时的选项错误）
- 命名选项数据源收集（分享/报表依赖是否包含画布筛选的动态源）
- 参数表允许 `stringList` 作为 `filter`

至少覆盖：`stringList` 多选把数组写入绑定组件请求；`string` 筛选仍传标量；`string` 与 `stringList` 不能绑在一起；空数组不出现在请求体。

监控接缝：`get_host_instance_list` 只返回授权主机；`get_host_metric_range` 按主机折叠子维度且未选主机不退回全量；`get_host_resource_snapshot` 无健康字段；`get_host_resource_top` 在传入 `instance_ids` 时只排所选授权主机。

## Out of Scope

- 健康 / 异常 / 无数据主机数
- 内置「主机综合监控」画布 YAML
- 筛选方案收藏、级联下拉（先选业务再选主机）、图表点击钻取
- 跨仪表盘共享筛选状态
- 用逗号拼接 ID 冒充多选
- 修改 3D 机房 `get_room3d_layout` 入参，或把机房下拉从 `componentSwitch` 迁走

## Further Notes

- 长期能力合同：`specs/capabilities/dashboard-unified-filter.md` 必须在同一实现变更中补上 `stringList` 扫描、数组传参和空列表省略；该文档目前仍写本期仅 `string` 与 `timeRange`。
- 产品决策记忆：`docs/design/product-decisions/ops-analysis-unified-filter.md`
- 用户于 2026-08-20 确认：不做健康主机指标；其余筛选管道与主机取数继续落地。
- 非内置画布样例（可 YAML 导入，不进 `init_builtin_canvases`）：`server/apps/operation_analysis/support-files/host_comprehensive_dashboard.yaml`
