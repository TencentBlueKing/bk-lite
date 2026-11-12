# ITSM 工单

Status: ready

## Problem Statement

工单创建之后，处理人需要能认领、退回、转单、挂起、终止、关闭和重开。这些动作如果只改本地记录，流程实例会停在原处，认领后的待办还会从列表里消失。

## Solution

工单动作都作用到同一条 Flowable 流程实例。认领保留待办并改写引擎处理人。退回、转单、挂起和终态动作改变待办或状态。重新打开会按已发布流程从提单再启动。

## User Stories

1. As a 处理人, I want a later node to submit only the fields I changed without clearing fields already saved, so that a partial update does not fail required checks.
2. As a 处理人, I want 认领 to keep the task on the ticket and update the engine assignee, so that the task does not disappear from the list.
3. As a 处理人, I want 退回提单 and 退回上一节点, 转单, 挂起 and 恢复, 驳回, 终止, 关闭 and 撤回 to move the same ticket, so that I do not leave a stuck task.
4. As a 处理人, I want 重新打开 on a finished, cancelled, or terminated ticket to start the published process again at 提单, so that I can continue instead of seeing a local placeholder task.
5. As a 处理人, I want 通知, 决策, 知识发布 and 自动派单 to complete through the external job, and a 子流程 to wait for the child user task, so that those nodes are not dead ends.
6. As a 处理人, I want a 认领 button on a pending task in the ticket detail, so that I can take the task from the page.

## Implementation Decisions

- 节点提交先合并已保存的表单值，再按表单规格校验。
- 用户任务的处理人变量覆盖审批、处理、手动节点和子流程处理。
- 认领把任务标为已认领，并改写引擎处理人。列表和详情仍展示已认领任务，催办包含认领人。
- 重新打开时，若原流程实例已结束或已删除，按已发布的流程定义重新启动，并把待办同步回提单节点。实例仍在运行时只恢复状态，不另起一条流程。
- 通知节点使用通知外部作业。决策、知识发布、自动派单使用自动外部作业。子流程是调用活动，待办来自子流程里的用户任务。
- 没有流程引擎时，重新打开才允许落一条本地待办。有引擎时不制造无法继续的本地节点。

## Testing Decisions

- 只看待办节点、处理人和工单状态。
- 最高缝是工单服务加上本机 Flowable。
- 一条十节点流程覆盖提单、审批、分支、并行、汇聚、通知和结束。
- 另一条覆盖认领、退回上一节点、催办、终止、重开后再次提交、关闭、自动作业链和子流程。

## Out of Scope

- 重开后从终止前的中间节点继续。
- 认领、转单、退回之外的新工单动作。
- 表单画布交互和资源列表。
- 把本规格标成 M1 或 M2 已验收。

## Further Notes

- 十节点验收和补测已经在本机 Flowable 上通过。
- Flowable REST 前缀是 `/flowable-rest/service`。外部作业的领取和完成不走 `/flowable-rest/service/external-worker`。
