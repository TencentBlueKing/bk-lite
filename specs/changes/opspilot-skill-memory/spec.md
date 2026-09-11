# OpsPilot 智能体渠道对话记忆

Status: in-progress

## Completion Evidence

- 模型与 migration：`LLMSkill.memory_space` / `memory_write_rounds`（默认 10，1–50），`SkillConversation.memory_written_message_id`；`MemorySpace.is_builtin` 字段保留但不参与查询筛选；`Memory.owner_user_id`；与 `force_wiki_grounded` 一并落在 `0078_force_wiki_and_skill_memory`（替换已下线的 `0078_llmskill_force_wiki_grounded`，只加字段，不创建/挂接内置记忆体）
- 不再创建或自动挂接内置记忆体：新建/默认智能体 `memory_space` 为空；查询与 ChatFlow 读写不再按 `is_builtin` 过滤
- 配置：管理员在记忆管理页自建个人记忆体，在智能体「能力拓展」中自选记忆体与写入轮次；空 = 不启用
- 读取注入：仅 `stream_skill_channel_chat` / `execute_skill_channel_im_sync`；未配置则不读不写；记忆块放到 Wiki 之后
- 写入：满 `memory_write_rounds` 轮投递；摘要抽 AG-UI 可见正文；归并走空间 `write_rule`；0 点 idle 只扫已挂接个人记忆体的会话
- 删除：`keep_memory` + `pending_memory_rounds`（未配置时为 0，不出现保留选项）
- 测试：`test_skill_channel_memory.py`、`test_llm_viewset_views.py` 记忆字段可写；前端 `skillMemorySettingsFields.test.tsx`

## Remaining

- 无

## Problem Statement

智能体（LLMSkill）已支持多渠道发布（见 `opspilot-skill-channel-publish`），但记忆能力目前只以 ChatFlow 的 `memory_read` / `memory_write` 节点形式存在。独立发布的智能体没有工作流，无法使用记忆。配置形态应与旧版一致：管理员自建记忆体、在智能体上自选、自选写入轮次，未选则整条链路不启用。

## Solution

在 LLMSkill 上提供可选的「记忆体」与「写入轮次」。管理员在记忆管理页创建个人记忆体，再在智能体设置「能力拓展」中选用（放在聊天历史前）。选了才对已发布渠道对话读注入、按轮数异步写入；未选则不读、不写、删除会话不出现「保留到记忆」。不创建内置记忆体，也不给默认智能体自动挂接。

## User Stories

1. As a 智能体管理员, I want 在能力拓展里自选记忆体和写入轮次, so that 只有需要长期记忆的智能体才会启用，且沉淀节奏可配。
2. As a 智能体管理员, I want 在记忆管理页自建个人记忆体再挂到智能体, so that 写入规则、默认模型由我维护，而不是系统暗挂一份看不见的空间。
3. As a 渠道对话用户, I want 智能体在每轮回复时参考我在该记忆体里的个人记忆, so that 跨会话的偏好、事实与结论不必重复说明。
4. As a 渠道对话用户, I want 删除会话时可以选择是否把尚未沉淀的内容保留到记忆, so that 「不想留痕」与「别丢了」两种意图都能表达。

## Implementation Decisions

### 生效范围

- 仅渠道对话链路生效：`stream_skill_channel_chat` 与 `execute_skill_channel_im_sync`。
- 未配置 `memory_space` 视为关闭：不读、不注入、不调度写入、idle 扫描跳过、`pending_memory_rounds=0`。
- 不生效：智能体配置页测试对话；Bot 工作流 agent 节点。

### 配置

- `LLMSkill.memory_space` 可空；只能挂 `scope=personal`、调用者有组织权限的空间。
- `memory_write_rounds` 默认 10，范围 1–50；更新接口接受客户端传入的记忆体与轮次。
- 新建/默认智能体不自动挂接。`is_builtin` 字段保留，查询暂不按该字段筛选。
- 摘要 / 归并模型：空间 `default_model` 为空时回退 `skill.llm_model`；写入走空间 `write_rule`。

### 记忆归属

- personal scope；平台用户 `owner = 系统管理 User.user_id`（UUID），`SkillConversation.external_user_id` 同步用 UUID；`owner_username` 仅展示。企微等外部渠道仍用 `sender_id`。不加渠道前缀。同一平台用户跨智能体渠道共用一条个人记忆，改 username 不丢。

### 读取与注入

- 配置了可用个人记忆体时每轮读取该空间；`engine.read(..., top_k=5)`；空记忆不注入。同一系统用户在平台 / Web / 嵌入式 / IM 渠道共用这一份个人记忆。
- 注入 `system_message_prompt`，顺序 `skill_prompt → Wiki → 用户记忆块`（记忆放最后，避免技能包、Wiki 或「直接简洁回答」把个人约定挤到中间被忽略）。
- 注入引导要求优先复用记忆中的环境、结论与检查约定：只取与本轮相关的条目，禁止另起通用清单、编造记忆里没有的整段 SQL，也禁止把其它技术栈的检查项混进来。
- 无工具空计划直答时，短指令在前、含记忆的 `user_system_message` 在后。
- 运行时拼接，不写入会话消息，不进 `chat_history`。

### 写入：水位线 + 可配轮次

- 调度使用 `LLMSkill.memory_write_rounds`（默认 10，范围 1–50）。
- assistant 落库后，水位线之后 assistant 数 ≥ N 则投递写入任务。
- 摘要使用内置 prompt：保留身份、环境与资产、已确认结论/指标、检查约定与阈值、未决问题与偏好；寒暄、工具过程和大段 SQL/报表原文不保留。助手落库若为 AG-UI 事件数组，摘要前先抽可见正文，超长按近轮优先截断。无有价值内容时模型输出 `EMPTY`，任务推进水位线但不落库。
- 归并使用记忆空间 `write_rule`。
- 失败语义不变：`MemoryWriteLlmUnavailable` 不推进水位线，WARNING 一条。

### 每日兜底 / 并发 / 删除

- 0 点扫空闲（最后消息 ≥ 30 分钟）且已挂接可用记忆体、有未写 assistant 的会话，`force` 写入。
- 冲突重归并最多 2 次后追加。
- 删除会话 `keep_memory` 与 `pending_memory_rounds` 保留；未配置记忆体时不写。

### 前端

- 设置页「能力拓展」中，Wiki 知识库之后、聊天历史之前：记忆体下拉（可清空=不启用，仅个人空间）+ 选中后显示写入轮次；链到记忆管理页新建。
- 删除确认在 `pending_memory_rounds > 0` 时仍可选择「同时保留到记忆」。

## Testing Decisions

- 新建技能不自动挂记忆体；update 可改挂个人空间或清空；拒绝团队空间。
- 未配置则 system prompt 无记忆块、不调度写入、idle 不扫、pending 为 0。
- 渠道对话 system prompt 含记忆且在 Wiki 之后；历史与落库无记忆块；注入引导含跨渠道优先复用、禁止另起通用清单。
- 无工具空计划直答保留完整 `user_system_message`，记忆块位于短指令之后。
- 第 N 轮才 delay；成功推进水位线；EMPTY 摘要推进水位线且不 commit；LLM 失败水位线不动且一条 WARNING。
- 摘要 prompt 含寒暄丢弃规则、环境/结论/阈值保留规则，且不拼接空间 write_rule；AG-UI 落库正文抽可见文本后再摘要。
- 0 点 idle 只扫已挂接可用个人记忆体的空闲会话。
- `keep_memory` 快照写入走所选用户空间 id。
- 平台用户记忆/会话归属用系统用户 UUID；改 username 后仍能读到；企微 sender_id 不改。

## Out of Scope

- 智能体测试对话与 Bot 工作流 agent 节点的记忆读写。
- 自动挂接记忆体、创建系统内置记忆体。
- 用 `is_builtin` 筛选记忆空间/记忆列表（字段保留，查询暂不筛）。
- IM 渠道的删会话能力。
- 非 `local` 记忆引擎。
