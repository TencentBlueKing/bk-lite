# CMDB 模型分类与实例数量数据源设计

## 背景

运营分析组件参数支持从另一个数据源动态加载选项。现在需要按 CMDB 模型分类选择一个分类，再用多值组件展示该分类下各模型的实例数量。

本次变更同时扩展多值组件的数据提取能力，使其兼容运营分析常见的数据源响应包裹格式。

## 目标

1. 新增一个模型分类选项数据源，供组件参数下拉框使用。
2. 新增一个分类模型实例数量数据源，供多值组件使用。
3. 分类、模型和实例统计遵循当前用户权限、组织范围、可见性与语言设置。
4. 过滤实例数量为零的模型，并按数量从高到低返回。
5. 多值组件同时接受顶层数组、`items` 和 `data.items` 三种响应外形。

## 非目标

- 不修改现有 `get_model_inst_statistics` NATS 接口及其表格数据源。
- 不修改现有 `get_cmdb_model_instance_top` 接口。
- 不为多值组件增加自定义 label/value 字段映射。
- 不增加分页、Top N 限制或缓存。

## 方案选择

采用两个专用 NATS 接口和两条专用运营分析数据源配置。

该方案保持现有表格和 TopN 数据源行为不变，两个新接口各自只有一种稳定响应契约，也避免通过参数让同一接口返回多种不相干的数据结构。

## 接口一：模型分类选项

### 职责

返回当前用户可用于模型实例统计的 CMDB 模型分类，作为组件参数的动态选项源。

建议 NATS 路由：

```text
cmdb/get_model_classification_options
```

### 响应

```json
{
  "items": [
    {
      "classification_id": "middleware",
      "classification_name": "中间件"
    }
  ]
}
```

### 查询规则

1. 通过现有 CMDB 权限构建逻辑获取当前用户有权查看的模型。
2. 模型必须满足 `is_visible=true`；缺少旧数据字段时按可见处理。
3. 分类必须满足 `is_visible=true`；缺少旧数据字段时按可见处理。
4. 只返回至少包含一个当前用户有权查看且可见模型的分类。
5. 分类名称使用当前请求语言对应的本地化名称。
6. 顺序沿用 `ClassificationManage.search_model_classification()` 的分类顺序。
7. 无权限或无匹配分类时返回 `{ "items": [] }`。

### 运营分析数据源配置

新增“CMDB 模型分类列表”数据源。它作为参数选项源使用，至少声明以下字段：

```json
[
  {
    "key": "classification_id",
    "title": "模型分类ID",
    "value_type": "string"
  },
  {
    "key": "classification_name",
    "title": "模型分类名称",
    "value_type": "string"
  }
]
```

参数输入配置使用：

```json
{
  "type": "dynamic",
  "sourceRef": {
    "type": "rest_api",
    "value": "cmdb/get_model_classification_options"
  },
  "valueField": "classification_id",
  "labelField": "classification_name"
}
```

使用 `sourceRef.rest_api` 而不是数据库 ID，避免初始化环境之间的数据源 ID 差异。

## 接口二：分类模型实例数量

### 职责

接收分类 ID，统计该分类下当前用户可见模型的可见实例数量，并返回多值组件数据。

建议 NATS 路由：

```text
cmdb/get_classification_model_instance_counts
```

### 请求

```json
{
  "classification_id": "middleware"
}
```

`classification_id` 是必需的业务参数。缺失、空字符串、分类不存在、分类不可见或当前用户无权查看该分类下任何模型时，统一返回空结果，避免泄露对象是否存在。

### 响应

```json
{
  "items": [
    {
      "label": "Tomcat",
      "value": 100
    },
    {
      "label": "Nginx",
      "value": 10
    }
  ]
}
```

### 查询与排序规则

1. 使用现有 `_build_nats_model_permission_map` 构造模型权限范围。
2. 使用现有 `_build_nats_permission_map` 构造实例权限和组织范围。
3. 通过 `ModelManage.search_model` 查询指定分类下的模型，并沿用默认隐藏模型过滤。
4. 通过 `InstanceManage.model_inst_count` 按 `model_id` 聚合有权限实例的数量。
5. 过滤数量等于零的模型。
6. 模型名称使用当前请求语言对应的本地化名称，并映射到 `label`。
7. 实例数量映射到数值型 `value`。
8. 首先按 `value` 降序；数量相同时按本地化模型名称升序，保证结果稳定。
9. 无模型权限、无实例权限或无非零统计结果时返回 `{ "items": [] }`。
10. 查询或通信异常沿用现有 NATS 数据源错误链路，不转换成成功的空结果。

### 运营分析数据源配置

新增“分类模型实例数量”数据源：

- 图表类型仅允许 `multiValue`。
- 定义字符串参数 `classification_id`，并使用接口一作为动态选项源。
- 字段定义为 `label`（模型名称）和 `value`（实例数量）。
- 不配置分页或默认 Top N 限制。

## 多值组件响应兼容

### 支持的响应外形

顶层数组：

```json
[
  { "label": "Tomcat", "value": 100 }
]
```

`items`：

```json
{
  "items": [
    { "label": "Tomcat", "value": 100 }
  ]
}
```

`data.items`：

```json
{
  "data": {
    "items": [
      { "label": "Tomcat", "value": 100 }
    ]
  }
}
```

### 校验规则

1. 先从三种响应外形中抽取条目数组，再统一调用现有严格校验逻辑。
2. 每个条目必须显式包含 `label` 和 `value`。
3. 字符串和数字是合法值；数字统一转换为字符串展示。
4. `null`、`undefined` 和空字符串沿用现有行为，展示为 `--`。
5. 对象或数组等复杂 label/value 值使整组数据校验失败。
6. `items` 或 `data.items` 存在但不是数组时，判定为格式错误。
7. `{}`、`{ "data": null }` 等无法识别的对象判定为格式错误，不能伪装成空结果。
8. 三种外形中的空数组均是合法空数据，组件显示空状态。
9. 条目顺序与数据源返回顺序一致。

该抽取和校验逻辑继续由普通仪表盘、大屏和拓扑节点共享，避免不同宿主产生不一致行为。

## 数据流

```text
组件加载 classification_id 参数选项
  → 调用 CMDB 模型分类列表数据源
  → 用户选择 classification_id
  → 组件请求分类模型实例数量数据源
  → 应用模型权限、实例权限、组织范围和可见性
  → 按 model_id 聚合实例数
  → 过滤零值并降序排序
  → 返回 {items: [{label, value}]}
  → 多值组件抽取 items 并渲染
```

## 测试设计

### 后端

- 分类选项只返回可见且包含有权可见模型的分类。
- 分类名称遵循请求语言，顺序遵循 CMDB 分类顺序。
- 分类、模型、实例权限以及当前组织范围分别生效。
- 分类参数缺失、为空、不存在、不可见或无权限时返回空 `items`。
- 统计接口仅包含指定分类下的可见模型。
- 零实例模型被过滤。
- 结果按数量降序，数量相同时按本地化模型名称升序。
- 数值字段保持数字类型。
- 现有 `get_model_inst_statistics` 测试和内置表格配置保持不变。

### 前端

- 顶层数组继续通过校验。
- `items` 和 `data.items` 能正确抽取并通过校验。
- 三种空数组响应均是合法空数据。
- 非数组包裹、未知对象外形和非法条目显示格式错误。
- 数字转字符串、空值显示 `--` 的现有行为保持不变。
- 普通仪表盘、大屏与拓扑入口使用相同结果。

### 数据源定义

- 两条新数据源可以由初始化命令导入。
- 分类统计数据源的 `classification_id` 动态选项通过 `rest_api` 引用分类数据源。
- 分类统计数据源只出现在多值组件的数据源候选中。
- 现有模型实例统计表格数据源定义无变化。

## 验收标准

1. 用户可以在多值组件配置中选择“分类模型实例数量”数据源。
2. `classification_id` 参数以下拉框展示当前用户有权查看的可见分类。
3. 选择“中间件”后，组件只展示该分类中实例数大于零的可见模型。
4. 结果从高到低排列，例如 Tomcat 100 在 Nginx 10 之前。
5. 无结果时显示正常空状态，无权限信息泄露。
6. 现有模型实例统计表格行为不变。
7. 既有顶层数组多值数据源以及新增的两种包裹响应均可正常渲染。
