## ADDED Requirements

### Requirement: 系统必须提供三个问答预算环境变量

系统 MUST 集中读取 `WIKI_QA_MAX_LLM_CALLS`、`WIKI_QA_MAX_KNOWLEDGE_TOKENS` 和 `WIKI_QA_MAX_OUTPUT_TOKENS`，默认值分别为 2、8,000 和 1,500。变量缺失时 MUST 使用默认值；变量存在但不是正整数时 MUST 阻止服务启动并明确指出变量名。

#### Scenario: 环境变量均未配置
- **WHEN** 服务启动且三个问答变量均缺失
- **THEN** 系统 MUST 使用 2、8,000 和 1,500 的默认值

#### Scenario: 配置非法值
- **WHEN** 任一变量配置为 0、负数或非整数
- **THEN** 服务启动 MUST 失败
- **AND** 系统 MUST NOT 静默使用默认值或关闭限制

### Requirement: 问答知识预算必须覆盖所有 Wiki 内容

8,000 token 硬上限 MUST 统一计算 Index、根/目录 Overview、页面证据、图谱证据和引用来源摘要。系统提示、当前用户问题和对话历史 MUST 不计入该 Wiki 知识额度。

#### Scenario: 多种知识来源共同装配
- **WHEN** 查询同时使用 Overview、页面和图谱证据
- **THEN** 三者与引用摘要的累计 token MUST 不超过配置上限
- **AND** 任一来源 MUST NOT 绕过统一计数

### Requirement: Wiki 与 Bot/ChatFlow 必须保持上下文职责边界

Wiki MUST 返回知识内容、实际/估算 token、截断原因和 Generation ID。Bot/ChatFlow MUST 继续管理系统提示、当前问题、历史和最终模型窗口；当前问题不得由 Wiki 截断。

#### Scenario: 对话历史已占满模型窗口
- **WHEN** Bot 在加入 Wiki 结果前发现剩余模型窗口不足
- **THEN** 系统 MUST 返回受控上下文超限错误
- **AND** MUST NOT 截断用户问题或无检查地塞入知识内容

### Requirement: 一次问答最多使用两次 LLM 调用

Generation Navigation MUST 负责高/低置信度判断、Overview 路由和候选选择；本 capability 只提供请求级调用计数与允许/拒绝门禁。高置信度检索 MUST 只允许一次回答模型。只有低置信度或跨目录问题 MAY 额外消费一次 Overview 路由额度；调用计数 MUST 在同一用户问题的 Wiki 问答链中共享，多个知识库不得分别获得完整额度。系统 MUST NOT 自动二次重答或超过配置次数。 最终回答 MUST 通过单次模型调用执行，Agent 循环、工具重规划和失败回退不得增加模型调用。

#### Scenario: 高置信度 Index 命中
- **WHEN** Index 返回足够证据
- **THEN** 整轮问答 MUST 只调用一次回答模型

#### Scenario: 一个问题查询多个知识库
- **WHEN** Bot 为同一用户问题检索多个知识库
- **THEN** 所有知识库路由与最终回答 MUST 共享两次 LLM 调用和一份 8,000 token 知识预算
- **AND** MUST NOT 按知识库重复分配额度

#### Scenario: Overview 路由失败
- **WHEN** 第一次路由调用失败
- **THEN** 系统 MUST 回退确定性 Index 并保留一次回答额度
- **AND** MUST NOT 发起第二次路由或第三次总调用

### Requirement: 回答输出必须具有硬上限

每次最终回答调用 MUST 显式设置不超过 `WIKI_QA_MAX_OUTPUT_TOKENS` 的输出上限。系统不得因知识预算有剩余而扩大回答额度。 非流式与 SSE 响应都 MUST 直接返回稳定预算错误码；达到 provider 输出上限时 MUST 显示回答可能不完整。

#### Scenario: 模型尝试生成长回答
- **WHEN** 输出达到配置上限
- **THEN** provider 请求 MUST 停止继续生成
- **AND** 响应 MUST 标明是否因输出上限而不完整

### Requirement: 问答超限必须返回结构化错误

当调用次数、知识 token 或最终模型窗口不足以形成受证据支持的回答时，系统 MUST 返回 `wiki_query_token_budget_exceeded` 或明确的上下文超限错误，不得生成无证据答案。

#### Scenario: 知识证据超过上限且无法安全裁剪
- **WHEN** 必需证据无法在知识预算内装配
- **THEN** 系统 MUST 返回结构化超限错误
- **AND** Web 用户 MUST NOT 获得提高额度的入口
