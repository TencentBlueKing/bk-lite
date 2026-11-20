# CMDB 负责人交接

Status: implemented

## Problem Statement

人员离职或调岗后，CMDB 里大量资产仍挂在原负责人名下。现在只能逐条改实例，或靠导入导出绕行，交接成本高，也容易漏。

## Solution

在「管理 / 负责人交接」中先单选一个用户字段，再选定原负责人、新负责人和带该字段的模型，先预览将改动的实例数量、模型分布和样例，确认后再批量替换。只改这个字段里仍包含原负责人的值，同一字段里的其他共有人保留。已成功的实例不回滚；失败实例进入失败清单。每条成功写入现有变更记录，场景为「负责人交接」，可在操作日志中筛选。

## User Stories

1. As a CMDB 管理员, I want to preview every asset still owned by a departing person, so that I can see the count and model mix before anything changes.
2. As a CMDB 管理员, I want one confirmation to hand those assets to a new person, so that I do not edit instances one by one.
3. As a CMDB 管理员, I want co-owners on the same field to stay, so that handing over 张三 does not remove 王五.
4. As a CMDB 管理员, I want a failure list when some instances cannot be updated, so that the ones already handed over stay with the new owner.
5. As a CMDB 管理员, I want the operation log to filter by the handover action, so that I can see who moved which instance from whom to whom.
6. As a CMDB 管理员, I want assets outside my current organization scope to be counted as excluded, so that I do not silently change instances I cannot operate.

## Implementation Decisions

- 入口在管理菜单，页签与「系统设置」共用 `model_management`，这样现有模型管理权限就能看到。接口同时接受 `owner_handover` 的查看/执行，以及模型管理的查看和「编辑模型」。预览、提交、取消要求执行或编辑模型。
- 一次交接只选择一个 `attr_type=user` 字段，按属性 ID 和属性名同时匹配。下拉列出全部用户字段，模型范围只显示含该字段的模型。不新增字段，也不按属性名白名单裁剪。字符串类型的「负责人」视为不适用。
- 字段值是用户 ID 列表。替换只把原负责人 ID 换成新负责人 ID，并去掉重复。整型单值先按单元素列表处理，写回时仍是列表。
- 原负责人可以是已禁用或已离职的目录用户。新负责人必须未禁用，且任职状态不是离职；未设置任职状态可以接收。双方必须属于执行人的同一 domain，且不能是同一个人。
- 预览签发 30 分钟签名令牌，绑定执行人、组织范围、双方用户、所选字段和当时解析出的模型列表。执行以令牌为准重新查询，不信任客户端传来的实例清单。
- 预览分页上限 50。无权限实例只计入排除数量，不返回名称。预览行带转移状态，执行前是 `pending`（未转移）。任务结束后按实例结果更新：成功 `succeeded`，失败 `failed`，未写出或跳过仍是 `pending`。
- 执行创建持久化交接任务。Celery 可用时异步执行；不可用时在请求提交后的同一进程执行。同一原负责人同时只有一个排队或执行中的任务。幂等键相同且内容相同返回原任务，内容不同返回冲突。
- 执行按批写图。同一批里每个实例只提交发生变化的用户字段，值可以不同。一次图查询同时写入该字段、展示值和人工维护标记。变更记录用批量创建，场景 `owner_handover`，概述动作为「负责人交接」，来源写「原展示名 → 新展示名」。不调度自动关联。一批写入失败时拆开重试，单条失败进入失败清单，已成功的不回滚。取消在两批之间生效。
- 组织、关系和其他属性不修改。超级管理员仍受当前团队范围限制；范围内实例允许交接。其他用户沿用创建者加组织，或实例操作权限。
- 任务状态为 queued、running、succeeded、partial_failed、failed、cancelled。取消在写出前直接取消；写出后只停止后续实例。已成功的不回滚。
- 每条实例结果按任务和实例 UUID 记一次。写入失败只保留失败阶段和错误类型；权限校验异常只打一条带 traceback 的错误日志。
- 不暴露 OpenAPI。
- 页面分成「用户转移」「转移历史」「清理历史」。历史列出当前团队的交接任务，可按原用户或新用户筛选，并可多选删除已结束的任务。排队或执行中的任务不删。清理历史的用户可多选。选中的人只清理各自早于所选天数的交接任务和交接变更记录；不选用户时清理当前团队这段时间的全部已结束任务，以及这段时间的全部交接变更记录。进行中的任务保留。当前团队以外的交接任务不删。

预览返回的核心形状：

```json
{
  "preview_token": "<signed>",
  "total": 3,
  "excluded_no_permission": 1,
  "by_model": [{"model_id": "host", "model_name": "主机", "count": 2}],
  "items": [{
    "model_id": "host",
    "inst_name": "web-prod-01",
    "organization": "运维一组",
    "transfer_status": "pending",
    "changes": [{"attr_id": "operator", "attr_name": "主要维护人", "before": "张三(zhangsan)", "after": "李四(lisi)"}]
  }]
}
```

## Testing Decisions

测试接缝是交接服务的公开预览和执行、目录用户筛选、图查询合并、实例写入参数，以及视图的权限拒绝。服务测试使用内存目录和内存实例，样例对齐原型：张三名下主机与应用、共有人王五、组织外实例、执行前负责人已变化、单条写入失败。断言来自这些已知样例，不从实现反推期望值。图库、权限 RPC 和 Celery 由替身代替。真实图库上的全量交接不在本接缝证明。

## Out of Scope

不禁用账号，不改告警分派和值班，不联动 ITSM 或 AD，不按负责人重算数据权限，不在预览里勾掉单条实例，不把字符串负责人猜测成用户。

## Further Notes

操作日志的查询口径是变更记录场景 `owner_handover`，不是平台操作日志镜像。列表和详情展示新负责人，是因为用户字段和 `_display` 已更新。

## Completion Evidence

2026-11-16，sqlite 内存库：

`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_owner_handover.py --no-cov`

19 passed。覆盖原型样例预览、共有人保留、部分失败不回滚、执行前负责人变化则跳过、幂等与忙碌锁、离职原负责人、目录筛选、取消、整型写回列表、权限异常只记一条错误且不列出组织外实例、写入参数和图查询。

2026-11-17，执行改为按批写图，变更记录改为批量创建。同一命令 26 passed，另有 Neo4j / FalkorDB 的批量属性写入测试 4 passed。

菜单注册：`cd web && pnpm exec vitest run src/app/cmdb/(pages)/assetManage/ownerHandover/menu.test.ts`，1 passed。

全量 Celery 静态清单测试被既有 `apps/job_mgmt/tasks.py` 的 `JOB_CELERY_QUEUE` 挡住，本次任务名已单独断言注册在 `background` 队列。
