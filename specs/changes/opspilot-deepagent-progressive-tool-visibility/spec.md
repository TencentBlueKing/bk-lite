# OpsPilot DeepAgent 按步工具可见性与渐进披露

Status: implemented

## Problem Statement

OpsPilot 技能执行已引导模型做计划，但 DeepAgent 在首次及后续模型调用中仍把技能加载到的全量业务工具完整 Schema 一并绑定进请求。工具未调用也会产生输入 Token；在 Kubernetes 等大工具集场景下，约 60 个工具 Schema 每轮重复计费，真实根因分析曾出现约 20 万 Token 的不合理消耗。运维人员需要在保留规划与分步执行能力的同时，显著降低工具 Schema 相关 Token，并在执行过程中流式看到各步工具结果。

## Solution

将「工具注册」与「模型可见工具 Schema」分离。首轮仅向规划模型提供紧凑工具目录（工具名与截断后的短描述，不含参数 JSON Schema），产出结构化步骤计划（每步精确工具名）。执行阶段仍可注册全量工具供运行时调用，但每一轮模型请求只暴露当前步骤允许的工具子集；步骤切换时移除上一步工具；最终总结轮可见工具为空。执行过程中通过既有 AG-UI/SSE 通道边执行边推送工具调用与结果。默认启用该行为，并提供环境变量紧急回退到「全量 Schema」旧行为。

## User Stories

1. As a 使用大工具集 Skill 的运维人员, I want 首轮规划不再携带全量工具完整 Schema, so that 单次任务不会因工具目录重复计费而消耗数十万 Token。
2. As a 运维人员, I want 执行时每一步只让模型看到该步需要的少量工具, so that 后续轮次也不会反复支付全量 Schema 成本。
3. As a 运维人员, I want 任务最后总结阶段模型不再携带任何业务工具 Schema, so that 总结轮只产出回答而不再浪费工具 Token。
4. As a 运维人员, I want 每个步骤的工具调用与执行结果在对话中流式出现, so that 我能边看过程边等待，而不必等整任务结束。
5. As a 平台运维/发布人员, I want 出现异常时能用环境变量紧急关闭按步可见性并回退全量 Schema, so that 可以快速止血而不必立刻回滚整包。

## Implementation Decisions

- 主路径对齐 Token 对比文档中的「规划后按步骤筛选」模型，而不是「按类别 activate_tools 整类灌入 Schema」或「子集选出后整轮只增不减」。
- 架构为：独立结构化规划调用 + DeepAgent 分步执行 + 每轮工具可见性中间件。规划器输出目标、步骤目标与每步精确工具名列表；可见性中间件在每次模型调用前过滤本轮 `tools`，保证「注册了 N 个工具」不等于「模型收到 N 个 Schema」。
- 规划首轮输入仅为：用户问题、已完成步骤摘要（首次为空）、最近失败信息（首次为空）、紧凑工具目录。目录中每个工具描述最多 120 字符；不得包含参数 JSON Schema；工具描述视为不可信元数据，不得当作可执行指令。
- 硬上限原样采用对比文档：最多 4 个有效工具步骤；每个步骤最多 4 个工具；不存在、重复或超限的工具名在规划结果中删除；不需要工具的纯分析步骤不单独作为工具步骤，统一留到最终总结；每个工具步骤内 DeepAgent 模型调用上限与全流程模型调用上限、失败重规划次数（最多 2 次且只替换当前及后续步骤、已完成步骤不重跑）与文档一致。
- DeepAgent 内置 `write_todos` 不负责选择模型可见业务工具 Schema；规划职责在独立规划器。规划阶段不向模型暴露用于「挑选全量业务工具」的 DeepAgent 内置能力。
- 执行阶段允许文件系统类内置工具按需常驻，便于大结果落盘；禁止 `task` 子代理携带或绕过业务工具可见性限制。
- 交互类工具（如用户选择、配置对比/修复报告）与知识库检索：在执行步骤可作为小型常驻集合，避免计划漏写导致无法问用户或检索；最终总结轮必须强制清空可见工具（含卸掉上述常驻与 FS），总结轮 `visible_tool_count` 应为 0。
- 默认启用按步可见性（渐进披露）。保留环境变量紧急开关（建议名 `OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS`）：默认开启；显式关闭时回退为向模型绑定全量业务工具 Schema 的旧行为。小工具集是否额外用阈值短路全量绑定可作为实现细节，但不得削弱「大工具集必须按步可见」的约束。
- 流式体验：分步执行时，每步工具的 start/参数/结果须通过既有 AG-UI/SSE 事件边执行边推送；可增加步骤边界事件便于前端分组。工具自身若非流式生成，则在工具返回后立即推送结果事件，不得攒到整任务结束。流式只影响展示，不改变每轮模型请求的可见 Schema 集合。
- 可观测性：每轮记录 `call_index`、`visible_tool_count`、`visible_tools`、以及 prompt/completion/total tokens；任务结束记录 `llm_call_count` 与合计用量。排查 Token 异常时优先核对可见工具数是否超出规划、总结轮是否为 0、是否因超长工具返回而非 Schema 导致暴涨。
- 当前代码树中文档所述规划器与可见性中间件可能缺失或未接线；实现时应恢复或按上述语义重建，并确保 DeepAgent 包装路径真正按步换绑，而不是只写 prompt 却仍全量 `create_deep_agent(tools=all)`。
- 既有按类别的 `activate_tools` / 工具池阈值逻辑不作为本变更主路径；若保留，不得替代按步精确工具可见性，也不得在激活一类时把该类全部 Schema 一次性暴露给模型。

## Testing Decisions

- 好测试只断言外部行为：首轮规划请求不可见完整工具 Schema；执行各步模型可见工具集合等于（或为子集且不超过）该步计划工具且数量 ≤4；换步后上一步工具不再可见；总结轮可见工具为空；失败重规划不重跑已完成步骤；流式路径能发出工具 start/结果类事件；关闭紧急开关后可回退全量 Schema 行为。
- 优先接缝：规划器（紧凑目录、步骤/工具上限、非法工具名过滤）；可见性中间件（按步过滤、总结清空）；DeepAgent 分步编排与重规划；Token/可见工具日志字段；AG-UI/SSE 工具事件在分步场景下仍能发出。
- 先验：对比文档中的回归覆盖（规划约束、同 Agent 不同步骤替换可见工具、总结空工具、重规划、NATS/AGUI Token 与可见工具日志）应作为本变更测试清单的基线；若对应测试文件曾随实现缺失，需按行为重新补齐，而不是只测 prompt 文案。
- 不要求首期 Playwright 全链路 E2E；以服务端单测与现有 AGUI/NATS 用量日志断言为主。

## Out of Scope

- 以「按类别 activate_tools 整类激活且只增不减」作为降低 Token 的主方案。
- 修改各业务工具内部返回体积的压缩策略（日志/YAML 截断等可另案），本变更只约束模型可见工具 Schema。
- 为所有工具实现真正的逐 token 流式返回（仅要求工具结果事件及时推送）。
- 改变 Skill 配置 UI 的工具勾选产品形态（除非为实现可见性所必需的最小说明）。
- 非 DeepAgent 执行引擎的全面重写；本变更在 DeepAgent 分步执行之上加规划与可见性控制。

## Further Notes

- Token 问题根因与量级对照见 `server/docs/opspilot-deepagent-tool-token-comparison.md`（原始全量 Schema 每轮重复计费 vs 规划后按步筛选）。
- Grill 共识要点：对齐文档的按步精确工具与硬上限；独立规划 + DeepAgent 分步；FS 可常驻、禁子代理绕过；HITL/KB 执行步小常驻、总结轮清空；过程流式推工具结果；默认开启并保留紧急关闭开关。
- 成功标准（验收）：大工具集场景下，首轮不得接近全量工具 Schema Token；典型多步任务的工具 Schema 相关输入应从「全量×轮次」降为「当前步工具数×该步轮次」；总结轮 `visible_tool_count=0`；用户侧能看到分步工具执行流。
- 完成证据（2026-08-03）：在既有 `ToolExecutionPlanner` / `ToolVisibilityMiddleware` / 分步 DeepAgent 路径上补齐共识缺口——`OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS` 默认开启、关闭回退全量 Schema；执行步 FS + HITL/KB 常驻、总结轮清空；隐藏 `write_todos`/`task`/`execute`；步骤边界自定义事件。聚焦测试：`test_deepagent_runtime_policy.py`、`test_deepagent_engine_service.py`（排除既有 SkillBackend 基线失败）通过。
