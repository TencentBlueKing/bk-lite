# 运营分析通用关系拓扑 TopologyMap MVP

Status: implemented

## Problem Statement

运营分析模块已有稳定的网络领域场景组件 `networkStatusTopology`，但 AD、Exchange、SQL Server HA / AG、Oracle RAC、应用依赖等运营分析场景还缺少一个只负责展示实体、实体关系与当前告警状态的通用只读拓扑 Widget。

这些场景的业务语义和上游取数方式不同，但展示输入可以收敛为标准 graph payload：DataSource 决定展示哪些节点、节点间如何连接以及节点当前告警摘要；Widget 只负责校验、布局和展示。MVP 不应把领域 Projection、CMDB 查询、告警 enrichment 或拓扑编辑能力带入 Renderer，也不应为了复用而重构已稳定运行的 `networkStatusTopology`。

## Solution

新增普通运营分析 `chartType: topologyMap`，通过现有 DataSource 取数链路直接消费：

```text
DataSource
  → valueConfig.dataSource
  → widgetDataRenderer
  → get_source_data
  → { nodes, edges }
  → topologyMap validator / normalizer
  → TopologyMap X6 viewer
```

`topologyMap` 在 MVP 中放入 WidgetSelector 的“数据组件”，不新增或修改 `sceneWidgetType`。组件提供：

- 通用实体卡片节点；
- 实体关系线及六种线型组合；
- 节点告警数量与 0/1/2 等级视觉；
- 一种默认自动布局；
- zoom、pan、fit 和画布尺寸响应；
- loading、empty、error 与报告渲染终态；
- Dashboard、Screen、share 和报告渲染链路中的普通 Widget 行为。

## User Stories

1. 作为运营分析画布搭建者，我希望选择声明支持 `topologyMap` 的 DataSource，并把其 graph payload 展示为关系拓扑，从而不必为每个业务域开发专用拓扑 Widget。
2. 作为看板使用者，我希望在同一节点上看到实体名称、模型名称、可选副标题和当前告警数量，从而快速识别实体及健康风险。
3. 作为看板使用者，我希望通过实线/虚线与无箭头/单箭头/双箭头区分关系视觉，从而阅读由上游定义的关系方向，但不要求 Renderer 理解关系业务含义。
4. 作为看板使用者，我希望没有坐标的 chain、tree、cyclic 和 disconnected graph 都能自动形成稳定、可读的布局。
5. 作为报告订阅用户，我希望合法空拓扑作为空状态成功完成渲染，而不是让 PDF 报告失败或一直等待。
6. 作为维护者，我希望 `topologyMap` 与 `networkStatusTopology` 完全隔离，从而不扩大网络专用组件的回归范围。

## Product and Architecture Decisions

### Widget seam

- `topologyMap` 是普通 DataSource 驱动的 `chartType`，不是 Scene Widget。
- MVP 在 WidgetSelector 中归入“数据组件”；不修改 Scene Widget 分类、`SCENE_WIDGETS` 或 `SceneWidgetType`。
- DataSource 的 `chart_type` 可选择 `topologyMap`；Widget 配置抽屉只在所选 DataSource 声明支持该类型时展示它。
- `valueConfig` 只需保存既有字段 `chartType: "topologyMap"`、`dataSource` 及现有通用参数/筛选绑定；MVP 不新增 `valueConfig.topologyMap` 配置块。
- NATS 下游仍使用平台既有成功响应 envelope；其中 `data` 直接为 `{ nodes, edges }`。TopologyMap contract 本身不再增加 envelope，也不要求 `rows` / `columns`。
- MVP 的 graph object contract 首先面向 NATS DataSource。现有 mysql、postgresql、rest_api connector 和 excel runtime 主要输出统一的 `items[]`，本阶段不要求它们适配 `{ nodes, edges }`，也不为此修改 connector runtime。
- “TopologyMap 由 DataSource 驱动”不表示 MVP 要让所有 `source_type` 都支持 graph payload。沿用现有 `chart_type` 声明机制：只有实际能够返回 graph object 的 DataSource 才声明 `chart_type=topologyMap`；不新增 source-type capability framework。
- `field_schema` 可为空；MVP 不扩展平面 `field_schema` 来描述嵌套 graph。
- 不新增 backend handler、专用 API、数据库模型或 migration。

### Responsibility

TopologyMap 只负责：

- 校验和归一化 graph payload；
- 节点与关系展示；
- 节点告警摘要视觉；
- 默认自动布局；
- 基础 Viewer 交互和渲染生命周期。

TopologyMap 不理解 SQL Server、Oracle、Exchange、AD、CMDB relationship、Primary / Secondary、DAG、RAC、replication 或 application dependency，不根据这些业务类型执行 Projection 或特殊渲染。

### NetworkStatusTopology isolation

- 不修改 `networkStatusTopology` 的 API、Scene Widget 接入、配置 schema、CMDB BFS、interface projection、hop 布局、故障路径、节点视觉、布局持久化或交互。
- TopologyMap 不导入 `networkStatusTopology` 私有 graph model、status palette、node shape 或 layout config。
- 可参考其 X6 生命周期、badge 数量格式、critical pulse、resize/dispose 经验；只有已经天然独立且不携带网络业务语义的纯 helper 才允许直接复用。
- 若复用要求先重构 `networkStatusTopology`，MVP 必须保持独立实现。

## Data Contract

正式 TypeScript 数据契约如下；字段名是 wire contract，不在 Renderer 中提供字段映射：

```ts
interface TopologyMapPayload {
  nodes: TopologyMapNode[];
  edges: TopologyMapEdge[];
}

interface TopologyMapNode {
  id: string;
  instance_id: string | number;
  instance_name: string;
  model_name: string;
  subtitle?: string;
  alert_count: number;
  alert_level?: string;
}

interface TopologyMapEdge {
  source: string;
  target: string;
  label?: string;
  line_style?: 'solid' | 'dashed';
  connection_type?: 'none' | 'single' | 'double';
}
```

### Node identity

- `id` 是 graph-local identity，必须是非空 string，并在当前 payload 的 `nodes` 内唯一。
- Edge 的 `source` / `target` 只引用 `node.id`。
- `id` 必须由 DataSource 提供；validator 不使用 `instance_id`、`model_name` 或展示名称构造 composite id。
- `instance_id` 是上游实体标识和展示数据，不承担 graph identity；TopologyMap 不假设它跨模型或跨数据源全局唯一。
- MVP 不增加 `model_id`。TopologyMap 不访问 CMDB，也不提供实例详情下钻，当前没有稳定 identity 或交互需要它。

### Node content

- `instance_name` 是必填非空主标题。
- `model_name` 是必填非空模型展示名称，只用于展示。
- `subtitle` 是可选辅助文本；空白 string 归一化为缺失。
- 不增加 role、IP、RPO、status、severity、color、pulse 等专用字段。
- 节点使用固定、通用实体卡片视觉，不使用网络设备 icon + 72×72 节点视觉。
- 长标题、模型名和 subtitle 必须安全省略并提供完整文本访问方式；badge 不得遮挡正文。
- subtitle 缺失时调整卡片内部排版，不要求改变节点外部尺寸，避免破坏布局稳定性。

### Alert summary

- `alert_count` 必填，必须为大于等于 0 的有限整数。
- `alert_count === 0` 表示明确无告警：隐藏 badge，忽略存在的 `alert_level`，不引入 `normal` level，也不显示绿色健康 badge。
- `alert_count > 0` 时显示数量；1–99 显示实际数量，超过 99 显示 `99+`。
- `alert_level` wire type 为 string。MVP 只识别：
  - `"0"`：严重 / Critical；
  - `"1"`：错误 / Error；
  - `"2"`：警告 / Warning。
- 其他 string 或 `alert_count > 0` 时缺失 `alert_level` 均按 unknown 容错；继续显示原告警数量，使用中性 badge，不显示 `?`，不显示绿色正常。
- unknown 容错不代表 MVP 支持平台动态告警等级体系。
- Critical 与 Error 第一版使用 error/danger 语义色；Critical 在浏览器态可以 pulse，但 pulse 不能成为唯一差异，必须同时存在一种能在 Dashboard、Screen、Share 和 PDF 静态输出中辨识的最小静态特征。实现阶段根据现有 Design Token 选择 badge 外环、border、stroke、opacity/tonal difference 等最简单方式。
- Error 不 pulse；Warning 使用 warning 语义色；unknown 使用 neutral/secondary 语义视觉并继续显示真实数量。
- 静态差异要求不新增 wire contract 字段、alert icon 系统、全局状态体系、动态 Level metadata provider 或全局 `AlertVisualResolver`。
- 新视觉必须使用 `web/src/styles/globals.css` 的 Design Token / CSS variables 或 Ant Design token，支持 light/dark theme；不得复制 `networkStatusTopology` 私有 hardcoded palette。
- MVP 不依赖 Alarm 页面专属 `CommonContext`、`levelMap` 或 `getLevelMeta`，不新增全局 `AlertVisualResolver` 或 Alert metadata 请求。

### Edge visual

- `line_style` 默认 `solid`，支持 `solid | dashed`。
- `connection_type` 默认 `none`，支持：
  - `none`：无箭头；
  - `single`：`source → target`；
  - `double`：`source ↔ target`。
- 两个正交字段形成六种线型；不新增六值 `line_type` enum。
- `label` 可选，空白 string 归一化为缺失。
- A→B 与 B→A 可以同时存在；它们是两个方向不同的 edge，不得强制合并或转换成 `double`。
- MVP 以 normalized 后的 `source + target` 作为 Edge 结构唯一性约束。同一方向 A→B 只允许一条 Edge；第二条相同 `source + target` 的 Edge 是 graph integrity error，不因 label、`line_style` 或 `connection_type` 不同而放行。
- A→B 与 B→A 的端点顺序不同，因此可以同时存在且不合并；`connection_type=double` 表示单条双向视觉关系，而 A→B 与 B→A 表示两条独立方向关系。
- 同向多 Edge、parallel edge routing 和 label offset 不属于 MVP；Renderer 不实现 parallel edge offset。
- MVP wire contract 不要求 edge `id`；Renderer 在校验后生成稳定、唯一的内部 cell id。若未来出现边选中、编辑、持久化或跨刷新引用需求，再单独评估把 edge id 加入 wire contract。
- 不增加 edge alert、health、业务 relation type、颜色、宽度或动画字段。

### Self-loop

- Self-loop（A→A）在 graph 概念上不定义为业务非法，但不属于 TopologyMap MVP 的显式支持与验收范围。
- Validator 不因业务语义直接声称 self-loop 是非法关系；MVP 不要求专门实现 X6 loop router、fixture 或 renderer test。
- 如果当前 X6 + Dagre 默认能力能够自然显示，可以保留自然行为；如果不能可靠显示，实施阶段必须明确记录为当前限制 / Future Consideration，不得静默丢弃数据，也不得为了支持它扩大 MVP。

## Validation and Normalization

### Result states

1. 整体 payload 无法解析：Widget error。
2. `{ nodes: [], edges: [] }`：合法 empty，显示统一空状态。
3. 合法非空 graph：进入布局和渲染。
4. 请求、权限或 DataSource 缺失错误：沿用 `widgetDataRenderer` 既有错误体系，不由 TopologyMap 重定义。

### Payload validation

- payload 必须是非数组 object，且 `nodes`、`edges` 都必须是数组。
- Node 非 object、缺少必填字段、`id` 为空或重复、`instance_name` / `model_name` 为空、`alert_count` 非法：整体结构错误。
- `instance_id` 必须是 string 或 number；空 string 非法。
- Edge 非 object、`source` / `target` 为空、引用不存在的 node、线型字段非法、同向 `source + target` 重复：整体结构错误。
- isolated node 合法。
- A→B 与 B→A 同时存在合法。
- self-loop 不因业务语义被 validator 直接拒绝，但其可靠显示不属于 MVP 验收范围。
- unknown `alert_level` 合法并按中性 badge 容错。
- 可选文本可 trim；空白 subtitle/label 归一化为缺失。
- Graph identity 或 referential integrity 错误不得通过 skip 坏行来掩盖，因为静默删除节点/边会生成另一张看似正确但业务事实错误的拓扑。
- Validator 返回归一化后的 typed graph 或一个可展示错误；Renderer 不重复维护第二套结构判断。

### Scale protection

- 节点/边规模是 MVP 的真实性能风险，但当前不凭经验写死阈值。
- 性能不作为 MVP 的硬性 benchmark 或 completion gate；不要求正式 performance fixture。
- 实施阶段可以使用代表性 graph 做基本 sanity verification，观察 Dagre layout、X6 首次渲染和 zoom/pan 是否存在明显卡顿。
- 只有发现真实性能问题时，才记录并回报数据规模、现象及 layout/render 耗时，再决定是否加入节点/边限制。
- 本 Spec 不设固定阈值，不允许静默截断，也不允许未经产品确认加入 `node_limit` / `edge_limit`。

## Layout and Canvas Interaction

### Default layout

- MVP 只保留一种内部默认自动布局，不暴露 layout mode、方向或间距配置。
- 使用 Web 已有依赖 `@antv/layout` 的 `DagreLayout`，以有向 layered layout 为内部实现。
- 产品和持久化配置不出现 `hierarchical` mode；实现选择不形成可切换布局 interface。
- 默认布局必须稳定处理并测试：chain、tree、cyclic、disconnected graph、A→B 与 B→A，以及 isolated node。
- 布局不要求 center、root、hop 或 position 输入，不读取任何领域字段。
- Dagre 可以使用 Edge 的 `source` / `target` 进行 layered layout 计算，但二者首先只是 graph edge 的结构端点。是否向用户表达方向只由 `connection_type` 控制；例如 `source=A, target=B, connection_type=none` 可以按 A→B 参与布局，但最终必须渲染为无箭头的 A——B。
- `source` / `target` 不表示业务领域 relationship type，Renderer 不得因为 Dagre 使用 directed input 而擅自显示箭头。
- DataSource 不提供 position；所有位置由 Renderer 计算，也不写回 DataSource 或 `valueConfig`。
- 布局方向、节点间距和边间距是 Renderer 内部常量，以卡片尺寸、label 和可读性为依据。

### Viewer interaction

- 支持 mousewheel zoom、pan 和显式 fit view。
- fit view 只在首次有效 graph 完成布局、graph identity 发生变化或用户主动点击 fit 时执行。这里的 graph identity 只由 node id 集合和 edge 结构决定；告警数量、告警等级或展示文本刷新不得重置用户视口。
- 容器 resize 必须更新 X6 canvas 尺寸，但不得在每次 resize 后无条件 zoomToFit，以免重置用户已有 zoom/pan。
- 节点可使用 X6 原生拖动做当前会话内的临时摆放；不持久化、不新增 reset layout，不把 Viewer 变成 Editor。
- 不允许新建、删除、重连或编辑节点/边；不显示端口、selection tools、context menu 或 minimap。
- Graph、observer、事件监听和布局实例在卸载或数据重建时必须正确释放；迭代型布局若被引入必须显式 stop，但 MVP 默认 DagreLayout 不依赖持续模拟。

## Renderer and Theme

- 在运营分析 app 内新增 TopologyMap Widget 和 app-local node shape；不晋升 `web/src/components` shared。
- 优先使用 X6 SVG node shape，避免把 Ant Design Card DOM、编辑器端口或领域组件带入 graph model。
- 节点显示 `instance_name`、`model_name`、可选 `subtitle` 和 alert badge。
- 颜色不是唯一告警载体：Critical 除浏览器态 pulse 外还必须具有最小静态可辨识特征；badge 中始终保留告警数量。
- 普通、warning、error、critical 和 unknown 状态必须在 light/dark 下保持文字、边框、badge 和连线对比度。
- 画布 empty 使用现有 Ant Design/Widget empty pattern；格式错误使用 Widget 统一 error state。
- Renderer 必须响应数据切换、主题切换和容器尺寸变化，不因 resize 重置用户视口。

## Runtime, Surface and Persistence Integration

- Dashboard runtime registry 注册 `topologyMap`。
- DataSource `ChartType`、`getChartTypeList()`、WidgetSelector label、配置抽屉选项、submit/serialization 和中英文 i18n 必须同步。
- Screen 同步加入 `ScreenWidgetChartType` 与 `SCREEN_WIDGET_DEFINITIONS`，提供适合关系图的默认尺寸；`topologyMap` 不是 Screen-only 类型。
- `chartTypeSurface` 不新增限制：TopologyMap 同时允许 Dashboard 和 Screen。
- Dashboard/Screen `view_sets` 只透传既有 `valueConfig`；无 migration，无 topologyMap 专属持久化 schema。
- share 链路按普通 DataSource Widget 透传，不新增 share 后端分支。
- Dashboard/Screen 报告 manifest 继续收集 `widget_type` 与 `datasource_id`，不新增 topologyMap 特判。
- 如果 Storybook family 同时使用另一套 ops-analysis widget registry，只在真实 fixture 接入该 family 时同步注册；运行时唯一事实仍以 Dashboard 使用的 `widgetRegistry.ts` 为准。

## Loading, Empty, Error and Report Ready Contract

- `onReady(boolean)` 的 boolean 沿用现有语义：表示 `hasData`，不是“渲染流程是否完成”。
- 合法非空 graph 在数据校验、Dagre 布局、X6 首轮 graph render 完成后调用 `onReady(true)`。
- 合法 empty graph 在空状态完成渲染后调用 `onReady(false)`。
- Widget `empty` 是报告 terminal success；`ready` 和 `empty` 都允许整体产生 `report-ready`，只有 `failed` 产生 `report-failed`。
- 当前通用 empty 判定会把 `{ nodes: [], edges: [] }` 误认为有可渲染数据。TopologyMap 接入必须选择与现有 Widget empty contract 一致、改动范围最小的 seam 修复结果，使该 payload 最终显示 empty、调用 `onReady(false)`、上报 `status: empty` 并允许报告 `report-ready`。Spec 不锁定必须修改某个具体 helper。
- 不得用 `onReady(true)` 伪装有数据，不得省略 onReady，也不得让状态持续 loading。
- 请求未 settled、布局未完成或 X6 首轮 render 未完成时不得提前上报 terminal 状态。
- 合法 empty graph 必须在 Dashboard PDF 和 Screen PDF 中成功结束等待并生成报告。

## Testing Decisions

测试验证外部行为和稳定 seam，不锁定 X6 内部 DOM 层级或私有事件名。

### Pure contract tests

- 合法 payload 归一化。
- `{ nodes: [], edges: [] }` 合法 empty。
- Node 必填字段、graph-local id 唯一、`alert_count` 非负整数。
- Edge referential integrity、非法 enum、同向 `source + target` 重复。
- A→B 与 B→A 同时存在合法，且不转换为 double。
- isolated node 合法。
- alert level 0/1/2、unknown/missing + count>0、count=0 忽略 level。
- 默认 `line_style=solid`、`connection_type=none`。

### Layout tests

- 使用真实 `DagreLayout` 或其外部 adapter seam 验证 chain、tree、cyclic、disconnected、isolated、反向双边均产生有限且不完全重叠的节点坐标。
- 同一输入重复布局的节点坐标稳定。
- 布局输入不需要 root、center、hop、model 或业务字段。

### Renderer tests

- 节点主标题、模型名、可选 subtitle 和长文本行为。
- alert_count 数量与 99+；0 隐藏 badge。
- Critical 浏览器态可 pulse 且具有静态可辨识特征、Error 不 pulse、Warning 警告色、unknown 中性 badge 且继续显示数量；Dashboard、Screen、Share 和 PDF 静态输出中 Critical 与 Error 可区分。
- 六种 edge visual；A→B、B→A 各自保留。
- empty/error/loading 状态。
- light/dark token 行为。
- 首次 graph render 后才 onReady；resize 更新 canvas 但不重置用户 zoom/pan；主动 fit 有效。

### Focused integration test

至少新增一个覆盖真实接入 seam 的 focused integration test：

```text
DataSource payload
  → widgetDataRenderer
  → topologyMap validator
  → topologyMap renderer
  → onRenderStatus
```

该测试至少覆盖：

1. 合法非空 `{nodes, edges}` 最终上报 `ready`；
2. 合法 `{nodes: [], edges: []}` 最终上报 `empty` 而不是停留在 `loading`；
3. empty 作为 terminal status 参与 `buildDashboardRenderSignal` 后产生 `report-ready`；
4. 非法 graph integrity 不进入 Renderer，显示运营分析既有数据格式错误 UI，通过 `onRenderStatus` 上报 `failed`，不得停留在 `loading`，PDF/report 不得无限等待；
5. DataSource payload 对象未被 Widget 取数链路改写为 rows/columns。

不新增真实 backend handler；测试使用现有 DataSource API seam 的 mock/fake response。

### Fixtures and visual verification

- Storybook/test fixtures 至少包含三种业务无关结构：
  - chain：A → B → C；
  - cyclic/mesh：A ↔ B、A ↔ C、B → C，可用两条反向 edge 或 double visual 分别覆盖不同 contract；
  - tree：A → B、A → C。
- fixtures 额外覆盖 disconnected/isolated node、subtitle 缺失、无告警、0/1/2/unknown level、实线/虚线、无/单/双箭头。
- Storybook 分别检查 light/dark、长文本、窄/宽容器、empty 和 error。
- 性能只做可选 sanity verification，不要求正式 benchmark fixture；发现真实问题后再记录证据并回报。

## Acceptance Criteria

1. 声明支持 `topologyMap` 的 DataSource 可在“数据组件”路径创建 Widget，保存后仍保留 `chartType` 与 DataSource 绑定。
2. NATS DataSource 返回的 `{nodes, edges}` object 能原样进入 topologyMap validator，无额外 graph envelope 或 rows/columns 转换。
3. 同一 Renderer 能正确展示 chain、cyclic/mesh、tree、disconnected 和 isolated graph，不读取领域类型做 Projection。
4. Node 以 graph-local `id` 关联 Edge；不同节点不能因 `instance_id` 或展示名称相同而冲突。
5. `alert_count` 必填并正确显示；0/1/2 与 unknown fallback 符合本 Spec，unknown 不显示绿色或问号；Critical 与 Error 在动态界面及静态输出中均可区分。
6. 六种 edge visual 正确；默认无箭头；A→B 与 B→A 不被合并；相同 `source + target` 的第二条 Edge 被拒绝；不实现同向 parallel edge routing。
7. Dagre 默认布局稳定处理目标 graph 结构，不要求 root/center/hop，不暴露布局模式配置；`connection_type=none` 的 Edge 不因 directed layout 自动出现箭头。
8. zoom、pan、fit 可用；resize 不无条件重置用户视口；节点临时拖动不持久化。
9. 合法 empty graph 显示空状态、上报 `empty` terminal status，并允许 Dashboard/Screen 报告产生 `report-ready`。
10. 非法 graph 显示既有数据格式错误 UI、上报 `failed` terminal status，且报告不无限等待。
11. Dashboard、Screen、share、PDF render、theme 和 i18n 接入没有 chartType 白名单遗漏。
12. `networkStatusTopology` 的代码、配置、API、视觉和行为保持不变。

## Out of Scope

- CMDB model → instance → depth 自动展开
- CMDB relationship 通用查询
- cascading DataSource 参数
- Topology Projection framework
- SQL / AD / Exchange / Oracle adapter 或专用 backend capability
- backend handler 数量治理
- Alert enrichment pipeline、动态 Level metadata 或全局 AlertVisualResolver
- 一个 Widget 多 DataSource join
- Edge health、Edge alert、Edge animation、业务 relation type
- 同向多 Edge、parallel edge routing、parallel label offset
- Groups、lanes、cluster、architecture layer、legend、annotation、template
- 节点详情下钻、告警列表跳转、右键菜单、fault path
- minimap、多布局切换、layout mode、layout persistence、reset layout
- topology editor、新建/删除/重连节点或边
- 用户自由配置节点/边颜色、线宽、尺寸或布局参数
- `networkStatusTopology` 重构或通用化
- 真实 SQL Server、AD、Exchange、Oracle backend handler 或内置业务画布
- 未经性能证据与产品确认的固定节点/边阈值或静默截断
- mysql、postgresql、rest_api connector、excel 的 graph object contract 适配
- Self-loop 的专门 routing、fixture、renderer test 和显式验收承诺

## Further Notes

- “通用”指 Renderer 不理解业务语义，不表示第一版建立跨 App shared graph engine。TopologyMap 归运营分析 app-local 所有。
- `instance_id`、`instance_name`、`model_name` 是上游实体摘要；只有 `id` 是当前 graph 的引用 identity。
- `connection_type` 描述线条 marker 视觉；它不声明业务关系类型。即使 `connection_type=none`，`source` / `target` 仍用于 graph identity、布局和数据方向。
- unknown alert level 是安全容错，不是动态等级能力承诺。
- Self-loop（A→A）在 MVP 中不因业务语义被 validator 拒绝，也不会被静默删除。当前默认 X6 edge（无专用 loop router / loop fixture）不能可靠地形成可见自环，因此记为 **Current Limitation / Future Consideration**：本阶段不增加 loop routing、正式 self-loop 验收或 Acceptance Criteria 扩大。
- 若实施证据推翻 Dagre 稳定性或暴露真实性能问题，必须先更新本 Spec 并取得确认，不得通过静默降级或截断改变数据事实。

## Implementation Evidence

- 普通 DataSource / `chartType` 注册：`web/src/app/ops-analysis/{types/dataSource.ts,constants/common.ts,components/widgetSelector.tsx,components/widgetRegistry.ts}`。
- graph contract、结构校验、默认值与 Dagre 布局：`web/src/app/ops-analysis/utils/topologyMapData.ts`。
- X6 viewer、告警静态/动态视觉、edge marker、fit/zoom/pan、resize 与临时拖动会话策略：`web/src/app/ops-analysis/components/widgets/topologyMap/`（含 `topologyMapViewerSession.ts`）。
- empty / failed / report terminal contract：`web/src/app/ops-analysis/{components/widgetDataRenderer.tsx,utils/topologyMapWidgetContract.ts,renderContract.ts}`。
- Dashboard / Screen / Share / PDF 共用普通 Widget 渲染链路；Screen 注册位于 `web/src/app/ops-analysis/{types/screen.ts,(pages)/view/screen/constants/widgets.ts}`。
- 聚焦测试：`web/src/app/ops-analysis/{components/__tests__/widgetDataRenderer.topologyMap.test.tsx,utils/__tests__/topologyMapData.test.ts,utils/__tests__/topologyMapWidgetContract.test.ts,components/widgets/topologyMap/__tests__/topologyMapGraph.test.ts,components/widgetConfig/utils/__tests__/submitConfig.topologyMap.test.ts,constants/__tests__/chartTypeList.test.ts}`。
- Storybook fixtures：`web/src/stories/ops-analysis-widgets-family.stories.tsx`，覆盖 chain、tree、cyclic、disconnected、empty、invalid、light/dark 与长文本。
