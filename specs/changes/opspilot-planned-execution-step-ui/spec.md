# OpsPilot 对话 planned_execution_step 分组展示

Status: implemented

## Problem Statement

DeepAgent 已通过 AG-UI 发出 `planned_execution_step` 步骤边界事件，但主对话 UI 未消费，用户只能看到扁平「已调用 N 个工具」，无法对应「第几步 / 步骤目标」。

## Solution

消费 `planned_execution_step`，按方案 A 将工具调用嵌套进步骤组：标题为「步骤 i/n · 目标文案」；流式仅展开当前 running 步；结束后默认全部收起。

## User Stories

1. As a 运维人员, I want 对话中看到计划步骤边界与目标, so that 我知道当前执行到哪一步。
2. As a 运维人员, I want 结束后步骤默认收起, so that 最终回答不被过程噪声淹没。
3. As a 运维人员, I want 打开历史会话仍能看到步骤分组, so that 复盘时过程可还原。

## Implementation Decisions

- 前端纯状态机 `plannedExecutionState.ts` 负责 start/end 与工具挂组；`AGUIMessageHandler` 与 `historyMessageProcessor` 共用。
- UI 组件 `PlannedExecutionSteps`（方案 A 嵌套）；步骤标题只展示目标文案，不展示计划工具名列表。
- 已挂到步骤的工具不再写入扁平 `tool-call-group` HTML，避免重复。
- 无 `planned_execution_step` 的对话保持原扁平工具组行为。

## Testing Decisions

- 状态机与历史回放接缝：`web/scripts/opspilot-planned-execution-step-test.ts`

## Out of Scope

- AgentStepProgress 折叠改造
- 长 markdown「显示更多」
- Wiki QA 轻量对话补齐思考/工具面板

## Further Notes

- 产品确认：结束后默认收起；标题目标文案；方案 A。
- 完成证据：状态机 + 历史回放脚本通过；主路径接线 `CustomChatSSE` / studio chat / logUtils。
