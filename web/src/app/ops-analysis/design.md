# Ops Analysis UI/UE Design Guide

## Context

`ops-analysis` 是面向运营分析场景的工作台模块，当前主要包含：

- `view`：分析视图入口，承载 dashboard、topology、screen、architecture、networkTopology 等内容视图。
- `settings`：数据源、命名空间等基础配置。
- `components/unifiedFilter`：dashboard、topology、screen 等视图共享的统一筛选能力。
- `components/widgetConfig`：图表、表格、单值等组件的公共配置入口。
- `components/widgets`：dashboard、topology、screen 共享的图表和场景组件渲染资产。
- `utils/chartTheme.ts`：ops-analysis 图表视觉 token。

本模块的 UI/UE 目标不是营销展示，而是让用户在高信息密度下稳定完成查看、筛选、编辑、配置、保存和演示。

## Goals

- 沉淀 dashboard、topology、screen、architecture、networkTopology、settings 的共性页面模式。
- 明确统一筛选、图表配置、图表主题、画布编辑等公共能力的复用边界。
- 约束亮色 / 暗色主题下的基础视觉规则。
- 为后续新增页面、组件、节点、widget 提供实现前检查清单。
- 降低后续 AI 或开发者在 ops-analysis 中重复造 UI 模式的概率。

## Non-Goals

- 不作为每个组件的完整 props API 手册。
- 不替代 `specs/capabilities/` 的长期契约或 `specs/changes/` 的变更文档。
- 不要求一次性重构现有页面。
- 不规定所有内部 hook 的实现细节。
- 不改变现有后端接口、导入导出结构或数据源协议。

## Design Principles

### 工作台优先

页面首屏应直接呈现可操作内容：视图列表、工具栏、筛选区、画布、配置入口。避免大面积宣传式说明、装饰性区块或 hero 式布局。

### 查看态和编辑态分明

查看态突出数据消费，编辑态突出新增、拖拽、配置、保存、取消。编辑态按钮和危险操作需要清晰分组，避免保存、取消、删除、刷新处于相同视觉层级。

### 配置入口稳定

图表类配置优先复用 dashboard 的 `ViewConfig` 体系。topology 可以封装自己的节点配置流程，但不应复制一套独立图表配置模型。

### 筛选行为一致

`UnifiedFilterBar` 是 dashboard、topology、screen 的统一查询入口。筛选项配置、搜索、重置、命名空间选择应保持一致语义。

### 主题 token 优先

普通 UI 优先使用 `var(--color-bg-*)`、`var(--color-text-*)`、`var(--color-border-*)`。图表视觉优先通过 `getOpsChartTheme()` 获取，避免 widget 内散落硬编码颜色。

### 小范围演进

新增能力优先复用已有页面模式和公共组件。只有当现有边界无法表达新需求时，才增加新的薄封装或公共抽象。

## Information Architecture

推荐把 ops-analysis 理解为两层结构：

```text
ops-analysis
├── view
│   ├── dashboard
│   ├── topology
│   ├── screen
│   └── architecture
└── settings
    ├── dataSource
    └── namespace
```

`view` 是分析消费和画布编辑入口，`settings` 是支撑 view 的基础资源配置入口。view 页面不应承载复杂数据源建模流程，settings 页面也不应复制 view 的画布操作能力。

## Page Patterns

### Standard View Page

dashboard、topology、screen、architecture 的主视图优先遵循以下结构：

```text
OpsAnalysisProvider
└── View Page
    ├── Resource / View Selector
    └── Main Area
        ├── Toolbar
        ├── UnifiedFilterBar
        ├── Canvas / Content
        └── Config Drawer / Modal
```

这个顺序表达的是：先选择分析对象，再执行页面级操作，再应用筛选，最后查看或编辑内容。

### Toolbar

工具栏承担页面级动作，不承担单个 widget 或单个节点的内部配置。

适合放在工具栏的动作：

- 编辑 / 退出编辑
- 保存 / 取消
- 刷新
- 新增组件 / 新增节点
- 导入导出
- 全屏 / 演示
- 页面级配置入口

不建议：

- 在工具栏堆积单个 widget 的细粒度配置。
- 让刷新、保存、删除使用近似视觉权重。
- 在只读态展示编辑专属按钮。
- 把危险操作和常规操作混在一起。

### Unified Filter Area

`UnifiedFilterBar` 应放在 toolbar 下方、主内容上方。

约束：

- 有筛选项或命名空间选择时展示。
- 支持 `default` 和 `embedded` 两种外观。
- 搜索表示应用当前草稿值。
- 重置表示恢复默认值或空值，并触发查询。
- 筛选项配置入口只在编辑态出现。
- 筛选条不直接关心 dashboard、topology 或 screen 的具体刷新实现。

### Dashboard Canvas

dashboard 是 widget 编排和数据消费画布。

约束：

- 使用 grid 布局承载 widget。
- widget 卡片保持统一边框、背景、标题区、操作区。
- 分组是布局组织能力，不应改变 widget 数据契约。
- 编辑态允许拖拽、缩放、配置、删除。
- 查看态应降低操作噪音，优先展示数据。
- 空数据、加载、错误不应破坏卡片高度和布局稳定性。

### Topology Canvas

topology 是节点、连线、图表节点、单值节点的图形编辑和展示画布。

约束：

- 画布优先保障拖拽、缩放、连线、节点配置。
- 节点内图表应复用图表主题和取数配置。
- minimap、全屏、演示态属于画布辅助能力，不能遮挡主操作路径。
- 节点配置流可以有 topology 专属封装，但图表配置能力应尽量复用 dashboard 的 `ViewConfig`。
- 单个节点刷新不应导致整张拓扑明显闪烁。

### Screen Canvas

screen 是固定分辨率的大屏展示和汇报画布，用于总览、展示、汇报、值守，不承载拓扑建模语义。

定位：

- screen 面向“展示视图”，dashboard 面向“分析编排”，topology 面向“关系定位”。
- screen 可以复用 dashboard 已有图表、表格、单值、TopN、Gauge、事件表、轻量关系展示等组件，但不能把 dashboard 的普通卡片外观直接搬进大屏。
- screen 的科技感外观应在 screen 画布和 screen widget frame 内隔离实现，不污染 dashboard/topology 的组件样式。

约束：

- 固定分辨率是 screen 的基础能力，画布应按 `viewport.width / viewport.height` 等比缩放展示。
- 查看态优先隐藏编辑噪音，保留刷新、全屏、画布设置、编辑等页面级操作。
- 编辑态允许添加组件、拖拽、缩放、配置、删除、保存、取消；组件级操作收敛在组件右上角更多操作中。
- 拖拽应只更新当前拖拽组件的临时位置，松手后再同步到外层画布配置，避免拖动中全画布频繁重渲染造成延迟。
- resize 可以沿用组件级临时尺寸状态，保存前不应破坏进入编辑前的 snapshot。
- screen 不新增一套数据源配置模型，图表数据源和字段配置继续复用 `ViewConfig`。
- screen 不应为了某个数据源硬造新的组件类型；只有数据源配置明确支持的组件类型才允许被页面配置出来。
- screen 内置示例应来自页面可配置结果。为了调试快速生成的布局只能作为临时脚本或一次性数据，不应沉淀为业务预置常量或解析器。
- screen 的标题、时间、装饰线、背景、面板边框属于大屏 chrome，可以有专属视觉，但要服务信息层级，不能压过数据内容。
- 组件角框、选中态、拖拽把手应克制；编辑态要可操作，但不应出现强烈发光边框包围整屏。
- 大屏首屏应尽量饱满，优先使用 KPI 小卡、趋势、分布、TopN、表格、关系展示等组合形成稳定布局，避免大量空白或组件互相遮挡。

### Settings Pages

settings 页面优先服务基础资源配置。

约束：

- 数据源、命名空间等资源配置应采用表格、搜索、操作弹窗等常规管理页模式。
- 配置成功后应能被 view 页面统一消费。
- 不应在 settings 页面内复制 dashboard/topology/screen 的画布编辑体验。

## Theme Rules

### Theme Source

全局主题由 Ant Design `defaultAlgorithm` / `darkAlgorithm` 和 CSS variables 支撑。ops-analysis 不维护独立主题系统。

### Use CSS Tokens For Common UI

普通 UI 推荐使用：

```tsx
bg-(--color-bg-1)
bg-(--color-fill-1)
text-(--color-text-1)
text-(--color-text-2)
border-(--color-border-2)
```

避免：

- 大面积硬编码 `#fff`、`#f8fafc`、`#1f2329`。
- 只在亮色主题下成立的阴影和渐变。
- 暗色主题下仍使用高亮白背景卡片。
- 不经过主题 token 的文本、边框、填充颜色。

### Use Chart Theme For Charts

图表、tooltip、axis、splitLine、legend、单值卡颜色优先通过：

```ts
resolveOpsChartThemeName()
getOpsChartTheme(themeName)
```

约束：

- 坐标轴文字、分割线、tooltip 背景、tooltip 边框必须适配暗色。
- 图表面板背景使用 `panelBg`。
- 图表边框使用 `panelBorderColor`。
- 单值指标颜色和辅助文本使用 `singleValueColor` / `singleValueMetaColor`。
- 不在 `comLine`、`comBar`、`comPie`、`comSingle` 等 widget 内各自发明主题规则。

### Light Theme

亮色主题应保持清爽、克制、可扫描。

建议：

- 主背景使用 `var(--color-bg-1)` 或轻量中性背景。
- 面板边框优先使用 `var(--color-border-2)` 或 `chartTheme.panelBorderColor`。
- 阴影只用于强调浮层、拖拽态或卡片层级，不大面积堆叠。
- 图表网格线和坐标轴保持低对比，避免干扰数据本身。

### Dark Theme

暗色主题应保证层次和可读性，不只是反转颜色。

避免：

- 低透明白色叠加过多导致层级发灰。
- 蓝色主色和图表线条过亮造成刺眼。
- tooltip 阴影过重。
- grid、minimap、canvas 背景仍保留亮色渐变。
- 依赖纯黑 / 纯白形成强烈割裂。

topology 的 canvas 和 minimap 样式如果继续优化，应优先抽成基于 `.dark` 或 token 的双主题样式。

## Shared Component Boundaries

### `UnifiedFilterBar`

职责：

- 展示筛选控件。
- 维护本地草稿值。
- 触发 search / reset。
- 支持 `prefixContent` 注入命名空间等页面上下文控件。

不负责：

- 业务数据刷新。
- 节点遍历。
- widget reload。
- 接口调用。
- 保存筛选配置。

### `UnifiedFilterConfigModal`

职责：

- 配置筛选项定义。
- 管理筛选项排序、启用、默认值等配置。

不负责：

- 决定 dashboard/topology/screen 如何将筛选绑定到组件。
- 直接触发画布刷新。

### `ViewConfig`

职责：

- 图表、表格、单值等组件的数据源与展示配置。
- 承载字段、阈值、表格列、TopN、Gauge 等配置分区。

复用要求：

- dashboard widget、topology 图表节点和 screen widget 应共享它。
- 新增图表配置能力时，优先判断是否属于 `ViewConfig`。
- 不为 topology 复制独立图表配置模型。

### `chartTheme`

职责：

- 提供 ops-analysis 图表视觉 token。
- 统一亮色 / 暗色下图表、tooltip、legend、单值卡的颜色和层级。

复用要求：

- 新增图表类型必须优先接入。
- 新增图表视觉 token 应集中扩展在 `utils/chartTheme.ts`。

### Widget Components

职责：

- 根据 `ValueConfig` 和数据渲染图表内容。
- 处理自身加载、空态、错误态。
- 允许根据外层场景接收轻量展示上下文，例如 dashboard/topology/screen 的容器风格差异。

不负责：

- 页面级编辑模式。
- 保存逻辑。
- 筛选配置弹窗。
- dashboard/topology/screen 的资源同步。

复用要求：

- dashboard、topology、screen 共用的图表渲染资产应放在 shared widget 层，不应长期放在某个单一页面目录下。
- screen 需要的内置科技风面板样式应由 screen frame 或 screen 专属 class 包裹，不应改写共享 widget 的默认外观。
- 共享 widget 只能表达数据和通用状态，不能内置 screen 专属布局坐标、标题装饰、背景纹理。

### Topology Node Config

topology 可以保留专属节点配置面板，例如形状节点、边配置、单值节点配置等。

约束：

- 只要涉及图表数据配置，应尽量进入 dashboard 已有配置体系。
- 节点外观、位置、边样式可以由 topology 独立管理。
- 节点配置流程可以薄封装，但不应引入新的图表配置事实来源。

## Interaction State Rules

### Draft / Applied / Snapshot

筛选、配置、编辑流程需要区分三类状态：

- `draft`：用户正在编辑但尚未搜索或保存。
- `applied`：已经应用到数据刷新或画布展示。
- `snapshot`：进入编辑前的可恢复状态。

不要求所有模块立即 reducer 化，但新增复杂流程时应显式考虑这三类状态，避免草稿态和已应用态混在一起。

### Save / Cancel

编辑态必须有明确退出方式。

- 保存：持久化当前配置。
- 取消：恢复进入编辑前状态。
- 只读对象：不能进入破坏性编辑流程。
- 保存中应禁用重复提交或给出明确 loading。

### Loading

- 页面级加载用于首次进入、切换对象、全量拉取。
- widget / 节点级加载只影响自身。
- 刷新单个节点不应阻塞整个画布。
- 自动刷新不应制造明显闪烁。

### Empty

空态需要给出下一步动作。

示例：

- 无 dashboard：提示创建或选择 dashboard。
- 无 widget：提示新增组件。
- 无 topology 节点：提示从左侧拖入节点。
- 无数据源：引导到数据源配置。

### Error

错误态需要区分：

- 数据源请求失败。
- 参数配置不完整。
- 无权限。
- 数据为空。
- 渲染异常。

不建议统一只显示“暂无数据”。

### Permission

权限不足时应隐藏或禁用编辑、删除、保存等破坏性动作。只读态可以保留查看、筛选、刷新等非破坏性动作。

## Visual Rules

### Radius

普通卡片、筛选区、工具栏建议保持 8px 左右圆角。画布节点和按钮遵循现有 AntD / Tailwind 风格即可，避免过度圆角导致工作台显得轻浮。

### Shadow

阴影需要克制。图表卡片可以轻阴影，编辑拖拽态可增强，但不要大面积使用强浮层阴影。

### Buttons

- 主按钮用于主要确认动作，如保存、搜索、新增。
- 次按钮用于取消、重置、普通操作。
- 删除等危险动作需要 Popconfirm 或明确危险态。
- 工具按钮优先图标 + tooltip。
- 长文本按钮只用于明确命令，不用于密集工具区。

### Text

- 页面标题使用中等尺寸，避免 hero 级大字。
- 卡片标题建议 14px 左右，单行截断。
- 辅助说明建议 12px 左右，颜色使用 `text-2` / `text-3`。
- 说明文字不应占据主要操作区。

### Editable Mapping Tables

参数映射、字段映射等密集编辑表格应把新增和删除收敛到行内操作列：

- 正常行的操作列优先展示 `+` / `-` 图标按钮，`+` 表示在当前行后插入一行，`-` 表示删除当前行。
- 不再为“添加参数映射”单独占用一整行，避免在密集配置区制造额外视觉噪音。
- 当映射列表为空时，展示一行轻量空态，占位文案跨过主要字段列，操作列只保留 `+` 图标按钮。
- 图标按钮应使用 AntD `Button type="text"` 或现有同类图标按钮样式，并保持 tooltip 或可理解的上下文。

### Chart Panels

- 标题、操作、图表内容分区稳定。
- 图例、tooltip、坐标轴遵守主题。
- 空数据和错误不能破坏卡片高度。
- 导出 PDF 时隐藏不该导出的操作按钮。

## Key Files

- `web/src/app/ops-analysis/(pages)/view/layout.tsx`
- `web/src/app/ops-analysis/(pages)/view/page.tsx`
- `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx`
- `web/src/app/ops-analysis/(pages)/view/topology/index.tsx`
- `web/src/app/ops-analysis/(pages)/view/screen`
- `web/src/app/ops-analysis/components/unifiedFilter`
- `web/src/app/ops-analysis/components/widgetConfig`
- `web/src/app/ops-analysis/components/widgets`
- `web/src/app/ops-analysis/components/widgetRenderer.tsx`
- `web/src/app/ops-analysis/utils/chartTheme.ts`
- `web/src/app/ops-analysis/context/common.tsx`

## Decisions

### D1: Document As A Module-Level Design Guide

本文件是 ops-analysis 的长期 UI/UE 约束文档，不是某一次具体需求的实现设计。

### D2: Prefer Reuse Over Parallel UI Models

dashboard、topology、screen 共享筛选、图表配置、图表主题等能力。新增能力优先扩展共享层，而不是在单个页面复制一套平行模型。

### D3: Keep Theme Rules Centralized

普通 UI 使用全局 CSS variables，图表使用 `chartTheme`。只有节点画布、第三方图形引擎等特殊场景可以局部补充样式，但需要同时考虑亮色和暗色。

### D4: Keep Product States Explicit

编辑、筛选、保存等流程应明确区分 draft、applied、snapshot。复杂流程可以逐步收敛实现，不要求一次性重构。

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| 文档过泛，后续实现仍然各做各的 | 保持 checklist 和 anti-patterns，代码评审时引用具体条目 |
| 文档过细，跟随代码变化很快过期 | 不写完整 props 手册，只写稳定模式和边界 |
| topology 有特殊画布需求，难以完全复用 dashboard 模式 | 允许 topology 保留节点/边/画布专属封装，但图表配置和筛选语义尽量共享 |
| screen 需要强视觉风格，容易污染共享 widget | screen 外观集中在 screen canvas/frame，widget 只暴露必要场景 class |
| screen 固定分辨率编辑容易产生拖拽延迟 | 拖拽中只更新单组件本地临时几何，松手后同步配置 |
| 暗色主题在第三方画布和图表中适配不完整 | 优先通过 `chartTheme` 和 token 收敛，特殊样式集中处理 |

## Implementation Checklist

新增或修改 ops-analysis UI 前，应检查：

- 是否复用 `OpsAnalysisProvider`。
- 是否复用已有 toolbar / filter / config / canvas 模式。
- 是否支持亮色和暗色主题。
- 是否避免硬编码主题色。
- 图表是否接入 `chartTheme`。
- 是否有 loading / empty / error / permission 状态。
- 是否区分查看态和编辑态。
- 是否会破坏 dashboard/topology/screen 共用配置。
- screen 改动是否隔离在 screen canvas/frame，避免污染 dashboard/topology。
- screen 拖拽是否避免在 mousemove 中刷新整张画布。
- screen 示例布局是否来自页面可配置数据，而不是业务代码中的硬编码预置解析。
- 是否影响导入导出或保存结构。
- 是否有最小验证方式。

## Anti-Patterns

- 为 topology 单独复制一套图表配置系统。
- 为每个页面重新造筛选条。
- 在 widget 内写页面级刷新逻辑。
- 在展示组件内直接写保存逻辑。
- 把亮色硬编码样式带进暗色主题。
- 用一次性大重构替代小范围复用。
- 为了视觉丰富牺牲信息密度和可读性。
- 把数据源、命名空间配置散落到 view 页面内部。
- 把 dashboard/topology/screen 的公共配置能力分叉。
- 为 screen 复制一套独立图表配置系统。
- 为了 screen 视觉效果修改共享 widget 默认样式，导致 dashboard/topology 被动变样。
- 在业务代码里沉淀一次性 screen 布局生成常量、数据源解析器或调试脚本。
- 让 screen 组件在拖拽过程中反复触发整屏配置更新。

## Maintenance Notes

- 涉及 ops-analysis 的 UI/UE 或组件变更前，建议先阅读本文件。
- 新增跨 dashboard/topology/screen 复用的能力时，优先更新本文件的 Shared Component Boundaries。
- 新增图表类型或图表视觉 token 时，优先更新 Theme Rules 和 `utils/chartTheme.ts`。
- 若某次需求需要偏离本文件约束，应在对应需求 design 文档中说明原因。
