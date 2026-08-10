# 模块 ARD：Operation Analysis（运营分析）

> Migrated from `spec/ARD/modules/operation_analysis.md` as legacy capability evidence.

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
| DashboardReportSubscription | `models/subscription_models.py` | 画布报告订阅配置；绑定 Dashboard FK（兼容，Screen 可空）与 `resource_type`/`resource_id`、创建者 `(username, domain)`、组织、名称、状态、单个接收邮箱、邮件渠道及预留 config；`revision` 提供全字段 CAS，`version` 仅表示调度配置版本 |
| DashboardReportExecution | `models/subscription_models.py` | 一次 Dashboard 报告订阅执行审计；含 `resource_type`/`resource_id`；支持 manual 触发及 pending/running/succeeded/failed/unknown；`pending→running` 仅经 Claim；Delivery Fact 终态修正使用独立审计字段 |
| DashboardReportExecutionSnapshot | `models/subscription_models.py` | 一次订阅执行的不可变输入快照；冻结 `resource_type`/`resource_id`、Dashboard id、Subscription revision/schedule version、创建者 `(username, domain)`、执行组织、时区与已保存筛选值，不复制布局或 Widget |
| DashboardReportRenderSnapshot | `models/subscription_models.py` | 一次执行的不可变渲染输入；冻结 Dashboard 名称、布局、筛选、其他展示配置、`resource_type`/`resource_id`、`render_schema_version` 与 Widget 清单；清单只保留 DataSource identity，不复制运行配置或凭据 |
| DashboardReportPdfArtifact | `models/subscription_models.py` | 一次执行生成的短期 PDF 元数据；保存附件文件名、受控共享存储引用、文件大小、SHA-256、生成时间与到期时间，不提供历史下载或长期归档 |
| DashboardReportRenderToken | `models/subscription_models.py` | 一次 Execution 对应的一次性短时 Render Token 审计记录；数据库仅保存 SHA-256、到期与消费时间，明文只在 Worker 内存存在 |

内置机制【已实现/已存在】：`Directory`/`Dashboard`/`Topology`/`Architecture`/`Screen`/`Report` 通过 `is_build_in` + 唯一 `build_in_key` 标识内置画布，承载「内置视图对组织可见但不可删改」语义（删改在视图层被 `_raise_if_builtin` 拦截，见 §3）；`DataSourceTag.build_in` 标识内置标签。

## 3. 接口【已实现/已存在】
路由组：`data_source`/`dashboard`/`dashboard_subscription`/`dashboard_execution`/`directory`/`topology`/`architecture`/`screen`/`report`/`namespace`/`tag`/`import_export`/`scene_widgets`；开放端点 `open_api/import_export`。

关键自定义动作【已实现/已存在】：
- `data_source` 的 `get_source_data/{pk}`（POST）：组件运行时取数对外入口，是整个取数链路的起点（`views/datasource_view.py:337`）。
- `data_source` 的 `preview`（POST，保存后）与 `preview_config`（POST，未保存配置）：用于连接测试 / 数据预览。非 NATS 数据源在管理页直接走内联执行，NATS 仍按命名空间配置运行时取数；前端可把预览识别出的字段一键回填到 `field_schema`，并在设置页继续手工增删、排序与校验唯一字段名（`views/datasource_view.py:481-529`、`web/src/app/ops-analysis/(pages)/settings/dataSource/{previewPanel,fieldSchemaTable,operateModalUtils}.tsx`）。
- `directory` 的 `tree`（GET）：返回目录树（`views/view.py:148`）。
- `scene_widgets/network_status_topology`（POST）：按 `model_id`、`inst_id`、`depth` 构建网络状态拓扑场景数据，是网络状态拓扑组件的专用后端入口；复用 CMDB network_topology/实例权限并汇总 Alerts 活跃告警，权限动作 `view`（证据：`urls.py:23`、`views/scene_widget_view.py:10-23,10,12`、`services/network_status_topology.py:5,65,87`）。
- `screen` / `report`【已实现/已存在】：通过 `CanvasModelViewSet` 复用画布类 CRUD、权限与内置对象保护逻辑，新增 `directory.screen` 与 `directory.report` 两类权限域（`views/view.py:347-423`）。
- `dashboard_subscription`【已实现】：当前用户画布报告订阅 GET/POST/PATCH/DELETE。owner scope 使用 `(username, domain)`；创建与更新要求当前用户仍可查看目标画布（Dashboard 或 Screen）；写入支持 `dashboard` 或 `resource_type`+`resource_id`（`dashboard` 双写旧 FK；`screen` 无 dashboard FK）；响应返回 `resource_type`/`resource_id`；列表支持 `?dashboard_id=` 与 `?resource_type=&resource_id=`；PATCH/DELETE 使用 `revision` 原子 CAS；删除允许创建者在画布查看权限丢失后清理；`terminated` 不可由 API 直接写入（证据：`views/subscription_view.py`、`services/subscription_service.py`、`services/canvas_report/binding.py`、`serializers/subscription_serializers.py`）。
- `dashboard_subscription/{id}/execute` 与 `dashboard_execution/{id}`【已实现】：前者为已保存订阅创建 manual Execution、冻结 Input Snapshot，支持 `request_id` 幂等与在途串行，立即返回 Execution；请求线程不调用 Orchestrator。后者只读返回当前用户自己的执行及双 Snapshot。异步 Render Worker Claim 后经 Orchestrator 完成 Render + Email Delivery，两端均明确完成后才进入 `succeeded`；主链路无 `not_ready` placeholder（证据：`views/{subscription_view,execution_view}.py`、`services/{execution_service,execution_orchestrator,delivery_service}.py`）。
- `dashboard_execution/{id}/render-token-exchange` 与 `render-input`【已实现】：Worker 为 `running` Execution 签发一次性短时 Token，匿名 exchange 原子消费后建立绑定 Execution/Snapshot/attempt 的受限 Render Session；该会话默认拒绝普通 API，仅允许本 Execution 的 render-input 与 manifest 数据源查询，新 attempt 使旧会话失效。正式页面使用双 Snapshot 冻结布局与筛选，Widget 根据 manifest 中的 DataSource identity 实时解析当前定义、权限和凭据；Render Snapshot 不复制 DataSource 运行配置。PDF artifact 按 Execution 隔离；生产环境强制配置 Render/Delivery 共同可见的 `DASHBOARD_REPORT_ARTIFACT_ROOT`（证据：`views/execution_view.py`、`services/{render_token_service,render_scope_service,dashboard_report_renderer,report_render_service,render_snapshot_service}.py`）。
- `open_api/import_export`：开放导入导出 API 通过 `api_pass`/API Token 校验，支持 `export`、`precheck_import`、`submit_import` 三类动作；授权服务解析组织、计算导入导出权限矩阵，并在实例/组织维度过滤对象（证据：`views/openapi_import_export_view.py:34,48,118,190,280`、`services/import_export/authorization_service.py:24,71,87,180`）。

安全说明【已实现/已存在】：`NameSpace` 密码使用 AES（`PasswordCrypto`）加解密，密钥取自 `constants.constants.SECRET_KEY`；该密钥已移除源码内置硬编码值，仅从环境变量 `SECRET_KEY` 读取，未配置时为空串（`constants/constants.py:51-53`）。命名空间编辑时前端只回显掩码占位符；若用户未修改密码，提交时会省略 `password` 字段并以 PATCH 保留原密文，避免因重复提交掩码值而覆盖真实密码（`web/src/app/ops-analysis/(pages)/settings/namespace/operateModal.tsx:10-18,30-49,74-83`、`web/src/app/ops-analysis/api/namespace.ts:22-27`）。

### 前端层：画布组件与展示能力【已实现】

**组件注册表（widgetRegistry）**【已实现】
`web/src/app/ops-analysis/components/widgetRegistry.ts` 以 `chartType` 字符串为键，将组件类型映射至对应 React 组件，由 `getWidgetComponent` 统一解析。当前注册的组件类型（共 15 种）：

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
| topologyMap | topologyMap/index.tsx | 普通 DataSource 驱动的通用关系拓扑；消费 `{nodes, edges}`，使用 Dagre + X6 渲染 |
| room3D | widgets/room3D/index.tsx | 3D 机房大屏组件：消费 CMDB NATS `get_room3d_layout`，渲染 row/col 网格、U 占用、机柜类型、设备摘要与图例 |

证据：`web/src/app/ops-analysis/components/widgetRegistry.ts:11,22`、`web/src/app/ops-analysis/components/widgets/networkStatusTopology/index.tsx`、`web/src/app/ops-analysis/api/networkStatusTopology.ts:11-25`、`web/src/app/ops-analysis/components/widgets/room3D/{index.tsx,room3DData.ts,room3DMeshes.ts,room3DScene.ts}`。

**大屏与报表前端入口**【已实现】
- `screen`：前端提供独立页面、全屏、统一筛选、命名空间选择、组件布局与保存接口（`(pages)/view/screen/index.tsx:76-213`、`api/screen.ts:4-28`）。
- `report`：前端提供独立报表页面与读取接口，当前为基础画布模式，构建器仍处于占位态（`(pages)/view/report/index.tsx:37-109`、`api/report.ts:4-28`）。

## 4. 依赖与通信【已实现/已存在】
- NATS：`nats/nats.py` 暴露 `get_operation_analysis_module_data`（`nats/nats.py:11`）/`get_operation_analysis_module_list`（`nats/nats.py:28`）（仅暴露自身数据源模块）；`common/get_nats_source_data.py:GetNatsData.get_data()` 为**通用数据源取数器**。其当前实现为**单命名空间取数**：先经 `_get_target_namespace()` 从 `params.namespace_id` 解析目标命名空间（运行时选择；未指定则取第一个可用命名空间，显式指定但数据源未关联该命名空间则报错），再按 `path` 在该命名空间的 NATS 客户端上解析函数；当客户端存在 `DEFAULT_NATS` 属性时改调 `get_customization_nast_data`，否则按 `path` 取同名函数（`common/get_nats_source_data.py:83-138`）。
- 非 NATS 数据源预览执行器【已实现/已存在】：`services/datasource_preview/` 按 `source_type` 分派到数据库、REST API、Excel 执行器；数据库预览只允许单条 `SELECT` 或按表限量拉取，Excel 仅支持 `.xlsx` 且单文件不超过 2MB；预览结果会推断字段结构并回传给前端，供数据源默认字段定义复用（`services/datasource_preview/{registry,database,excel,schema}.py`）。
  - 更正：operation_analysis **Python 代码中未硬编码调用** alerts 的 `get_alert_*`；这些是 alerts 独立的 NATS 端点，经通用取数器按 `path` 动态解析调用，非代码级内置依赖（证据：`grep -rn "get_alert_\|alerts\." --include=*.py` 在本模块无命中）。需注意：内置画布 YAML `support-files/builtin_canvases.yaml` 中确以 dataSource 字符串形式配置了 `get_alert_*`/`alert/get_alert_*` 等取数路径（约 37 处），即 alerts 是**配置态数据源**而非代码态依赖。
- 服务：`services/directory_service.py`（目录树）、`services/node_tree.py`、`services/import_export/*`（YAML 导入导出）。
- 画布报告订阅 Adapter【Phase 3 已实现】：`services/canvas_report/` 注册 `dashboard` 与 `screen`；隔离布局 walker、Render Snapshot、权限与删除终止；Screen PDF 为 A4 landscape 单页等比 fit（策略 2）；Scheduler / Delivery / Claim 不感知布局（证据：`services/canvas_report/{registry,dashboard,screen,permissions}.py`、`services/{render_snapshot_service,subscription_service,dashboard_report_renderer,execution_orchestrator}.py`）。
- 依赖 `apps.core` 装饰器/视图工具；RPC 经 `OperationAnalysisRpc`（独立 server/namespace，`apps/rpc/base.py`）。
- 初始化/导出 management commands【已实现/已存在】：`init_builtin_canvases`（内置画布落地）、`init_default_namespace`（默认命名空间）、`init_default_groups`（默认分组）、`init_source_api_data`（内置数据源导入）、`export_source_api_data`（数据源导出），是内置画布与默认数据源/命名空间的落地机制（`management/commands/`）。

## 5. 风险 / 待确认
- 数据源为外部 NATS / 数据库 / REST API / Excel，运营分析本身不落原始数据；组件运行时已按 `scopeId + requestVersionKey + requestSignature` 做内存级请求缓存，`compare` 维度也参与签名，以减少同页重复请求，但跨页面/跨会话一致性仍依赖上游数据源【已实现 / 待确认】（`web/src/app/ops-analysis/utils/widgetRequestCache.ts:1-39`、`web/src/app/ops-analysis/components/widgetDataRenderer.tsx:324-354`）。
- Dashboard 报告 Render Task【已实现】：`operation_analysis.render_dashboard_report` 固定进入 `dashboard_report_render` 队列，由默认并发 2 的独立 Supervisor Worker 消费，负责原子 claim、Orchestrator Render、分级 Retry 与 Email Delivery；Cleanup 独立处理（`tasks/tasks.py`、`support-files/release/supervisor/dashboard_report_render_worker.conf`、`services/{execution_service,execution_orchestrator,delivery_service}.py`）。Retry 为同 task 多 attempt、按资源状态 resume，MVP 不接管 orphan。
- Dashboard 报告 Scheduler【已实现】：固定 Beat 每分钟触发 `operation_analysis.scan_due_dashboard_report_subscriptions`；`DueSubscriptionScanner` 仅扫描 `active + schedule_type/next_run_at 非空且到期` 的订阅，经专用 `create_scheduled` 创建 Execution 后复用 `_dispatch_render`；旧订阅无默认调度回填；missed-run 只补最近一期，不逐期追发（`services/{schedule_calculator,due_subscription_scanner,execution_service}.py`、`config.py`）。

## 2026-07-01 Code-ARD 校准
- `[operation_analysis#20260701-013]` 补录 `api/scene_widgets/network_status_topology` 路由、view 权限、CMDB 拓扑/实例权限复用和 Alerts 活跃告警汇总边界。
- `[operation_analysis#20260701-014]` 补录开放导入导出 API Token 认证、组织解析、权限矩阵与实例/组织过滤。

## 2026-07-09 Code-ARD 校准
- `[operation_analysis#20260709-001]` 3D 机房大屏组件 `room3D` 已注册到 `widgetRegistry`（此前 spec 未覆盖）：消费 CMDB NATS `get_room3d_layout` 返回的机房布局数据（含 `rack_type_name` 可读类型名），渲染 row/col 网格、机柜 U 占用、设备摘要与图例。
- `[operation_analysis#20260709-002]` `Room3DRack` 数据模型扩展 `rack_type_name?: string | null` 字段：区分 `rack_type` 枚举 id 与可读名称，作为机柜顶部贴图第二行文本（位置 + 类型名双行排版）与图例 label 渲染源（`web/src/app/ops-analysis/components/widgets/room3D/room3DData.ts:17` 定义、`:270-275` 校验、`:292` 返回；`room3DMeshes.ts:128` `createRackTopTexture(label, category?)` 双行排版；`index.tsx:114-125` 图例按 `rack_type_name` 去重）。机柜体颜色统一硬编码 `#82878b`（`room3DMeshes.ts:958`），移除 `RACK_COLOR_MAP` / `getRackVisualMeta`。
- `[operation_analysis#20260709-003]` `OpsAnalysisWidgetSurface` 收紧为 `'dashboard' | 'screen'`：移除 `'topology'` 表面（`utils/chartTypeSurface.ts:1`），并同步移除 `ROOM3D_CELL_GAP` import（`room3DMeshes.ts:7-9` 原 import 列表）、`room3DScene.ts:22-27` 导出块中的 `ROOM3D_CELL_GAP` re-export，以及 `getRackDoorOpenRotation` 函数（原位于 `room3DScene.ts` 顶部 export 块附近，本轮已整体删除）。
- `[operation_analysis#20260709-004]` `WidgetWrapper` 中"等待初始数据"判断抽为 `widgetRequestVersion.shouldWaitForInitialWidgetData`（`utils/widgetRequestVersion.ts:9` `WidgetInitialDataWaitOptions` 接口 + 函数收尾于 `:50-54`），调用点 `widgetDataRenderer.tsx:671-680,695-698`，属于纯重构，扩展加入 `hasResolvedDataSource` 因子。

## 2026-07-28 Phase 1A 校准

- `[operation_analysis#20260728-001]` 新增 Dashboard 报告订阅配置模型、migration、CRUD API 与 Dashboard 内 Modal。状态单字段为 `active/paused/terminated`，Phase 1A 仅开放前两者；未引入 Execution、Scheduler、PDF、Chromium、Email 或 Snapshot。

## 2026-07-28 Phase 1B-1 校准

- `[operation_analysis#20260728-002]` 新增 Dashboard 报告 Execution 基础模型、manual execute/retrieve API 与 Modal 立即测试反馈。同步实验路径显式经过 `pending/running/succeeded`，仅验证执行记录与状态机，不执行报告。

## 2026-07-29 Phase 1B-2A 校准

- `[operation_analysis#20260729-003]` 新增一对一 Execution Input Snapshot，冻结源对象标识和 Subscription 已保存筛选值。execute API 在快照成功后返回 `pending`；快照失败经 `pending → failed` 记录 `failure_stage=snapshot`。状态转换公开入口收敛到 Execution Service；不冻结页面临时筛选、布局、Widget、权限或 DataSource 运行态。

## 2026-07-29 Phase 1C 校准

- `[operation_analysis#20260729-004]` 新增统一 Execution Orchestrator 和 Permission/Snapshot/Render/Delivery 步骤边界。Manual Execute API 委托同一 Orchestrator；权限或 Snapshot 校验失败分别记录 `permission_check` / `snapshot`。Render 与 Delivery 仍为无副作用 placeholder，未接入异步任务、Chromium、PDF 或邮件。
- `[operation_analysis#20260729-005]` 修正 Manual Execute 异步边界与成功语义：POST 只创建并返回 `pending` Execution；View 不再同步调用 Orchestrator；未实现的 Render/Delivery 返回 `not_ready`，不得产生 `succeeded`。Subscription Modal 可查询并展示单条 Execution 状态。
- `[operation_analysis#20260729-006]` 新增一对一不可变 Render Snapshot。Orchestrator 在 Input Snapshot 校验后、Render Step 前冻结 Dashboard 配置及 Widget manifest；创建失败记录 `failure_stage=render_snapshot`。未新增 Render Route，未冻结 DataSource 运行配置，也未接入 Chromium、PDF、Email 或 Scheduler。
- `[operation_analysis#20260729-007]` 新增事务性 Execution Claim Service，通过条件更新及受影响行数保证同一 pending Execution 只被一个消费者领取并进入 running；公共 transition 禁止绕过 Claim。Orchestrator 改为只消费已领取的 running Execution，不再自行推进 pending。未新增 Worker、Chromium、PDF、Email、Scheduler 或 Retry。
- `[operation_analysis#20260729-008]` 接入 Execution Render Vertical Slice：Manual Execute 提交后异步派发专用队列 Render Task，独立 Worker claim 后经统一 Orchestrator 加载双 Snapshot；正式 execution render route 注入冻结筛选与布局，Chromium 仅等待显式 ready/failed 并生成临时 PDF artifact。Render 成功保持 running 等待 Delivery，失败记录 `failure_stage=render`。本阶段未实现 Render Token，使用 Worker 新建的无登录审计副作用标准用户会话作为阶段性边界；未实现 Email/Retry。
- `[operation_analysis#20260729-009]` Render 生产边界收口：新增一次性短时 Render Token 与匿名 exchange，明文不落库，短时渲染 JWT 绑定 Execution，普通登录 Session 与跨 Execution 会话不能读取 render-input；PDF artifact 增加附件文件名、到期时间和共享根目录硬约束。Release-image Chromium 回归增加 `fc-match`、版本与 PyMuPDF 中文文本提取断言；未实现 Email、Retry 或清理 Worker。

## 2026-07-30 MVP Closure 契约对齐

- `[operation_analysis#20260730-001]` 手动主链路（含 Email Delivery）已落地；报告取数使用实时 DataSource，不保证配置变更不影响历史或在途 Execution。清理过时的 Email 未实现 / `not_ready` placeholder / Phase 临时表述；`ALLOWED_TRANSITIONS` 去掉误导性的 `pending→running` 条目（Claim 仍为唯一入口）。
- `[operation_analysis#20260801-001]` 删除未被查询链路消费的 DataSource 配置审计副本；Render Snapshot 继续通过 Widget manifest 保留 DataSource identity，查询时实时解析当前定义、权限和凭据，不支持历史配置重放。
- `[operation_analysis#20260730-002]` Retry Resume / Orphan 语义对齐（未编码）：Execution 重试期间保持 `running`、claim 一次、同 task 多 attempt；下一 attempt 起点按 InputSnapshot / RenderSnapshot / Artifact 资源状态决定。**修正**：Snapshot 创建阶段 transient failure 允许再 ensure/create；仅冻结成功后损坏才终结且禁止重建。Artifact 可在 Delivery retry 复用；不可用 Artifact 视为需重跑 Render。MVP 超时收敛为 `failed`；orphan running 不自动 reclaim，且继续占用 in-flight 阻塞同订阅新的 manual/scheduled。

## 2026-08-01 多画布报告订阅 Phase 1

- `[operation_analysis#20260801-002]` 抽取 `CanvasReportAdapter` 边界（`services/canvas_report/`）：仅注册 `dashboard`；Render Snapshot / widget manifest、画布查看权限、PermissionStep 与 Dashboard 删除终止经 Adapter 分派。无 migration、无 `resource_type`/`resource_id` 落库、无对外 API 契约变更；`screen` 未注册。演进契约见 `specs/changes/canvas-report-subscription/spec.md`。

## 2026-08-03 多画布报告订阅 Phase 2

- `[operation_analysis#20260803-001]` Subscription / Execution / 双 Snapshot 落库 `resource_type`/`resource_id`（Render Snapshot 另加 `render_schema_version=1`）；migration `0020` 回填；写入归一化双写旧 `dashboard` FK；API 返回新字段并兼容 `?dashboard_id=` / `?resource_type=&resource_id=`；仍拒绝 Screen 订阅创建。

## 2026-08-03 多画布报告订阅 Phase 3

- `[operation_analysis#20260803-002]` 注册 `ScreenCanvasReportAdapter`；开放 `screen` 订阅写入（无 dashboard FK）；migration `0021` 快照 `dashboard_id` 可空；Screen 删除终止订阅；PDF 策略 2（viewport 来自 snapshot + A4 landscape 等比 fit）；前端 Screen 订阅入口与 render 分支。PermissionStep 经 Adapter 存在性判断支持删除后在途继续；Screen render-input HTTP 合同已覆盖。migration `0022` 冻结 `resource_display_label`；Delivery 消费展示标签而非 `resource_type` 分支；订阅/执行入口统一 `require_canvas_view`。演进契约见 `specs/changes/canvas-report-subscription/spec.md`。

## 2026-08-09 TopologyMap MVP 校准

- `[operation_analysis#20260809-001]` 新增普通 DataSource `chartType=topologyMap`：MVP 面向可直接返回 `{nodes, edges}` object 的 NATS DataSource，不修改 mysql/postgresql/rest_api/excel connector runtime。前端以 graph-local node id 校验引用，使用单一 Dagre 自动布局与独立 X6 viewer；empty 上报 `empty` 并允许报告 `report-ready`，非法 graph 上报 `failed`。该组件与 `networkStatusTopology` Scene Widget 保持实现与契约隔离。Self-loop 不静默丢弃，但默认 X6 能力不能可靠显示，记为 Current Limitation。变更契约与证据见 `specs/changes/ops-analysis-topology-map-mvp/spec.md`。

## 2026-08-10 单值说明字段与表格单元格样式

- `[operation_analysis#20260810-001]` 仪表盘 `single` 增加可选 `descriptionField`（主值下方原样说明行；空态仍由主值门控）。生产 `ComTable` 增加列级 `valueMappings` / `cellThresholdColors` / `cellType`（`text` | `colorBackground` 纯色块），操作列不配置样式；不改挂 `OpsAnalysisTable`。变更契约与证据见 `specs/changes/ops-analysis-single-description-table-cell-styling/spec.md`。

## 6. 证据来源
`server/apps/operation_analysis/{urls.py,models/*,views/datasource_view.py,views/view.py,nats/nats.py,common/get_nats_source_data.py,constants/constants.py,tasks/tasks.py,management/commands/*,services/*}`、`apps/operation_analysis/migrations/0010_remove_namespace_groups.py`、`apps/rpc/base.py:OperationAnalysisRpc`、`web/src/app/ops-analysis/{utils/widgetRequestCache.ts,components/widgetDataRenderer.tsx,api/namespace.ts,(pages)/settings/namespace/operateModal.tsx}`。

前端层新增证据：
- `web/src/app/ops-analysis/components/widgetRegistry.ts:12-21`（组件注册表全量映射）
- `web/src/app/ops-analysis/api/networkStatusTopology.ts:11-25`（网络状态拓扑组件取数）
- `web/src/app/ops-analysis/api/{screen.ts,report.ts}`、`web/src/app/ops-analysis/(pages)/view/{screen/index.tsx,report/index.tsx}`（大屏/报表入口）
- `web/src/app/ops-analysis/utils/{singleDescription.ts,tableCellStyle.ts}`、`web/src/app/ops-analysis/components/widgets/{comSingle.tsx,comTable.tsx}`（单值说明字段与表格列单元格样式）
