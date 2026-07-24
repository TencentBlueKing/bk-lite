# 地区资源概览数据源设计

## 背景

运营分析需要使用多个多值组件展示不同地区的资源概览。每个组件对应一个地区，组件内部按 CMDB 模型分类展示该地区的实例总数，例如“数据库 300、主机 200、中间件 100”。

地区由 CMDB 实例的标签字段表达。首版固定使用标签 key `region`，实例标签的完整存储形式为 `region:<地区值>`。地区的可选范围来自模型定义中的标签候选项，而不是仅从当前已有实例反推，因此尚无实例使用的地区也能被提前配置到组件中。

## 目标

1. 新增一个地区选项数据源，返回当前用户可见模型定义过的全部 `region` 标签候选值。
2. 新增一个地区资源概览数据源，接收一个地区值，按模型分类汇总该地区的实例数量。
3. 两个接口均遵循当前用户的模型权限、实例权限、组织范围、模型与分类可见性以及请求语言。
4. 地区资源统计过滤零值分类，并按实例数量从高到低返回。
5. 复用现有多值组件，由多个组件分别配置不同地区，不新增地区卡片组件。

## 非目标

- 不支持通过参数切换标签 key；首版固定为 `region`。
- 不从实例当前使用情况生成地区选项。
- 不修改现有模型分类、模型实例数量、`get_model_inst_statistics` 或 TopN 数据源。
- 不修改多值组件的数据格式、样式或渲染行为。
- 不开发一次返回全部地区的复合接口。
- 不治理单个实例同时配置多个不同 `region:*` 标签的异常数据。
- 不增加分页、Top N、缓存或新的地区排序配置。

## 方案选择

采用“专用地区概览服务 + 两个轻量 NATS 接口 + 两条运营分析数据源配置”。

专用服务负责模型标签候选解析和资源分类聚合；NATS handler 负责构造当前请求的权限与语言上下文、调用服务并返回数据源契约。该边界避免继续把标签解析和聚合规则堆入已经较大的 `server/apps/cmdb/nats/nats.py`，同时允许核心行为通过不依赖 NATS 的单元测试验证。

未采用以下方案：

- 直接在两个 NATS handler 内完成全部逻辑：改动文件少，但标签解析、权限和响应组装耦合，测试成本更高。
- 通用标签分析接口：虽然可通过 `tag_key` 支持更多场景，但超出首版固定 `region` 的需求，会引入额外参数和安全边界。

## 组件与职责

### 地区资源概览服务

建议新增一个聚焦服务文件，例如：

```text
server/apps/cmdb/services/region_resource_overview.py
```

该服务包含两个独立能力：

1. 从已经过权限和可见性过滤的模型中提取地区候选项。
2. 将按 `model_id` 聚合的地区实例数量汇总成按 `classification_id` 的多值数据。

服务不自行推导当前用户身份，不读取 HTTP/NATS 请求对象。调用方显式传入已解析的语言和权限映射，以保持职责清晰和测试隔离。

### NATS 接口

在 `server/apps/cmdb/nats/nats.py` 注册两个接口：

```text
cmdb/get_region_options
cmdb/get_region_resource_overview
```

handler 复用现有 `_build_nats_model_permission_map`、`_build_nats_permission_map`、`ClassificationManage`、`ModelManage` 和 `InstanceManage` 能力，不复制权限规则。

### 运营分析数据源定义

在 `server/apps/operation_analysis/support-files/source_api.json` 新增两条内置数据源：

- `CMDB地区列表`
- `地区资源概览`

第二条数据源通过稳定的 `rest_api` 引用第一条数据源，不依赖不同环境中的数据库 ID。

## 接口一：获取地区选项

### 路由

```text
cmdb/get_region_options
```

### 请求

无业务参数。用户、组织、下级组织范围和语言由现有 NATS 数据源上下文注入。

### 响应

```json
{
  "items": [
    { "label": "东区", "value": "东区" },
    { "label": "北区", "value": "北区" },
    { "label": "本部", "value": "本部" },
    { "label": "太湖总院", "value": "太湖总院" }
  ]
}
```

`label` 和 `value` 首版使用相同的地区名称。

### 查询与提取规则

1. 构造当前用户的模型权限映射。
2. 查询当前用户有权查看且 `is_visible=true` 的模型。
3. 查询 `is_visible=true` 的模型分类，只保留属于可见分类的模型。
4. 从每个模型的 `attrs` 中查找 `attr_id=tag` 且 `attr_type=tag` 的属性。
5. 解析标签属性的 `option.options` 候选数组。
6. 只保留 `key` 严格等于小写 `region` 的候选项。
7. 对 `value` 去除首尾空白，忽略空值。
8. 多个模型定义相同地区时按地区值去重。
9. 按地区名称升序排列，保证动态下拉选项稳定。
10. 即使候选地区暂无实例使用，也必须返回。

### 容错规则

- 旧模型的 `attrs` 可能是 JSON 字符串，也可能是已经解析的列表；服务应通过现有模型属性解析约定统一处理。
- 缺少 tag 属性、`option`、`options`、`key` 或 `value` 的模型/候选项直接忽略。
- `options` 不是数组、候选项不是对象或其他局部格式损坏时忽略该局部项，不使整个接口失败。
- 模型权限映射不存在或没有可见模型时返回 `{ "items": [] }`。
- 底层图查询或 NATS 异常不转换为空结果，沿用现有错误链路。

## 接口二：获取单地区资源概览

### 路由

```text
cmdb/get_region_resource_overview
```

### 请求

```json
{
  "region": "本部"
}
```

只接收地区值，不接受完整的 `region:本部` 标签字符串。

### 响应

```json
{
  "items": [
    { "label": "数据库", "value": 300 },
    { "label": "主机", "value": 200 },
    { "label": "中间件", "value": 100 }
  ]
}
```

响应直接符合现有多值组件的 `{items: [{label, value}]}` 契约。

### 验证与查询规则

1. 对输入的 `region` 去除首尾空白。
2. 空值直接返回 `{ "items": [] }`。
3. 使用接口一相同的模型权限和候选项口径验证地区是否对当前用户可见。
4. 未在当前用户可见模型候选项中定义的地区返回空结果；未知地区与无权地区使用相同响应，避免泄露存在性。
5. 将地区值构造成完整标签 `region:<地区值>`。
6. 构造当前用户的实例权限映射和组织范围。
7. 调用 `InstanceManage.group_inst_count`，使用完整标签过滤实例并按 `model_id` 在图数据库中聚合；不得先拉取全部实例到 Python。
8. 查询当前用户有权查看且 `is_visible=true` 的模型，只接受所属分类也为 `is_visible=true` 的模型。
9. 忽略统计结果中无权、隐藏、未知或缺少分类的模型。
10. 将同一 `classification_id` 下多个模型的实例数量相加。
11. 过滤分类总数为零的结果。
12. 分类名称使用当前请求语言对应的本地化名称。
13. 首先按实例数量降序；数量相同时按本地化分类名称升序。

实例标签过滤使用完整值：

```json
{
  "field": "tag",
  "type": "list[]",
  "value": ["region:本部"]
}
```

该过滤与实例权限条件在图查询中使用 AND 关系。

### 边界行为

- 地区已定义但暂无匹配实例：返回空 `items`。
- 匹配实例全部被权限、模型可见性或分类可见性过滤：返回空 `items`。
- 同一实例同时包含多个不同 `region:*` 标签时，会分别计入对应地区的独立查询结果；本次不负责修复标签数据。
- 底层服务异常继续抛出，由现有 NATS 数据源错误机制处理。

## 权限、可见性与本地化

### 地区选项

地区值只有在至少一个当前用户有权查看、模型可见且分类可见的模型标签候选项中定义时才返回。这样不会通过下拉选项泄露仅由无权或隐藏模型定义的地区。

### 资源统计

统计结果是以下条件的交集：

- 当前用户模型查看权限；
- 当前用户实例查看权限；
- 当前组织和“包含下级组织”范围；
- 模型 `is_visible=true`；
- 分类 `is_visible=true`；
- 实例标签包含指定的完整 `region:<value>`。

分类展示名称使用请求上下文语言。语言解析沿用 CMDB NATS 的现有 locale/language 约定，归一化为 CMDB `SettingLanguage` 可识别的语言值。

## 数据源一：CMDB 地区列表

```json
{
  "name": "CMDB地区列表",
  "desc": "返回当前用户可见模型定义的全部region标签候选值，供运营分析参数动态选项使用",
  "rest_api": "cmdb/get_region_options",
  "tag": ["cmdb"],
  "chart_type": [],
  "params": [],
  "field_schema": [
    {
      "key": "label",
      "title": "地区名称",
      "value_type": "string",
      "description": "region标签候选项的地区名称"
    },
    {
      "key": "value",
      "title": "地区值",
      "value_type": "string",
      "description": "传给地区资源概览接口的region参数值"
    }
  ]
}
```

该数据源只作为动态选项源，不直接提供图表类型。

## 数据源二：地区资源概览

```json
{
  "name": "地区资源概览",
  "desc": "按region标签统计当前权限范围内各CMDB模型分类的实例数量",
  "rest_api": "cmdb/get_region_resource_overview",
  "tag": ["cmdb"],
  "chart_type": ["multiValue"],
  "params": [
    {
      "name": "region",
      "type": "string",
      "value": "",
      "alias_name": "地区",
      "filterType": "params",
      "required": true,
      "inputConfig": {
        "control": "select",
        "optionsSource": {
          "type": "dynamic",
          "sourceRef": {
            "type": "rest_api",
            "value": "cmdb/get_region_options"
          },
          "valueField": "value",
          "labelField": "label"
        }
      }
    }
  ],
  "field_schema": [
    {
      "key": "label",
      "title": "资源分类",
      "value_type": "string",
      "description": "当前语言下的CMDB模型分类名称"
    },
    {
      "key": "value",
      "title": "实例数量",
      "value_type": "number",
      "description": "指定地区和当前权限范围内的分类实例总数"
    }
  ]
}
```

动态选项通过 `sourceRef.rest_api` 引用地区列表数据源，避免不同环境中的数据库 ID 差异。

## 页面配置方式

一个多值组件对应一个地区。组件均选择“地区资源概览”数据源，但分别保存不同参数：

```json
{ "region": "本部" }
```

```json
{ "region": "东区" }
```

```json
{ "region": "北区" }
```

组件标题由页面配置人员分别设置为“本部”“东区”“北区”等。本次不增加根据参数自动生成标题的逻辑。

## 数据流

```text
组件配置加载地区参数
  → 调用 cmdb/get_region_options
  → 从有权可见模型的tag候选项提取region值
  → 用户选择并保存一个region
  → 组件调用 cmdb/get_region_resource_overview
  → 验证region候选可见性
  → 图查询按region完整标签过滤并按model_id聚合
  → 过滤有权可见模型和分类
  → 按classification_id累加
  → 过滤零值并降序
  → 返回{items:[{label,value}]}
  → 现有multiValue组件渲染
```

## 测试设计

### 地区候选解析服务

- 从一个模型的多个候选标签中只提取 `key=region`。
- 从多个模型提取、去重并按名称升序。
- 没有实例使用的候选地区仍返回。
- 大小写不是小写 `region` 的 key 被忽略。
- 空 value、非对象候选项、非数组 options 和损坏 attrs 被局部忽略。
- 没有 tag 属性时返回空列表。

### 地区资源聚合服务

- 实例查询参数使用完整 `region:<value>` 和 `tag/list[]` 条件。
- 实例权限映射和组织范围传递给图聚合服务。
- 多个模型属于同一分类时正确累加。
- 未知、无权、隐藏或缺少分类的模型统计被忽略。
- 隐藏分类不返回。
- 零值分类被过滤。
- 数量按降序排列，同值按本地化分类名称升序。
- 中英文请求使用对应分类名称。

### NATS handler

- 模型权限为空时地区选项返回空 `items`。
- 空、未知或无权 region 返回空 `items`。
- 实例权限为空时资源统计返回空 `items`。
- 服务成功结果按数据源契约封装。
- 服务异常不被 handler 吞掉。

### 数据源定义

- `source_api.json` 保持合法 JSON。
- 两条数据源能由 `init_source_api_data` 导入。
- 地区列表数据源的 `chart_type` 为空。
- 地区资源概览只支持 `multiValue`。
- `region` 参数必选，并通过 `cmdb/get_region_options` 的稳定 `rest_api` 引用加载动态选项。
- 两条数据源的 `field_schema` 与实际 `label/value` 类型一致。

### 回归

- 现有模型分类、模型实例数量、`get_model_inst_statistics` 和 TopN 接口行为不变。
- 现有 multiValue 数组、`items` 和 `data.items` 响应继续正常渲染。
- 普通仪表盘、大屏和拓扑仍共享同一个多值组件实现。

## 验收标准

1. 配置“地区资源概览”多值组件时，地区参数以下拉框展示当前用户可见模型定义的所有 `region` 候选值。
2. 暂无实例的候选地区也出现在下拉框中。
3. 每个组件可以独立保存一个地区，并由配置人员设置对应标题。
4. 组件只展示该地区下当前权限范围内、可见模型和可见分类的实例汇总。
5. 同一分类下多个模型的数量正确累加。
6. 零值分类不展示。
7. 分类按数量从高到低排列；同值顺序稳定。
8. 未知、无权或无数据地区显示正常空状态，不泄露存在性。
9. 现有数据源和多值组件行为不受影响。
