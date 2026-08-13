# 运营分析单值说明文案与表格单元格样式

Status: implemented

## Problem Statement

运营分析仪表盘里，单值 KPI 只能展示一个主字段，无法把数据源里的副信息（如 `46/48`、失败率）挂到主值下方，卡片信息密度不足。表格单元格目前是纯文本，无法按状态枚举或数值阈值上色，状态矩阵/健康矩阵只能靠肉眼扫字，难以一眼区分正常/关注/严重。

搭建者需要在现有单值与表格组件上补齐这两类可配置能力，且不引入新的图表类型、不切换表格生产入口。

## Solution

在现有 Dashboard 表格与单值链路上补齐两类配置与渲染能力：

1. **单值说明文案**：`single` 可额外选择一个可选数据字段，作为主值下方的说明行；未选择或字段空值时不渲染该行。
2. **表格单元格样式**：在生产路径 `ComTable` 上按列配置值映射与数值阈值配色，并支持文字着色与纯色块两种展示形态；未配置样式的列保持现有行为。

## User Stories

1. 作为运维分析看板搭建者，我希望给单值组件可选地绑定一个说明字段，以便在主值下方展示动态副文案。
2. 作为看板使用者，我希望未配置说明字段时单值卡片与现在一致，避免无意义的空行。
3. 作为运维分析看板搭建者，我希望按列配置枚举映射与数值阈值颜色，以便状态列和数值列都能上色。
4. 作为看板使用者，我希望状态矩阵列可以显示为纯色块（悬停再看原文案），以便快速扫健康态。
5. 作为看板使用者，我希望未命中颜色的色块列单元格仍显示普通文本，避免出现大量空白格。
6. 作为产品负责人，我希望本次只增强现有 `single` 与 `ComTable`，不改挂表格家族组件、不上 gauge 单元格，从而控制回归面。

## Implementation Decisions

### 单值说明文案

- 仅作用于 `chartType = single`，不扩展到 `gauge` / `multiValue`。
- 配置项为可选数据字段选择（与主值字段同源可选列表）；未选择则不渲染说明行。
- 说明内容按字段原值转字符串展示，不复用主值的单位/小数位/换算格式化。
- 字段值为 `null` / `undefined` / 空字符串时，不渲染说明行。
- 布局顺序：主值 → 说明文案 → 环比 → sparkline。
- 说明文案与环比可同时存在，不互斥。
- 主值仍决定空态：主值无数据时整卡走现有空态；说明字段即使有值也不能单独撑起卡片。
- 卡片标题下的静态 `description`（布局项说明）保持不变，与本次数据字段说明文案不是同一概念。

### 表格单元格样式

- 生产入口保持 `ComTable`；不把仪表盘改挂到 `OpsAnalysisTable`。可参考家族表的渲染语义，但能力落在现有生产链路的类型、配置、提交与渲染上。
- 样式配置为**列级**；配置交互为**先选中一列，再编辑该列样式**。
- 列可配置：
  - 完整 `valueMappings`（`value` / `range` / `regex` / `special`），复用现有值映射模型与匹配顺序（首条命中）。
  - `cellThresholdColors` 数值阈值配色。
  - `cellType`：`text`（默认）或 `colorBackground`。
- 颜色优先级：值映射颜色优先；未命中再用数值阈值色。
- `cellType = text`：有颜色时改文字颜色（可加粗），不铺底。
- `cellType = colorBackground`：**纯色块**（默认不显示文字）；原文案/映射文案放入 Tooltip；仅当存在可应用颜色时才进入色块形态。
- 色块模式下未命中任何颜色：退回普通文本展示（不上色块）。
- 未配置映射、阈值且保持默认 `text` 的列：行为与当前 `ComTable` 完全一致。
- 操作列（`actions`）不提供单元格样式配置。
- 明确不包含 `cellType = gauge` 与 `cellMax`。

### 接入范围

- 覆盖配置抽屉、提交配置归一化、类型定义、生产渲染、国际化文案、回归测试。
- 历史仪表盘无新字段时必须兼容；新字段缺省即关闭说明行 / 关闭单元格样式。

## Testing Decisions

- 只验证外部可观察行为，不锁定内部实现细节。
- 优先复用现有接缝：
  - 配置提交归一化测试（与现有 `submitConfig.*` 风格一致）。
  - 值映射 / 阈值工具的既有行为不回退。
  - 单值与表格渲染的聚焦测试（有/无说明字段；映射色优先于阈值色；色块/文字形态；未命中回退文本；未配置列无回归）。
- 单值重点：
  - 未选说明字段 → 不渲染说明行。
  - 选中字段有值 → 主值下方出现原样文案，且位于环比之上。
  - 说明字段空值 → 不渲染说明行。
  - 主值空态时，即使说明字段有值，仍整卡空态。
- 表格重点：
  - 列级映射与阈值可保存并回读。
  - 映射色优先于阈值色。
  - `text` 与 `colorBackground` 形态差异可观察。
  - 色块未命中颜色时显示普通文本。
  - 未配置样式列与现网一致。

## Out of Scope

- 将仪表盘表格改挂或收敛到 `OpsAnalysisTable`。
- `gauge` / `multiValue` 的说明文案字段。
- 表格 `cellType = gauge` 与 `cellMax`。
- 新建独立于 `valueMappings` 的 enum 配置模型。
- 页面壳、侧栏导航、一键诊断等 Exchange 演示盘定制交互。
- 单值说明字段的独立格式化（单位/小数位/换算）。

## Further Notes

- 本变更来自逼近 Exchange 健康运营面板信息密度的组件能力补齐：KPI 副文案与状态矩阵着色；演示盘 mock 本身不在本 spec 范围。
- 「卡片静态描述」与「单值数据说明字段」必须长期保持语义分离，避免配置面混淆。
- `colorBackground` 纯色块是有意偏离家族表「色块内嵌白字」与 DESIGN Semantic Triple 的扫描密度取舍；可访问性通过 Tooltip + `aria-label` / `sr-only` 文案补齐，不把可见文字塞回色块。

## Completion Evidence

- 聚焦测试（2026-08-10）：
  `pnpm exec tsx --test src/app/ops-analysis/utils/__tests__/singleDescription.test.ts src/app/ops-analysis/utils/__tests__/tableCellStyle.test.ts src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.singleDescriptionTableCell.test.ts`
  → 9 passed。
- 生产链路：`ComSingle` 说明行（主值→说明→环比）、`ComTable` 列样式渲染、`submitConfig` 归一化、仪表盘配置抽屉（`showDescriptionField` 仅仪表盘单值开启）、`zh`/`en` i18n。
- 主值空态继续由既有 `isDataReady = rawValue !== null` 门控，说明字段不单独撑卡。
