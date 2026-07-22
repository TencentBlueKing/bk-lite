# Historical Superpowers change: 2026-06-09-dashboard-table-actions

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-09-dashboard-table-actions-design.md

## 目标

在运营分析仪表盘的基础表格组件中，支持给表格新增“操作列”，并在每一行渲染一个或多个固定文本操作项，用于跳转到指定 URL。

第一版只聚焦基础 `table` 组件的操作列：

- 支持在展示列中新增操作列。
- 支持为操作列配置多个固定文本操作项。
- 每个操作项支持配置按钮文案、目标 URL、打开方式和 URL 参数映射。
- URL 参数可以来自当前行字段，也可以来自固定值。

第一版不支持普通数据列字段值点击跳转，不支持预置目标页面注册表，也不要求用户手写操作列内部 key。

## 当前上下文

运营分析仪表盘的组件布局和配置存储在后端 `Dashboard.view_sets` JSON 字段中。前端通过 `valueConfig` 保存组件行为配置，例如数据源、参数、表格配置、TopN 字段、阈值颜色、统一筛选绑定等。

基础表格组件已经支持组件级表格配置：

- `tableConfig.filterFields`
- `tableConfig.columns`

本能力继续复用 `tableConfig.columns` 记录列结构，并在 `ValueConfig.actions` 中记录操作行为，不需要新增后端表结构或迁移。

## 适用范围

第一版只在 `chartType === 'table'` 的基础表格组件中开放。

不纳入本次范围：

- `eventTable`
- `topN`
- 单值卡片、仪表盘、底部操作条
- 普通数据列字段值点击跳转
- 必填参数缺失时置灰或 Tooltip
- 参数表达式或复杂计算

## 配置模型

`tableConfig.columns` 继续负责列顺序、列名、显隐、列类型。`actions` 负责操作项交互行为。

```ts
interface TableColumnConfigItem {
  key: string;
  title: string;
  visible: boolean;
  order: number;
  width?: number;
  columnType?: 'data' | 'actions';
}

interface ValueConfig {
  actions?: DashboardActionConfig[];
}

interface DashboardActionConfig {
  columnKey: string;
  text: string;
  url?: string;
  openMode?: 'sameTab' | 'newTab';
  params?: DashboardActionParamMapping[];
}

interface DashboardActionParamMapping {
  key: string;
  source: 'rowField' | 'fixed';
  sourceKey?: string;
  value?: string | number | boolean | null;
}
```

字段含义：

- `columnType: 'data'` 或缺省表示普通数据列。
- `columnType: 'actions'` 表示操作列，使用 `__actions__`、`__actions_2__` 这类内部虚拟标识。
- `columnKey` 表示操作项绑定到哪一个操作列。
- `text` 表示单元格显示的固定操作文本，例如“查看”“管理”。
- `url` 表示目标 URL，可以填写相对路径或完整 URL。
- `params` 表示追加到目标 URL 上的 query 参数映射。

## 配置 UI

### 展示列

在“表格设置 / 展示列”区域，将“添加”做成下拉入口：

- `添加数据列`
- `添加操作列`

`添加操作列` 自动创建虚拟列：

- 第一个标识为 `__actions__`
- 如果已存在，则依次生成 `__actions_2__`、`__actions_3__`
- 默认显示名称为 `操作`
- 默认 `visible: true`
- 默认 `columnType: 'actions'`

操作列的字段格不要求用户手写虚拟标识，界面上显示只读的“操作列”标签。

普通展示列的字段 key 使用可选择也可输入的控件，占位提示为“可选择或输入字段”。

### 交互配置弹框

只有操作列展示交互配置入口。弹框采用序号卡片布局，每张卡片表示一个操作项。

每个操作项包含：

- 按钮文案
- 目标 URL
- 打开方式：当前页 / 新标签
- 参数映射

目标 URL 输入框占位提示为“支持相对路径或完整 URL”。

参数映射区域使用“URL 参数”作为目标参数列文案。URL 参数支持下拉选择当前展示列字段，也支持直接输入自定义 query key，占位提示为“可选择或输入 URL 参数”。

当某个操作项没有参数映射时，不展示表头，只展示居中的“暂无参数映射”，并把新增参数按钮放在“参数映射”标题旁。

点击弹框确认后，保存当前操作列配置并提示通用文案 `common.done`。

## 渲染逻辑

`ComTable` 继续基于 `tableConfig.columns` 构造表格列，并增加操作列处理：

1. 按展示列配置解析并渲染列。
2. 如果列是 `columnType === 'actions'`，查找所有 `columnKey` 等于当前列标识的行级动作配置。
3. 在该单元格内渲染匹配到的固定文本操作项。
4. 1 到 2 个操作项直接展示；超过 2 个时展示前两个，其余放入“更多”下拉。
5. 点击操作项时解析参数映射：
   - `rowField`：读取 `record[sourceKey]`
   - `fixed`：直接使用 `value`
6. 将解析出的非空参数追加到目标 URL query 中。
7. 按 `openMode` 执行当前页跳转或新标签打开。

旧配置没有 `actions` 时，应完全按原逻辑渲染。旧列配置没有 `columnType` 时，按普通数据列处理。

## 错误处理

第一版保持轻量：

- 保存时移除完全空白的参数映射。
- 如果目标 URL 为空，点击时不跳转，并用 `message.warning` 提示。
- 第一版不处理必填参数缺失时的置灰或 Tooltip，因此不保存必填字段。

## 后续扩展

当前结构为更通用的动作能力保留空间：

- `displayMode: 'fieldValue'`：后续支持普通数据列字段值点击跳转。
- `trigger.type: 'item'`：后续支持 TopN 条目点击。
- `scope: 'widget'`：后续支持 KPI 或图表级操作。
- `scope: 'footer'`：后续支持组件底部 CTA。
- `source: 'globalFilter'`：后续支持目标参数来自仪表盘统一筛选。
- 目标 URL 可以在后续演进为预置目标页面注册表。

## 测试建议

最小测试和验证范围：

- 旧 `tableConfig.columns` 没有 `columnType` 时仍按普通列处理。
- 操作列虚拟标识生成：
  - 第一个标识是 `__actions__`
  - 重复时生成 `__actions_2__`、`__actions_3__`
- 目标 URL 拼接：
  - 支持无 query 的 URL。
  - 支持已有 query 和 hash 的 URL。
  - 空参数不追加。
- 参数解析：
  - `rowField` 能读取当前行字段。
  - `fixed` 能读取固定值。
- 表格渲染：
  - 没有 `actions` 的旧表格渲染不变。
  - 操作列可以渲染多个固定文本操作项。
  - 点击时能把 `rowField` 和 `fixed` 参数拼入链接地址。
- 实现后执行 Web 最小门禁：
  - `cd web && pnpm lint && pnpm type-check`
