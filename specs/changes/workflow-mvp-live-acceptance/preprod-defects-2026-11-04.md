# 预发 L2 验收缺陷备忘（先记不改）

Date: 2026-11-04  
环境: `https://bklite.canway.net`  
流程: workflow `22`（`[验收] K8s双触发记忆闭环(绕过意图)`，已发布 v5，绕过意图分类）  
状态: **仅记录，本轮不改代码**

## D1. 通知正文引用被发布转义成字面量

- 现象: 邮件正文收到字面量 `${agent.output.message}`，不是智能体输出。
- 预期: 通知 `body`/`title` 支持 `${taskRef.output.field}` 在运行时解析。
- 证据: 智能体输出契约为 `message`（`bklite_agent/schemas/output.schema.json`）；通知 schema 中 `body`/`title` **没有** `x-binding: literal-only`。发布路径 `prepare_definition_for_publish` → `_escape_literal_conductor_expressions` 按字段名全局转义 `_LITERAL_INPUT_KEYS`（含 `body`、`title`），把 `${...}` 写成 `$${...}`，Conductor 当作字面量。
- 碰撞: 同名字段 `body` 对 HTTP 请求需要逃逸，对通知需要解析；按 key 全局逃逸过宽。
- 判定: **产品/实现缺陷**（配置写法正确）。
- 状态: **已修（本地）** — 从 `_LITERAL_INPUT_KEYS` 移除 `body`/`title`；回归见 `test_prepare_definition_keeps_notification_body_and_title_workflow_references`。预发需重新发布流程后验证邮件正文。

## D2. 意图分类依赖的 LLM 在预发不可用/不稳定

- 现象: 意图分类节点执行失败；曾见 `IntentNotFoundError`，换模型后出现 `RuntimeError`；页面错误被截断，难定位。
- 背景: OpsPilot 工作台可用模型枚举 ≠ 编排意图节点可选/可用集合；`model_id` 非法或不在枚举时直接失败。
- 影响: 挡住含意图节点的 L2 全图；当前用「绕过意图」拓扑继续验记忆/通知。
- 判定: **环境/配置问题为主**，需补：可用模型清单、服务端完整错误、意图节点与工作室模型对齐。是否另有代码缺陷待有日志后再判。
- 修复方向（未做）: 对齐模型源；页面展示完整 `error_type`/关联 ID；有日志后再查 IntentNotFound 根因。

## D3. 多触发器公共输入 schema 取交集，易踩空

- 现象: 发布校验报 `workflow.input.message` 不存在；NATS 有 `message`，SCHEDULE 默认输出 schema 无同名字段时，公共 `workflow.input` 取交集后丢失 `message`。
- 背景: `commonTriggerInputSchema` / 数据契约按多触发字段交集暴露 `workflow.input.*`；告警信封字段（`message`/`team`/`user_ids`/`object_id`/`scene`）与定时内建字段不一致。
- 加重因素（2026-11-04 复现）: 编辑定时配置时 `ScheduleTriggerEditor.onChange` 会执行 `changeTrigger({ config, input_schema: scheduleOutputSchema })`，**整表覆盖** SCHEDULE 的 `input_schema`，把手工补的 `message` 冲掉，随后再发布必现 D3。
- 当前绕过: 两边触发 schema 都显式补齐所需公共字段（至少 `message`）；NATS 侧保留告警字段；改 cron 后必须再把 `message` 补回 SCHEDULE 再发布。
- 判定: **产品契约易踩坑** + **编辑器实现缺陷**（改 cron 不应抹掉已扩展字段）。
- 修复方向（未做）: 设计侧明确多触发公共参数声明；编辑器提示「仅交集可引用」；校验文案指向缺字段的触发器；`onChange` 合并而非覆盖 `input_schema`。
- 局部进展（2026-11-05）: **新建 NATS** 默认写入告警信封 schema（`buildNatsAlertEnvelopeSchema`），单 NATS 流程可直接引用 `workflow.input.message`；**不**解决 SCHEDULE 覆盖 / 多触发交集本身。

## D5. 记忆上下文上限大于智能体 message 上限，月报支路易超限

- 现象: SCHEDULE 支路跑到 `agent_3` 失败：`message超出限额`（v6，2026-11-04 16:08）。
- 证据: `memory_read` 可输出 `memory_context` 最长 100_000；`execute_agent` 对 `message` 限额 50_000、`prompt` 限额 10_000。验收配置把同一份 `memory_context` 同时塞进 `message` 与 `prompt`，放大超限概率。
- 判定: **限额不一致 / 易踩坑**（验收配置不当为主；产品上记忆→智能体无自动截断）。
- 临时绕过: `top_k=1`；记忆只放 `message`；`prompt` 仅短指令。
- 修复方向（未做）: 对齐限额或在引用侧自动截断；编辑器提示双字段重复引用风险。

## D4. 定时触发「调试流程」表单无法填写数组字段 `schedule`

- 现象: 调试入口选 SCHEDULE 时，填 `调度规则=0 9 1 * *` 报「流程输入「schedule」不符合要求」。
- 原因: 触发 schema 里 `schedule` 类型是 `array`（真实 cron 事件为 `["0 9 1 * *"]`），但 `WorkflowSchemaForm` 对无 enum 的 array 退化成普通文本框，提交的是字符串。
- 判定: **前端缺陷**（调试表单与 SCHEDULE 输出契约不匹配）。
- 临时绕过: 不用调试弹窗；改 cron 后发布，等调度器真实触发；或等表单支持数组/ tags 后再用调试。
- 状态: **已修（本地）** — SCHEDULE 调试不再渲染事件 schema 表单；用节点 `config` 调 `schedule-preview` 取 `test_output` 后直接 `/debug/`。单一定时入口跳过弹窗；多触发仅保留入口选择。FORM/WEBHOOK/NATS 调试未改。

## 相关验收进度（旁注）

- NATS 告警支路（绕过意图）已跑通到邮件；邮件内容受 D1 影响。
- 意图分类暂搁置（D2）。
- 定时月报支路受 D4 影响，调试弹窗暂不可用；改走真实 cron。
