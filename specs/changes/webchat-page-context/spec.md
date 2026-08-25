# AI 悬浮机器人页面上下文（Page Context）

Status: draft

## Problem Statement

平台右下角的 AI 悬浮机器人（`GlobalWebchat` + 根目录 `webchat/` 包）目前是"裸聊"：对话与用户当前正在查看的页面完全脱节。用户在监控仪表盘看到异常曲线、在告警列表看到一堆事件时，希望直接问"这个尖峰是什么原因""哪条告警最紧急"，而机器人对页面内容一无所知。参考 Notion / GitHub Copilot / M365 Copilot 的"当前上下文注入"模式，需要让机器人在对话时自动携带当前页面的内容快照。

三个硬约束：

1. 机器人挂在根 layout，所有 app（monitor、alarm、cmdb、opspilot 等）都会出现，接入方式必须对各 app 统一。
2. 机器人未打开 / 未发消息时，不得产生任何采集或计算开销。
3. 页面含图表（折线/饼/柱状/图谱）时，底层是密集数值时序，直接喂接口数据会撑爆 LLM 上下文。

## Solution

建立"惰性注册 Provider"框架：web 侧提供全局 `AiPageContext Registry`，页面与共享图表组件通过 hook 注册**提供函数**（不注册数据本身）；webchat 在每次发消息前经桥接回调调用 `collect()` 现场采集，快照放入请求体独立字段 `page_context`。后端在 `skill_channel` 对话链路中将快照模板包裹后拼为**当前轮**用户消息的伴随内容（文本 + 图表截图走既有多模态 `image_url` 管道），**不落会话历史**——每轮 prompt 只含一份最新快照，token 不随轮数累积。图表统一走"缩小截图 + 自动 caption"，不喂原始数据。**已登记页面每轮发送默认附加页面快照**（无「已附加当前页面」chip）；未登记路由保持裸聊。

## User Stories

1. As a 监控用户, I want 打开机器人直接问"当前仪表盘哪个指标异常", so that 不必手动复述页面数据。
2. As a 任意 app 用户, I want 未接入的页面仍是裸聊、已接入页面每轮自动带当前快照, so that 不必手动开关且行为可预期。
3. As a 用户, I want 对话中途切换页面、切换时间筛选或页面数据刷新后继续提问, so that 机器人回答基于最新页面状态而非开场快照。
4. As a 业务前端开发者, I want 用 `.pilot.ts` 旁路或 hook 注册本页面上下文、图表由通用 echarts 采集器截图, so that 不必改业务页面代码且各 app 姿势统一。
5. As a 未接入页面的用户, I want 机器人保持原有裸聊行为, so that 功能渐进铺开不影响存量体验。

## Implementation Decisions

### 采集侧（web）

- **惰性注册 Provider，两种注册来源，统一进同一个 Registry**（新增共享模块 `web/src/components/ai-page-context/`）：
  1. **路由旁路 Pilot 模块（试点采用，零侵入）**：按 `<页面目录>/*.pilot.ts` 约定放置旁路文件（Next.js App Router 对非保留文件名不生成路由，安全共存）；中央 manifest（`ai-page-context/pilots.ts`）登记"路由模式 → 动态 import"，`collect()` 时按当前 URL 惰性加载匹配的 pilot 模块并执行。pilot 只依赖 URL 参数与通用图表采集，不 import 页面组件内部代码——业务页面代码零改动。
  2. **组件内 hook `useAiPageContext(provider, deps)`（保留，供愿意深度集成的页面用）**：注册提供函数，卸载自动注销，可获取内存 state 等 pilot 拿不到的信息。
  - **可组合多点注册**：同页多个注册源（pilot + hook 可并存），采集时合并，各源可标 `priority`。
  - Registry 通过 `window.__BK_AI_PAGE_CONTEXT__ = { collect(): Promise<AiPageContext> }` 暴露给 webchat 独立包（webchat 是 script 注入的独立打包产物，拿不到 web 的 React Context）。
- **快照 schema**（`AiPageContext`）：`{ url, app, title, sections: [{ id, label, content, priority }], images: [{ caption, dataUrl }] }`。
- **图表通道 = 缩小截图 + 自动 caption**，不喂原始数据、不做降采样：
  - **通用零侵入采集器**：扫描页面 DOM 中的 echarts 容器，用 `echarts.getInstanceByDom(dom)` 取实例（同 bundle 内 echarts 为单例模块），`getDataURL({ backgroundColor: '#fff' })` 后经离屏 canvas 缩放至约 **600px 宽**（保持宽高比）；caption 从 `getOption()` 通用提取（标题、序列名、Y 轴范围、最新值），一个通用函数，不要求每类图表写摘要逻辑。`getOption()` 反映的是当前实际渲染的数据窗口，天然携带用户选择的时间范围等内存态信息。recharts（SVG serialize → canvas）与 G6/X6（自带导出 API）适配器按接入页面需要再补。
  - 单页截图上限 **4–6 张**，超出按 priority 取舍。
  - 依据：Notion AI 喂图表底层数据源而非图像（其底层是文本型 database 行，且 >500 行即放弃）；我们底层是密集时序，缩小截图（单张 ~100–300 token）+ caption 是更优形态。模型不支持 vision 时服务端按 `is_multimodal` 去图留 caption。
- **预算控制**：文本 sections 合计封顶 ~8K 字符，超预算先裁低 priority 的 section。
- `collect()` 全程 **2 秒超时**，任一 provider 失败/超时静默跳过（记 `console.debug`），绝不阻塞发消息。
- **已知代价（知情接受）**：pilot 模式把耦合从编译期移到运行期约定——被采集页面改 URL 参数名、换图表库时 pilot 静默失效、机器人退回裸聊。缓解：pilot 文件与页面目录同址（重构可见）+ 采集失败有 debug 日志。

### 传输与 UI（webchat 包）

- `webchat` 包保持通用性，不感知 BK-Lite 具体页面：`PlatformChat` / `Chat` 新增可选配置 `collectContext?: () => Promise<PageContext | null>`，由 `GlobalWebchat`（`web/src/app/(core)/components/global-webchat/index.tsx`）初始化时注入（回调内部读 `window.__BK_AI_PAGE_CONTEXT__`）。
- `Chat.tsx` 发消息前调用 `collectContext`，快照放入 POST body **独立字段 `page_context`**，不混进 `message`。有 `collectContext` 且 registry 有匹配源时**每轮默认采集**（已去掉「已附加当前页面」chip）。
- **每轮发消息都重新采集最新快照**（页面切换、筛选变更经 `currentTime`、数据刷新自然生效）。

### 注入侧（server/apps/opspilot）

- `execute_skill_channel_chat`（`views.py`）接受可选 `page_context`；`skill_channel_chat_service.stream_skill_channel_chat` 收口处理：
  - `append_message` **只落用户原始消息文本**，`page_context` 不写入 `SkillConversationMessage`——历史回放无旧快照，token 不随轮数累积（对齐 GitHub Copilot"隐式上下文每轮重组、不入历史"与 M365 Copilot per-turn grounding 模式）。
  - 新增 `inject_page_context(params, page_context, mode="inline")`：`inline` 模式将文本部分用 `<current_page>` 固定模板包裹，附引导语"以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考"，与截图（`image_url` 列表项）一起拼为**当前轮**多模态用户内容，复用既有 `history_service` / `metis/llm/chain/node.py` 的多模态 `HumanMessage` 路径。
  - 注入位置在对话历史之后、当前用户消息旁，保护 system prompt 前缀的 prompt cache。
  - **`mode` 为策略位**：预留 `mode="tool"` 演进方向（把页面快照注册成 `get_current_page_content` 工具，LLM 判断相关才拉取，无关问题零 token），本变更只实现 `inline`。
- 服务端对 `page_context` 做尺寸防御：文本超限截断、图片数量/单图大小超限丢弃，不报错。

### 试点

- 其它 app 按 [`app-integration.md`](./app-integration.md) 自行接入；框架与后端注入已就绪，业务页默认零改动。
- 首批只接 **monitor 仪表盘**（`/monitor/view/dashboard/[objectKey]`），采用 **pilot 旁路模式，不改 monitor 任何现有代码**：
  - 新建 `web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`：文本 sections 从 URL 读对象/实例身份（`monitorObjId`、`name`、`instance_id`、`instance_name` 均在 URL）；图表走通用 echarts DOM 采集器（时间范围等内存态经 `getOption()` 自然反映在截图与 caption 中）。
  - 验证文本 section、图表截图、caption、预算裁剪、筛选变更重采全链路，打磨契约后再铺开其他 app。

## 修订 v2：getMessage/getContext 契约、筛选收口服务端、多模态标注

> 2026-08-24 grill-me 对齐。动因：前端按问法筛图不保险（主题词误伤，如问「网络吞吐趋势」带出「网络错误速率」「磁盘吞吐趋势」）；pilot 手工登记 manifest 有维护成本；模型不支持多模态时传图会异常。本节覆盖 v1 中冲突的条目，未提及的 v1 决策继续有效。

### 采集契约（覆盖 v1「pilot 导出 collect(hint)」）

- 每个接入页面仍放同目录 `*.pilot.ts`，但导出两个函数：
  - `getMessage(): { title, currentTime }`——**每次问答必调**。`title` 由接入方自定义（可写死、可拼 ID），作为缓存 key；重名后果接入方自负，**不用 URL 当 key**（详情页 ID 可能不在 URL 上，会串缓存）。`currentTime` 由接入方在数据刷新、筛选变化、切视图时更新；**不提供视为永远过期**（每次重采，宁可多采不可发旧图）。
  - `getContext(toolkit): Promise<Partial<AiPageContext>>`——采集页面实际内容（文本 sections + 图表截图）。仅当缓存未命中（title 无记录或 currentTime 变化）才调用。
- **缓存**：opspilot 侧 registry 内存 Map（`title → { currentTime, content }`），不落 localStorage / 磁盘。命中则直接复用旧 content。
- **前端不再按问题筛图**：`getContext` 全量采集（6 张截图 / 8K 文本上限保留，按 DOM 顺序、有标题者优先截到上限）；`rankChartsByQuestion` 等问法匹配逻辑从前端删除。**筛选统一收口服务端**：`_focus_page_context`（点名图表只留匹配截图）；`_history_for_focused_charts`：**本轮点名任一图表即清空对话历史**（见修订 v3），防止换时间筛选后复述旧时间窗。
- 所有提问统一按页面问答处理，不做寒暄 / 意图判断；未登记路由 = 裸聊（无页面快照）。

### 解耦与收集（覆盖 v1「中央 manifest 手工登记」）

- **解耦目标**：opspilot 未加载时其它模块不得异常。手段是运行时依赖方向控制，不是字面禁止 import：
  - 截图 / caption 提取升为**中性公共模块** `web/src/components/chart-snapshot/`（echarts 截图、缩放、`captionFromOption`），任何 app 可直接 import，与 opspilot 运行时无关；
  - `ai-page-context/`（registry、bridge、manifest、缓存）归 opspilot 侧；app 对它只允许 `import type`（编译期擦除）；
  - 运行时工具经 `getContext(toolkit)` 参数注入。
- **codegen 自动收集**：构建期脚本扫 `web/src/app/**/*.pilot.ts` 生成 manifest（`pilots.generated.ts`），挂 dev / build 前置。约束：
  - **路由从文件位置推导**（去掉 `(group)` 段、去文件名做前缀匹配），pilot 必须与所服务页面同目录——不加载模块即可判断路由是否命中，保住惰性；
  - fail-safe：脚本任何错误写空 manifest 并 exit 0，不阻断启动；
  - 确定性输出（路径排序、无时间戳）、内容不变不写盘——生成物**提交进 git**，fresh clone 不跑脚本也可编译；日常 dev 不产生 git 噪音；
  - 运行中新增 `.pilot.ts` 需重启 dev（接受，低频）；Windows 路径分隔符须 normalize；
  - 动态 import 仅在「点发送且路由命中」时执行，且 load 失败 catch 降级为无上下文——opspilot 未挂载或 pilot 损坏都不影响业务页。

### 超限行为（新增）

- **单轮页面内容一次会话装不下**：直接以错误流提示「当前页面内容过多，无法进行问答」，不做静默裁剪救场。此类页面视为设计问题或不适合接入，不为其优化。
- **会话累计超限**（历史 + 本轮估算超阈值）：错误流提示「上下文过长，请新开会话」。「新开会话」只用于这种情形。
- 阈值为服务端常量（token 估算基于既有 ingest report），测试经 patch 常量覆盖两条分支。

### 模型多模态标注（从 Out of Scope 移入）

- `LLMModel` 增加 `is_multimodal`（BooleanField，**默认 True** 保持现状），能力无法跨厂商自动探测，由管理员在**模型管理**处勾选——标注在模型上而非智能体配置上，一次标注全部技能继承。
- 问答注入前，若 `skill.llm_model.is_multimodal` 为 False，服务端**丢弃全部 `image_url` 项**（含用户上传图），保留 `<current_page>` 文本与「图表说明」caption——caption 本身就是数据摘要（图名 + 序列 + 最新值），**不回退为原始数据传输**（密集时序撑 token，v1 已否决）。丢弃记日志一行。
- 前端不感知模型能力，照常采集照常传，由服务端统一裁剪（上行多传截图属可接受浪费，换前端零改动）。

### v2 影响面

- webchat 包**无需改动**（`collectContext({ message })` 签名不变，hint 由新 registry 忽略）；不必重建 bundle。
- monitor 试点 `dashboard.pilot.ts` 迁移到新契约；`app-integration.md` 按新契约重写。
- 前端删除 `chart-relevance.ts`（问法匹配下沉服务端，服务端已有同构实现与测试）。

## Testing Decisions

- 后端（`server/apps/opspilot/tests/`）：
  - 带 `page_context` 的 chat 请求：LLM 入参含模板包裹文本与 image 项（LLM 用替身）；`SkillConversationMessage` 仅存原始消息文本。
  - 不带 / 空 `page_context`：行为与现状完全一致（回归保护）。
  - 超限防御：超长文本被截断、超量图片被丢弃且请求成功。
  - 多轮会话：第 N 轮 LLM 入参只含一份快照，历史消息不含旧快照。
- 前端：registry 的注册/注销/合并/priority 裁剪/超时降级做单元测试；截图适配器与 monitor 试点以手动验证为主。
- 只断言外部行为（LLM 收到什么、库里存了什么），不绑定内部 helper 结构。
- v2 增补：
  - registry 缓存：同 title + 同 currentTime → `getContext` 只调一次；currentTime 变化 / 缺失 → 重采。
  - codegen：路由推导（含 `(group)` 剥离、`[param]` 前缀截断）、确定性输出、fail-safe 空 manifest。
  - 服务端：`is_multimodal=False` 时 LLM 入参无 `image_url` 项且文本保留图表说明；True 时行为不变。单轮内容超限 / 会话累计超限分别返回对应错误流且不调用 LLM（patch 阈值常量驱动）。
- v3 增补：
  - 点名图表 → `history_messages=0`；筛选变更后新会话回答对齐新 `时间筛选` / caption `横轴`。
  - pilot `currentTime` 随 DOM 筛选文案变化（可不改业务页）。

## Out of Scope

- `mode="tool"` 工具化按需拉取（策略位已留，本变更不实现）。
- monitor 仪表盘之外页面的接入（框架已就绪；其它 app 按 [`app-integration.md`](./app-integration.md) 自行接入）。
- DOM 自动抓取兜底、临时会话知识库（RAG）、图表原始数据降采样。
- IM 渠道（企微/钉钉/公众号）与嵌入式渠道的页面上下文（仅平台悬浮机器人）。
- 前置意图判断（小模型判断问题是否页面相关）——统一按页面问答处理；未登记路由 = 裸聊。
- 按模型上下文窗口动态调整超限阈值（v2 用服务端常量，窗口感知留待后续）。
- 为对接而改业务页写入 URL / 全局事件（默认只用 pilot DOM/URL 嗅探；见修订 v3）。

## 修订 v3：默认附加、筛选指纹、点名丢历史、横轴 caption

> 2026-08-25 落地对齐。覆盖 v1/v2 中关于 chip 与「仅焦点切换才丢历史」的冲突条目。

### UI 与采集

- **去掉「已附加当前页面」chip**：已登记页每轮发送默认 `collectContext`；未登记页无快照。
- **筛选 / 刷新不改业务页**：`currentTime` 由 pilot 从 DOM / URL / 可见 KPI 文案合成（监控：`toolbarTimeSelector` + `statValue` + 采集/运行状态）。KPI 为窗末瞬时值，切窗后 headline 可能相同——指纹必须含筛选文案。
- **caption 横轴**：`chart-snapshot.captionFromOption` / `timeSpanFromOption` 对 unix 秒序列附加 `横轴: HH:mm~HH:mm`，减轻只靠看图猜时间窗。
- 监控 pilot 可在采集时 `console.info('[ai-page-context] page data updated at', …)` 便于手测。

### 服务端

- `_history_for_focused_charts`：**本轮 `_focused_titles` 非空 → 返回空历史**（同一张图换时间筛选再问也不保留上一问）。未点名图表的追问仍带历史。
- 引导语明确：时间范围 / 横轴 / KPI 以本轮 `<current_page>` 为准，禁止沿用历史旧时间窗。

对接细则见 [`app-integration.md`](./app-integration.md)。

## Further Notes

- 其它 app 对接规范：[`app-integration.md`](./app-integration.md)。
- 竞品参照结论：Notion AI 走 embedding+RAG 读数据源、忽略图表视觉层、大表直接放弃；GitHub Copilot Chat 每请求全新组装 prompt，活动文件等隐式上下文独立分层、不入历史；M365 Copilot 每轮现场 grounding，历史只存对话。本设计的"每轮唯一快照 + 不落历史 + 已登记页默认附加"综合了三者已验证的模式。
- grill-me 对齐决策记录：惰性 Provider（无 DOM 兜底）→ 随请求注入 + tool 策略位 → 截图(≈600px,≤4–6张)+自动 caption → 每轮重采、不落历史、注入当前轮 → 可组合多点注册 → inline 模板包裹注入 → 试点 monitor 仪表盘 → 试点采用 `.pilot` 路由旁路模式（零侵入，不改 monitor 代码；图表经 `echarts.getInstanceByDom` 通用采集；知情接受运行期约定的静默失效风险）。
- grill-me v2 对齐决策记录（2026-08-24）：前端去筛选、服务端聚焦与丢历史 → 缓存 key 用接入方自定义 title（拒绝 URL）、currentTime 接入方维护、缺失视为永远过期 → 单页 content 装不下直接提示「内容过多，无法进行问答」、新开会话提示只用于会话累计超限 → 截图提中性公共模块 chart-snapshot、toolkit 参数注入、`import type` 豁免 → codegen 扫 `*.pilot.ts` → `LLMModel.is_multimodal`。
- 落地修订 v3（2026-08-25）：去掉 chip 默认附加；pilot DOM 指纹驱动 `currentTime`；点名图表一律丢历史；caption 带横轴；对接文档同步。
