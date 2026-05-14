# 修复 Job_Mgmt 状态一致性问题

## 概述

修复 job_mgmt 模块中两个严重的状态一致性问题：
1. 定时任务与 celery-beat 分离写入导致调度状态分裂
2. Ansible 异步回调异常不收敛终态导致作业永久 RUNNING

## 背景

链路审核发现 job_mgmt 模块存在状态一致性缺陷，已创建 GitHub Issues：
- [#2962](https://github.com/TencentBlueKing/bk-lite/issues/2962) - 定时任务与 celery-beat 分离写入
- [#2963](https://github.com/TencentBlueKing/bk-lite/issues/2963) - Ansible 异步回调异常不收敛终态

## 问题分析

### 问题 1: 定时任务与 celery-beat 分离写入

**现状**：
- `ScheduledTaskCreateSerializer.create()` 先创建 `ScheduledTask`，再创建 `PeriodicTask`
- 两个写入操作无事务保护
- `PeriodicTask` 创建失败时仅记录日志返回 None，不回滚 `ScheduledTask`

**风险**：
- 页面显示任务已启用，但 celery-beat 无此任务
- 定时任务永远不会被调度执行

**代码位置**：
- `server/apps/job_mgmt/serializers/scheduled_task.py` (lines 180-195, 294-310)
- `server/apps/job_mgmt/services/scheduled_task_service.py` (lines 94-96, 131-133)

### 问题 2: Ansible 异步回调异常不收敛终态

**现状**：
- `ansible_task_callback()` 在多个异常分支直接 return，不更新 `execution.status`
- 异常场景包括：结果格式非法、主机未匹配、主机重复等

**风险**：
- `JobExecution` 永久卡在 RUNNING 状态
- 如果 `concurrency_policy=SKIP`，后续调度被阻塞

**代码位置**：
- `server/apps/job_mgmt/nats_api.py` (lines 76-218)

## 解决方案

### 方案 1: 事务保护定时任务写入

使用 `transaction.atomic()` 包裹 `ScheduledTask` 和 `PeriodicTask` 的写入操作，`PeriodicTask` 创建失败时抛出异常触发回滚。

### 方案 2: 异常分支收敛到 FAILED 终态

新增 `_fail_execution()` 辅助函数，所有异常分支调用此函数将 `execution.status` 设置为 `FAILED` 后再 return。

## 影响范围

| 问题 | 修改文件 | 影响接口 | 向后兼容 |
|------|---------|---------|---------|
| 问题 1 | `serializers/scheduled_task.py` | 定时任务创建/更新 API | ✅ 是 |
| 问题 2 | `nats_api.py` | Ansible 回调（内部 NATS） | ✅ 是 |

## 关联 Issues

- https://github.com/TencentBlueKing/bk-lite/issues/2962
- https://github.com/TencentBlueKing/bk-lite/issues/2963
