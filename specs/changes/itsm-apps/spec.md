# ITSM 应用

Status: ready

## Problem Statement

知识、值班、变更、满意度、打印、交接、业务对象、在线客服和 AI 都是同一层录入壳。没有测试数据时页面是空的，也无法确认列表和新建是否可用。

## Solution

这些应用页共用现有表格。每页展示该类型已保存的行，并允许新建一行。各应用不再复制一套列表。

## User Stories

1. As a 应用管理员, I want each application page to list its saved rows, so that I can tell the page is showing data.
2. As a 应用管理员, I want to create one row on 知识, 值班, 变更, 满意度, 打印, 交接, 业务对象, 在线客服 and AI, so that the operation can be checked on the page.

## Implementation Decisions

- 九个页面继续使用各自的资源类型，不合并成一个应用总表。
- 列表使用项目里已有的表格，列名为中文。
- 变更窗口仍按现有接口校验时间冲突。交接仍按现有接口转移待办。
- 不为这些页面新做卡片墙或独立工作台。

## Testing Decisions

- 应用页先只展示和新建。ITSM4 里这些能力多数在应用集市，不套用决策表那套编辑和删除。
- 页面验收只点产品里存在的按钮。

## Out of Scope

- 知识同步、值班签到、客服会话和 AI 提示词的专有编辑器。
- 把应用页改成实体网格卡片。

## Further Notes

- 样例数据只用于本地验收，不作为生产种子。
