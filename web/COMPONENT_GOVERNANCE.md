# Web 组件所有权治理

## 约束

`src/components` 只允许两类实现：

1. 被两个及以上真实 app 直接或传递消费的跨 app 组件。
2. 进入 `component-ownership.allowlist.json` 的通用 primitive，类别仅限 Layout、Form、Feedback、Data display、Interaction。

Storybook 是组件行为与变体的契约中心，但 Storybook 引用本身不构成 shared 证据。业务域组件应放在 `src/app/<app>/components`；控制台根壳组件放在 `src/app/(core)/components`。shared 组件禁止反向依赖 `@/app/*`。

视觉、token、Tailwind / 行内样式的产品规则以 `DESIGN.md` 为准；本节只规定治理改动时如何执行这些样式约束，避免“换了 shared 壳、留下整段行内布局债”。

Agent 日常入口：根 `CLAUDE.md` / `AGENTS.md`「Web UI 硬约束」；**勿要求每次通读** `DESIGN.md`。治理大迁移或归属争议时再读本文与 `DESIGN.md` 相关章节。

## 样式与布局约束（治理执行）

完整规则见 `DESIGN.md` → **Layout & Styling**。治理迁移与跨 app 收敛时额外遵守：

1. **ClassName First / Tailwind 优先（触及即改）**  
   接入 shared 或改布局时，同区块的 `style={{ display:'flex', gap, padding, width... }}` 须改为 Tailwind `className`。禁止只换组件、不改布局写法；也勿为普通布局新建 SCSS Module。

2. **Token，不硬编码色**  
   治理触及的颜色必须是 `var(--color-…)` 或已映射的语义 class；发现 `#ff4d4f`、`#8c8c8c`、`bg-white` / `text-black` 等主题硬编码时，随治理一并改掉，不要新增。

3. **行内样式白名单**  
   仅保留：AntD 组件契约（如 Modal `styles.body` 限高）、运行时动态值（进度/拖拽/图表坐标）、画布类瞬时尺寸。其余布局行内视为债；新代码不得扩大比例。

4. **不为样式分叉组件**  
   仅因间距、圆角、边框色不同而复制 app-local 平行实现 → 删除分叉，复用 shared variant 或补稳定 props；样式差异优先用 `className` / token，不新开目录。

5. **交付自检（非所有权脚本）**  
   `check:component-ownership` 只校验目录所有权，不替代样式审查。治理 PR / cycle 说明中应点明：触及区块是否已按 `DESIGN.md` 改为 className；若刻意保留行内，写明例外类别（动态值 / AntD 契约 / 未触及历史债）。

## 当前终态

完整机器可读清单见 `component-ownership.manifest.json`。

| 分类 | 数量 | 判定 |
| --- | ---: | --- |
| `shared-cross-app` | 69 | 至少两个真实 app 直接或传递消费 |
| `shared-primitive` | 43 | 当前消费者不足两个，但具有明确 primitive 理由和 contract story |
| `app-local` | 0 | 不允许留在 `src/components` |
| `story-only-review` | 0 | 不允许仅因 Storybook 引用留在 `src/components` |
| `invalid-reverse-dependency` | 0 | shared 禁止依赖 app |
| `unused` | 0 | 无消费者实现必须删除或明确归属 |

白名单共记录 65 个 primitive；其中 17 个当前也已获得跨 app 运行证据，因此 manifest 按优先级将其归为 `shared-cross-app`。所有白名单项均包含 `reason` 和存在的 `contractStory`。

本轮将 `src/components` 从 229 个一级目录收敛到 112 个：114 个业务目录下沉到 app，3 个平行重复实现删除。

## 跨应用对比与决策

### Job

- 候选：`job-*`、文件预览、主机选择、危险规则、脚本编辑、目标选择和 Playbook 弹窗。
- 对比：这些 API 均表达 Job 类型或流程，不存在第二个 app 运行消费者。Host Selection 和 Dangerous Rule 的 Storybook 版本边界更完整；Script Editor 和 Target Controls 的业务版本更接近真实运行态。
- 决策：全部归 `src/app/job/components`。Host Selection 与 Dangerous Rule 采用较完整契约并接回页面；Script Editor 与 Target Controls 保留业务实现，删除 Storybook 平行实现。
- Storybook：`job-family.stories.tsx` 直接引用 app-local 唯一实现。

### Integration / K8s

- 候选：完成态、K8s 三步流程、前置条件提示，以及 catalog、instance、配置和导入壳。
- 对比：`integration-access-complete`、`integration-k8s-configuration-shell`、`integration-step-callout` 已由 Monitor 和 Log 真实页面共同消费；其余契约仍只有 Storybook 证据。
- 决策：前述 3 个保留 shared；其余归 `src/app/monitor/components/integration-contract`，第二个 app 真正接入后才可晋升 shared。`integration-setting-row` 去除业务前缀并收敛为 `form-setting-row` primitive。
- Storybook：Integration/K8s family 分别引用 shared 或 Monitor owner 下的唯一实现。

### Alarm / Monitor / Log

- 候选：`event-*`、`monitor-*`、`log-*`、`k8s-*` 及 `declare-incident`。
- 对比：这些组件只绑定一个业务域的类型、运行时或工作流；跨 family stories 仅用于横向展示，不能证明跨 app 复用。
- 决策：分别归 `src/app/alarm/components`、`src/app/monitor/components`、`src/app/log/components`。通用图表、布局、状态和交互叶子按能力进入 primitive 白名单。
- Storybook：原 family stories 保留，导入改为对应 app-local 路径。

### OpsAnalysis / OpsPilot

- 候选：`ops-analysis-*` 和 `opspilot-*` 的 widgets、配置区、选择器、卡片与工具编辑器。
- 对比：虽然部分展示壳可注入数据，但当前运行语义和类型仍属于单一 app，没有第二个 app 消费证据。
- 决策：分别归 `src/app/ops-analysis/components` 和 `src/app/opspilot/components`；不以“未来可能复用”为由保留 shared。
- Storybook：OpsAnalysis/OpsPilot family 直接验证 app-local 唯一实现。

### CMDB / System Manager / Node Manager / MLOps

- 候选：`cmdb-*`、`custom-reporting-*`、`system-manager-*`、`node-manager-*`、`mlops-*`。
- 对比：组件名称、字段模型、接口和操作流程均绑定对应 app；Storybook 中的多场景展示不改变所有权。
- 决策：全部归各自 `src/app/<app>/components`。
- Storybook：保留业务 family 契约，导入切换到 app-local 唯一实现。

### 控制台根壳

- 候选：`top-menu`、`user-preferences` 和旧 `user-info`。
- 对比：它们服务根 layout，而不是多个业务 app。旧 `user-info` 与 `top-menu/user-info` 重复，且反向依赖 System Manager。
- 决策：`top-menu`、`user-preferences` 归 `src/app/(core)/components`；删除旧 `src/components/user-info`，以 `top-menu/user-info` 为唯一实现。
- Storybook：Layout、TopMenu、User Profile stories 直接引用根壳实现。

## Primitive 白名单规则

- 白名单按能力登记，不按目录前缀登记。
- 带 `job-`、`cmdb-`、`monitor-`、`opspilot-` 等业务前缀的组件不得进入 primitive 白名单。
- 每条必须包含：
  - `component`：`src/components` 一级目录名。
  - `reason`：不依赖具体业务语义的理由。
  - `contractStory`：Storybook 唯一契约文件。
- 当 primitive 获得两个以上 app 消费后，manifest 自动优先归为 `shared-cross-app`，无需删除白名单说明。

## MoreActionsDropdown(2026-07)

抽象为 shared primitive,统一 `MoreOutlined + Dropdown + 可选 PermissionWrapper` 模式:

- API:`items: MoreActionsDropdownItem[]`(含 `key/label/onClick/permission/disabled/danger/icon/confirm`)+ `ariaLabel/placement/trigger/stopPropagation/buttonSize/buttonType/buttonClassName/overlayClassName/iconStyle`
- 已知消费者:alarm、cmdb、log、monitor、ops-analysis、opspilot、system-manager(共 7 app,11+ 处使用点)
- contract story:`src/stories/more-actions-dropdown.stories.tsx`
- 验证:`pnpm audit:component-ownership` 自动归类为 `shared-cross-app` 当消费者 ≥ 2

### 显式不迁移清单(触发器形态与 primitive 默认不一致)

| app | 文件 | 不迁移理由 |
|---|---|---|
| opspilot | `(pages)/memory/page.tsx` | 触发器使用 `text-white/80 hover:text-white hover:bg-black/10` 在深色背景图片上,与 primitive 默认 Button 颜色冲突;即使通过 buttonClassName 透传,AntD Button 默认尺寸/padding 仍会破坏布局 |
| log | `(pages)/search/fieldList.tsx` | 使用 `CustomPopover` 而非 `Dropdown`,不属于本 primitive 抽象范围 |
| alarm | `components/alarm-action` 与 `(pages)/alarms/components/alarmAction` | 主色「操作」按钮 + DownOutlined;作业规则为动态子菜单,不属于 MoreOutlined 行操作菜单 |

### MoreActionsDropdown 本轮增量(2026-08)

- 迁移: `ops-analysis/components/sidebar.tsx` 目录树 More 菜单从旧 `Menu` overlay 收敛到 `MoreActionsDropdown`(含内置对象禁用项与权限守卫)。
- primitive 增强: `stopPropagation` 同时拦截 `onMouseDown`,避免树节点选中抢占点击。
- 仍保留: log `fieldList` CustomPopover、system-manager menu dead code、opspilot memory 深色触发器。

### 审计分类修正(2026-08)

- 白名单 primitive 在消费者 < 2 时应归 `shared-primitive`,不得因单 app 消费被误判为 `app-local`。
- `shared-primitive-ghost` 仅用于白名单且既无 app 消费、也无活跃 Storybook JSX 渲染的条目。
- Storybook: `notifications.stories.tsx` 补显式 `render`,避免 CSF3 `component` 元数据被当成无契约渲染。
- 门禁: `pnpm check:component-ownership` 必须在修正后通过。

### OperateDrawer / CompactEmptyState 分叉收敛(2026-08)

- 删除 `log/components/operate-drawer` 与 `patch-manager/components/operate-drawer`,统一到 `@/components/operate-drawer`。
- shared OperateDrawer 恢复 `bodyStyle` 透传(映射到 `styles.body`),与 SCSS 默认 `padding: 16px` 并存;调用方可覆盖为 `padding: 0`。
- 删除 `ops-analysis/components/compactEmptyState.tsx` 平行实现,全部改用 `@/components/compact-empty-state`。
- Storybook: 既有 `content-draw.stories.tsx` / `feedback-family.stories.tsx` 覆盖契约;本轮无新 story 文件。

### MoreActions / 工具栏 / 状态徽章增量(2026-08 Cycle 3)

- 删除死文件 `src/app/(core)/components/top-menu/notifications.tsx`(与 shared `notifications` 平行且未被引用)。
- MoreActions 迁移: APM `services/page.tsx`、`services/[serviceId]/page.tsx`; system-manager `UserSyncSourceList.tsx`、`application/manage/menu/page.tsx`(原 dropdown 承载第 4 项删除,并非死代码)。
- 显式不迁: AlarmAction(`alarm-action` / `alarms/components/alarmAction`)——触发器是主色「操作」按钮 + DownOutlined,且含作业规则动态子菜单,不属于 MoreOutlined primitive。
- SearchActionBar: APM `policies/page.tsx` 接入,为 toolbar 族增加真实 app 消费。
- ExecutionStatusBadge: Job `job-record/page.tsx` 列表/详情/目标状态首批接入(零消费者 primitive → 有真实消费)。

### FilterToolbar 激活(2026-08 Cycle 4)

- APM `integration/instances/page.tsx` 与 Patch `risk-execution/page.tsx` 接入 `filter-toolbar`,结束该 primitive 零真实消费状态。
- OpsPilot: 8 个 skill `*ToolEditor` 去掉重复 `statusColorMap`,统一复用 app-local `ToolConnectionStatusTag`(不晋升 shared)。
- 仍保留 log `fieldList` CustomPopover 为例外。

### 工具栏扩面 + SecretValueDisplay(2026-08 Cycle 5)

- FilterToolbar 继续接入 APM 旧路径 `events/page.tsx`、`errors/page.tsx`、`endpoints/page.tsx`；Patch `baseline/page.tsx`、`risk-pending/page.tsx`。
- SearchActionBar: Patch `settings/page.tsx` 接入。
- Alarm `teamSecretsManager.tsx` 接入 `secret-value-display`,替换手写掩码 + CopyOutlined。
- PageStatus: `not-found.tsx` 与 `no-permission/page.tsx` 收敛到 shared,结束零真实消费。

### Master 合并后路径重挂 + 工具栏扩面(2026-08 Cycle 6)

- 同步 `upstream/master`(`b80524101`)：APM 菜单 IA 调整，旧 `apm/events|errors|endpoints|policies` 变为 redirect。
- 冲突处理：redirect stub 保留 upstream；工具栏迁移改挂到新路径：
  - FilterToolbar → `apm/explore/endpoints`、`apm/explore/errors`、`apm/events/alerts`
  - SearchActionBar → `apm/events/policies`
- FilterToolbar 继续接入：`apm/explore/traces`、`apm/services/page`、`apm/services/topology`、`apm/integration/applications`。
- SecretValueDisplay：Alarm `integration/detail/page.tsx` 两处 secret 行收敛(仍属 alarm 单 app；CURL/Python 示例区保留本地 Copy)。
- 显式不迁：Patch `risk-execution` 状态 Tag——API 驱动 `status_color` + 域状态(`pending_reboot`/`partial_success` 等)，与 `ExecutionStatusBadge` 语义不匹配。
- 门禁：`node scripts/component-ownership-audit.mjs --check` 通过(112 records)。

### 合并最新 master 后跨 app 补强(2026-08 Cycle 7)

- 同步 `origin/master` + `upstream/master` 到治理分支。
- ExecutionStatusBadge：MLOps `TrainTaskHistory` 接入(RUNNING/FINISHED/FAILED/KILLED + i18n label)，获得第二真实 app。
- SecretValueDisplay：system-manager API Key 创建成功弹窗明文展示 + 复制收敛(`masked={false}`)，获得第二真实 app。
- SearchActionBar + FilterToolbar：OpsPilot `tool/page.tsx` 技能包搜索/导入工具栏。
- CompactEmptyState：Patch `baseline-compliance-detail` 三处空态。
- 门禁：`node scripts/component-ownership-audit.mjs --check` 通过(112 records；68 cross-app / 44 primitive)。

### 全量再扫 + 分叉收敛(2026-08 Cycle 8)

- 同步最新 `upstream/master`。
- 删除 CMDB `app/cmdb/components/tag-capsule-group` 平行实现，assetSearch/baseInfo/common 统一 `@/components/tag-capsule-group`。
- ChartEmptyState：Log `stackedBarChart` / `barChart` 空态收敛(chart-empty-state 增加 log 消费)。
- CompactEmptyState：Job playbook-library 参数/文件/README 空态。
- SearchActionBar：Node Manager 云区域变量页；CMDB 自定义上报任务表工具栏。
- 显式保留：AlarmAction 双实现(列表 batch dropdown vs 行内操作，见 `alarm-batch-action-toolbar-test.ts`)；relatedAlertsPanel 双路径(props/数据模型不同)；log `fieldList` CustomPopover。
- 门禁：check 通过(112 records；68 cross-app / 44 primitive)。

### Loop 续跑(2026-08 Cycle 9)

- 再同步 `upstream/master`(告警日志安全相关提交)。
- VersionBadge：MLOps `DatasetReleaseList` 版本列接入，获得第二真实 app(`job,mlops`)。
- SearchActionBar：system-manager 用户同步记录抽屉；IM 通知渠道页搜索/操作区。
- 门禁：check 通过(112 records；69 cross-app / 43 primitive)。

### Loop 续跑(2026-08 Cycle 10)

- 再同步 `upstream/master`(凭据结果兼容、补丁周期评估通知、日志正则预览边界等)。
- CompactEmptyState：Monitor 采集页/自动配置空态；OpsPilot 技能包选择弹窗空态。
- FilterToolbar：Patch `library` 候选补丁抽屉筛选条。
- 门禁：check 通过(112 records；69 cross-app / 43 primitive)。

### 文档：样式规则入库(2026-08)

- `DESIGN.md` 新增 **Layout & Styling**：className/Tailwind 优先、token 着色、行内样式白名单、触及即改。
- 本节新增 **样式与布局约束**：治理迁移时同步执行，所有权脚本不替代样式自检。
- 根 `DESIGN.md` 导航补链组件治理与布局写法。
- Agent 短清单落在根 `CLAUDE.md` / `AGENTS.md`「Web UI 硬约束」；不另建 `.cursor/rules`，避免默认通读整篇 DESIGN。

### Loop 续跑(2026-08 Cycle 11)

- 合并本地已缓存的 `upstream/master`(webchat 流式批处理相关；本机 fetch 经 gh-proxy 暂不可用，以已有 remote-tracking 为准)。
- SearchActionBar：CMDB `assetManage/management` 模型管理工具栏；Monitor `savedQueryDrawer`。
- VersionBadge：Job playbook-library 列表/详情抽屉 + job-record 详情版本展示；触及区硬编码绿改为 `var(--color-success)`。
- CompactEmptyState：OpsPilot provider `modelManagement` / `grid` / `vendorCardGrid`、`SkillPackageDetailDrawer`、wiki `MaterialTab`。
- 门禁：check 通过(112 records；69 cross-app / 43 primitive)。

### Loop 续跑(2026-08 Cycle 12)

- master 已与本地 remote-tracking 对齐(fetch 仍受 gh-proxy 限制)。
- SearchActionBar：CMDB 模型属性页、专业采集任务页、订阅规则抽屉(行内 width→className)。
- FilterToolbar：Patch baseline compliance 详情筛选条。
- CompactEmptyState：OpsPilot skill/tool 页与 skill 工具编辑器族、operateModal/toolSelector；CMDB ViewsWorkspaceShell；Node collectorDetail 空态 + 搜索宽度 className。
- 门禁：check 通过(112 records)。

### Loop 续跑(2026-08 Cycle 13)

- 合并 `upstream/master`(运营分析连接测试与 3D 机房展示)。
- SearchActionBar：system-manager 集成实例创建弹窗；OpsPilot skill settings 技能包选择；CMDB nodeMgmtSyncDetail。
- CompactEmptyState：CMDB batchReviewDrawer / assetOverview；Log 集成列表；Ops-analysis networkLibrary(保留 data-testid 包装)；nodeMgmtSyncDetail。
- 门禁：check 通过(112 records)。

### Loop 续跑(2026-08 Cycle 14)

- master 已对齐；CompactEmptyState：Alarm 集成列表、actionTimeline、incident collaboration；CMDB assetData 空态。
- 门禁：check 通过(112 records)。

### Loop 续跑(2026-08 Cycle 15)

- ChartEmptyState：MLOps charts（bar/line/horizontalBar/simpleLine）。
- CompactEmptyState：MLOps FormPreview；system-manager 用户同步列表/进度抽屉；CMDB 模型管理页与 unknown view。
- 门禁：check 通过(112 records)。

### Loop 续跑(2026-08 Cycle 16)

- CompactEmptyState：Monitor search/updateConfig/event template、mysql dashboard、Job home/job-record 空态、OpsPilot ExecutionPreview/WikiPageReadingPane、Node cloudregion 未部署提示。
- ChartEmptyState：Monitor ring/horizontal-bar panels（shared + monitor-dashboard-widgets 副本）。
- 门禁：check 通过(112 records)。

### Loop 续跑(2026-08 Cycle 17)

- fetch 经 gh-proxy 不可用；合并本地 `upstream/master` / `origin/master` 均为 Already up to date（相对 upstream ahead 7 / behind 0）。
- ChartEmptyState：Monitor `stackedBarChart`、`echarts-line-chart`；Alarm `stackedBarChart`（触及区布局行内 → className）。
- CompactEmptyState：Alarm integration detail（3 处）/ `teamSecretsManager` / `relatedAlertsPanel`；Monitor integration list；Ops-analysis sidebar 目录空态。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 18)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 tracking：`origin/master`（会话恢复/图片预算等）成功；随后 `upstream/master` Already up to date（相对 remote-tracking ahead 8 / behind 0）。
- CompactEmptyState：Ops-analysis `networkEdgeDrawer`/`networkNodeDrawer`/`dataSource/previewPanel`；Patch `risk-execution` 详情空态（2 处）；CMDB `assetSearch` 结果区。
- ChartEmptyState：Monitor `metricPreview`；Log dashboard `comKpiCard`/`comLine`/`comBar`。
- 显式不迁：Patch `risk-execution` 状态 Tag（API `status_color` + 域状态，与 ExecutionStatusBadge 不符）；assetSearch landing 表内 emptyText（保留 AntD Table locale + 既有 class）。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 19)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 tracking：`upstream/master` / `origin/master` Already up to date（相对 remote-tracking ahead 8 / behind 0）。
- ChartEmptyState：Log dashboard 其余通用图 `comPie`/`comBarLine`/`comScatter`。
- CompactEmptyState：CMDB 关系 `list`/`networkTopo`；Ops-analysis `fieldSchemaTable`/`paramTable` 表空态。
- 显式不迁：assetSearch/landing 表内 emptyText（Cycle 18 同）；roomFloorPlan / applicationResourceOverview 域文案 Empty（下轮）；Log 域专用 widget（docker/http/…）与 heatmap/sankey/single/table。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 20)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 tracking：`upstream/master` / `origin/master` Already up to date（相对 remote-tracking ahead 8 / behind 0）。
- ChartEmptyState：Log `comHeatmap`/`comSankey`/`comSingle`；域 widget 首批 `docker/dockerBarChart`、`http/httpRequestTrend`。
- CompactEmptyState：CMDB `roomFloorPlan` 两处域文案空态。
- 显式不迁：assetSearch/landing 表内 emptyText（Cycle 18/19 同）；applicationResourceOverview 多处域 Empty；Log 其余域 widget（mysql/redis/kafka/…）与 `compactInsightTable`/`dockerErrorTable`。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 21)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 `upstream/master`（ahead 9 / behind 0）；`origin/master` Already up to date。
- ChartEmptyState：Log 域 widget `mysql/mysqlInstanceBar`、`redis/redisTrendLine`、`http/httpStatusTrend`、`http/httpLatencyBar`。
- CompactEmptyState：CMDB `rackElevation`、`ipamMatrix` 域文案空态。
- 显式不迁：assetSearch/landing 表内 emptyText；landing 分类区 Empty 与 applicationResourceOverview 多处域 Empty（下轮）；Log `kafka`/`nginx`、docker 其余、`compactInsightTable`/`dockerErrorTable`。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 22)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 `upstream/master` / `origin/master` Already up to date（相对 remote-tracking ahead 9 / behind 0；ahead 35 / behind 0）。
- ChartEmptyState：Log `kafka/kafkaTrend`、`nginx/nginxTrend`；docker 其余 `dockerDualLine`/`dockerAreaChart`/`dockerDonutChart`；`compactInsightTable`。
- 显式不迁：assetSearch/landing 表内 emptyText（Cycle 18+ 同）；landing 分类区 Empty（非表内，下轮）；applicationResourceOverview 多处域 Empty；`dockerErrorTable`。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 23)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 `upstream/master` / `origin/master` Already up to date（相对 remote-tracking ahead 9 / behind 0；ahead 35 / behind 0）。
- ChartEmptyState：Log `docker/dockerErrorTable`；域 widget `apache/apacheTrend`、`elasticsearch/elasticsearchTrend`、`mongodb/mongodbTrend`。
- CompactEmptyState：landing 分类区（非表内）；CMDB `applicationResourceOverview` 四处域空态。
- 显式不迁：assetSearch/landing 表内 / List emptyText（Cycle 18+ 同）；其余 Log 域 widget（redisInstanceBar/redisNodeCompareBar、rabbitmq/postgresql/fileIntegrity、syslog/windowsEvent）。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### Loop 续跑(2026-08 Cycle 24)

- fetch 经 gh-proxy / origin SSH 均失败；合并本地 `upstream/master` / `origin/master` Already up to date（相对 remote-tracking ahead 9 / behind 0；ahead 35 / behind 0）。
- ChartEmptyState：Log 域 widget 收尾 `redis/redisInstanceBar`、`redis/redisNodeCompareBar`、`rabbitmq/rabbitmqTrend`、`postgresql/postgresqlTrend`、`fileIntegrity/fileIntegrityTrend`、`syslog/syslogTrend`、`windowsEvent/windowsEventTrend`（7 处；dashboard widgets 内 `Empty.PRESENTED_IMAGE_SIMPLE` 已清零）。
- 显式不迁：assetSearch/landing 等表内 emptyText（Cycle 18+ 同）；tree-selector / fieldList / 指南页域 Empty；ops-analysis canvas/topology 大块空态（非 compact chart 形态）。
- **剩余评估**：Log ChartEmpty 高收益批次已稀薄；剩余多为表内 emptyText、域文案 Empty、画布/拓扑全页空态，边际收益下降。**建议放慢或暂停组件治理 loop**（间隔 ≥60m，或仅在有明确新共享证据时再跑）。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### 扫尾评估(2026-08 Cycle 25) — 可暂停

- fetch：`upstream/master` 经 gh-proxy 成功；`origin/master` SSH 失败，用本地 tracking。合并二者均为 Already up to date（相对 remote-tracking ahead 9 / behind 0；ahead 35 / behind 0）。
- CompactEmptyState 扫尾 4 处：Alarm `alarmDetail` 时间线、`ganttChart`；CMDB `selectIcon` 搜索无结果、`changeRecords` 时间线。
- 全仓再扫：MoreActions 仅余已标注保留（log `fieldList` CustomPopover 等）；FilterToolbar / SearchActionBar 无明显低成本缺口；剩余 Empty 多为表内 emptyText、指南页、树选择器、画布/拓扑/Select notFound、带 CTA children 的域空态。
- **结论**：高收益批次已尽；本轮为扫尾。**建议暂停定时 loop**，改为仅事件驱动（新 shared 消费证据 / 新平行分叉 / 明确治理票据）。
- 门禁：`pnpm check:component-ownership` 通过(112 records；Node v24.18.0)。

### 样式统一 loop(2026-08 Style-1)

- 目标：布局/间距统一 Tailwind `className`；颜色走 token；行内仅动态值/AntD 契约。
- `CLAUDE.md` / `DESIGN.md` Layout：明确 Tailwind 优先于新建 SCSS Module。
- 本轮：`dual-selector`、`patch library` 导入抽屉与页壳、`compact-empty-state` 行内布局/色改为 className。
- 下一轮优先：patch home/risk-*、job-record 等高密度 `style={{}}` 文件。

### 样式统一 loop(2026-08 Style-2)

- patch-manager 页壳批量收敛：`home` 47→4（仅动态色/高度）、`settings`→1（连通性动态色）、`risk-pending`/`target`/`baseline`→0、`risk-execution`→5（步骤状态色/时间线等动态边框）。
- 退出条件未达：全仓仍有较多 `style={{}}`（job-record、ipamMatrix、cmdb subscription 等）；loop 继续直至高密度布局行内明显收敛。

### 样式统一 loop(2026-08 Style-3)

- OpsPilot chat：`UserChoiceCard`/`ToolCallGroup` 布局行内 →0（条件态用 className；hover 替 mouseEnter 改色）。
- CMDB 双份 `triggerTypeConfig`：布局/错误色/标签行 → Tailwind；仅保留选中 Card `borderColor` 动态行内 + AntD `styles.body`。
- `ipamMatrix` 收敛至约 6（进度宽/动态色、grid minmax、cell 底色、图例色块）。
- 下一轮优先：`job-record`(≈70)、`changeRecords`(≈33)、`job/home`(≈30)、`networkNodeDrawer` 等高密度布局文件。

### 样式统一 loop(2026-08 Style-4)

- `job-record` 70→2（树深度 padding、语法高亮色）。
- `job/home` 30→14（图表/Tag/进度条动态色与尺寸）。
- `changeRecords` 33→5（场景色 map）。

### 样式统一 loop(2026-08 Style-5)

- `useConfigRenderer` 25→0；`file-dist` 18→0；`tableSettingsSection` 20→0；`node.tsx` 16→0。
- `roomFloorPlan` 17→12（画布坐标/机柜色/进度宽等动态值保留）。
- `networkNodeDrawer` 已为 0。跳过纯 Storybook `widgetShowcase.stories`。
- 退出条件接近：app 内 ≥15 的布局行内文件已基本清完；下一轮扫 ≥10 的剩余并评估是否可停 heartbeat。

### 样式统一 loop(2026-08 Style-6)

- `playbook-library` 14→1；`searchFilter` 14→1；`filterBar` 12→0；`job/target` 12→1；topology `toolbar` 13→1；`edgeConfPanel` 13→0。
- 可选：`networkNodeShape`→2；`networkEdgeDrawer`→2（动态边框/色）。
- 退出评估：≥15 布局行内已清空；剩余 ≥10 多为图表/画布/动态色（home、roomFloorPlan、stacked-bar、authSettings 等）。下一轮可再清一轮 ≥10 静态布局后标注接近可停。

### 样式统一 loop(2026-08 Style-7)

- `authSettings` 11→0；`operateModal` 11→0；`commonColumns` 10→0。
- `levelFormModal` 11→2；`userInformation` 10→1；`collectorDetail` 11→4（动态色保留）。
- `comKpiCard` 仅静态 flex；`comTopN` 全动态未改。SKIP：job home / roomFloorPlan / stacked-bar。
- 退出评估：静态布局 ≥10 基本清完；剩余多为图表/动态色。下一轮若无新高密度布局文件，可标注接近可停 heartbeat。

### 样式统一 loop(2026-08 Style-8) — 可停

- stacked-bar ×2：11→4（段宽/色动态）；paramTable/script-library→0；installGuidance/model*/environment/cron/quick-exec 等静态布局收敛。
- 仍 ≥8 且均为动态/缩放例外：job home、roomFloorPlan、chartLegend(scale)、comTopN/comKpiCard（SKIP）。
- **退出判定**：高密度静态布局行内已明显收敛；剩余为图表/画布/动态色例外。本 loop **停止再挂 style_unify heartbeat**（组件治理 loop 不受影响）。

### 已知 Storybook 构建阻塞

- Node 24 全量 `pnpm build-storybook` 在 webpack `WasmHash._updateWithBuffer` 崩溃(#0125)。MoreActionsDropdown 的 Storybook 契约暂时以单文件 + 定向 ESLint 保障。

## 门禁

```bash
pnpm audit:component-ownership
pnpm check:component-ownership
pnpm type-check
pnpm build-storybook
```

新增目录若为单 app、story-only、unused 或反向依赖 app，`check:component-ownership` 必须失败。业务组件晋升 shared 前必须先完成至少两个 app 的真实迁移，并同步更新 Storybook contract。

治理改动触及 UI 时，还须按 `DESIGN.md` Layout & Styling 与上文「样式与布局约束」自检：布局 className 化、颜色走 token、不为样式分叉组件。所有权脚本不替代该审查。
