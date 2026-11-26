# ITSM 表单与数据

Status: ready

## Problem Statement

数据源页面是一层录入壳，字典和数据表已经有自己的列表。把数据源继续做成英文键值拼接，无法和字典、数据表放在同一模块里验收。

## Solution

数据源用现有表格列出已保存的数据源，并允许新建。数据字典和数据表保持现有可操作列表，不改成通用壳。

## User Stories

1. As a 数据管理员, I want saved 数据源 to appear in a table with a name and a kind, so that I can see what is configured.
2. As a 数据管理员, I want to create a 数据源 from that page, so that the new row shows up in the same table.

## Implementation Decisions

- 数据源继续走资源接口。
- 列表使用项目里已有的表格，列名为中文。
- 不把数据字典和数据表并入通用资源壳。

## Testing Decisions

- 数据源在 ITSM4 没有对应的通用增删改查列表。本页只展示和新建，不默认提供修改和删除。
- 数据字典和数据表保持各自已有操作：字典含导入导出，数据表含导入、导出和删除。

## Out of Scope

- 数据源连接测试和字段映射。
- 表单设计器画布。表单模型的设计行为见表单设计规格。

## Further Notes

- 表单模型列表和设计器已经能创建并打开，不在本规格重做。
