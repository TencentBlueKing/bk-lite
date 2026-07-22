# Add Cmdb K8S Resource Overview

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/add-cmdb-k8s-resource-overview/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

CMDB 已经采集并关联 K8S Cluster、Namespace、Workload、Pod、Node，但集群详情缺少符合 K8S 层级语义的专属资源视图，用户只能在通用实例列表和关联关系中手工定位资源。需要提供一个权限安全、支持大规模 Pod 按需展开的只读视图，让用户在集群上下文中完成资源盘点和 Pod 到 Node 的关系定位。

## What Changes

- 在 `k8s_cluster` 实例详情增加一级菜单「资源详情」，与「基础信息」「关联关系」「变更记录」并列；现有通用关联关系页面保持不变。
- 首屏展示 Cluster、Namespace、Workload、Node 和统一口径的资源统计，Pod 默认不加载。
- 基础拓扑对 Namespace、Workload、Node 采用明确的增量展示和稳定排序，不静默截断大集群资源。
- 支持同时展开多个 Workload；每个分支首次加载 50 个 Pod，可继续分页加载，并将 Pod 关联到首屏已有 Node。
- 增加 Namespace、五类业务 Workload、其他工作负载、Pod、Node 的资源导航与分页列表，并按资源类型展示有可靠采集来源的固定业务列。
- 资源列表严格只读，仅提供筛选、搜索、刷新、分页和进入现有 CMDB 实例详情，不提供创建、YAML、批量操作、导出或其他写操作入口。
- 展示最近上报、最近成功采集、最近错误等可观察事实，不由系统替用户推断集群健康或采集状态。
- 对 Cluster 入口和各子资源分别执行模型/实例权限过滤，确保指标、拓扑和列表不泄露无权资源。
- 区分未归属 Pod、未调度 Pod、Node 未匹配和目标 Node 无权限等关系事实，并提供局部失败重试。
- 明确不在本次引入 K8S 写操作、新资源模型、实时推送、跨集群聚合、健康评分或告警嵌入。
- v1 不注册或展示尚未交付的页签与禁用占位；后续能力在下一次迭代真正实现时再增加入口。

## Capabilities

### New Capabilities

- `cmdb-k8s-resource-overview`: 定义 K8S 集群资源概览、按需 Pod 拓扑、多资源列表、DIV 五列视觉结构、权限过滤和异常降级行为。

### Modified Capabilities

无。

## Impact

- 后端：CMDB Instance API、K8S 资源聚合/可见性服务、查询序列化器和相关测试。
- 前端：`k8s_cluster` 实例详情一级导航、独立资源详情容器、K8S 拓扑、资源导航、列表、局部加载状态及国际化。
- 数据：复用现有五个 K8S 模型、实例关联和采集事实，不新增模型或数据库迁移。
- 权限：复用现有 CMDB 模型/实例权限规则，但对每种子模型独立求值并统一应用于统计、拓扑和列表。

## Implementation Decisions

## Context

CMDB 当前已经通过 K8S 采集插件维护 `k8s_cluster`、`k8s_namespace`、`k8s_workload`、`k8s_pod`、`k8s_node` 五个模型及其关联，但实例详情只有通用关联关系页面。采集数据允许 Pod 直接关联 Namespace，也可能产生独立 ReplicaSet，因此资源视图不能假设所有对象都严格符合 `Cluster → Namespace → Workload → Pod → Node` 单一路径。

该变更横跨 CMDB 后端查询与权限、前端拓扑和资源列表。设计必须复用现有模型与关联，不新增 K8S 模型；必须在大规模 Pod 场景下保持首屏可用；必须遵循各模型独立的实例权限，不能因用户可查看 Cluster 就自动暴露全部子资源。

## Goals / Non-Goals

**Goals:**

- 在 `k8s_cluster` 详情中提供只读、符合 K8S 层级语义的资源概览。
- 首屏稳定展示 Cluster、Namespace、Workload、Node，Pod 按 Workload 分支分页展开。
- 支持多个 Workload 同时展开，并将 Pod 关联到首屏已有 Node。
- 统一统计、拓扑、列表的资源归属和权限口径。
- 使用可检查、可访问的 DOM 节点呈现五列分层拓扑，避免资源概览依赖通用画布组件。
- 对未归属、未调度、未匹配、无权限和局部请求失败提供可行动反馈。

**Non-Goals:**

- 创建、修改、删除 K8S 资源或查看/编辑 YAML。
- 新建 Service、Ingress、Endpoint、CRD、HPA、RBAC、ConfigMap、Secret、PV、PVC 等模型。
- 跨集群聚合或对比、实时推送、健康评分、告警嵌入。
- 重做 K8S 采集任务管理或定义新的采集健康状态机。
- 为后续迭代预留未实现页签、空白路由或禁用占位入口。

## Decisions

### 1. 使用实例详情一级菜单「资源详情」

K8S 资源视图作为 `k8s_cluster` 实例详情的独立一级菜单「资源详情」，与「基础信息」「关联关系」「变更记录」并列，并固定排列在「基础信息」之后、「关联关系」之前。该入口只对 `k8s_cluster` 显示，内容区域使用独立资源详情容器，并在容器内部提供概览、Namespace、Workload、Pod、Node 等二级资源导航。前端继续使用页面查询参数保存资源子视图和展开状态。

该布局遵循原型中的三段信息层级：实例详情一级导航负责切换业务域，资源二级导航负责切换 K8S 资源类型，右侧内容区负责概览拓扑或资源列表。它仍处于当前 Cluster 实例上下文中，不新增脱离实例详情的 CMDB 全局页面。

备选方案是把 K8S 资源视图继续放在「关联关系」内部，但资源概览、分支拓扑和多类列表已经构成持续使用的资源工作台，不只是通用关联关系的一种展示方式，因此不采用。

导航采用随能力交付逐次增加的策略。v1 只注册已经具备真实内容、数据接口和验收场景的入口，不渲染禁用页签或空白占位。「关系拓扑」「网络流向」以及其他后续规划能力不进入当前菜单、路由和国际化文案；下一次迭代实现时再通过独立规格增加。

资源二级导航按语义分为四段：概览与 Namespace 作为基础入口；Deployment、StatefulSet、DaemonSet、Job、CronJob、其他工作负载归入“工作负载”分组；Pod 进入独立“Pod”分组；Node 进入独立“Node”分组。Pod 和 Node 不得在视觉层级上从属于工作负载。由于二者当前各只有一个真实列表入口，分组采用常驻标题与单项导航，不增加无意义的折叠父菜单。

### 2. 使用四个职责明确的 API

后端提供以下逻辑接口，具体 DRF `url_path` 可保持下划线风格：

1. `GET .../k8s_overview/{cluster_id}/`：返回可见资源统计、采集事实、Cluster 和 Namespace 20、Workload 50、Node 50 的首批节点与基础边、各层分页元数据和各 Workload 的 Pod 数，不返回具体 Pod。
2. `GET .../k8s_overview/{cluster_id}/layers/{layer}/?page=...&page_size=...`：增量返回 Namespace、Workload 或 Node 节点与关系边；Workload 查询限定在当前已加载 Namespace ID 集合内。
3. `GET .../k8s_overview/{cluster_id}/workloads/{workload_id}/pods/?page=1&page_size=50`：返回单个 Workload 的 Pod、关系边和分页信息。
4. `GET .../k8s_overview/{cluster_id}/resources/{kind}/`：返回 Namespace、五类业务 Workload、其他工作负载、Pod、Node 的分页列表，并支持适用的关联过滤。

未归属 Pod 作为基础视图中的 Namespace 聚合信息，并通过专用分支查询或通用 Pod 列表的 `unowned` 过滤获取。接口不再暴露任意 `layers` 参数，因为层级组合会制造不完整依赖和不稳定查询成本。

备选方案是保留 summary、topology、resources 三个完全独立接口，但会重复图遍历并导致统计与拓扑来自不同可见集合，因此不采用。基础层增量接口复用同一可见资源服务和稳定排序，不能形成另一套统计口径。

### 3. 集中建立 K8S 可见资源服务

新增聚合服务负责：

1. 校验 Cluster 存在、模型正确且当前用户有实例查看权限；
2. 分别为 Namespace、Workload、Pod、Node 构建模型权限映射；
3. 从 CMDB 实例关联边构建 Cluster 范围内的资源集合；
4. 按父子可见性剪枝，避免悬空节点和旁路泄露；
5. 向统计、基础拓扑、Pod 分支和资源列表提供同一套规范化结果。

权限策略采用“Cluster 是入口、子资源继续独立过滤”。用户没有 Cluster 权限时拒绝整个请求；用户只有部分子资源权限时，所有数量和关系只基于可见资源。Pod 可见但 Node 无权限时，只返回无权限虚拟关系，不返回 Node 名称或属性。

备选方案是继承 Cluster 权限到所有子对象，虽然实现简单，但会绕过现有模型/实例授权，因此不采用。

### 4. 以关联边为唯一关系依据

拓扑关系使用现有实例关联中的模型 ID、实例 ID 和关联 ID 生成。`self_cluster`、`self_ns`、Pod `node` 名称等字段只可用于诊断或兼容性核对，不作为推断父节点的主要依据。所有请求参数中的资源 ID 都必须再次验证属于 URL 指定 Cluster。

这避免原草案通过名称包含或字段反查父 Workload/Namespace 所造成的重名、改名和孤立数据问题。

### 5. 默认四类节点可见，Pod 按分支增量加入

基础图固定展示 Cluster、Namespace、Workload、Node；Pod 层初始为空。用户点击 Workload 后，前端请求该分支第一页 Pod，并局部插入 `Workload → Pod`、`Pod → Node` 边。Node 在全图中按实例 ID 唯一，所有 Pod 复用首屏 Node。

多个 Workload 可以同时展开。每个分支首次加载 50 个 Pod，后续每次加载下一页；UI 始终显示已加载数量和可见总数。该设计用明确分页代替“取前 500 个节点”的静默截断。

未归属 Pod 在 Namespace 下使用聚合入口。Pod 无 Node 关联、Node 不存在、Node 无权限分别映射为“未调度”“Node 未匹配”“目标 Node 无权限”虚拟节点，三者不得合并。

备选方案是首屏加载全部五层实例，但在中大型集群中会形成不可读线团并放大查询成本，因此不采用。

### 6. Workload 分类采用业务类型加兜底类型

导航和列表明确展示 Deployment、StatefulSet、DaemonSet、Job、CronJob。未能归入这五类的独立 ReplicaSet 和其他类型进入“其他工作负载”。概览主指标中的 Workload 数仅统计五类业务 Workload；其他工作负载数量在类型分布和对应列表中独立展示，避免把实现层对象混入业务工作负载口径。

该方式既保持常用业务对象清晰，又不静默丢弃采集器已经写入的独立 ReplicaSet。

### 7. 概览不展示采集事实

概览只展示资源指标和分层拓扑，不再渲染最近上报时间、最近成功采集时间、最近结果或错误摘要、关联采集任务等“采集事实”区域。后端现有 `collection_facts` 响应字段本次保持不变，避免把前端信息层级调整扩大为接口兼容变更；前端停止消费和展示该字段。

资源数量为零时直接显示零和空列表，页面不根据采集事实替用户解释零资源原因。

### 8. 前端使用独立分支状态和稳定布局

前端以 `expandedWorkloadIds` 管理多分支展开，并为每个分支保存状态、页码、总数、节点、边和错误。并发 Pod 请求上限为四个，额外请求排队；收起加载中分支时取消请求或忽略迟到响应。

已完成分支保留会话缓存，收起再展开不重复请求；手动刷新清空缓存。URL 使用 `expanded=<id1>,<id2>` 保存展开集合，但不保存分页进度，刷新后每个分支从第一页恢复。

拓扑使用五列 DOM 布局。Cluster、Namespace、Workload、Pod、Node 使用稳定列分组和排序；插入或移除 Pod 时只更新受影响的列和关系线。单分支错误只在该 Workload 上显示并支持重试，不覆盖其他分支或资源列表。

### 9. 资源列表保持严格只读

v1 资源列表只承担“在当前 Cluster 中查找资源并进入现有 CMDB 实例详情”的任务。工具区只提供适用的关联筛选、名称搜索和刷新，列表提供分页与每页数量；资源名称使用语义化链接，在新的浏览器标签页打开该资源现有的 CMDB 基础信息页，并携带目标模型、实例 ID 和实例名称。当前 K8S 资源列表及筛选上下文保留在原标签页。

所有 K8S 资源列表直接复用资产管理实例列表使用的 `CustomTable` 与 `size="small"` 密度，而不是复制一套相似 CSS。表格沿用同一套表头、紧凑行高、列宽拖拽、表体滚动、底部分页、加载态、空态和缺失值呈现。页面不启用实例列表的勾选、字段设置、创建、导出和批量操作，确保视觉底座一致但能力仍严格只读。工具栏布局与资产实例列表一致：搜索和关联筛选位于左侧，刷新位于右侧；资源列表不再使用额外卡片边框和大内边距包裹表格。

资源列表页只保留表格内部一个纵向滚动区域。内容区通过 flex 剩余高度约束列表，`CustomTable` 根据实际父容器高度计算表体，不使用基于浏览器视口的固定 `calc(100vh - Npx)`。实例详情外层、K8S 内容区和表格不得同时产生纵向滚动条；概览页继续使用自身页面滚动，不受列表高度策略影响。

不渲染创建 Deployment、查看或编辑 YAML、“更多”写操作、批量选择、列设置、下载导出或其他未交付工具。后续写操作、YAML 或导出能力必须通过独立规格定义权限、安全和审计后再增加，当前页面不预留禁用入口。

### 10. 列表使用资源类型固定列

列表不直接复用通用 CMDB 动态字段表，而是按 K8S 资源类型配置稳定、可识别的业务列：Namespace 展示名称和聚合的 Workload/Pod 数；Workload 展示名称、Namespace、类型、副本数和 Pod 数；Pod 展示名称、Namespace、所属 Workload、Node、Pod IP 和资源请求/限制；Node 展示名称、角色和 CPU/内存/临时存储容量。

列值来自现有模型属性或 K8S 可见资源服务基于关联的可靠聚合。字段没有数据时显示 `—`。当前采集链路不能可靠提供的镜像、运行状态、创建时间等原型字段不进入 v1 列配置，避免用占位值制造错误信息。

### 11. 概览与资源列表保持不同信息密度

资源指标卡和分层拓扑只在二级导航“概览”中渲染。用户切换到 Namespace、Workload、Pod 或 Node 时，内容区域只保留当前资源标题、适用筛选、名称搜索、刷新和列表，避免重复概览信息挤压可用表格高度。

概览组件在资源详情容器内保留展开集合和分支缓存；用户从列表返回概览时恢复离开前状态，而不是重新加载并丢失定位上下文。

### 12. 拓扑采用 DIV 五列与轻量 SVG 关系线

概览拓扑固定使用 `Cluster | Namespace | Workload | Pod | Node` 五列。列头和节点使用 CSS Grid 与可聚焦 DIV 卡片实现；Pod 列初始为空且不显示伪节点，展开 Workload 后 Pod 增量进入该列并连接 Node 列中的既有唯一节点。Container、Service 不属于 v1 模型范围，不配置对应列。

拓扑不再使用 `NetworkTopologyX6Canvas` 或其他通用画布组件。关系线由位于节点层下方的绝对定位 SVG 覆盖层绘制，SVG 设置 `pointer-events: none`，只负责视觉连线，不承载选择、菜单或数据状态。组件通过节点 DOM 引用和 `ResizeObserver` 获取端点坐标，并在容器尺寸、节点集合或展开状态变化后重新计算。

五列共享同一个纵向滚动容器，内容高度取最长节点列；禁止各列独立滚动，也不产生页面级横向滚动。列头保持固定，SVG 与节点位于相同滚动坐标空间，滚动后关系线不得错位。移除缩略图、放大、缩小、适应画布、画布拖动和拓扑导出；资源类型图例保留。节点类型颜色保持稳定，选中态仅增加蓝色描边。

### 13. 单击聚焦与右键操作分离

节点单击只更新 `selectedNodeId` 和高亮路径，不改变数据加载状态。Namespace 聚焦其可见下游，Workload 聚焦当前可见路径，Pod 聚焦到对应 Node 的完整可见链路，Node 聚焦当前已加载的关联 Pod。再次单击当前节点或点击画布空白清除聚焦。

节点右键打开只读上下文菜单。Workload 菜单根据分支状态提供“展开 Pod”“收起 Pod”“继续加载 Pod”“查看 Pod 列表”和“查看实例详情”；其他节点只提供适用的关联列表和实例详情入口。打开菜单本身不触发请求，只有选择菜单项才执行动作。

为保证键盘可达性，聚焦节点支持菜单键和 `Shift+F10` 打开同一菜单，方向键切换菜单项，Enter 执行，Escape 关闭。上下文菜单不包含任何资源写操作或 YAML 能力。

### 14. 基础层使用稳定的增量批次

基础拓扑首批最多返回 Namespace 20、Workload 50、Node 50，并分别返回已展示数量、当前可见总数和下一页信息。Namespace 和 Node 按名称排序；Workload 按 Namespace 名称、类型、名称排序。每次“展开更多”沿同一排序继续加载，响应必须去重且不得用任意截断冒充完整结果。

Workload 增量范围限定在前端当前已加载的 Namespace 集合，确保任何 Workload 返回时父 Namespace 已存在。新增 Namespace 后前端更新 Workload 当前可加载总数，用户可以继续加载对应 Workload。概览指标仍统计整个 Cluster 下所有可见资源，不随拓扑加载批次变化。

### 15. 三栏布局优先保障内容区宽度

页面沿用实例详情一级导航，并在资源详情内容中增加默认 220px 的 K8S 二级资源导航。二级导航支持折叠为 56px 图标栏，折叠状态在当前页面会话和资源子视图切换期间保留。

当展开导航会使右侧内容区低于 1100px 时，页面自动折叠二级导航；用户主动展开时使用覆盖式面板，不继续挤压拓扑和表格。v1 以宽度不低于 1280px 的桌面控制台为支持边界，不增加独立移动端信息架构。拓扑和表格只在内容区内部自适应，页面外层禁止横向滚动。

## Risks / Trade-offs

- [基础视图中的 Workload 或 Node 仍可能很多] → 保留缩放、定位和列表入口；Pod 不进入首屏，避免最主要的数据膨胀源。
- [基础层增量导致拓扑节点数小于概览指标] → 每层明确展示“已展示/总数”，资源列表始终提供完整分页查询，禁止用当前图节点数覆盖概览指标。
- [分别计算五种模型权限增加查询成本] → 在单次请求内缓存权限映射和可见实例集合，所有输出复用该集合。
- [关联数据不完整导致虚拟节点较多] → 明确区分未归属、未调度、未匹配和无权限，不使用名称推断掩盖数据质量问题。
- [多分支展开导致请求和画布压力] → 每分支分页 50、并发上限四个、无一键展开全部，并提供完整列表入口。
- [大量节点使 DOM 和 SVG 关系线更新成本上升] → 基础层继续分页，Pod 按 Workload 分支分页；使用单个 `ResizeObserver` 批量重新计算，不为每条边注册独立观察器。
- [URL 中展开 ID 较多] → 仅记录用户手动展开集合，不记录 Pod ID 或页码；无效或越权 ID 在恢复时安全忽略并局部提示。
- [三栏布局压缩内容区] → 二级导航可折叠，在内容区不足 1100px 时自动折叠并以覆盖方式临时展开。

## Migration Plan

1. 增加后端规范化查询、权限过滤、接口和测试，不修改现有 K8S 模型与采集关系。
2. 增加仅适用于 `k8s_cluster` 的实例详情一级「资源详情」入口。
3. 增加独立资源详情容器、二级导航、DIV 五列基础拓扑、Pod 分支和资源列表。
4. 在测试环境使用小集群、大 Workload、孤立关系和部分权限账号验证。
5. 若需要回退，只移除「资源详情」一级入口和新增接口/组件，不涉及数据迁移，现有「关联关系」页面不受影响。

## Open Questions

无。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-10
```

## Capability Deltas

### cmdb-k8s-resource-overview

## ADDED Requirements

### Requirement: K8S 集群资源详情一级入口
系统 SHALL 仅在 `k8s_cluster` 实例详情提供一级菜单「资源详情」，该菜单 SHALL 与「基础信息」「关联关系」「变更记录」并列，并 SHALL 保留现有通用关联关系页面及其能力。

#### Scenario: K8S 集群显示资源详情
- **WHEN** 用户具有目标 `k8s_cluster` 实例的查看权限并打开其实例详情
- **THEN** 系统在实例详情一级导航中显示「资源详情」入口
- **AND** 「资源详情」排列在「基础信息」之后、「关联关系」之前
- **AND** 用户进入该入口后看到独立的 K8S 资源导航与内容区域

#### Scenario: 非 K8S 集群不显示资源详情
- **WHEN** 用户打开非 `k8s_cluster` 模型的实例详情
- **THEN** 系统不显示「资源详情」入口

#### Scenario: 通用关联关系保持独立
- **WHEN** 用户在 `k8s_cluster` 实例详情选择「关联关系」
- **THEN** 系统继续展示现有通用关联关系页面
- **AND** 不把 K8S 资源详情嵌入该页面的子视图

### Requirement: 不展示未实现页签
系统 SHALL 仅注册和展示 v1 已交付能力对应的导航入口，并 MUST NOT 为后续迭代预留空白、禁用或不可用页签。

#### Scenario: 资源详情渲染 v1 导航
- **WHEN** 用户打开 K8S「资源详情」
- **THEN** 系统仅展示当前可用的概览和资源类型导航
- **AND** 不展示「关系拓扑」「网络流向」或其他尚未实现的页签

#### Scenario: 后续能力尚未交付
- **WHEN** 某个规划能力尚未包含在当前版本
- **THEN** 该能力的页签、路由入口和占位文案均不存在

### Requirement: 三栏桌面布局与二级导航折叠
系统 SHALL 在现有实例一级导航、K8S 二级资源导航和内容区组成的三栏桌面布局中，为二级资源导航提供折叠和窄屏覆盖模式，并 SHALL 避免通过挤压内容区或外层横向滚动适配窄屏。

#### Scenario: 标准桌面宽度
- **WHEN** 可用页面宽度足以容纳三栏且内容区不少于 1100px
- **THEN** K8S 二级资源导航默认以 220px 宽度展开
- **AND** 用户可以手动折叠为 56px 图标栏

#### Scenario: 内容区宽度不足
- **WHEN** 展开的二级资源导航会使内容区宽度低于 1100px
- **THEN** 系统自动将二级资源导航折叠为 56px
- **AND** 用户临时展开时导航以覆盖式面板显示，不继续压缩内容区

#### Scenario: 保留会话折叠状态
- **WHEN** 用户在当前会话中手动折叠或展开二级资源导航
- **THEN** 页面在资源子视图切换期间保持该状态

#### Scenario: 桌面端边界
- **WHEN** 用户在宽度不低于 1280px 的桌面浏览器访问资源详情
- **THEN** 拓扑和表格在内容区内自适应
- **AND** 页面外层不产生横向滚动条
- **AND** v1 不承诺独立移动端布局

### Requirement: 默认资源概览
系统 SHALL 在首次进入视图时展示当前集群下用户可见的 Cluster、Namespace、Workload 和 Node 节点，且 MUST NOT 首屏加载具体 Pod 节点。

#### Scenario: 首屏加载基础拓扑
- **WHEN** 用户首次打开 K8S 资源视图
- **THEN** 系统返回并展示 Cluster、Namespace、Workload、Node 及其现有 CMDB 关联
- **AND** 系统不请求或展示具体 Pod 节点

#### Scenario: 默认显示资源统计
- **WHEN** 基础视图加载成功
- **THEN** 系统展示当前用户可见的 Namespace、业务 Workload、Pod、Node 数量
- **AND** Pod 数量同时包含有 Workload 归属和未归属 Pod

### Requirement: 概览信息不侵占资源列表
系统 SHALL 仅在二级导航选择“概览”时展示资源指标卡和分层拓扑，并 MUST NOT 展示采集事实区域，也 MUST NOT 在 Namespace、Workload、Pod、Node 资源列表页重复展示这些概览区域。

#### Scenario: 打开概览
- **WHEN** 用户选择二级导航“概览”
- **THEN** 页面展示资源指标卡和分层拓扑
- **AND** 不展示最近上报、最近成功采集、最近结果或采集任务等采集事实

#### Scenario: 打开资源列表
- **WHEN** 用户选择 Namespace、任一 Workload 分类、Pod 或 Node
- **THEN** 页面内容区仅展示当前资源标题、适用的关联筛选、名称搜索、刷新和资源列表
- **AND** 不展示资源指标卡或概览拓扑

#### Scenario: 从列表返回概览
- **WHEN** 用户从资源列表返回“概览”
- **THEN** 页面恢复离开概览前的 Workload 展开集合和已加载分支缓存

### Requirement: 五列 DIV 分层拓扑视觉结构
系统 SHALL 使用 CSS Grid、DIV 节点和轻量 SVG 关系线表达固定列头 `Cluster | Namespace | Workload | Pod | Node`，并 MUST NOT 使用 X6 通用画布组件。

#### Scenario: 首屏渲染五列结构
- **WHEN** 用户打开概览
- **THEN** 页面固定展示 Cluster、Namespace、Workload、Pod、Node 五个列头
- **AND** 列头与节点由 DOM 元素渲染
- **AND** Pod 列在未展开 Workload 时不创建占位节点
- **AND** Node 列展示首屏已加载的可见 Node

#### Scenario: 展开 Pod 后保持 Node 唯一
- **WHEN** 用户展开一个或多个 Workload
- **THEN** Pod 节点出现在 Pod 列并关联到 Node 列中的既有唯一 Node
- **AND** 既有 Cluster、Namespace、Workload、Node 的位置保持稳定

#### Scenario: 长列使用共享滚动
- **WHEN** 任一拓扑列的节点超出当前拓扑内容区
- **THEN** 五列在同一个纵向滚动容器中同步滚动
- **AND** 列头保持固定
- **AND** 各列不创建独立滚动条
- **AND** 页面不额外生成横向滚动条

#### Scenario: DOM 变化后关系线保持对齐
- **WHEN** 容器尺寸、节点集合、Pod 展开状态或基础层批次发生变化
- **THEN** 系统根据节点 DOM 位置重新计算 SVG 关系线端点
- **AND** 滚动、展开或收起后关系线仍连接正确节点
- **AND** SVG 关系层不接收鼠标或键盘事件

#### Scenario: 不展示非 v1 层级与工具
- **WHEN** 系统渲染 v1 分层拓扑
- **THEN** 不显示 Container、Service 列
- **AND** 不显示缩略图、放大、缩小、适应画布、画布拖动、拓扑导出或独立拓扑刷新

#### Scenario: 保持资源类型视觉编码
- **WHEN** 用户选择拓扑节点
- **THEN** 节点使用蓝色描边表达选中状态
- **AND** 节点原有资源类型颜色保持不变

### Requirement: 基础拓扑分层增量展示
系统 SHALL 对 Namespace、Workload、Node 使用明确的服务端增量展示，首批分别最多展示 20、50、50 个节点，并 SHALL 显示每层已展示数量和当前可见总数，不得静默截断。

#### Scenario: 首次加载基础拓扑批次
- **WHEN** 当前集群的可见 Namespace、Workload 或 Node 超过对应首批数量
- **THEN** 系统首批最多展示 20 个 Namespace、50 个 Workload 和 50 个 Node
- **AND** 每层显示“已展示 N / 总数”和“展开更多”入口

#### Scenario: 加载更多基础节点
- **WHEN** 用户点击某层“展开更多”
- **THEN** Namespace 每次最多增加 20 个，Workload 和 Node 每次最多增加 50 个
- **AND** 已有节点不重复且已展示数量按实际结果更新

#### Scenario: 基础节点稳定排序
- **WHEN** 用户连续加载多批节点或刷新同一数据快照
- **THEN** Namespace 和 Node 按名称稳定排序
- **AND** Workload 按 Namespace 名称、类型、名称稳定排序

#### Scenario: Workload 父节点完整
- **WHEN** 系统返回一批 Workload 节点
- **THEN** 每个 Workload 的父 Namespace 必须已经在图中
- **AND** Workload 增量查询仅在当前已加载 Namespace 范围内计算可加载集合

#### Scenario: 完整资源仍可查询
- **WHEN** 某层拓扑尚未加载全部节点
- **THEN** 对应资源列表仍可分页查询当前 Cluster 下全部用户可见资源

### Requirement: 单击聚焦与右键菜单操作分离
系统 SHALL 将节点单击限定为拓扑聚焦，并 SHALL 通过节点右键上下文菜单执行 Pod 展开/收起和其他只读操作；单击 Workload MUST NOT 发起 Pod 请求。

#### Scenario: 单击 Namespace 聚焦
- **WHEN** 用户单击 Namespace 节点
- **THEN** 系统高亮该 Namespace 及其当前可见下游路径
- **AND** 其他分支降低透明度但不被隐藏

#### Scenario: 单击 Workload 聚焦
- **WHEN** 用户单击 Workload 节点
- **THEN** 系统仅聚焦该 Workload 及其当前可见路径
- **AND** 不展开、收起或请求 Pod

#### Scenario: 单击 Pod 或 Node 聚焦
- **WHEN** 用户单击 Pod
- **THEN** 系统高亮该 Pod 对应的 `Namespace → Workload → Pod → Node` 可见路径
- **WHEN** 用户单击 Node
- **THEN** 系统高亮当前已经加载且关联该 Node 的 Pod 和路径
- **AND** 不为尚未加载的 Pod 发起批量请求

#### Scenario: 清除聚焦
- **WHEN** 用户再次单击当前节点或单击画布空白区域
- **THEN** 系统清除聚焦并恢复全图正常透明度

#### Scenario: 右键展开或收起 Workload
- **WHEN** 用户右键 Workload 节点
- **THEN** 系统打开只读上下文菜单
- **AND** 菜单根据当前分支状态提供“展开 Pod”或“收起 Pod”
- **AND** 只有用户选择对应菜单项后系统才改变分支状态或发起请求

#### Scenario: 右键菜单只提供只读操作
- **WHEN** 用户打开任意拓扑节点上下文菜单
- **THEN** 菜单仅提供适用的展开/收起、查看关联资源列表和查看 CMDB 实例详情操作
- **AND** 不提供创建、编辑、删除或 YAML 操作

#### Scenario: 键盘打开上下文菜单
- **WHEN** 键盘焦点位于拓扑节点且用户按下菜单键或 `Shift+F10`
- **THEN** 系统打开与右键相同的上下文菜单
- **AND** 用户可以使用键盘选择菜单项或按 `Escape` 关闭

### Requirement: Workload 分类导航
系统 SHALL 提供概览、Namespace、Deployment、StatefulSet、DaemonSet、Job、CronJob、其他工作负载、Pod 和 Node 导航，并 SHALL 为每个导航项提供当前集群范围内的资源列表。

#### Scenario: 展示业务 Workload 分类
- **WHEN** 用户打开资源导航
- **THEN** 系统分别显示五类业务 Workload 导航
- **AND** 独立 ReplicaSet 或其他非五类 Workload 进入“其他工作负载”

#### Scenario: Namespace 与 Node 列表
- **WHEN** 用户选择 Namespace 或 Node 导航
- **THEN** 系统展示当前集群下用户可见的对应资源列表

#### Scenario: Pod 与 Node 使用独立导航分组
- **WHEN** 用户打开 K8S 资源二级导航
- **THEN** Deployment、StatefulSet、DaemonSet、Job、CronJob 和其他工作负载显示在“工作负载”分组
- **AND** Pod 显示在独立“Pod”分组
- **AND** Node 显示在独立“Node”分组
- **AND** Pod、Node 不显示为“工作负载”的子项

### Requirement: 多 Workload Pod 展开
系统 SHALL 允许用户同时展开多个 Workload，并 SHALL 为每个 Workload 独立维护未加载、等待加载、加载中、部分加载、全部加载和加载失败状态。

#### Scenario: 同时展开多个 Workload
- **WHEN** 用户依次展开多个 Workload
- **THEN** 系统保留所有已展开分支
- **AND** 每个分支独立加载和展示 Pod

#### Scenario: 限制并发请求
- **WHEN** 同时存在超过四个尚未完成的 Pod 分支请求
- **THEN** 系统最多并行执行四个请求
- **AND** 其余分支显示等待加载并按队列继续执行

#### Scenario: 收起 Workload
- **WHEN** 用户收起已展开 Workload
- **THEN** 系统从拓扑移除该 Workload 的 Pod 节点及相关边
- **AND** 保留 Cluster、Namespace、Workload、Node 及其他已展开分支

### Requirement: Pod 分页加载
系统 SHALL 为每个 Workload 首次加载最多 50 个 Pod，并 SHALL 明确展示已加载数量、可见总数和继续加载入口，不得静默截断。

#### Scenario: Workload Pod 超过 50 个
- **WHEN** Workload 有 137 个用户可见 Pod 且用户首次展开
- **THEN** 系统展示前 50 个 Pod 和“已显示 50 / 137”
- **AND** 系统提供继续加载和查看完整列表入口

#### Scenario: 继续加载 Pod
- **WHEN** 用户对部分加载分支执行继续加载
- **THEN** 系统加载下一页且不重复已有 Pod
- **AND** 已加载数量按实际结果更新

#### Scenario: Workload 没有 Pod
- **WHEN** 用户展开可见 Pod 数为零的 Workload
- **THEN** 系统明确显示 `Pod 0`
- **AND** 不创建空白或伪造节点

### Requirement: Pod 与 Node 关系展示
系统 SHALL 在展开 Workload 时使用现有 CMDB 实例关联生成 `Workload → Pod` 和 `Pod → Node` 边，并 SHALL 将 Pod 关联到首屏已存在的唯一 Node 节点。

#### Scenario: Pod 关联已有 Node
- **WHEN** 展开的 Pod 与当前视图中的可见 Node 存在关联
- **THEN** 系统复用该 Node 节点并展示 `Pod → Node` 边
- **AND** 不为同一 Node 创建重复节点

#### Scenario: Pod 未调度
- **WHEN** Pod 没有 Node 关联
- **THEN** 系统将其关联到“未调度”虚拟节点

#### Scenario: Node 未匹配
- **WHEN** Pod 记录了 Node 关联但对应 Node 不存在于当前集群采集结果
- **THEN** 系统将其关联到“Node 未匹配”虚拟节点

#### Scenario: 目标 Node 无权限
- **WHEN** Pod 可见但其目标 Node 被权限过滤
- **THEN** 系统将其关联到“目标 Node 无权限”虚拟节点
- **AND** 不返回或展示目标 Node 的名称及其他属性

### Requirement: 未归属 Pod 展示
系统 SHALL 统计和展示未关联到 Workload 的 Pod，并 SHALL 在 Namespace 下提供独立的未归属 Pod 聚合入口。

#### Scenario: Namespace 存在未归属 Pod
- **WHEN** 可见 Pod 直接关联 Namespace 而未关联 Workload
- **THEN** 系统在对应 Namespace 下展示未归属 Pod 数量和展开入口
- **AND** 这些 Pod 计入 Pod 总数和 Pod 资源列表

### Requirement: 资源列表查询
系统 SHALL 为每种导航资源提供分页、搜索、排序和集群范围约束，并 SHALL 支持按 Namespace、Workload 或 Node 进行适用的关联过滤。

#### Scenario: 从 Node 反查 Pod
- **WHEN** 用户在 Pod 列表中使用 `node_id` 过滤
- **THEN** 系统仅返回当前集群内关联该 Node 且用户可见的 Pod

#### Scenario: 从 Namespace 查看 Workload
- **WHEN** 用户在 Workload 列表中使用 `namespace_id` 过滤
- **THEN** 系统仅返回当前集群内关联该 Namespace 且用户可见的 Workload

#### Scenario: 搜索与分页保持集群边界
- **WHEN** 用户组合使用搜索、排序和分页参数
- **THEN** 所有返回结果仍限定于当前 Cluster 和用户可见范围

### Requirement: 资源列表严格只读
系统 SHALL 将 v1 资源列表限定为查询和查看用途，仅提供关联筛选、名称搜索、刷新、分页以及进入现有 CMDB 实例详情的操作，并 MUST NOT 提供任何资源写入或未交付的管理入口。

#### Scenario: 查看资源实例详情
- **WHEN** 用户点击资源列表中的资源名称
- **THEN** 系统在新的浏览器标签页打开该资源现有的 CMDB 基础信息页
- **AND** 新页面携带目标模型、实例 ID 和实例名称
- **AND** 原标签页保留当前 K8S 资源列表及筛选上下文
- **AND** 不在 K8S 资源详情页面内执行资源变更

#### Scenario: 不展示写操作
- **WHEN** 用户打开任意 K8S 资源列表
- **THEN** 页面不展示创建、编辑、删除、查看或编辑 YAML、“更多”写操作和批量选择入口

#### Scenario: 不展示未交付工具
- **WHEN** 下载导出、列设置或其他管理工具未包含在 v1 规格中
- **THEN** 页面不渲染对应按钮、禁用控件或占位菜单

#### Scenario: 资源表格与资产实例列表保持一致
- **WHEN** 用户打开任意 K8S 资源列表
- **THEN** 页面使用资产管理实例列表相同的 `CustomTable` 和紧凑表格密度
- **AND** 表头、行高、列宽交互、滚动区域、加载态、空态和底部分页保持一致
- **AND** 搜索与关联筛选位于工具栏左侧，刷新位于工具栏右侧
- **AND** 表格外层不增加独立卡片边框和大内边距

#### Scenario: 资源列表只保留一个纵向滚动区域
- **WHEN** 资源列表高度超过当前实例详情内容区可用高度
- **THEN** `CustomTable` 根据实际父容器剩余高度计算表体滚动区域
- **AND** 页面不使用固定视口偏移量计算表格高度
- **AND** 实例详情外层和 K8S 内容区不额外产生纵向滚动条
- **AND** 概览页仍可按页面内容正常纵向滚动

### Requirement: 按资源类型展示固定业务列
系统 SHALL 为每种 K8S 资源列表配置固定业务列，并 SHALL 仅展示现有模型或可靠聚合能够提供的数据；字段缺失时 MUST 显示 `—`，不得伪造值或因原型占位新增无来源字段。

#### Scenario: Namespace 列表字段
- **WHEN** 用户打开 Namespace 列表
- **THEN** 页面展示名称、Workload 数和 Pod 数

#### Scenario: Workload 列表字段
- **WHEN** 用户打开五类业务 Workload 或其他工作负载列表
- **THEN** 页面展示名称、Namespace、实际类型、副本数和 Pod 数
- **AND** 某类型没有可靠副本数据时对应单元格显示 `—`

#### Scenario: Pod 列表字段
- **WHEN** 用户打开 Pod 列表
- **THEN** 页面展示名称、Namespace、所属 Workload、Node、Pod IP 和资源请求/限制

#### Scenario: Node 列表字段
- **WHEN** 用户打开 Node 列表
- **THEN** 页面展示名称、角色、CPU、内存和临时存储容量

#### Scenario: 原型字段没有可靠来源
- **WHEN** 镜像、运行状态、创建时间或其他原型字段无法从当前模型和采集链路可靠获得
- **THEN** 页面不配置该列

### Requirement: 分层权限过滤
系统 MUST 先校验目标 Cluster 实例查看权限，再分别按 Namespace、Workload、Pod、Node 的模型和实例权限过滤子资源；指标、拓扑和列表 SHALL 复用同一可见资源口径。

#### Scenario: 无 Cluster 权限
- **WHEN** 用户没有目标 Cluster 实例查看权限
- **THEN** 所有 K8S 资源视图接口返回拒绝访问

#### Scenario: 仅有部分子资源权限
- **WHEN** 用户可以查看 Cluster 但仅能查看部分子资源
- **THEN** 指标、拓扑和列表仅包含有权资源
- **AND** 响应不泄露无权资源名称、属性或精确数量

#### Scenario: 父资源不可见
- **WHEN** 子资源自身可见但其父 Namespace 或 Workload 不可见
- **THEN** 系统不在拓扑中将该子资源作为悬空节点展示

### Requirement: 集群归属参数校验
系统 MUST 验证请求中的 Workload、Namespace、Pod 和 Node 标识属于 URL 指定的 Cluster，不得仅验证对象存在。

#### Scenario: 跨集群 Workload 标识
- **WHEN** 用户使用其他 Cluster 的 `workload_id` 请求 Pod 分支
- **THEN** 系统拒绝请求且不返回任何目标资源信息

#### Scenario: 跨集群列表过滤标识
- **WHEN** 用户使用其他 Cluster 的 `namespace_id`、`workload_id` 或 `node_id` 过滤资源列表
- **THEN** 系统拒绝请求或返回空结果
- **AND** 不泄露该标识对应的资源属性

### Requirement: 局部失败与状态恢复
系统 SHALL 隔离基础视图、资源列表和各 Pod 分支的请求状态，并 SHALL 支持局部重试、多分支缓存和 URL 展开状态恢复。

#### Scenario: 单分支加载失败
- **WHEN** 一个 Workload 的 Pod 请求失败
- **THEN** 仅该分支显示错误和重试入口
- **AND** 其他已加载分支及基础拓扑保持可用

#### Scenario: 收起后重新展开
- **WHEN** 用户在同一页面会话中收起并重新展开已加载 Workload
- **THEN** 系统复用该分支缓存而不重复请求

#### Scenario: 手动刷新
- **WHEN** 用户执行资源视图刷新
- **THEN** 系统清除分支缓存并重新加载基础视图及 URL 指定的展开分支

#### Scenario: URL 恢复多个展开分支
- **WHEN** 用户访问包含多个有效 Workload ID 的展开状态 URL
- **THEN** 系统恢复这些展开分支并从每个分支第一页开始加载

## Work Checklist

## 1. 后端契约测试

- [x] 1.1 为基础概览编写失败测试，覆盖默认返回 Cluster、Namespace、Workload、Node、不返回具体 Pod，以及统一可见数量
- [x] 1.2 为 K8S 可见资源集合编写失败测试，覆盖五种模型独立权限、父资源剪枝和无权数量不泄露
- [x] 1.3 为关联图构建编写失败测试，覆盖真实关联边、未归属 Pod、未调度、Node 未匹配和目标 Node 无权限
- [x] 1.4 为 Workload Pod 分支编写失败测试，覆盖每页 50、连续分页、零 Pod、跨集群 Workload 拒绝
- [x] 1.5 为资源列表编写失败测试，覆盖全部 kind、分页、搜索、排序及 Namespace、Workload、Node 关联过滤
- [x] 1.6 为接口守卫编写失败测试，覆盖 Cluster 不存在、模型错误、无 Cluster 权限、非法 kind 和跨集群过滤 ID
- [x] 1.7 为采集事实编写失败测试，覆盖部分字段可用、字段为空、最近错误存在且历史资源仍返回
- [x] 1.8 为基础层增量查询编写失败测试，覆盖 Namespace 20、Workload 50、Node 50、稳定排序、去重、父 Namespace 完整和总数元数据

## 2. 后端实现

- [x] 2.1 增加 K8S 概览查询序列化器，定义分页、搜索、排序、kind 和关联过滤参数白名单
- [x] 2.2 实现 K8S 可见资源服务，按 Cluster、Namespace、Workload、Pod、Node 分别构建并缓存权限映射
- [x] 2.3 使用 CMDB 实例关联构建 Cluster 范围资源集合与父子可见性剪枝，不使用名称字段推断主关系
- [x] 2.4 实现基础概览聚合，返回统计、类型分布、采集事实和无 Pod 的基础拓扑
- [x] 2.5 实现 Workload Pod 分支与未归属 Pod 查询，返回分页节点、关系边和可见总数
- [x] 2.6 实现 Namespace、五类业务 Workload、其他工作负载、Pod、Node 通用资源列表及关联过滤
- [x] 2.7 在 `InstanceViewSet` 注册基础概览、Pod 分支、未归属 Pod 和资源列表只读 action，并复用统一错误响应
- [x] 2.8 实现 Namespace、Workload、Node 分层增量 action，限制批次大小并验证 Workload 的已加载 Namespace 范围
- [x] 2.9 运行后端定向测试并重构重复查询和规范化逻辑，确认新增代码覆盖率不低于 75%

## 3. 前端契约与组件测试

- [x] 3.1 为 K8S 概览 API 客户端编写失败测试，覆盖基础视图、Pod 分页、未归属 Pod 和资源列表参数
- [x] 3.2 为资源导航编写失败测试，覆盖 Namespace、五类 Workload、其他工作负载、Pod、Node、URL 子视图状态，以及不渲染「关系拓扑」「网络流向」等未实现页签
- [x] 3.3 为概览和资源列表页面边界编写初版失败测试，确认初版概览与列表边界和状态恢复；采集事实断言最终由 3.16 替代
- [x] 3.4 为多 Workload 展开编写失败测试，覆盖同时展开、独立收起、并发上限四个、等待队列和局部失败重试
- [x] 3.5 为 Pod 分页和缓存编写失败测试，覆盖 50 条首屏、继续加载、收起后复用、手动刷新失效和 URL 恢复
- [x] 3.6 为关系异常编写失败测试，覆盖未归属、未调度、Node 未匹配和目标 Node 无权限的不同呈现
- [x] 3.7 为资源列表编写失败测试，覆盖分页、搜索、排序、关联过滤、空数据、局部接口失败、资源名称跳转，以及不渲染创建、YAML、更多、批量、设置和下载入口
- [x] 3.8 为各资源类型固定列编写失败测试，覆盖可靠字段映射、关联聚合数量、缺失值 `—` 和不展示无来源原型字段
- [x] 3.9 为初版 X6 五列拓扑视觉结构编写失败测试；X6、缩略图和画布控制断言最终由 3.16 替代
- [x] 3.10 为拓扑节点交互编写失败测试，覆盖单击聚焦不请求 Pod、右键菜单展开/收起、只读菜单项、清除聚焦和 `Shift+F10` 键盘操作
- [x] 3.11 为基础层“展开更多”编写失败测试，覆盖 20/50/50 首批数量、已展示/总数、稳定追加、去重和 Workload 父 Namespace 完整
- [x] 3.12 为三栏响应式布局编写失败测试，覆盖 220px 展开、56px 折叠、内容区不足 1100px 自动折叠、覆盖式展开和会话状态保持
- [x] 3.13 为资源导航分组编写失败测试，覆盖工作负载、Pod、Node 三个独立分组及 Pod/Node 不属于工作负载
- [x] 3.14 为资源表格视觉接线编写失败测试，覆盖复用 `CustomTable`、small 密度、资产列表式工具栏与分页，以及不启用选择和字段设置
- [x] 3.15 为实例详情菜单顺序、资源列表单滚动容器和名称新标签页跳转编写失败测试
- [x] 3.16 为移除采集事实和 X6 画布编写失败测试，覆盖 DIV 五列、SVG 关系线、共享滚动、连线重算、既有聚焦与右键/键盘交互

## 4. 前端实现

- [x] 4.1 在 `k8s_cluster` 实例详情增加与「基础信息」「关联关系」「变更记录」并列的一级「资源详情」入口，并验证其他模型不显示
- [x] 4.2 实现独立资源详情容器与二级资源导航，维护 `sub`、展开 Workload 集合和刷新状态，不注册未实现页签、空白路由或占位文案
- [x] 4.3 实现初版概览指标、采集事实和基础拓扑，并在列表切换期间保留概览状态；采集事实展示最终由 4.18 移除
- [x] 4.4 实现多 Workload Pod 分支状态机、最多四请求队列、取消或忽略迟到响应及会话缓存
- [x] 4.5 实现每分支 50 个 Pod 的分页加载、已加载/总数提示和完整列表入口
- [x] 4.6 将 Pod 增量关联到既有唯一 Node，并实现三种关系异常虚拟节点和未归属 Pod 聚合入口
- [x] 4.7 实现 Namespace、Workload 分类、Pod、Node 严格只读资源列表与关联过滤，仅保留搜索、筛选、刷新、分页和实例详情跳转
- [x] 4.8 实现 Namespace、Workload、Pod、Node 固定业务列配置和缺失值展示，不配置无可靠来源字段
- [x] 4.9 实现初版 X6 五列拓扑、图例与画布控制；X6 和画布控制最终由 4.18 替代
- [x] 4.10 实现节点单击聚焦、画布清除聚焦、只读右键上下文菜单及菜单键/`Shift+F10` 键盘等价操作
- [x] 4.11 实现 Namespace、Workload、Node 分层“展开更多”、已展示/总数提示、稳定追加和父节点完整性处理
- [x] 4.12 实现 220px/56px 二级资源导航、内容区不足 1100px 自动折叠、覆盖式展开和会话状态保持
- [x] 4.13 补齐中英文文案、加载/空态/错误/重试状态和无障碍标签
- [x] 4.14 运行前端定向测试并重构重复状态与图数据转换逻辑，确认关键交互均有行为测试
- [x] 4.15 将资源二级导航调整为工作负载、Pod、Node 独立分组，并补齐中英文分组文案
- [x] 4.16 将全部 K8S 资源列表切换到资产管理实例列表的 `CustomTable` 视觉底座，移除额外卡片包裹并保持严格只读
- [x] 4.17 将「资源详情」移动到「关联关系」之前，按父容器计算表格高度，并以新标签页打开资源实例基础信息
- [x] 4.18 从概览移除采集事实，将 X6 拓扑替换为 DIV 五列与无交互 SVG 关系层，并保留既有只读交互

## 5. 联调与验收

- [ ] 5.1 联调小集群首屏，确认统计、DIV 基础拓扑和导航列表口径一致
- [ ] 5.2 联调单个 Workload 超过 50 个 Pod 及多个 Workload 同时展开，确认分页、队列和节点稳定性
- [ ] 5.3 使用部分子资源权限账号验证指标、拓扑、列表和虚拟无权限节点不泄露名称或精确数量
- [ ] 5.4 验证未归属 Pod、未调度、Node 未匹配、零资源和最近采集错误等降级场景
- [ ] 5.5 执行 `cd server && make test` 和后端 lint，记录结果
- [ ] 5.6 执行 `cd web && pnpm lint && pnpm type-check`，记录结果
- [ ] 5.7 按规格逐项复核验收场景并记录手工走查结果
