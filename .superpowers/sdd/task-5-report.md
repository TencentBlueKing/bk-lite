# Task 5 实施报告：节点同步主机真实持久化

## 状态

- 已完成：已有主机仅在白名单字段真实变化时调用 `InstanceManage.instance_update`。
- 已完成：新增和更新均使用当前 `run.generation` 作为 `operation_id`，后台更新显式 `skip_permission_check=True`。
- 已完成：单主机失败不终止整批，分别汇总 `add_error` / `update_error`，父运行标记 `partial_success`。
- 已完成：错误明细与日志只保留操作类型和异常类型，不包含异常原文或节点原始敏感字段。

## 实现选择

- 更新白名单为 `inst_name`、`ip_addr`、`organization`、`cloud`、`os_type`；这些字段来自当前主机 payload 与真实 host 模型合同。
- 未采用计划示例中的 `cloud_region`，也未把 `cloud_id`、`cloud_name`、`node_id`、`source` 等同步元数据写入更新属性。
- 仍按 `(ip_addr, cloud)` 加载和查重；同一 generation 重试复用既有映射，不增加 schema。
- 创建与更新均传 `schedule_post_actions=False`，整批成功实例 ID 去重后只调度一次关联对账，避免逐条重复调度。
- 关联调度异常计入 `association_error` 并使父运行 `partial_success`，同样使用稳定脱敏错误。

## TDD 与验证

- RED：新增测试首次真实执行为 `7 failed`，证明 `_persist_hosts` 缺失、已有主机假更新、父运行误报成功、关联对账未统一调度。
- GREEN：`test_node_mgmt_sync_persistence.py` 最终 `8 passed`。
- Task 2–5 定向回归：models/reconciler/views/helpers/resilience/persistence 共 `111 passed`（补测前集合；新增第 8 项另行通过）。
- 覆盖率：persistence + resilience 的新增生产语句覆盖 `73/77 = 94.81%`，达到核心逻辑 ≥90% 要求。
- 静态检查：新增测试通过 black/isort/flake8；service isort 通过，flake8 仅报告未触及历史基线 `node_mgmt_sync_service.py:768 E125`。
- `git diff --check` 通过。

## 关注项

- `node_mgmt_sync_service.py` 历史整体不符合当前 black 基线；本任务未整文件格式化，避免数百行无关污染。
- 创建计数维持现有展示合同：`add`/`add_success` 统计成功新增，失败单独计入 `add_error`；更新按真实变化尝试数统计 `update`，成功/失败分别落 `update_success`/`update_error`。

## 独立审查 Important 修复

- RED：新增创建白名单断言与真实重载重试用例后，聚焦执行为 `2 failed`。创建分支实际把 `cloud_id`、`cloud_name`、`node_id`、`source`、`secret` 等完整同步元数据传给 `instance_create`，第二次完整 `_do_sync_hosts` 后 `detail.raw_data` 也保留了禁用字段。
- GREEN：新增与更新统一以 `inst_name`、`ip_addr`、`organization`、`cloud`、`os_type` 构造真实 host 持久化载荷；`add_data`、`update_data`、`raw_data` 使用独立白名单展示结构（仅额外保留 `_id`），聚焦 `2 passed`。
- 重试合同：移除复用 `_persist_hosts` 原地修改字典的旧测试；新测试连续执行两次 `_do_sync_hosts`，第二次由 `_load_existing_host_map` 按 `(ip_addr, cloud)` 返回持久化主机，确认 `instance_create` 仅调用一次且第二次 `add=0`、`update=0`。
- 回归：Task 2–5 的 models/reconciler/views/helpers/resilience/persistence 六文件共 `112 passed`；persistence + resilience 覆盖执行 `13 passed`。
- 覆盖率：本轮新增生产可执行语句 `15/15 = 100%`，达到新增行 ≥90% 要求。
- 静态检查：测试文件通过 black/isort/flake8，service 通过 isort；flake8 仍只报告未触及历史基线 `node_mgmt_sync_service.py:768 E125`；`git diff --check` 通过。
