# Add Ops Analysis Param Options Source

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/add-ops-analysis-param-options-source/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

运营分析参数输入存在两类问题：

1. **输入形态割裂**：组件配置抽屉和统一筛选分别处理输入框、下拉和单选，选项配置体验不一致。
2. **内置参数缺少声明式选项来源**：例如 `CMDB 3D机房布局.server_room_id` 应天然使用 CMDB 机房列表作为候选项，但当前只能手动配置或手动输入。

本变更把“参数选项配置”提升为“参数输入配置”：

- 输入控件支持输入框、下拉选择、单选按钮。
- 下拉/单选的选项来源支持静态列表和动态数据源。
- 内置数据源可用稳定的 `sourceRef/rest_api` 声明动态选项来源，不依赖数据库生成 ID。
- 组件配置抽屉和统一筛选共用同一个编辑器内部交互。
- 数据源管理参数表不提供手动选项配置入口，避免全局配置入口过重。

## What Changes

- 新增统一模型 `InputControlConfig`，替代本分支早期的 `optionsConfig` 作为新主模型。
- 新增/改造共享编辑器 `paramInputConfigEditor.tsx`：
  - 控件类型：输入框 / 下拉选择 / 单选按钮
  - 选项来源：自定义选项 / 数据源选项
- 新增/改造运行渲染组件 `paramInputControl.tsx`：
  - `input` 渲染原始参数输入控件
  - `select` 渲染 Select
  - `radio` 渲染 Radio.Group
  - 动态来源失败或无选项时回退原始输入控件，不阻断参数配置
- 组件配置抽屉：
  - 消费数据源定义中的 `inputConfig`
  - 允许 widget 级覆盖写入 `valueConfig.dataSourceParams[i].inputConfig`
- 统一筛选：
  - 使用同一个 `paramInputConfigEditor.tsx`
  - 新配置写入 `UnifiedFilterDefinition.inputConfig`
  - select/radio 运行态走同一套消费逻辑
- 数据源管理参数表：
  - 删除/不新增“选项”列和编辑入口
  - 只维护参数名、类型、默认值、过滤类型等基础字段
- CMDB 首个落地：
  - 注册 `CMDB 机房列表` 内置数据源（`rest_api: "cmdb/get_room_list"`）
  - `CMDB 3D机房布局.server_room_id.inputConfig` 声明引用 `cmdb/get_room_list`

## Capabilities

### New Capabilities

- `param-input-source`: 运营分析参数输入配置能力；支持输入框、下拉选择、单选按钮；下拉/单选支持静态选项与动态数据源选项；内置数据源可通过 `sourceRef/rest_api` 声明默认选项来源。

### Modified Capabilities

- 统一筛选配置：select 与 radio 的选项编辑和运行消费改为统一 `InputControlConfig` 模型。
- 组件参数配置：查询参数输入控件改为消费 `InputControlConfig`，并允许 widget 级覆盖。
- 内置数据源初始化：`source_api.json` 中参数可携带 `inputConfig`。

## Impact

- **前端**:
  - `web/src/app/ops-analysis/types/dataSource.ts` - 新增 `InputControlConfig`，扩展 `ParamItem.inputConfig`
  - `web/src/app/ops-analysis/types/dashBoard.ts` - 扩展 `UnifiedFilterDefinition.inputConfig`
  - `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx` - 新增/替换共享编辑器
  - `web/src/app/ops-analysis/components/paramInputControl.tsx` - 新增/替换运行渲染组件
  - `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts` - 新增归一化与动态来源解析工具
  - `web/src/app/ops-analysis/components/paramsConfig.tsx` - 按 `inputConfig` 渲染参数输入
  - `web/src/app/ops-analysis/components/widgetConfig.tsx` - 写入 widget 级 `inputConfig`
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx` - 使用统一编辑器
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx` - select/radio 共用统一运行渲染
  - `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx` - 移除本分支新增的选项配置入口
  - `web/src/app/ops-analysis/locales/zh.json` + `en.json` - 新增/调整 i18n key

- **后端**:
  - 新增 `cmdb/get_room_list` NATS handler 与服务函数
  - 不需要数据库 schema 变更

- **数据存储**:
  - `inputConfig` 存在现有 JSON 字段中，无数据库迁移
  - 旧 `options` 只做读取兼容，写入新配置时只写 `inputConfig`

## Out of Scope

- 不做数据源管理页面的全局选项来源手动编辑。
- 不做“恢复内置默认”按钮。
- 不做动态来源参数映射。
- 不做多种 `sourceRef` 类型，首版只支持 `rest_api`。
- 不做 TTL 缓存、选项快照或复杂空态过滤。
- 不做数据库迁移。

## 首个落地案例：CMDB 机房列表内置选项源

让 `CMDB 3D机房布局.server_room_id` 默认显示当前用户可见机房列表。

实现方式：

- 后端提供 `cmdb/get_room_list`，返回 CMDB 原始字段 `_id`、`inst_name` 等，并复用现有权限过滤。
- `source_api.json` 注册 `CMDB 机房列表`，`chart_type: []`。
- `CMDB 3D机房布局.server_room_id.inputConfig` 使用：

```json
{
  "control": "select",
  "optionsSource": {
    "type": "dynamic",
    "sourceRef": {
      "type": "rest_api",
      "value": "cmdb/get_room_list"
    },
    "valueField": "_id",
    "labelField": "inst_name"
  }
}
```

## Implementation Decisions

## Context

当前分支早期设计以 `optionsConfig` 为中心，目标是给字符串参数增加静态/动态选项来源。但讨论后目标调整为更通用的“参数输入配置”：

- 同一个参数既可能是普通输入框，也可能是下拉或单选。
- 下拉和单选都需要支持静态选项与动态数据源选项。
- 组件配置抽屉和统一筛选必须复用同一套编辑器内部交互。
- 内置数据源默认选项来源应通过 `source_api.json` 声明，而不是要求用户在数据源管理参数表里手动配置。

## Goals / Non-Goals

**Goals:**

- 定义 `InputControlConfig`，覆盖输入框、下拉选择、单选按钮。
- 下拉/单选的选项来源支持 static 与 dynamic。
- dynamic 支持两种引用：
  - `sourceId`：用户在 UI 手动选择数据源后保存
  - `sourceRef/rest_api`：内置数据源声明使用，避免依赖数据库 ID
- 组件配置抽屉和统一筛选共用 `paramInputConfigEditor.tsx`。
- 动态来源失败时回退原始输入控件，不能阻断参数配置。
- 删除数据源管理参数表的选项配置入口。

**Non-Goals:**

- 不做数据源管理页面的全局选项来源手动编辑。
- 不做“恢复内置默认”按钮。
- 不做动态来源参数映射或注入当前 widget 其它参数值。
- 不做 TTL 缓存。
- 不做多种 sourceRef 类型。
- 不修改数据库 schema。

## Decisions

### D1: 新主模型使用 InputControlConfig

**决策**：用 `inputConfig` 描述参数输入方式，不再把新主模型命名为 `optionsConfig`。

```ts
type InputControlConfig =
  | {
      control: 'input';
    }
  | {
      control: 'select' | 'radio';
      optionsSource:
        | {
            type: 'static';
            staticItems: Array<{ label: string; value: string | number }>;
          }
        | {
            type: 'dynamic';
            sourceId?: number;
            sourceRef?: {
              type: 'rest_api';
              value: string;
            };
            valueField: string;
            labelField: string;
          };
    };
```

理由：

- `optionsConfig` 无法自然表达“普通输入框”。
- `select` 与 `radio` 共享选项来源，但控件形态不同，模型需要同时表达二者。
- `inputConfig` 更贴近组件配置和统一筛选的真实语义。

### D2: 内置默认使用 sourceRef/rest_api

**决策**：内置数据源参数可以在 `source_api.json` 中写：

```json
{
  "inputConfig": {
    "control": "select",
    "optionsSource": {
      "type": "dynamic",
      "sourceRef": {
        "type": "rest_api",
        "value": "cmdb/get_room_list"
      },
      "valueField": "_id",
      "labelField": "inst_name"
    }
  }
}
```

运行时按 `rest_api` 查找真实数据源 ID，再调用 `getSourceDataByApiId(id, {})`。

理由：

- 内置 JSON 不能写死数据库生成的 `sourceId`。
- `rest_api` 是内置数据源稳定标识，适合版本化声明。
- 比初始化时两阶段回填 ID 更简单、更透明。

### D3: 用户手动配置仍保存 sourceId

**决策**：用户在编辑器里选择数据源时，保存 `sourceId`，不生成 `sourceRef`。

理由：

- 用户选择的是数据库中的具体数据源实例。
- 保持 UI 手动配置路径简单。
- `sourceRef` 只承担内置声明职责。

### D4: 数据源管理参数表不提供编辑入口

**决策**：移除本分支早期在 `paramTable.tsx` 添加的“选项”列和配置弹窗。

理由：

- 数据源管理里的参数定义是全局默认，手工修改影响面大。
- 当前核心需求是内置数据源默认体验，不是开放全局默认配置。
- 自定义覆盖应发生在 widget 级或统一筛选级，风险更小。

### D5: 组件配置与统一筛选共用编辑器

**决策**：新增/改造 `paramInputConfigEditor.tsx`，组件配置抽屉和统一筛选都使用它。

编辑器内部结构：

1. 控件类型：输入框 / 下拉选择 / 单选按钮
2. 选项来源：自定义选项 / 数据源选项，仅在下拉或单选时出现

文件名小写开头；React 组件名保持 PascalCase：

```ts
export const ParamInputConfigEditor = ...
```

### D6: 运行时失败回退原始输入

**决策**：动态选项来源失败时，不禁用参数配置，而是回退到参数原始输入控件。

失败场景包括：

- `sourceRef/rest_api` 找不到对应数据源
- 请求选项源失败
- 返回数据为空
- 映射后没有可展示项

理由：

- 选项来源只是增强输入体验，不应阻断用户配置参数。
- 用户仍可打开配置 icon，将控件改为输入框、自定义选项或另一个数据源选项。

### D7: 旧 options 只做集中读取兼容

**决策**：保留旧 `options` 字段读取兼容，但只在 `normalizeInputConfig` 中处理。

规则：

```ts
if (entity.inputConfig) return entity.inputConfig;
if (entity.options?.length) {
  return {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: entity.options,
    },
  };
}
return undefined;
```

写入新配置时只写 `inputConfig`。

### D8: CMDB 机房列表作为首个 sourceRef 落地

**决策**：

- 后端新增 `cmdb/get_room_list`，返回 `{"items": [...]}`。
- 返回 CMDB 原始字段 `_id`、`inst_name` 等，不重命名。
- 服务层复用 `InstanceManage.instance_list(model_id="server_room", permission_map=...)`。
- `CMDB 3D机房布局.server_room_id` 默认 `inputConfig.control = "select"`，动态来源引用 `cmdb/get_room_list`。

## Runtime Flow

### 组件参数

```txt
DataSourceParamsConfig 渲染参数
  → 读取 widget.valueConfig.dataSourceParams[i].inputConfig
  → 若不存在，读取 dataSource.params[i].inputConfig
  → normalizeInputConfig
  → ParamInputControl 渲染 input/select/radio
```

用户保存组件配置时：

```txt
ParamInputConfigEditor onConfirm(config)
  → 写入 widget.valueConfig.dataSourceParams[i].inputConfig
```

不提供恢复默认按钮。

### 统一筛选

```txt
UnifiedFilterConfigModal 打开编辑器
  → 使用 ParamInputConfigEditor
  → 保存到 UnifiedFilterDefinition.inputConfig
UnifiedFilterBar 渲染
  → normalizeInputConfig(definition)
  → ParamInputControl 渲染 input/select/radio
```

### 动态选项

```txt
optionsSource.type === 'dynamic'
  → 有 sourceId：直接调用 getSourceDataByApiId(sourceId, {})
  → 有 sourceRef/rest_api：从数据源列表查 rest_api，得到 sourceId 后调用
  → 映射 label/value
  → 有选项：渲染 select/radio
  → 无选项或失败：回退原始输入控件
```

字段映射保持简单：

```ts
label = String(row[labelField] ?? '')
value = row[valueField]
```

不做复杂逐行过滤；最终无可展示选项即回退。

## Risks / Trade-offs

**[Risk] widget 覆盖后没有恢复默认按钮**
- 影响：用户若想恢复内置默认，需要重新配置同等配置。
- Mitigation：首版接受，避免复杂交互。

**[Risk] sourceRef 依赖数据源初始化完整性**
- 影响：若 `cmdb/get_room_list` 未初始化，控件会回退普通输入。
- Mitigation：回退不阻断配置；初始化流程和手动验证覆盖该场景。

**[Risk] 每次挂载都拉动态选项**
- 影响：频繁打开配置抽屉可能重复请求。
- Mitigation：首版不缓存，保持行为实时和实现简单。

## Migration

无数据库迁移。

旧 `options` 字段读取兼容；新写入只使用 `inputConfig`。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-13
goal: 为运营分析参数提供统一 inputConfig 输入配置；组件参数和统一筛选共用编辑器，内置数据源可通过 sourceRef/rest_api 声明动态选项来源
```

## Capability Deltas

### param-options-source

## Purpose

为运营分析参数提供统一输入配置能力。参数可声明为输入框、下拉选择或单选按钮；下拉与单选可使用静态选项或动态数据源选项。内置数据源可通过 `sourceRef/rest_api` 声明默认选项来源，组件配置与统一筛选使用一致的编辑器内部交互。

## ADDED Requirements

### Requirement: 统一参数输入配置模型

系统 SHALL 使用 `InputControlConfig` 表达参数输入方式，支持 `input`、`select`、`radio` 三种控件类型；当控件类型为 `select` 或 `radio` 时，系统 SHALL 支持静态选项和动态数据源选项两类来源。

#### Scenario: 普通输入框配置
- **WHEN** 参数配置为 `{ control: "input" }`
- **THEN** 系统按参数原始类型渲染输入控件，不读取选项来源

#### Scenario: 静态下拉配置
- **WHEN** 参数配置为 `control: "select"` 且 `optionsSource.type: "static"`
- **THEN** 系统使用 `staticItems` 渲染下拉选项

#### Scenario: 静态单选配置
- **WHEN** 参数配置为 `control: "radio"` 且 `optionsSource.type: "static"`
- **THEN** 系统使用 `staticItems` 渲染单选按钮

#### Scenario: 动态选项配置
- **WHEN** 参数配置为 `control: "select"` 或 `control: "radio"` 且 `optionsSource.type: "dynamic"`
- **THEN** 系统从配置的数据源拉取选项并映射为 `{ label, value }`

---

### Requirement: sourceRef/rest_api 内置来源声明

系统 SHALL 支持内置数据源参数通过 `sourceRef: { type: "rest_api", value: string }` 声明动态选项来源。运行时系统 SHALL 根据 `rest_api` 查找真实数据源 ID，再调用该数据源获取选项。

#### Scenario: 通过 rest_api 解析动态来源
- **WHEN** `inputConfig.optionsSource.sourceRef` 为 `{ type: "rest_api", value: "cmdb/get_room_list" }`
- **THEN** 系统从数据源列表中查找 `rest_api === "cmdb/get_room_list"` 的数据源
- **AND** 使用查到的数据源 ID 拉取选项数据

#### Scenario: sourceRef 找不到数据源
- **WHEN** 系统无法找到 `sourceRef.value` 对应的数据源
- **THEN** 参数控件回退为原始输入控件
- **AND** 参数配置入口仍可打开

#### Scenario: 用户手动配置保存 sourceId
- **WHEN** 用户在编辑器中选择某个数据源作为动态选项来源
- **THEN** 系统保存 `sourceId`
- **AND** 不生成 `sourceRef`

---

### Requirement: 统一编辑器

系统 SHALL 提供共享编辑器 `paramInputConfigEditor.tsx`，组件配置抽屉和统一筛选配置都使用该编辑器。编辑器 SHALL 先选择控件类型，再在下拉选择或单选按钮时选择选项来源。

#### Scenario: 选择控件类型
- **WHEN** 用户打开 `ParamInputConfigEditor`
- **THEN** 编辑器显示“输入框 / 下拉选择 / 单选按钮”三种控件类型

#### Scenario: 输入框不显示选项来源
- **WHEN** 用户选择“输入框”
- **THEN** 编辑器不显示选项来源配置

#### Scenario: 下拉或单选显示选项来源
- **WHEN** 用户选择“下拉选择”或“单选按钮”
- **THEN** 编辑器显示“自定义选项 / 数据源选项”两种选项来源

#### Scenario: 自定义选项
- **WHEN** 用户选择“自定义选项”
- **THEN** 编辑器允许用户维护 `{ label, value }` 列表

#### Scenario: 数据源选项
- **WHEN** 用户选择“数据源选项”
- **THEN** 编辑器允许用户选择数据源，并选择 value 字段和 label 字段

#### Scenario: 保存输入框配置
- **WHEN** 用户选择“输入框”并保存
- **THEN** 系统写入 `{ control: "input" }`

---

### Requirement: 数据源管理参数表不提供输入配置入口

系统 SHALL 不在数据源管理参数表中提供参数输入配置编辑入口。数据源管理参数表 SHALL 只维护参数名、类型、默认值、过滤类型等基础字段。

#### Scenario: 参数表无选项列
- **WHEN** 用户打开数据源管理参数表
- **THEN** 表格不显示本变更新增的“选项”列或参数输入配置按钮

#### Scenario: 数据源定义仍可携带 inputConfig
- **WHEN** 数据源来自 `source_api.json` 且参数包含 `inputConfig`
- **THEN** 系统保存并返回该字段
- **AND** 数据源管理参数表不提供手动编辑该字段的 UI

---

### Requirement: 组件配置抽屉消费与覆盖 inputConfig

系统 SHALL 在组件配置抽屉中消费数据源参数定义自带的 `inputConfig`，并允许 widget 级覆盖写入 `ViewConfigItem.valueConfig.dataSourceParams[i].inputConfig`。

#### Scenario: 继承数据源定义 inputConfig
- **WHEN** widget 参数没有自己的 `inputConfig`
- **AND** 数据源参数定义存在 `inputConfig`
- **THEN** 组件配置抽屉使用数据源参数定义的输入配置渲染控件

#### Scenario: widget 级覆盖
- **WHEN** 用户在组件配置抽屉中打开参数配置并保存
- **THEN** 系统写入 `widget.valueConfig.dataSourceParams[i].inputConfig`
- **AND** 后续渲染优先使用 widget 级配置

#### Scenario: 覆盖为普通输入框
- **WHEN** 用户在组件配置抽屉中选择“输入框”并保存
- **THEN** 该 widget 参数后续渲染为普通输入控件

#### Scenario: 不提供恢复默认按钮
- **WHEN** 用户已经保存 widget 级覆盖
- **THEN** 编辑器不显示“恢复默认”按钮

---

### Requirement: 统一筛选使用同一编辑器与运行逻辑

系统 SHALL 让统一筛选配置使用 `paramInputConfigEditor.tsx`。统一筛选运行态 SHALL 通过同一套输入配置归一化与渲染逻辑处理 select 与 radio。

#### Scenario: 统一筛选编辑输入框
- **WHEN** 用户在统一筛选中选择“输入框”并保存
- **THEN** 筛选项保存 `inputConfig: { control: "input" }`

#### Scenario: 统一筛选编辑下拉
- **WHEN** 用户在统一筛选中选择“下拉选择”并配置选项来源
- **THEN** 筛选项保存对应 `inputConfig`
- **AND** 运行态渲染 Select

#### Scenario: 统一筛选编辑单选
- **WHEN** 用户在统一筛选中选择“单选按钮”并配置选项来源
- **THEN** 筛选项保存对应 `inputConfig`
- **AND** 运行态渲染 Radio.Group

#### Scenario: select 和 radio 都支持动态来源
- **WHEN** 统一筛选项的控件类型为 `select` 或 `radio`
- **AND** 选项来源为动态数据源
- **THEN** 两者都通过同一套动态选项解析逻辑获取选项

---

### Requirement: 动态选项失败回退原始输入

系统 SHALL 将动态选项来源视为输入增强。若来源不可用、请求失败、无数据或映射后无可展示选项，系统 SHALL 回退到该参数原始输入控件，而不是禁用参数配置。

#### Scenario: 动态来源请求失败
- **WHEN** 动态选项来源请求返回错误
- **THEN** 参数控件回退原始输入控件
- **AND** 用户仍可输入参数值

#### Scenario: 动态来源无选项
- **WHEN** 动态来源返回空数组或映射后无可展示项
- **THEN** 参数控件回退原始输入控件

#### Scenario: 配置入口仍可用
- **WHEN** 动态来源失败导致控件回退输入框
- **THEN** 参数配置 icon 仍然可用

---

### Requirement: 旧 options 读取兼容

系统 SHALL 对旧 `options: Array<{ label, value }>` 做读取兼容。若实体没有 `inputConfig` 但存在旧 `options`，系统 SHALL 将其视为静态下拉配置。新写入配置 SHALL 只写 `inputConfig`。

#### Scenario: 读取旧 options
- **WHEN** 系统读取到旧 `options` 且没有 `inputConfig`
- **THEN** 系统归一化为 `control: "select"` 且 `optionsSource.type: "static"`

#### Scenario: 新配置写入
- **WHEN** 用户通过新编辑器保存配置
- **THEN** 系统只写入 `inputConfig`
- **AND** 不写入新的 `optionsConfig`

---

### Requirement: 内置选项源：CMDB 机房列表

系统 SHALL 注册 `CMDB 机房列表` 内置数据源，并让 `CMDB 3D机房布局.server_room_id` 默认通过 `sourceRef/rest_api` 使用该数据源作为下拉选项来源。

#### Scenario: 数据源列表中可见
- **WHEN** 用户打开“运营分析 → 数据源管理”数据源列表
- **THEN** 列表中能看到 `CMDB 机房列表`
- **AND** 其 `rest_api` 为 `cmdb/get_room_list`
- **AND** 其 `chart_type` 为空数组

#### Scenario: 机房 ID 默认下拉
- **WHEN** 用户在组件配置抽屉中选择 `CMDB 3D机房布局`
- **THEN** `server_room_id` 参数默认渲染为下拉选择
- **AND** 下拉选项来自 `cmdb/get_room_list`

#### Scenario: 数据源返回 CMDB 原始字段
- **WHEN** 后端 `cmdb/get_room_list` 被调用
- **THEN** 返回 `items: [{ _id: 1, inst_name: "机房A", model_id: "server_room", ... }]`
- **AND** 不重命名为 `id` 或 `name`

#### Scenario: 按当前用户权限过滤
- **WHEN** 当前用户没有某机房查看权限
- **THEN** 该机房不出现在 `cmdb/get_room_list` 返回列表中

#### Scenario: 复用 CMDB 现成权限过滤
- **WHEN** 服务层列出机房
- **THEN** 通过 `InstanceManage.instance_list(model_id="server_room", permission_map=...)` 复用权限过滤

---

### Requirement: 国际化

系统 SHALL 为统一参数输入配置编辑器、控件类型、选项来源、动态来源错误提示等 UI 元素提供中英文 i18n 文案。

#### Scenario: 切换语言文案同步
- **WHEN** 用户切换系统语言
- **THEN** 参数输入配置相关文案全部同步切换

## Work Checklist

## 1. 类型与工具函数

- [x] 1.1 在 `web/src/app/ops-analysis/types/dataSource.ts` 定义 `InputControlConfig`、静态选项来源、动态选项来源和 `SourceRef` 类型
- [x] 1.2 在 `ParamItem` 中新增 `inputConfig?: InputControlConfig`
- [x] 1.3 保留旧 `options` 字段读取兼容，不再新增/使用 `optionsConfig` 作为新主模型
- [x] 1.4 在 `web/src/app/ops-analysis/types/dashBoard.ts` 为 `UnifiedFilterDefinition` 新增 `inputConfig?: InputControlConfig`
- [x] 1.5 编写 `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts`
  - `normalizeInputConfig(entity)`
  - `resolveDynamicSourceId(...)`
  - `mapDynamicItems(...)`
- [x] 1.6 工具函数测试覆盖：已有 `inputConfig`、旧 `options`、空配置、`sourceId`、`sourceRef/rest_api`、动态数据映射

## 2. 统一编辑器 paramInputConfigEditor

- [x] 2.1 新增/替换 `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx`
- [x] 2.2 文件名使用小写开头，React 组件导出为 `ParamInputConfigEditor`
- [x] 2.3 编辑器第一段实现控件类型：输入框 / 下拉选择 / 单选按钮
- [x] 2.4 当控件类型为输入框时，不展示选项来源配置
- [x] 2.5 当控件类型为下拉选择或单选按钮时，展示选项来源：自定义选项 / 数据源选项
- [x] 2.6 自定义选项支持维护 `{ label, value }` 列表
- [x] 2.7 数据源选项支持选择数据源、拉取字段、选择 valueField 和 labelField
- [x] 2.8 用户手动选择数据源时保存 `sourceId`，不生成 `sourceRef`
- [x] 2.9 不提供“恢复内置默认”按钮
- [x] 2.10 Modal body 长内容使用 antd v5 `styles.body` 控制滚动，保证底部按钮可见
- [x] 2.11 添加/调整 zh 和 en i18n key

## 3. 运行渲染组件 paramInputControl

- [x] 3.1 新增/替换 `web/src/app/ops-analysis/components/paramInputControl.tsx`
- [x] 3.2 `control: "input"` 渲染原始参数类型对应输入控件
- [x] 3.3 `control: "select"` 解析选项并渲染 Select
- [x] 3.4 `control: "radio"` 解析选项并渲染 Radio.Group
- [x] 3.5 动态来源有 `sourceId` 时直接调用 `getSourceDataByApiId(sourceId, {})`
- [x] 3.6 动态来源有 `sourceRef/rest_api` 时先按 rest_api 解析真实数据源 ID，再调用 `getSourceDataByApiId`
- [x] 3.7 动态来源找不到、请求失败、无数据或映射后无可展示选项时，回退原始输入控件
- [x] 3.8 配置入口不因动态来源失败而消失

## 4. 数据源管理参数表收敛

- [x] 4.1 删除 `paramTable.tsx` 中本分支新增的“选项”列
- [x] 4.2 删除 `paramTable.tsx` 中的参数选项编辑 state、handler、Modal 调用
- [x] 4.3 确认数据源管理参数表不写入 `inputConfig`
- [x] 4.4 保持参数名、类型、默认值、过滤类型等原有能力不变

## 5. 组件配置抽屉接入

- [x] 5.1 在 `paramsConfig.tsx` 使用 `normalizeInputConfig` 读取参数输入配置
- [x] 5.2 读取优先级：widget 级 `dataSourceParams[i].inputConfig` 优先，其次数据源定义 `params[i].inputConfig`
- [x] 5.3 有 `inputConfig` 时使用 `paramInputControl.tsx` 渲染
- [x] 5.4 每行保留配置 icon，点击打开 `ParamInputConfigEditor`
- [x] 5.5 保存编辑器结果到 `widget.valueConfig.dataSourceParams[i].inputConfig`
- [x] 5.6 选择“输入框”并保存后，后续该 widget 参数使用普通输入控件
- [x] 5.7 不提供“恢复内置默认”交互

## 6. 统一筛选接入

- [x] 6.1 `unifiedFilterConfigModal.tsx` 使用 `ParamInputConfigEditor`
- [x] 6.2 新配置写入 `UnifiedFilterDefinition.inputConfig`
- [x] 6.3 删除/替换旧 `FilterOptionsModal` 调用
- [x] 6.4 `unifiedFilterBar.tsx` 通过 `normalizeInputConfig` 渲染 input/select/radio
- [x] 6.5 select 和 radio 都支持静态与动态来源
- [x] 6.6 修复 radio 只读取旧 `options` 的问题
- [x] 6.7 旧 `inputMode + options` 仅做读取兼容

## 7. CMDB 机房列表内置来源

- [x] 7.1 在 `server/apps/cmdb/services/rack_room.py` 保留/新增 `list_server_rooms(permission_map, user_info) -> list`
  - 复用 `InstanceManage.instance_list(model_id="server_room", ...)`
  - `page_size=1000`
  - `order="inst_name"`
  - 返回 CMDB 原始字段，不做 `_id` / `inst_name` 重命名
- [x] 7.2 在 `server/apps/cmdb/nats/nats.py` 保留/新增 `get_room_list(user_info=None, **kwargs)`
  - 复用 `_build_nats_permission_map(user_info)`
  - 返回 `{"items": [...]}`
- [x] 7.3 补充/调整后端测试，覆盖返回结构、权限过滤参数透传、空列表
- [x] 7.4 在 `source_api.json` 注册 `CMDB 机房列表`
- [x] 7.5 在 `CMDB 3D机房布局.server_room_id` 上声明 `inputConfig`
  - `control: "select"`
  - `optionsSource.type: "dynamic"`
  - `sourceRef: { type: "rest_api", value: "cmdb/get_room_list" }`
  - `valueField: "_id"`
  - `labelField: "inst_name"`

## 8. 清理旧实现命名

- [x] 8.1 删除或重命名 `paramOptionsEditor.tsx`
- [x] 8.2 删除或重命名 `paramOptionsSourceSelect.tsx`
- [x] 8.3 删除或重命名 `paramOptionsUtils.ts`
- [x] 8.4 将 i18n 命名从 `paramOptions.*` 收敛为参数输入配置语义
- [x] 8.5 清理不再需要的 `optionsConfig` 类型、变量名和注释

## 9. 验证

- [x] 9.1 执行 `NEXTAPI_INSTALL_APP=ops-analysis pnpm exec tsx <工具测试脚本>` 验证输入配置工具函数
- [x] 9.2 执行 `NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check`
- [x] 9.3 执行相关 CMDB 后端单测
- [ ] 9.4 手动验证：`CMDB 3D机房布局.server_room_id` 默认显示当前用户可见机房下拉
- [ ] 9.5 手动验证：动态来源失败时回退普通输入，参数仍可配置
- [ ] 9.6 手动验证：组件配置和统一筛选编辑器内部交互一致
- [ ] 9.7 手动验证：统一筛选 select/radio 都能使用静态和动态来源
- [x] 9.8 执行 `git diff --check`
