# 运营分析仪表盘滚动取数与请求队列

Status: implemented

## Problem Statement

运营分析仪表盘中的每个 Widget 会独立发起运行时数据查询。画布组件很多时，首次打开、统一筛选、命名空间切换或刷新会在短时间内触发大量请求；相同请求虽已有在途合并，但不同数据源或不同参数的请求仍会同时进入 Server，并进一步占用 NATS、Prometheus、REST 或数据库查询资源。

本变更需要让交互式仪表盘只为当前阅读区域附近的组件取数，并由单画布请求队列限制实际网络并发。用户滚动时，当前内容必须优先加载；排队期间发生的新查询条件必须覆盖旧任务；已有周期刷新、latest-wins、错误态和报告终态合同不得被破坏。

## Solution

仪表盘查看态、编辑态和分享页按视口激活 Widget：真实视口上下各扩展一个视口高度作为预取区，进入该区域的 Widget 才具备运行时取数资格。单个浏览器页面中的单个画布维护独立调度队列，最多同时执行 6 个实际 Widget 运行时网络请求，超出部分等待。

队列优先满足真实视口内的组件，再按距视口由近到远调度预取组件。离开激活区但尚未开始的任务从队列移除；已经发出的请求自然完成。等待任务按 Widget 合并并只保留最新查询条件，周期刷新不积压。

## User Stories

1. 作为大型仪表盘查看者，我希望打开画布时只加载当前阅读区域附近的数据，从而不会因离屏组件很多而产生请求洪峰。
2. 作为滚动浏览仪表盘的用户，我希望即将看到的组件提前开始加载，并且快速滚动后当前可见组件优先于已经离屏的等待任务。
3. 作为使用统一筛选或命名空间切换的用户，我希望排队组件最终只按最新条件查询，从而不会执行已经失效的中间状态。
4. 作为手动刷新画布的用户，我希望整张画布的数据被标记为失效，但离屏组件等进入预取区后才按最新刷新版本取数，从而刷新不会重新制造全盘并发洪峰。
5. 作为启用周期刷新的用户，我希望慢请求不会让周期任务越积越多，且用户主动查询和首次加载始终优先。
6. 作为分享页查看者，我希望分享仪表盘具有与工作台一致的滚动取数和并发保护。
7. 作为报告订阅用户，我希望 PDF 渲染仍完整查询全部 Widget，但实际请求受到并发保护，不会因为没有滚动而遗漏离屏组件。
8. 作为画布编辑者，我希望编辑态同样受到请求保护，同时拖拽和编辑过程中的 Widget 状态不会被过期响应覆盖。

## Scope

- 交互式滚动激活覆盖：仪表盘查看态、仪表盘编辑态、仪表盘分享页。
- 报告渲染页不使用视口激活，全部 Widget 都进入队列，但仍受并发上限约束。
- 队列限制组件运行时产生的实际网络请求，包括数据源主数据、对比基线、组件内切换参数的动态选项查询，以及 Dashboard 内 `networkStatusTopology` 场景 Widget 的运行时查询。后者当前走独立 scene-widget API，不得绕过并发上限。
- 画布详情、权限、数据源元信息、布局保存、组件配置保存等页面基础请求不进入该队列。
- 本期只延迟数据请求，不虚拟化、不卸载离屏 Widget DOM、ECharts 或表格实例。

## Implementation Decisions

### 队列边界与并发

- 队列属于当前浏览器页面中的当前仪表盘。不同页签、不同浏览器、不同用户和不同画布不共享队列，也不互相占用额度。
- 并发上限固定为代码级常量 `6`，不开放画布或用户配置。常量应位于请求调度模块，不散落到组件。
- `6` 限制的是实际 Widget 运行时网络请求，不是 Widget orchestration 数量。完全相同的物理请求只占一个槽位；参数不同的主查询和对比基线分别占槽位。当前 compare 是 main 成功后再顺序请求 baseline，本期不得为了排队改成并行。
- 等待队列不设置会丢弃任务的硬上限。交互页只有激活区内 Widget 可以排队，每个 Widget 最多保留一个最新等待意图；报告页必须允许全部 Widget 最终完成，不能静默丢弃。
- 任一实际请求成功、失败或超时后都立即释放槽位并继续调度。队列层不自动重试；后续重试只能来自手动操作、条件变化或现有周期刷新机制。
- 切换画布或销毁队列时，清除所有未开始任务。已在途请求不要求新增服务端取消语义，但其响应必须继续服从现有 generation / unmount 防写回合同。
- 调度实例必须按 Dashboard 挂载实例隔离并随其销毁，不能只以持久化 `dashboardId` 作为生命周期身份。相同 Dashboard 快速卸载再挂载时，新实例不得复用旧实例尚未开始的排队任务。

### 调度 seam

- Widget owner 与物理请求调度是两个不同职责：
  - Widget owner 判断当前是否需要取数，维护 latest intent / generation / activation；已激活 Widget 的主动 latest intent 立即启动 orchestration，不受旧 orchestration 是否 settle 限制；
  - 单画布 runtime scheduler 在真正调用 HTTP adapter 前完成物理请求去重、优先级排队、槽位获取和生命周期收敛。
- 不得只给整个 `fetchCompareData` 或整个 Widget 分配一个并发槽位。物理 scheduler 必须位于 main / baseline / dynamic options 拆分之后、HTTP 调用之前；否则无法证明实际网络并发始终不超过 6。
- scheduler 的小 interface 应表达 `physicalKey`、当前优先级、开始实际请求的函数以及画布生命周期；Widget 不感知槽位计数、等待数组或重复消费者管理。
- 物理去重必须发生在占用槽位之前，并由 scheduler 与排队状态共同管理：重复消费者复用同一 Promise、不新增槽位；后来进入真实视口的重复消费者应能提升尚未开始物理请求的优先级。
- `physicalKey` 不得只由 URL + params 构成，还必须包含明确的 freshness identity。现有合同要求新的手动、筛选或 namespace 请求不能并入旧 periodic/visibility 的在途 Promise；只有同一画布运行实例、同一 freshness identity、同一 endpoint identity 和同一归一化 params 才允许物理合并。实现前优先核对并复用现有 `requestVersionKey`（`reloadVersion` + 按 Widget 相关性纳入的 filter / namespace version）能否承担该 identity；只有 component-switch options、Widget 私有 runtime parameter 或 scene Widget 等无法由现有 key 完整表达的路径，才补充最小的等价 identity。不得预设新增一套全画布 counter。main 与 baseline 因 params 不同自然是不同 key。
- 现有 `getOrCreateInflightWidgetRequest` 的 get-or-create 语义由 physical scheduler 承接，但 Widget compare orchestration 不再在 scheduler 外层先做 module-global Promise 合并。否则第二个 consumer 无法 attach 到 physical entry，也无法提升 queued priority。main / baseline 各自在真正发请求前进入 physical scheduler；同一 compare orchestration 内仍保持 main 后 baseline 的顺序。
- 普通、分享和 Render 会话的数据源查询最终都经 `getSourceDataByApiId` 选择各自 HTTP adapter；应在该 adapter 调用前注入同一个 Dashboard runtime scheduler。数据源元信息调用不经过该 seam。
- component-switch 动态选项当前由独立 loader 直接调用 `getSourceDataByApiId`；只把这个 runtime query 注入 scheduler，loader 为解析 `sourceRef` 而调用的数据源列表仍属于元信息请求，不占槽位。
- `networkStatusTopology` 场景 Widget 当前直接调用 `/scene_widgets/network_status_topology/`，需显式接入相同 scheduler；不因此改写其它画布或全仓请求抽象。

### 视口激活

- 激活区是滚动容器的真实视口向上、向下各扩展一个当前视口高度。窗口或容器尺寸变化后重新计算。
- 当前普通、全屏和分享 Dashboard 的真实滚动容器是 Dashboard 包裹 `DashboardCanvas` 的 `h-full overflow-auto` 元素，不是 `window`，也不是 `ViewWorkspace` 的 `overflow-hidden` 外壳。该元素必须以 ref 显式提供给激活模块。
- GridStack 已为每个 Widget 建立稳定 shell（`data-node-kind="widget"` / `data-node-id`）和 host（`data-widget-host`），激活观察应复用这些真实 DOM，不新增占位布局或虚拟化层。
- 可使用以真实滚动容器为 root 的 `IntersectionObserver`，但上下预取距离必须按 `root.clientHeight` 计算为像素并在 root resize 后重建或更新；不得用 `rootMargin: 100%` 代替一个视口高度。等待任务出队时应读取最新位置或使用同步后的优先级，不能把首次观察时的距离永久固化。
- Widget 首次进入激活区后才提交运行时查询。加载成功后滚出再滚回，如果查询条件和刷新版本未变化，不重复请求；滚动本身不是数据失效条件。
- Widget 离开激活区时：
  - 撤销该 Widget 尚未 `physical-started` 的工作，包括未启动 intent、尚未发出后续物理步骤的 orchestration，以及仍在 physical queue 中的 consumer；共享 queued entry 只有在移除该 consumer 后已无其他有效 consumer 时才整体删除；
  - 已经 `physical-started` 的请求自然完成，不为本期新增 Abort 或后端取消协议；如果它仍是该 Widget 的 latest generation，返回后允许正常写回数据或错误；
  - 已加载的数据保留，不因离屏清空。
- 离屏本身不是 generation stale 条件。只有新的有效 intent、Widget unmount、切换/销毁 Canvas 等 owner 生命周期变化才使既有 generation 失效。
- 编辑态沿用同一激活区。拖拽导致 Widget 短暂离开激活区时，不取消已经开始的请求；布局稳定后按最新位置更新等待资格和优先级。
- 报告渲染上下文显式绕过视口资格判断，把全部 Widget 激活。不得依赖滚动、IntersectionObserver 回调或打印分页过程来触发报告取数。

### 排序与公平性

调度优先级从高到低为：

1. 用户主动查询：手动刷新、统一筛选、命名空间、运行参数等变更；
2. 首次可见加载；
3. 周期刷新。

同一原因层级内按位置排序：

1. 与真实视口相交的 Widget；
2. 预取区内按到真实视口的距离由近到远；
3. 距离相同时按画布从上到下、从左到右。

- 周期刷新到点时，如果同一 Widget 已有等待或在途任务，则跳过本轮，不在请求结束后补发，等待下一个正常 tick。
- 同一 Widget 的等待意图被更高优先级或更新版本的意图替换，而不是追加。位置变化只调整尚未开始任务的优先级。
- 已取得执行槽位的请求不被后来高优先级任务抢占或强制中断；高优先级任务在下一个槽位释放时先执行。

### 查询版本、刷新与状态

- 每个 Widget 数据 owner 维护 latest intent / generation / activation。Widget 已激活时，新的主动 intent 立即推进 latest generation、启动自己的 orchestration，并直接竞争 physical scheduler 槽位；不得等待旧 orchestration settle。旧 orchestration 可以在 stale 后继续自然 settle，但不得写回 UI，也不得因此阻止 B/C 主动请求进入 physical scheduler。
- 每次 orchestration 使用创建该 intent 时捕获的完整请求快照（签名、参数、刷新原因和 generation）。不能让已经启动或排队的 orchestration 在执行时混读不同 React render 的 config 与 params。
- started history 只表示某个 intent 已经启动 orchestration，不等于该版本已经 fulfilled。若 compare 等 orchestration 因离屏撤销了尚未 `physical-started` 的必要后续步骤，该 generation 仍属未满足；重新进入激活区时必须能够再次发起完整查询。实现需要分别记录 started 与 fulfilled/required identity，不能再用单一 `hasRequested` 同时表达三者。
- stale / superseded orchestration 在每个尚未开始的后续 physical step 前重新检查 validity。A 的 main 已经 physical-started 时可自然完成；若完成时 A 已 stale，不得再为 A 启动 baseline 等后续请求。
- 统一筛选、命名空间或运行参数连续变化时，旧等待意图被最新意图覆盖。离屏 Widget 不立即请求；进入激活区后直接使用最新条件。
- 手动刷新使全盘 Widget 的运行时数据版本失效：激活区内立即按优先级排队，离屏 Widget 只记录最新刷新版本，进入激活区后再查询。
- 周期刷新只调度当前激活区内的 Widget，并遵守既有静默刷新规则：已有成功数据时不显示 loading，失败时保留旧值；未激活的离屏 Widget 不因周期 tick 入队。
- 新请求仍需遵守现有 latest-wins / generation 合同。旧响应不得覆盖新条件下的数据、错误或 loading；组件卸载或切换画布后不得写回；仅滚出激活区但仍挂载、且未被新 intent 取代的 latest generation 可以正常写回。
- 排队不是新的错误状态。等待中的可见 Widget 沿用现有加载态，不展示动态队列名次；本期不新增画布级 Alert、排队进度条或 toast。
- 相同请求的物理合并在 scheduler 内、占槽之前发生。共享同一 Promise 的多个 Widget 均等待同一结果，但调度器只统计一次物理请求；消费者卸载只使自身 generation 失效，不取消其他有效消费者仍需要的请求。

### 与已有周期刷新合同的关系

- 本变更不修改 `refresh_interval`、effective/saved interval、页签可见性、静默 loading 或错误保留语义。
- owner 级周期 single-flight 继续生效：periodic / visibility 遇到该 owner 已有在途或尚未 physical-started 的周期工作时 skip，不积压、不补发。主动 manual / filter / namespace / runtime parameter intent 不受旧 orchestration 阻塞，Widget 已激活时立即启动 orchestration并进入 physical scheduler；并发只由 physical scheduler 的 6 个槽位控制。
- 禁止用画布级 `isRefreshing` 大锁替代队列。一个慢 Widget 只能占用一个或其实际子请求对应的槽位，不能阻止其他空闲槽位继续工作。
- 手动刷新和条件变更仍是主动请求并成为最新 generation，但离屏 Widget 只更新失效版本，不绕过视口激活立即发起网络请求。

## Observable Behaviour

| 场景 | 预期行为 |
|---|---|
| 首次打开 100 Widget 仪表盘 | 只激活视口及上下各一屏；实际运行时请求始终不超过 6 |
| 当前视口有 8 个不同请求 | 先执行其中 6 个；槽位释放后继续，预取区任务不得抢先 |
| 快速滚动到底部 | 顶部未执行任务移出队列；底部真实可见 Widget 优先；顶部在途请求自然完成 |
| 排队时连续修改筛选 | 每个 Widget 最终只执行最新有效条件，不依次执行所有中间条件 |
| 点击手动刷新 | 全盘版本失效；激活区立即刷新；离屏 Widget 滚近后按最新版本刷新 |
| 周期 tick 遇到等待或在途 | 跳过该 Widget 本轮，不积压补发 |
| 请求失败或超时 | 释放槽位并继续队列；组件走既有错误合同；队列不自动重试 |
| 滚出后滚回且条件未变 | 保留原数据，不重复请求 |
| 多 Widget 在同一 freshness identity 下签名完全相同 | 只产生一个实际请求并占一个槽位，结果由多个 Widget 共享；新主动版本不并入旧周期请求 |
| PDF 报告渲染 | 全部 Widget 入队，实际并发不超过 6，最终不得因离屏遗漏 |
| 画布切换或组件卸载 | 未执行任务清除；旧在途响应不得写入新画布或已卸载组件 |

## Report Contract

- Render Dashboard 已由 `renderMode` 禁用周期刷新，并通过 `renderResultsRef` 收集每个 Widget 的 `loading / ready / empty / failed`；只有全部 Widget 都有非 loading 终态，`buildDashboardRenderSignal` 才产生 `report-ready` 或 `report-failed`。
- Render 必须显式使用 `activationMode = all` 或等价输入。所有 Widget 挂载后立即形成 initial required generation；不得依赖 IntersectionObserver、自动滚动、打印展开或分页副作用激活。
- “已提交等待意图”与“已进入 physical queue”都不是终态。尚未开始或正在等待槽位的 initial generation 必须保持现有 loading / missing-result 语义，不能调用 renderer ready 把旧数据或空值上报为 `ready / empty`。
- 当前报告聚合在结果缺失时会继续等待，Widget 初始 loading 与 component-switch options pending 也会主动上报 loading，因此不要求给公开 `DashboardWidgetRenderStatus` 新增 `queued`。queued 可以作为内部状态，但不得暴露为用户错误态、toast 或队列进度。
- 报告只允许 latest required generation 的 settle 更新 Widget 终态；stale success、stale error 和被 supersede 的等待任务均不得推动报告聚合。
- Chromium 当前等待 render signal 的总预算为 120 秒。全量排队会增加大盘尾部耗时；本期不得用自动延长 timeout 掩盖容量问题，必须用代表性数据验证 100 Widget 在既有预算内的行为。超出时继续走现有 `report_ready_timeout`，并作为容量证据另行决策。

## Testing Decisions

测试优先覆盖调度模块和 Widget 请求接缝，不用定时器实现细节或源码正则证明行为。

### 调度模块单元测试

- 并发上限：100 个不同异步任务中，在途峰值始终为 6，最终全部 settle，成功、失败和超时路径均释放槽位。
- 优先级：真实视口任务优先于预取任务；主动请求优先于首次加载；首次加载优先于周期刷新；同级任务按距离和画布位置稳定排序。
- 离屏移除：尚未 `physical-started` 的 consumer 可撤销；已经 `physical-started` 的请求不被强制中断，仍为 latest generation 时允许正常写回；撤销后槽位、consumer 与队列计数正确。
- 主动 latest：A 已在途时接受 B/C，B/C 均不等待 A settle，立即启动 orchestration 并进入 physical scheduler；A/B 是否实际 HTTP started 只由槽位和 physical dedupe 决定，只有 C latest generation 可写回。
- 后续步骤 validity：A main 已 physical-started 后被 B supersede，A main 可自然 settle，但不得再启动尚未开始的 baseline；离屏撤销必要后续步骤后，该 generation 不得记为 fulfilled，滚回必须能重新发起完整查询。
- 生命周期：画布销毁后不启动残余任务，迟到的 settle 不造成负计数或继续调度已销毁队列。
- 物理请求计数：去重发生在占槽之前；同一 freshness identity 下相同 physical key 只占一个槽位，重复消费者可提升 queued priority；不同 freshness identity、不同参数和 compare 子请求按实际请求分别计数。测试优先以现有 `requestVersionKey` 验证身份隔离，不把新增 counter 当成实现断言。

### Widget 与页面接缝测试

- Widget 未进入激活区时不调用运行时数据源 API；进入上下各一屏的预取区后才提交。
- 加载完成后滚出再滚回，条件未变化时不重复取数；数据失效后滚回则按最新版本取数。
- 快速滚动使未开始的旧位置任务撤销，并让新真实可见 Widget 优先。
- 手动刷新只立即调度激活区，离屏 Widget 记录失效并在滚近后查询。
- 周期刷新只覆盖激活区，且保持现有无 loading、失败保留旧数据、同 owner 在途时 skip 的行为。
- 编辑态、分享页与工作台查看态使用相同激活语义；报告渲染显式全量激活。
- component-switch 动态 options 和 `networkStatusTopology` 场景 Widget 查询受相同物理并发上限约束；数据源元信息不受影响。
- 组件卸载、切换画布和最新 generation 防写回继续成立。
- 报告中 Widget 等待 intent 或 physical slot 时不得进入终态；全部 latest initial generation settle 后才能发出一次 render signal。

### 压力与回归验收

- 使用 100 个请求签名不同的 Widget 作为功能压力场景；不以 mock 的固定总耗时作为通过标准，而以并发峰值、激活范围、调度顺序、无遗漏、无重复和最终排空为准。
- 对真实浏览器做滚动 smoke：正常滚动时预取组件在进入视口前开始加载，快速滚动后当前可见组件不会长期被离屏等待任务阻塞。
- 报告渲染回归必须确认全部 Widget 达到 ready/empty/failed 终态后再生成 PDF；队列不得改变失败聚合和超时合同，并记录 120 秒预算下的代表性完成证据。
- 运行现有周期刷新、Widget 错误态、分享页和报告渲染相关测试，证明本变更未回退既有行为。

## Observability

- 调度模块应具备可测试的状态快照或开发诊断接口，至少能观察当前物理在途数、去重后的等待数和已销毁状态；不得把可变队列名次暴露给最终用户。
- 若仓库已有前端性能/遥测入口，可记录去标识化的请求等待时长、执行时长、在途峰值和队列峰值；本变更不为此引入新的第三方 SDK，也不记录数据源参数、响应内容或凭据。
- 并发从 6 调整到其他值必须以真实环境的首屏 Widget 数、等待时长分位数、请求耗时分位数和 Server/下游容量为依据，不凭单次主观体验调整。

## Out of Scope

- 大屏、拓扑图、网络拓扑和架构图的视口滚动激活。
- 服务端跨用户、跨画布的全局排队、限流或容量治理。
- Widget DOM、ECharts、表格或 GridStack 布局虚拟化。
- 用户可配置并发数、预取距离或队列长度。
- 展示实时队列名次、全盘加载进度或新增画布级排队告警。
- 为在途请求新增服务端取消协议或强制中断下游查询。
- 队列级自动重试、指数退避或补偿任务。
- 修改数据源查询结果、权限、统一筛选、命名空间或报告快照语义。
- 把所有 `useApiClient` / fetch 请求改写成全局通用 scheduler；本期只接入 Dashboard Widget 的已确认 runtime adapter。

## Further Notes

- 术语使用“激活区”“等待意图”“实际 Widget 运行时网络请求”和“并发槽位”。不要把前端等待队列描述成后端任务队列或 Celery 队列。
- “滚动加载”只表示运行时取数延迟，不表示 Widget DOM 虚拟化或分页加载画布布局。
- 默认并发 6 是当前缺少生产分位数数据时的保守起点：它高于现有网络拓扑运行时池的并发 4，同时避免一次性放大同步数据源查询。后续调整应保留本 spec 的所有行为合同。
- 本 spec 与 `ops-analysis-canvas-periodic-refresh` 共同生效；发生歧义时，周期刷新原因、loading、失败保留和 generation 语义以既有周期刷新 spec 为准，本 spec 只增加视口资格和跨 Widget 实际请求调度。

## Completion Evidence

- 2026-08-14：调度、StrictMode 生命周期、激活、compare 后续步骤、参数选项、普通 Widget 与 `networkStatusTopology` 针对性测试共 46 项通过。
- 2026-08-14：`tsc --noEmit -p tsconfig.build.json` 与本次影响文件 ESLint 通过，`git diff --check` 通过。
- 2026-08-14：Node 24.19.0 下生产构建运行 10 分钟仍停留在 Turbopack 编译心跳，无成功或失败终态后人工终止；该项标记为 NOT COMPLETED，不作为通过证据。
