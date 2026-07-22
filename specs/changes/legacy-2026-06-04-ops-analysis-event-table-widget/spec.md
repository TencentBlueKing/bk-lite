# Historical Superpowers change: 2026-06-04-ops-analysis-event-table-widget

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-04-ops-analysis-event-table-widget.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current log-specific message widget path with a generic expandable event table that reuses existing table configuration and handles plain-list and paginated responses.

**Architecture:** Keep the current `message` chart type entry point for now, but route it to a new generic event-table implementation. Reuse `tableConfig.columns`, `useTableConfig`, `TableSettingsSection`, and `CustomTable`, while extracting common table-like data parsing utilities so `comTable` and the new event widget share the same response-shape logic.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, CustomTable

---

### Task 1: Extract shared table-like data utilities

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/shared/tableLikeData.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable.tsx`
- Test: `web/scripts/ops-analysis-event-table-validation.ts`

- [ ] Add a failing validation script that asserts plain-list and paginated data are parsed consistently.
- [ ] Run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm it fails because the shared utility does not exist yet.
- [ ] Implement shared parsing helpers for records, pagination metadata, and fallback column config generation.
- [ ] Switch `comTable` to use the shared utility without behavior regression.
- [ ] Re-run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm it passes.

### Task 2: Implement generic expandable event table widget

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTable.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTableDetail.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`

- [ ] Add a failing validation case for expandable event-table data handling to `scripts/ops-analysis-event-table-validation.ts`.
- [ ] Run the validation script and confirm the new case fails.
- [ ] Implement the generic event-table widget with `CustomTable`, single-row expand, full-record detail rendering, and interface-driven pagination.
- [ ] Replace log-specific normalization in `comMessage` with the new generic widget path.
- [ ] Relax widget data validation for `message` chart type to accept any list or `{ items }` paginated shape.
- [ ] Re-run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm all cases pass.

### Task 3: Reuse table config UI for message/event widget

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig/hooks/useTableConfig.ts`
- Modify: `web/src/app/ops-analysis/constants/common.ts`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] Extend table-like config handling so the current `message` chart type reuses `useTableConfig` probing and `TableSettingsSection`.
- [ ] Ensure initialization, re-probe, and save logic all treat `message` like `table` for `tableConfig.columns` and optional filter fields.
- [ ] Rename the chart type label from message-oriented wording to event-table wording in locales if needed.
- [ ] Run targeted ESLint on modified files and confirm no new errors.

### Task 4: Verify end-to-end behavior

**Files:**

- Test: `web/scripts/ops-analysis-event-table-validation.ts`
- Test: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage.tsx`
- Test: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`

- [ ] Run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts`.
- [ ] Run targeted ESLint for event-table and view-config files.
- [ ] Run `get_errors` on touched files to confirm no editor diagnostics remain.
- [ ] Manually verify the widget supports list data, paginated data, configured columns, and expanded full-record display.

## specs: 2026-06-04-ops-analysis-event-table-widget-design.md

日期: 2026-06-04
范围: 运营分析仪表盘通用事件表 Widget（第一版）
目标: 将现有偏日志语义的 Message 组件升级为通用事件表 Widget，最大化复用现有 Table 配置与渲染能力，同时保留“行展开查看完整记录”的事件流体验。

## 1. 背景与问题

当前运营分析中的 Message 组件已经不再只是日志列表展示，而是被期望承载更广义的事件流场景，包括：

1. 指标异常时同图查看相关事件流。
2. 告警概览、变更记录、审计日志的嵌入式展示。
3. 后续承接告警中心、日志模块和其他模块通过数据源接入运营分析仪表板的统一载体。

但当前实现存在以下问题：

1. 组件语义仍然绑定在 message / log 上，和目标场景不匹配。
2. 当前逻辑包含日志专属字段猜测与归一化，不适合作为通用事件表基础。
3. 外层字段展示能力过于固定，无法复用现有 table 的展示字段配置模型。
4. 分页、字段探测、列配置等能力与 table 组件存在重叠，但尚未形成可复用边界。

## 2. 目标与非目标

### 2.1 目标

1. 提供一个通用事件表 Widget，不再针对日志场景做专属字段语义处理。
2. 外层列表展示字段完全可配置，配置模型尽量复用现有 tableConfig.columns。
3. 配置交互复用现有 table 的“刷新样本数据后选择展示字段”思路。
4. 支持普通列表和分页列表两类接口返回形态。
5. 支持单行展开，展开区展示该行完整字段列表。
6. 保持运营分析现有 widget 渲染链路约定，包括 loading、empty、onReady 与统一筛选联动。

### 2.2 非目标

1. 第一版不做固定字段模板，不要求 time / level / source / message 四字段存在。
2. 第一版不做日志专属字段归一化，不做 message/log line 语义拆分。
3. 第一版不做级别颜色和等级映射。
4. 第一版不做本地排序，完全信任接口返回顺序。
5. 第一版不做嵌套路径解析，字段选择按字面字段名处理。
6. 第一版不做表达式字段、字段回退链、展开区分组布局。
7. 第一版不把 comTable 直接扩展成事件模式。

## 3. 方案对比与选择

### 方案 A: 继续在现有 comMessage 上演进

优点: 改动面最小，短期交付最快。
缺点: 组件语义与通用事件表方向持续冲突，后续维护成本高。

### 方案 B: 新建通用事件表 Widget，最大化复用 table 能力（推荐）

优点: 语义清晰，能够同时满足“尽量复用现有逻辑”和“去日志专用化”两个目标。
缺点: 首轮改动面比方案 A 略大，需要明确新组件与 table 的边界。

### 方案 C: 直接把 comTable 扩展为事件模式

优点: 表面复用度最高。
缺点: 普通表格与事件表职责混杂，组件边界变差，后续演进风险最高。

最终选择: 方案 B。

## 4. 组件边界与配置模型

### 4.1 组件分层

1. Widget 入口层

- 新建通用事件表 Widget 入口组件。
- 负责接收 rawData、识别分页形态、管理展开状态、回传 onReady。

2. 通用表格展示层

- 继续复用 CustomTable 作为底层表格能力。
- 外层列表列配置直接复用 tableConfig.columns。

3. 展开详情层

- 保留事件表差异化能力。
- 用户展开单行后，展示该行完整字段列表。

### 4.2 配置模型

第一版不新增独立 eventConfig，优先复用现有 tableConfig：

1. 外层展示字段直接复用 tableConfig.columns。
2. 展示字段配置能力与现有 table 保持一致：显隐、标题、顺序、宽度。
3. 字段探测交互复用 table 的刷新样本数据模式。

新增的最小差异能力只有：

1. Widget 默认支持单行展开。
2. 展开区展示策略固定为 full record。

### 4.3 现有组件去留

1. comTable 保持为普通表格组件，不承载事件表模式。
2. 现有 comMessage 不再作为长期方向的主语义组件。
3. 当前日志专属 normalizeMessageRows 退出主路径，不再作为通用实现基础。

## 5. 数据流与接口兼容规则

### 5.1 接口返回形态

第一版兼容两类结构：

1. 普通列表

- 直接将返回值视为记录数组。

2. 分页列表

- 识别带 items 的包裹结构。
- 外层列表使用 items。
- 分页信息优先使用接口返回的 count。
- 如果 count 缺失，则以 items.length 兜底。

### 5.2 分页与排序原则

1. 是否分页由接口参数和返回结构决定。
2. 组件完全信任接口，如果接口返回分页结构就按分页展示，否则按普通列表展示。
3. 组件不做本地重排，完全信任接口返回顺序。

### 5.3 字段探测与配置流程

1. 用户在配置面板点击刷新按钮。
2. 使用当前数据源参数拉取一次样本数据。
3. 从第一条记录提取可用字段列表。
4. 用户基于探测结果配置外层展示字段。
5. 展开区不单独探测，直接展示当前记录完整字段。

### 5.4 字段读取规则

1. 字段选择按字面字段名处理。
2. 不解析嵌套路径。
3. 类似 agent.name、@timestamp 这类 key 被视为普通原始字段名。

## 6. 展示与交互设计

### 6.1 外层列表

1. 外层列表像 table 一样展示任意个配置字段。
2. 不预设固定四字段布局。
3. 外层列表支持接口驱动的分页展示。
4. 外层区域使用组件容器滚动，不新增本地分页策略。

### 6.2 行展开

1. 默认单行展开。
2. 展开后展示该行完整字段键值对列表。
3. 展开区允许和外层字段重复，第一版不做去重。
4. 展开区内容支持滚动。

### 6.3 空态与配置态

1. 空数组或 items 为空时显示空态，不视为格式错误。
2. 若用户尚未配置外层展示字段，显示“请先配置展示字段”的显式提示，不自动猜字段渲染。

## 7. 复用策略与代码落点

### 7.1 直接复用

1. 复用 CustomTable 作为底层表格渲染能力。
2. 复用 tableConfig.columns 作为外层展示列配置结构。
3. 复用 table 现有字段探测与配置交互思路。

### 7.2 优先抽公共逻辑

如果以下逻辑与 comTable 重复，优先抽公共 util / hook，而不是复制实现：

1. 从 rawData 识别普通列表 / 分页列表。
2. 从样本数据提取字段列表。
3. 从 tableConfig.columns 生成外层展示列。

### 7.3 新建模块

建议新增：

1. 通用事件表 Widget 入口组件。
2. 事件表专用展开详情渲染模块。
3. 必要的公共数据识别 / 字段探测 util。

## 8. 错误处理与校验规则

### 8.1 数据结构校验

第一版只校验：

1. 返回值是否为数组。
2. 或者是否为带 items 的分页结构。

只要满足其一，就允许进入渲染。

### 8.2 错误与降级策略

1. 数据结构不符合上述两种形态时，显示统一的格式错误提示。
2. 空数据只显示空态，不视为结构错误。
3. 分页结构缺少 count 时按 items.length 兜底，不阻塞渲染。
4. 用户未配置展示字段时，显示配置提示，不自动猜测字段渲染。

## 9. 验证范围

第一版至少覆盖以下验证范围：

1. 普通列表渲染正确。
2. 分页列表渲染正确。
3. 外层展示字段配置生效。
4. 行展开后完整字段可见且可滚动。
5. 字段探测与刷新交互可正常工作。

## 10. 第一版明确不做什么

1. 不做日志专属字段归一化。
2. 不做固定四字段模板。
3. 不做级别颜色与等级映射。
4. 不做本地排序。
5. 不做嵌套路径解析。
6. 不做表达式字段。
7. 不做展开区分组布局。
8. 不把 comTable 改造成事件模式。

## 11. 实施建议

### 第一阶段

1. 新建通用事件表 Widget 入口与展开详情模块。
2. 抽离普通列表 / 分页列表识别逻辑。
3. 让配置侧尽量复用 table 的字段探测与展示字段配置能力。

### 第二阶段

1. 清理现有 comMessage / normalizeMessageRows 主路径依赖。
2. 评估日志场景是否也迁移到统一事件表基座。
3. 视需求补充更丰富的事件语义能力。

## 12. 自检结果

1. Placeholder 检查: 无 TBD / TODO / 待补充占位。
2. 一致性检查: 组件边界、接口规则、复用策略与非目标一致，无冲突。
3. 范围检查: 聚焦第一版通用事件表，不扩展到日志语义增强和复杂表达式能力。
4. 歧义检查: 已明确“分页、排序由接口决定；列配置尽量复用 tableConfig.columns；展开区默认 full record”的边界。
