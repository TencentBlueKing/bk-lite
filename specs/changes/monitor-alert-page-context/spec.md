# 告警列表页面问答

Status: done

## Problem Statement

运维人员在监控告警中心看活跃告警或历史告警时，右侧智能问答仍然看不见当前筛选结果。改级别、切对象、翻页之后，仍要把列表里的告警名称、级别和资产手工复述给机器人。打开某一条告警详情、想针对这条告警（含 Event 时间线）继续问时，机器人同样不知道抽屉里是哪一条。监控仪表盘和运营分析仪表盘已经按同一套全站问答接上当前页；告警列表还没有。

用户要的是对着**已经看见的列表**和**已经打开的那条详情**提问，不是再做一个聊天窗口，也不是把筛选条件下的全量告警 dump 进模型。

## Solution

告警列表按全站页面问答对接规范接入：用户在 `/monitor/event/alert` 的活跃告警或历史告警下提问，智能问答自动带上当轮页面快照。未打开详情时，快照等于当前筛选条件加上当前页已渲染的表格行。打开详情抽屉时，同一轮快照再附上这条告警的字段和 Event 列表。插件额外 Tab、未打开的详情、未翻到的列表页保持不采集。公共上限沿用全站框架（约 8K 字、最多 6 张缩略图、约 2 秒采集），本期不放宽，也不为 Recharts 补截图适配器。

## User Stories

1. As an 运维人员, I want 在活跃告警或历史告警列表直接问「现在筛出来的哪些最紧急」, so that 不必把当前页的级别、名称和资产手工复述给智能问答。
2. As an 运维人员, I want 改完对象树、级别、状态、时间、搜索或翻页后再提问时答案跟新结果走, so that 机器人不会复述上一问的旧筛选或旧页。
3. As an 运维人员, I want 快照写明共 N 条、当前第 X 页, so that 模型知道这是当前页切片，不会把 20 行当成筛选全量。
4. As an 运维人员, I want 打开某一条告警详情后，提问能同时用到当前列表和这条详情, so that 沟通可以针对这条告警，而不只是列表摘要。
5. As an 运维人员, I want 详情里的 Event 列表进入快照，即使我还停在「信息」Tab, so that 问「这条告警怎么演变的」不必先切到事件 Tab 再复述时间线。
6. As an 运维人员, I want 关掉详情后再提问时不再带上一条告警的详情, so that 对话回到当前列表。
7. As an 运维人员, I want 列表或详情还在加载时问答明确未就绪、且不把空白当成零, so that 总览不会系统性说错。
8. As an 运维人员, I want 打开插件额外 Tab 时仍是普通聊天, so that 不会把主机告警列表的采集规则套到别的槽位上。

## Implementation Decisions

- 第一期只接监控告警中心主机列表：pathname `/monitor/event/alert`，且当前 Tab 为 `activeAlarms` 或 `historicalAlarms`。活跃与历史共用一个 pilot。插件 `AppSlot` 额外 Tab、告警策略页、日志告警页不在本期。
- 不新做问答 UI。继续用全站智能问答；发送前采集、快照进当轮 `page_context`、不写入会话历史——全部复用已有框架，不改 GlobalWebchat，不改 skill_channel 注入，不放宽图片/文本预算，不新增 Recharts 截图适配器。
- 列表采集用页面旁路 pilot：`web/src/app/monitor/(pages)/event/alert/alert.pilot.ts`，导出 `getMessage` / `getContext` / `getTextContext`。只读 URL、DOM；不改列表页可见展示。登记走现有 `*.pilot.ts` codegen，路径前缀 `/monitor/event/alert/`。**闸门在 pilot 内认 Tab**，不把 `activeAlarms` / `historicalAlarms` 写进 codegen。非主机 Tab 返回空快照（裸聊）。
- `getMessage().title` 用列表身份，不用 URL 整段当缓存键。约定：`monitor-alert:` + 当前 Tab + `:` +（查询参数 `objId` 或 `all`）。`currentTime` 必须随 Tab、对象、级别、状态、时间筛选文案、搜索词、分页（第 X 页 / 共 N 条）和当前页行指纹变化。活跃告警的时间控件只有刷新，文案写「活跃告警不按时间窗过滤」；**刷新频率不充当时间窗**，单独改刷新间隔不得让 `currentTime` 变。省略 `currentTime` 视为每轮重采。
- 列表查询范围锁在本页壳上：`[class*="alarmList"]` 与左侧 `[class*="filters"]`。不扫 body 上其它表格，不把详情抽屉里的内容误当成列表行。
- 列表文字通道（优先级从高到低）：
  1. 身份 + 当前筛选（priority 10）：正在看告警列表、活跃/历史、对象树选中文案、`objId`、级别、状态、时间窗或「不按时间窗过滤」、搜索词。
  2. 结果范围（priority 8）：共 N 条、当前第 X 页、每页 Y 条。
  3. 分布图文字（priority 6，可选）：Collapse 展开时从可见 SVG/图例读摘要；折叠则组件不在 DOM，跳过。加载中/空态带屏幕文案。
  4. 当前页表格（priority 4）：已渲染行 + 表头，去掉末列操作按钮（详情 / 关闭）。抄当前页全部已渲染行（默认 pageSize 20），不抄未翻到的页，不另打列表接口。
- 列表 `getContext` 第一期 `images: []`。分布图是 Recharts，不走 ECharts 采集器。超时走 `getTextContext`，至少带上筛选和当前页表行。失败 `console.debug` 后跳过，不挡发送。
- 级别/状态多选若显示「已选 N 项」，用 rest tag 的 `title` 展开已选项，对齐运营分析表选择采集。
- 打开告警详情时，**同一轮合并列表快照与详情快照**。详情不能只靠抽屉 DOM：信息 Tab 与事件 Tab 互斥挂载，Event 目前要点「事件」才请求，时间线是虚拟列表，视口外行不在 DOM。因此详情走 hook，这是对接规范允许的例外（内存态 DOM 读不到）。
- 详情对 `AlertDetail` 做两处**无展示**改动，不改抽屉布局：
  1. `showModal` 拿到行数据后立刻用该行 `id` 请求 Event 列表（沿用现有 `getMonitorEventDetail`，`page_size: -1`），与拉指标并行，不必等指标返回，也不必先切到事件 Tab。切到事件 Tab 时若已有数据，沿用现有刷新逻辑即可，不要求去掉。
  2. 抽屉可见时用 `useAiPageContext` 注册详情提供函数；关闭后返回空 section。Hook 每轮发送都执行，不走 pilot 的 `title` 缓存。
- 详情文字通道（优先级高于列表表行，避免 8K 把正在看的这条裁掉）：
  1. 详情身份（priority 10）：告警 id、名称、级别、状态、类型、更新时间、资产。
  2. 详情字段（priority 9）：维度、策略名、通知/通知人、操作人、结束时间（若有）、指标名与单位；PMQ 则带当前已加载的报文键值。不依赖当前停留在哪个详情 Tab。
  3. Event 列表（priority 8）：每条含时间、动作、级别、内容、值。按 `event_time` 降序取**最近 30 条**，并写「共 N 条，已附最近 M 条」。N=0 且已加载完则写空态，不编造事件。
- 详情指标图是 Recharts，不截图；只保留图名/单位等文字。不采集关闭按钮、权限、操作区。禁止凭据、token、密钥。
- 详情加载中：身份仍在，字段/事件行写「详情加载中」或「事件加载中」，不把空列表当成零。换一条告警后下一问必须用新 id 的详情；关掉抽屉后下一问不得再带详情 section。
- 超 8K 时由现有 `mergePageContexts` 按 priority 丢弃。固定顺序含义：列表身份与筛选、详情身份、详情字段、Event、列表分页、分布图文字、列表表行。表行和超出 30 条的事件可以少抄，身份和当前这条告警不能先被挤掉。
- 数据范围等于用户已经能看见的内容（含其权限下已查出的数），不扩大权限。列表不额外请求；详情只把**打开这条时业务页本来就会（或点事件 Tab 就会）拉取的 Event** 提前拉好并注入，不新开权限、不拉其它告警的 Event。

## Testing Decisions

好测试只锁对外契约：给定 DOM/URL 或详情 provider 入参时，`getMessage` / `getTextContext` / 详情快照纯函数的返回值（title、currentTime、sections 内容与优先级、行数上限、加载中跳过）。不测 JPEG、不测 Recharts 像素、不测 GlobalWebchat、不测 skill_channel、不测 LLM 回答质量。

列表 pilot（jsdom 夹具，对齐两套仪表盘 pilot）：

- 当前 Tab 不是 `activeAlarms` / `historicalAlarms` 时不产生页面快照；主机 Tab 时 title 含 tab 与 `objId`
- 改筛选文案、翻页、表行则 `currentTime` 变化；只改刷新间隔不变
- 文字含身份、筛选、共 N 条、当前页全部已渲染行；不含操作列、不含第 2 页未渲染行
- 超预算时身份和筛选仍在，表行可被裁掉
- 表格加载中不把空白当零；空表带空态；分布图折叠无图文
- 活跃告警快照含「不按时间窗过滤」；历史告警含时间筛选文案
- codegen 文件位置推导为 `/monitor/event/alert/`；Tab 闸门在 pilot 内测，不写进 codegen

详情 hook / 纯函数：

- 抽屉未打开：无详情 section
- 打开后即含详情身份、字段、Event（即使当前 Tab 仍是信息）
- Event 超过 30 条只留最近 30，并带总数
- 关闭抽屉或换一条告警 id 后，快照不再含旧详情
- 详情/事件加载中文案出现，且不把空事件当「没有发生过事件」

手测（不替代单测）：告警列表发送请求带 `page_context`；改筛选后 Console 指纹变化；打开详情后再问，请求文本含列表筛选与该条 Event；关掉详情后不再含该条详情；策略页等未登记路由仍是裸聊。

## Out of Scope

- 插件额外 Tab、告警策略/模板页、日志告警页、告警中心其它产品线的页面快照
- 把筛选条件下的全量告警列表 dump 进模型，或另打列表接口拉未渲染页
- 为 Recharts 分布图/详情指标图补公共截图适配器，或放宽 6 张 / 8K / 2 秒
- 新问答 UI、改 GlobalWebchat 或后端注入
- 让问答关闭告警、改策略或执行运维操作（沿用现有智能体安全限制）
- 为对接而改列表页可见展示，或把筛选写入 URL
- 详情抽屉的可见布局改动（预取 Event 与 hook 不得改变信息/事件 Tab 的展示）

## Further Notes

产品范围是「对着已经看见的告警提问」。列表切片来自全站页面问答的反 dump 约束，不是告警中心单独抠的。详情 Event 走 hook，是因为虚拟列表和 Tab 互斥挂载让 DOM 读不全；这不授权其它页面默认改业务组件。每轮快照不进历史，是为了筛选一变或关掉详情后旧告警立刻作废。

对接写法以 [页面问答 app 接入规范](../webchat-page-context/app-integration.md) 为准；监控仪表盘与运营分析仪表盘 pilot 是列表侧参考实现。日志告警、策略页、Recharts 截图若要做，另开变更并重新评审公共预算。

## Verification

- `cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/alert/__tests__/alert.pilot.test.ts' 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.context.test.ts' 'src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx'`
