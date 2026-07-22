# Historical Superpowers change: 2026-07-15-soid-table-bottom-spacing

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-15-soid-table-bottom-spacing-design.md

## 背景

在 1200×800 视口下，SOID 表格容器底部距离视口底部为 135px，资产实例列表为 54px。SOID 使用 `calc(100vh - 450px)`，导致表体目标高度比资产实例列表少 130–150px。

## 目标

- SOID 表格底部留白与资产实例列表对齐，正常桌面视口下误差不超过 2px。
- 保留 `CustomTable` 已有的 160px 最小表体高度保护。
- 不改变资产实例列表及其他 `CustomTable` 使用方。

## 方案

仅将 SOID 页的表体高度偏移从 450px 调整为 370px。按当前页面布局计算，1200×800 视口下 SOID 表格容器底部留白将由 135px 降至约 55px，与资产实例列表的 54px 基本一致。

本次不新增 ResizeObserver，不修改公共 `CustomTable`，避免扩大影响面或重新引入高度反馈循环。

## 验证

1. 先增加回归测试，确认 SOID 使用 370px 偏移且资产实例列表保持 300/320px 规则。
2. 运行触及文件的 ESLint 与现有 CustomTable 高度回归测试。
3. 在 1200×800 视口分别测量两页表格容器底部留白，目标差值不超过 2px。
4. 缩小视口高度，确认表体不会低于 160px，也不会出现连续高度漂移。
