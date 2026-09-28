# 节点管理 Agent 清单导出

Status: implemented

## Problem Statement

运维已经能按在线状态和组件状态把节点圈出来，也能跨页勾选后批量处置，但无法把这一批清单带出产品。对账、报备和给未登录同事的材料仍然要靠截屏或手抄，筛出来的集合不能变成一份可打开的表格。

## Solution

在云区域节点清单工具栏提供同步导出。有勾选则导出全部已选节点（含跨页），没勾选则导出当前筛选结果。文件是固定列的 Excel，一行一台机器，状态口径与列表 Sidecar 列和托管组件列相同。

## User Stories

1. As a 节点管理员, I want 在没勾选时导出当前筛选结果, so that 我能把刚圈出的离线或异常节点直接带走。
2. As a 节点管理员, I want 有勾选时导出全部已选节点, so that 跨页凑齐的一批也能整表导出，且不再套一遍当前筛选。
3. As a 节点管理员, I want 导出列与列表可见信息对齐且一行一台, so that 表格里的在线状态和托管组件状态与我在页面上看到的一致。
4. As a 节点管理员, I want 空结果或无权对象被明确拒绝, so that 我不会下载一份空表，也不会把别人的节点导出去。
5. As a 无节点权限的用户, I want 导出仍受现有节点权限和当前云区域约束, so that 看不见的机器也导不出。

## Implementation Decisions

### 入口与集合

- 入口是当前云区域节点清单工具栏，与安装控制器同排，不进入 Sidecar 或托管程序下拉，不弹字段选择。
- 请求体带当前云区域。有非空已选 ID 时按这些 ID 导出，忽略组合筛选；无已选 ID 时按当前筛选导出，筛选包含组合条件。当前是否「仅未归属」仍走与列表相同的目录查询，因为切换该开关会清空勾选，导出时的可见范围必须与勾选来源一致。
- 集合始终落在当前云区域，并走与列表相同的节点授权。已删除或已无权限的已选 ID 丢弃；丢弃后若一个都不剩，视为没有可导出节点。
- 能看列表就能导出，不新增动作权限，不新增对外 OpenAPI，不改 Sidecar 上报协议。

### 文件与列

- 同步返回 `.xlsx`，一张工作表。文件名：`节点清单_{云区域名}_{年月日时分秒}.xlsx`。表头和单元格跟当前界面语言。
- 固定列顺序：节点名称、IP、操作系统、CPU 架构、节点类型、安装方式、组织、在线状态、最后上报时间、控制器版本、控制器可升级、托管组件。
- 组织导出显示名，多个用逗号拼接，未归属写列表同一套「未归属」文案，不写组织 ID。在线状态与 Sidecar 列同一心跳口径（间隔小于 60 秒为在线，恰好 60 秒为离线）。控制器可升级为是/否；无版本则版本列为空。
- 托管组件一格：`展示名:状态文案`，多项用中文分号拼接。展示名、状态文案、空跑错误改写与列表托管组件列同一口径。没有组件则该格为空，不写「未安装」。
- 不导出节点内部 ID。

### 上限与失败

- 单次最多 5000 台。超过则整次失败并说明当前数量与上限，不截断、不改异步任务。
- 没有可导出节点：提示「没有可导出的节点」，不返回只有表头的文件。
- 导出接口不记录节点 payload、凭据或 Excel 正文。

### 模块与缝

- 节点搜索接口旁增加导出动作：复用现有授权查询、筛选处理和列表状态加工，导出门不做分页。
- 测试主缝是该导出动作的 HTTP 响应（状态码、附件、读回的工作表行列）。行内容以列表已加工后的展示值为准，不另开一套状态计算。

## Testing Decisions

只锁定外部行为：给定筛选或已选 ID 时文件中的节点集合、列口径、空结果、越权和超限。不测 Excel 库内部，不测工具栏按钮样式。

服务端覆盖：无勾选时导出当前筛选（含在线状态、组件状态与现有字段 AND）；有 ID 时只导出这些 ID 且忽略筛选；跨页意义上的多 ID 全集；当前云区域隔离；无权或已删 ID 被丢弃；丢弃后为空则失败且无附件；空筛选失败且无附件；超过 5000 失败且不截断；托管组件单元格使用展示名与改写后状态；无组件单元格为空。风格对齐现有节点搜索测试，读回 xlsx 的方式对齐系统管理操作日志/登录日志导出测试。

前端只锁定：有已选时请求带已选 ID；无已选时请求带当前筛选与未归属，不带已选 ID。不测浏览器下载对话框。

## Out of Scope

- 导入节点或 Agent 清单。
- 异步导出任务、导入导出记录、进度条、按相同条件重新提交。
- 导出前选择字段。
- 按组件拆成多行或第二张组件明细表。
- 一键全选当前筛选结果。
- 导出节点内部 ID。
- 修改 Sidecar 上报协议、新增对外 OpenAPI。

## Further Notes

- 筛选与跨页勾选已在 `specs/changes/node-mgmt-agent-status-filter/spec.md` 交付；本变更只补导出。
- 验收主链：筛离线后导出；跨页勾选后导出全集；筛 Telegraf 异常后导出且空跑改写为正常的节点不在文件中。
- 验收降级：无命中不下载；勾选全部无权不下载；命中超过 5000 整次失败；无权限看不到别人的节点。
- 实现计划：`specs/changes/node-mgmt-agent-export/plan.md`

## Verification

2026-09-28，`--nomigrations` 后端回归 57 passed；前端 vitest 7 passed。

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/node_mgmt/tests/test_node_export.py \
  apps/node_mgmt/tests/test_node_viewset_export.py \
  apps/node_mgmt/tests/test_node_viewset_search_update_enum.py \
  apps/node_mgmt/tests/test_b75_node_filter_handler.py \
  --no-cov --nomigrations
# 57 passed in 2.38s

cd web && pnpm exec vitest run \
  src/app/node-manager/utils/__tests__/nodeListExport.test.ts \
  src/app/node-manager/utils/__tests__/nodeListSelection.test.ts \
  src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts
# Test Files 3 passed / Tests 7 passed (4.05s)
```
