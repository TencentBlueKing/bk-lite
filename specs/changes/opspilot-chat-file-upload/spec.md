# OpsPilot 对话文件上传与历史附件持久化

Status: proposed

## Problem Statement

OpsPilot 对话目前只支持图片上传，且实现存在结构性缺陷：

- **图片不持久化**：图片在前端转 base64 data URI 内联进请求体（`web/src/app/opspilot/components/custom-chat-sse/index.tsx`），后端拆出后放进 `extra_config.current_image_data` 直喂多模态 LLM（`services/chat_service.py::format_chat_server_kwargs` → `services/history_service.py::process_user_message_and_images`），不落 MinIO、不落数据库。历史表（`SkillConversationMessage.content`、`BotConversationHistory.conversation`）均为纯 TextField，渠道落库明确只抽纯文本（`skill_channel_chat_service.py::persistable_user_message_text`）。刷新页面后当初上传的图片就看不到了。
- **入口残缺**：图片上传实际只在技能调试聊天（`skill/detail/settings/page.tsx` → `execute_agui`）生效；Skill Web Chat（`skill/chat/page.tsx`）与 Studio Chat 页面有上传按钮 UI 但发送 payload 不带图片。
- **不支持文档**：PDF/Word/Excel/txt 等文件完全无法在对话中上传，而仓库已有完整的 MarkItDown 文档解析能力（`services/wiki/parsing/markitdown_parser.py`）仅用于知识库导入。

主流产品（ChatGPT Library、Claude）均支持历史对话中查看并下载当初上传的文件，本需求对齐该行为。

## Solution

引入「上传先行 + 附件持久化」的统一附件链路：

1. 新增附件上传 API 与 `ChatAttachment` 模型：前端选文件即上传，后端存 MinIO、建附件记录并触发解析，返回附件 ID；发消息时只携带附件 ID 列表。
2. 文档（pdf/docx/pptx/xlsx/csv/txt/md）复用 MarkItDown 解析成文本，缓存到附件记录；聊天时从 DB 读缓存解析文本按预算注入 prompt。图片迁移到同一上传链路，发给 LLM 时由后端从 MinIO 取出喂 vision。
3. 消息落库时回填附件的 message 外键；历史 API 序列化消息时带出附件元数据，前端历史界面回显图片缩略图与文件卡片，支持下载。
4. 下载/上传端点统一双鉴权：登录态 + `Api-Authorization`（复用嵌入式渠道现有的密钥→用户/组解析），覆盖嵌入式无登录态场景。
5. 生效范围：技能调试聊天、Skill Web Chat、平台助手（PlatformChat）、嵌入式 webchat 四个入口（前三者与嵌入式共用 `stream_skill_channel_chat` 执行核与 `SkillConversation` 历史表；调试聊天走 `execute_agui`，仅当轮附件生效、不做历史回显）。

## User Stories

1. As a 运维人员, I want 在对话里上传 PDF/Word/Excel 让智能体阅读分析, so that 不必先把文件导入知识库再提问。
2. As a 运维人员, I want 上传文件后继续追问文件内容, so that 整个会话里模型都记得这份文件。
3. As a 运维人员, I want 在对话历史里看到当初上传的文件和图片并能下载, so that 回溯会话时上下文完整。
4. As a 第三方网站的终端用户, I want 在嵌入式对话挂件里上传文件, so that 嵌入场景与平台内体验一致。
5. As a 运维人员, I want 文件解析失败或未完成时被明确告知而不是静默发送, so that 不会出现模型没读到文件却装作读过的误导性回答。

## Implementation Decisions

### 附件模型与存储

- 新建 `ChatAttachment` 模型：`file`（FileField，`MinioBackend(bucket_name="munchkin-private")`，参照 `WorkflowAttachmentAsset`）、原始文件名、MIME、大小、`status`（`pending` / `ready` / `failed`）、解析文本（`parsed_text`，文档专用）、失败原因、上传者/组、所属会话外键（可空）、**可空的 message 外键**（上传时为空，消息落库时回填）、`created_at`。
- 附件表是单一事实源：孤儿清理、下载权限校验、历史序列化都以它为准。消息正文 `content` 保持纯文本不动，老消息序列化时 `attachments` 为空数组，天然向后兼容。
- 生命周期：删除会话时级联删除附件记录与 MinIO 对象；定时任务清理「message 外键为空且创建超 24h」的孤儿附件，同时把长时间卡 `pending` 的记录转 `failed`（防任务丢失导致永久 pending）。不设整体 TTL。

### 上传与解析

- 上传 API（双鉴权，见「鉴权」节）接收单文件，后端校验白名单与大小（**以 Content-Type/magic bytes 为准，不只看扩展名**）：
  - 文档：`pdf / docx / pptx / xlsx / csv / txt / md`，单文件 ≤ 20MB；
  - 图片：`jpeg / png / gif / webp`，单文件 ≤ 5MB；
  - 明确拒绝可执行文件与压缩包（zip 解包解析不做，规避 zip bomb）。
- 解析时机 = 上传即解析：
  - 图片与轻文本（`txt/md/csv`）在上传请求内同步就绪（图片无需解析，直接 `ready`）；
  - 重格式（`pdf/docx/pptx/xlsx`）投**独立 Celery 队列**（不与 wiki 导入等重任务混排）用 MarkItDown 解析，成功写 `parsed_text` 转 `ready`，失败转 `failed`；任务设硬超时（120s），超时即 `failed`。
- 提供附件状态查询接口供前端轮询。

### 发送门禁（两层防线）

- 前端：附件存在 `pending` 时发送按钮置灰并提示「文件解析中」，`failed` 的附件不可随消息发出。
- 服务端兜底：聊天入口收到带附件 ID 的消息时同步校验状态，任一附件非 `ready` → **立即拒绝**（明确错误码与文案），不等待、不静默跳过。防竞态、多标签页、第三方直调嵌入式 API（它本质是开放 API）与前端 bug。
- 聊天链路只读 DB 中已缓存的 `parsed_text`，与 Celery 队列状态完全解耦；**LLM 调用永不等待解析**。

### 消息协议与上下文注入

- 四个入口的消息 payload 新增附件 ID 列表字段（具体字段名实现时统一，兼容现有 `message` / `user_message` 结构）；废弃前端 base64 内联图片路径，图片同样走附件 ID。
- 单条消息附件合计 ≤ 5 个（文档+图片），服务端校验。
- 当轮注入：文档的 `parsed_text` 按预算截断后拼进 prompt；图片由后端从 MinIO 读出转为 vision 消息（沿用 `chain/node.py::human_message_with_images` 的 OpenAI `image_url` 格式与 `drop_images_from_user_message` 非多模态降级）。
- 预算两级控制：单文件截断上限 + 全部注入内容总预算，对齐现有 context budget 机制（参照 `test_chat_service_context_budget` 锁定的行为）；发生截断时在注入内容中显式标注「文件已截断」。
- **多轮留存**：拼接 chat_history 时检测历史消息带文档附件 → 从附件记录重读 `parsed_text` 注入（受同一预算约束；预算不足时优先保最近轮次的文件，老文件降级为「[文件: xxx.pdf]」占位）。**图片仅当轮生效**，历史中可见可下载但不向模型回放。
- 解析文本注入 prompt 的提示注入风险与 Wiki 导入同类，按现有治理方式处理，不新增防线。

### 鉴权与下载

- 下载走权限校验端点（附件 ID → 附件 → 会话 → 用户/组归属链校验），**不发时效签名 URL**。
- 上传与下载端点同时接受两种鉴权：平台登录态；`Api-Authorization` 请求头（复用 `skill_channel_chat_service.py::authenticate_embedded` 的 `UserAPISecret` → 用户/组解析与组范围判断）。
- 嵌入式挂件内图片缩略图不能用裸 `<img src>`（需携带鉴权头），用 fetch + blob URL 渲染。

### 历史回显

- `serialize_skill_session_messages` 及相关历史序列化补充 `attachments: [{id, name, mime, size, status}]`。
- 平台内历史界面（skill/chat 会话列表、历史页）按类型渲染：图片缩略图（经下载端点取图）、文档文件卡片（点击下载）。
- 嵌入式挂件 localStorage 历史只存附件 ID + 元数据，不存 base64；渲染时经下载端点取内容。
- 技能调试聊天（`execute_agui`）不做历史附件回显，附件仅当轮生效；其上传同样走附件链路以复用解析与校验。

### 入口接通与前端

- `CustomChatSSE` 上传控件放开文件类型（原仅 `accept="image/*"`），改为「选文件→调上传 API→展示状态 chips」；移除 FileReader base64 路径。
- 接通 Skill Web Chat（`skill/chat/page.tsx`）与平台助手的发送链路（现状是有按钮但 payload 不带附件）。
- 嵌入式挂件（`webchat/packages/webchat-ui/Chat.tsx`）同步改造：上传先行 + 附件 ID 发送，图片数量上限从 4 统一到 5。
- 文件上传能力默认全量开启，**不加技能级开关**（文档走文本注入，与模型多模态能力无关）。

## Testing Decisions

- 附件模型与生命周期：上传→`pending`→`ready`/`failed` 状态机；孤儿清理只删「无 message 外键且超 24h」；卡 `pending` 超时收敛为 `failed`；删会话级联删附件与 MinIO 对象。
- 上传校验：白名单外类型/超大小/伪造扩展名（magic bytes 不符）被拒；单消息附件数 > 5 被拒。
- 发送门禁：带 `pending`/`failed` 附件的聊天请求被服务端立即拒绝并返回明确错误；全 `ready` 时正常进入 LLM 链路；断言链路中不存在任何等待解析的逻辑。
- 上下文注入：当轮文档 `parsed_text` 进 prompt 且超预算时截断并带标注；历史轮文档重新注入、预算不足时老文件降为占位；图片当轮走 vision 格式、历史轮不回放；非多模态模型仍正确丢弃图片。
- 鉴权：登录态与 `Api-Authorization` 各自可上传/下载；跨组/无权会话的附件下载被拒；双租户测试覆盖（若端点经 OpenAPI 网关暴露，按 `specs/capabilities/openapi-gateway.md` 登记）。
- 历史序列化：带附件消息返回 `attachments` 元数据；老消息返回空数组；嵌入式响应同样携带。
- 前端：上传状态 chips 渲染（`pending` 转圈 / `ready` / `failed`）；`pending` 时发送禁用；历史界面图片缩略图与文件卡片渲染；嵌入式 fetch+blob 缩略图。
- 既有测试调整：`test_chat_service_context_budget.py`（新增文件注入预算断言）、`history_service` 的图片处理单测（`test_current_turn_images_go_to_blank_history` 契约随图片迁移附件链路调整）、嵌入式 `imageBudget` 相关测试。
- 日志：按 `backend-engineering.md` §8，上传/解析/清理记生命周期与终态 INFO（附件 ID、`failed_stage`、`error_type`），不记文件内容与解析文本。

## Out of Scope

- Studio Chatflow（`execute_chat_flow` / Bot 会话体系）与 IM 渠道（企微/钉钉/飞书文件消息）的文件上传。
- 临时 RAG（文件切片 + 向量检索）；大文件超预算时只做截断。
- 附件保留期 TTL 与「已过期」UI 态（将来存储有压力时作为纯增量添加）。
- zip 等压缩包的解包解析。
- 图片内容随历史回放给模型（历史图片仅展示/下载）。
- 技能级「允许文件上传」开关。
- 旧会话历史数据迁移（老消息无附件记录，显示为空即可）。

## Further Notes

- Grill 共识记录（2026-10-12）：
  - 范围 = 技能调试聊天 + Skill Web Chat + 平台助手 + 嵌入式 webchat（B + 嵌入式）；Studio 与 IM 渠道不做。
  - 文件→模型取 MarkItDown 文本注入（A），否决临时 RAG（B）。
  - 链路取上传先行（A），否决 base64 内联后端落盘（B）。
  - 下载取权限校验端点 + 双鉴权（B），否决时效签名 URL（A）与 MinIO 直连（C）；用户确认 `Api-Authorization` 可解析出用户与组。
  - 生命周期取随会话 + 孤儿清理（A），不设 TTL。
  - 限额：文档 20MB / 图片 5MB / 单消息 5 附件 / 两级注入预算，用户确认。
  - 解析取异步状态机（A）+ 四条约束：独立队列、硬超时、pending 兜底收敛、轻格式快路径；失败语义 fail-closed（拒发而非跳过/等待）。
  - 关联取附件表持可空 message 外键（A）；技能调试聊天不做历史回显。
  - 多轮留存取「文档持续注入、图片仅当轮」（C）。
  - 开关取默认全量开启（A）。
- 关键事实依据：现状图片 base64 内联不落库（`history_service.py::process_user_message_and_images` → `extra_config.current_image_data`）；历史表仅纯文本（`persistable_user_message_text` 注释明示）；Skill Web Chat / Studio Chat 上传按钮不发图；嵌入式与平台 Skill 对话共用 `stream_skill_channel_chat` 与 `SkillConversation` 表，嵌入式鉴权为 `Api-Authorization`（`authenticate_embedded`）；仓库已有 MinIO 附件基建（`WorkflowAttachmentAsset`）与 MarkItDown 解析（`markitdown_parser.py`）；ChatGPT Library / Claude 均支持历史文件下载（含保留策略），故历史下载在范围内。
- 验收标准：四个入口可上传白名单文件并在解析就绪后发送；模型能回答文档内容且多轮可追问；刷新后历史界面可见当初上传的图片与文件并可下载（含嵌入式经鉴权头下载）；解析中/失败时发送被前端禁用且服务端兜底拒绝；删除会话后 MinIO 对象与附件记录不残留；孤儿附件 24h 后被清理。
