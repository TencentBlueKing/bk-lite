# 运营分析通用卡片列表 Card List MVP

Status: implemented

## Problem Statement

运营分析需要一种通用的记录型展示组件：把一组普通 records 按有限信息层次呈现为卡片，强调单条记录的主次扫描，而不是字段横向对比。

现有 Table 适合高密度列比较，Event Timeline 要求上游输出固定的 `time`/`title`/`status` 语义字段且不做字段映射。告警列表、健康检查、治理建议、工单等场景如果各自做专用卡片组件，会把业务字段写进渲染器。搭建者需要一个普通 chartType：从 DataSource 的普通 record 里选择字段，映射到固定视觉槽位。

## Solution

新增普通 DataSource 驱动的 `chartType=cardList`，同时可在 Dashboard 与 Screen 使用。Widget 只消费 `array<object>` 或 `{items: object[]}`，通过 `valueConfig.cardList` 把字段映射到固定槽位，再由同一套 renderer 画出只读卡片列表。

Card List 不是第二张表，也不是自由卡片构建器。它不理解告警、工单或健康检查语义。

## User Stories

1. 作为看板搭建者，我希望把任意返回记录列表的 DataSource 配置成卡片列表，并从普通字段中选择标题，从而不必先改造成 `title`/`description`/`status` 结构。
2. 作为看板搭建者，我希望把摘要、序号或前置字段、短强调文本、主辅尾部信息映射到固定槽位，从而控制一条记录的信息层次，但不能增加任意槽位或自由模板。
3. 作为看板搭建者，我希望在较宽的组件里把卡片排成自适应网格，在较窄的组件里自动变成单列，从而不必配置列数。
4. 作为看板或大屏使用者，我希望快速扫描每条记录的主标题和关键短文本，超长文本被截断，列表在组件内部滚动，从而在有限画布里阅读重点。
5. 作为大屏搭建者，我希望 Dashboard 与 Screen 使用同一套配置模型和数据契约，无需维护另一套 Screen-specific 配置或改造 DataSource。
6. 作为报告订阅用户，我希望合法空列表作为空状态成功完成渲染，非法 payload 使该组件失败，从而 PDF 不会因空数据卡住。

## Implementation Decisions

- Card List 是普通 `chartType`，不是 Scene Widget。不新增 `sceneWidgetType`、专用后端或 Scene 选择器条目。
- Dashboard 与 Screen 共用同一套 parser、validator、Card List renderer 和 `valueConfig.cardList`。不建立 Screen-specific runtime、config、parser 或 datasource contract。
- DataSource 的 `chart_type` 可勾选 `cardList`。配置抽屉只在当前数据源已声明且当前 surface 支持时展示该类型，不向所有数据源自动注入。
- 运输层继续使用既有 `{data, warnings}`。Card List 不新增公共 envelope，不把普通 object 当成单条 record，不把 `{data:[]}` / `{results:[]}` 当作一等输入。
- 字段读取复用现有路径取值；配置面复用数据源 `field_schema` 下拉，对标 TopN 的具名字段选择，不复用表格列编辑器。
- MVP 不新增字段探测或 sample-data inference。字段选择器只列出当前 `field_schema` 中的 key；schema 为空或不包含目标字段时，不提供对应选项，也不能从预览样本补字段。已持久化的字段名运行时仍按路径取值，缺失则走 Displayable scalar / Primary 规则。
- Prometheus / Excel 等数据源的默认 chartType 列表不因本次需求改写。只有实际返回记录列表的 DataSource 才应声明 `cardList`。

### Config contract

配置只存在 `valueConfig.cardList`。该类型形状是唯一持久化契约：

```ts
type CardListLeadingConfig =
  | { type: 'index' }
  | { type: 'field'; field: string };

interface CardListConfig {
  titleField: string;
  descriptionField?: string;
  leading?: CardListLeadingConfig;
  badgeField?: string;
  trailingPrimaryField?: string;
  trailingSecondaryField?: string;
  layout?: 'list' | 'grid';
}
```

`type: 'none'` 与 `{ type: 'field' }`（无 field）都不是合法持久化状态。前者只存在于配置 UI / form state；提交时必须归一成 `leading: undefined`。

槽位与字段对应：

| Slot | 是否 MVP capability | 配置项 | 配置是否必填 |
| --- | --- | --- | --- |
| Primary | 是 | `titleField` | 必填 |
| Secondary | 是 | `descriptionField` | 可选 |
| Leading | 是 | `leading` | 可选 |
| Badge | 是 | `badgeField` | 可选 |
| Trailing Primary | 是 | `trailingPrimaryField` | 可选 |
| Trailing Secondary | 是 | `trailingSecondaryField` | 可选 |

六个槽位都是 MVP 必须实现的展示能力。只有 `titleField` 是配置必填项。未配置的可选字段表示该槽位在本次 Widget 中不启用，不表示该能力被移出 MVP。

### Card anatomy

每张卡片的区域与顺序固定，用户不能改变槽位顺序：

- 左侧：Leading
- 中间 Main：Primary → Secondary
- 右侧 Trailing：Badge → Trailing Primary → Trailing Secondary

未启用或按下方 scalar 规则判定为 missing 的槽位不占位。本契约只锁定区域与顺序，不锁定 padding、font-size、gap 等实现值。

### Displayable scalar contract

所有卡片槽位只展示可显示标量：`string`、`number`、`boolean`。

| 原始值 | 结果 |
| --- | --- |
| `null` / `undefined` | missing |
| `string` trim 后为空（含只含空白） | missing |
| `number`，包括 `0` | 有效，展示 `"0"` |
| `boolean`，包括 `false` | 有效，展示 `"false"` |
| `true` | 有效，展示 `"true"` |
| 非空 `string` | 有效，展示 trim 后的文本 |
| 非零 `number` | 有效，展示十进制文本 |
| `object` / `array` | missing；不 `String(object)`，不 `JSON.stringify` |

Primary 不满足上述有效规则时，视为缺失 Primary。  
已启用的 optional slot 不满足时，仅隐藏该 slot。

### Persistence isolation

- `submitConfig` 为 `chartType=cardList` 使用专属白名单，只写出 `cardList` 以及既有通用字段（`name`、`description`、`chartType`、`dataSource`、`dataSourceParams`、`filterBindings`）。Screen 上继续写入既有公共 `appearance.frame=panel`，但不为 Card List 开放 frame 配置项。
- `titleField` 经 trim 后为空则提交失败。
- 可选字段（`descriptionField` / `badgeField` / `trailingPrimaryField` / `trailingSecondaryField`）trim 后为空则省略，不写空字符串。
- 合法持久化 `leading` 仅三种：`undefined`、`{ type: 'index' }`、`{ type: 'field'; field: string }`。`field` 必须是 trim 后非空的字符串。
- 配置 UI 可选 `none`；提交时 `none` / 未选 → `leading` 省略为 `undefined`，不得写出 `{ type: 'none' }`。
- `leading.type='field'` 且 `field` 缺省或 trim 后为空：配置校验失败，不允许提交，不得静默省略 `leading` 后保存成功。
- `type='index'` 不得持久化 `field`。
- `layout` 缺省为 `list`；仅当值为 `grid` 时持久化 `layout: 'grid'`。
- Card List 不读取、不写入顶层 `descriptionField`、`tableConfig`、`actions`、`eventTimeline`、`radar`、`selectedFields`、`topNLabelField`、`topNValueField`。
- 从其他 chartType 切到 `cardList`，或从 `cardList` 切走时，提交结果不得泄漏对方的专有字段。

### Leading contract

- 运行时只认持久化 discriminated union：缺省 / `undefined` 不显示 Leading；`index` 与 `field` 如上。
- 配置 UI 的 `none` 等价于运行时 `undefined`，不是落盘类型。
- `index`：renderer 按**已渲染卡片**生成序号，不读取 DataSource 字段。先跳过无效记录并应用 render safety cap，再对展示中的卡片编号。显示格式固定为 `01`、`02`、…、`99`、`100`：1–99 左侧补零到两位，`100` 显示为 `100`。
- `field`：`field` 必填；用现有路径取值读取该字段，再套用 Displayable scalar contract。值为 missing 时仅隐藏该卡片的 Leading，不影响 Primary 或其他槽位。
- 不支持 text / badge / icon / avatar 等 display subtype。

### Badge contract

- Badge 是 Trailing 区内的短文本强调标签，展示值仍来自 `badgeField` 的 displayable scalar。
- 样式固定，与字段值无关；使用现有 Design Token，不因 `P1` / `异常` / `健康` 等业务值换色。
- 不增加 value → color mapping，不复用 Table / Single 的 `valueMappings`。

### Layout contract

- `layout?: 'list' | 'grid'`，缺省 `list`。
- `list`：单列排列。
- `grid`：根据 Widget 当前可用宽度自动分列；不允许配置列数；宽度不足以放下第二列时自动退化为单列。
- 布局只影响 Card List renderer 内部排列，不修改 Dashboard 或 Screen 的 Canvas 几何协议，不为列数引入画布级观察或专用 runtime。
- 具体用何种网格算法属于实现细节，不是产品合同。

### Data contract

先判断原始 payload 形态，再过滤元素并映射槽位。

原始 payload 为空：

| 原始 payload | 结果 |
| --- | --- |
| `null` / `undefined` | empty |
| `[]` | empty |
| `{ items: [] }` | empty |

`undefined=empty` 只适用于 **fetch 完成后** 交给 Card List parser/validator 的业务 payload。仓库事实：`widgetDataRenderer` 在初始 loading / 未完成请求时不把 rawData 交给 chart renderer；`validateChartData` 只在 fetch settle 后用 `currentData` 调用。因此 `undefined` 不是 loading/uninitialized 信号，不需要、也不新增 Card List 运行时分支。公共 loading lifecycle 继续处理未取数状态。

原始 payload 为列表形态（`array` 或带 `items` 数组的 object）且非空时，按 **mixed-record** 过滤：

- 非 record 数组元素（标量、`null`、array）跳过
- record 缺少有效 Primary 跳过
- 过滤后仍有至少一条有效 record → 按原始相对顺序渲染这些 record
- 过滤后 0 条有效 record → invalid

示例：

| 原始 payload | 结果 |
| --- | --- |
| `[]` | empty |
| `[1, 2]` | invalid |
| `[{}, {}]` | invalid |
| `[1, { title: "A" }]`（`titleField=title`） | 渲染 A |

其他非法形态：

| 原始 payload | 结果 |
| --- | --- |
| 普通 object（没有 `items` 数组） | invalid |
| 标量 | invalid |
| graph 等异形 object（例如 `{ nodes, edges }`） | invalid |
| `{ data: [] }` / `{ results: [] }` | invalid；不是 Card List 输入 |

有效 Primary：`titleField` 经路径取值后满足 Displayable scalar contract。  
已启用 optional slot 不满足该合同：只隐藏该槽位，卡片仍渲染。

不增加 object fallback，不把单条 object 当成一行，不把 `{data}` / `{results}` 解包为记录列表。

### Render safety cap

这是 **render/display safety cap**：只限制最终渲染多少张卡片，不代表 DataSource response-size 防护，也不改变上游返回多少条。

复用 Event Timeline 已落地的 safety-cap **行为**，不复用其“按 time 取最新 N 条”的窗口规则。

Event Timeline 的可复用事实：固定阈值 `100`；超限截断而不是 invalid；用 parser 的 `truncated` 在组件内显示 Alert；`onReady` 仍按截断后是否还有数据上报；Dashboard / Screen / report 因共用 renderer 而语义一致；阈值不是用户配置。

不能原样调用 Event Timeline parser 的代码原因：该 parser 要求固定 `time`/`title`，并先按时间排序再切“最新窗口”。Card List 没有时间字段，且必须保持 DataSource 原始顺序。

因此 Card List 的唯一 cap 合同是：

- 固定阈值 `100`，内部常量，不是 `valueConfig` 字段。
- 先按 Data contract 得到有效 records，并保持原始相对顺序。
- 有效 records 数量 `<= 100`：全部展示，`truncated=false`。
- 有效 records 数量 `> 100`：只展示**原始顺序中的前 100 条**有效记录；`truncated=true`。这是截断，不是 invalid，也不是 empty。
- 禁止静默丢弃：`truncated=true` 时必须在组件内显示可见 warning，文案需同时给出有效总数和阈值，对标 Event Timeline 的组件内 Alert，而不是运输层 `warnings`，也不是 `onRenderStatus=failed`。
- 截断后只要仍有至少一条有效卡片，render 终态为 `ready`。empty / failed 判定不受 cap 影响。
- Dashboard、Screen、report 使用同一 renderer，因此 cap、warning 与终态语义一致。报告 PDF 会拍到该 Alert，这是接受结果，不是分叉。

### Overflow and surface behavior

- Card List renderer 自己负责组件内部 overflow；卡片超出 Widget 高度时在组件内滚动。
- Dashboard 与 Screen 共用这一行为。
- Screen 的整画布缩放和 density context 不产生 Card List 专用逻辑。Card List 不消费 Screen density / uiScale 去做第二套字号或间距。
- 文本溢出：Primary 单行 ellipsis；Secondary 最多两行 ellipsis；Badge 与两个 Trailing 单行 ellipsis。Tooltip 不是验收项。

### Screen registration

MVP 正式包含 Screen，且只做登记，不写新行为：

- `ScreenWidgetChartType` 增加 `cardList`
- `SCREEN_WIDGET_DEFINITIONS` 增加一条；默认尺寸与 Event Timeline 相同，为 `520 × 360`
- 选择器标签与 Screen i18n 文案
- `layoutUtils` 注册回归：`cardList` 可创建、带上默认尺寸，未知类型仍报原错误

明确不包含：

- Screen-specific renderer / config / parser / datasource contract
- 为 Card List 开放 `appearance.frame` 配置；创建时沿用公共默认 `panel`

### Existing platform isolation

- 不进入 `isTableLikeChart`，不接入表格分页参数，不扩大 Share `query_list` 参数面。
- 统一筛选绑定继续走既有通用字段，不属于 Card List 专有 DSL。

## Testing Decisions

- 只验证外部可观察行为，不锁定内部 DOM 结构、CSS 算法或 class 名。
- 最高优先沿用现有运营分析 Widget 接缝：提交配置归一化、payload 解析/校验、Screen 类型注册、运行时校验与报告终态。

- 解析与校验：
  - 数组与 `{items}` 在过滤后至少一条有效 Primary 时可渲染。
  - fetch 完成后的业务 payload 为 `[]`、`{items: []}`、`null` / `undefined` 时为空。
  - 原始 payload 非空但过滤后 0 条有效 record 为非法，包括 `[1, 2]` 与 `[{}, {}]`。
  - `[1, { title: "A" }]` 在 `titleField=title` 时渲染 A。
  - 普通 object、顶层标量、`{data:[]}`、`{results:[]}`、graph object 为非法。
  - Displayable scalar：`0` 与 `false` 为有效展示；只含空白的 string、object、array 为 missing。Primary 上的 missing 使该 record 被跳过；optional slot 上的 missing 只隐藏该 slot。
- Render safety cap：
  - 101 条有效记录只展示前 100 条，`truncated` 为真，组件内可见 warning，终态仍为 `ready`。
  - 截断限制的是渲染数量，不是 DataSource 响应大小。
  - 截断不是 invalid，也不是 empty。
  - warning 不进入运输层 `warnings`，也不把 widget 打成 `failed`。
- 配置提交：
  - 只持久化 `valueConfig.cardList` 白名单字段。
  - `titleField` 为空不可提交。
  - 持久化 `leading` 不得出现 `type=none` 或无 `field` 的 `{ type: 'field' }`。
  - UI 选 `none` 或不设 → 提交后 `leading` 为 `undefined`。
  - `type='field'` 且 `field` 为空 → 提交失败，不得省略后保存成功。
  - `field_schema` 为空时字段下拉无选项；不触发 sample-data probing。
  - 默认 `list` 不写 `layout`；`grid` 才写入。
  - 与 `table` / `single` / `eventTimeline` / `radar` 互切后，专有字段不互相残留。
  - 不写入 `tableConfig`，不把 Card List 标成表格类组件。
- Screen：
  - `cardList` 是合法 Screen 类型，可创建，默认宽高 `520 × 360`。
  - 未知类型仍抛原有“不支持的大屏组件类型”错误。
  - 数据源未勾选时，Screen 与 Dashboard 配置抽屉都不展示该类型。
- 布局：
  - 组件测试只验证 `list` / `grid` 配置进入对应布局分支，不用源码正则证明网格实现。
  - 宽/窄容器自动分列与退回单列属于视觉行为。当前仓库没有运营分析 Widget 的浏览器级布局测试接缝，因此记为 visual smoke，不为验证布局引入新的 Canvas / runtime 逻辑。
  - 两种布局都不改变画布 layout item 的宽高协议。
- 卡片解剖与展示：
  - 未启用或不满足 scalar 合同的槽位不占位；用户不能改变槽位顺序。
  - Leading `index` 对已渲染卡片显示 `01`…`99`、`100`。
  - Badge 使用固定强调标签样式，不随字段值换色。
- 报告：
  - 合法空列表结束为 `empty`，可 `report-ready`。
  - 非法 payload 结束为 `failed`。
  - 截断后的非空列表结束为 `ready`。
- 回归：
  - 现有 DataSource 不会自动多出 `cardList`。
  - Share 不会因为 Card List 放行表格查询参数。

## Out of Scope

Deferred：

- semantic / value color mapping
- density
- formatter
- prefix / suffix
- sort
- 用户可配 maxItems
- openLink / actions
- Tooltip 作为验收项
- image / icon / avatar
- Screen-specific scaling logic
- leading 的 text / badge display subtype

Rejected：

- 复用 `tableConfig`
- 进入 `isTableLikeChart`
- pagination / search / filter / group by
- 任意列数配置
- HTML / JSX / 自由模板
- 新的 DataSource envelope
- 独立 formatter framework
- 把业务专用字段写进组件
- Scene Widget、专用后端
- object fallback
- 为 Card List 开放 `appearance.frame`

## Further Notes

- Event Timeline 继续保持“固定事件语义字段、不做映射”。Card List 的差异化是映射普通 record 到固定展示槽位。两者可以声明在同一 DataSource 的 `chart_type` 上，但产品语义保持分离。
- Screen 接入走与 Event Timeline / Radar 相同的类型登记路径，不因此复制它们的数据契约。

## Completion Evidence

- 已完成 `chartType=cardList` 的 Dashboard + Screen 全链路接入：parser/validator、`valueConfig.cardList`、submit 白名单、registry、配置面、renderer、Screen 类型登记、i18n、Share `query_list` 回归。
- 聚焦测试通过：
  - `./node_modules/.bin/tsx --test src/app/ops-analysis/utils/__tests__/cardListData.test.ts src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.cardList.test.ts src/app/ops-analysis/constants/__tests__/chartTypeList.test.ts src/app/ops-analysis/(pages)/view/screen/utils/__tests__/layoutUtils.cardList.test.ts`（24 passed）
  - `./node_modules/.bin/vitest run src/app/ops-analysis/components/widgets/__tests__/comCardList.layout.test.tsx`（2 passed）
  - `uv run pytest apps/operation_analysis/tests/test_share_service.py::test_share_query_denies_query_list_for_card_list_widgets apps/operation_analysis/tests/test_share_service.py::test_share_query_allows_query_list_only_for_table_widgets -q`（2 passed）
- 新增/改动文件聚焦 ESLint 通过：`cardList.ts`、`comCardList.tsx`、`cardListSettingsSection.tsx`、`submitConfig.ts`、`widgetConfig.tsx`、`widgetDataRenderer.tsx`、`widgetRegistry.ts`、`widgetSelector.tsx`、`common.ts`、相关 types、Screen widgets、Dashboard persist。
- 未跑全量 `pnpm type-check`：既有基线仍会因未改动文件失败，与 Event Timeline / Radar 交付记录一致。
