# 运营分析 · 选项查询参数级联 — 实现方案

- 最近更新：2026-11-03
- 状态：产品已拍板，已实现（2026-10-30）；2026-11-03 修订 D4：同名同类型始终并成一行
- 关联决策记忆：`docs/design/product-decisions/ops-analysis-unified-filter.md`（其中「级联下拉」原为明确后置，由本文接续）
- 范围模块：`web/src/app/ops-analysis`
- 实现入口包：`components/unifiedFilter/`（页面实际 import）；`components/ops-analysis-unified-filter/` 为并存旧包，改动需评估是否同步或删死引用，不以旧包为主路径

## 审查修订（2026-10-30）

- 同名同类型始终并成一行，不因选项源拆行。查询入参选中全局筛时 `ref` 存这一行的筛 id，下拉展示来源显示名。运行时按 id 读草稿，校验图按筛 id 建边。配置里若仍有多行且只存参数名、对不上唯一一行时，禁止保存并提示。
- `normalizeStoredQueryParams` 失败时丢掉非法 `queryParams`，不当成功写入。提案应用同样丢掉非法入参并给出警告；环和级数走 `validateOptionsQueryParams`。运行时 `blocked` 区分上游为空（`empty`）和入参非法（`invalid`）。
- 选项第一次回来时，把校正写入已应用初值，不触发搜索。之后的校正只改草稿。报表打开时保留传入的动态选项值，不再先清空再套默认。
- 已有 `` `${key}__${type}` `` 的 `inputConfig` 优先保留；没有已有定义时用先扫到的那份。对不上时不再新开摘要 id。已存的摘要 id 若仍在配置里，引用解析继续认；新扫描不再生成第二行。
- 自动搜索只保留内置 3D 机房筛，判定是固定 id `server_room_id__string`。空值时只把机房自身写入已应用并搜索，不把其它筛的草稿一并提交。应用系统筛走普通校正：首次写入已应用初值，之后只改草稿，不搜索。
- 2026-11-02：存在 `queryParams` 引用时禁用并关掉 `componentSwitch`。`filterBindings` 缺键视为跟随，显式 `false` 才读局部值。提案写入组件参数时与筛定义一样做环、不超过 3 级和类型校验，非法则丢掉并警告。超长链只丢掉超出 3 级的那一节，仍合法的前缀保留。同一张卡上的环、超长和类型问题一次扫完，分别警告。
- 2026-11-03：D4 改回级联前语义。同一画布是同一场景，同名同类型全局筛始终一行，异源同名也并，不再因 `optionsSource` 拆行，显示名也不再拼「· 数据源」。并一行后的 `inputConfig` 以先到或已有定义为准；后挂图的另一套选项宇宙被盖掉，是接受的取舍。已存的摘要 id 若仍在配置里，引用解析继续认；新扫描不再生成第二行。同日：引用下拉不再因成环或超过 3 级藏候选；选中后点确认仍按 `validateOptionsQueryParams` 拒绝，用提示说明超三级或成环，路径用显示名，不在表单里常驻内部 id。引用下拉弹出层高度 256，选项多时在层内滚动。

---

## 1. 背景与现状缺口

运营分析统一筛选已具备：盘级筛定义、草稿 +「搜索」才应用、动态选项、组件内切换、AI/YAML 读写 `inputConfig`。缺的是 **Grafana / 观测云型「选项查询入参引用上游参数」**——下游候选项随上游值变化，而不是新 Cascader 控件，也不是「记住上次搜索」。

### 1.1 代码对照（真实路径）

2026-10-30 记下的缺口已经落地。下表是当前代码，不再描述「还没有查询入参」。

| 能力点 | 现状 | 关键符号 / 路径 |
| --- | --- | --- |
| 参数输入配置 UI | 动态源可配 `queryParams`；引用按来源候选，确认时校验环和级数 | `components/paramInputConfigEditor.tsx` |
| 动态选项模型 | `DynamicOptionsSource.queryParams`：字面量或 `{ ref }` | `types/dataSource.ts` → `DynamicOptionsSource` |
| 选项请求 | `getSourceDataByApiId(sourceId, resolvedParams)`；上游空则 `blocked`，不发请求 | `utils/paramInputOptionsLoader.ts` |
| 选项缓存键 | 配置键含规范化 `queryParams`；运行时签名另含已解析上游值 | `paramInputOptionsLoader.ts`、`hooks/useParamInputOptions.ts` |
| `$` 语法 | 整值 `$key$` / `$key:type$` 归一成 `{ ref }`；拼接拒绝。展示模板仍独立 | `utils/optionsQueryParamRefs.ts`；`utils/filterTemplate.ts` |
| 草稿 + 搜索 | 栏上改值进草稿；点搜索才 `onSearch`。级联校正不触发搜索 | `components/unifiedFilter/unifiedFilterBar.tsx` |
| 打开校正 | 动态选项首次校正写入已应用初值，不触发搜索；不在列表则清空 | `utils/optionBackedFilterValue.ts`、`unifiedFilterBar.tsx` |
| 选项 reconcile 副作用 | `reconcileFilterOptions` 只改草稿；该筛选项第一次回来时另写已应用初值 | `unifiedFilterBar.tsx` |
| 合并键 | `` `${name}__${type}` ``，同名同类型并一行；后挂图的 `optionsSource` 不覆盖已有 | `utils/scanUnifiedFilterParams.ts` `filterMergeKey` |
| AI 合同摘要 | `optionsSourceIdentity` 含 queryParams 的 refs 与字面量 | `utils/optionsSourceIdentity.ts` |
| 组件内切换失效 | 不在选项里清空，不落到 `options[0]`。有 `queryParams` 引用时关掉 `componentSwitch`。选项尚未返回时保留现值；已经是空列表则清空 | `utils/componentParamSwitch.ts` |
| 筛选 id | `` `${key}__${type}` ``（如 `server_room_id__string`、`organization__string`）。不再新生成摘要 id | `assignFilterDefinitionIds` |

### 1.2 产品痛点（由 grill 确认）

1. 下游选项查询无法带上游值 → 级联做不成。  
2. 同一画布不会出现「一个组件用这套同名筛、另一个组件用另一套同名筛」。异源同名硬并成一行，后挂图的选项宇宙让位于先到或已有配置。  
3. 时间 / 组织等盘级共用维度按名和类型并，与普通筛相同（`screen_11` 机房仍是一条）。  
4. 组件内切换失效选第一项，与全局筛「失效清空」不一致。

---

## 2. 目标 / 非目标

### 2.1 目标

1. 在参数「配置」的选项查询上，支持**结构化引用**其它可筛参数作为请求入参（Grafana / 观测云型）。  
2. 硬顶约 **3** 级依赖；配置期校验：整值引用、禁拼接、环检测、级数。  
3. 上游变化 → **立刻重载**下游候选项；上游空 → **不请求**下游；旧值在列表保留，不在则**清空且不自动第一项**；只改草稿，**不**触发搜索；点搜索才应用刷图。  
4. 全局筛合并恢复为仅同名 + 同类型一行。时间范围、组织等盘级维度同样按名和类型并。异 `optionsSource` 不拆行。  
5. 组件内切换：失效清空不选；存在 `queryParams` 引用时禁用并关掉；没有引用时，局部选项依赖 = 本卡局部值 + **已应用**全局筛。  
6. AI 搭盘 / YAML 与配置 UI 读写同一份 `inputConfig`。

### 2.2 非目标

- 新 Cascader / 树形联动控件。  
- 「记住上次点搜索的整组值」或 Saved View / 跨会话筛选持久化。  
- 改造无依赖路径以外的图表主查询协议。  
- 把 `$` 展示模板（`filterTemplate`）改成选项查询引擎（可共用 token 解析风格，存储仍落在 `inputConfig`）。  
- 无依赖组件内切换以外的大范围交互改版。

---

## 3. 产品决策表（已拍板）

D4 于 2026-11-03 按产品拍板修订。其余行仍按表实现。

| # | 决策 | 说明 |
| --- | --- | --- |
| D1 | 模型 | Grafana / 观测云型选项查询入参 `$` 引用；硬顶约 3 级；非 Cascader；不做记住上次搜索 |
| D2 | 打开 | `defaultValue`（+ URL / 报表传入）→ 按新候选项校验 |
| D3 | 上游变 | 立刻重载下游选项；上游空不请求；旧值在则保留、不在则清空不选第一项；只动草稿不搜；点搜索才应用 |
| D4 | 合并 | 同名同类型始终并成一行（`getFilterDefinitionId` = `` `${name}__${type}` ``），异源同名也并。不因 `optionsSource` 或上游引用不同拆行，显示名不拼「· 数据源」。`timeRange` / `dateRange`、组织控件同样只按名和类型并。配置以先到或已有定义为准，后挂图的另一套选项宇宙被盖掉。配置表一行 = 运行时栏一个控件。存量摘要 id 只在配置里真有多行时继续参与引用解析；新扫描不再生出第二行 |
| D5 | 组件内切换 | 失效清空不选；存在 `queryParams` 引用时禁用并关掉。没有引用时，局部选项跟本卡局部值 + 已应用全局筛 |
| D6 | 配置入口 | 上游引用配在参数「配置」里的选项查询入参；**不是**全局筛总表另开「上游」列 |

---

## 4. 数据模型

### 4.1 扩展 `DynamicOptionsSource`

文件：`web/src/app/ops-analysis/types/dataSource.ts`

```ts
/** 选项查询入参：整值引用其它参数；禁止与字面量拼接 */
export type OptionsQueryParamValue =
  | string
  | number
  | boolean
  | null
  | { ref: string }; // ref = 被引用参数的 name（盘级筛 key / 同卡 params.name）

export interface DynamicOptionsSource {
  type: 'dynamic';
  sourceId?: number;
  sourceRef?: SourceRef;
  valueField: string;
  labelField: string;
  /** 选项查询请求体/查询参数；值为字面量或 { ref } */
  queryParams?: Record<string, OptionsQueryParamValue>;
}
```

- **主存储**：`queryParams` 内 `{ ref: 'server_room_id' }`。  
- **YAML / 展示友好**：允许整值写成 `"$server_room_id$"` 或 `"$server_room_id:string$"`，读写时归一成 `{ ref }`；**禁止** `"prefix-$id$"` 这类拼接（配置保存与运行解析均拒绝）。  
- 落点：筛定义的 `UnifiedFilterDefinition.inputConfig`；组件参数的 `ParamItem.inputConfig`（组件内切换同源）。全局筛总表不新增「上游」列。

### 4.2 `optionsSourceIdentity`（AI digest 与存量多行消歧）

全局筛合并不再使用这份 identity。它继续描述选项合同，供 AI 摘要和「配置里真有多行」时的引用匹配。同名同类型在扫描时仍然并成一行。

从 `applyDashboardProposal.ts` 私有函数抽出到 `utils/paramInputConfigUtils.ts`（或新建 `utils/optionsSourceIdentity.ts`），并扩展：

```ts
optionsSourceIdentity(inputConfig) =>
  | null  // input / organization / 无 options
  | { type: 'static'; itemsDigest }
  | {
      type: 'dynamic';
      sourceId; sourceRef; valueField; labelField;
      queryParamsRefs: string[]; // 规范化后的 ref 名列表，排序后参与 identity
      // 字面量 queryParams 也进入 digest，避免「同源不同固定入参」误并
      queryParamsLiterals: Record<string, string | number | boolean | null>;
    }
```

静态源：用 staticItems 稳定序列化进 identity，供合同比较。同名静态列表不同也不会在栏上拆成两行。

### 4.3 引用校验（配置期 + 可选运行期断言）

| 规则 | 行为 |
| --- | --- |
| 整值引用 | 入参值要么纯字面量，要么纯 `{ ref }` / 整 token `$key$`；拒绝拼接 |
| 目标存在 | `ref` 必须指向同画布启用筛的 `key`，或（组件内）同卡其它 `params.name` |
| 类型可绑定 | 被引用参数须为可筛/可传值类型；自引用禁止 |
| 环检测 | 对 `queryParams.ref` 建有向图，DFS/拓扑；有环则保存失败并提示路径 |
| 级数 | 最长依赖链 ≤ 3 个节点（A→B→C 可保存，A→B→C→D 拒绝）；超限拒绝保存 |
| 空上游 | 运行时任一 required 上游值为 `null` / `undefined` / `''` / `[]` → 下游不发请求，选项置空 |

校验函数建议：`utils/optionsQueryParamRefs.ts`（纯函数 + 单测）。

### 4.4 筛选 id

id 固定为 `` `${key}__${type}` ``，与级联前 `getFilterDefinitionId` 一致。同名同类型不再生成 `` `${key}__${type}__${shortDigest}` ``。

- 绑定面板、`FilterBindings`、运行时传参仍按 **definition.id**；传给数据源的参数名仍是 **key**。同一画布上跟随该名的组件读同一条 id。  
- 存量配置里若已经有摘要 id，引用解析仍按 id 命中那一行；裸名在只剩一行时解析到 `` `${key}__${type}` ``。新的布局扫描和配置表扫描不再制造第二行。  
- 打开配置或布局同步时，已有 `` `${key}__${type}` `` 的 `inputConfig` 优先保留；没有已有定义时用先扫到的那份。后出现的异源 `optionsSource` 不写回这一行。

---

## 5. 运行时

### 5.1 选项加载签名

扩展 loader / hook：

- `getParamInputConfigKey(config)` → 增加规范化 `queryParams` 结构（含 ref 名，不含运行时值）。  
- 另增 **运行时签名**：`optionsLoadSignature = configKey + '|' + resolvedUpstreamValuesJson`。  
- `createParamInputOptionsLoader.load(config, resolvedParams)`：动态源调用 `getSourceDataByApiId(sourceId, resolvedParams, …)`，**不再传 `{}`**。  
- 上游未齐（空）→ 不调用 API，返回 `success` + `options: []`（或明确 `status: 'blocked'`，UI 显示「请先选择上游」）；与 error 区分。

文件：`paramInputOptionsLoader.ts`、`hooks/useParamInputOptions.ts`；筛栏与组件内切换共用 loader。

### 5.2 草稿 vs 已应用

| 场景 | 读哪个值解析下游 `queryParams` | 是否改 applied / 刷图 |
| --- | --- | --- |
| 全局筛栏上改上游 | **草稿** `filterValues` / bar `localValues` | 只更新下游草稿选项与草稿值校正；**不** `onSearch` |
| 点「搜索」 | 将草稿写入 applied | 刷图 |
| 组件内切换拉选项 | 本卡局部切换值 + **已应用**全局筛 | 局部立即影响本卡请求（既有 componentSwitch 语义）；不改全局草稿 |

**必须改**：`unifiedFilterBar.tsx` 的 `reconcileFilterOptions` 不得默认 `publishValues(..., 'search')`。级联校正应：

1. 只写 local draft（`setLocalValues` / 等价）；  
2. **不**调用 `onSearch`；  
3. 与「用户点搜索」分离；  
4. 该筛的选项**第一次**回来时，另把校正写入已应用初值（`onApplyInitial`），仍不增加搜索版本。

自动搜索只留给内置 3D 机房筛，且只认固定 id `server_room_id__string`。空值时选中第一项，但只把机房自身交出去搜索，已应用值里的其它筛保持原样，不带走栏上还没搜索的草稿。`key === server_room_id` 的拆行摘要 id 不走这条路径。应用系统筛同样走普通校正，不选第一项、不搜索。

若当前存在「打开盘时 defer 动态默认值再 reconcile 且误触发搜索」的路径，一并收口为「只同步 draft + applied 初值策略按 D2，不额外打图表请求风暴」。

### 5.3 失效策略

统一用 `retainFilterValueInOptions` / 扩展后的 reconcile：

- 在列表 → 保留。  
- 不在 → **`null`（清空不选）**，禁止 `options[0]`。  
- 多选：只保留仍在列表中的子集；全无则 `null` 或 `[]`（与现有多选空语义对齐：空选择省略参数）。

全局筛：已基本是清空（`optionBackedFilterValue`）。  
组件内：改 `reconcileComponentSwitchValue`（及 `resolveComponentSwitchRuntime` 对空值的 gate），与 D5 对齐。

### 5.4 与 UnifiedFilterBar「搜索」关系

- 选项重载、草稿值清空：**不是**搜索。  
- 搜索按钮 / 等价入口：唯一把草稿提交为 applied 并驱动画布请求的用户动作（重置若产品已定义为「恢复默认并立即应用」，保持现行为，但重置仍应按新选项再校验）。

### 5.5 解析顺序

1. 按依赖图拓扑排序启用筛（无依赖优先）。  
2. 对每个动态筛：解析 `queryParams` → 若缺上游则跳过请求。  
3. 选项返回后校正该筛草稿值。  
4. 值变化则使直接下游签名失效并重载（链式，深度 ≤ 3）。  
5. 用户点搜索 → applied = draft → 图表用 applied 组参。

---

## 6. 合并算法

入口：`scanFilterParams`（`unifiedFilterConfigModal.tsx`）；发现/同步其它调用点（`widgetDataTransform` 收集、旧包 `scanUnifiedFilterParams`、报表/拓扑若复用）必须同一套纯函数，建议抽到 `utils/scanUnifiedFilterParams.ts`。

### 6.1 合并键

```
mergeKey = `${name}__${type}`
```

普通筛、`timeRange` / `dateRange`、组织控件都用这一条。`optionsSourceIdentity` 不再参与合并键，只留给 AI 合同摘要，以及配置里确实还存着多行时的引用消歧。

扫描时：同一 `mergeKey` 只建一条，累加 `componentCount`。`sampleInputConfig` 取先扫到的那份；若已有同 id（或同名同类型）定义，用那份 `inputConfig`，不用后挂图覆盖。

### 6.2 行为表

| 场景 | 配置表行数 | 查看态栏 |
| --- | --- | --- |
| 三图同一数据源、同名同配置 | 1 | 1 个控件 |
| 异源、同名，`optionsSource` 相同（`screen_11` 机房） | 1 | 1 |
| 异源、同名，`optionsSource` 不同（如 `accept_metrics` 与 `accept_metrics_b`） | 1，显示名仍是别名 | 1 个控件 |
| 同名且上游引用相同或不同 | 1 | 1 |
| 多数据源各绑 `time` / 组织 | 1 | 1 |

后挂图的选项宇宙被先到或已有定义盖住。同一画布不提供两套同名筛。

### 6.3 并着之后

- 并成一行 = 盘级唯一 `inputConfig` / 默认值 / 显示名；点「配置」改的是这一套。  
- 显示名用别名或用户已保存的名称，不追加「· 数据源」。  
- 已配好的查询入参留在已有定义上。后挂的图继续跟随这一行，不另起一套级联。  
- **禁止**一行内嵌多套配置，也禁止为了保住第二套选项宇宙再拆行。

---

## 7. 配置 UI

### 7.1 全局筛选配置表（不新增「上游」列）

- 列保持：参数名、显示名、类型、控件、默认值、启用、配置、…  
- 显示名默认是 `alias` 或已保存的名称。同名不再建议 `alias · 数据源名`。  
- 点「配置」打开现有 `ParamInputConfigEditor`，在动态源区编辑 `queryParams`。改的是并成的那一行。

### 7.2 参数配置 · 引用拾取

选中选项数据源后，若该源声明了参数，按声明展开「选项查询参数」。入参名跟源参数，不能另起名，也不能再为这个入参选择数据源。

- 四列：参数名、别名、取值方式（固定值 | 引用参数）、值/引用。参数名是只读技术名，列宽约 112px。别名显示 `alias_name`，没有则显示「—」，列宽约 112px。取值方式列窄，值/引用列占剩余宽度。查询参数表不加边框。  
- 展开时用数据源参数的 `value` 预填固定值。已经保存或用户改过的值保留，不用源默认值覆盖。  
- 每个参数只能填固定值，或一个完整的 `$` 引用。保存字面量或 `{ ref }`。不支持拼接和表达式。  
- `$` 候选按名称排序，不按页面顺序。组件参数可引用本组件其它参数和当前画布全局筛选；全局筛选只能引用本画布其它全局筛选。下拉排除自身、类型不兼容、其它组件的私有参数，以及全局筛 scope 里的组件参。成环和超过 3 级仍出现在下拉里；点确认时拒绝，用提示说明「查询入参存在循环」或「查询入参依赖超过 3 级」，路径用显示名（明细 → 实例 → 指标 → 监控对象），不在表单里常驻，也不展示 `__string` 或摘要 id。下拉弹出层高度 256，选项多时出现滚动条。下拉展示来源，例如「全局筛选 · 监控对象」。组件参配置里选中同名组件参数时，ref 保持参数名，不因画布上有唯一同 key 全局筛就收成 definition.id；选中全局筛时 ref 仍是筛 id。回显按 ref 区分「组件参数」和「全局筛选」。建校验图时，本卡组件参名（含正在编辑的参数）占用的 key 不再挂到全局筛别名上，避免和并成一行的同名筛误报「同名多条」。两个不同 id、同 key 的筛定义里，裸名仍然拒绝，存具体 id 可以通过。  
- 参数已绑定全局筛选时，运行时引用取该筛选的实际生效值。  
- 保存时跑 §4.3 校验；环与超深用提示反馈，不在查询参数表下常驻红字。  
- 值字段和展示字段优先用 `field_schema`。没有 schema 时可以手填字段名。预览是可选辅助：源声明了参数时不自动预览。存在 `$` 引用时预览按钮仍可用；试拉只提交已填固定值，不传引用键。失败不清空已选字段。成功把返回列名并入候选。

### 7.3 组件内切换配置

- 存在 `queryParams` 引用时禁用并关掉 `componentSwitch`。不再提示「有依赖仍可开」。  
- 没有引用时，局部选项依赖本卡其它局部值 + 已应用全局筛。

---

## 8. AI 搭盘 / YAML

- Proposal / YAML 中筛与参数的 `inputConfig.optionsSource` 直接带 `queryParams`。组件参数与筛定义一样做环、不超过 3 级和类型相容校验；非法则丢掉该参数的 `queryParams` 并警告，不原样留下。引用仍合法时，同时关掉 `componentSwitch`。  
- `filterContractDigest` 使用抽出后的 `optionsSourceIdentity`（含 refs + literals），避免 AI 合并时丢掉级联合同。  
- `applyDashboardProposal.ts`：按筛选 id 对齐筛定义。提案若仍带历史摘要 id，按该 id 对齐；布局扫描不会因为选项源不同再写出一个新 id。  
- 导入导出：旧盘无 `queryParams` 视为 `{}`，行为与现网一致。  
- 文档化给搭盘提示词：级联用 `queryParams.{ name: { ref } }`，禁止拼接字符串。

---

## 9. 迁移与兼容

| 项 | 策略 |
| --- | --- |
| 无 `queryParams` 的旧配置 | 等价空；选项请求仍可传 `{}` |
| 仅 `key__type` 的旧 filter id | id 不变；bindings 不动。再挂异源同名图仍是这一行 |
| 同 key+type 已拆成摘要 id 的旧盘 | 新扫描只产出 `` `${key}__${type}` ``。已有该 id 时沿用它的 `inputConfig` 和显示名；没有该 id 时用已有同名定义里的第一份。摘要 id 不再新生成。引用解析仍能按 id 读到配置中还在的摘要行；并回一行后，裸名和 `` `${key}__${type}` `` 都指向这唯一一行 |
| `reconcileComponentSwitchValue` → 清空 | 行为变更：原先失效变第一项；接受为对齐全局筛；changelog 一句说明 |
| 旧包 `ops-analysis-unified-filter` | 若测试仍引用，抽公共 scan/identity 后两边共用，避免两套合并键 |

不做：批量改写用户已存显示名；不做会话级「恢复上次搜索」。

---

## 10. 验收用例

1. **`screen_11`（3D 机房）**：多组件、多数据源、同名 `server_room_id`、同 `cmdb/get_room_list` → 配置表 1 行、栏上 1 个机房筛；跟随与现网一致。  
2. **三图同一数据源同名参数**：配置表 1 行、栏 1 控件；改配置一处生效。  
3. **异源 + 异 optionsSource 同名**（如指标图 A 的 `accept_metrics` 与图 B 的 `accept_metrics_b`）：配置表和栏上仍各 1 行。显示名不带数据源。已配的对象→指标→实例引用留在先到的定义上，加 B 不拆 `metric_id`，栏上不因同名多条变成「请先选择上游」。  
4. **异源 + 同 optionsSource + 同 refs**：1 行。  
5. **异源 + 异 optionsSource + 相同或不同 refs**：仍 1 行。后挂图的选项宇宙不另起控件。  
6. **多数据源各绑 timeRange / 组织**：栏上仍各 1 个，不拆。  
7. **级联两级**：机房 → 设备；改机房草稿立刻换设备选项；设备旧值失效则清空；图不变直至点搜索。  
8. **上游空**：清空机房 → 设备不请求、选项空、设备值清空（草稿）。  
9. **三级**：A→B→C 可保存；A→B→C→D 配置拒绝。  
10. **环**：A→B→A 配置拒绝。  
11. **拼接**：`queryParams.x = "pre-$id$"` 拒绝。  
12. **打开盘**：用 defaultValue（+URL）；按选项 retain；不恢复上次搜索会话。  
13. **组件内切换**：存在 `queryParams` 引用时禁用并关掉，不能在组件内切换。没有引用时可以开启；选项随本卡局部值 + 已应用全局筛变化；失效清空不选第一项。  
14. **YAML 往返**：带 `queryParams.ref` 的盘导出再导入，行为一致。  
15. **点搜索**：仅此时 applied 更新并刷图；上游抖动不刷图。

---

## 11. 建议实现文件清单与 PR 边界

### 11.1 建议改动文件（主路径）

**模型 / 纯函数**

- `web/src/app/ops-analysis/types/dataSource.ts` — `DynamicOptionsSource.queryParams`、`OptionsQueryParamValue`  
- `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts` — 导出 / 扩展 identity、normalize ref  
- `web/src/app/ops-analysis/utils/optionsQueryParamRefs.ts`（新）— 解析、环、深度、空上游  
- `web/src/app/ops-analysis/utils/scanUnifiedFilterParams.ts`（新，或从 modal 抽出）— 合并键含例外  
- `web/src/app/ops-analysis/utils/paramInputOptionsLoader.ts` — 带参请求 + 签名  
- `web/src/app/ops-analysis/utils/optionBackedFilterValue.ts` — 保持清空语义，供级联复用  
- `web/src/app/ops-analysis/utils/componentParamSwitch.ts` — 失效改清空  
- `web/src/app/ops-analysis/utils/applyDashboardProposal.ts` — 改用共享 identity  
- `web/src/app/ops-analysis/utils/widgetDataTransform.ts` — 若有扫参/id，对齐新 mergeKey  

**UI / hooks**

- `components/paramInputConfigEditor.tsx` — 查询入参编辑 + 校验  
- `components/unifiedFilter/unifiedFilterConfigModal.tsx` — 新合并；拆行副文案  
- `components/unifiedFilter/unifiedFilterBar.tsx` — 依赖重载；reconcile **不**触发 search  
- `hooks/useParamInputOptions.ts` — 接收 resolved upstream  
- 组件内切换消费处（TopN / nodeGraph / room3D 等调用 `useParamInputOptions` / reconcile 的组件）— 传入局部+applied  

**测试**

- `utils/__tests__/optionsQueryParamRefs.test.ts`（新）  
- `utils/__tests__/scanUnifiedFilterParams.test.ts`（新；含 screen_11 同类 fixture）  
- `utils/__tests__/paramInputOptionsLoader.test.ts` — 带参 / 空上游  
- `utils/__tests__/componentParamSwitch.multipleReconcile.test.ts` — 失效清空  
- `components/unifiedFilter/__tests__/…` — 草稿不搜、拆行 UI  

**文档**

- 本文；落地后回写 `ops-analysis-unified-filter.md`「明确后置」中「级联下拉」→ 指向本文并标已拍板/已实现  

### 11.2 PR 边界

- **单功能单 commit / 单 PR**：只做「选项查询参数级联」（含合并收紧 + 失效清空 + 草稿不搜）。  
- 不顺手改 Saved View、Cascader、无关筛选视觉。  
- 提交作者：`yvtian0107 <2915505011@qq.com>`；**禁止** `Co-authored-by`。  
- 从 fork `master` 开分支；复杂实现可交 **Cursor cloud**，以本文为唯一产品合同。  
- 若 cloud 不可用：本机改同一文件清单，仍保持单 PR 边界。

### 11.3 建议实现顺序（便于 cloud 拆步）

1. 类型 + `optionsQueryParamRefs` + 抽出 `optionsSourceIdentity` + 单测。  
2. Loader 带参 + 空上游短路 + hook 签名。  
3. 合并算法抽出 + 配置表副文案；`screen_11` / 时间 / 组织单测。  
4. ConfigEditor 入参 UI + 校验。  
5. FilterBar 依赖链 + reconcile 改草稿不搜。  
6. componentSwitch 失效清空 + 局部依赖解析。  
7. AI digest / YAML 往返测试。  
8. 回写决策记忆与 changelog 一句。

---

## 12. 决策来源

- 用户 grill（2026-10-30）：打开策略、失效不搜、合并收紧与时间/组织例外、`screen_11` 仍一条、配置表并一行合理性、分别配置=先拆、组件内失效改清空、上游配在参数「配置」而非总表列。2026-11-02 改为：有查询入参引用时关掉组件内切换。2026-11-03 拍板收回「异 optionsSource 必须拆」：同一画布同名同类型始终一行，异源硬并，配置以先到或已有定义为准。  
- 代码现状：`ParamInputConfigEditor`、`DynamicOptionsSource`、`paramInputOptionsLoader`（`{}`）、`filterTemplate`（仅展示）、`UnifiedFilterBar` draft+Search、`` key__type `` 合并、`reconcileComponentSwitchValue`、`optionBackedFilterValue`、`applyDashboardProposal.optionsSourceIdentity`。  
- 前序后置声明：`docs/design/product-decisions/ops-analysis-unified-filter.md` §明确后置「级联下拉」。
