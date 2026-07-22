# 修复 Job_Mgmt 状态一致性问题

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-14-fix-job-mgmt-state-consistency/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         修复前 vs 修复后                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  问题 1: 定时任务分离写入                                                │
│  ┌─────────────────────┐      ┌─────────────────────┐                  │
│  │ 修复前              │      │ 修复后              │                  │
│  │                     │      │                     │                  │
│  │ ScheduledTask ✓     │      │ transaction.atomic: │                  │
│  │ PeriodicTask ✗      │  →   │   ScheduledTask ✓   │                  │
│  │ 结果: 状态分裂      │      │   PeriodicTask ✗    │                  │
│  │                     │      │   → 全部回滚 ✓      │                  │
│  └─────────────────────┘      └─────────────────────┘                  │
│                                                                         │
│  问题 2: 回调异常不收敛                                                  │
│  ┌─────────────────────┐      ┌─────────────────────┐                  │
│  │ 修复前              │      │ 修复后              │                  │
│  │                     │      │                     │                  │
│  │ 异常 → return       │      │ 异常 → _fail_exec() │                  │
│  │ status = RUNNING    │  →   │ status = FAILED     │                  │
│  │ 永久卡死            │      │ 正常收敛 ✓          │                  │
│  └─────────────────────┘      └─────────────────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 详细设计

### 1. 定时任务事务保护

#### 1.1 Create 流程

```python
# server/apps/job_mgmt/serializers/scheduled_task.py

from django.db import transaction

class ScheduledTaskCreateSerializer(serializers.ModelSerializer):

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["created_by"] = request.user.username
            validated_data["updated_by"] = request.user.username

        with transaction.atomic():
            instance = ScheduledTask.objects.create(**validated_data)

            periodic_task = ScheduledTaskService.create_periodic_task(instance)
            if periodic_task:
                instance.periodic_task_id = periodic_task.id
                instance.save(update_fields=["periodic_task_id"])
            else:
                # PeriodicTask 创建失败，回滚整个事务
                raise serializers.ValidationError(
                    {"non_field_errors": ["创建定时调度任务失败，请检查 Cron 表达式或计划执行时间"]}
                )

        return instance
```

#### 1.2 Update 流程

```python
class ScheduledTaskUpdateSerializer(serializers.ModelSerializer):

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["updated_by"] = request.user.username

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            periodic_task = ScheduledTaskService.update_periodic_task(instance)
            if periodic_task:
                instance.periodic_task_id = periodic_task.id
                instance.save(update_fields=["periodic_task_id"])
            elif instance.is_enabled:
                # 启用状态下 PeriodicTask 更新失败，回滚
                raise serializers.ValidationError(
                    {"non_field_errors": ["更新定时调度任务失败，请检查配置"]}
                )

        return instance
```

### 2. Ansible 回调异常收敛

#### 2.1 辅助函数

```python
# server/apps/job_mgmt/nats_api.py

def _fail_execution(execution, error_message: str):
    """将执行记录收敛到 FAILED 终态"""
    execution.status = ExecutionStatus.FAILED
    execution.finished_at = timezone.now()
    target_list = execution.target_list or []
    execution.execution_results = [
        {
            "target_key": str(t.get("target_id", "")),
            "name": t.get("name", ""),
            "ip": t.get("ip", ""),
            "status": ExecutionStatus.FAILED,
            "stdout": "",
            "stderr": error_message,
            "exit_code": 1,
            "error_message": error_message,
            "started_at": execution.started_at.isoformat() if execution.started_at else "",
            "finished_at": timezone.now().isoformat(),
        }
        for t in target_list
    ]
    execution.success_count = 0
    execution.failed_count = len(target_list)
    execution.save(update_fields=[
        "status", "execution_results", "finished_at",
        "success_count", "failed_count", "updated_at"
    ])
    logger.warning(f"[ansible_task_callback] 任务异常收敛到 FAILED: task_id={execution.id}, reason={error_message}")
    send_callback(execution)
```

#### 2.2 异常分支处理

所有异常分支调用 `_fail_execution()` 后再 return：

```python
# 验证结果格式
if not (isinstance(raw_result, list) and raw_result and all(isinstance(item, dict) for item in raw_result)):
    _fail_execution(execution, f"回调结果格式非法: {raw_result}")
    return {"success": False, "message": "非法的新版本结果格式，已收敛到 FAILED"}

# 主机未匹配
if not target_info:
    _fail_execution(execution, f"结果中的主机未匹配到目标: {host_key}")
    return {"success": False, "message": f"主机未匹配到目标: {host_key}，已收敛到 FAILED"}

# 主机重复
if target_key in seen_target_keys:
    _fail_execution(execution, f"结果中的主机重复: {host_key}")
    return {"success": False, "message": f"主机重复: {host_key}，已收敛到 FAILED"}
```

## 边界情况

### 问题 1 边界情况

| 场景 | 处理方式 |
|------|---------|
| PeriodicTask 创建失败 | 抛出 ValidationError，事务回滚 |
| PeriodicTask 更新失败但任务已禁用 | 允许通过（禁用状态不需要 PeriodicTask） |
| 数据库连接异常 | 事务自动回滚 |

### 问题 2 边界情况

| 场景 | 处理方式 |
|------|---------|
| task_id 缺失 | 直接返回（无法定位 execution） |
| execution 不存在 | 直接返回（无法更新） |
| execution 已是终态 | 直接返回（幂等处理） |
| 结果格式非法 | 收敛到 FAILED |
| 主机未匹配 | 收敛到 FAILED |
| 主机重复 | 收敛到 FAILED |

## 测试要点

1. 定时任务创建时 PeriodicTask 失败，验证 ScheduledTask 是否回滚
2. 定时任务更新时 PeriodicTask 失败，验证 ScheduledTask 是否回滚
3. Ansible 回调结果格式非法，验证 execution 是否收敛到 FAILED
4. Ansible 回调主机未匹配，验证 execution 是否收敛到 FAILED
5. Ansible 回调主机重复，验证 execution 是否收敛到 FAILED

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
```

## Work Checklist

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
