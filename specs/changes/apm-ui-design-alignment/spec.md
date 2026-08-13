# APM UI 设计系统对齐与体验优化

Status: implemented

## Problem Statement

APM 已具备首页、服务、探索、事件和集成五条完整产品路径，也已开始复用
`FilterToolbar`、`SearchActionBar`、`MoreActionsDropdown` 等共享组件。但当前页面仍由多轮局部实现叠加而成，存在以下系统性问题：

- 页面壳、卡片、表格和详情区的层级表达不统一，局部仍有卡片嵌套、固定宽度和强制横向滚动。
- loading / empty / error / degraded / forbidden 已有状态区分，但恢复动作、按钮防重和骨架形状不完整。
- 表格分页、长文本、数字排版、操作列和行点击语义未形成统一契约。
- 图表与代码块仍有硬编码颜色，亮暗主题的视觉契约不完整。
- APM 文案主要硬编码中文，与 OpsPilot 已形成的 i18n、空状态和数据表格成熟度有明显差距。
- 键盘操作、窄屏降级和 200% 缩放仍有阻断性问题。

此前静态合规审查的严格基线约为 **48/100**；OpsPilot 同类企业页面成熟度参照约为 **65/100**。灰色模块底已单独整改，不再作为本方案的待办项。本方案以消除可证实的 DESIGN 违规为验收目标，而不是追求视觉翻新。

## Source of Truth and Reference Boundary

执行优先级固定如下，出现冲突时高优先级覆盖低优先级：

1. `web/DESIGN.md`：视觉语义、组件选择和主题边界的唯一验收标准。
2. `web/src/styles/globals.css` 与主题 contract：运行时亮暗主题 token 真相。
3. `web/COMPONENT_GOVERNANCE.md`：shared、primitive 与 app-local 的所有权边界。
4. Storybook：组件状态与变体契约。
5. OpsPilot：仅作为成熟交互、骨架屏、空状态、表格和 i18n 的实现参照。
6. `legacy-design-ui.md`：只保留与现行 `web/DESIGN.md` 不冲突的历史建议。

因此，本方案明确不复制 OpsPilot 或 legacy 规范中的大阴影、悬浮卡片、装饰渐变、纯 `div` 交互等模式。APM 保持 Ant Design 优先、边框分层、系统字体和语义 token。

## Design Direction

### Creative North Star

APM 的设计方向是 **APM Operations Desk（应用性能工作台）**：高密度但可扫描，状态明确但不过度着色，首要任务是从异常信号快速下钻到服务、端点、Trace 和告警处置。

不做监控大屏风、营销页风或独立品牌视觉。主色只表达操作、链接、选中和焦点；健康、警告、严重和未知必须同时使用图标或形状、文案和语义色。

### Surface Hierarchy

| 层级 | 用途 | 视觉契约 |
| --- | --- | --- |
| L0 应用画布 | APM 页面底 | 继承全局 `--color-background-body`，APM 子布局透明 |
| L1 主承载面 | 页面头、表格、主要卡片 | `--color-bg` + `1px --color-border` + `8px` 圆角 |
| L2 弱承载面 | 筛选区、分组头、代码说明、选中前背景 | `--color-fill-1/2`，不再额外套 Card |
| L3 临时浮层 | Modal、Drawer、Popover、Dropdown | Ant Design Portal 与平台阴影，不在页面内自造浮层 |
| Semantic | active / success / warning / error | 语义 token + 图标/形状 + 文案，不只依赖颜色 |

页面默认不使用阴影。业务实体卡可使用 `12px` 圆角，但不能同时叠加大阴影与边框；普通容器统一 `8px`。

### Typography and Density

| 角色 | 规格 | 使用场景 |
| --- | --- | --- |
| Page title | `16px / 600 / 1.5` | 页面标题、Modal/Drawer 标题 |
| Section title | `14px / 500-600 / 1.5` | 卡片标题、表头、分组头 |
| Body | `14px / 400 / 1.5` | 表格、正文、表单、按钮 |
| Label | `12px / 500 / 1.5` | 状态、时间戳、副说明 |
| Micro | `10px` | 仅极窄标签，不承载正文 |
| Code | `12-13px monospace` | 命令、配置和 Trace 标识 |

指标、时间、百分比、持续时长和计数统一使用 `tabular-nums`。页面间距只使用 4/8 节奏：页面内边距 `16px`（大屏可 `20px`），区块间距 `12/16px`，主承载面内边距 `16px`。

### Standard Page Frame

所有 APM 主页面遵循同一纵向结构：

```text
全局顶栏 / APM 一级导航
└─ 二级视图切换（存在同级页面时）
   └─ Route Header：标题 + 一句话说明 + 可选页面动作
      └─ Dependency Notice：正常时紧凑说明，降级时提升为 Alert
         └─ Filter / Search Surface
            └─ Summary（可选）
               └─ Primary Content Surface
                  └─ Pagination / next cursor
```

`ApmRouteShell` 继续保持 app-local，负责页面内边距、标题层级和主内容宽度，不新增 shared 页面壳。正常依赖说明保持次级信息；只有 degraded/error 才使用整行 Alert，避免每页都制造强提醒。

## Component and Interaction Contracts

### Reuse Decisions

| 场景 | 统一组件 | 决策 |
| --- | --- | --- |
| KPI 摘要 | `SummaryMetricCard` | 首页删除平行 `KpiCard`，Sparkline 通过 `footer` 组合 |
| 筛选器 | `FilterToolbar` | 所有多条件即时筛选统一使用，窄屏自然换行 |
| 搜索 + 操作 | `SearchActionBar` | 管理类列表和显式提交搜索统一使用 |
| 数据表格 | `CustomTable` | 复用长文本、loading 与表格高度能力；不再新建 `ApmTable` |
| 长文本 | `EllipsisWithTooltip` | 应用、服务、路由、组织、描述和资源标识统一使用 |
| 空状态 | `CompactEmptyState` / AntD `Empty` | 局部紧凑空态用前者；整页状态由 `CatalogState` 组合 |
| 更多操作 | `MoreActionsDropdown` | 表格和实体卡的次级操作统一收口 |
| 可选择卡片 | `SelectableCardGrid` | 接入方式和运行时选项使用真实选择控件 |

OpsPilot 的 `CustomTable`、形状匹配骨架屏、i18n 空状态和键盘卡片行为作为正向参照；其 `shadow-md/hover:shadow-lg` 等视觉样式不进入 APM。

### Catalog State

`CatalogState` 扩展为所有 APM 数据页的状态契约：

```ts
interface CatalogStateProps {
  kind: 'loading' | 'empty' | 'forbidden' | 'degraded' | 'error';
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  onRetry?: () => void;
  retryLoading?: boolean;
  compact?: boolean;
}
```

- loading：骨架形状与目标内容一致，列表、表格、KPI、图表分别提供对应骨架；不使用整页居中 Spin。
- empty：说明为什么为空，并提供“调整筛选”“添加接入”或“创建策略”等上下文动作。
- forbidden：说明权限范围和申请路径，不提供无效重试。
- degraded：保留可用元数据，明确不可用能力并提供重试。
- error：说明失败对象，提供带 pending 状态的重试按钮。

### Async and Feedback

- 所有 API 触发按钮绑定当前请求的 `loading` 或 `disabled`；同一目标的重复提交被阻止。
- 页面首次加载使用骨架；筛选刷新保留已有内容并显示局部更新状态，避免闪回全空态。
- mutation 成功使用简短 message；失败消息包含对象、原因和恢复动作。
- 删除、归档、停用和权限变更继续使用 Modal/Popconfirm，文案说明后果。
- 长表单 Modal 主体限高并内部滚动；超过一个视口的配置流程改用 Drawer。

### Tables and Long Content

- 默认 20 条，提供 10 / 20 / 50 / 100 和总数；服务端目录优先使用已有分页能力。
- Trace/Span 等 cursor API 使用明确的上一页/下一页或“继续加载”控件，不伪造总数。
- 操作列固定右侧，行内动作使用 `link small`；主标识使用真实 `Link`。
- 行本身需要下钻时，优先把主标识列做链接；确需整行可点击时必须同时支持 Enter/Space、可见焦点和正确 role。
- 不允许交互元素嵌套，不允许仅 `onClick` 的 `tr/g/div`。
- 核心列自适应容器；窄屏通过响应式隐藏次要列、换行和 tooltip 降级，不用固定 `scroll.x` 撑宽整页。

### Theme and Charts

- 删除组件内 hex、`white/black`、slate/gray 主题色和主题判断分支。
- P50/平均值使用 primary，P95 使用 warning，P99/错误使用 fail；健康使用 success，未知使用 text-4。
- 多序列除颜色外增加实线/虚线/点线或不同 marker，并提供图例和 tooltip。
- 拓扑图始终提供可访问的依赖列表/表格替代视图；移动端默认列表，桌面可切换图形视图。
- 代码块新增平台级语义 token（code background / text / border），必须在亮暗主题 contract 同时定义；APM 仅消费这些 token。
- 图表加载、空数据和查询失败分别显示骨架、说明性空态和可重试错误态。

### Accessibility, Responsive and i18n

- 所有图标按钮有 `aria-label`，装饰图标 `aria-hidden="true"`，状态不只靠颜色。
- 交互控件保留 AntD focus ring；自定义业务卡使用真实 `button`/`Link` 或完整键盘语义。
- 关键断点为 320、768、1024、1440；320px 不出现整页横向滚动，200% 缩放时 Modal footer 始终可见。
- 新增和迁移文案统一进入 APM locale；中文、英文、长服务名、路径和 emoji 均验证换行/省略/tooltip。
- 时间、数字和单位走本地化格式化；Trace ID、Span ID 和代码不翻译。

## Page Family Design

### Home

- 顶部只保留全局时间窗，不增加营销式欢迎 Hero。
- 6 个核心指标改用 `SummaryMetricCard`，桌面 6/3/2 列自适应，移动端单列或双列；趋势线作为 footer。
- 健康分布、SLO、实时告警和 TOP5 使用统一 section header：图标、14px 标题、时间范围、右侧下钻链接。
- loading 骨架与最终卡片数量和高度一致；首次无接入提供“前往添加接入”主动作；局部失败仅替换对应 section。

### Services

- 保留“应用 / 服务”双视角和 URL 可恢复筛选状态。
- 应用卡是 APM app-local 业务实体卡：整卡主动作与告警链接互为兄弟节点，不嵌套；状态、服务数、RED 摘要和趋势保持固定阅读顺序。
- 服务视角使用 `CustomTable`。核心列常驻：服务、健康、吞吐、错误率、P95；环境、SLO、最后活跃和组织按断点降级。
- 服务详情统一为“身份摘要 → RED 趋势 → 端点/Trace → SLO”信息顺序；标题回归 16px，数值统一 tabular。
- 已归档内容继续使用 Drawer，搜索和解档动作显示 pending；抽屉内长名称使用 tooltip。

### Explore

- Traces、Endpoints、Errors 统一为“查询条件 → 当前条件摘要 → 结果”的工作流，筛选条件同步 URL。
- Trace/Span 表格主标识为链接；查询按钮、刷新和分页均有 loading/disabled。
- Endpoint 列表采用响应式列和服务/路由长文本 tooltip；样本表作为下钻内容，不与主列表同时争夺页面宽度。
- Error 聚类保留分组语义，错误类型、影响服务、样本量和最近发生时间形成稳定扫描顺序。
- Trace 详情瀑布图在窄屏切换为按开始时间排序的 Span 列表；桌面瀑布允许局部横向缩放，但不得把整页撑宽。

### Services Topology

- 桌面默认图形视图，提供“图形 / 依赖列表”切换；移动端默认依赖列表。
- SVG 使用响应式 viewBox，不依赖 `min-width: 960px`；节点以真实按钮/链接或可聚焦图形语义实现。
- 健康状态使用节点形状/边样式、文本和语义色共同表达；图例可键盘读取。
- 空态提供调整环境或时间窗动作，加载/失败复用统一状态契约。

### Events

- Alerts 页面保留严重度与趋势摘要，但摘要不阻断表格扫描；主列表使用服务端分页或明确 cursor 控件。
- 告警主标识、服务和状态为固定阅读主线；整行不再是唯一入口。
- Policies 页面继续使用 `SearchActionBar`，操作列固定右侧；启停、删除和重试均有目标级 pending。
- 策略表单保留可见 label、紧邻验证和视口内 footer；复杂通知配置超过一屏时使用 Drawer。

### Integration

- 添加接入采用“选择应用 → 选择运行环境/语言 → 生成配置 → 验证上报”的渐进流程，不在同一屏并列所有说明。
- 可用接入项使用 `SelectableCardGrid`；规划中项目使用真实 disabled/`aria-disabled`，展示可用条件且不响应点击。
- 代码块使用平台 code token、复制按钮和复制成功/失败反馈；命令允许局部横向滚动。
- Applications 与 Instances 使用 `CustomTable`、标准分页和长文本 tooltip；应用描述 TextArea 使用 `showCount + maxLength`。
- 应用创建/编辑 Modal 限高；内容继续增长时升级为 Drawer，不嵌套 Card。

## Delivery Phases

| 阶段 | 范围 | 完成标志 |
| --- | --- | --- |
| P0 契约与基线 | Storybook 状态矩阵、审查清单、评分脚本/表 | 亮暗、窄屏、长文本、loading/empty/error 可复现 |
| P1 基础合规 | CatalogState、API 防重、交互语义、主题硬编码、Modal fit | 无 P1/P2 交互阻断；核心状态都有恢复路径 |
| P2 数据工作台 | CustomTable、分页、响应式列、图表/拓扑替代视图 | 核心页面 320px 无整页横滚，键盘可完成下钻 |
| P3 页面家族 | Home、Services、Explore、Events、Integration 按模板收敛 | 页面层级、标题、筛选、内容面和反馈一致 |
| P4 i18n 与发布验收 | 中英文、视觉回归、200% 缩放、主题与真实数据验收 | 严格 DESIGN 评分 ≥ 85，目标 88+ |

P1 必须先于视觉细节；P2/P3 可按页面家族并行，但共享组件契约先落地再迁移消费者。

## Target Scorecard

以下为静态合规目标，不把 OpsPilot 作为第二套验收标准：

| 维度 | 权重 | 原审查基线 | 目标 | 验收重点 |
| --- | ---: | ---: | ---: | --- |
| 页面壳与层级 | 12 | 6/10 | 9/10 | 页面模板一致、无卡片嵌套 |
| Token 与主题 | 12 | 5/10 | 9/10 | 无硬编码主题色、亮暗完整 |
| 表格与图表 | 16 | 4/10 | 9/10 | 分页、长文本、响应式、图表替代视图 |
| 状态与反馈 | 12 | 7/10 | 9/10 | 骨架、恢复动作、局部刷新 |
| 键盘与可访问性 | 15 | 4/10 | 9/10 | 真实语义、焦点、ARIA、非颜色表达 |
| 响应式 | 12 | 3/10 | 8/10 | 320px/200% 缩放无阻断 |
| 表单与弹窗 | 8 | 6/10 | 9/10 | label、验证、pending、viewport fit |
| 排版与长内容 | 8 | 6/10 | 9/10 | 16/14/12、tabular、tooltip |
| i18n | 5 | 2/10 | 8/10 | 生产文案进入 locale，中英文安全 |
| **加权总分** | **100** | **约 48/100** | **约 88/100** | **无 P1，P2 全部关闭或有批准例外** |

## Testing and Acceptance

- 组件：为 `ApmRouteShell`、`CatalogState`、应用卡、首页指标和拓扑替代视图补 Storybook；覆盖 default/loading/empty/error/degraded/disabled/long-text/narrow。
- 交互：Testing Library 覆盖键盘行下钻、disabled 接入项、API 防重、重试、Modal/Drawer 提交和分页。
- 视觉：真实页面检查 `/apm/home`、`/apm/services`、Trace 列表/详情、Alerts、Integration；亮色与暗色分别在 320/768/1440px 验证。
- 可访问性：Tab 顺序、Enter/Space、可见 focus、ARIA 名称、状态非颜色表达；正文对比度至少 4.5:1，图形元素至少 3:1。
- 内容：中文、英文、64+ 字符服务名、长 URL/路径、emoji、空值、超大数字和时区格式。
- 弹窗：短视口与 200% 缩放下 footer 可见；长内容内部滚动或切换 Drawer。
- 门禁：定向 Vitest/ESLint、`pnpm type-check`、组件所有权审计；Storybook 全量构建若仍受已知 Node 24 WasmHash 基线阻塞，保留原始日志并运行对应 family 的定向检查。

## Public Interface and Data Boundary

- 不新增后端模型或领域 API，不改变 APM 数据语义。
- 目录型接口使用已存在的 `page/page_size/count` 能力；cursor 查询保持 cursor，不为 UI 伪造 total。
- 前端公开变化限于 `CatalogStateProps` 扩展；`ApmRouteShell` 如需增加 `actions`/`notice` 插槽仍保持 app-local。
- 不创建新的 shared 组件；只有现有 shared primitive 出现稳定、跨 app 的契约缺口时才扩展其 variant，并同步 Storybook 和所有消费者验证。

## Out of Scope

- 重做 APM 产品信息架构、数据模型、查询语言或告警领域逻辑。
- 把 APM 做成独立深色监控大屏或营销式 SaaS 页面。
- 为视觉统一重写 Ant Design Button、Table、Modal、Drawer、Form、Select 或 Segmented。
- 在没有第二个真实 app 消费者前把 APM 业务组件晋升为 shared。
- 顺带整改 OpsPilot 自身与现行 DESIGN 冲突的历史样式。

## Completion Evidence

### Closed Findings

- 统一 `CatalogState` 的 loading / empty / forbidden / degraded / error 契约，补齐上下文动作、重试 pending、错误 live region 与形状匹配骨架。
- 首页 KPI 改用 `SummaryMetricCard`；添加接入移除嵌套 Card；应用卡修复 `button > Link` 非法交互嵌套。
- Applications、Instances、SLO、Endpoints、Alerts、Policies 迁移到标准分页表格，补齐长文本 tooltip、右侧操作列、tabular 数字和目标级 mutation 防重。
- 刷新、查询、重试、继续加载和生成配置等 API 触发动作绑定 loading/disabled；空态与错误态提供恢复路径。
- 删除 APM 运行时代码中的硬编码图表/代码块主题色，平台主题 contract 同时补齐亮暗 code token 与 primary foreground token。
- 拓扑改为响应式 SVG，并提供图形/依赖列表双视图；移动端默认列表；SVG 节点支持聚焦、Enter 与 Space 下钻。
- 移除主列表固定 `scroll.x` 与 960px 拓扑最小宽度；关键列按断点降级，Drawer/Modal 使用视口安全宽高。
- 未开放接入项改为真实 disabled 并说明开放状态；装饰图标补 `aria-hidden`；整行点击替换为显式操作。
- 字号收敛到 16 / 14 / 12 阶梯，时间、百分比、延迟和计数补齐 `tabular-nums`。

### Final Static Score

| 维度 | 实施后评分 | 说明 |
| --- | ---: | --- |
| 页面壳与层级 | 9/10 | 继承全局画布，主内容使用单层承载面 |
| Token 与主题 | 9/10 | 运行时无组件 hex/white/black/slate，亮暗 contract 完整 |
| 表格与图表 | 9/10 | 标准分页、长文本、响应式列与拓扑替代视图 |
| 状态与反馈 | 9/10 | 状态有解释、动作和 pending；首页使用形状匹配骨架 |
| 键盘与可访问性 | 8.5/10 | 阻断性交互已关闭；完整读屏回归仍需真实浏览器复核 |
| 响应式 | 8.5/10 | 固定撑宽已移除；320px 关键路径无整页横向溢出 |
| 表单与弹窗 | 9/10 | label、校验、计数、pending 与 viewport fit 已覆盖 |
| 排版与长内容 | 9/10 | 字号、数字和 tooltip 契约已收敛 |
| i18n | 3/10 | 新增文案保留 fallback；存量 APM 中文尚未全量迁移 locale |
| **加权总分** | **约 86/100** | 静态合规评分；未把未执行的视觉检查计为通过 |

### Automated Verification

- `pnpm exec vitest run src/app/apm --maxWorkers=1 --no-file-parallelism`：13 个测试文件、43 个用例通过。
- `pnpm run test:theme-module`：通过；亮暗主题 token 键集合与兼容变量完整。
- `pnpm run test:apm-responsive-shell`：通过；顶部主导航和 APM 二级导航具备窄屏局部滚动契约。
- `pnpm run test:apm-{home,event,explore,integration,instance,service}-workflow`：全部通过。
- `pnpm run test:apm-real-query-wiring`、`test:apm-notification-closure`、`test:apm-dynamic-route-permission`：全部通过。
- 变更文件定向 ESLint：通过。
- 全仓 `tsc --noEmit`：本次 APM、主题、Storybook 与共享组件无错误；命令整体仍被仓库基线的可选企业依赖缺失和其他模块既有错误阻断。

### Storybook and Retained Exceptions

- 新增 `APM/Design Contract`，覆盖页面壳、CatalogState 状态矩阵、应用卡长文本/降级状态和 320px 窄屏。
- Trace/Span cursor 结果和详情内有界样本表保留 `pagination={false}`，因为不存在可展示的 total，继续加载使用显式 cursor 按钮。
- Trace 瀑布图保留组件内部局部横向滚动；移动端默认 Span 列表，因此不会撑宽整页。
- 本机真实浏览器已复核亮暗主题下 `/apm/home`、`/apm/services`，以及 320px 下首页、服务、拓扑和添加接入关键路径；均无 APM 灰底或整页横向溢出。
- 存量 APM 文案全量 i18n，以及 768px、200% 缩放和完整读屏矩阵留作发布前 P4，不在本次结果中虚报完成。
