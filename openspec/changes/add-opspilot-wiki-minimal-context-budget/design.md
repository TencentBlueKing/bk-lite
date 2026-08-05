## Context

复杂 Profile、审批和多级配额不符合当前产品形态：知识库与 Bot 由管理员配置，终端用户只通过 Web Bot 提问。问答需要系统级硬限制；管理员确认上传的资料则应尽量完整构建，累计 token 仅作为审计软阈值，不能把正常长文件误判为失败。

## Goals / Non-Goals

**Goals:**

- 用 5 个环境变量约束问答和单文件构建。
- 让简单问答通常只调用一次模型。
- 让每个文件独立处理，旧知识规模不导致冲突比较调用线性增长。
- 让普通文件单次生成，长文件按单次安全上下文自适应 Map 并分层 Reduce。
- 在调用后优先使用 provider usage 校正并记录软阈值。
- 只有系统安全保护触发时才阻止不完整 Generation 激活。
- 上传大文件和新增 URL 时提前告知潜在耗时与模型用量。

**Non-Goals:**

- 不建设 Budget Profile、预算审批或 BudgetGrant。
- 不允许 Web 用户、知识库管理员或 Bot 配置任意 token 数。
- 不为每个目录、页面或阶段增加环境变量。
- 不接管 Bot/ChatFlow 的对话历史管理。
- 不修改模型能力配置和向量能力。
- 不承诺任意大小文件一定在单个任务内完成；异常调用循环和模型上下文仍需熔断。

## Decisions

### 1. 仅保留五个系统环境变量

默认值：

```env
WIKI_QA_MAX_LLM_CALLS=2
WIKI_QA_MAX_KNOWLEDGE_TOKENS=8000
WIKI_QA_MAX_OUTPUT_TOKENS=1500
WIKI_BUILD_MAX_LLM_CALLS_PER_MATERIAL=64
WIKI_BUILD_MAX_TOTAL_TOKENS_PER_MATERIAL=60000
```

环境变量缺失使用默认值；存在但不是正整数时启动失败。读取集中在单一配置模块，业务代码不得散落 `os.getenv`。构建调用次数是硬熔断；构建累计 token 是软审计阈值。

### 2. Wiki 问答只预算知识内容

8,000 token 包含 Index、Overview、页面证据、图谱证据和引用来源摘要，不包含系统提示、当前问题和历史。Bot/ChatFlow 负责历史裁剪和最终模型窗口；Wiki 仍返回 token trace 供最终装配检查。

### 3. 两次问答调用有固定用途

Generation Navigation 负责判断高置信度、低置信度和跨目录路由。高置信度查询只调用一次回答模型；低置信度或跨目录问题可以先调用一次 Overview 路由，再调用一次回答模型。调用计数由同一用户问题共享，不能由多个知识库、Agent 循环或自动重答绕过。SSE 与非流式响应都必须暴露稳定预算错误码；模型因输出上限截断时必须显示不完整提示。

### 4. 每个文件独立计数

批量上传拆成独立文件任务，每个文件拥有自己的 BuildRecord、调用计数、token 累计和 checkpoint。一个文件触发安全熔断不影响其他文件。

### 5. 构建使用自适应 Map 与分层 Reduce

1. 资料解析与 ingest 摘要确定性执行，不因 LLM token 软阈值失败。
2. 解析文本能放入单次安全输入窗口时，直接生成最终页面候选、summary、keywords 和 entities。
3. 超出单次窗口时，按安全输入大小生成完整、连续的 Map 分块，不以固定 4 块为上限。
4. Map 输出不能一次放入最终生成请求时，按组执行分层 Reduce；每轮必须缩小条目数或 token，否则触发无进展安全熔断。
5. 疑似冲突最多执行一次批量证据比较；语义 Overview 只在软阈值尚有余额时执行，否则使用确定性 Overview。

普通文件仍通常使用 1～3 次调用。64 次默认值只作为异常和超大任务的系统熔断，不是目标调用量。

### 6. 累计 token 是软阈值

每次调用记录输入估算、输出预留和 provider 实际 usage。超过 60,000 token 后继续必要的 Map、Reduce、冲突比较和最终生成，并在 trace 中标记 `soft_budget_exceeded=true`。可选语义 Overview 可以在软阈值耗尽后跳过。

单次调用仍必须符合系统保守上下文上限；调用总数、上下文和异常归并保护属于硬限制。

### 7. 硬安全失败使用结构化状态

问答无法在知识/调用/输出预算内形成证据时返回 `wiki_query_token_budget_exceeded`。构建只有在调用次数、单次上下文或异常归并保护触发时保存 checkpoint、标记 `budget_exhausted` 并拒绝激活不完整 Generation。普通累计 token 超过软阈值不得产生该失败状态。

### 8. 上传提醒不是拒绝策略

单个文件严格大于 500 MiB 时，Web 在上传前展示文件名、大小和模型用量风险，管理员确认后继续上传。URL 新增页提示系统只解析当前 URL，正文或图片较多时可能增加耗时与模型用量。两类提醒都不改变后端解析和构建资格。

## Risks / Trade-offs

- [固定保守上下文不能精确适配所有模型] → 每次调用仍由模型能力层最终校验，后续可在模型元数据中增加窗口能力。
- [管理员确认的超大文件仍可能触发 64 次硬熔断] → 保留 checkpoint 和明确安全错误；该上限防止异常循环，不按上传字节直接拒绝。
- [估算与实际 usage 有偏差] → 调用后优先使用 provider usage，并在 trace 记录计量来源。
- [分层 Reduce 丢失细节] → Map 明确保留实体、限定条件、时间、数值、步骤和来源，最终页面仍需来源证据。
- [语义 Overview 因软阈值跳过] → 确定性 Overview 始终可用。

## Migration Plan

预算和提醒不需要数据迁移。

## Open Questions

无。