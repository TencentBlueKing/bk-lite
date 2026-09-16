# 公共能力目录公开组件二期（告警 / 监控 / CMDB / 事故）

Status: implemented

## Completion Evidence

- 前端：`pnpm test:app-capabilities`（含本期 log/node/apm 声明、事故切换器与选项文案、viewModal 高度链与 embed 工具栏、room3D 槽与侧栏入口、资产变更主场时间线复用与嵌入 list|detail 统一顶栏、历史日志线索契约、策略只读与宿主铺满、节点状态语义）47 files / 157 tests PASS。
- 前端：`pnpm type-check` PASS。
- 后端：`DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest --nomigrations --create-db --no-cov` 覆盖 `test_monitor_object_snapshot_*`、lookup 两例 43 passed；`test_alert_query_clue`、冻结线索落库、snapshots 不读 live Policy、`test_room3d_embed`（含 403/IDOR user_info）12 passed。sqlite 全量 migrate 仍被仓库既有 `NewSessionEventRelation.event` 阻断（与本期无关）。
- 迁移：`server/apps/alerts/migrations/0034_event_node_id.py` 已在工作区，本地库已 apply。

## Problem Statement

运维在告警处置、监控对象排查、CMDB 资产与事故研判时，仍要跳转日志、节点管理、APM、CMDB 变更与运营分析机房视图才能看原始日志、资产变更、监控策略、节点状态、服务概览/调用链和 3D 机房。一期（`public-capability-widgets`，下文称 689）已打通目录化嵌入与告警详情、CMDB 资产详情两宿主，但未覆盖上述能力，也未把监控对象 viewModal、事故详情收成宿主；若再靠编译期引用他模块页面，或按 IP、名称现场反查补联动，会打穿模块边界与身份契约。

## Solution

沿用 689 公共机制：提供模块声明；宿主探测后，进入对应 Tab 再按需加载；只传稳定 ID；未购买、无权限、未声明或没有稳定 ID 时不显示入口；禁止按 IP、名称猜测关联；宿主不得直接引用其他业务模块页面或组件。

本期新增 7 个公开组件；扩展告警详情与 CMDB 资产详情；新增监控 viewModal 与事故详情两个宿主。公开嵌入只要求组件已声明（提供方未购时该键即未声明）+ 有稳定 ID，不额外收「已购运营分析」的门。`monitorId` 一律指监控实例 ID（`MonitorInstance.id`）。

**689 已交付的 6 个公开组件，以及告警详情、CMDB 资产详情两个既有宿主的既定行为，不在本需求重复实现**；本变更只新增能力与扩展宿主接缝。

## User Stories

1. As an 处置日志类告警的运维人员, I want 在告警详情用 `logAlertId` 同时查看发生时保存的查询线索和原始数据, so that 不依赖当前策略重跑查询。
2. As an 处置告警或事故、或查看监控对象的运维人员, I want 在有 `instUuid` 时打开「资产变更」, so that 与告警单据「变更记录」在名称和口径上可区分。
3. As an 查看已联动监控资产的运维人员, I want 在 CMDB 详情打开「监控策略」, so that 不必跳去监控中心。
4. As an 查看机房资产的运维人员, I want 在关联关系里打开「3D 机房」, so that 只在机房详情看到该能力且不含机柜。
5. As an 查看主机或快照已有 `nodeId` 的主机类告警的运维人员, I want 打开「节点状态」, so that 能看到节点在线、采集器与最近心跳。
6. As an 处置已带明确 APM `serviceId` 的告警的运维人员, I want 分别打开服务概览与调用链, so that 无明确 serviceId 时不出现入口。
7. As an 在监控对象列表点击实例打开抽屉的运维人员, I want 动态看到适用的公开 Tab 且不新建详情页, so that 本地三 Tab 与公开能力并存且不重复嵌入。
8. As an 未购买提供方模块的用户, I want 宿主不出现对应入口且原有能力仍可用（未购运营分析只影响 `ops-analysis.*` 件）, so that 售卖与权限降级不打断主路径。
9. As an 研判事故的运维人员, I want 在成员告警之后打开「资产变更」，多对象时由宿主切换且每次只传一个 `instUuid`, so that 不必下钻单条告警也能看资产变更历史。

## Implementation Decisions

### 公共机制（沿用并扩展 689）

- 延续系统层 `appCapabilities`：提供模块在各自 `capability` 中声明组件并登记目录；使用模块先按售卖 / 模块级访问探测，再按稳定组件键检查声明与可加载性。不另建运行时注册表，不把业务组件搬进 shared `src/components`。
- 入口层（藏入口）：组件未声明 / 不可加载（`useAppWidget().declared === false`）、缺稳定标识。
- **公开能力目录是加载接缝，不是售卖 SKU**：本期日志、节点管理、APM、CMDB 变更等挂到告警 / 监控 / CMDB / 事故宿主，**不要求已购运营分析**。售卖门只有一处——`useAppCapability` 按 `hasAppAccess(clientData, <提供方 app>)` 判授权，未购则该 app 名下所有键 `declared` 恒为 `false`；「未购运营分析 ⇒ `ops-analysis.*` 不出」由这条链兜住。宿主一律不得自行 `hasAppAccess(clientData, 'ops-analysis')`，也不得以「宿主 app ≠ 提供方 app」为由加门；同模块自用同样不加此门。
- 组件内（展示入口再提示）：资源无权、不存在、关联失效、查询失败；成功无数据 → 空态。实例级 ACL 不回头关掉 Tab / 入口。
- 使用模块只传稳定业务标识，禁止直接引用提供模块页面、内部组件路径或 NATS 接口；禁止宿主串他模块数据再拼装业务组件。
- 除告警原始日志外，嵌入展示**当前**数据，不作告警发生时快照；原始日志只读发生时保存的两类历史证据：查询线索与原始数据。

### 稳定声明键

| 能力 | 稳定键 | 入参 | 主要使用位置 |
|---|---|---|---|
| 告警原始日志 | `log.alertRawLog` | `{ logAlertId }` | 日志类告警详情 |
| 资产变更 | `cmdb.assetChange` | `{ instUuid }` | 告警详情、viewModal、事故详情 |
| 监控策略 | `monitor.monitorPolicy` | `{ monitorId }` | CMDB 资产详情（外宿主）；viewModal 本地策略 Tab 不经此键重嵌 |
| 3D 机房 | `ops-analysis.room3D` | `{ instUuid }` | CMDB 机房详情（不含机柜） |
| 节点状态 | `node.nodeStatus` | `{ nodeId }` | viewModal、CMDB 主机详情、快照已有 nodeId 的主机类告警详情 |
| 服务概览 | `apm.serviceOverview` | `{ serviceId }` | 告警上已有 serviceId 的告警详情 |
| 调用链 | `apm.callChain` | `{ serviceId }` | 同上（独立键、独立 Tab） |

- 目录扩加载器应用名：`log`、`node`（售卖 `clientData.name`，路由仍为 node-manager）、`apm`，以及既有 `cmdb` / `monitor` / `ops-analysis`。
- APM 必须两键两 Tab，探测与失败态各自独立；无 `serviceId` 时两个入口都不出。

### 快照与稳定 ID

- **对象级**（跟 `monitor_objects[]`）：扩展 `node_id`，与现网 `monitor_id` / `cmdb_id` 同路径——事件落库列、监控推送 payload、归并快照三处对齐；告警产生时从 `MonitorInstance.node_id` 冻结写入；打开详情禁止反查；历史缺字段当空、不回填。
- **告警级 `logAlertId`**：沿用现网推送 `labels.log_alert_id`（值为日志模块 `Alert.id`）；告警详情必要时只读透出该指针；组件仅用 `{ logAlertId }` 调日志模块**历史**快照 / 原始数据 API；禁止 VictoriaLogs / 按现行策略 live regenerate。
- **告警级 `serviceId`**：当且仅当 `resource_type === 'apm_service'` 时，告警 / 事件上的 `resource_id` 即 APM `ApmService` UUID 主键（现网 APM→告警中心推送已带该字段）；否则不出 APM 两 Tab。不建设 CMDB 应用系统与 APM 服务的绑定，不按服务名反查。
- 对象切换器：列出快照全部对象；「资产变更」只消费当前对象 `instUuid`；「节点状态」只消费当前对象 `nodeId`；切到缺标识对象时组件内提示且不发起查询。告警级能力（原始日志、APM 两 Tab）不纳入对象切换器。
- Tab / 入口显隐看告警整体或宿主级是否具备对应标识（与 689 一致：避免切换对象时 Tab 栏跳动）；当前对象缺标识时进入后明确提示。
- 告警「资产变更」入口门（与节点状态、689「资产信息」同构）：告警级任一快照对象有非空 `instUuid` / `cmdb_id` → 出 Tab；当前对象缺 ID → 进入 Tab 后明确提示且不发起查询。

### 组件口径

- **告警原始日志**：嵌入只读发生时保存的两类证据，不得只 JSON dump `raw_data` 而丢掉 API 已返回的有用历史元数据。
  1. **查询线索**：至少覆盖发生时可复盘的数据源 / 索引（或现网等价字段，如 `collect_type` / `log_groups`）、时间窗、过滤 / 检索条件、策略侧与本次命中相关的条件快照（以现网日志告警结构为准，如 `alert_condition` / 规则 / `period` 等发生时值）。告警产生写 `AlertSnapshot.snapshots[]` 时一并冻结；不要只存 policy id 打开时再读 live Policy。
  2. **原始数据**：现网已落的 `raw_data`（关键词样本行或聚合结果包等）。
  - 组件入参仍仅为 `{ logAlertId }`；用它调日志历史快照 / 原始数据 API（`/log/alert/snapshots/` 等）；禁止 VictoriaLogs / 现行策略重跑冒充现场。
  - 历史缺线索的老单：组件内明确提示线索不可用，仍可展示已有原始数据（若有）；不做历史回填任务。缺原始数据与无线索须可区分。
  - 可展示 `alert_info` 中已有且属于历史证据的字段（如 `source_id` / `level` / `start_event_time` / `content`），前提是不引入 live 策略。
  - 失败与空态在组件内；无 `logAlertId` 不出 Tab。
- **资产变更**：复用 CMDB 主场「变更记录」的只读核心呈现（时间线 + 点选一条看摘要 / 属性 diff / 关系 diff），不得把整页（筛选 chips、统计条、复杂搜索、导出、双栏 `100vh` 布局）塞进 Tab，也不得另造一套无关卡片列表。**嵌入布局**默认只展示时间线并占满宿主高度；点选一条进入详情态。详情态始终用同一条工具栏（单/多对象同一套）：最左「← 返回时间线」（箭头 + 文案，回时间线列表），多对象时对象 Select 紧挨返回右侧（不要居中），「在 CMDB 中打开」右对齐；单对象时左边只有返回。工具栏下方才是变更头（色点 / 时间 / 场景标签 / 操作者）与摘要 / diff。禁止：返回单独占第二行、返回塞进色点标题行、Select 放正中间、同屏两份「在 CMDB 中打开」。时间线列表态保持既有对象切换 + 打开入口。主场变更记录页的上一条 / 下一条 / 关闭不改。禁止嵌入里同时钉死时间线 + 详情双栏（上下或左右）。宿主 Tab 文案固定为「资产变更」，不得与告警单据「变更记录」混名。嵌入只传 `{ instUuid }`，组件内用详情接口自举 `model_id`，不读宿主 URL / CommonProvider。高度跟宿主容器，禁止 `vh` 撑破告警 / 事故 Tab。客户端可默认场景子集，不暴露重筛选 UI；全量拉取、无服务端分页（与主场相同）。
- **监控策略**：复用监控中心策略列表只读能力，入参严格 `{ monitorId }`。公开键 `monitor.monitorPolicy`（CMDB 等外宿主）Tab 内只读；名称 / 行操作不得链到策略「编辑」路由（禁止 `buildMonitorStrategyDetailUrl('edit', …)` 这类写入口）。若需外链，仅允许只读详情或不提供跳转。viewModal 本地「监控策略」Tab 不经此键重嵌，保持既有产品行为；若与公开嵌入共用同一表组件，用 `readOnly` 区分，默认嵌入只读。
- **3D 机房**：复用运营分析 `room3D` 领域查询与核心渲染，嵌入薄适配层处理尺寸与交互；入参 `{ instUuid }`。**不得**用 `ops-analysis.application3D` 顶替机房；机房只走 `ops-analysis.room3D`，且仅 `server_room`。查询与渲染须按当前机房实例收窄；**「短期全量机房墙再前端过滤」只作实现过渡，不算验收完成态**（与 689「3D应用」收窄同精神）。
- **节点状态**：展示节点在线、采集器与最近心跳，文案须与主场列表一致的人话语义，不得把状态码 `String(...)` 直接丢出。在线用 `active`（或同等语义）表达在线 / 离线；采集器复用或抽取与 `useTelegrafMap` 同等映射（0 / 2 / 3 → 正常 / 失败 / 停止）；最近心跳继续用现网 last-report 字段（通常为 `updated_at`），标签与主场一致。权限、取数、空态、失败与重试由组件自理。
- **服务概览 / 调用链**：各自声明、探测、懒加载与失败态；同传一个 `serviceId`。

### 告警详情宿主（扩展 689）

- 页与抽屉同一套规则。
- Tab 顺序固定（有条件才插入，缺则跳过）：概述 → 事件 → **告警原始日志** → 监控视图 → 关联拓扑 → 资产信息 → **资产变更** → **节点状态** → **服务概览** → **调用链** → 变更记录 → 处理动作。
- 变更记录、处理动作仍是告警中心单据 Tab；不含「实例日志」。
- 689 已有公共 Tab 的既定显隐与懒加载规则保持；本期只插入上表新能力并沿用统一对象切换器语义（对象级新能力挂入切换器）。

### 监控 viewModal 宿主（新建）

- 指监控对象列表点击实例后打开的现有抽屉；不修改 `/monitor/view/detail` 指标整页，不新建监控对象详情页。
- 本地固定 Tab：监控视图、告警列表、监控策略（不经公开能力重嵌）+ 右上角「查看仪表盘」跳转保持原样，不做成公开能力。宿主本地 tab key 不得与公开稳定键字符串混用（例如本地策略 Tab 不得写成 `monitor.monitorPolicy`）。
- 动态公开 Tab（有稳定 ID 且门通过才插入）：关联拓扑 → 基础信息（689 能力，需 `instUuid`）→ 资产变更 → 节点状态。
- 稳定 ID 来源：当前监控实例行 / 表单上的 `cmdb_id` → `instUuid`，`node_id` → `nodeId`；若打开路径未带齐字段，允许按 `instance_id`（即 monitorId）**只读**拉取该监控实例详情补 `cmdb_id` / `node_id`（仍是实例主键查询，禁止 IP / 名称猜关联）；缺则对应 Tab 不出现。

### CMDB 资产详情宿主（扩展 689）

- **监控策略**：侧栏入口；资产 `monitor_id` 非空 ∧ 组件已声明 → 传入该 `monitorId`。不要求已购运营分析。
- **节点状态**：侧栏入口；`model_id === 'host'` ∧ 资产实例 `node_id` 非空 ∧ 组件已声明 → 传入该 `nodeId`。不要求已购运营分析。直接读 CMDB 主机上的系统关联字段，禁止经 `monitor_id` 反查监控实例补 `nodeId`。
- **3D 机房**：挂关联关系 Segmented（与网络状态拓扑并列，不替换原网络拓扑 / 列表 / 二维应用拓扑等）；同时在侧栏提供快捷入口，与「机房视图」同逻辑——点击落到关联关系 `?tab=room3D`，选中时与「关联关系」父菜单互斥，直达 `/detail/room3D` 的旧链接按保参重定向落到该 tab（与网络状态拓扑同模式）。门同 Segmented：仅 `model_id === 'server_room'` ∧ 有 `instUuid` ∧ 组件已声明（未购 OA 时该键即未声明）；**`rack` 不出**。侧栏与 Segmented 都不得挂 `ops-analysis.application3D` 冒充机房。
- 689 已定的默认「拓扑」槽替换、监控视图 / 告警列表 / 网络状态拓扑 / 3D应用等既有入口行为不在本期重复改写。

### 事故详情宿主（新建薄宿主）

- 只加载「资产变更」。
- 稳定 ID 取自成员告警已有 `monitor_objects`：汇总非空 `cmdb_id`，按 uuid 去重。
- 0 个非空 `cmdb_id` → 不展示入口；1 个 → 直接加载该 `instUuid`；多个 → 必须提供宿主切换器，每次只传当前一个 `instUuid`；允许默认选中去重后的第一项；选择为空 / 过期时允许回落第一项。禁止：在 length > 1 时不提供切换器、却固定只查某一个；禁止一次传入多个 ID。
- Tab 插在**成员告警之后**（现网事故页未必有「变更记录」锚点，不以不存在的栏位定位）。过 `cmdb.assetChange` 声明即可，不要求已购运营分析；进入再按需加载。

### 建议实现序

目录扩键与按键探测 → 快照 `node_id` 契约 → 各提供方声明组件 → 告警宿主扩 Tab → viewModal 宿主 → CMDB 入口 → 事故薄宿主。

## Testing Decisions

好测试只锁对外行为：声明键是否可被探测、入口显隐是否只依赖模块级探测 + 稳定标识 / 模型闸门、组件是否只收到约定单值入参、宿主是否禁止静态依赖提供方内部模块、懒加载是否在首次激活前不发业务请求、失败与空态是否可区分。不锁具体 DOM 结构。

最高接缝优先（沿用 689 与 `appCapabilities` 既有风格）：

- **目录与探测**：七新键已声明 / 未声明 / 模块不可用；`log` / `node` / `apm` 加载器登记；按键失败不得误伤无关键。
- **售卖门只有一处**：锁「未购某模块 ⇒ 该 app 所有键 `declared === false`」（`useAppWidget` 测试）。在此之上，未购运营分析 + 已购监控 / CMDB / 日志 / 节点 / APM 的夹具下，告警、viewModal、CMDB、事故上的 `monitor.*` / `cmdb.*` / `log.*` / `node.*` / `apm.*` 入口**仍要出**（已声明 + 有稳定 ID 时）；`ops-analysis.*` 因未声明而不出，已购时不回归。宿主源码不得出现 `hasAppAccess`，不得存在「宿主 app ≠ 提供方 app 就收 OA 税」的路径。
- **隔离**：告警详情页 / 抽屉、CMDB 详情、viewModal、事故详情不得静态 import 提供方 `@/app/*` 业务实现；经 `useAppWidget`（或同等目录接缝）按需加载。
- **快照**：监控产生告警时 payload / Event / `monitor_objects` 含 `node_id`；历史缺字段不出节点状态入口；打开详情不反查补齐。日志告警新快照 `snapshots[]` 含冻结 `query_clue` + `raw_data`；历史 API 原样返回、不读 live Policy。
- **告警宿主**：Tab 序；`labels.log_alert_id` 可驱动原始日志；新快照含冻结查询线索；嵌入同时展示线索与原始数据且不走 VictoriaLogs / 现行策略重跑；改策略后仍显示发生时线索；缺线索 / 缺原始数据可区分；`apm_service` + `resource_id` 才出 APM 两 Tab；资产变更 / 节点状态告警级出 Tab、当前对象缺 ID 进 Tab 后不查；对象切换对二者生效；单据 Tab 不依赖该切换器。
- **viewModal**：动态 Tab 序与 ID 门；本地三 Tab 不经公开键重嵌且本地 tab key 不与公开稳定键字符串混用；不新建详情页、不改指标整页。抽屉 body 为 flex 列 + overflow hidden，公开 Tab 高度链铺满剩余内容区；`cmdb.assetChange` 能收到 `onHeaderAction` / `onEmbedToolbar`（不要用只收 string 的 props 把回调裁掉）。
- **CMDB**：监控策略 / 节点状态侧栏闸门；公开 `monitor.monitorPolicy` 路径不出现 edit URL 构建；3D 机房仅 `server_room` 进关联关系 Segmented **与侧栏快捷入口**（侧栏项落 `?tab=room3D` 且与关联关系父菜单互斥），且查询按 `instUuid` 收窄（不以全量墙过滤为完成态）；不得用 `application3D` 顶替；`rack` 与非机房不出。
- **节点状态**：嵌入用 `active` 表达在线 / 离线，采集器映射与 `useTelegrafMap` 同等，心跳用 `updated_at`；不得裸出状态码。
- **事故**：0 个 `cmdb_id` 不出入口；1 个直载；多个必须有切换器，默认可为去重后第一项，每次只传一个 `instUuid`。
- **资产变更**：宿主文案为「资产变更」，与告警「变更记录」可区分。嵌入走主场时间线 + diff 共享组件，**list | detail 两步**（默认整高时间线，点选进详情可返回）；详情态一条工具栏（← 返回时间线 | 多对象 Select 紧挨右侧 | 打开右对齐），变更头在工具栏下方；无导出 / 无 chips / 无 `100vh` / 无上下钉死双栏；主场筛选 / 导出 / 双栏 / 上一条下一条关闭不回归。

## Out of Scope

- 「实例日志」整行 Tab（本迭代不出现该入口）
- 对象仪表盘、对象作业记录等公开导航能力（现有抽屉「查看仪表盘」保持原样）
- 拓扑节点跳转（须另开需求）
- 运营分析画布外模块宿主（含活动告警、监控视图、基础信息、实例日志进画布）
- 远程连接
- 按 IP、名称补全跨模块关系（含用日志 instance_id / 主机名去对监控实例名）
- 回填历史告警缺失的 `node_id` / `logAlertId` / `serviceId` / 历史查询线索
- 重做 689 已交付的 6 个公开组件与告警 / CMDB 两宿主既定行为

## Further Notes

- 本变更承接 `specs/changes/public-capability-widgets/spec.md`（689）。
- **本变更正式修订 689 Spec 的目录键集合与告警详情 Tab 序**（目录由 6 键扩至 13 键；告警详情插入本期公共 Tab）。其它 689 行为不回滚；独立复核不得再按「冻死 6 键 / 旧 Tab 序」卡本期交付。
- `ops-analysis.room3D` 不得用 `ops-analysis.application3D` 顶替。
- 现网已具备、可直接消费的事实：APM 推送 `resource_id` = 服务 UUID 且 `resource_type = apm_service`；日志推送 `labels.log_alert_id`；CMDB 主机实例自带系统关联字段 `node_id`；监控实例模型与列表序列化已有 `node_id` / `cmdb_id`。监控 → 告警中心身份快照**尚缺** `node_id`，由本变更按与 `cmdb_id` 同路径补齐。
- 「可以加载」是模块声明与组件键可用性，不是「这台资产有没有变更记录 / 节点是否在线」。缺标识是绑定门；资源无权是组件内权限门；二者与售卖门分开。
- **本条口径已修订**：初版写成「跨模块公开嵌入一律须已购运营分析」，是把「目录」当成了售卖 SKU。运营分析要收的是它自己编排出来的跨域件（`ops-analysis.*`），不是「别人的组件被挂到另一页」这个动作；而 OA 件本来就靠「未购 OA ⇒ 该键未声明」挡住，宿主侧那道 `hasAppAccess('ops-analysis')` 是重复防线，已全部删除。现行判定就是 `declared && <稳定 ID>`；689 spec 同步修订。
