# Historical Superpowers change: 2026-07-15-preserve-cmdb-table-column-config

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-15-preserve-cmdb-table-column-config-design.md

## 背景

`model_init` 会把 `model_config.xlsx` 中主机 `proc` 字段的表格列配置解析为数组。随后执行的 `migrate_field_constraints` 把非字典且非枚举的 `option` 统一改成空字典；当同模型其他字段触发整体保存时，表格列配置随之丢失。

## 方案

- `table` 字段允许 `option` 保持数组结构。
- 其他字段类型的既有约束迁移行为保持不变。
- 不在本次修复中回填已经丢失的历史列配置；后续重新执行 `model_init` 可按初始化文件同步配置。

## 测试

新增回归测试覆盖以下行为：同一模型中的旧字符串字段触发约束补全和整体保存时，表格字段的列配置仍以原数组完整保存。

## 验收标准

1. 修复前回归测试因表格 `option` 被保存为 `{}` 而失败。
2. 修复后回归测试通过。
3. 现有 `migrate_field_constraints` 目标测试通过。
