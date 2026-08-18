# OpsPilot 智能体多渠道发布

Status: in-progress

## Completion Evidence

- Worktree: `.claude/worktrees/opspilot-skill-channel-publish`（分支 `feat/opspilot-skill-channel-publish`）
- 后端：LLMSkill.`usage_team`、SkillChannel/会话模型与 migration `0071_skill_usage_team_and_channels`、渠道 CRUD、平台/Web 列表、登录态/嵌入式 SSE、四类 IM 完整协议
- Worktree 已对齐 `origin/master`（`badd1b959`）后重新生成 migration
- 前端：智能体详情「渠道发布」页、Web 独立对话页 `/opspilot/skill/chat`（服务端历史 + 通道 Tag）、API 客户端
- 测试：`test_skill_channel_publish*.py`、`test_skill_channel_aibot.py`、`test_skill_channel_wechat*.py`、`test_skill_channel_dingtalk.py`

## Remaining

- 钉钉 Stream 常驻客户端（本变更仅 HTTP 回调）
- 平台悬浮壳 UI（他方交付）

## Problem Statement

智能体（LLMSkill）配置完成后，只能作为工作台 Bot / ChatFlow 的能力单元使用，无法独立发布到运维平台、企微、钉钉、公众号、Web 对话与嵌入式对话等入口。使用者希望把「配好的智能体」直接按渠道开通，并指定哪些组织可以使用；同时企微 / 钉钉 / 公众号侧尚未做用户与组织同步，这些入口暂时不能按组织拦截。

## Solution

为智能体增加与 Bot 对齐的使用组织，并提供按渠道独立启停的发布绑定。发布后：平台与 Web 在 SaaS 登录态下对话（弹窗 vs 独立页），嵌入式用系统管理已有的用户 API Secret 鉴权并固定打到某个智能体渠道，企微应用 / 企微机器人 / 钉钉 / 公众号复用现有 Bot 渠道配置协议，回调落到带渠道绑定 ID 的入口。对内一律走与「单 Agent 节点」相同的对话执行；配置活引用；会话与消息落在智能体独立历史中。平台悬浮机器人壳由其他交付承接，本变更提供有权限渠道列表与对话请求接口。

## User Stories

1. As a 智能体管理员, I want 为智能体配置使用组织（默认包含管理组织，并可额外授权）, so that 平台 / Web / 嵌入式只对授权组织开放对话。
2. As a 智能体管理员, I want 按渠道独立创建、启停、填写凭证并看到带渠道绑定 ID 的回调地址, so that 同一智能体可发布到多个入口且同类型可挂多套配置。
3. As a 智能体管理员, I want 修改智能体使用组织后已发布渠道上的组自动同步, so that 第一版不必逐渠道改组，同时组仍落在各渠道上便于以后拆分。
4. As a SaaS 登录用户, I want 查询我有权限的平台渠道并发起 SSE 对话（弹窗由其他交付使用同一接口；Web 为独立路由页）, so that 在站内与已发布智能体多轮交谈。
5. As an 嵌入式 / 同域 App 调用方, I want 用 Api-Authorization（UserAPISecret）调用固定智能体与渠道绑定的对话接口, so that 第三方集成不必走 SaaS 页面登录。
6. As an 企微 / 钉钉 / 公众号用户, I want 在对应应用或机器人里与已启用渠道对话且不因 BK-Lite 组织校验被拒, so that 在尚未同步组织映射前仍能使用。
7. As a 智能体管理员, I want 下线某渠道后新请求被拒绝但历史仍可查、删除智能体时级联清除渠道绑定与会话, so that 生命周期清晰且不留孤儿入口。
8. As a 工作台配置者, I want 同一智能体既能被 Bot/ChatFlow 引用又能独立发布, so that 工作室流程与直连渠道发布互不排斥。

## Implementation Decisions

- 发布对象是智能体（LLMSkill），不是工作台 Bot。智能体无 ChatFlow；对外只提供对话入口，对内执行等价于单 Agent 节点，复用同一套 Agent 执行能力，仅包装渠道受理与回覆。
- 智能体增加 `usage_team`：创建/更新时强制 `team ⊆ usage_team`，管理组织不可从使用组织移除；允许额外授权非管理组织。行为与权限校验对齐现有 Bot 使用组织规则。有智能体管理组权限即可配置渠道发布，不另增渠道专用权限点。
- 新增智能体渠道绑定（概念名 SkillChannel）：归属某个智能体；字段至少包括渠道类型、启用态、渠道配置（凭证等）、可用组副本。同类型允许多条并行绑定。回调与对话 URL 必须包含稳定的渠道绑定 ID 以消歧。
- 渠道类型至少区分：`platform`（SaaS 弹窗）、`web_chat`（SaaS 独立路由页）、`embedded_chat`、`enterprise_wechat`（企微应用）、`enterprise_wechat_aibot`（企微机器人）、`dingtalk`、`wechat_official`。平台与 Web 后端鉴权与对话契约一致，仅产品承载与 `channel_type` 不同，须两个类型以便独立启停。
- 组策略：平台 / Web / 嵌入式用渠道上的组副本做准入（含 OpsPilotGuest 特例，对齐 Bot 对话）；企微应用 / 企微机器人 / 钉钉 / 公众号不校验 BK-Lite 组织，仅校验绑定存在、已启用与渠道协议自身校验。改智能体 `usage_team` 时自动覆盖同步到所有已发布（含已启用与仍存在的）渠道绑定上的组副本；第一版不提供「渠道组覆盖且不同步」。
- 配置活引用：渠道绑定不快照 prompt / 模型 / 工具；执行时读当前智能体配置。「发布」职责是开通或更新绑定、写入组副本、启停与对外入口，不是冻结版本。
- 企微 / 钉钉 / 公众号的配置字段与协议复用现有 Bot/ChatFlow 对应入口节点 schema；执行层复用或薄封装现有渠道 utils，对话内核改为智能体单 Agent，不假造 ChatFlow 节点。
- 嵌入式：请求携带固定智能体 ID 与渠道绑定 ID；用现有 `UserAPISecret`（`Api-Authorization`）解析调用方用户与绑定 team，再要求该 team 属于该渠道组副本。渠道绑定不保存、不关联具体 Secret 主键。第一版不做 Origin/域名白名单。
- 平台本侧交付：当前用户有权限的平台渠道列表接口 + SSE 对话请求接口。悬浮机器人 UI / 多智能体选择壳不在本变更实现，但必须能消费上述契约。Web 为 SaaS 登录下的独立对话路由页，复用同一套登录态对话能力。
- 平台 / Web / 嵌入式对话响应为 SSE 流式（风格对齐现有 Bot 对话执行）；IM 渠道为回调受理后异步生成再回覆，不在回调请求内同步阻塞长推理。
- 会话与消息使用独立于 Bot 的智能体会话模型，关联智能体与渠道绑定，并按外部用户标识或 SaaS 用户区分会话；支持多轮续聊与历史只读。下线渠道：拒绝该绑定上的新请求，保留历史。删除智能体：级联删除其渠道绑定与会话/消息。
- 与 Bot 并存：独立发布不改变 Bot 的 `online` 或流程引用；两边入口互不抢状态。删除或活引用变更对两边同时生效。
- 管理侧提供智能体详情内的渠道发布配置 UI：列表、创建/编辑凭证、展示回调 URL、启停、嵌入式调用说明；与后端 API 同交付。

## Testing Decisions

- 好测试只断言外部行为：组不变式与同步、启停后门禁、各入口鉴权通过/拒绝、回调按渠道绑定 ID 路由、会话持久化与级联删除、活引用下改智能体后对话用新配置；不绑定内部 helper 调用次数或私有函数结构。
- 优先接缝（由高到低）：智能体使用组织写入与 `team ⊆ usage_team`；渠道绑定 CRUD / 启停与组副本同步；平台有权限列表与登录态对话门禁（含 Guest）；嵌入式 `UserAPISecret` + 组校验；IM 回调 online/enabled 与「不校组织」；删智能体级联；SSE/异步回覆的受理契约（可用替身替换真实 LLM）。
- 既有先验：Bot 的 `usage_team` 创建更新与授权用例；ChatFlow / Bot 的企微钉钉公众号回调与 online 门禁用例；OpenAPI / `UserAPISecret` 鉴权用例；Bot 发布与对话执行测试风格。智能体发布测试应平行这些接缝，而不是先上浏览器 E2E。

## Out of Scope

- 平台悬浮机器人 UI、多智能体选择交互与默认智能体策略（由其他交付消费本变更 API）。
- 企微 / 钉钉 / 公众号的用户与组织同步，以及这些入口上的 BK-Lite 组织校验。
- 嵌入式域名 / Origin 白名单。
- 按渠道配置不同组且改 `usage_team` 时保留渠道覆盖的差异化策略（结构已预留组副本，行为第一版为全量同步）。
- 智能体发布版本快照、灰度与回滚。
- 将智能体发布与 Bot `online` / ChatFlow 入口发布合并为单一模型。
- 移动端应用目录或其它未列入的渠道类型（除非复用协议所必需的最小接线）。
- Playwright/Cypress 全链路浏览器 E2E（本仓当前无该门禁要求）。

## Further Notes

- 产品文案可称「智能体发布」；实现上发布单元是 LLMSkill + 渠道绑定，工作台 Bot 仍是流程型应用的发布单元，二者并存。
- 「企微应用」对齐 Bot 的企微应用/触发配置；「企微机器人」对齐企微智能机器人（aibot）配置，均以现网 Bot 节点为准。
- 对齐会话结论见 grill-me：Skill 独立发布、单 Agent 执行、SkillChannel、usage_team 与自动同步组副本、按渠道启停、平台列表+对话 API、Web 独立页、嵌入式 UserAPISecret、IM 不校组织、复用 Bot 渠道 schema、独立会话、级联删除、SSE + IM 异步、管理 UI 同交付。
