# ITSM 设置

Status: ready

## Problem Statement

处理组、通知模板已经有自己的列表。平台设置仍是只录用户名的壳，代理和公告如果出现，也看不出已保存的行。

## Solution

处理组和通知模板保持现有列表。平台设置以及同模块里走资源接口的代理、公告，用现有表格展示并允许新建。

## User Stories

1. As a 设置管理员, I want 平台设置 to list saved VIP users in a table, so that a username I create is visible.
2. As a 设置管理员, I want to add one VIP user from that page, so that the list updates.
3. As a 设置管理员, I want 处理组 and 通知模板 to stay on their existing pages, so that those flows are not replaced by the generic shell.

## Implementation Decisions

- 平台设置对应 VIP 用户资源。
- 表格使用项目里已有的表格，列名为中文。
- 处理组和通知模板不改成通用资源壳。

## Testing Decisions

- VIP 对齐 ITSM4：添加用户和删除，不提供改用户名。
- 处理组和通知模板保持现有页面上的操作，不套通用删除。

## Out of Scope

- 系统设置里的人员选择器重做。
- 通知渠道和公告的富文本编辑。

## Further Notes

- 代理、公告若从设置菜单进入且走资源接口，遵守同一张表的展示和新建规则。
