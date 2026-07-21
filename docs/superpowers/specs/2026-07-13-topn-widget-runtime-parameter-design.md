# 排行榜组件内运行时参数与多排行主体切换设计

日期：2026-07-13
范围：运营分析排行榜（TopN）组件、数据源参数配置、云资源费用分布数据源
状态：设计已确认，进入实施计划

## 1. 背景与问题

当前排行榜通过组件配置中的 `topNLabelField` 和 `topNValueField`，从一次数据源请求结果中读取名称和值。一个组件实例只能展示一个固定分组结果。

费用分布场景需要在同一个排行榜顶部切换“对象类型、使用部门、申请人”。切换后不仅标题变化，后端分组字段、数据项、排序和占比都要重新计算。因此它不是前端筛选，也不是同一份结果的字段切换，而是一次由组件内部交互触发的新查询。

当前项目已经具备部分基础能力：

- 数据源参数通过 `params` JSON 声明，运行时请求只能覆盖已声明的参数名。
- `_resolve_request_params` 只有对 `fixed` 参数强制使用默认值，其余参数均可从请求覆盖，因此不需要修改后端通用查询协议。
- `WidgetWrapper` 已统一处理请求签名、缓存、并发请求复用和过期响应丢弃。
- `ComTopN` 已支持从数组、`items` 或 `data` 中读取排行行，但云费用当前返回 `{ group_by, groups }`，两者不匹配。
- 云费用数据源当前把 `total_cost`、`pct` 声明为字符串，排行榜的数值字段选择器只接收 number 字段，导致 `total_cost` 无法被选为数值字段。本需求必须修正 schema，并以 `total_cost` 作为费用排行榜的数值字段；`instance_count` 只是随行辅助指标。
- `ParamItem.options` 和通用参数渲染层虽有残留支持，但数据源设置页没有选项编辑入口，保存时也不会保留 `options`；它不能作为本功能的选项配置来源。

## 2. 目标

1. 一个排行榜组件实例可以配置多个排行主体选项。
2. 排行主体选项显示在排行榜顶部，默认展示配置中的默认项。
3. 用户切换选项时，将对应值写入一个数据源运行时参数并重新请求数据。
4. 新响应到达后，名称、数值、排序和进度条全部使用新数据。
5. 运行时选中值只属于当前组件实例，不影响画布中的其他组件，也不写回持久化配置。
6. 编辑态和预览态使用同一套切换、请求和渲染逻辑。
7. 底层配置协议保持通用，但第一期只由排行榜消费，并且一个排行榜只绑定一个组件内运行时参数。
8. 历史排行榜不需要迁移或重新配置。

## 3. 非目标

1. 不在前端对云费用明细做聚合、排序或占比计算。
2. 不把选项配置加入数据源设置页，也不补齐数据源参数的通用 `options` 编辑能力。
3. 不让排行榜直接配置原始数据的多个 `categoryField` / `valueField` 组合。
4. 第一期不支持一个组件同时出现多个运行时参数控件。
5. 第一期不向后端查询参数的合法选项，不做动态选项发现接口。
6. 第一期不把该控件开放给折线图、饼图、表格等其他组件。
7. 不改变画布级统一筛选器；组件内切换与统一筛选互相独立。

## 4. 方案比较

### 方案 A：数据源声明参数，组件实例配置选项，切换时重新请求（推荐）

数据源仅把 `group_by` 声明为可由组件控制；排行榜侧边栏配置选项、默认值和展示顺序。运行时值在统一取数层覆盖该参数。

优点：职责清晰；不需要扩展数据源 `options` 编辑器；每个组件实例可以有不同选项；复用现有请求缓存和竞态保护；未来其他组件可以复用同一协议。

缺点：组件侧栏填写的值可能不被具体接口支持，需要前端结构校验和后端明确报错共同兜底。

### 方案 B：选项也配置在数据源中，组件只能引用或裁剪

优点：数据源可以成为参数合法值的单一事实来源。

缺点：必须补齐数据源选项编辑、保存、校验、默认值一致性和迁移逻辑；组件实例的个性化配置也会变复杂。本期收益不足以覆盖改动范围。

### 方案 C：排行榜配置多个字段并在前端重新聚合

优点：切换不必请求后端。

缺点：需要把明细数据下发到前端；统计口径、权限、数据量和排序逻辑容易与后端不一致；不适合云费用场景。

最终选择方案 A。

## 5. 总体架构

```text
数据源设置
  声明 group_by，filterType = widget
             │
             ▼
排行榜配置侧栏
  绑定 group_by
  配置 label/value/defaultValue/order
             │ 保存到当前组件 valueConfig
             ▼
排行榜运行时控件
  用户点击“使用部门”
             │ runtimeParams.group_by = department
             ▼
WidgetWrapper 统一取数层
  合并参数、生成请求签名、发起请求、丢弃过期响应
             │
             ▼
云费用数据源
  按 department 聚合、按 total_cost 降序、计算 pct
             │
             ▼
标准 TopN 行数组
  [{ key, total_cost, instance_count, pct }]
             │
             ▼
ComTopN 使用既有 labelField/valueField 渲染
```

职责边界：

- 数据源定义“哪些参数允许被组件内部交互修改”。
- 组件配置定义“当前组件向用户提供哪些选项”。
- `WidgetWrapper` 管理运行时值和请求生命周期。
- `ComTopN` 只负责控件展示、交互回调和排行渲染。
- 具体数据源负责校验参数值并重新聚合。

## 6. 配置协议

### 6.1 数据源参数声明

给 `filterType` 增加值 `widget`，设置页中文名称为“组件内交互”。

```ts
interface ParamItem {
  name: string;
  alias_name: string;
  type?: string;
  value: string | number | boolean | [number, number] | null;
  filterType?: 'filter' | 'fixed' | 'params' | 'widget';
}
```

云费用分布数据源中的声明：

```json
{
  "name": "group_by",
  "alias_name": "排行主体",
  "type": "string",
  "value": "instance_type",
  "filterType": "widget"
}
```

`widget` 只表示该参数允许被组件内部交互覆盖，不携带选项。现有后端把所有非 `fixed` 的已声明参数视为可覆盖参数，因此通用请求协议不需要增加分支。

### 6.2 组件实例配置

在 `ValueConfig` 中增加一个可选的单控件配置：

```ts
export interface RuntimeParamOption {
  label: string;
  value: string | number;
}

export interface RuntimeParamControl {
  paramName: string;
  controlType: 'segmented';
  defaultValue: string | number;
  options: RuntimeParamOption[];
}

export interface ValueConfig {
  // 既有字段保持不变
  runtimeParamControl?: RuntimeParamControl;
}
```

云费用排行榜组件示例：

```json
{
  "chartType": "topN",
  "topNLabelField": "key",
  "topNValueField": "total_cost",
  "runtimeParamControl": {
    "paramName": "group_by",
    "controlType": "segmented",
    "defaultValue": "instance_type",
    "options": [
      { "label": "对象类型", "value": "instance_type" },
      { "label": "使用部门", "value": "department" },
      { "label": "申请人", "value": "user" }
    ]
  }
}
```

第一期使用单对象而不是数组，明确限制一个排行榜只有一个内部切换控件，避免提前引入控件布局、参数联动和组合查询问题。

### 6.3 配置合法性

保存组件配置时必须满足：

1. `paramName` 对应当前数据源中一个 `filterType === 'widget'` 的参数。
2. `options` 至少包含一个选项。
3. 每个 `label` 非空。
4. 每个 `value` 非空，且同一控件内唯一。
5. `defaultValue` 必须命中某个选项值。
6. 第一期 `controlType` 固定为 `segmented`。

切换数据源或图表类型后，如果原配置不再合法，侧边栏清除 `runtimeParamControl`，不把失效绑定静默保存。

## 7. 配置侧边栏交互

排行榜既有“名称字段”和“数值字段”配置保持不变，在其下新增“组件内切换”区域。

1. 当前数据源不存在 `widget` 参数：整个“组件内切换”区域不显示，不展示空状态或说明文案。
2. 存在 `widget` 参数：显示启用开关。
3. 启用后显示：
   - 参数选择：候选项只来自当前数据源的 `widget` 参数；只有一个时自动选中。
   - 选项编辑：每行包含“显示名称”和“参数值”，支持新增、删除和调整顺序。
   - 默认项：从已配置选项中选择。
4. 关闭开关时删除当前组件的 `runtimeParamControl`，但不修改数据源参数。
5. 选项顺序就是排行榜顶部的展示顺序。

数据源设置页只在“参数用途”下拉列表增加“组件内交互”，不新增任何 `options` 列、弹窗或编辑器。

## 8. 运行时状态与数据获取

### 8.1 状态归属

运行时当前值由每个 `WidgetWrapper` 实例独立维护：

```ts
runtimeParams = {
  [runtimeParamControl.paramName]: activeValue
}
```

它不是画布全局状态，不进入统一筛选状态，也不会在用户点击时写回 `valueConfig`。重新打开页面时回到配置的默认项。

初始化优先级：

1. `runtimeParamControl.defaultValue` 合法时使用它。
2. 否则使用数据源参数默认值，但仅当它命中组件选项。
3. 否则使用第一个选项。

正常通过侧边栏保存的配置必须满足第 1 条；第 2、3 条用于防御手工数据和异常历史配置。

### 8.2 参数合并优先级

最终请求参数优先级从低到高为：

```text
数据源默认参数
  < 组件保存的 dataSourceParams
  < 统一筛选绑定值
  < 表格分页/命名空间等系统运行时参数
  < 当前组件 runtimeParams
```

`runtimeParams` 只能包含当前组件绑定且由数据源声明为 `widget` 的参数，不能借此覆盖任意参数、`namespace_id` 或表格分页参数。

### 8.3 请求和竞态

用户切换选项后：

1. 立即更新当前组件的 `activeValue`。
2. `runtimeParams` 参与请求参数和请求签名计算。
3. 请求签名变化触发现有 `WidgetWrapper` 取数流程。
4. 缓存键包含 `group_by`，不同排行主体不会复用错误数据。
5. 继续使用现有 `fetchIdRef` 丢弃晚到的旧响应，快速连续点击时只渲染最后一次选择。
6. 切换加载期间保留顶部切换控件并展示内容区加载状态，避免整个组件被全局 Spin 替换后用户失去当前选择反馈。
7. 请求失败时保留已选项，内容区展示现有错误态；再次切换或刷新可以重试。

组件配置变化、数据源变化或组件重新挂载时，重新按初始化规则建立运行时状态。

## 9. TopN 数据契约

### 9.1 通用契约

排行榜继续使用 `topNLabelField` 和 `topNValueField`，数据源最终返回行数组：

```json
[
  {
    "key": "运维部",
    "total_cost": 12800.25,
    "instance_count": 36,
    "pct": 32.10
  }
]
```

约束：

- `key`：字符串，当前分组项的展示名称。
- `total_cost`：数字，费用合计。
- `instance_count`：数字，当前分组的实例数。
- `pct`：数字，范围为 `0..100`，不是 `0..1`。
- 服务端按 `total_cost DESC` 排序；排行榜不重新定义业务排序。
- 空结果返回 `[]`。

云费用排行榜的字段配置固定为：

```json
{
  "topNLabelField": "key",
  "topNValueField": "total_cost"
}
```

`instance_count` 和 `pct` 可以保留在标准行中供后续展示扩展使用，但本需求不使用 `instance_count` 作为排行榜数值字段。字段选择器必须依据修正后的 `field_schema` 将 `total_cost` 提供为可选数值字段。

### 9.2 云费用适配

`CloudCostService.distribution` 仍处于未定稿阶段，因此直接把返回结构改成标准 TopN 行数组，不再保留 `{ group_by, groups }` 包装：

```python
[
    {
        "key": "运维部",
        "total_cost": 12800.25,
        "instance_count": 36,
        "pct": 32.10,
    }
]
```

费用计算过程仍可使用 `Decimal` 保证精度，但 Service 返回的 `total_cost`、`pct` 应转换为可序列化为 JSON number 的数值，`instance_count` 返回整数。NATS 发布函数 `get_cloud_resource_cost_distribution` 只负责调用 Service 和包装统一的 NATS 成功响应，不再进行 `groups` 解包或领域结构转换。

数据源 `field_schema` 固定声明：

```json
[
  { "key": "key", "value_type": "string" },
  { "key": "total_cost", "value_type": "number" },
  { "key": "instance_count", "value_type": "number" },
  { "key": "pct", "value_type": "number" }
]
```

## 10. 前后端改动边界

### 10.1 前端

| 文件或模块 | 设计改动 |
|---|---|
| `types/dataSource.ts` | 收紧并扩展参数用途类型，加入 `widget` |
| 数据源 `paramTable.tsx` 与中英文 locale | 参数用途下拉增加“组件内交互”；不增加 options 编辑 |
| `types/dashBoard.ts`、`types/topology.ts` | 增加 `RuntimeParamControl` 配置类型并保证仪表盘、拓扑配置链路载入时不丢字段 |
| `widgetConfig.tsx`、`widgetConfig/utils/submitConfig.ts` | 加载、校验、保存、切换数据源时清理运行时控件配置 |
| `widgetConfig/sections/topNSettingsSection.tsx` | 增加排行榜组件内切换配置区域；复杂编辑 UI 拆成独立小组件 |
| Dashboard/Screen 的配置复制与持久化映射 | 显式透传 `runtimeParamControl`，避免布局保存时被字段白名单丢弃 |
| `widgetDataRenderer.tsx` | 持有当前组件运行时值，合并到请求与签名，调整二次加载状态 |
| `widgetRenderer.tsx` | 向 TopN 传递当前值、配置和变更回调 |
| `widgets/comTopN.tsx` | 渲染顶部 Segmented，并在加载、空数据、错误前保持控件区域 |
| `utils/widgetDataTransform.ts` | 明确并测试运行时参数最高优先级及参数白名单 |
| TopN 数据校验 | 继续校验标准行数组，不加入 `groups` 专属兼容 |

Dashboard、Screen、Topology 中所有保存或复制排行榜 `ValueConfig` 的显式字段映射都必须透传新字段；Topology 本期不新增专属配置界面，只保证共享排行榜配置不会被其类型和复制链路截断。

### 10.2 后端与数据源

通用数据源查询协议不需要修改，也不需要数据库结构迁移。需要调整：

| 文件或模块 | 设计改动 |
|---|---|
| `support-files/source_api.json` | 云费用分布的 `group_by.filterType` 改为 `widget`；修正字段类型 |
| 数据源初始化/数据迁移 | 将已存在的内置云费用数据源同步为新参数声明和 schema |
| `CloudCostService.distribution` | 直接返回标准 TopN 行数组，保留分组映射、聚合、降序和非法 `group_by` 校验，并输出正确数值类型 |
| `cmdb/nats/nats.py` | 透传 Service 的标准数组并包装 NATS 成功响应，不再处理 `groups` |

## 11. 历史兼容

### 11.1 历史排行榜

历史配置通常只有：

```json
{
  "topNLabelField": "model",
  "topNValueField": "count"
}
```

由于 `runtimeParamControl` 是可选字段：

- 缺少该字段时不渲染切换控件。
- 请求参数、排序、字段映射和展示完全沿用现状。
- 不需要把旧配置转换成单选项配置，也不需要用户重新保存。

### 11.2 历史云费用组件

已有组件如果保存了 `group_by` 值但没有 `runtimeParamControl`，仍按该值展示单一排行榜。内置数据源从 `params` 改成 `widget` 后，后端依然允许请求覆盖它；组件内没有运行时控件时不会自动出现切换项。

### 11.3 异常配置降级

当 `runtimeParamControl` 异常时按以下规则降级：

- 绑定参数不存在、选项为空、label/value 非法或 value 重复：运行态忽略该控件并按普通单维度排行榜请求。
- 仅 `defaultValue` 未命中 options，但参数和选项本身合法：按 8.1 的初始化优先级回退到命中 options 的数据源默认值，否则使用第一个选项。
- 编辑侧栏显示校验提示，用户修正后才能保存新的配置。
- 不因无效控件配置阻断历史排行榜的基础展示。

## 12. 错误处理

1. 组件侧栏阻止空 label、空 value、重复 value 和默认项失配。
2. 运行态只发送数据源已声明的 `widget` 参数，避免绕过参数白名单。
3. 云费用服务对不支持的 `group_by` 返回明确错误，支持值为 `instance_type`、`department`、`user`。
4. 接口失败沿用组件现有错误态，不回退到上一个选项的数据并伪装成功。
5. 响应字段缺失或数值不可转换时沿用 TopN 数据格式错误提示。
6. 某分组无数据时返回空数组，显示空状态，不视为请求失败。

## 13. 测试策略

### 13.1 前端单元测试

- `runtimeParamControl` 校验：合法配置、空选项、重复值、默认值失配、绑定非 `widget` 参数。
- 参数合并：运行时值覆盖组件保存值；不能覆盖未声明参数；统一筛选不覆盖组件运行时参数。
- 请求签名：切换 `group_by` 后签名和缓存键变化。
- 状态初始化：配置默认值、数据源默认值和首选项三个优先级分支。
- 历史配置：无 `runtimeParamControl` 时请求和渲染与原行为一致。

### 13.2 前端组件测试

- 侧边栏只列出 `filterType=widget` 的参数。
- 保存、重新打开和复制组件后选项顺序及默认值保持。
- TopN 默认选中第一/默认主体并发起对应请求。
- 点击不同选项后重新请求并替换排行数据。
- 快速连续切换时只显示最后一个响应。
- 切换加载中控件仍可见，错误态和空状态不丢失当前选中项。
- 两个使用同一数据源的排行榜分别切换时互不影响。
- 编辑态与预览态行为一致。

### 13.3 后端测试

- 三个合法 `group_by` 分别使用正确账单字段聚合。
- 按 `total_cost` 降序，`pct` 使用 `0..100` 口径，实例数口径保持一致。
- 非法 `group_by` 返回清晰失败。
- `CloudCostService.distribution` 直接返回数组，不再包含 `group_by` 和 `groups` 包装。
- NATS 发布结果透传该数组，`total_cost`、`instance_count`、`pct` 均为 JSON number。
- 云费用排行榜的 `topNValueField` 为 `total_cost`，字段选择器不能因为 schema 类型错误而只允许选择 `instance_count`。
- 内置数据源初始化或迁移后，`group_by.filterType=widget` 且 field schema 类型正确。
- 费用汇总、费用分布、账单明细三组件的总费用一致性测试继续通过。

### 13.4 验证门禁

- Web：相关单测、`pnpm lint`、`pnpm type-check`。
- Server：云费用及数据源相关测试，之后执行对应模块测试门禁。
- 手工验收：同一画布放置两个费用排行榜，分别切换主体，并验证编辑态、预览态、刷新后的默认项和错误提示。

## 14. 实施步骤

1. 先补前后端失败测试，锁定参数声明、配置持久化、运行时覆盖和标准响应。
2. 增加 `widget` 参数用途及数据源设置页选项，不增加数据源 options 编辑能力。
3. 增加 `RuntimeParamControl` 类型、侧边栏编辑器、校验和配置透传。
4. 在 `WidgetWrapper` 增加实例级运行时状态和请求参数合并，复用现有缓存与竞态保护。
5. 在 `ComTopN` 增加切换控件并调整加载、空数据和错误布局。
6. 调整云费用 NATS 发布格式、字段数值类型和内置数据源声明。
7. 执行自动化测试、类型检查、lint 和双组件手工验收。

## 15. 风险与限制

1. **配置值与接口能力可能不一致**：选项归属组件后，前端无法自动知道后端支持值；由侧栏结构校验和接口白名单共同兜底。动态选项发现不在一期范围。
2. **配置字段可能在复制链路丢失**：Dashboard、Screen、Topology 存在显式字段复制，需要逐入口检查并测试。
3. **加载布局回归**：现有非表格组件加载时会整体返回 Spin；为保留切换控件，需要区分首次加载和已有数据后的切换加载。
4. **请求缓存污染**：运行时参数必须进入请求签名，否则不同主体会复用错误缓存。
5. **响应数值类型不一致**：Decimal 若序列化成字符串，会与 `field_schema:number` 冲突；`CloudCostService.distribution` 必须直接返回可序列化为 JSON number 的数值，NATS 层只透传。
6. **控件空间不足**：选项名称过长或数量过多时 Segmented 会拥挤。第一期允许横向滚动或自动换行，但不引入下拉模式；推荐控制在 2—5 项。
7. **服务端 TopN 数量**：当前费用分布返回全部分组，组件滚动展示。若后续数据量明显增大，再独立设计 `limit` 参数；本期不新增。

## 16. 验收标准

1. 数据源设置页可把参数用途设为“组件内交互”，但看不到 options 编辑入口。
2. 排行榜侧栏可绑定该参数并配置三个及以上 label/value 选项和默认项。
3. 保存后排行榜顶部出现对应切换项，默认项正确。
4. 每次切换都携带对应参数重新请求，服务端重新聚合和排序。
5. 返回结果按当前主体正确展示名称、值和进度条。
6. 同画布多个排行榜之间的选择和请求互不影响。
7. 编辑态、预览态均可切换；页面刷新后恢复配置默认项。
8. 无新配置的历史排行榜保持原样。
9. 云费用排行响应符合标准数组和数值类型契约。
10. 自动化测试、类型检查和相关质量门禁通过。

## 17. 规格自检

- 占位检查：无 TBD、TODO 或未决定的实现分支。
- 一致性检查：数据源不存 options；组件实例存 options；运行时由 `WidgetWrapper` 合并并重新请求；`CloudCostService.distribution` 直接输出标准 TopN 数组，NATS 层只透传，职责一致。
- 范围检查：协议通用、实现只开放排行榜；不扩展统一筛选、不支持多控件、不做动态选项发现。
- 兼容检查：新配置字段可选，历史排行榜零迁移；历史云费用组件无控件时继续单维度展示。
- 歧义检查：默认值优先级、参数覆盖优先级、百分比口径、数值类型、非法配置降级和加载行为均已明确。
