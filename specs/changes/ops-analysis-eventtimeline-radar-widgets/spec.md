# 运营分析新增 Event Timeline 与 Radar 组件

Status: implemented

## Problem Statement

运营分析模块当前缺少两类高频通用可视化：事件叙事时间线与多维指标画像雷达图。现有组件里，`eventTable` 偏检索和列表扫描，`stateTimeline` 偏状态段展示，均不能替代通用事件叙事；同时没有雷达图能力，无法在单卡片内直观表达多指标轮廓。

用户需要在不引入因果图复杂度、不过度设计配置面的前提下，新增两个可在 Dashboard 中直接使用的通用 Widget，并保持验收边界清晰、范围可控。

## Solution

新增两个独立 Widget 类型：`eventTimeline` 与 `radar`，并完成从组件家族到 Dashboard runtime 的完整接入（配置、渲染、校验、国际化、测试）。

- `eventTimeline` 提供通用事件时间序列叙事展示，不承担因果关系建模或事件检索。
- `radar` 提供单实体多维指标画像展示，支持两种输入形态并统一刻度。
- 两个类型纳入数据源 `chart_type` 可选集合；Widget 配置抽屉仅展示当前数据源已勾选的图表类型。

## User Stories

1. 作为运维分析看板搭建者，我希望使用事件时间线组件按时间叙事展示关键事件，从而快速理解事件演进过程。
2. 作为运维分析看板搭建者，我希望使用雷达图组件展示单实体多维指标轮廓，从而快速判断健康度和短板维度。
3. 作为看板使用者，我希望新增组件与现有 Dashboard 编辑与渲染链路一致，从而可以直接在现有仪表板中配置和使用。
4. 作为产品负责人，我希望本次需求边界聚焦新增组件，不混入既有组件补齐工作，从而保证验收清晰可控。

## Implementation Decisions

- 新增独立 `chartType`：`eventTimeline` 与 `radar`。
- `getChartTypeList()` 包含上述两个类型，供数据源设置页勾选。
- Widget 配置抽屉的图表类型选项来自数据源 `chart_type` 与 surface 过滤结果，不再对所有 Widget 无条件注入这两个类型。
- 完整接入范围包含：组件家族层、Dashboard runtime registry、类型定义、配置面、提交配置归一化、渲染时数据校验、国际化文案、回归测试。

- `eventTimeline` 的定位与边界：
  - 是事件叙事组件，不是事件检索组件。
  - 必填语义字段：`time`、`title`；可选：`description`、`category`、`status`、`link`。
  - 缺少可选字段时不报错；单条记录缺少 `time`/`title` 时跳过该条，不影响其余记录渲染。
  - 明确不支持 `parentId`、`edge`、causal relationship，不引入树/图布局语义。
  - `sortOrder` 支持 `asc | desc`，默认 `desc`。
  - 不做分页；业务过滤由数据源负责。
  - 内置渲染保护阈值 `maxItems`（内部常量），超限行为为“展示最新 N 条 + warning”，且禁止静默丢弃。
  - `link` 交互为新窗口打开。
  - `status` 采用内置语义枚举 `info/warning/error/success` 负责节点颜色与状态表达，不开放自定义映射。
  - `category` 仅作为业务标签，不参与颜色表达；聚合/分组属于后续阶段。
  - `icon` 不纳入 MVP。
  - 数据源输出固定语义字段；Widget 直接读取 `time`/`title` 等默认字段，不提供字段映射配置。

- `radar` 的定位与边界：
  - 先支持单实体多维画像，不支持多实体雷达对比（后续阶段）。
  - MVP 支持两种输入形态：
    1) 自描述列表：`[{ name, value }]`；
    2) 宽表对象 + 指标映射配置。
  - 指标配置采用 `label/key/value` 思路：`key` 绑定数据字段，`label` 控制展示名，避免字段名直接作为展示文案。
  - 刻度采用统一 `min/max`，默认 0/100。
  - `min/max` 能力可共享，但不继续扩大 `gaugeMin/gaugeMax` 命名；若已有历史字段则按兼容策略处理。
  - 新建独立 `RadarSettingsSection`；复用字段选择与范围配置子能力，不复用 `GaugeSettingsSection`。
  - 轴数量仅给 UX warning（如过少/过多），不做强校验拦截。

- 明确排除本次范围：`stateTimeline`、`barGauge` 的补齐接入。

## Testing Decisions

- 测试目标聚焦外部可观察行为，不验证实现细节。
- 最高优先沿用现有运营分析 Widget 的配置提交与渲染校验测试接缝，保证与既有回归风格一致。

- `eventTimeline` 测试重点：
  - 单条记录缺少 `time`/`title` 时被跳过；全部记录不可解析时才提示数据结构不符。
  - `sortOrder` 的 `asc/desc` 显示顺序与默认值。
  - `maxItems` 超限时“展示最新 N 条 + warning”且无静默丢弃。
  - `status` 内置枚举颜色语义生效，`category` 仅标签展示。
  - `link` 新窗口打开行为。
  - 不分页、不 `tableConfig` 相关行为。

- `radar` 测试重点：
  - 两种输入形态的正确解析与渲染。
  - 指标 `key/label` 映射生效与展示回退逻辑。
  - 统一 `min/max` 默认值与配置覆盖行为。
  - 轴数量仅 warning 不阻断渲染。
  - 多实体对比输入在 MVP 阶段的非支持行为提示。

- 接入回归重点：
  - 两个新 Widget 在编辑态可选、可配置、可保存、可渲染。
  - registry、submit 配置、runtime 校验、i18n 文案全链路一致。
  - 数据源未勾选 `eventTimeline`/`radar` 时，Widget 配置抽屉不展示对应图表类型。

## Out of Scope

- `eventTimeline` 的因果关系、父子依赖、边连接、树/图布局。
- `eventTimeline` 的 icon、category 聚合/分组、复杂检索能力。
- `eventTimeline` 分页与复杂表格配置能力。
- `radar` 多实体对比能力。
- `stateTimeline`、`barGauge` 既有组件的补齐接入。
- 任何不属于 Widget 层新增能力的后端取数逻辑扩展。

## Further Notes

- 本次需求强调“通用组件”与“可控 MVP”，优先保证清晰语义与可验收边界，避免组件设计器化。
- `eventTable` 与 `eventTimeline` 可以消费同类事件数据，但两者产品语义应长期保持分离：前者用于检索与高密度扫描，后者用于叙事与演进表达。

## Completion Evidence

- 已完成 `eventTimeline` 与 `radar` 的 family + dashboard runtime 全链路接入（registry、类型、配置、submit、校验、i18n、测试）。
- 图表类型注册策略已更正：`getChartTypeList()` 含 `eventTimeline`/`radar`；Widget 配置仅展示数据源已选类型。
- 新增聚焦测试并通过：
  - `pnpm exec tsx --test src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.eventTimelineRadar.test.ts`
  - `pnpm exec tsx --test src/app/ops-analysis/utils/__tests__/eventTimelineRadarData.test.ts`
- 新增/改动文件聚焦 ESLint 检查通过：
  - `pnpm exec eslint src/app/ops-analysis/components/ops-analysis-widgets/event-timeline.tsx src/app/ops-analysis/components/ops-analysis-widgets/radar.tsx src/app/ops-analysis/components/widgetConfig.tsx src/app/ops-analysis/components/widgetDataRenderer.tsx src/app/ops-analysis/components/widgetConfig/sections/radarSettingsSection.tsx src/app/ops-analysis/utils/eventTimeline.ts src/app/ops-analysis/utils/radarData.ts src/stories/ops-analysis-widgets-family.stories.tsx`
- 全量 `pnpm type-check` 在当前基线仍失败，错误位于未改动的既有问题：
  - `.next/types/validator.ts` 路由类型约束冲突
  - `src/app/ops-analysis/utils/sidebarSelection.ts` 的 `Key[]` 类型不匹配
