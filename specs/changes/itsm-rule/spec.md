# ITSM 规则与时效

Status: ready

## Problem Statement

规则与时效里的决策表、触发器、定时任务还是同一层录入壳。页面只有标题和几个英文输入框，看不出已有规则，也不能当成列表来验收。

## Solution

决策表从流程管理移到本模块。决策表、触发器、定时任务用同一套现有表格展示已保存的行，并允许新建一行。服务日历、SLA 和状态沿用各自已经能操作的页面，不并进这张通用表。

## User Stories

1. As a 规则管理员, I want 决策表 under 规则与时效, so that it is not a tab on the flow designer.
2. As a 规则管理员, I want saved 决策表, 触发器 and 定时任务 to appear in a table, so that I can see the name and the fields I entered.
3. As a 规则管理员, I want to create one row from the page, so that the list updates without leaving the module.

## Implementation Decisions

- 决策表、触发器、定时任务继续走按类型读写的资源接口。
- 列表使用项目里已有的表格，不新做列表引擎。
- 字段列用中文标签。空列表用空状态，不写介绍性说明。
- 新建时非法 JSON 要提示失败，不能让页面抛出未处理错误。

## Testing Decisions

- 决策表列表对齐 ITSM4：新增、编辑、删除。导入、批量导出和引用详情后置。内置表不可删也后置。
- 触发器和定时任务对齐 ITSM4：新增、编辑、删除、启用和停用。
- 在页面上操作，不通过数据库直接插入来代替。

## Out of Scope

- 决策表的 DMN 可视化。
- 触发器动作的专有表单（通知模板选择、状态选择器）。
- 阶段管理。状态管理只保留状态和 A 到 B 的扭转。

## Further Notes

- 决策表保存条件字段、结果字段和规则行。部署到 Flowable DMN 时取每行第一个条件值和第一个结果值。
- 触发事件对齐 ITSM4 工单信号：创建、更新、挂起、恢复、退回、撤回、结束、完结、关闭、终止、催办、进入节点。响应动作目前是打标签、发送通知、变更状态。
- 定时任务分单次和周期。周期才写 cron，并注册 Celery Beat。单次只记录时间，不注册周期任务。任务类型是创建工单和定时提醒，可选触发后通知。
- 新增和编辑使用项目的 OperateModal。
