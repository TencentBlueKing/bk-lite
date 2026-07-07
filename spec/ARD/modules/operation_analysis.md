# 模块 ARD：Operation Analysis（运营分析）

> 路径 `server/apps/operation_analysis` ｜ API 前缀 `api/v1/operation_analysis/`

## 1. 职责【已实现/已存在】
统一可视化层：聚合外部 REST/NATS 数据源，组织仪表盘、拓扑、架构图，并向大屏、报表两类新画布扩展；同时提供网络状态拓扑场景组件与配置导入导出能力。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Directory | `models/models.py` | 层级目录（最多 3 级）；含 `is_build_in`/`build_in_key`（unique）内置标识 |
| Dashboard / Topology / Architecture | `models/models.py` | 仪表盘/拓扑/架构图（filters、view_sets JSON）；三者均含 `is_build_in`/`build_in_key`（unique）内置标识 |
| Screen / Report | `models/models.py` | 大屏/报表画布；均含 `directory`、`view_sets`、`is_build_in`/`build_in_key` |
| NameSpace | `models/datasource_models.py` | NATS 连接配置（域/账号/密码加密/TLS）；含 `namespace`（NATS 命名空间标识，消息主题前缀，default=`bklite`）；含 `is_active`（内部预留，前端不暴露、运行时不校验） |
| DataSourceAPIModel | `models/datasource_models.py` | 数据源定义；含 `source_type`（NATS/MySQL/PostgreSQL/REST API/Excel）、`connection_config`（连接配置）、`query_config`（取数配置）、`chart_type`（JSON，图表类型，default=list）、`field_schema`（JSON，接口返回字段定义，default=list）、`is_active`（内部预留） |
| DataSourceTag | `models/datasource_models.py` | 数据源标签；含 `build_in`（是否内置） |

内置机制【已实现/已存在】：`Directory`/`Dashboard`/`Topology`/`Architecture`/`Screen`/`Report` 通过 `is_build_in` + 唯一 `build_in_key` 标识内置画布，承载「内置视图对组织可见但不可删改」语义（删改在视图层被 `_raise_if_builtin` 拦截，见 §3）；`DataSourceTag.build_in` 标识内置标签。

## 3. 接口【已实现/已存在】
路由组：`data_source`/`dashboard`/`directory`/`topology`/`architecture`/`screen`/`report`/`namespace`/`tag`/`import_export`/`scene_widgets`；开放端点 `open_api/import_export`。

关键自定义动作【已实现/已存在】：
- `data_source` 的 `get_source_data/{pk}`（POST）：组件运行时取数对外入口，是整个取数链路的起点（`views/datasource_view.py:337`）。
- `data_source` 的 `preview`（POST，保存后）与 `preview_config`（POST，未保存配置）：用于连接测试 / 数据预览。非 NATS 数据源在管理页直接走内联执行，NATS 仍按命名空间配置运行时取数；前端可把预览识别出的字段一键回填到 `field_schema`，并在设置页继续手工增删、排序与校验唯一字段名（`views/datasource_view.py:481-529`、`web/src/app/ops-analysis/(pages)/settings/dataSource/{previewPanel,fieldSchemaTable,operateModalUtils}.tsx`）。
- `directory` 的 `tree`（GET）：返回目录树（`views/view.py:148`）。
- `scene_widgets/network_status_topology`（POST）：按 `model_id`、`inst_id`、`depth` 构建网络状态拓扑场景数据，是网络状态拓扑组件的专用后端入口（`views/scene_widget_view.py:10-23`）。
- `screen` / `report`【已实现/已存在】：通过 `CanvasModelViewSet` 复用画布类 CRUD、权限与内置对象保护逻辑，新增 `directory.screen` 与 `directory.report` 两类权限域（`views/view.py:347-423`）。

安全说明【已实现/已存在】：`NameSpace` 密码使用 AES（`PasswordCrypto`）加解密，密钥取自 `constants.constants.SECRET_KEY`；该密钥已移除源码内置硬编码值，仅从环境变量 `SECRET_KEY` 读取，未配置时为空串（`constants/constants.py:51-53`）。命名空间编辑时前端只回显掩码占位符；若用户未修改密码，提交时会省略 `password` 字段并以 PATCH 保留原密文，避免因重复提交掩码值而覆盖真实密码（`web/src/app/ops-analysis/(pages)/settings/namespace/operateModal.tsx:10-18,30-49,74-83`、`web/src/app/ops-analysis/api/namespace.ts:22-27`）。

### 前端层：画布组件与展示能力【已实现】

**组件注册表（widgetRegistry）**【已实现】  
`web/src/app/ops-analysis/components/widgetRegistry.ts:12-29` 以 `chartType` 字符串为键，将组件类型映射至对应 React 组件，由 `getWidgetComponent` 统一解析。当前注册的组件类型（共 9 种）：

| chartType | 组件文件 | 说明 |
|-----------|---------|------|
| line | comLine.tsx | 折线图 |
| bar | comBar.tsx | 柱状图（含堆叠模式，由 `stack` 字段控制）|
| pie | comPie.tsx | 饼图 |
| table | comTable.tsx | 表格 |
| single | comSingle.tsx | 单值 |
| topN | comTopN.tsx | Top-N |
| gauge | comGauge.tsx | 仪表盘（半圆/整圆） |
| eventTable | eventTable/eventTable.tsx | 事件表（事件流） |
| networkStatusTopology | networkStatusTopology/index.tsx | 网络状态拓扑场景组件 |

证据：`web/src/app/ops-analysis/components/widgetRegistry.ts:12-21`、`web/src/app/ops-analysis/components/widgets/networkStatusTopology/index.tsx`、`web/src/app/ops-analysis/api/networkStatusTopology.ts:11-25`。

**大屏与报表前端入口**【已实现】  
- `screen`：前端提供独立页面、全屏、统一筛选、命名空间选择、组件布局与保存接口（`(pages)/view/screen/index.tsx:76-213`、`api/screen.ts:4-28`）。
- `report`：前端提供独立报表页面与读取接口，当前为基础画布模式，构建器仍处于占位态（`(pages)/view/report/index.tsx:37-109`、`api/report.ts:4-28`）。

## 4. 依赖与通信【已实现/已存在】
- NATS：`nats/nats.py` 暴露 `get_operation_analysis_module_data`（`nats/nats.py:11`）/`get_operation_analysis_module_list`（`nats/nats.py:28`）（仅暴露自身数据源模块）；`common/get_nats_source_data.py:GetNatsData.get_data()` 为**通用数据源取数器**。其当前实现为**单命名空间取数**：先经 `_get_target_namespace()` 从 `params.namespace_id` 解析目标命名空间（运行时选择；未指定则取第一个可用命名空间，显式指定但数据源未关联该命名空间则报错），再按 `path` 在该命名空间的 NATS 客户端上解析函数；当客户端存在 `DEFAULT_NATS` 属性时改调 `get_customization_nast_data`，否则按 `path` 取同名函数（`common/get_nats_source_data.py:83-138`）。
- 非 NATS 数据源预览执行器【已实现/已存在】：`services/datasource_preview/` 按 `source_type` 分派到数据库、REST API、Excel 执行器；数据库预览只允许单条 `SELECT` 或按表限量拉取，Excel 仅支持 `.xlsx` 且单文件不超过 2MB；预览结果会推断字段结构并回传给前端，供数据源默认字段定义复用（`services/datasource_preview/{registry,database,excel,schema}.py`）。
  - 更正：operation_analysis **Python 代码中未硬编码调用** alerts 的 `get_alert_*`；这些是 alerts 独立的 NATS 端点，经通用取数器按 `path` 动态解析调用，非代码级内置依赖（证据：`grep -rn "get_alert_\|alerts\." --include=*.py` 在本模块无命中）。需注意：内置画布 YAML `support-files/builtin_canvases.yaml` 中确以 dataSource 字符串形式配置了 `get_alert_*`/`alert/get_alert_*` 等取数路径（约 37 处），即 alerts 是**配置态数据源**而非代码态依赖。
- 服务：`services/directory_service.py`（目录树）、`services/node_tree.py`、`services/import_export/*`（YAML 导入导出）。
- 依赖 `apps.core` 装饰器/视图工具；RPC 经 `OperationAnalysisRpc`（独立 server/namespace，`apps/rpc/base.py`）。
- 初始化/导出 management commands【已实现/已存在】：`init_builtin_canvases`（内置画布落地）、`init_default_namespace`（默认命名空间）、`init_default_groups`（默认分组）、`init_source_api_data`（内置数据源导入）、`export_source_api_data`（数据源导出），是内置画布与默认数据源/命名空间的落地机制（`management/commands/`）。

## 5. 风险 / 待确认
- 数据源为外部 NATS / 数据库 / REST API / Excel，运营分析本身不落原始数据；组件运行时已按 `scopeId + requestVersionKey + requestSignature` 做内存级请求缓存，`compare` 维度也参与签名，以减少同页重复请求，但跨页面/跨会话一致性仍依赖上游数据源【已实现 / 待确认】（`web/src/app/ops-analysis/utils/widgetRequestCache.ts:1-39`、`web/src/app/ops-analysis/components/widgetDataRenderer.tsx:324-354`）。
- 无 Celery 后台任务【已实现】：任务文件已由顶层 `tasks.py` 调整为包形式 `tasks/tasks.py`，文件仍不含任何 Celery 任务（`tasks/tasks.py:1-4`，仅文件头注释）。

## 6. 证据来源
`server/apps/operation_analysis/{urls.py,models/*,views/datasource_view.py,views/view.py,nats/nats.py,common/get_nats_source_data.py,constants/constants.py,tasks/tasks.py,management/commands/*,services/*}`、`apps/operation_analysis/migrations/0010_remove_namespace_groups.py`、`apps/rpc/base.py:OperationAnalysisRpc`、`web/src/app/ops-analysis/{utils/widgetRequestCache.ts,components/widgetDataRenderer.tsx,api/namespace.ts,(pages)/settings/namespace/operateModal.tsx}`。

前端层新增证据：
- `web/src/app/ops-analysis/components/widgetRegistry.ts:12-21`（组件注册表全量映射）
- `web/src/app/ops-analysis/api/networkStatusTopology.ts:11-25`（网络状态拓扑组件取数）
- `web/src/app/ops-analysis/api/{screen.ts,report.ts}`、`web/src/app/ops-analysis/(pages)/view/{screen/index.tsx,report/index.tsx}`（大屏/报表入口）
