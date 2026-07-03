# 监控对象字段展示列设计

## 背景

监控对象的“展示”配置目前只支持把指标值展示到对象列表中。现有配置保存在 `MonitorObject.display_fields`，前端在集成-对象-展示弹窗中配置展示列，后端在实例列表 `add_metrics=true` 时按配置回填指标值。

新的需求是支持展示指标返回序列里的维度字段值，例如采集节点 IP、设备型号等标签信息。这类列和现有指标值列的差异是：指标值列展示 VM value，字段展示列展示 VM metric labels 中指定 key 的值。

## 目标

- 将配置页现有“添加展示列”改名为“添加指标列”，语义对应展示指标值。
- 保留“添加展示列”入口，点击后新增字段展示列。
- 字段展示列同样支持多个模板/指标绑定。
- 字段展示列的每个绑定在模板和指标后增加“字段”配置，字段由用户手动输入。
- 字段输入右侧提供查询按钮，按当前所选指标实时查询 VictoriaMetrics 中该指标已有的字段 key，弹窗单选后回填字段输入框。
- 对象列表同时支持指标值列和字段展示列，并沿用多绑定按顺序取首个命中值的规则。

## 非目标

- 不新增数据库字段。
- 不依赖 `Metric.dimensions` 作为字段候选来源。
- 不强制修改 metrics.json 指标定义格式。
- 不做字段值预览、多字段拼接、模板化格式化或字段值单位转换。
- 不因为 VM 当前无数据而禁止保存手填字段。

## 数据模型

继续使用 `MonitorObject.display_fields` JSON 字段保存配置。

旧配置不带 `type`，默认视为指标值列：

```json
{
  "name": "CPU使用率",
  "sort_order": 0,
  "metrics": [
    { "plugin": "主机（Telegraf）", "metric": "cpu_usage" }
  ]
}
```

新增字段展示列增加 `type: "field"`，并在绑定上增加 `field`：

```json
{
  "name": "采集节点IP",
  "type": "field",
  "sort_order": 1,
  "metrics": [
    {
      "plugin": "主机（Telegraf）",
      "metric": "node_info",
      "field": "collector_ip"
    }
  ]
}
```

规则：

- `type` 缺省或为 `"metric"` 时，列展示指标值。
- `type` 为 `"field"` 时，列展示 VM label 字段值。
- 指标值列绑定要求 `plugin` 和 `metric`。
- 字段展示列绑定要求 `plugin`、`metric` 和 `field`。
- 保存时只校验 `plugin + metric` 是否存在；`field` 不校验是否存在于 VM，允许用户手填和提前配置。
- `sort_order` 继续决定对象列表展示顺序，两类列混合排序。

## 后端设计

### 保存校验

扩展 `apps.monitor.utils.display_fields.validate_display_fields`：

- 继续接受旧结构。
- 规整输出时为旧列补默认语义，不需要持久化 `type: "metric"`，但允许持久化以提升可读性。
- 字段展示列缺 `field` 时返回错误。
- 字段展示列的 `field` 仅做非空字符串规整，不查询 VM 校验。

### 对象列表回填

扩展 `MonitorObjectService._fill_display_metrics()` 的职责，使它能处理两种展示绑定：

- 指标值列：沿用当前查询逻辑，把 VM value 回填到 `插件::指标` 复合 key。
- 字段展示列：查询绑定指标，读取 VM 响应中每条序列的 `metric[field]`，回填到字段展示复合 key。

字段展示复合 key 使用独立前缀，避免与指标值列冲突：

```text
field::<plugin>::<metric>::<field>
```

字段展示列仍沿用当前插件隔离规则：

- 有 `CollectConfig` 的实例按采集配置归属插件。
- 上报型实例继续按插件 `status_query` 反查归属。
- 绑定了插件但实例不属于该插件时不回填该 key，前端显示 `--`。

字段展示列的查询也应尽量复用现有批量查询分组：同 query 和同 `instance_id_keys` 的绑定可以合并查询，再按绑定的插件和字段分发结果。

### VM 字段候选接口

新增一个用于配置弹窗的轻量接口：

```text
GET /monitor/api/metrics/{metric_id}/vm_fields/
```

接口行为：

- 根据 metric id 读取 `Metric.query`。
- 向 VictoriaMetrics 发起即时查询。
- 从 `data.result[].metric` 收集 label key。
- 去重并排序后返回字符串数组。
- 至少过滤 `__name__`。
- VM 当前无数据时返回空数组。
- VM 查询失败时返回错误，前端提示失败。

该接口只查 VM，不读取 `Metric.dimensions`。

## 前端设计

在 `web/src/app/monitor/(pages)/integration/object/displayFieldsModal.tsx` 中保持现有弹窗结构，按 A 方案扩展：

- 顶部原按钮“添加展示列”改名为“添加指标列”，新增 `type="metric"` 列。
- 旁边新增“添加展示列”，新增 `type="field"` 列。
- 列卡片中增加小标签展示列类型：`指标列` 或 `展示列`。
- 指标列绑定行保持 `模板 Select + 指标 Select + 删除`。
- 展示列绑定行使用 `模板 Select + 指标 Select + 字段 Input + 查询字段按钮 + 删除`。
- 字段 Input placeholder 为“请输入维度 key”。
- 查询字段按钮要求当前行已选择模板和指标；未选择时提示用户先选择。
- 查询成功后打开单选弹窗，展示 VM 返回字段 key。用户选中后回填当前绑定行的字段输入框。
- 查询无结果时显示空态或提示“未查询到字段”，仍允许手填。

对象列表渲染在 `viewList.tsx` 扩展：

- 根据列 `type` 决定解析 key。
- 指标值列沿用 `displayFieldKey(plugin, metric)`。
- 字段展示列使用 `displayFieldKey("field", plugin, metric, field)`，返回 `field::<plugin>::<metric>::<field>`，与后端 key 保持一致。
- 字段展示列按普通文本展示，不走进度条、枚举颜色、单位转换或维度 tooltip。
- 多绑定沿用现有规则：按绑定顺序取第一个非空值。

`viewHive.tsx` 如依赖 `display_fields` 的指标集合，应只把指标值列或所有绑定指标作为取数候选时谨慎处理，避免字段列破坏现有蜂窝视图逻辑。

## Storybook 视觉伴随与验收

实现阶段用 Storybook 承载配置弹窗关键状态，作为视觉伴随和验收入口：

- 默认已有指标列配置。
- 点击“添加展示列”后的字段输入态。
- 字段查询弹窗有结果态。
- 字段查询弹窗空态。
- 指标列和展示列混合排序、多模板多指标绑定态。

Storybook 场景应尽量复用真实组件和 mock API 数据，避免只做静态截图。

## 错误处理

- 保存字段展示列缺字段时，后端返回明确错误。
- VM 字段查询失败时，前端提示操作失败，保留用户已输入内容。
- VM 字段查询无结果时，不阻塞用户手填。
- 对象列表查不到字段值时显示 `--`。
- 旧配置缺 `type` 时按指标值列兼容。

## 测试计划

后端：

- 覆盖 `validate_display_fields` 的旧结构兼容、指标值列保存、字段展示列保存、字段展示列缺 `field` 报错。
- 覆盖字段展示列从 VM labels 取值并写入字段复合 key。
- 覆盖字段展示列按插件隔离，不串到其他插件实例。
- 覆盖 VM 字段候选接口：有数据、空数据、过滤 `__name__`、VM 查询失败。

前端：

- 覆盖两个新增按钮文案与新增列类型。
- 覆盖字段展示列绑定行出现字段输入和查询按钮。
- 覆盖字段查询弹窗单选回填。
- 覆盖字段列在对象列表按普通文本展示，缺值显示 `--`。
- 覆盖旧配置缺 `type` 时仍按指标值列渲染。

门禁：

- 后端改动后运行相关监控测试，必要时扩展到 `cd server && make test`。
- 前端改动后运行 `cd web && pnpm lint && pnpm type-check`。
- Storybook 场景用于人工视觉验收，不替代 lint/type-check。
