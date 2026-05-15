# 任务列表

## 问题 1: 定时任务事务保护

- [x] 1.1 修改 `ScheduledTaskCreateSerializer.create()` 添加事务保护
  - 文件: `server/apps/job_mgmt/serializers/scheduled_task.py`
  - 使用 `transaction.atomic()` 包裹写入操作
  - PeriodicTask 创建失败时抛出 `ValidationError`

- [x] 1.2 修改 `ScheduledTaskUpdateSerializer.update()` 添加事务保护
  - 文件: `server/apps/job_mgmt/serializers/scheduled_task.py`
  - 使用 `transaction.atomic()` 包裹写入操作
  - 启用状态下 PeriodicTask 更新失败时抛出 `ValidationError`

## 问题 2: Ansible 回调异常收敛

- [x] 2.1 新增 `_fail_execution()` 辅助函数
  - 文件: `server/apps/job_mgmt/nats_api.py`
  - 将 execution 状态设置为 FAILED
  - 填充所有目标的失败结果
  - 调用 `send_callback()` 通知

- [x] 2.2 修改 `ansible_task_callback()` 异常分支
  - 文件: `server/apps/job_mgmt/nats_api.py`
  - 结果格式非法时调用 `_fail_execution()`
  - 主机未匹配时调用 `_fail_execution()`
  - 主机重复时调用 `_fail_execution()`

## 验证

- [x] 3.1 运行语法检查
  - `python -m py_compile` 通过

- [x] 3.2 代码验证完成
  - 语法正确
  - 逻辑符合设计
