# 多画布报告订阅（Dashboard + Screen）

Status: in-progress（Phase 3 done；Phase 4 未做）

### Completion Evidence（Phase 3）

- PDF 策略 2 已冻结于 §6；常量 `SCREEN_PDF_*` + `resolve_render_viewport` / `resolve_screen_pdf_scale`
- `ScreenCanvasReportAdapter` 注册；writable 含 `screen`；`can_view_canvas` 走 `directory.screen`
- Migration `0021`：Execution/Render Snapshot `dashboard_id` 可空；Screen 无 dashboard FK
- Screen 删除经 Adapter `terminate_for_resource_deletion`；前端 Screen 订阅入口 + render 分支
- Release remediation（B1/B2）：
  - PermissionStep 经 `canvas_resource_exists`（Adapter `load_resource`）做画布无关存在性判断；`source_canvas_deleted_during_execution` + Render Snapshot 时继续执行（Dashboard/Screen 对称）
  - Screen `GET .../render-input/` HTTP 合同：冻结 `resource_type`/`viewport`、不读 live layout、Render Session scope 拒绝跨 Execution
- Release remediation（Non-blocking 收敛）：
  - Screen 创建 / PermissionStep 真实实例权限链测试（`get_permission_rules` → `ScreenModelViewSet`，不 mock `can_view_canvas`）
  - Snapshot 冻结 `resource_display_label`；Delivery 不再按 `resource_type` 分支文案
  - Subscription/Execution 入口统一 `require_canvas_view`（Dashboard 仍经 `can_view_dashboard` 测试缝）
  - Screen Delivery channel team boundary 合同；Screen ready 聚合 widget terminal status
- 验收：`test_canvas_report_*` + `test_dashboard_report_*` + orchestrator + render_token **252 passed / 4 skipped**；FE Screen ready **2 passed**

### Release Follow-ups（仍不处理）

- `SCREEN_PDF_SINGLE_PAGE` 强制 page.pdf 参数化
- Orchestrator 大规模拆分 / Render schema 重构 / 多画布 rename
- Dashboard `can_view_dashboard` 测试缝最终拆除（与全量 monkeypatch 迁移绑定）

### Completion Evidence（Phase 1）

- `CanvasReportAdapter` + `DashboardCanvasReportAdapter` + 注册表：`server/apps/operation_analysis/services/canvas_report/`
- 调用改道：Render Snapshot / DS 扫描 manifest、`can_view_dashboard`→`can_view_canvas`、PermissionStep→`can_view_canvas`、Dashboard destroy 终止钩子
- 验收：`test_canvas_report_adapter.py` + `test_dashboard_report_*` + `test_execution_orchestrator.py` **209 passed / 4 skipped**；`makemigrations operation_analysis --check` 无变更
- Phase 1 硬约束满足：无 schema / 无 `resource_*` 落库 / 无对外 API 契约变更；`screen` 未注册

### Completion Evidence（Phase 2）

- Migration `0019`（已合并原 0020–0022）：Subscription / Execution / Input Snapshot / Render Snapshot 自建表起即含 `resource_type`/`resource_id`；Snapshot `dashboard_id` 可空；Render Snapshot 含 `render_schema_version`（默认 1）；Input/Render Snapshot 含 `resource_display_label`（默认「仪表盘」）
- 写入归一化：`services/canvas_report/binding.py`；只传 `dashboard` 或 `resource_type=dashboard`+`resource_id` 双写；`screen` 拒绝
- API：响应返回新字段；列表保留 `?dashboard_id=`，新增 `?resource_type=&resource_id=`
- 验收：`test_canvas_report_resource_binding.py` + Dashboard 报告全量回归 **216 passed / 4 skipped**；`makemigrations operation_analysis --check` 无新变更；`screen` Adapter 仍未注册
- 仍不创建 Screen 订阅（Phase 3）

Originating MVP: [`../dashboard-report-subscription/spec.md`](../dashboard-report-subscription/spec.md)

Release Gate（Dashboard MVP）: [`../dashboard-report-subscription/release-review-remediation.md`](../dashboard-report-subscription/release-review-remediation.md)

## Problem Statement

运营分析已交付仅绑定 Dashboard 的报告订阅主链路。产品需要在同一套订阅、执行、投递能力上支持 Screen（大屏），而不是复制第二套 Subscription / Execution / Delivery 栈。当前实现把资源绑定、权限、布局遍历和 Chromium 渲染硬编码为 Dashboard，无法安全扩展到 Screen，同时又不能在扩展时破坏已发布的 Dashboard 订阅行为。

## Solution

在现有报告订阅编排壳层上引入画布适配边界：用 `resource_type` + `resource_id` 表达订阅绑定的分析画布，通过 `CanvasReportAdapter` 隔离资源加载、权限、Render Snapshot / manifest 与渲染路由差异。Scheduler、Execution 状态机、Render Token、PDF Artifact 与 Email Delivery 继续画布无关。首期只开放 Dashboard 与 Screen；既有 Dashboard 订阅在兼容期内行为不变。类名与表名不在首期一次性改名为 `CanvasReportSubscription`。

## User Stories

1. As an 运营分析用户, I want 继续按现有方式管理 Dashboard 报告订阅, so that 已上线能力不因多画布演进而回归。
2. As an 运营分析用户, I want 对 Screen 创建、编辑、暂停、恢复、删除并手动测试报告订阅, so that 大屏也能按计划或即时投递 PDF 邮件。
3. As an 运营分析用户, I want Screen 订阅执行使用创建时冻结的布局与筛选语义、且取数仍按我当前权限实时解析, so that 版式稳定且不泄露凭据或过期授权。
4. As an 系统, I want 删除 Dashboard 或 Screen 时终止其关联未删除订阅并正确处理在途执行, so that 源画布消失后不会继续错误投递。
5. As an 开发者, I want Execution / Scheduler / Delivery 不感知画布类型细节, so that 后续扩展其他画布时只需新增 Adapter，而不复制订阅栈。

## 1. 目标和非目标

### 目标

- 将报告订阅绑定从「仅 Dashboard」演进为「分析画布」：首期支持 `dashboard` 与 `screen`。
- 保持现有 Dashboard 报告订阅的对外行为、安全边界与执行语义不变（兼容期内）。
- 复用同一 Subscription / Execution / Snapshot / Render Token / PDF / Delivery 栈；按画布类型注入 Adapter。
- 延续 MVP 已冻结的安全决策：`(username, domain)` 身份、revision CAS、Render scoped identity、Email Channel 组织边界、Delivery Fact 专用 reconciliation、DataSource 运行配置不冻结。

### 非目标

- Topology、Architecture、Report、NetworkTopology 的报告订阅。
- 一次性将模型/表/类/URL 全量 rename 为 `CanvasReport*`。
- 为 Screen 复制平行的订阅、执行、调度或投递实现。
- 冻结 DataSource `query_config` / `field_schema` / connection / credential，或支持历史运行配置重放。
- 改变 Delivery Fact 与普通终态不可变的仲裁模型。
- Orchestrator 职责拆分重构（既有 FU-02）。
- 对象存储长期归档、历史 PDF 下载、逐期漏期追发等 MVP 已排除项。

## 2. Domain Model

### 资源绑定

订阅与执行的源画布统一表示为（**自 Phase 2 起落库**；Phase 1 仅代码内隐式 `dashboard`）：

| 字段 | 含义 |
|---|---|
| `resource_type` | 画布类型；首期枚举：`dashboard` \| `screen`；取值对齐运营分析 `CANVAS_TYPE_REGISTRY` |
| `resource_id` | 对应画布主键 |

术语遵循仓库 glossary：**报告订阅**绑定一个分析画布；**订阅执行**仍是一次生成与投递的审计边界。

### 兼容既有 `dashboard` / `dashboard_id`

渐进迁移，不破坏已有行与客户端（字段引入自 **Phase 2**）：

1. 现有 `dashboard` FK（及 Snapshot 中的 `dashboard_id` 等列）在 Phase 1–3 **保留可读可写**（Phase 1 无新列）。
2. Phase 2 新增 `resource_type`（默认 `dashboard`）与 `resource_id`。
3. 数据回填：`resource_type='dashboard'` 且 `resource_id = dashboard_id`（或 FK id）。
4. 写入归一化：
   - 若只传旧字段 `dashboard`：服务端写入 `resource_type=dashboard`、`resource_id=<id>`，并同步维护旧 FK/列。
   - 若传 `resource_type` + `resource_id`：校验类型合法；当类型为 `dashboard` 时同步旧 FK/列；当类型为 `screen` 时旧 Dashboard FK 置空（或不使用），不得伪造 dashboard 绑定。
5. 读取 API：同时返回 `resource_type` / `resource_id`；Dashboard 场景继续返回既有 `dashboard` 字段直至 Phase 4 命名收敛。
6. 查询参数：保留 `?dashboard_id=` 语义（隐含 `resource_type=dashboard`）；新增 `?resource_type=&resource_id=`（或等价过滤）。

### 快照与审计字段

- **Execution Input Snapshot**：冻结 `resource_type`、`resource_id`、订阅 revision/schedule version、创建者 `(username, domain)`、`execution_team_id`、渠道 id、筛选值与语义；不复制布局。
- **Render Snapshot**：冻结资源展示名/更新时间、布局 payload、筛选 payload、other/decorations 所需展示配置，以及 `widget_manifest`（仅 widget/component identity + `datasource_id`）。
- **删除联动**：`source_canvas_deleted_during_execution` 语义保持；终止原因扩展为画布删除（可保留旧 `dashboard_deleted` 值作 dashboard 兼容，Screen 使用明确 reason 或统一 `canvas_deleted`——实现期在不破坏审计查询的前提下二选一并写清迁移）。

### 目标命名（延后）

域语言可称「画布报告订阅」；物理模型在 Phase 4 前仍可使用现有 `DashboardReport*` 表/类名。Phase 4 再评估 rename，**禁止**与 Screen 功能交付绑在同一大爆炸迁移里。

## 3. Adapter Boundary

### `CanvasReportAdapter`

按 `resource_type` 注册的适配器，是编排层感知画布差异的**唯一**边界。

职责：

| 职责 | 说明 |
|---|---|
| Resource loading | 按 `resource_id` 加载当前画布实体；不存在则按既有缺失语义失败 |
| Permission check | 封装 `can_view_canvas`；供创建/更新扫描与 Execution PermissionStep |
| Filter loading | 读取创建/执行所需的筛选定义来源（Dashboard 顶层 `filters` vs Screen `view_sets.filters`） |
| Manifest generation | 从该类型布局结构收集 `{widget_id, widget_type, datasource_id}` |
| Render snapshot generation | 深拷贝布局与筛选等展示输入，写入统一 Render Snapshot 契约 |
| Render route | 声明 Worker/前端使用的渲染页路径或路由选择键（仍经统一 render-input） |
| Delete termination hook | 画布销毁前终止关联订阅（Dashboard 已有；Screen 必须对等） |

### 编排侧不感知布局

Execution / Scheduler / DueScanner / Claim / Timeout / RetryClassifier / Render Token 签发与 scoped auth 框架 / PDF Artifact 存储 / Email Channel 校验与 SMTP Delivery / Delivery Fact reconciliation **不感知** `resource_type` 的布局细节；它们只消费订阅行、执行行、统一 Snapshot 字段与 Adapter 输出的契约数据。

### Adapter 依赖边界

允许依赖：

- 对应画布模型与资源加载逻辑；
- 画布实例权限判断（经 `can_view_canvas` / 既有 ViewSet 规则）；
- 该类型的 filter 定义读取、layout walker、manifest 构建；
- Render Snapshot 展示输入的组装规则（落库仍由既有 Snapshot 服务/调用方完成时可注入，解析与深拷贝规则属 Adapter）；
- 渲染路由键 / 前端类型选择所需的纯描述信息。

禁止依赖（不得 import、回调或反向控制）：

- DueScanner / ScheduleCalculator / 订阅调度推进；
- Execution 状态机、Claim、Timeout、RetryClassifier、Orchestrator 编排主循环；
- Email Channel 校验、SMTP Delivery、Delivery Fact reconciliation；
- PDF Artifact 存储与队列投递实现细节。

Adapter 只产出契约数据（资源元数据、manifest、snapshot payload、route key、权限布尔结果）；生命周期与投递副作用留在现有 Subscription / Execution / Delivery 服务，避免 Adapter 演变成第二套大 Service。

### 分派

`get_canvas_report_adapter(resource_type) -> CanvasReportAdapter`。未知类型拒绝创建/执行。首期实现 `DashboardCanvasReportAdapter` 与 `ScreenCanvasReportAdapter`；Phase 1 仅前者接入，行为与现网等价。

## 4. Snapshot Contract

### 冻结（Render Snapshot / 等价展示输入）

- 布局结构（Dashboard：grid/`view_sets` list；Screen：`viewport` + `items` + `decorations` 等 layout object）。
- 组件/Widget 结构（含 chart 类型等展示标识，以现有深拷贝策略为准）。
- 筛选定义与本次执行已解析的筛选值（Input Snapshot 持值；Render Snapshot 持定义/展示所需 filters payload）。
- 资源展示名与用于乐观展示的更新时间。
- `widget_manifest`：仅 identity + `datasource_id`。

### 不冻结

- DataSource 运行配置（`query_config` / `field_schema` / connection）。
- 凭据与解密后的密钥材料。
- 权限规则快照、组织成员资格快照（执行期与 Render 期实时复核 creator）。
- Channel SMTP 配置与凭据（Delivery 实时读取，沿用 RR-03）。

### 统一性

Dashboard 与 Screen 共用同一 Input / Render Snapshot **表与 API 形状**；`layout_payload` / `filters_payload`（或现有 `view_sets` / `filters` 列）的解释由 `resource_type` + Adapter 负责，不拆平行 Screen 快照表族。

### `render_schema_version`（架构预留，Phase 2 可选）

为支撑 Dashboard / Screen 异构 layout payload 的后续演进，Render Snapshot（及如需要的 API 投影）预留可选字段 `render_schema_version`（正整数）。

- **Phase 1**：不引入、不实现。
- **Phase 2**：可随 `resource_type` / `resource_id` 一并落库；默认 `1`；首期 Dashboard / Screen 均可为 `1`。
- 解释仍以 `resource_type` 为主；本变更**不**实现多版本并存迁移器或协商协议。
- 禁止在无版本字段时随意改写已发布 payload 含义；若未来同类型布局合同破坏性变更，递增该版本并单独约定兼容策略。

## 5. Permission Contract

### `can_view_canvas(request_or_user, resource_type, resource_id, team_context) -> bool`

统一实例查看校验入口，映射：

| `resource_type` | 实例权限域 |
|---|---|
| `dashboard` | `directory.dashboard`（现有 Dashboard ViewSet 规则） |
| `screen` | `directory.screen`（现有 Screen ViewSet 规则） |

功能级入口权限仍使用运营分析既有 `view-View`，**不**新增 `screen-View` 一类平行功能键。

### `can_view_canvas` 职责

只负责：

- 给定用户（或 request 用户上下文）与组织上下文下，是否可**查看**指定 `resource_type` + `resource_id` 的画布实例。

不负责（保持 MVP 多层权限边界，由既有模块继续承担）：

- DataSource 实例/组织数据权限与创建期 DataSource 已知权限扫描；
- Render / Widget `get_source_data` 等查询权限与 execution scope；
- Email Channel 组织归属、类型与凭据有效性（Delivery / Channel Service）；
- Execution / Subscription 属主身份（`(username, domain)`）、revision CAS 等并发与属主边界。

`CanvasReportAdapter` 的 permission check **仅**封装 `can_view_canvas`；不得在 Adapter 内合并上述其他权限层。

### 行为对齐

- 创建/更新 active 订阅：要求当前用户可 `can_view_canvas` 目标资源（pause-only 豁免等既有例外保持，且对 Screen 同样适用）。创建期 DataSource 扫描仍走既有扫描路径，不并入 `can_view_canvas`。
- Execution PermissionStep：按执行冻结的资源身份调用 `can_view_canvas`（及 creator 解析）；失败 error_code 语义与现网 dashboard 失败对齐或扩展为 canvas 中性码（实现期保持可观测、不复活终态）。
- 分享/公开大屏会话**不得**作为订阅执行身份；订阅仍使用 creator 稳定身份 + Render scoped principal。
- 删除订阅：仍以创建者 `(username, domain)` 为主，不因画布查看权丢失而阻断清理。

## 6. Render Contract

### 统一流程

```text
Execution (running)
  → Adapter 生成 Render Snapshot
  → Render Token（绑定 execution / snapshot / attempt）
  → Chromium 打开统一渲染路由
  → 前端按 resource_type 选择画布渲染实现
  → GET render-input（scoped）
  → Widget/组件按 manifest 实时取数
  → ready signal
  → PDF
  → Delivery
```

### 统一面

- **render-input**：同一 Execution API；返回含 `resource_type` 的 input/render snapshot（Phase 2+；Phase 1 仍为现有 Dashboard 形状）。
- **ready signal**：Worker 等待单一渲染完成协议；Dashboard / Screen 可由 Adapter/前端映射到同一等待条件（允许内部事件名不同，对外合同稳定）。
- **PDF flow**：同一 Claim、Artifact、队列与 Delivery；Dashboard 保持现有默认策略；Screen 视口与页面策略见下节，**不得默认继承** Dashboard PDF 语义。

### Screen PDF 输出策略（已冻结 — Phase 3）

Dashboard 现有 PDF 输出语义（含固定视口 1440×900 与 print 预处理）**不得**默认继承为 Screen 语义。

**选定策略：2 — 缩放到统一 PDF 页**

| 项 | 约定 |
|---|---|
| Chromium 视口 | 使用 Render Snapshot 中 Screen `view_sets.viewport` 的宽高打开页面 |
| PDF 页面 | 固定 **A4 landscape 单页**（页格式与 Dashboard 对齐，但视口语义独立） |
| 缩放 | 整幅 Screen 画布 **等比缩放完整落入一页**；MVP **不分页** |
| 溢出 | 禁止裁切丢失；靠缩放保证 fit |
| 自动化 | render-input 声明的 viewport 与 Worker 使用的视口一致；PDF 策略常量可单测 |

Dashboard 路径保持现网固定 `VIEWPORT=1440×900` + A4 landscape，不受本策略影响。

### 差异归属

布局引擎、print 预处理、组件树（含 Screen-only 组件如 room3D）、Chromium 视口与页面挂载，一律由 **Adapter + 对应前端 renderMode 实现**处理；Orchestrator 与 Delivery 无分支。

Render Token 的 scoped allowlist 可按路由扩展，但鉴权模型（不建普通登录 Session、`_verify_token` fail-closed、creator 实时权限复核）不变。

## 7. Migration Strategy

渐进迁移原则：

1. **先缝后类型**：Phase 1 只抽 Adapter，Dashboard 路径行为金丝雀等价；**无 schema / 无 `resource_*` 落库**。
2. **先字段后双写**：Phase 2 增加 `resource_type`/`resource_id`（可选一并加 `render_schema_version`）并回填；旧 `dashboard` 字段双写保留。
3. **再开放 Screen**：Phase 3 在 PDF 策略已冻结前提下注册 Screen Adapter、API/UI、删除终止、Render 页。
4. **最后命名收敛**：Phase 4 再评估表/类/URL rename；可与废弃只读兼容字段一起做，单独变更、单独回归。

禁止：

- 首期 drop 旧 `dashboard` FK 或强制客户端一次性改字段。
- 未回填就依赖 `resource_id` 唯一路径。
- 为 Screen 新建平行 `ScreenReportSubscription` 表栈。
- Phase 1 将 `resource_type` / `resource_id`、任何 schema 变更或对外 API 契约变更与 Adapter 抽取绑在同一提交。
- Phase 1–3 将物理模型一次性 rename 为 `CanvasReport*`。

## 8. Implementation Plan

### Phase 1 — 抽 Adapter，Dashboard 行为不变

硬约束（本 Phase 全部满足）：

- **不新增 migration**；
- **不修改数据库 schema**；
- **不引入** `resource_type` / `resource_id`（及 Snapshot 对等列、`render_schema_version`）；
- **不修改** 现有 Subscription / Execution 对外 API 请求/响应契约（字段名、语义、错误码保持兼容）；
- 仅做代码内 Adapter 抽取与调用改道；Dashboard 路径上 `resource_type` 可视为隐式常量，**不得落库**。

工作项：

- 定义 `CanvasReportAdapter` 与注册表；实现 Dashboard Adapter，替换直连 Dashboard 模型的 Snapshot / manifest / 权限调用点。
- Scheduler、Execution、Delivery、Render Token 经 Adapter 取画布契约数据，但仅注册 `dashboard`。
- 验收：全量 Dashboard 报告订阅回归通过；`makemigrations --check` 无新变更。

### Phase 2 — `resource_type` 支持

- Migration：加 `resource_type`/`resource_id`（及 Snapshot 对等字段），默认与回填 dashboard。
- 可选：同批预留 `render_schema_version`（默认 `1`），不实现多版本迁移器。
- 写入/读取归一化与双写；列表过滤兼容。
- API 开始返回新字段；旧客户端仅用 `dashboard` 仍可用。
- 仍不创建 Screen 订阅。

### Phase 3 — Screen 支持

准入：§6 Screen PDF 输出策略已冻结并写入文档。

- `ScreenCanvasReportAdapter`：items walker、filters 来源、`directory.screen`、viewport、render 路由键。
- Screen 删除终止订阅；创建期 DS 扫描与 PermissionStep（权限层分离保持）。
- 前端：Screen 入口订阅 UI；Render 页按类型挂载 Screen `renderMode`；PDF 按冻结策略实现。
- 测试：Screen CRUD 订阅、跨类型隔离、权限拒绝、Render scope、Delivery 组织边界回归；Dashboard 回归不降级。

### Phase 4 — 命名收敛

- 评估并执行文档/类/路由/表向 Canvas Report 命名的收敛。
- 废弃冗余 dashboard-only 列或只读兼容层（若产品允许破客户端）。
- 明确下一批画布（若有）只加 Adapter，不开新栈。

## Implementation Decisions

- 模块边界：在运营分析报告订阅服务层增加 Adapter 注册与分派；遵守 §3 Adapter 依赖边界；不把画布 JSON 解析细节泄漏进 DueScanner、DeliveryService 或 reconcile 路径。
- 资源枚举首期锁定为 `dashboard` 与 `screen`；其他 registry 类型显式拒绝。
- API 采用渐进 Canvas 化，而非长期平行的 Screen 专用订阅 API；**不**引入 Screen 平行订阅栈。
- Render Snapshot 继续一张表；用 `resource_type` 解释 payload，不建 Screen 专用快照模型；`render_schema_version` 仅为 Phase 2 可选预留。
- DataSource 策略继承 MVP：**不改变**实时解析策略；manifest 只保留 identity；查询实时鉴权。
- 安全基线继承 Dashboard MVP Release Gate：身份二元组、revision CAS、Render scoped identity、Channel 边界、Delivery Fact 专用 reconciliation。
- 物理 rename 推迟到 Phase 4；Phase 1–3 **不提前** rename `DashboardReport*`；以行为与字段兼容为交付标准。
- Phase 1 与资源模型迁移解耦：无 migration / 无 schema / 无 API 契约变更。

## Testing Decisions

- 好测试只断言外部行为：API 状态码与字段、执行终态、权限拒绝、Render scope 拒绝、邮件通道边界、Dashboard 兼容路径。
- 优先最高缝：HTTP API、订阅生命周期、Execution retrieve/render-input、Delivery 服务边界；Adapter 可用针对 walker/权限映射的聚焦单测，但不得用 mock 绕过真实权限链冒充通过。
- Prior art：`test_dashboard_report_*`、Render Token scope 测试、Delivery channel 边界测试、revision 并发测试。
- Phase 1 门禁：现有 Dashboard 报告套件零回归；确认无新增 migration。
- Phase 3 门禁：PDF 策略已文档冻结；新增 Screen 行为用例 + 全量 Dashboard 回归；Chromium 集成仍可按环境 skip，但 Render Contract（render-input、scope、viewport 与策略一致性）必须有自动化证据。
- 禁止引入第二套 Screen 订阅测试夹具去复制整栈编排，应复用执行/投递夹具并切换 `resource_type`。

## Out of Scope

见第 1 节非目标。另不包括：分享链路作为订阅执行身份、Screen 手动浏览器 PDF 工具栏与订阅 PDF 强制合一、多收件人、非 email 渠道、Phase 1 的 schema/API 泛化、Phase 1–3 的 `DashboardReport*` 全量 rename。

## Further Notes

- 仓库 glossary 已将报告订阅定义为绑定「分析画布」；本变更使实现与术语对齐，并显式限制首期类型集合。
- 与 Dashboard MVP spec 的关系：MVP 仍是 Dashboard 行为与安全基线的事实来源；本 spec 是其上的多画布演进契约。冲突时，已发布安全边界（Release Gate）不得削弱。
- 前端可从 Screen 详情预填 `resource_type=screen`；跨画布选择器非 Phase 3 必须项。
- Screen PDF 策略与打印就绪信号的产品拍板是 Phase 3 准入项，不阻塞 Phase 1–2。
