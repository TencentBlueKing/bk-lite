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
