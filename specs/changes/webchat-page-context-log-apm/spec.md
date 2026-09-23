# 日志搜索与 APM 页面问答

Status: done

## Problem Statement

值班人员已在日志搜索、APM 服务详情或某条调用链详情页完成筛选并盯着当前结果，希望直接问「我现在看到的这个」，而不必把查询语句、时间窗、图表或 Trace 结构再口述一遍。全站页面问答框架与监控/告警/运营分析仪表盘试点已就绪，但这三条调查路径尚未接入；未接入时仍是裸聊。

## Solution

在既有 `ai-page-context` 框架上，为三条路由各增加旁路 `*.pilot.ts`，经页面侧 `register-*.pilot.ts` 运行时登记（对齐监控告警列表、运营分析仪表盘做法）。用户在本页打开右下角机器人并发送消息时，当轮对话自动附带页面快照；未打开或未发送不采集；采集失败不挡发送；快照不落会话历史。不改业务页展示，不改 GlobalWebchat 与 `skill_channel` 注入协议。采集能力仍限于读 URL/DOM 文本与 echarts 截图，本单不扩展 recharts、html2canvas 或自定义图适配器。

## User Stories

1. As a 值班人员, I want 在日志搜索列表模式带着当前查询与时间窗问「这批日志在说什么」, so that 模型能看到查询语句与可见日志摘要而我不必复述。
2. As a 值班人员, I want 在 APM 服务详情问「我现在看到的这个」, so that 模型能看到所有 Tab 共用的身份/环境/时间窗/KPI，以及当前激活 Tab 的可见主体；概览最多 3 张 RED，错误 Tab 可再附 1 张错误率趋势。
3. As a 值班人员, I want 在调用链详情问「慢在哪一层」, so that 模型能看到服务耗时分解与错误/选中 Span 文本而我不必描述瀑布结构。
4. As a 值班人员, I want 上述页面之外仍是裸聊, so that 不会为覆盖模块而误采其它页面。
5. As a 值班人员, I want 日志终端模式、未登记路由与普通聊天行为一致, so that 不会把流式终端日志或无关页面内容注入模型。

## Implementation Decisions

### 通用

- 对接规范以 [`../webchat-page-context/app-integration.md`](../webchat-page-context/app-integration.md) 为准；本 spec 只补充三条路径的差异决策。
- 每个 pilot 导出 `getMessage`、`getContext`；APM 服务详情另导出 `getTextContext` 供 2s 截图超时回退（对齐监控仪表盘 pilot）。
- 登记方式：`registerPageContextPilot` + 对应 `page.tsx` 顶部 import register 文件；不依赖 codegen 写入 `pilots.generated.ts`。
- 文本 sections 合计约 8K、截图最多 6 张、采集总 deadline 2s 不变。
- 新增共享脱敏：`ai-page-context` 模块内 `redactSensitiveText`（轻量正则），供日志与 Trace pilot 调用；现有 pilot 无现成实现，须单测覆盖。

### 脱敏规则（日志 message、Trace 属性值写入 sections 前）

- `Bearer\s+\S+` → `Bearer [已省略]`
- `(password|passwd|api_key|apikey|secret|token)\s*[:=]\s*\S+`（不区分大小写）→ `key=[已省略]`
- 脱敏失败不挡发送；不以截断代替脱敏。

### 1. 日志搜索 `/log/search`

**场景成立条件（闸门）**

- 路由匹配 `/log/search`。
- 列表/终端 `Segmented` 的选中项对应值必须为 `list`（非 `overview` 终端模式）。
- **实现约定**：`rc-segmented` 的 radio 不把 `value` 写入 DOM，须用与业务页 `options` 顺序一致的常量 `['list', 'overview']`，取 `.ant-segmented-item-input:checked` 的索引映射为当前 view；**不得**仅依赖单一 CSS 类名或中文/英文 Segmented 文案。
- 终端模式（`LogTerminal`）本单不接：`getMessage().title` 为空，不产快照。

**采集来源（DOM 为主）**

- 页内搜索**不写 URL**；外链跳入时 URL 可有 `query`、`startTime`、`endTime`、`log_groups` 作首屏初始值，但 pilot 仍以 DOM 为权威来源。
- 查询语句：`LogQueryInput` 输入框 DOM。
- 时间窗：`TimeSelector` DOM（相对时间为 Select 选中项，绝对时间为 RangePicker input）。
- 日志分组：顶部多选 `Select` 的选中项 DOM。
- 结果范围：直方图折叠区可见的「总数」等文案（如 pagination total）。
- **已知限制**：用户修改输入框但未点「搜索」时，输入框与表格结果可能不一致；不改业务页，接受此边界。

**可见日志**

- 只采虚拟滚动表**主行**的 `timestamp` + `message`；**不含** expandable 展开行的全字段 kv。
- 不截直方图（`CustomBarChart` / recharts）。

**`currentTime` 指纹**

- 查询（DOM）+ 时间窗（DOM）+ 分组（DOM）+ 可见行 message 摘要 + 总数文案；任一变化应触发重采。

**sections 优先级（建议）**

- 身份与筛选（priority 10）：正在查看日志搜索、查询、时间、分组。
- 可见日志摘要（priority 4）：当前 DOM 可见主行 message，经脱敏后写入。

### 2. APM 服务详情 `/apm/services/[serviceId]`

最小集是**所有 Tab 的底座**，不是「整页只许这几样」。人已经切到某个 Tab 时，还要注入当前屏上正在看的那一块。

**壳（Tabs 外，每轮都采）**

- `serviceId` 来自路由；`environment` 来自 `?environment=` 或页内环境 `Select` DOM。
- 时间窗与服务目录一致：读写 `?window=`（`15m` / `1h` / `4h` / `1d` / `7d`，默认 `1h` 可省略）。目录/首页进详情会带上该参数；详情页 Segmented 变更必须写回 URL，避免快照第一行 `url:` 仍是旧窗。pilot 采集仍以 Segmented DOM 为准（`.ant-segmented-item-selected` 文案），与 URL 应对齐。
- 当前详情 Tab 读 `.ant-tabs-tab-active` 的 `data-node-key`（`overview` / `traces` / `errors` / `runtime` / `deployments` / `slo`）。未知 key 只保留壳，不把隐藏 pane 当当前内容。
- KPI 四卡：吞吐、错误率、P99、P95。选择器与错误 Tab 内四卡相同（`.text-2xl.font-bold.tabular-nums`），页头 KPI 必须排除 `.ant-tabs`。

**主体（只读当前激活 Tab）**

- 只从 `.ant-tabs-tabpane-active` 读，并用 `isHidden` 跳过隐藏 pane。Ant Design Tabs 默认不销毁非激活面板；错误/部署是点开才请求，隐藏 pane 里可能是 loading / 空态 / 旧图。
- 标题查找对齐 Trace：从 `strong` / `.ant-typography` 向上走到真正含列表/表的容器；标题用 i18n 默认值做中英正则。
- 采集能力仍是 DOM 文本 + echarts；错误 message 与表格单元格走 `redactSensitiveText`。空态 / loading 把可见文案带上。
- 文本合计约 8K，靠 priority + 段内行数上限；超了先丢明细表，留壳和摘要。

| Tab | 注入什么 | 段内上限 | priority |
|------|----------|----------|----------|
| 所有 | 壳：身份 + KPI | — | 10 / 9 |
| 概览 | Top 端点（路径 + 吞吐 + P99）；依赖（上游/下游计数 + Tag，或近窗内无调用文案） | 端点 10 行 | 端点/依赖 8 |
| 概览 | 激活 pane 内最多 3 张 RED echarts + visible-charts | 3 图 | 图 9 |
| 调用链 | 「近窗调用链样本」可见行：Trace ID、入口服务、资源、耗时、跨度数、状态 | 20 | 8 |
| 错误 | Tab 内四卡：入口请求 / 失败次数 / 错误率 / 受影响端点 | — | 9 |
| 错误 | 错误原因表、失败端点、最近失败样本；若点了端点过滤，只采可见样本并写「已按端点过滤」 | 类型 8、端点 8、样本 8 | 8 / 4 |
| 错误 | 激活 pane 内 1 张错误率趋势 echarts | 1 图 | 图 9 |
| 运行时 | 可见空文案（尚未接入 JVM/Go Runtime） | — | 8 |
| 部署 | 版本、环境、时间、状态、来源；禁止按接口 `page_size: 100` dump 全表 | 10～15 行 | 4 |
| SLO | 名称、目标、当前、错误预算 | 10 行 | 8 |

**截图**

- 只截激活 pane 内 echarts。概览最多 3 张 RED（吞吐、错误率、延迟趋势）；错误 Tab 可再截 1 张「错误率趋势」。其它 Tab `images: []`。总张数仍受全局 6 张上限。
- caption 第一段为稳定图名（图旁标题或 `aria-label`）。Progress / 列表 / Tag / 拓扑不截图。
- `getTextContext` 必须含当前 Tab 文本（端点/表/空文案），2s 超时回退不能只剩 KPI。

**`currentTime` 指纹**

- environment + 时间窗 Segmented + 当前 Tab + KPI 四值 + **当前 Tab 主体指纹**（端点路径、Trace 状态、错误次数、部署版本等）。只靠 Tab 名不够：同一 Tab 里筛选/刷新列表也要重采。

### 3. 调用链详情 `/apm/explore/traces/[traceId]`

**纯文本，不截图**

- 瀑布/火焰为自定义 DOM，本单不截图、不新做图适配器。
- `/apm/traces/[traceId]` 仅为 redirect，以 `/apm/explore/traces/[traceId]` 为准。

**采集顺序与段内上限**

| 顺序 | 内容 | priority | 段内上限 |
|------|------|----------|----------|
| 1 | 身份：Trace ID、错误 Span 数、总耗时、服务数（页头 KPI 区） | 10 | — |
| 2 | 右侧「服务耗时分解」：服务名 + 百分比 + 耗时 | 9 | — |
| 3 | 错误 Span 明细 | 8 | 最多 8 条 |
| 4 | 当前选中 Span：Descriptions + 属性表 | 4 | 属性最多 20 行 |

整体仍受 8K 总预算裁剪；超预算按 priority 丢弃（`mergePageContexts` 既有行为）。

**错误 Span：按当前视图分别识别（显式分支，禁止一套规则打天下）**

| 视图 | 判定方式 | 备注 |
|------|----------|------|
| 瀑布 | 行内存在 `.ant-tag-error` | 较可靠 |
| 列表 | 耗时单元格文本以 `⚠` 结尾 | **不得**用红色文字（慢但非错误的 Span 也会变红） |
| 火焰 | `button` 的 `background` 含 `var(--color-fail)` | 最弱，主题变更可能失效 |

- 页头 KPI 始终读取错误 Span **总数**。
- **列表模式且 `spanQuery` 非空**：只采过滤后可见的错误行，sections 注明「列表已过滤」。
- 明细条数少于页头总数时注明「共 N 个，以下可见 M 条」。
- 当前 Trace 视图模式读 Trace 视图 `Segmented` 选中项（`waterfall` / `flame` / `list`），同样用 checked radio 索引映射常量，不绑文案。

**属性与截断**

- 属性值经 `redactSensitiveText` 后写入。
- 服务端已对 Trace 做脱敏/截断；`trace.truncated` 警告若在 DOM 可见，身份 section 可带一句「展示部分 Span」。

### 参考实现

- 纯文本 + DOM 闸门：`monitor/event/alert/alert.pilot.ts`、`alarm/alarms/alarms.pilot.ts`
- echarts + `getTextContext`：`monitor/view/dashboard/dashboard.pilot.ts`

## Testing Decisions

只锁对外契约：给定 DOM fixture 时 `getMessage` / `getTextContext` / `getContext`（mock toolkit）的返回值；不测 JPEG、不测 GlobalWebchat、不测 LLM。

| 模块 | 要点 |
|------|------|
| `redact-sensitive-text` | Bearer、password=、api_key= 被替换；普通日志不误伤 |
| 日志 `search.pilot` | 非 `list` view 不采集；DOM 查询/时间/分组进入 sections；只含主行 message；脱敏生效；`currentTime` 随筛选变 |
| APM `service.pilot` | 壳每轮都有；主体只来自 active pane；隐藏 pane 的表/图不出现；概览最多 3 张 RED，错误 Tab 可有 1 张趋势；部署行数封顶；`currentTime` 随 Tab/列表变 |
| APM `trace.pilot` | 三分视图错误 Span 识别；列表过滤尊重 spanQuery；错误 8 条/属性 20 行封顶；priority 顺序 |

Prior art：`web/src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts`。

## Out of Scope

- OpsPilot 自身页面、Wiki、设置、CMDB、作业、补丁、节点管理、系统管理、策略/集成/凭据
- 监控对象实例列表与实例指标详情
- APM 首页、调用链列表、端点列表
- 运营分析拓扑/架构/大屏/报表
- 监控指标搜索、日志告警列表、日志分析看板
- 日志搜索终端模式（`LogTerminal`）
- 为 recharts、自定义瀑布/火焰、html2canvas 补采集框架
- 改业务页组件仅为对接；改 GlobalWebchat / skill_channel；放宽 8K / 6 图 / 2s 约定

## Further Notes

- 需求草稿曾写「查询、时间、日志分组已在 URL」——仅对外链跳入成立；页内主路径搜索不写 URL，以 DOM 为准（grill 确认）。
- 日志 `Segmented` 的 `value`（`list` / `overview`）须通过 checked input 索引映射，不可假设 DOM 上存在 `value="list"` 属性。
- APM 服务详情隐藏 Tab 内 echarts 仍挂载于 DOM，截图必须 scoped 到 `.ant-tabs-tabpane-active`，否则会把错误 Tab 趋势图与概览 RED 图混采。错误 Tab 允许截那 1 张趋势，其它非概览 Tab 仍不截图。

## Completion Evidence

- 旁路接入：`search.pilot.ts` / `service.pilot.ts` / `trace.pilot.ts` + 对应 `register-*-pilot.ts`，业务 `page.tsx` 仅增加 register import。
- 共享脱敏：`web/src/components/ai-page-context/redact-sensitive-text.ts`。
- 验证（2026-09-18）：`vitest run` 覆盖 redact、generate-ai-pilots 登记断言、三个 pilot + 服务详情真实页采集，**38 passed**（含当前 Tab 主体、隐藏 pane 隔离、错误 Tab 1 张趋势、部署行数封顶）；未 commit。
