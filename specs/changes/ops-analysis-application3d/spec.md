# 运营分析 3D 应用场景组件

Status: implemented (pending review / Phase 7–8 benchmark)

## Implementation Evidence (WIP)

- Backend domain: `server/apps/operation_analysis/services/application3d/`（QueryService、health/severity/notifications、exact relation projection、Share/Normal 共用）。
- Normal APIs: `POST .../scene_widgets/application3d/{wall,application_detail,alarm_detail,metric}/`
- Share APIs: `POST .../share/session/{id}/application3d/{wall,application_detail,alarm_detail,metric}/`
- Frontend: Scene capability metadata、Screen-only selector、Three.js Wall + Detail DOM、ephemeral `system_status` filter。
- Tests (fresh): `pytest .../test_application3d_*.py` → **15 passed**；vitest capability+layout → **6 passed**；`pnpm type-check` ok。
- Review fixes applied: per-app relation integrity；policy-incomplete → unavailable；same-card reselect no-op；AbortController on unmount。
- 未完成/待校准：真实浏览器 20/50/100/200 WebGL benchmark、hard capacity 产品值、import/export/Report 完整 metadata 拒绝矩阵、CMDB 字段级 View 权限进 properties、Share 撤权/query-count 测试、silent refresh 增量 reconcile、E2E。

application3D Alarm Detail 是 MonitorAlert 的场景化投影，不是 Monitor Alert Detail UI 的直接复用。它可以裁剪字段和增加 Application 场景派生信息，但共享领域概念必须与 Monitor 同源同义；不得用不同来源的数据冒充同一业务概念。

## Problem Statement

运营分析 Screen 缺少一个以应用为业务中心、同时表达关联主机监控健康的 3D 场景。现有普通 DataSource Widget 适合消费通用数据并渲染图表，`networkStatusTopology` 则是网络领域专用的 self-fetch Scene Widget；两者都不能表达完整的 Application Wall → Focus → Application Detail 交互，也不能把 CMDB Application、`application_run_host`、Monitor 权限与 `MonitorAlert` 健康口径安全地收敛在一个后端查询接缝中。

旧 3D 应用墙仅作为深色背景、应用卡片、状态颜色、glow、告警 badge 和 camera intro 的 UX reference。其 API、数据基座、Babylon/Three 封装、颜色编码、参数和代码均不是本变更的输入契约。

## Solution

新增运营分析场景组件：

```text
name: 3D应用
sceneWidgetType: application3D
surface: Screen only
engine: Three.js
runtime: self-fetch Scene Widget
```

`application3D` 在 Normal Screen 和 Share Screen 中提供完整能力：

```text
Application Wall
→ Application Focus
→ Application Detail
→ Close Detail（保持 Focus）
→ Back to Wall
```

前端拥有请求与场景生命周期，但不拥有 CMDB × Monitor 聚合。所有领域查询、权限过滤、Application→Host projection、Host→Monitor mapping、`MonitorAlert` 聚合、属性展示转换和 Alarm scope 校验均由 permission-aware backend seam 完成。

## User Stories

1. 作为 Screen 搭建者，我可以添加并配置 `application3D`（通用标题/appearance），但不能把它添加到 Dashboard、Report、Topology、Architecture 或其他 Canvas，也无需勾选 Application 列表。
2. 作为 Screen 使用者，我可以在连续 3D Application Wall 中看到每个 Application 的名称、当前健康、最高严重级别和 active alarm badge；并可用 ephemeral 的应用系统运行状态多选过滤 Wall。
3. 作为使用者，我在查看/分享态点击 Application 后先看到即时的本地 3D focus，再主动进入 Scene 内完整 Application Detail，而不是被跳转到 CMDB 页面；编辑态仅预览、不可场景交互。
4. 作为使用者，我在 Application Detail 中看到与 Wall 完全同源的 active alarm 数量、severity statistics、列表、详情、previous/next、真实通知结果和按需指标快照。
5. 作为 Share 访问者，我在 sharer current authorization 下获得与 Normal Screen 相同的数据、交互和撤权行为，不能利用 Share 参数扩大资源范围。
6. 作为维护者，我可以通过统一 Scene Widget metadata 管理 surface、self-fetch、Share 和 Report 能力，不再增加 `type === A || type === B` 特判。

## Product Boundary

### Included

- Screen add/edit/view。
- Normal Screen 与 Share Screen。
- 真实 Three.js/WebGL 3D Application Wall。
- 当前 actor 权限可见的全部 Application 自动上墙（无编辑期 Application 勾选）。
- 连续 Wall、`system_status` filter、refresh、empty/error/unknown/stale。
- Application selection、focus、detail、close detail、back（仅 view/share）。
- `application_run_host` 关联 Host 的 Monitor 健康聚合。
- 经 exact `system_contains_application` 的父 System.`status` 成员过滤（与健康投影解耦）。
- Application Detail 的属性、severity statistics、active alarm browsing、alarm detail、previous/next、通知摘要和 metric snapshot trend。
- Screen 编辑态对齐 `room3D`：无场景交互，仅预览；view/share 全交互。
- 20/50/100/200 Application 的真实浏览器 benchmark 与 capacity 校准。
- Scene Widget capability metadata 最小收敛，并登记 `application3D` 与既有 `networkStatusTopology`。

### Explicit Non-goals

- Application dependency lines 或 Application-to-Application relation。
- 部署架构、APM Service Wall。
- Dashboard、Report、Topology、Architecture 或其他 Canvas 支持（仅针对 `application3D`）。
- 编辑期 Application 白名单/勾选（类 NST 设备列表）。
- Application 模型自身字段业务 filter（如 `app_type`）；Screen unified filter 绑定。
- `system_status` 选择写入 Widget/`valueConfig` 持久化默认值。
- 编辑态 Scene interaction mode / 显式场景交互开关。
- 本变更重构 `networkStatusTopology` 的混合 Share 路径。
- Central Alert integration。
- Prometheus、Zabbix、K8s、SNMP 或 APM 告警健康聚合。
- 任意 CMDB relation、BFS projection、`Application ← System → Host` **健康** fallback、Module/Service 中间路径。
- 传统 Wall 分页。
- 自由拖动 3D Application cards 或复杂自由相机。
- 旧 Babylon/Three 代码迁移。
- 为未来 APM、部署架构或跨告警源能力预留 DTO 字段。
- application3D 领域专用配置项（第一版仅复用通用 Widget 项：标题、appearance 等）。

## Surface and Capability Contract

### Capability matrix

| Surface | Add | Edit | View | Share | Report |
| --- | --- | --- | --- | --- | --- |
| Screen | yes | yes | yes | yes | no |
| Dashboard | no | no | no | no | no |
| Report | no | no | no | no | no |
| Topology / Architecture / other Canvas | no | no | no | no | no |

限制必须由统一 Scene Widget capability metadata 执行。目标 metadata 至少表达：

```ts
interface SceneWidgetCapability {
  type: SceneWidgetType;
  selfFetch: boolean;
  surfaces: readonly OpsAnalysisWidgetSurface[];
  shareSupported: boolean;
  reportSupported: boolean;
}
```

`application3D` 固定为：

```ts
{
  type: 'application3D',
  selfFetch: true,
  surfaces: ['screen'],
  shareSupported: true,
  reportSupported: false
}
```

既有 `networkStatusTopology` 一并登记为（固化当前产品事实，不是本变更收窄）：

```ts
{
  type: 'networkStatusTopology',
  selfFetch: true,
  surfaces: ['dashboard', 'screen'],
  shareSupported: true,
  reportSupported: false
}
```

该 metadata 是 selector、registry、runtime、import/export validation、copy/duplicate、Share rendering 和报告拒绝的共同事实来源。不得只在 WidgetSelector 隐藏，也不得通过手工构造旧配置把 Widget 放进不支持的 Canvas。Import/copy 遇到 surface 不匹配必须拒绝整个非法 Widget 配置并给出可定位错误，不得静默降级成普通 chart。新增路径禁止再写 `type === '…'` 能力特判；本变更不建设通用 plugin framework，也不重做 NST 业务/Share 模型。

## Domain Invariants

### Application identity

唯一 canonical identity：

```text
model_id = application
id = CMDB Application.inst_uuid
```

Three object key、selection、health reconciliation、detail query、cache、Share capability 和请求去重均使用 `inst_uuid`。Application name 仅显示，禁止作为 identity 或 join key。Wire contract 不增加始终等于 `id` 的 `renderKey`。

### Application health resource projection

第一版唯一合法 **健康** projection：

```text
CMDB Application
  └─ model_asst_id = application_run_host
       └─ peer model_id = host
```

Hard invariants：

- 只认 `application_run_host`。
- 按当前 CMDB association 定义解析方向；Application 位于 src/dst 哪侧都必须以 relation metadata 判定 peer，不能假定数组方向。
- peer 必须为 `host`；错误 peer 不纳入且视为 projection integrity failure，不能静默传播健康。
- wrong relation、任意直接 Host association、BFS、System fallback、Module/Service 路径均不纳入健康。
- shared Host 合法；一个 Host 的同一 `MonitorAlert` 可以影响所有通过 `application_run_host` 关联它的 Application。
- 去重键是 Host `inst_uuid`；同一 Application 重复 relation 不得重复计算告警。
- 零 Host（无任何合法 `application_run_host` peer）在查询完整时为 `normal` / `no_active_alarm` / `activeAlarmCount=0`，不是 `unavailable`。

### Wall membership

默认 Wall 成员 = 当前 actor 权限可见的全部 Application（CMDB Application View），无编辑期勾选。

可选 `system_status` filter 经 exact `system_contains_application` 收窄成员（见 Filters）；该路径不得用于 Host/告警健康聚合。

### Authoritative alarm model

第一版唯一 authoritative chain：

```text
CMDB Application(inst_uuid)
→ application_run_host
→ permission-visible Host
→ Host.monitor_id
→ authorized MonitorInstance
→ authorized MonitorPolicy
→ MonitorAlert(status="new")
→ Application-level aggregation
```

Central Alert 不参与 Wall health、severity statistics、alarm count、alarm membership、alarm detail、notification、metric trend 或 previous/next。

### Active alarm scope

对某一 Application `A`，定义：

```text
ScopedActiveAlerts(A, actor)
= permission-scoped MonitorAlerts
  WHERE status = "new"
  AND monitor_instance_id IN AuthorizedMonitorIds(
        VisibleHosts(A, application_run_host, actor)
      )
```

Wall 和 Detail 必须由同一个 `ScopedActiveAlerts` 查询模块生成。Wall 的 `activeAlarmCount=N`、Detail severity statistics、alarm list、alarm detail membership 和 navigation collection 必须引用同一集合。禁止 Wall 使用 Host summary、Detail 再走另一套查询口径。

## Health and Severity Semantics

### Health state

```ts
type ApplicationHealthState = 'normal' | 'alarming' | 'unknown';

type ApplicationHealthReason =
  | 'no_active_alarm'
  | 'active_alarm'
  | 'unavailable'
  | 'stale_after_refresh_failure';

// Backend internal only; MUST NOT be serialized to Normal or Share clients.
type ApplicationHealthInternalReason =
  | 'monitor_mapping_missing'
  | 'permission_incomplete'
  | 'source_failure';
```

Health、Alert Severity、Alert Type 是三条正交轴：

- **Application health**：`normal` / `alarming` / `unknown`。`unknown` 只表示无法得到可信完整结论，不等于 no_data，也不等于 info。
- **Alert severity**：`MonitorAlert.level` → canonical `critical` > `error` > `warning`，外加 `info` 仅作 defensive compatibility。
- **Alert type**：`MonitorAlert.alert_type` = `alert` | `no_data`。

Health invariant（查询 scope 完整时）：

```text
incomplete mapping/permission/aggregation → unknown / unavailable
complete && activeAlarmCount == 0 → normal
complete && activeAlarmCount > 0 → alarming
```

规则：

| Condition | state | reason | count semantics |
| --- | --- | --- | --- |
| 查询完整，任意 `status=new` MonitorAlert ≥ 1（含 only `alert_type=no_data`） | alarming | active_alarm | exact non-null；按每条 Alert 的 `level` 计入 `severityCounts` / `highestSeverity` |
| 查询完整，无任何 active alert | normal | no_active_alarm | `0` |
| 查询完整，且无 `application_run_host` 关联 Host（零 Host） | normal | no_active_alarm | `0` |
| 必需 Host 缺 monitor_id / mapping 无法确认 | unknown | unavailable | `null`，不得伪造部分 count |
| CMDB Host、MonitorInstance 或 MonitorPolicy scope 不完整 | unknown | unavailable | `null` |
| 单个 Application 聚合无法完成 | unknown | unavailable | `null` |
| silent refresh 失败且仍显示上次完整成功值 | 保留上次 state | stale_after_refresh_failure | 保留上次 exact count，`stale=true` |

`null` 表示无法证明完整、精确的计数；`0` 只表示完整查询明确得到零条。Widget-level 功能权限拒绝使用现有 permission/error UI，不通过单张 Application card 暗示隐藏资源。

Backend 可以使用 `ApplicationHealthInternalReason` 做控制流、审计和诊断，但不得把它、隐藏资源数量或可反推出隐藏资源存在性的错误文案序列化到 Normal/Share wire response。所有 per-Application mapping、permission 或局部 source completeness 问题在 wire 上统一折叠为 `unknown/unavailable`。无法生成可信 Wall 的整体 source failure 继续使用 Widget-level hard error，不伪装成某张 Application 的具体内部原因。Normal 与 Share 使用同一 presenter 和折叠规则。

禁止 `unknown/no_data_alarm`。已完整查到的 no_data Alert 是真实活跃告警，health 必须是 `alarming`。

### Canonical severity

```ts
type SeverityId = 'critical' | 'error' | 'warning' | 'info' | 'normal';
type SeverityColor = 'critical' | 'danger' | 'warning' | 'info' | 'success';

interface Severity {
  id: SeverityId;
  label: string;
  rank: 400 | 300 | 200 | 100 | 0;
  color: SeverityColor;
}
```

| id | rank | semantic color | product role |
| --- | ---: | --- | --- |
| critical | 400 | critical | Monitor 正式告警档：最高级 |
| error | 300 | danger | Monitor 正式告警档：明确故障 |
| warning | 200 | warning | Monitor 正式告警档：风险/退化 |
| info | 100 | info | **defensive compatibility only**。正常 Monitor UI 不产生；若 API/evaluator 产生 `MonitorAlert(level=info,status=new)`，仍按 alarming + info 处理，不得映射为 unknown |
| normal | 0 | success | 仅完整查询且无 active alert 时使用 |

正式产品告警档位只有 critical / error / warning。canonical type 保留 info ≠ Wall/Detail 固定展示「提示」档，也不新增 Application health state。

后端把 Monitor 原始 `level` 归一成完整 `Severity`；Widget 不解释 Monitor level 排序，不硬编码跨域 severity mapping。`color` 是平台语义色 key，前端统一映射到现有 design token，不由后端返回十六进制颜色。

### `no_data`

`no_data` 是 `MonitorAlert.alert_type`，与 `MonitorAlert.level` 正交。生产数据可以是 `alert_type=no_data` 且 `level=critical|error|warning`（info 仅 edge compatibility）。

- 所有 scoped `status=new` MonitorAlert（含 no_data）都按自身 `level` 计入 `activeAlarmCount`、`severityCounts`、`highestSeverity`。
- `noDataAlarmCount` 只统计 `alert_type=no_data`，是类型维，不是 severity 维。
- 同一条 no_data + critical 同时：`severityCounts.critical += 1` 且 `noDataAlarmCount += 1`。这不是 double-count。`activeAlarmCount` 按 Alert 记录数只加一次。
- 识别到的 severity 求和：对可映射的 `critical|error|warning|info`，以及 **空 `MonitorAlert.level`（防御性按 warning 计入）**，`sum(severityCounts) == activeAlarmCount`。非空但无法映射的 level 仍只计入 `activeAlarmCount`，可不进入 `severityCounts`。`noDataAlarmCount` 不参与该求和。
- only no_data critical → `state=alarming`，`highestSeverity=critical`，不得 `highestSeverity=null`，不得 unknown。
- 空 `level` 的 active alert（含 no_data）→ 按 `warning` 计入 severity / highestSeverity / 卡片文案「警告」；不得画成 critical/「严重告警」，也不得「状态未知」。
- Alarm list/detail 的 no_data 项必须返回真实 `severity`，禁止 `isNoData=true → severity=null`。
- Detail UI：严重/错误/警告是固定产品级别；左侧应用信息不单独展示「告警类型 / 无数据告警」统计格；告警列表项可保留「无数据告警」类型标签。info 仅当 `severityCounts.info > 0` 时动态出现。

## Backend Architecture

形成 application3D 专用深模块，具体文件和类名实施时按 `operation_analysis` 现有 convention 落位。模块的外部 interface 只接受 scene operation、已验证 actor/share scope 和最小参数，只返回 application3D DTO。

```text
Normal Scene View ─┐
                   ├─ Application3DQueryService
Share Capability ─┘       ├─ visible Application query
                           ├─ optional system_status via system_contains_application
                           ├─ exact application_run_host projection
                           ├─ Host monitor_id mapping
                           ├─ MonitorInstance permission scope
                           ├─ MonitorPolicy permission scope
                           ├─ MonitorAlert scope/aggregation
                           ├─ CMDB display property presenter
                           ├─ notification presenter
                           └─ metric snapshot resolver
```

这是一个真实的领域查询 seam，不引入通用跨告警源 binding framework。Normal 与 Share 必须调用同一 domain module，不能复制两套聚合。

### Permission chain

```text
Authenticated user / reconstructed sharer
↓ core/session authentication
operation-analysis View
↓ operation-analysis permission
Screen View
↓ Screen ownership/team permission
application3D Scene operation
↓ scene capability + widget declaration
visible CMDB Applications
↓ CMDB Application View, batch
application_run_host
↓ exact relation projection, batch
visible Hosts
↓ CMDB Host View, batch
Host.monitor_id
↓ batch mapping, no hidden identity exposure
authorized MonitorInstances
↓ existing Monitor instance permission, batch
authorized MonitorPolicies
↓ existing Monitor policy permission, batch
MonitorAlert(status="new")
↓ one scoped query/aggregation
Application DTO
```

Requirements：

- 复用现有 CMDB topology View 与 MonitorInstance/MonitorPolicy permission helper；不得用 `skip_permission`、superuser shortcut 绕过 current team。
- Share actor 重建后执行同一权限链。
- partial permission 或 mapping completeness 无法证明时，不返回部分值冒充完整值。
- 不返回隐藏 Host 数量、隐藏 MonitorInstance identity 或“存在 N 个无权资源”。
- 无权限与不存在在详情/IDOR 路径使用仓库现有统一 fail-closed 响应，禁止资源枚举。

### IDOR protection

所有 application/detail/alarm/metric operation 必须重新验证：

```text
Application visible
AND exact application_run_host projection
AND Host/Monitor/Policy permission
AND alert_id ∈ ScopedActiveAlerts(applicationId, actor)
```

禁止仅凭 `applicationId + arbitrary alertId` 读取 Alert。跨 Application alert、已关闭/恢复 alert、撤权 alert、非关联 Host alert 均 fail closed。Metric operation 还必须先完成同一 alarm membership 校验。

### Query/performance invariants

禁止：

```text
for Application → query Hosts
for Host → query Monitor
for Monitor → query Alerts/Policies
```

要求：

- batch visible Applications。
- batch exact relation projection；如果底层图服务缺少批量接口，在 backend module 内做有界批次调用并设置总预算，禁止前端 fan-out。
- batch Host entity/monitor_id lookup。
- batch MonitorInstance permission filtering。
- batch MonitorPolicy permission filtering。
- one/few bounded MonitorAlert aggregation queries。
- batch policy metadata for list/detail page。
- query count 随固定批次近似常数，不随 Application/Host 数线性增长。
- 列表与 relation 输入有服务端 capacity/batch guard；不得无界加载整表。
- 使用 Django ORM，禁止 raw SQL。

Backend tests 必须断言 query count；若 CMDB 图查询不是 Django DB query，则另断言其批次调用次数上界。

## Wire Contracts

所有 DTO 都是 UI-oriented contract。不得向 Widget 暴露 `Host[]`、`MonitorInstance[]`、raw `MonitorAlert[]`、CMDB raw schema、password/sensitive 字段、Three presentation state 或 Central Alert 字段。

### Shared types

```ts
type ApplicationHealthState = 'normal' | 'alarming' | 'unknown';

type ApplicationHealthReason =
  | 'no_active_alarm'
  | 'active_alarm'
  | 'unavailable'
  | 'stale_after_refresh_failure';

interface Severity {
  id: 'critical' | 'error' | 'warning' | 'info' | 'normal';
  label: string;
  rank: 400 | 300 | 200 | 100 | 0;
  color: 'critical' | 'danger' | 'warning' | 'info' | 'success';
}

interface SeverityCounts {
  critical: number;
  error: number;
  warning: number;
  info: number;
}

interface DisplayProperty {
  key: string;
  label: string;
  displayValue: string;
}
```

Numbers in count objects are always finite non-negative integers. `DisplayProperty.displayValue` is already converted for display and never contains raw password/secret values.

### Application property selection

`DisplayProperty[]` 由 application3D backend presenter 控制，不由 Widget、Screen 配置、Share 参数或 CMDB raw response 动态决定。第一版采用 default-deny、ordered allowlist：

```text
Application entity
→ application3D code-owned ordered property key allowlist
→ CMDB field-level View permission
→ sensitive/password exclusion
→ CMDB display conversion
→ non-empty DisplayProperty[]
```

Requirements：

- backend application3D module 维护唯一、带顺序的 Application property key allowlist；Normal/Share 复用同一 allowlist 和 presenter。
- 第一版有序 allowlist 固定为：`app_id` → `app_type` → `organization` → `operator` → `bak_operator` → `comment`。
- 不允许“返回所有非敏感字段”、遍历全部 CMDB schema 自动出现在 UI，或让请求参数选择任意字段。
- `id/inst_uuid` 和 Application name 已有专用 DTO 字段，不在 properties 中重复。
- key 不在 allowlist、调用者无字段 View 权限、字段类型被标记 sensitive/password/secret、或值无法安全 display-convert 时均省略。
- label 和 displayValue 必须来自 CMDB metadata/display conversion；Widget 不接收 raw value、raw enum/schema 或自行格式化日期、枚举、引用、表格等字段。
- Allowlist 中字段在具体 Application model 不存在或值为空时只省略该 property；`properties=[]` 合法。
- 后续调整展示字段是 backend presenter policy 变更，必须经过 contract review；不得借由 filter 或 Share capability 扩大字段面。

### ApplicationWallData

```ts
interface ApplicationWallData {
  items: ApplicationWallItem[];
  filters: ApplicationFilterDefinition[];
  appliedFilters: Record<string, string[]>;
  refreshedAt: string; // ISO-8601
  capacity: {
    actualCount: number;
    supportedCount: number | null;
  };
}

interface ApplicationWallItem {
  id: string; // Application.inst_uuid
  name: string;
  health: {
    state: ApplicationHealthState;
    reason: ApplicationHealthReason;
    activeAlarmCount: number | null;
    severityCounts: SeverityCounts | null;
    noDataAlarmCount: number | null;
    highestSeverity: Severity | null;
    stale: boolean;
  };
}
```

Semantics：

- `items=[]` 是合法 empty wall，不是 failure。
- `highestSeverity=null`：`unknown/unavailable`，或 `alarming` 但 scoped active alerts 仅含非空且无法映射的 level。`normal` 使用 `id=normal` 的 Severity。空 `level` 防御性按 warning。有可映射 level（含空→warning、no_data、defensive info）的 `alarming` 必须带最高 Severity。
- `severityCounts=null`、`activeAlarmCount=null` 表示查询不完整，不得渲染为零。
- `stale=true` 只允许来自同一 actor/scope/filter 的上一次完整成功 snapshot；权限撤销不能保留 stale detail。
- `supportedCount=null` 表示 benchmark 尚未校准 hard capacity，不表示无限支持。
- `ApplicationWallData` 不含分页字段。

### ApplicationDetailData

```ts
interface ApplicationDetailData {
  application: {
    id: string;
    name: string;
    health: ApplicationWallItem['health'];
    properties: DisplayProperty[];
  };
  alarms: ApplicationDetailAlarmCollection;
  refreshedAt: string;
}

type ApplicationDetailAlarmCollection =
  | {
    state: 'available';
    activeAlarmCount: number;
    severityCounts: SeverityCounts;
    noDataAlarmCount: number;
    highestSeverity: Severity | null;
    items: ApplicationAlarmListItem[];
    page: {
      nextCursor: string | null;
      hasMore: boolean;
    };
  }
  | {
    state: 'unavailable';
  };

interface ApplicationAlarmListItem {
  id: string;
  content: string;
  severity: Severity | null;
  alertType: 'alert' | 'no_data';
  isNoData: boolean;
  occurredAt: string | null;
  resource: {
    id: string; // Host.inst_uuid, not MonitorInstance.id
    name: string;
  };
  metricName: string | null;
  durationSeconds: number;
  policyName: string;
}
```

Semantics：

- Detail health/statistics 必须与同一 Wall refresh generation 的 scope 一致；重新获取后允许反映更新的 active collection，但响应内部必须自洽。
- `alarms.state='available'` 表示权限、mapping 和查询完整；此时 counts 必须全部精确且非 null。
- `alarms.state='unavailable'` 不携带内部 reason、count、statistics、items 或 cursor，避免把部分结果误解为完整结果或暴露隐藏资源存在性。
- `alarms.items=[]` 且 `activeAlarmCount=0` 是合法 zero alarms，只能出现在 `available` 分支。
- 列表分页只用于 Detail DOM alarm browser，不改变连续 Wall；cursor 必须 opaque、scope-bound，不能携带可篡改权限范围。
- `metricName` 必须来自真实指标展示名：`query_condition.type='metric'` → `Metric.display_name`（fallback `Metric.name`）；`type='formula'` → `result_name`。**禁止**使用 `MonitorPolicy.alert_name`（告警名称/标题模板）冒充指标名；无法解析时为 `null`。
- `isNoData` 与 `severity` 正交：no_data Alert 仍返回按 `MonitorAlert.level` 归一的 Severity；`severity=null` 只用于无法映射的 level，不得仅因 `isNoData` 清空。
- `alertType` 来自 `MonitorAlert.alert_type`（归一为 `alert` | `no_data`），不得并入 severity。
- Application properties 由 CMDB display conversion 生成，遵循字段权限并排除 sensitive/password fields。空 properties 合法。
- Detail silent refresh 的普通网络失败可以在客户端暂留同 actor/scope 的上次完整数据并显式显示 stale；服务端新响应不使用 `unavailable` 表达 transient transport failure。权限/作用域变化必须清除暂留数据。

### ApplicationAlarmDetailData

```ts
interface ApplicationAlarmDetailData {
  applicationId: string;
  alarm: {
    id: string;
    content: string; // MonitorAlert.content；前端不得重拼或 fallback 到 alert_name
    severity: Severity | null;
    alertType: 'alert' | 'no_data';
    isNoData: boolean;
    occurredAt: string | null; // MonitorAlert.start_event_time；UI「首次告警时间」
    status: 'new';
    durationSeconds: number; // end_event_time or now − start；UI「持续时间」仅格式化
    resource: {
      id: string; // Host.inst_uuid
      name: string; // Host.inst_name；UI 文案为「关联主机」
    };
    dimensions: Array<{
      key: string;
      label: string;
      displayValue: string;
    }>; // MonitorAlert.dimensions 的安全展示；空数组时 UI 不展示
    metric: {
      id: string | null; // Metric 定义 id（query_condition.metric_id），不是 metric_instance_id
      name: string | null; // Metric.display_name / formula result_name；禁止 alert_name / policy.name
      value: string | null; // MonitorAlert.value
      unit: string | null; // policy chart unit
    };
    monitorContext: {
      objectName: string;
      instanceName: string;
    };
    policy: {
      id: string;
      name: string; // MonitorPolicy.name，不是 alert_name
    };
    notification: NotificationSummary;
  };
  navigation: {
    previousAlarmId: string | null;
    nextAlarmId: string | null;
    order: 'start_event_time_desc_id_desc';
  };
}

type NotificationExecutionState =
  | 'not_configured'
  | 'pending'
  | 'partially_delivered'
  | 'delivered'
  | 'failed'
  | 'unknown';

interface NotificationSummary {
  configured: boolean;
  state: NotificationExecutionState;
}
```

Notification rules：

- 以 `MonitorAlert.notice_logs` 的实际投递记录为首要事实。
- `MonitorPolicy.notice` 只表示是否配置通知，不能伪装成 delivered。
- 第一版只展示“是否配置通知 + 实际执行状态”摘要，不返回通知用户列表、渠道列表、recipient identity、内部 channel ID/config 或 endpoint。
- 多条 `notice_logs` 的归一规则：尚无终态且存在待执行意图为 `pending`；全部成功为 `delivered`；成功与失败并存为 `partially_delivered`；有执行记录且全部失败为 `failed`；未配置为 `not_configured`；现有记录不足以稳定判断时为 `unknown`。
- `configured=false` 时 `state` 必须为 `not_configured`；`configured=true` 时不得返回 `not_configured`。
- `alert_center_notified` 与 Alert Center outbox bookkeeping 不进入 UI DTO，也不用于计算 `NotificationSummary.state`。
- 数据不足时返回 `unknown`，不得引入 Central Alert enrichment。

### Alarm navigation

Navigation collection 是当前 Application、当前 actor、当前 filter-independent active alarm scope：

```text
ORDER BY start_event_time DESC NULLS LAST, id DESC
```

如果目标数据库的 NULL 排序行为不同，ORM 必须显式表达 NULLS LAST。Cursor/adjacent lookup 同时绑定 `applicationId`、actor/share scope 和排序键。Refresh 后 alert 不再属于 active scope、Application 变化或权限丢失时 fail closed，绝不跳到其他 Application。前端数组位置不是长期 identity。

### ApplicationMetricSeriesResult

```ts
type MetricSeriesState =
  | 'available'
  | 'no_snapshot'
  | 'failure'
  | 'permission_denied';

interface MetricThreshold {
  level: 'critical' | 'error' | 'warning' | 'info';
  value: number;
  operator?: string | null;
  label: string; // Monitor severity label，例如「严重」；UI 优先 i18n(level)
}

interface ApplicationMetricSeriesResult {
  applicationId: string;
  alarmId: string;
  state: MetricSeriesState;
  series: Array<{
    name: string | null; // Metric.display_name / formula result_name；禁止 policy.name / alert_name
    unit: string | null;
    points: Array<{ timestamp: string; value: number | null }>;
  }> | null;
  thresholds: MetricThreshold[]; // 来自 MonitorPolicy.threshold；保持策略原序，可多条
  alarmMarker: { timestamp: string; label: string } | null; // start_event_time；竖线 ≠ 阈值水平线
  errorCode?: 'metric_unavailable' | 'metric_source_failure';
}
```

- 只有 alarm detail 打开后按需请求；Wall/Detail summary payload 不含 trend。
- `available` 要求 `series` 非 null，可包含业务上合法的空 points，但不能用空 points 表达其他状态。
- `no_snapshot`：`series=null`，UI 显示“暂无指标快照”。
- `failure`：`series=null`，局部错误与重试，不影响其他 alarm detail。
- `permission_denied`：fail closed，清除当前 metric visual；不得继续显示长期缓存。
- 数据来自 `MonitorAlertMetricSnapshot`，后端完成 snapshot conversion、单位转换和 alarm marker 归一化，Widget 不消费 S3 raw snapshot schema。
- `series[].name` 与 Detail `metric.name` / list `metricName` 使用同一展示名语义；解析失败必须为 `null`，**禁止** fallback 到 `MonitorPolicy.name`、`alert_name`、`content` 或 `metric_instance_id`。
- `thresholds` 复用 `MonitorPolicy.threshold`（level/value/method），不重新发明阈值计算；UI 画水平参考线，与 `alarmMarker` 竖线正交。
- Trend UI 必须用 `points[].timestamp` 作为 X、真实 value（含 threshold）作为 Y 域；不得用点序号冒充时间轴。
- Legend 仅在 `series[].name != null` 时展示；禁止用策略名拼出虚假 legend。

### Error contract

Scene operations 使用统一业务错误 code：

```ts
type Application3DErrorCode =
  | 'invalid_request'
  | 'permission_denied'
  | 'not_found'
  | 'scope_changed'
  | 'source_failure'
  | 'capacity_exceeded';
```

Capacity error：

```ts
interface CapacityExceededError {
  code: 'capacity_exceeded';
  actualCount: number;
  supportedCount: number;
}
```

禁止 silent truncate。`supportedCount` 在真实 benchmark 前不得凭经验写死产品 hard capacity。

第一版容量策略：

- Wall 成员来自权限可见全集（可再经 `system_status` 过滤），无编辑期勾选分流。
- benchmark 完成前 `supportedCount` 保持 `null`；服务端仅保留足够高的 **safety batch/query budget**，超出返回 `capacity_exceeded`，文案/合同区分安全上限与已校准产品上限。
- 不把 NST 的 100/200 抄成 application3D 产品承诺。
- Phase 7 benchmark 后再写入双方共用的 hard capacity（如需要）。

## Filters

第一版唯一业务 filter：父应用系统运行状态。

```ts
interface ApplicationFilterDefinition {
  id: string;
  label: string;
  type: 'single' | 'multiple';
  options: Array<{ value: string; label: string }>;
}
```

第一版 definition：

```ts
{
  id: 'system_status',
  label: /* i18n: 应用系统运行状态 */,
  type: 'multiple',
  options: /* System.status enum，按当前 sharer/actor 可见口径由服务端给出 */
}
```

### Filter projection（与健康解耦）

```text
Visible Applications
  └─ optional filter system_status
       └─ exact model_asst_id = system_contains_application
            └─ peer model_id = system
                 └─ System.status ∈ selected values
```

Hard invariants：

- 只认 `system_contains_application`；不得用其它 System↔Application 边或 BFS。
- System 关联 **只决定 Wall 成员资格**；Host/Monitor/Alert 健康仍只走 `application_run_host`。
- `appliedFilters.system_status` 未选或空数组 = 不启用该 filter，返回权限可见全集。
- 多选为 OR：父 System.`status` ∈ 选中集即可。
- 过滤生效时，以下 Application **排除**：无父 System、父 System 对 actor 不可见、父 System.`status` 为空。不提供「未关联系统」option。
- Definition/options 由服务端基于当前 actor/share scope 与 System 模型 enum 返回，客户端不能自造 option。
- Widget runtime 选中值是 **ephemeral**；第一版不写入 `valueConfig` / Screen 持久化默认值；重新进入页面重置为未选=全集。
- **不接入** Screen unified filter；筛选条变更不得改变 Application 集合。
- Wall request 只接受 definition 中允许的 filter IDs/value；未知、越权或篡改值返回 `invalid_request`，不忽略后扩大 scope。
- Share operation 允许请求携带合法 `system_status`；frozen config 声明该 filter 能力存在，options 按 sharer current authorization 重算；不冻结访客的选择。
- Filter change 表示新 Wall generation：fetch → reconcile/layout → camera fit。

## Widget Configuration

第一版无 application3D 领域专用配置。搭建者只使用 Screen Widget 通用项（标题、appearance 等）。

- 默认 `appearance.frame = 'bare'`（与 `room3D` 一致，便于编辑态拖拽层）。
- 刷新跟随 Screen 画布 `refresh_interval`；不新增组件级刷新秒数配置。
- 不配置 Application 列表、健康阈值或持久化 filter 默认值。

## Share Capability

普通 DataSource Share proxy 不足以承载 self-fetch Scene。新增 scene-specific Share capability，至少允许：

```text
wall
application_detail
alarm_detail
metric
```

本变更必须为 `application3D` 做齐上述四类 operation，且 Normal/Share 共用同一 `Application3DQueryService` 与 DTO。本变更 **不** 重构 `networkStatusTopology` 现有「直连 scene API + overlay DataSource」混合 Share。

每次 operation 必须验证：

```text
share session valid
AND visitor binding valid
AND link active/not expired/not revoked
AND shared object is Screen
AND frozen Screen config declares application3D
AND requested operation allowed by application3D capability
AND filters are declared/allowed
AND sharer still has current Screen permission
AND same Application3DQueryService permission/scope checks pass
```

Share 页面禁止直接调用普通 CMDB、Monitor、Alert API。链路固定为：

```text
visitor
→ share session
→ active shared Screen
→ frozen config declares application3D
→ reconstruct sharer current authorization
→ force share current_team/space
→ scene-specific Share capability
→ same Application3DQueryService
→ same DTO
```

Share 完整支持 Wall、filters、refresh、selection、focus、Application Detail、previous/next 和 metric trend。

### Revocation and stale policy

| Event | Required behavior |
| --- | --- |
| share revoked / session expired | 立即 fail closed，清除 Wall/Detail/Alarm/Metric domain cache，进入 Share permission error |
| sharer loses Screen | 同上 |
| sharer loses Application | 下一次 operation/refresh 后移除 Application；若当前 selected，关闭 Detail、取消 focus 并回 Wall |
| sharer loses Host/Monitor/Policy | 不保留旧 alarm/detail；Application 变 unknown 或从新完整 scope 重新计算 |
| selected Alarm loses permission / closes | 清除 alarm/metric，返回 Application Detail；不得导航到越权 alarm |
| ordinary transient network failure | 可短暂保留同 actor/scope 上次成功 Wall health，标 `stale=true`；Detail/Alarm 显示局部失败 |

权限/撤权错误与普通网络失败必须由错误 code 明确区分。权限撤销禁止 stale retention；浏览器缓存不得在撤权后长期显示 Detail 或 Alarm。

## Frontend Architecture

```text
Application3DWidget
├─ runtime/data orchestration
│  ├─ request generation / abort
│  ├─ wall/detail/alarm/metric state
│  ├─ refresh/filter/retry
│  └─ Normal/Share transport adapter
├─ Three.js scene controller
│  ├─ renderer/scene/camera/lights
│  ├─ card meshes/materials/labels
│  ├─ layout/camera fit/raycast
│  └─ intro/focus/return transitions
└─ DOM UI
   ├─ filters/status/error/actions
   └─ Application Detail/alarm/metric
```

- Three controller 不调用业务 API，不理解 Monitor/CMDB DTO 之外的 schema。
- Runtime 不直接操作具体 Mesh；通过 controller interface reconcile/update/focus/restore/dispose。
- DOM Detail 不渲染进 WebGL texture。
- 复用 `room3D` 已证明的通用 WebGL lifecycle 原则，但不复制 room/rack domain implementation。
- Three.js 是核心产品能力，不允许以 DOM/CSS 伪 3D 替代。

## Scene State Machine

主状态：

```text
initializing
wall
focusing
focused
detailLoading
detail
returning
hardError
```

`loading/error/stale/permission/capacity` 是正交 runtime/data state，不无限扩充 Scene state。

### Transitions

```text
mount → initializing
initial wall success → wall + intro
initial empty → wall(empty)
initial hard failure → hardError

wall + select(A) → focusing(A) → focused(A)
focused(A) + openDetail → returning(A) → wall + Detail overlay
detail overlay + closeDetail → wall
focused(A) + back → returning(A) → wall
focused(A) + blank scene click → returning(A) → wall
```

Rules：

- 点击「应用详情」时 Focus Card 回到 Application Wall，然后展示 Detail overlay。这是正式设计，不是回退到 Focus。
- Focus 下点击场景空白区域返回 Application Wall。这是正式设计。
- select/focus transition 纯本地，点击后立即开始，不等待 Detail 请求。
- 再次点击已 selected card 不创建重复 transition。
- focusing 中选择另一 Application：取消旧 tween，以最新 selection 启动新 transition。
- Detail response 必须带 request generation；selection 已变时丢弃 stale response。
- selected Application 在 refresh 后消失：取消 detail/alarm/metric 请求，关闭 overlay，恢复/重排 Wall；不得保留幽灵 selection。
- Alarm navigation response 返回时必须再次验证 applicationId/alarmId/generation。
- unmount 后任何 response/tween/RAF 不得更新状态。
- Filter change 创建新 Wall generation，清除 selection/detail，并 camera fit；播放短 reconcile transition，不重播首次完整 intro。
- health silent refresh 只更新 health/material/badge，不重建 renderer、不改变 card position、不重播 intro。

## Three.js Wall and Interaction Contract

### Visual contract

- 深色科技视觉，但遵循 BK-Lite 克制、可靠、高密度可读的产品原则。
- WebGL perspective camera、depth、lighting、emissive/glow。
- 3D Application cards 显示 name、health visual、alarm badge。
- Wall 视觉 tone 为 `normal | critical | error | warning | info | unknown`：
  - `normal`：无活跃告警；badge 不显示 `0`。
  - `critical`：`alarming` 且 highestSeverity=critical；badge 显示 count（1–99 实际值，≥100 为 `99+`）。
  - `error`：`alarming` 且 highestSeverity=error；badge 显示 count（同上）。
  - `warning`：`alarming` 且 highestSeverity=warning；badge 显示 count（同上）。
  - `info`：`alarming` 且 highestSeverity=info 的 defensive 信息态；badge 显示 count；文案不得为「状态未知」。
  - `unknown`：仅 `unavailable`（无法完整计算）；badge 固定为 `--`。
- `alarming` 但 `highestSeverity=null`（非空且无法映射的 level）：文案为「警告」，使用 warning 视觉；**不得**默认画成 critical/「严重告警」，也不得画成「状态未知」。空 `level` 在后端已按 warning 归一，卡片走正常 warning 路径。
- no_data Alert 按自身 `level` 着色（例如 no_data + critical → critical 视觉），不得显示「状态未知」。
- `info` 使用现有 semantic information token 的低强度视觉，不走红/黄危险级别，不新增 health enum。
- 状态不能只靠颜色；badge、文字/形态和 unknown 标识提供辅助区分。
- 首次有效 Wall 播放 camera intro；reduced-motion 环境缩短或关闭非必要过渡，但功能完整。
- focus：selected card 移动/旋转/突出，其他 cards 弱化，显示“应用详情”和“返回应用墙”。

### Continuous layout

当前 filter 结果始终是一面连续 Wall，不出现页码。Application count 变化时重新布局整面 Wall。

布局目标：

- 根据 count 与容器 aspect ratio 选择 row/column，使 card projected aspect 与可用视口接近。
- 首选近似 `columns = ceil(sqrt(count * viewportAspect / cardAspect))`，再在相邻 column 候选中以 projected card size、空位和 camera distance 评分；算法属于 controller 内部，可在 benchmark 后调整。
- card world size 固定在有限范围，间距随 density tier 调整；不能只通过 camera 无限拉远。
- camera fit 同时考虑 Wall bounds、focus reserve、safe area 和最小可读 projected pixels。
- 当完整 Wall fit 会低于最小 label readability 时，启用 label LOD、guided row/cluster navigation、filter 提示或有限 pan/zoom；禁止把文字缩到不可读。

### Performance strategy

- geometry/material reuse；相同卡片框体优先 instancing/batching。
- text/icon/badge 使用受控 texture atlas 或共享 CanvasTexture cache；Application identity 变化时增量 reconcile，释放 orphan texture。
- health silent refresh 只更新 per-instance attribute/material/badge region。
- raycasting 只针对可交互 card set，pointer move 节流；不每帧遍历无关 DOM。
- glow/particles 分 quality tier；大数据量优先降低 particles、postprocessing resolution 和非关键信号，不能删除业务 cards。
- label LOD 保留 selected/hover/alarming 的优先可读性；数量 badge 不因 LOD 丢失告警事实。
- DPR 使用有上界的 `min(devicePixelRatio, calibratedDprCap)`；cap 由 benchmark 校准。
- DOM 仅承载 controls/detail/accessibility mirror，不为每张 Wall card 创建常驻 DOM overlay。
- renderer 只有一个 RAF loop；不可为 card/tween 各建循环。

### Capacity

- 必测 20/50/100/200 Applications。
- 在目标 Screen 硬件和支持浏览器上记录 FPS、首次可交互、layout、texture upload、raycast、camera transition、GPU/JS memory。
- benchmark 前不声明 200/500/1000 为 hard capacity。
- 校准后若需要 hard capacity，服务端与 Widget 从同一 capability/config 值读取。
- 超限返回 `capacity_exceeded(actualCount,supportedCount)`，禁止 silent truncate。

## Scene Lifecycle

```text
mount
→ dynamic import Three/controller
→ create renderer/scene/camera/lights
→ register ResizeObserver/pointer/wheel/touch
→ fetch Wall
→ build/reconcile cards
→ intro
→ idle

silent health refresh
→ fetch summary
→ generation/scope check
→ update card attributes/material/badge only

filter
→ new generation/fetch
→ clear selection/detail
→ reconcile/layout
→ camera fit + short transition

select
→ local focus transition

detail
→ Detail fetch
→ Alarm fetch/navigation on demand
→ Metric fetch on demand

return
→ restore camera/cards/opacity

resize
→ renderer size + camera projection
→ preserve scene state
→ re-evaluate fit/readability without replaying intro

unmount
→ abort requests
→ cancel tweens/RAF
→ remove listeners/observer
→ dispose geometry/material/texture/render targets
→ renderer.dispose()
→ force context loss only if current Three lifecycle convention requires it
→ clear controller references
```

Repeated mount/unmount must not accumulate WebGL contexts、RAF、ResizeObserver、event listener 或 GPU resources。

## Screen Editor Interaction

对齐既有 `room3D` 产品体验，而不是引入显式 Scene interaction mode：

```text
edit mode: Canvas owns pointer for Widget selection/drag/resize；
           application3D 仅预览 Wall（可 silent refresh 健康色），禁用 select/focus/detail/相机操纵
view/share mode: application3D owns supported interaction（完整 Wall → Focus → Detail）
```

- 编辑态通过 `editMode`（及默认 bare 框拖拽层）禁止场景交互；不提供「进入场景交互」开关。
- Resize handle 始终由 Screen editor 拥有。
- view/share 下 Screen fit scaling 后使用实际 canvas bounding rect 与 DPR 计算 normalized pointer，禁止直接使用未缩放 layout coordinates。
- 搭建者若要验证 focus/detail，需退出编辑进入查看或 Share 预览。

## Loading, Empty, Error and Stale

| State | UI / runtime behavior |
| --- | --- |
| initial loading | Scene skeleton/loading，未将空数据解释为 empty |
| empty wall | 明确空状态，可保留背景 Scene，不创建 cards |
| wall hard failure | hard error + retry；不得显示 normal wall |
| silent refresh failure | 保留同 scope 上次成功 cards，health 标 stale；不改变位置/selection |
| Application unknown | 中性视觉 + reason 对应通用文案；不泄露隐藏资源 |
| detail loading | Focus Card 回到 Wall，然后展示 Detail overlay loading |
| detail failure | Wall 保持；Detail overlay 局部 retry |
| detail close | 关闭 overlay，停留在 Wall；不回到 Focus |
| zero active alarms | statistics 全零、合法空列表 |
| alarm detail failure | Detail 列表保留，alarm 局部 retry/返回 |
| metric no_snapshot | “暂无指标快照” |
| metric failure | metric 区域 retry，不影响其他详情 |
| permission lost | fail closed；清除受影响 detail/alarm/metric，不使用 stale retention |
| capacity exceeded | 明确实际数/支持数，不渲染截断 Wall |

任何 request failure、权限不完整或 mapping missing 都不得被解释为 normal。

## Implementation Phases

### Phase 1 — Domain + Backend Contract

- application3D query module/interface。
- visible Application batch + optional `system_status` via exact `system_contains_application`。
- exact `application_run_host` batch projection。
- Host `monitor_id` mapping。
- MonitorInstance/MonitorPolicy permission reuse。
- `status=new` MonitorAlert scope；`alert_type` 与 `level` 正交聚合。
- Wall/Detail/Alarm/Metric DTO presenters。
- IDOR、notification summary、query-count backend tests。

Exit gate：相同 scoped queryset 证明 Wall/Detail count 一致，所有 incomplete path 非 normal；System 过滤不污染健康投影。

### Phase 2 — Share Capability

- Normal scene operations。
- scene-specific Share operations/session validation。
- sharer current authorization reconstruction 和 forced team/space。
- revoke/expiry/permission loss/filter tampering tests。

Phase 2 先于前端 Wall，是为了让 Normal/Share transport contract 在 UI 实现前稳定，避免后期复制 Share 数据路径。

### Phase 3 — Scene Registry / Screen Surface

- `application3D` 与 `networkStatusTopology` type/metadata/selector/registry/runtime registration。
- 各自 surfaces 执行：application3D Screen-only；NST Dashboard+Screen。
- import/export、copy/duplicate、invalid old config、Report rejection tests。
- self-fetch registry 收敛，移除新增 type special-case 的需要。

### Phase 4 — 3D Wall

- Three lifecycle/controller。
- card wall、health visual、badge、layout、intro、camera fit。
- loading/empty/error/stale/unknown/capacity UI。
- resize、theme、reconcile、silent health refresh。

### Phase 5 — Selection

- raycast、focus/return transitions（view/share only）。
- local-first selection、double click/repeated click handling。
- Scene state machine；编辑态禁用场景交互（对齐 room3D）。

### Phase 6 — Application Detail

- DOM overlay、Application properties/statistics。
- alarm list/detail、stable cursor/previous/next。
- notification summary。
- metric snapshot states/marker/retry。
- close Detail preserves focus；Back restores Wall。

### Phase 7 — Performance

- geometry/material/texture reuse 与 batching/instancing。
- label LOD、quality tiers、DPR。
- 20/50/100/200 target-hardware benchmark。
- hard safety capacity 校准及 shared server/widget value（如需要）。

### Phase 8 — E2E Verification

- Normal Screen / Share Screen。
- edit/view/share、permissions/revoke、filters/refresh。
- aspect ratio/resize、focus/detail/back。
- repeated mount/unmount、WebGL resource/memory verification。

每个 phase 独立通过其 exit gate 后再进入下一 phase；不得用 Phase 4 的 mock domain data 作为 Phase 1 完成证据。

## Testing Contract

### Backend matrix

- 只返回 visible Applications。
- 只解析 exact `application_run_host`；relation direction 正确。
- wrong relation、wrong peer、BFS-reachable Host 不传播 health。
- Host permission；隐藏 Host 不泄露数量。
- internal mapping/permission/source reason 只用于 backend，Normal/Share wire 均折叠为 `unknown/unavailable`。
- Host without monitor_id → unknown，不是 normal。
- MonitorInstance permission；partial/all denied。
- MonitorPolicy permission；scope incomplete → unknown。
- active 仅 `status=new`；closed/recovered 不计。
- multi Host 去重与聚合。
- shared Host 影响多个显式关联 Applications；每 Application 内不重复计数。
- critical/error/warning 正式档 + info defensive compatibility 的 count/order。
- no_data 按自身 `level` 参与 `severityCounts`/`highestSeverity`；only no_data → alarming，不是 unknown。
- `sum(severityCounts) == activeAlarmCount`（在可识别 level 下）；`noDataAlarmCount` 是正交类型维。
- zero active alerts 明确返回 count=0/normal。
- Wall/Detail count 与 statistics consistency。
- Application cross-IDOR。
- MonitorAlert cross-Application/closed Alert IDOR。
- previous/next stable ordering、scope change、race。
- metric available/no_snapshot/failure/permission lost。
- notification summary 基于 notice_logs，不使用 alert_center_notified。
- Application properties 只来自 backend ordered allowlist，字段权限/敏感字段/display conversion 生效；不返回未列入字段。
- NotificationSummary 只含 configured/state，不返回 users/channels/recipient identity。
- query count / CMDB batch call assertion；禁止 N+1。
- capacity exceeded 不 truncate。
- Share expiry/revoke、visitor binding、Screen declaration、sharer permission loss。
- Share Application/Host/Monitor permission loss。
- filter unknown/tampering/Share expansion rejection。
- `system_status` multiple OR；未选=全集；过滤生效时排除孤儿/不可见父 System/空 status。
- System 过滤不改变 `application_run_host` 健康口径。
- 不消费 Screen unified filter。

### Frontend matrix

- Screen selector visible；Dashboard/Report/other selector absent。
- invalid import/copy/surface config rejected。
- initializing、empty、hard error、retry。
- silent refresh stale；permission error 不 stale-retain。
- unknown/mapping incomplete 不显示 normal。
- unknown/unavailable 不显示或记录 backend internal reason，Normal/Share 文案一致；only no_data 与 info 不得渲染「状态未知」。
- Detail 固定展示严重/错误/警告；`severityCounts.info>0` 才动态展示提示；左侧不单独展示无数据类型统计；告警列表可保留无数据标签。
- real WebGL Wall render；badge 99+；severity/unknown 非纯颜色表达。
- health refresh 不重建 renderer、不改变 card positions、不重播 intro。
- filter creates new Wall/reconcile/camera fit。
- focus、focus double/repeated click、focus network independence。
- Detail open/close；close preserves focused；Back restores Wall。
- zero alarms、list/detail、previous/next。
- selection/alarm request generation race。
- selected Application removed/permission lost。
- metric available/no snapshot/failure/permission denied。
- Notification UI 不读取 alert_center_notified。
- Normal/Share adapter DTO parity。
- resize/aspect ratio/Screen scaling pointer coordinates。
- 编辑态无场景交互；view/share 可 focus/detail。
- unmount disposal：abort/tween/RAF/listener/observer/geometry/material/texture/renderer。

### Browser / real WebGL verification

自动化单元测试不能替代以下真实浏览器验证：

| Surface/mode | Required scenarios |
| --- | --- |
| Normal Screen | edit、view、filter、refresh、focus/detail/back、permission loss |
| Share Screen | Wall、filters、focus/detail/navigation/metric、revoke、expiry、sharer permission loss |
| Aspect | wide、standard、narrow/tall Screen widgets |
| Dataset | 20、50、100、200 Applications |
| Lifecycle | repeated mount/unmount、route switch、resize、theme/Screen fit change |

每档记录：

- actual FPS（idle、camera transition、hover/raycast）。
- initial fetch settled 到首次可交互时间。
- projected card/label readability。
- layout/camera fit 与 guided navigation 行为。
- JS heap、GPU/renderer memory trend。
- WebGL context 数量/丢失。
- ResizeObserver、event listener、RAF 数量。
- geometry/material/texture/render target 数量和卸载后释放。

Benchmark target 是待验证要求，不是已验证事实。测试报告必须记录目标硬件、OS、浏览器版本、DPR、分辨率、数据规模和 quality tier。

## Acceptance Gates

1. `application3D` 只能在 Screen 添加，Normal/Share 完整工作，其他 surface 从 metadata 层拒绝；NST metadata 保持 Dashboard+Screen。
2. 所有 Application identity 使用 `inst_uuid`，不存在 name-based join。
3. 所有 health Hosts 严格来自 `application_run_host`；`system_status` 只影响 Wall 成员。
4. MonitorAlert 是唯一 authoritative alarm；Central Alert 不在 contract 或查询链。
5. Wall/Detail/Alarm navigation 使用同一 Application-scoped active MonitorAlert 集合。
6. `0` 只来自完整查询（含零 Host）；mapping/permission/source failure 均非 normal。
7. `no_data` 是 alert type，按 `MonitorAlert.level` 参与 severity；only no_data 为 alarming。`info` 仅为 defensive compatibility，不得固定产品化，也不得渲染为 unknown。
8. 前端 wire 不含 permission/mapping 等内部诊断原因，Normal/Share 只获得一致的 `unknown/unavailable`。
9. Application properties 只来自 backend ordered allowlist（六字段）和 CMDB display conversion，不默认返回全部非敏感字段。
10. NotificationSummary 只表达 configured/state，不暴露 users/channels，也不读取 `alert_center_notified`。
11. Share 每次 operation 重验 session、widget declaration、filters、sharer current permission 和 IDOR；四类 scene ops 齐全。
12. 前端无 CMDB×Monitor join 或 per-resource N+1。
13. Detail、notification、metric、previous/next 完整实现，不跳转 CMDB 代替。
14. 3D 是真实 Three.js/WebGL 核心能力，focus/return 是 Scene transition，不是仅 Modal；编辑态无场景交互。
15. 20/50/100/200 benchmark 完成后才允许声明 hard capacity；超限不 silent truncate。

## Evidence Anchors

- CMDB UUID canonical identity：`CONTEXT.md` 与 `docs/adr/0005-use-uuid-as-cmdb-instance-identity.md`。
- 现有 Application relation/topology读取：`server/apps/cmdb/services/application_resource_overview.py`。
- CMDB UUID→monitor_id permission-aware batch helper：`server/apps/cmdb/nats/nats.py::get_monitor_ids_by_inst_uuids`。
- MonitorInstance identity：`server/apps/monitor/models/monitor_object.py::MonitorInstance`。
- MonitorAlert/notification/snapshot model：`server/apps/monitor/models/monitor_policy.py`。
- Monitor permission seam：`server/apps/monitor/views/monitor_alert.py::AlertPermissionMixin` 与 `server/apps/monitor/nats/monitor.py`。
- Existing active batch query：`server/apps/monitor/nats/monitor.py::query_latest_active_alerts`。
- Existing detail/snapshot behavior：`server/apps/monitor/views/monitor_alert.py` 与 `web/src/app/monitor/(pages)/event/alert/alertDetail.tsx`。
- Scene selector/registry/runtime seams：`web/src/app/ops-analysis/constants/sceneWidgets.ts`、`types/sceneWidget.ts`、`components/widgetSelector.tsx`、`components/widgetDataRenderer.tsx`。

## Remaining Open Questions

NONE BLOCKING IMPLEMENTATION.

Grill-aligned product decisions（已写入正文，此处仅作索引）：

- Wall 成员：权限可见全集；第一版唯一 filter=`system_status`（ephemeral、multiple）。
- 容量：软 safety guard；benchmark 前 `supportedCount=null`。
- 编辑态：对齐 room3D，无场景交互。
- metadata：NST=`dashboard+screen`，application3D=`screen`；不重构 NST Share。
- 无领域配置、不接 unified filter；Detail properties 六字段 allowlist。

Implementation-time, non-product calibration only：

- 目标 Screen 硬件/browser benchmark 得出的 DPR、quality tier 和 hard capacity（如需要）。
- 当前 CMDB 图层是否已有满足 query-count gate 的 exact relation batch primitive（`application_run_host` 与 `system_contains_application`）；没有时在 backend seam 内选择有界批次实现。
- Three text atlas/instancing 的具体实现以 20/50/100/200 benchmark 结果选择，但不得改变 wire/domain contract。
- safety batch/query budget 的具体数值在实现时按服务端资源与 query-count 测试校准，不得伪装成已验证产品 hard capacity。
