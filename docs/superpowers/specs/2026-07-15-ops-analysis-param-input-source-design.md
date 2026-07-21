# 运营分析参数输入与选项来源设计

日期：2026-07-15

## 背景

运营分析已有数据源参数、组件参数和统一筛选三类输入配置。当前分支尝试把参数选项从固定 `options` 扩展为动态数据源选项，但需要进一步收敛边界：

- 内置数据源应能声明参数选项来源，例如 `CMDB 3D机房布局.server_room_id` 自动使用 `CMDB 机房列表`。
- 组件配置抽屉和统一筛选必须使用一致的编辑体验，不能一个地方是下拉配置、另一个地方是单独的 radio/options 配置。
- 数据源管理参数表不再提供手动配置选项来源入口，避免把内置默认能力变成全局手工配置。
- 选项来源失败不能阻断参数配置，用户仍应能回到普通输入。

## 目标

- 建立统一的参数输入配置模型，覆盖输入框、下拉选择、单选按钮。
- 支持静态选项和动态数据源选项两类选项来源。
- 支持内置数据源用稳定的 `sourceRef/rest_api` 声明动态来源，不依赖数据库生成的 ID。
- 组件配置和统一筛选共用同一个编辑器内部交互。
- 删除数据源管理参数表里的选项配置入口，保持代码职责清晰。

## 非目标

- 不做数据源管理页面的全局选项来源手动编辑。
- 不做“恢复内置默认”按钮。
- 不做动态来源参数映射。
- 不做多种 `sourceRef` 类型，首版只支持 `rest_api`。
- 不做 TTL 缓存、选项快照或复杂空态过滤。

## 配置模型

新增统一内部模型 `InputControlConfig`：

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

语义：

- `control: 'input'`：普通输入控件，不使用选项来源。
- `control: 'select'`：以下拉选择展示选项。
- `control: 'radio'`：以单选按钮展示选项。
- `optionsSource.type: 'static'`：手动维护固定选项。
- `optionsSource.type: 'dynamic' + sourceId`：用户在 UI 中选择某个数据源后保存的运行时引用。
- `optionsSource.type: 'dynamic' + sourceRef/rest_api`：内置数据源声明的稳定引用。

字段命名建议：

- 类型文件中使用 `InputControlConfig`。
- 数据结构字段使用 `inputConfig`。
- 旧 `options` 只在归一化函数中读取兼容，写入新配置时不再写旧字段。

## 内置数据源声明

内置数据源在 `source_api.json` 中直接声明参数默认输入配置。

示例：`CMDB 机房列表` 作为选项源数据源：

```json
{
  "name": "CMDB 机房列表",
  "rest_api": "cmdb/get_room_list",
  "chart_type": []
}
```

示例：`CMDB 3D机房布局` 的 `server_room_id` 参数使用机房列表：

```json
{
  "name": "server_room_id",
  "type": "string",
  "value": "",
  "alias_name": "机房ID",
  "filterType": "params",
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

`sourceRef` 首版只支持：

```ts
{ type: 'rest_api'; value: string }
```

不支持按名称、标签或模型等方式查找，避免解析规则发散。

## 编辑器

新增/改造文件：

```txt
web/src/app/ops-analysis/components/paramInputConfigEditor.tsx
```

React 组件名保留 PascalCase：

```ts
export const ParamInputConfigEditor = ...
```

弹窗内部交互固定为两段。

第一段：控件类型

- 输入框
- 下拉选择
- 单选按钮

第二段：选项来源，仅当控件类型为下拉选择或单选按钮时显示

- 自定义选项
- 数据源选项

组件配置抽屉和统一筛选配置都使用这一个编辑器。它们可以在外层做数据结构适配，但编辑器内部的选项、文案、校验和保存语义必须一致。

## 持久化位置

### 数据源定义

内置默认写在数据源参数的 `inputConfig` 上，主要来自 `source_api.json` 初始化数据。

数据源管理参数表不提供 `inputConfig` 手动编辑入口，只维护参数名、类型、默认值、过滤类型等基础字段。

### 组件配置

组件配置抽屉读取优先级：

1. `widget.valueConfig.dataSourceParams[i].inputConfig`
2. 数据源定义 `dataSource.params[i].inputConfig`
3. 参数类型对应的默认输入控件

用户在组件配置抽屉里打开配置 icon 并保存后，写入 widget 级 `inputConfig`，表示该 widget 使用自己的输入配置。

选择“输入框”即保存：

```ts
{ control: 'input' }
```

不提供“恢复内置默认”按钮。

### 统一筛选

统一筛选也使用 `ParamInputConfigEditor`。新配置写入 `UnifiedFilterDefinition.inputConfig`。

旧的 `inputMode + options` 只做读取兼容，运行态通过统一的 `normalizeInputConfig` 转成 `InputControlConfig`。

统一筛选的 select 和 radio 必须走同一套运行渲染逻辑，避免 radio 只读旧 `options`。

## 运行渲染

新增/改造通用运行组件：

```txt
web/src/app/ops-analysis/components/paramInputControl.tsx
```

职责：

- `control: input`：渲染原始参数类型对应输入控件。
- `control: select`：解析选项后渲染 Select。
- `control: radio`：解析选项后渲染 Radio.Group。
- 动态来源失败或无可展示选项时，回退到原始输入控件。

选项解析建议收敛到工具或 hook：

```txt
web/src/app/ops-analysis/utils/paramInputConfigUtils.ts
```

核心函数：

```ts
normalizeInputConfig(entity): InputControlConfig | undefined
resolveDynamicSourceId(config): number | undefined
mapDynamicItems(items, valueField, labelField): Option[]
```

兼容规则集中在 `normalizeInputConfig`：

1. 有 `inputConfig`：直接使用。
2. 没有 `inputConfig`，但有旧 `options`：转为静态下拉。
3. 没有任何配置：返回 `undefined`，由调用方使用原始输入控件。

动态来源解析：

- 有 `sourceId`：直接调用 `getSourceDataByApiId(sourceId, {})`。
- 有 `sourceRef/rest_api`：先从数据源列表中找到 `rest_api` 相同的数据源 ID，再调用 `getSourceDataByApiId(id, {})`。
- 找不到、请求失败、返回空数组、映射后无选项：回退原始输入控件。

字段映射保持简单：

```ts
label = String(row[labelField] ?? '')
value = row[valueField]
```

不做复杂逐行过滤规则；最终没有有效选项就按失败处理，回退原始输入控件。

## 错误处理

原则：选项来源增强输入体验，但不能阻断参数配置。

- 内置选项源未初始化：回退普通输入。
- 动态请求失败：回退普通输入。
- 选项为空或字段不匹配：回退普通输入。
- 配置 icon 仍然可用，用户可以重新打开同一个弹窗，选择输入框、自定义选项或数据源选项。

## 当前分支调整范围

删除/收窄：

- 删除 `paramTable.tsx` 新增的“选项”列。
- 删除数据源参数表中的选项编辑 state、handler 和编辑器调用。
- 不在数据源管理页面写入 `inputConfig`。
- 不保留 `optionsConfig` 作为新主模型；改为 `inputConfig`。

保留/改造：

- 保留 `cmdb/get_room_list` 内置数据源和后端 NATS 能力。
- `source_api.json` 给 `CMDB 3D机房布局.server_room_id` 增加 `inputConfig.sourceRef/rest_api`。
- 组件配置抽屉保留参数配置 icon，但弹窗换成 `paramInputConfigEditor.tsx`。
- 统一筛选保留配置能力，并和组件参数共用同一个编辑器内部交互。
- 运行消费组件统一支持 input/select/radio。
- `getSourceDataByApiId` 继续作为动态来源拉取入口，确保支持 NATS 内置数据源。

## 测试设计

前端工具函数测试：

- `normalizeInputConfig` 直接返回已有 `inputConfig`。
- `normalizeInputConfig` 将旧 `options` 转为静态下拉。
- `normalizeInputConfig` 无配置时返回 `undefined`。
- `sourceId` 动态来源直接使用 ID。
- `sourceRef/rest_api` 能从数据源列表解析到 ID。
- `sourceRef/rest_api` 找不到时返回失败态，调用方回退原始输入。
- 动态 items 能按 `valueField` 和 `labelField` 映射。

前端手动验证：

- 组件配置中 `CMDB 3D机房布局.server_room_id` 默认显示机房下拉。
- 同一个弹窗可切换输入框、下拉选择、单选按钮。
- 下拉选择和单选按钮都可选择自定义选项或数据源选项。
- 选择输入框并保存后，第二次打开仍是输入框。
- 统一筛选 select 和 radio 都能消费静态与动态来源。
- 动态来源失败时参数仍可手动输入，配置 icon 仍可打开。

后端测试：

- `cmdb/get_room_list` 返回 `{"items": [...]}`。
- 返回 CMDB 原始字段 `_id`、`inst_name` 等，不做重命名。
- 复用 `InstanceManage.instance_list` 权限过滤。
- `source_api.json` 中 `CMDB 机房列表` 与 `CMDB 3D机房布局.server_room_id.inputConfig` 声明正确。

## 验收标准

- 数据源管理参数表没有选项配置入口。
- 组件配置和统一筛选使用一致的 `paramInputConfigEditor.tsx` 内部交互。
- 内置数据源可用 `sourceRef/rest_api` 声明参数选项来源。
- `CMDB 3D机房布局.server_room_id` 自动展示当前用户可见机房列表。
- 选项来源异常时不阻断配置，自动回退原始输入控件。
- 新写入配置只使用 `inputConfig`；旧 `options` 只作为读取兼容。
