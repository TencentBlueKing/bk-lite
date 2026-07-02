# 模块 ARD：Operation Analysis（运营分析）

> 路径 `server/apps/operation_analysis` ｜ API 前缀 `api/v1/operation_analysis/`

## 1. 职责【已实现/已存在】
统一可视化层：聚合外部 REST/NATS 数据源，组织仪表盘、拓扑、架构图，支持配置导入导出。仪表板组件形态持续扩展：本轮新增分级条形仪表盘（barGauge）、状态时间线（stateTimeline）、文本（text）三类；同时引入结构化单位库与值映射展示层能力（见 §3 前端层）。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Directory | `models/models.py` | 层级目录（最多 3 级）；含 `is_build_in`/`build_in_key`（unique）内置标识 |
| Dashboard / Topology / Architecture | `models/models.py` | 仪表盘/拓扑/架构图（filters、view_sets JSON）；三者均含 `is_build_in`/`build_in_key`（unique）内置标识 |
| NameSpace | `models/datasource_models.py` | NATS 连接配置（域/账号/密码加密/TLS）；含 `namespace`（NATS 命名空间标识，消息主题前缀，default=`bklite`）；含 `is_active`（内部预留，前端不暴露、运行时不校验） |
| DataSourceAPIModel | `models/datasource_models.py` | 外部 REST API 数据源；含 `chart_type`（JSON，图表类型，default=list）、`field_schema`（JSON，接口返回字段定义，default=list）、`is_active`（内部预留） |
| DataSourceTag | `models/datasource_models.py` | 数据源标签；含 `build_in`（是否内置） |

内置机制【已实现/已存在】：`Directory`/`Dashboard`/`Topology`/`Architecture` 通过 `is_build_in` + 唯一 `build_in_key` 标识内置画布，承载「内置视图对组织可见但不可删改」语义（删改在视图层被 `_raise_if_builtin` 拦截，见 §3）；`DataSourceTag.build_in` 标识内置标签。

## 3. 接口【已实现/已存在】
路由组：`data_source`/`dashboard`/`directory`/`topology`/`architecture`/`namespace`/`tag`/`import_export`；开放端点 `open_api/import_export`。

关键自定义动作【已实现/已存在】：
- `data_source` 的 `get_source_data/{pk}`（POST）：组件运行时取数对外入口，是整个取数链路的起点（`views/datasource_view.py:337`）。
- `directory` 的 `tree`（GET）：返回目录树（`views/view.py:148`）。
- `scene_widgets/network_status_topology`：网络状态拓扑接口，复用 CMDB network_topology/实例权限并汇总 Alerts 活跃告警，权限动作 `view`（证据：`urls.py:23`、`views/scene_widget_view.py:10,12`、`services/network_status_topology.py:5,65,87`）。
- `open_api/import_export`：开放导入导出 API 通过 `api_pass`/API Token 校验，支持 `export`、`precheck_import`、`submit_import` 三类动作；授权服务解析组织、计算导入导出权限矩阵，并在实例/组织维度过滤对象（证据：`views/openapi_import_export_view.py:34,48,118,190,280`、`services/import_export/authorization_service.py:24,71,87,180`）。

安全说明【已实现/已存在】：`NameSpace` 密码使用 AES（`PasswordCrypto`）加解密，密钥取自 `constants.constants.SECRET_KEY`；该密钥已移除源码内置硬编码值，仅从环境变量 `SECRET_KEY` 读取，未配置时为空串（`constants/constants.py:51-53`）。

### 前端层：仪表板组件与展示能力【已实现】

**组件注册表（widgetRegistry）**【已实现】  
`web/src/app/ops-analysis/components/widgetRegistry.ts:14-25` 以 `chartType` 字符串为键，将所有组件类型映射至对应 React 组件，由 `getWidgetComponent` 统一解析。当前注册的组件类型（共 11 种）：

| chartType | 组件文件 | 说明 |
|-----------|---------|------|
| line | comLine.tsx | 折线图 |
| bar | comBar.tsx | 柱状图（含堆叠模式，由 `stack` 字段控制）|
| pie | comPie.tsx | 饼图 |
| table | comTable.tsx | 表格 |
| single | comSingle.tsx | 单值 |
| topN | comTopN.tsx | Top-N |
| gauge | comGauge.tsx | 仪表盘（半圆/整圆） |
| barGauge | comBarGauge.tsx | 分级条形仪表盘【新增】 |
| stateTimeline | comStateTimeline.tsx | 状态时间线【新增】 |
| text | comText.tsx | 文本（轻量 Markdown content 字段）【新增】 |
| eventTable | eventTable/eventTable.tsx | 事件表（事件流） |

证据：`web/src/app/ops-analysis/components/widgetRegistry.ts:22-24`（barGauge/stateTimeline/text）；`web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comBarGauge.tsx`、`comStateTimeline.tsx`、`comText.tsx`。

**组件配置区（viewConfig）**【已实现】  
`web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`：
- `gauge || barGauge`：共享 `GaugeSettingsSection`（阈值、形态、量程、单位）（取数分支 `viewConfig.tsx:728`，渲染分支 `:950`）。
- `stateTimeline`：独立配置，挂载 `ValueMappingsConfigSection`（`viewConfig.tsx:992`）。
- `text`：独立配置，`content` 字段 + `Input.TextArea`（`viewConfig.tsx:1001-1007`）。
- `line || bar`：新增堆叠系列开关 `stack`（`Switch` 组件，`viewConfig.tsx:978-990`）。

**结构化单位库（unitFormat）**【已实现】  
`web/src/app/ops-analysis/utils/unitFormat.ts`：对齐 Grafana 单位分类与自动量纲缩放。支持单位族：
- `bytesIEC`（字节，IEC 1024 进制）、`bytesSI`（字节，SI 1000 进制）
- `bps`（比特/秒，自动 Kbps/Mbps/Gbps/Tbps）
- `ms`（毫秒，自动进位至 s/m/h/d）
- `percent`（0–100）、`percentunit`（0.0–1.0）
- `short`（计数自动缩放 K/M/B/T）
- `none`（原样）、`custom:<后缀>`（字面后缀，兼容旧自由文本 `unit`）

`formatDisplayValue`（`thresholdUtils.ts`）新增可选 `unitId` 形参：传入时委托 `formatUnit`；不传则保持原有自由文本后缀行为，向后兼容（证据：`thresholdUtils.ts formatDisplayValue` 函数签名及委托分支）。  
配置 UI：`GaugeSettingsSection` 的单位字段改为 `Select` 下拉（调用 `getUnitCategories()` 生成分组选项），`unitId` 为空时回退至自由文本 `unit` 字段（`gaugeSettingsSection.tsx:205-248`）。

**值映射（Value Mappings）**【已实现】  
`web/src/app/ops-analysis/utils/valueMapping.ts`：纯函数，支持四类规则：
- `value`：精确匹配（与 `String(raw)` 比较）
- `range`：数值区间（含边界，缺边界表示无穷）
- `regex`：正则匹配（非法正则忽略不报错）
- `special`：特殊值（null / nan / empty / true / false）

规则按声明顺序首条命中即返回（与 Grafana 一致）；结果含可选 `text`（展示文本）与 `color`（颜色 hex）。  
配置入口：`web/src/app/ops-analysis/components/valueMappingsConfigSection.tsx`（187 行）；已接入 `stateTimeline` 配置区与 `GaugeSettingsSection`；`singleValueSettingsSection.tsx` 亦引入该组件（证据：`valueMappingsConfigSection.tsx`；`viewConfig.tsx:992`）。

## 4. 依赖与通信【已实现/已存在】
- NATS：`nats/nats.py` 暴露 `get_operation_analysis_module_data`（`nats/nats.py:11`）/`get_operation_analysis_module_list`（`nats/nats.py:28`）（仅暴露自身数据源模块）；`common/get_nats_source_data.py:GetNatsData.get_data()` 为**通用数据源取数器**。其当前实现为**单命名空间取数**：先经 `_get_target_namespace()` 从 `params.namespace_id` 解析目标命名空间（运行时选择；未指定则取第一个可用命名空间，显式指定但数据源未关联该命名空间则报错），再按 `path` 在该命名空间的 NATS 客户端上解析函数；当客户端存在 `DEFAULT_NATS` 属性时改调 `get_customization_nast_data`，否则按 `path` 取同名函数（`common/get_nats_source_data.py:83-138`）。
  - 更正：operation_analysis **Python 代码中未硬编码调用** alerts 的 `get_alert_*`；这些是 alerts 独立的 NATS 端点，经通用取数器按 `path` 动态解析调用，非代码级内置依赖（证据：`grep -rn "get_alert_\|alerts\." --include=*.py` 在本模块无命中）。需注意：内置画布 YAML `support-files/builtin_canvases.yaml` 中确以 dataSource 字符串形式配置了 `get_alert_*`/`alert/get_alert_*` 等取数路径（约 37 处），即 alerts 是**配置态数据源**而非代码态依赖。
- 服务：`services/directory_service.py`（目录树）、`services/node_tree.py`、`services/import_export/*`（YAML 导入导出）。
- 依赖 `apps.core` 装饰器/视图工具；RPC 经 `OperationAnalysisRpc`（独立 server/namespace，`apps/rpc/base.py`）。
- 初始化/导出 management commands【已实现/已存在】：`init_builtin_canvases`（内置画布落地）、`init_default_namespace`（默认命名空间）、`init_default_groups`（默认分组）、`init_source_api_data`（内置数据源导入）、`export_source_api_data`（数据源导出），是内置画布与默认数据源/命名空间的落地机制（`management/commands/`）。

## 5. 风险 / 待确认
- 数据源为外部 REST/NATS，运营分析本身不落原始数据；数据一致性与缓存策略【待确认】。
- 无 Celery 后台任务【已实现】：任务文件已由顶层 `tasks.py` 调整为包形式 `tasks/tasks.py`，文件仍不含任何 Celery 任务（`tasks/tasks.py:1-4`，仅文件头注释）。

## 2026-07-01 Code-ARD 校准
- `[operation_analysis#20260701-013]` 补录 `api/scene_widgets/network_status_topology` 路由、view 权限、CMDB 拓扑/实例权限复用和 Alerts 活跃告警汇总边界。
- `[operation_analysis#20260701-014]` 补录开放导入导出 API Token 认证、组织解析、权限矩阵与实例/组织过滤。

## 6. 证据来源
`server/apps/operation_analysis/{urls.py:23,models/*,views/datasource_view.py,views/view.py,views/scene_widget_view.py:10,12,views/openapi_import_export_view.py:34,48,118,190,280,nats/nats.py,common/get_nats_source_data.py,constants/constants.py,tasks/tasks.py,management/commands/*,services/*,services/network_status_topology.py:5,65,87,services/import_export/authorization_service.py:24,71,87,180}`、`apps/operation_analysis/migrations/0010_remove_namespace_groups.py`、`apps/rpc/base.py:OperationAnalysisRpc`。

前端层新增证据：
- `web/src/app/ops-analysis/components/widgetRegistry.ts:14-25`（组件注册表全量映射）
- `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comBarGauge.tsx`、`comStateTimeline.tsx`、`comText.tsx`（新增三类组件）
- `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx:728,950,978-1010`（barGauge/stateTimeline/text/stack 配置分支）
- `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig/sections/gaugeSettingsSection.tsx:205-248`（unitId Select + 自由文本回退）
- `web/src/app/ops-analysis/utils/unitFormat.ts`（结构化单位库全量实现）
- `web/src/app/ops-analysis/utils/thresholdUtils.ts`（formatDisplayValue 新增 unitId 形参与委托分支）
- `web/src/app/ops-analysis/utils/valueMapping.ts`（值映射纯函数，四类规则）
- `web/src/app/ops-analysis/components/valueMappingsConfigSection.tsx`（值映射配置 UI，187 行）
