# AI 悬浮机器人页面上下文（Page Context）

Status: draft

## Problem Statement

平台右下角的 AI 悬浮机器人（`GlobalWebchat` + 根目录 `webchat/` 包）目前是"裸聊"：对话与用户当前正在查看的页面完全脱节。用户在监控仪表盘看到异常曲线、在告警列表看到一堆事件时，希望直接问"这个尖峰是什么原因""哪条告警最紧急"，而机器人对页面内容一无所知。参考 Notion / GitHub Copilot / M365 Copilot 的"当前上下文注入"模式，需要让机器人在对话时自动携带当前页面的内容快照。

三个硬约束：

1. 机器人挂在根 layout，所有 app（monitor、alarm、cmdb、opspilot 等）都会出现，接入方式必须对各 app 统一。
2. 机器人未打开 / 未发消息时，不得产生任何采集或计算开销。
3. 页面含图表（折线/饼/柱状/图谱）时，底层是密集数值时序，直接喂接口数据会撑爆 LLM 上下文。

## Solution

建立"惰性注册 Provider"框架：web 侧提供全局 `AiPageContext Registry`，页面与共享图表组件通过 hook 注册**提供函数**（不注册数据本身）；webchat 在每次发消息前经桥接回调调用 `collect()` 现场采集，快照放入请求体独立字段 `page_context`。后端在 `skill_channel` 对话链路中将快照模板包裹后拼为**当前轮**用户消息的伴随内容（文本 + 图表截图走既有多模态 `image_url` 管道），**不落会话历史**——每轮 prompt 只含一份最新快照，token 不随轮数累积。图表统一走"缩小截图 + 自动 caption"，不喂原始数据。对话框内提供"已附加当前页面" chip，用户可关闭（关闭则连采集都不发生）。

## User Stories

1. As a 监控用户, I want 打开机器人直接问"当前仪表盘哪个指标异常", so that 不必手动复述页面数据。
2. As a 任意 app 用户, I want 问题与页面无关时关闭"已附加当前页面"开关, so that 不浪费 token 也不被无关上下文干扰。
3. As a 用户, I want 对话中途切换页面或页面数据刷新后继续提问, so that 机器人回答基于最新页面状态而非开场快照。
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
  - 依据：Notion AI 喂图表底层数据源而非图像（其底层是文本型 database 行，且 >500 行即放弃）；我们底层是密集时序，缩小截图（单张 ~100–300 token）+ caption 是更优形态。模型不支持 vision 时接受静默降级（chip tooltip 注明"图表理解需多模态模型"）。
- **预算控制**：文本 sections 合计封顶 ~8K 字符，超预算先裁低 priority 的 section。
- `collect()` 全程 **2 秒超时**，任一 provider 失败/超时静默跳过（记 console warning），绝不阻塞发消息。
- **已知代价（知情接受）**：pilot 模式把耦合从编译期移到运行期约定——被采集页面改 URL 参数名、换图表库时 pilot 静默失效、机器人退回裸聊。缓解：pilot 文件与页面目录同址（重构可见）+ 采集失败有 warning 日志。

### 传输与 UI（webchat 包）

- `webchat` 包保持通用性，不感知 BK-Lite 具体页面：`PlatformChat` / `Chat` 新增可选配置 `collectContext?: () => Promise<PageContext | null>`，由 `GlobalWebchat`（`web/src/app/(core)/components/global-webchat/index.tsx`）初始化时注入（回调内部读 `window.__BK_AI_PAGE_CONTEXT__`）。
- `Chat.tsx` 发消息前调用 `collectContext`，快照放入 POST body **独立字段 `page_context`**，不混进 `message`。
- 对话框输入区上方显示"📄 已附加当前页面" chip：默认开启、可点击关闭；关闭时不调用 `collectContext`（零采集开销）；registry 无注册源时不显示 chip。
- **每轮发消息都重新采集最新快照**（页面切换、数据刷新自然生效）。

### 注入侧（server/apps/opspilot）

- `execute_skill_channel_chat`（`views.py`）接受可选 `page_context`；`skill_channel_chat_service.stream_skill_channel_chat` 收口处理：
  - `append_message` **只落用户原始消息文本**，`page_context` 不写入 `SkillConversationMessage`——历史回放无旧快照，token 不随轮数累积（对齐 GitHub Copilot"隐式上下文每轮重组、不入历史"与 M365 Copilot per-turn grounding 模式）。
  - 新增 `inject_page_context(params, page_context, mode="inline")`：`inline` 模式将文本部分用 `<current_page>` 固定模板包裹，附引导语"以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考"，与截图（`image_url` 列表项）一起拼为**当前轮**多模态用户内容，复用既有 `history_service` / `metis/llm/chain/node.py` 的多模态 `HumanMessage` 路径。
  - 注入位置在对话历史之后、当前用户消息旁，保护 system prompt 前缀的 prompt cache。
  - **`mode` 为策略位**：预留 `mode="tool"` 演进方向（把页面快照注册成 `get_current_page_content` 工具，LLM 判断相关才拉取，无关问题零 token），本变更只实现 `inline`。
- 服务端对 `page_context` 做尺寸防御：文本超限截断、图片数量/单图大小超限丢弃，不报错。

### 试点

- 首批只接 **monitor 仪表盘**（`/monitor/view/dashboard/[objectKey]`），采用 **pilot 旁路模式，不改 monitor 任何现有代码**：
  - 新建 `web/src/app/monitor/(pages)/view/dashboard/dashboard.pilot.ts`：文本 sections 从 URL 读对象/实例身份（`monitorObjId`、`name`、`instance_id`、`instance_name` 均在 URL）；图表走通用 echarts DOM 采集器（时间范围等内存态经 `getOption()` 自然反映在截图与 caption 中）。
  - 验证文本 section、图表截图、caption、预算裁剪、chip 开关全链路，打磨契约后再铺开其他 app。

## Testing Decisions

- 后端（`server/apps/opspilot/tests/`）：
  - 带 `page_context` 的 chat 请求：LLM 入参含模板包裹文本与 image 项（LLM 用替身）；`SkillConversationMessage` 仅存原始消息文本。
  - 不带 / 空 `page_context`：行为与现状完全一致（回归保护）。
  - 超限防御：超长文本被截断、超量图片被丢弃且请求成功。
  - 多轮会话：第 N 轮 LLM 入参只含一份快照，历史消息不含旧快照。
- 前端：registry 的注册/注销/合并/priority 裁剪/超时降级做单元测试；截图适配器与 monitor 试点以手动验证为主。
- 只断言外部行为（LLM 收到什么、库里存了什么），不绑定内部 helper 结构。

## Out of Scope

- `mode="tool"` 工具化按需拉取（策略位已留，本变更不实现）。
- monitor 仪表盘之外页面的接入（框架就绪后由各 app 按接入方案自行接入）。
- DOM 自动抓取兜底、临时会话知识库（RAG）、图表原始数据降采样。
- `LLMModel` 增加 vision 能力标注字段与按模型能力自动裁剪图片。
- IM 渠道（企微/钉钉/公众号）与嵌入式渠道的页面上下文（仅平台悬浮机器人）。
- 前置意图判断（小模型判断问题是否页面相关）。

## Further Notes

- 竞品参照结论：Notion AI 走 embedding+RAG 读数据源、忽略图表视觉层、大表直接放弃；GitHub Copilot Chat 每请求全新组装 prompt，活动文件等隐式上下文独立分层、不入历史；M365 Copilot 每轮现场 grounding，历史只存对话。本设计的"每轮唯一快照 + 不落历史 + 用户可见开关"综合了三者已验证的模式。
- grill-me 对齐决策记录：惰性 Provider（无 DOM 兜底）→ 随请求注入 + chip 开关 + tool 策略位 → 截图(≈600px,≤4–6张)+自动 caption → 每轮重采、不落历史、注入当前轮 → 可组合多点注册 → inline 模板包裹注入 → 试点 monitor 仪表盘 → 试点采用 `.pilot` 路由旁路模式（零侵入，不改 monitor 代码；图表经 `echarts.getInstanceByDom` 通用采集；知情接受运行期约定的静默失效风险）。
