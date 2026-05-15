# 设计文档

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
