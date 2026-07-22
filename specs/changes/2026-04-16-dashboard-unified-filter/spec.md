# 2026 04 16 Dashboard Unified Filter

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-16-dashboard-unified-filter/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

运营分析仪表盘当前缺乏统一筛选能力，用户需要逐个配置每个组件的筛选参数（如时间范围、环境、命名空间），操作繁琐且容易遗漏。需要在仪表盘层面提供统一筛选功能，让多个组件可以共享筛选条件，一次修改、全局生效。

## What Changes

- 新增仪表盘顶部统一筛选栏，支持「关键字输入」和「时间范围」两种控件类型
- 自动扫描画布组件，收集 `filterType='filter'` 的参数供用户选择
- 组件级显式绑定：用户通过开关控制是否将组件参数绑定到统一筛选
- 绑定规则：仅当参数 key 和 type 都匹配时才可绑定
- 统一筛选值变更时，所有已绑定组件自动重新请求数据
- 绑定失效时，组件右上角显示警告图标提示用户
- **BREAKING**: 时间类型筛选不再使用 `other.timeSelector`，统一存入 `Dashboard.filters`

## Capabilities

### New Capabilities

- `dashboard-unified-filter`: 仪表盘统一筛选功能，包括筛选项定义、组件绑定、值变更联动、失效检测

### Modified Capabilities

<!-- 无需修改现有 spec，数据源参数分类机制(filterType)已存在 -->

## Impact

- **前端**:
  - `web/src/app/ops-analysis/types/dashBoard.ts` - 扩展 Dashboard.filters 类型
  - `web/src/app/ops-analysis/utils/widgetDataTransform.ts` - 参数合并逻辑支持统一筛选
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/` - 集成筛选栏和配置
  - 新增 `unifiedFilter/` 组件目录和 `useUnifiedFilter` hook

- **后端**:
  - `server/apps/operation_analysis/schemas/import_export_schema.py` - YAML 导入导出支持 filters

- **数据存储**:
  - 复用现有 `Dashboard.filters` JSONField，无需数据库迁移

## Implementation Decisions

## Context

运营分析仪表盘已具备以下基础设施：
- `ParamItem.filterType` 字段支持 `'fixed' | 'filter' | 'params'` 三种参数分类
- `Dashboard.filters` JSONField 已预留（当前为空 `{}`）
- `processDataSourceParams()` 函数处理参数优先级和合并逻辑
- 时间范围通过 `globalTimeRange` 传递给组件（仅限 `type='timeRange'`）

本设计在现有架构上扩展，复用已有字段和函数，最小化改动范围。

## Goals / Non-Goals

**Goals:**
- 仪表盘级定义统一筛选项，支持 `string` 和 `timeRange` 两种控件类型
- 自动扫描画布组件收集可筛选参数，按 key + type 联合去重
- 组件级显式绑定（开关控制），绑定规则为 key + type 都匹配
- 统一筛选值变更时联动刷新所有已绑定组件
- 绑定失效时显示警告图标
- YAML 导入导出支持 filters 字段

**Non-Goals:**
- 不实现单选下拉控件（本期仅 string 和 timeRange）
- 不兼容旧数据的 `other.timeSelector` 字段
- 不实现跨仪表盘共享筛选状态
- 不实现图表点击联动、钻取联动
- 不实现统一筛选必填配置

## Decisions

### D1: 数据结构设计

**决策**: `Dashboard.filters` 存储 `{ definitions, values }`，组件绑定存储在 `LayoutItem.valueConfig.filterBindings`

**理由**:
- 筛选定义是仪表盘级别，值是运行时状态，两者分离便于管理
- 绑定关系属于组件配置，存在 valueConfig 符合现有数据组织方式
- 不引入新的顶层字段，减少 schema 变更

**备选方案**:
- A. 所有配置集中在 Dashboard.filters → 组件需要反向查询，耦合度高
- B. 新增独立的 filterBindings 顶层字段 → 增加 schema 复杂度

### D2: 参数优先级

**决策**: `固定参数 > 统一筛选 > 组件私有参数 > 数据源默认值`

**理由**:
- 固定参数（filterType='fixed'）是数据源强制配置，不应被覆盖
- 统一筛选是仪表盘级意图，优先于组件私有配置
- 组件私有参数作为兜底，保持向后兼容

### D3: 绑定匹配规则

**决策**: 仅当参数 `key`（name 字段）和 `type` 都匹配时才可绑定

**理由**:
- key 相同但 type 不同（如 env 既有 string 又有 number）是不同参数
- 类型不匹配会导致运行时错误（如把字符串传给时间控件）

### D4: 失效检测时机

**决策**: 每次加载仪表盘时实时校验绑定有效性

**理由**:
- 数据源可能被修改（参数增删改），需要实时校验
- 不在保存时校验，避免阻塞用户操作

### D5: 无值处理

**决策**: 统一筛选无值时，不传该筛选参数

**理由**:
- 让后端按默认逻辑处理，避免传空值导致的边界问题
- 与现有参数处理行为一致

## Risks / Trade-offs

**[Risk] 扫描性能** → 画布组件数量大时扫描耗时
- Mitigation: 扫描仅在打开配置弹窗时执行，非热路径；组件数量通常 < 50

**[Risk] 绑定失效累积** → 用户不处理警告导致大量失效绑定
- Mitigation: 失效绑定不影响组件正常工作（使用默认值）；警告图标提供清晰入口

**[Risk] BREAKING 时间类型迁移** → 旧仪表盘使用 other.timeSelector
- Mitigation: 本期不兼容旧数据，需用户重新配置；影响范围可控（运营分析模块内部）

**[Trade-off] 显式绑定 vs 自动绑定**
- 选择显式绑定：用户控制更精细，避免意外联动
- 代价：配置步骤多一步（开关确认）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-14
```

## Capability Deltas

### dashboard-unified-filter

## ADDED Requirements

### Requirement: 统一筛选项定义

系统 SHALL 允许用户在仪表盘级别定义统一筛选项，每个筛选项包含：唯一标识(id)、参数键(key)、显示名称(name)、控件类型(type: 'string' | 'timeRange')、默认值(defaultValue)、显示顺序(order)、启用状态(enabled)。

#### Scenario: 添加关键字输入筛选项
- **WHEN** 用户在统一筛选配置弹窗中添加一个 key='namespace'、type='string' 的筛选项
- **THEN** 系统创建筛选项定义并存储到 Dashboard.filters.definitions

#### Scenario: 添加时间范围筛选项
- **WHEN** 用户在统一筛选配置弹窗中添加一个 key='time_range'、type='timeRange' 的筛选项
- **THEN** 系统创建筛选项定义并存储到 Dashboard.filters.definitions

#### Scenario: 编辑筛选项显示名称
- **WHEN** 用户修改筛选项的显示名称
- **THEN** 系统更新 Dashboard.filters.definitions 中对应筛选项的 name 字段

#### Scenario: 删除筛选项
- **WHEN** 用户删除一个筛选项
- **THEN** 系统从 Dashboard.filters.definitions 中移除该筛选项，且所有组件对该筛选项的绑定自动失效

---

### Requirement: 参数自动扫描

系统 SHALL 自动扫描画布上所有组件的数据源参数，收集 filterType='filter' 且 type 为 'string' 或 'timeRange' 的参数，按 key + type 联合去重后供用户选择。

#### Scenario: 扫描并去重参数
- **WHEN** 用户打开统一筛选配置弹窗
- **THEN** 系统扫描所有组件数据源参数，按 key + type 联合去重，显示可选参数列表，每项包含：参数 key、类型、匹配组件数、默认显示名（取自 alias_name 或 name）

#### Scenario: 过滤不支持的参数类型
- **WHEN** 组件数据源存在 filterType='filter' 但 type='number' 的参数
- **THEN** 该参数不出现在可选列表中（本期仅支持 string 和 timeRange）

#### Scenario: 过滤非筛选参数
- **WHEN** 组件数据源存在 filterType='fixed' 或 filterType='params' 的参数
- **THEN** 该参数不出现在可选列表中

---

### Requirement: 组件绑定配置

系统 SHALL 允许用户为每个组件配置与统一筛选项的绑定关系，绑定通过开关控制，仅当组件数据源参数的 key 和 type 与统一筛选项匹配时才可启用绑定。

#### Scenario: 启用匹配的绑定
- **WHEN** 组件数据源存在 key='namespace'、type='string' 的参数，且统一筛选存在相同 key + type 的筛选项
- **THEN** 用户可开启该绑定开关，系统将绑定关系存储到 LayoutItem.valueConfig.filterBindings

#### Scenario: 禁用不匹配的绑定
- **WHEN** 组件数据源存在 key='env'、type='string' 的参数，但统一筛选存在 key='env'、type='number' 的筛选项
- **THEN** 绑定开关显示为禁用状态，并提示"类型不匹配"

#### Scenario: 无匹配参数时禁用
- **WHEN** 组件数据源不存在与某统一筛选项 key 匹配的参数
- **THEN** 该筛选项的绑定开关显示为禁用状态，并提示"组件无此参数"

---

### Requirement: 筛选值联动

系统 SHALL 在统一筛选值变更时，自动触发所有已绑定组件重新请求数据，使用最新的筛选值。

#### Scenario: 关键字输入值变更
- **WHEN** 用户在筛选栏中修改关键字输入的值
- **THEN** 所有绑定到该筛选项的组件立即使用新值重新请求数据

#### Scenario: 时间范围值变更
- **WHEN** 用户在筛选栏中修改时间范围的值
- **THEN** 所有绑定到该筛选项的组件立即使用新时间范围重新请求数据

#### Scenario: 组件未绑定时不受影响
- **WHEN** 用户修改统一筛选值，但某组件未绑定到该筛选项
- **THEN** 该组件不触发重新请求

---

### Requirement: 参数合并优先级

系统 SHALL 按以下优先级合并参数：固定参数(filterType='fixed') > 统一筛选参数 > 组件私有参数(filterType='params') > 数据源默认参数。

#### Scenario: 固定参数优先
- **WHEN** 数据源定义 filterType='fixed' 的参数，且该参数 key 存在统一筛选绑定
- **THEN** 使用数据源定义的固定值，忽略统一筛选值

#### Scenario: 统一筛选优先于私有参数
- **WHEN** 组件绑定了统一筛选，且组件自身也配置了该参数的私有值
- **THEN** 使用统一筛选值，忽略组件私有配置

#### Scenario: 无统一筛选值时使用私有参数
- **WHEN** 组件绑定了统一筛选，但统一筛选值为空
- **THEN** 不传该参数（统一筛选无值时按"不传"处理）

---

### Requirement: 绑定失效检测

系统 SHALL 在每次加载仪表盘时校验所有组件的绑定有效性，失效时在组件右上角显示警告图标。

#### Scenario: 筛选项被删除导致失效
- **WHEN** 组件绑定的 filterId 在 Dashboard.filters.definitions 中不存在
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"筛选项已删除"

#### Scenario: 数据源参数被删除导致失效
- **WHEN** 组件绑定的 filterId 对应的 key 在组件当前数据源中不存在
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"参数已不存在"

#### Scenario: 参数类型变更导致失效
- **WHEN** 组件绑定的参数 key 存在，但 type 与统一筛选项不匹配
- **THEN** 该绑定标记为失效，组件右上角显示警告图标，Hover 提示"类型不匹配"

#### Scenario: 失效不阻塞组件渲染
- **WHEN** 组件存在失效绑定
- **THEN** 组件正常渲染，使用数据源默认值或私有配置，仅显示警告图标

---

### Requirement: 筛选栏显示

系统 SHALL 在仪表盘顶部显示统一筛选栏，仅当存在已启用的筛选项时显示。

#### Scenario: 筛选栏渲染
- **WHEN** Dashboard.filters.definitions 中存在 enabled=true 的筛选项
- **THEN** 仪表盘顶部显示筛选栏，按 order 字段排序渲染各筛选控件

#### Scenario: 空状态不显示
- **WHEN** Dashboard.filters.definitions 为空或所有筛选项 enabled=false
- **THEN** 筛选栏不显示

#### Scenario: 编辑态显示配置入口
- **WHEN** 仪表盘处于编辑态
- **THEN** 筛选栏显示 [设置] 按钮，点击打开配置弹窗

#### Scenario: 查看态隐藏配置入口
- **WHEN** 仪表盘处于查看态
- **THEN** 筛选栏不显示 [设置] 按钮，仅允许修改筛选值

---

### Requirement: YAML 导入导出

系统 SHALL 在 YAML 导入导出时包含 Dashboard.filters 和各组件的 filterBindings 配置。

#### Scenario: 导出包含筛选配置
- **WHEN** 用户导出仪表盘 YAML
- **THEN** 导出内容包含 filters.definitions 和各组件的 valueConfig.filterBindings

#### Scenario: 导出不含运行时值
- **WHEN** 用户导出仪表盘 YAML
- **THEN** filters.values 为空对象（运行时值不持久化到导出文件）

#### Scenario: 导入恢复筛选配置
- **WHEN** 用户导入包含 filters 配置的 YAML
- **THEN** Dashboard.filters.definitions 和各组件 filterBindings 正确恢复

## Work Checklist

## 1. 类型定义扩展

- [x] 1.1 在 `web/src/app/ops-analysis/types/dashBoard.ts` 中定义 `DashboardFilters`、`UnifiedFilterDefinition`、`FilterValue`、`TimeRangeValue` 类型
- [x] 1.2 在 `web/src/app/ops-analysis/types/dashBoard.ts` 中扩展 `ValueConfig` 接口，添加 `filterBindings?: FilterBindings` 字段
- [x] 1.3 在 `web/src/app/ops-analysis/types/dashBoard.ts` 中定义 `FilterBindings`、`ScannedFilterParam`、`BindingValidationResult` 类型

## 2. 状态管理 Hook

- [x] 2.1 创建 `web/src/app/ops-analysis/hooks/useUnifiedFilter.ts`
- [x] 2.2 实现 `filterValues` 状态管理和 `setFilterValues` 方法
- [x] 2.3 实现 `updateDefinitions` 方法更新筛选项定义
- [x] 2.4 实现 `getEffectiveParams` 方法按优先级合并参数
- [x] 2.5 实现 `validateBindings` 方法校验绑定有效性

## 3. 参数合并逻辑

- [x] 3.1 修改 `web/src/app/ops-analysis/utils/widgetDataTransform.ts` 中的 `processDataSourceParams` 函数
- [x] 3.2 添加统一筛选值注入逻辑，遵循优先级：fixed > 统一筛选 > params > 默认值
- [x] 3.3 处理统一筛选无值时不传参数的逻辑

## 4. 统一筛选栏组件

- [x] 4.1 创建 `web/src/app/ops-analysis/components/unifiedFilter/` 目录
- [x] 4.2 实现 `UnifiedFilterBar.tsx` 组件，按 order 渲染筛选控件
- [x] 4.3 实现 string 类型筛选控件（Input）
- [x] 4.4 实现 timeRange 类型筛选控件（DateRangePicker）
- [x] 4.5 实现编辑态显示配置按钮、查看态隐藏的逻辑
- [x] 4.6 实现空状态时不显示筛选栏的逻辑

## 5. 统一筛选配置弹窗

- [x] 5.1 实现 `UnifiedFilterConfigModal.tsx` 组件
- [x] 5.2 实现参数自动扫描逻辑（收集 filterType='filter' 且 type 为 string/timeRange 的参数）
- [x] 5.3 实现按 key + type 联合去重逻辑
- [x] 5.4 实现可选参数列表展示（参数 key、类型、匹配组件数、默认显示名）
- [x] 5.5 实现筛选项添加功能
- [x] 5.6 实现筛选项编辑功能（修改显示名称、默认值、顺序、启用状态）
- [x] 5.7 实现筛选项删除功能
- [x] 5.8 实现筛选项拖拽排序功能

## 6. 组件绑定配置面板

- [x] 6.1 实现 `FilterBindingPanel.tsx` 组件
- [x] 6.2 实现自动匹配 key + type 的逻辑
- [x] 6.3 实现绑定开关（匹配时可启用）
- [x] 6.4 实现禁用状态展示（不匹配时显示原因：类型不匹配 / 组件无此参数）

## 7. 仪表盘集成

- [x] 7.1 在 `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx` 中集成 `useUnifiedFilter` hook
- [x] 7.2 在仪表盘顶部集成 `UnifiedFilterBar` 组件
- [x] 7.3 实现筛选值变更时触发组件刷新的逻辑
- [x] 7.4 将 filters 配置纳入仪表盘保存逻辑

## 8. 组件配置抽屉集成

- [x] 8.1 在 `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx` 中添加"统一筛选绑定"区域
- [x] 8.2 集成 `FilterBindingPanel` 组件
- [x] 8.3 将 filterBindings 纳入组件配置保存逻辑

## 9. 绑定失效警告

- [x] 9.1 在 `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx` 中添加失效检测逻辑
- [x] 9.2 实现警告图标渲染（组件右上角）
- [x] 9.3 实现 Hover Tooltip 显示失效原因

## 10. 后端 YAML 导入导出

- [x] 10.1 修改 `server/apps/operation_analysis/schemas/import_export_schema.py`，在 dashboard schema 中添加 filters 字段
- [x] 10.2 在 view_sets 的 valueConfig 中添加 filterBindings 字段
- [x] 10.3 验证导出时 filters.values 为空对象

## 11. 测试与验证

- [x] 11.1 执行 `cd web && pnpm lint && pnpm type-check` 确保类型检查通过
- [ ] 11.2 手动验证：定义统一筛选项并保存，刷新后回显正确
- [ ] 11.3 手动验证：组件绑定后，修改统一筛选值，组件正确刷新
- [ ] 11.4 手动验证：数据源参数变更导致绑定失效，警告图标正确显示
- [ ] 11.5 手动验证：YAML 导出包含 filters 配置，导入后恢复正确
- [ ] 11.6 回归验证：现有仪表盘无统一筛选时功能不受影响
