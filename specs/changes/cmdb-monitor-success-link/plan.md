# 导入与新增成功后续同步 Implementation Plan

> **For agentic workers:** 按任务顺序实现。每步验证后再做下一步。不要提交，除非用户要求。

**Goal:** 资产列表新增、导入新建、监控接入成功后，用现有胶水任务做一次可取消的后续同步。不新做推送 API。

**Architecture:** 要约是 `{ direction, ids[], modelOrObject }`。闸门复用 `canOpenMonitorLink` / `canOpenCmdbLink`。确认框复用列表已有 `Modal.confirm`。导入依赖转移任务摘要里有界的 `created_inst_uuids`。

规格：`specs/changes/cmdb-monitor-success-link/spec.md`

---

## 吞吐量检查点

- **Blocking first steps.** 导入摘要必须带回新建 UUID，否则前端要约没有输入。先做纯函数切片和转移写入，再接线。
- **Independent workstreams.** CMDB 新增、CMDB 导入结束、监控接入成功 三处接线互不改对方文件，可在阻塞步变绿后并行。
- **Shared mutable state.** 列表页的确认函数是共享入口。抽成带 ID 列表的同一个函数，三处只把 ID 传进去。不要复制三份 confirm。
- **Smallest safe decomposition.** 一个实现者按下列 5 个可验证单元顺序做。监控侧可在第 4 步之后交给第二人，但确认函数必须先存在。

---

## 单元 1 要约纯函数

把「这批 ID 能不能要约、要约哪些」收成纯函数。输入：许可、加载中、模型或对象名、原始 ID 列表、可选新建总数。输出：不要约，或 `{ ids, overflow }`，`ids` 最多 100。

验证：扩展 `web/src/app/cmdb/utils/__tests__/systemLinkage.test.ts`。空列表、无许可、平台树、无反向映射、截断 100、只保留非空 ID。

## 单元 2 转移导入记下新建 UUID

`TransferImport` 在真正 `create` 成功时把实例 UUID 追加到 `summary.created_inst_uuids`，写满 100 个停止追加。`created` 计数照旧。更新实例不进该列表。列表/详情 API 原样吐出 summary。

验证：`server/apps/cmdb/tests/test_transfer_import.py`。一次创建、一次更新、超过 100 条创建。跑 sqlite pytest，不启中间件。

## 单元 3 资产列表新增接线

资产列表新增保存成功后，若要约成立，弹出与「建立监控关联」同一确认。确认调用现有 `createCmdbMonitorTask` 并跳任务页。取消只刷新列表。采集任务里的同一表单不接线。

验证：资产页或抽出的确认 helper 测试。新增成功弹窗、取消不建任务、`canOpenMonitorLink` 为假时不弹。现有 `selectionActionBar` 行为不变。

## 单元 4 导入结束接线

`useTransferTasks` 在 import 进入 `succeeded` / `partial_success` 时，把 `summary.created_inst_uuids` 交给同一确认函数。`failed` / `interrupted` / `cancelled` 不弹。用户还停留在资产页才弹。

验证：扩展 `web/src/app/cmdb/hooks/__tests__/useTransferTasks.test.tsx`。终态、空新建、超过 100 的 overflow 文案。

## 单元 5 监控接入成功接线

接入配置成功且抽出了实例 ID 后、离开配置页前，若 `canOpenCmdbLink` 成立，弹出与「同步到 CMDB」同一确认。确认调用现有 `createMonitorCmdbTask`。不调用 `push_to_cmdb`。

验证：抽出实例 ID 的现有测试保持绿。接入成功编排测试：有 ID 弹窗、无许可不弹、取消仍按原路径离开或留在成功态。

---

## 不做

- 不改胶水任务表。
- 不把同步 `inst_import` 的 `data: []` 当成主路径。资产列表导入走转移任务。
- 不在扫描、采集落库、节点推送上再加弹窗。
- 不自动开任务。

## 完成定义

在资产列表新增一条可映射模型、确认同步后，会打开 `/module-link/cmdb-monitor/tasks/{id}`。导入新建一批后同样。监控接入成功确认后打开 `/module-link/monitor-cmdb/tasks/{id}`。取消不同步。无对端许可不弹窗。
