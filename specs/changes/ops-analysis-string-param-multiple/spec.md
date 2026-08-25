# 运营分析字符串参数以多选表达列表传参

Status: implemented

评审结论：补充合同后可执行。本规格已写入迁移保留、同 key 双 ID 合并、`multiple` 归属、设置页已知限制与关多选不得暗中回数组等合同；实现须遵守下列条款，不得另开隐藏 `stringList` 分支兜底。

## Completion Evidence

- 前端：废除一等 `stringList`；参数输入配置 `multiple` 与 `componentSwitch` 互斥；统一筛选配置/栏按 `inputConfig.multiple` 控制数组 vs 标量；加载与构建路径迁移/继承 `inputConfig`；关多选静默取首元素。
- 迁移：`stringParamMultipleMigrate` + `test:ops-analysis-string-param-multiple-migrate`（含 componentSwitch 互斥、双 ID、完整选项源身份）；内置 `source_api.json` 与主机综合 YAML 为 `string` + `instance_ids__string`；YAML 导入预检发出 `OA_STRING_LIST_MIGRATION` warning。
- 后端：`filter_snapshot` 按 string+multiple 校验列表/标量，legacy `stringList` 仅读兼容。
- 验证（本回合）：`pnpm test:ops-analysis-unified-filter-input`、`pnpm test:ops-analysis-string-param-multiple-migrate`；相关 operation_analysis 主机数据源/YAML/筛选快照 pytest 通过。

## Problem Statement

运营分析曾引入独立参数类型「字符串列表」（`stringList`），用于统一筛选和主机等多对象下拉按 ID 数组传参。实际体验上：设置里类型下拉会出现「字符串列表」，与「字符串」并列，但用户无法在设置页真正配通多选；后端对 `stringList` + 筛选联动的校验也不完整，保存易失败。搭建者需要的是「字符串参数在选了下拉之后能否多选」，而不是再学一个平行类型。

列表传参数能力仍要保留：内置主机相关数据源与样例画布已按数组使用 `instance_ids`；统一筛选与组件查询参数已有参数输入配置齿轮。本期要改的是类型表达与多选入口，不是取消数组传参。

已知产品限制（故意保留）：自定义数据源在设置页本期仍不能声明「此参永远是数组」；需要数组时，由画布上两处齿轮配置 `multiple`。内置源与旧 `stringList` 资产靠迁移自动带上 `multiple: true`，不依赖搭建者逐项补开。

## Solution

删除一等类型 `stringList`。参数与统一筛选项在类型上只保留「字符串」（以及既有的时间/日期范围等）。合同约定：`type` 表示基础数据类型；`inputConfig.multiple` 表示基数与请求形状——为 true 时传 ID 数组，为 false 或未开时传标量。

多选开关只加在现有参数输入配置弹窗中，且仅当控件为下拉或表格选择时显示。生产入口沿用现有两处齿轮：统一筛选配置中字符串类型旁的齿轮；组件配置侧栏查询参数中字符串类型旁的齿轮。数据源设置页参数表不增加多选控件或齿轮。

旧存盘 `stringList` 在读入与保存路径上规范为 `string` 并强制 `multiple: true`，且保留原有输入配置（控件、选项源、picker 等）；筛选项 id 从 `key__stringList` 迁到 `key__string`。内置主机源与样例画布迁移后默认并持续保存 `multiple: true`；若搭建者之后主动关闭多选，按通用规则改为标量请求，系统不得再用旧类型分支暗中转回数组。

## User Stories

1. 作为看板搭建者，我希望参数类型下拉只看到「字符串」而看不到「字符串列表」，从而不必在两个相似类型之间猜测。
2. 作为看板搭建者，我希望在统一筛选配置里对字符串筛选项点开参数输入配置，在选择下拉/表格后勾选多选，从而一次选出多个 ID 并驱动已绑定组件按数组重新查询。
3. 作为看板搭建者，我希望在组件配置的查询参数上对字符串参数点开同一套参数输入配置并勾选多选，从而该卡私有参数也能按数组传参。
4. 作为看板使用者，我希望多选清空后请求省略该参数（不传空数组），从而与现有空筛选语义一致。
5. 作为已使用主机综合样例或内置主机数据源的租户，我希望升级后主机多选筛选仍按数组工作，且不必手工改类型。
6. 作为自定义数据源的配置者，我理解设置页本期不能声明数组契约；需要数组传参时，我在画布统一筛选或组件查询参数的齿轮里打开多选。
7. 作为主动关闭主机 `instance_ids` 多选的搭建者，我希望请求按标量（或按空值省略规则）发出，从而配置与请求一致；若下游不接受标量，通过校验或请求错误暴露，而不是被系统暗中改回数组。

## Implementation Decisions

### 类型与形状合同

- 废除可绑定/可展示的独立类型 `stringList`。可绑定类型集合与数据源参数类型下拉均不再提供该选项；扫描、绑定、筛选项 id 对字符串侧统一为 `key__string`。
- `type` 表示基础数据类型；`inputConfig.multiple` 表示基数与请求形状：为 true 时运行时值与默认值为 ID 数组；未开多选时为标量。空数组 / null / 未选在绑定生效时省略该参数。禁止用逗号拼接字符串冒充列表。本期不提供「单选外观但必须传数组」；若未来需要，另议 `valueShape`，不在本期复活 `stringList`。
- 多选开关仅出现在参数输入配置弹窗，且控件为 `select`（含表格 picker）时；与组件内切换（`componentSwitch`）互斥——已开其一则禁用另一项。
- 关闭多选时：空 → 空；单元素 → 该元素；多元素 → 静默保留第一个，其余丢弃，不弹确认。

### 生产入口与已知限制

- 生产只改两处已挂载参数输入配置的入口：统一筛选配置（字符串筛选项齿轮）、组件配置查询参数（字符串齿轮）。
- **已知产品限制**：数据源设置页参数表本期不增加多选开关或齿轮；自定义数据源无法在设置页声明数组契约。需要数组时，必须在上述两处画布齿轮配置 `multiple`。不为拓扑单值面板补齿轮；旧版仅静态选项的筛选选项弹窗不跟本期扩多选。
- 统一筛选与组件查询参数共用同一套参数输入配置语义；不另设「筛选项多选声明」或「数据源参数再声明一次多选」的第二套开关，也不允许数据源配置在画布保存后持续回灌、覆盖已有筛选项或组件上的 `multiple` / 选项配置。

### `multiple` 归属：创建时继承、运行时归属消费者

- **创建时继承**：从数据源参数新扫出并创建统一筛选项时，若参数上已有 `inputConfig`（含 `multiple`、选项源、picker 等），筛选项应继承该配置作为初始值；参数无配置则按默认（字符串、非多选，或由搭建者随后在齿轮中配置）。
- **运行时归属消费者**：
  - 统一筛选路径：请求形状以**该筛选项**当前的 `inputConfig.multiple` 为准。
  - 组件私有参数路径：以**该组件参数**（含组件级覆盖）的 `inputConfig.multiple` 为准。
- 禁止：打开画布或保存时用数据源上后来改动的 `multiple`/选项配置覆盖已经存在于画布筛选项或组件覆盖上的配置（「创建时继承、之后不回灌」）。

### 兼容迁移（同一变更完成）

- **单条 `stringList` 规范化**（数据源 params、画布 filters、组件覆盖、运行时漏网旧值）：
  1. `type` 改为 `string`。
  2. **保留**原有 `inputConfig` 的控件类型、选项源、`picker`、`maxCount`、静态/动态配置及其他字段；**仅强制** `multiple: true`（若原为 false/缺失则改为 true；不得整表替换为新的默认 select）。
  3. **仅当完全没有 `inputConfig`（且无可用的旧版 `options` 可归一）时**，才补默认 `{ control: 'select', multiple: true, optionsSource: { type: 'static', staticItems: [] } }`（或与现网等价的默认 select + multiple）。
  4. 若仅有旧版 `options` 而无 `inputConfig`，先按现网规则归一为 select 的 `inputConfig`，再强制 `multiple: true`，不得丢掉选项。
  5. **与 `componentSwitch` 的存量冲突**：旧 `stringList` 规范化时，如果原配置同时启用了 `componentSwitch`，以列表传参兼容为优先——保留原选项配置，设置 `multiple: true`，**关闭** `componentSwitch`，并在导入 warning 或加载日志中记录互斥冲突。不得生成二者同时开启的配置。
- **筛选项 id**：`key__stringList` → `key__string`。
- **同 key 双 ID（`key__string` 与 `key__stringList` 并存）——确定性合并，禁止依赖对象遍历顺序**：
  1. 以旧 **`stringList` 侧**作为多选配置（`inputConfig` 经上述保留规则规范化后）与当前筛选值/默认值的来源。
  2. 两侧 `filterBindings`：按组件合并，对同一组件去重后并入最终 `key__string`；任一侧曾启用则结果启用（逻辑或），不得丢绑定。
  3. 最终只保留 `key__string`，删除 `key__stringList`。
  4. **不兼容判定**（任一成立则视为不兼容）：两侧在规范化后比较——`control` 不同；`picker` 不同；**完整选项源身份**不同。选项源比较不得只抽个别字段：对规范化后的整个 `optionsSource`（含 `type`、静态选项 value 集合、动态源的 `sourceRef`/`sourceId`、`valueField`/`labelField`，以及任何会改变候选集合的请求参数、过滤配置等字段）做确定性序列化或深比较；任一差异即不兼容。
  5. 不兼容时：**仍以 `stringList` 侧配置与值为准**写入最终 `key__string`（确定性优先，不拼接字段）；标量侧（原 `key__string`）的冲突配置不覆盖结果；必须留下可观测记录。
  6. **warning / log 落点**：YAML 导入预检或导入结果中给出受影响画布/筛选项 key 与冲突摘要；画布加载规范化路径打应用日志（含 canvas id、key、冲突字段）；`componentSwitch` 互斥关闭同样记录。不得静默合并。不要求本期做阻塞式弹窗，但测试须能断言迁移输出（warning 列表或 logger 副作用）已产生。
- 内置数据源登记与主机综合样例 YAML：去掉 `stringList` 类型名，改为 `string` + 保留原选项配置并 `multiple: true`；迁移后默认并**持续保存**该多选配置。
- **主动关闭主机 `instance_ids`（或其他已迁多选）的多选后**：按通用规则传标量（或空则省略）；**禁止**任何「若曾是 stringList / 若 key 为 instance_ids」的隐藏分支把请求改回数组。下游若只接受数组，由配置校验或请求错误反馈暴露；本规格不承诺关闭多选后仍满足数组型主机接口。
- 请求组装与筛选快照：按消费者侧 `string` + `multiple` 校验数组/标量；去掉对独立 `stringList` 类型名的依赖分支（含后端筛选快照与数据源 params 校验文案）。读路径可识别旧 `stringList` 仅用于规范化，写路径与请求路径不得再依赖该类型名决定形状。
- 长期能力合同 `dashboard-unified-filter` 与产品决策记忆须在同一实现变更中改为「字符串 + multiple」，不再把 `stringList` 列为一等控件类型。
- 主机取数与选项源等下游在**保持多选开启**时数组契约不变；仅存储与 UI 类型表达方式变更。
- 参数优先级不变：固定参数 > 统一筛选 > 组件私有参数 > 数据源默认；多选只改变值形状。

## Testing Decisions

优先测试用户可观察行为与迁移输出；加载迁移允许断言 warning/logger 副作用；不测试 React 内部状态。

### 功能行为

- 类型下拉无「字符串列表」。
- 参数输入配置在下拉/表格下可开多选；勾选后请求带数组；清空则省略参数。
- 未开多选的字符串筛选仍传标量。
- 关多选时多值只保留第一个。
- 自定义数据源仅在设置页无法配置多选（已知限制）；同一参数在画布两处齿轮打开多选后请求可为数组。
- UI 上 `multiple` 与 `componentSwitch` 互斥（已开其一则禁用另一项）。

### 兼容迁移验收

- 旧 `stringList` 带表格 picker / 动态 `sourceRef` 的配置：迁移后 `type=string`、`multiple=true`，且 picker、选项源字段与迁移前一致（不得被默认空 select 覆盖）。
- 旧 `stringList` 无 `inputConfig`：迁移后具备默认 select + `multiple: true`。
- 旧 `stringList` 同时启用 `componentSwitch`：迁移后 `multiple: true`、`componentSwitch` 关闭（或字段移除），选项配置保留，且产生互斥冲突 warning/log。
- `key__string` 与 `key__stringList` 并存：结果仅 `key__string`；配置与值来自原 stringList 侧；bindings 为两侧去重合并；不兼容时产生 warning/log，且结果仍确定性取 stringList 侧。
- 内置主机数据源登记与主机综合样例 YAML：类型为 `string` 且 `multiple: true`，选项源仍可用。
- 读入旧 `stringList` 后运行时行为与「字符串 + 多选」一致。

### 关多选不得暗中回数组

- 对已迁移的主机 `instance_ids`（或等价多选字符串筛选）：搭建者主动关闭 `multiple` 后，绑定请求必须发标量或按空值规则省略该参数，**不得**出现数组。
- 对应外部行为测试必须覆盖：关多选前后请求体形状断言；并断言不存在「仅因历史类型名而改回数组」的路径（可通过请求脚本/快照校验接缝覆盖）。

### 优先接缝

沿用现有最高层脚本与定义断言，不新造平行套件：

- 统一筛选入参/合并脚本（多选数组、空省略、与标量字符串共存、关多选变标量）
- 参数输入配置确认后的 `inputConfig.multiple` 与传参形状
- 迁移规范化纯函数或导入/加载接缝（保留 inputConfig、双 ID 合并、componentSwitch 互斥关闭、warning/logger）
- 内置主机数据源登记与主机综合样例 YAML 的类型/多选/选项源断言
- 数据源 params 校验（字符串可作筛选；不再要求 `stringList` 类型名）
- 筛选快照对「字符串 + multiple」数组值的接受与对关多选后标量的接受

## Out of Scope

- 数据源设置页参数表增加齿轮或行内多选开关（**已知产品限制**，见 Solution / Implementation；需要数组时用画布两处齿轮）
- 拓扑单值节点配置面板补参数输入配置入口
- 旧版静态筛选选项弹窗升级为完整参数输入配置
- 平台级多选硬顶（`maxCount`）产品拍板
- 「单选外观但请求必须为长度 1 的数组」（若需要，未来另议 `valueShape`）
- 级联下拉、筛选方案收藏、图表钻取、跨仪表盘共享筛选状态
- 修改监控下游 `instance_ids` 在多选开启时的语义，或把 3D 机房 `componentSwitch` 迁入统一筛选
- 健康/异常主机数等已明确不做的主机 KPI
- 关闭多选后仍保证数组型主机接口可用（明确不承诺；靠校验或请求错误暴露）

## Further Notes

- 本变更修正并替代 `ops-analysis-unified-filter-string-list` 中「`stringList` 作为一等参数/筛选项类型」的表达方式；列表传参数能力保留，改为 `string` + `inputConfig.multiple`。
- 产品决策记忆应改挂本规格，并写明：类型下拉不再并存 `stringList`；绑定 id 统一 `key__string`；`multiple` 为基数合同；设置页本期不声明数组为已知限制。
- grill / 评审共识：2026-08-21 确认入口与删类型方向；2026-08-24 评审结论为「补充合同后可执行」，并采纳迁移保留 inputConfig、双 ID 确定性合并、创建时继承运行时归属消费者、关多选不得暗中回数组等合同；开工前补齐 `stringList`+`componentSwitch` 存量互斥迁移、选项源完整身份比较、测试措辞（可观察行为 + 迁移输出）。
- 本文件即为实现依据；实现勿削弱上述迁移与测试条款。
