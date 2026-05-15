# 执行中断信号持久化修复

## 问题描述

执行中断只保存在带 TTL（默认 3600s）的缓存键里，运行中的 Agent/Tool/AGUI 轮询也只读这个缓存键，不读取任何持久状态。中断请求一旦过期或缓存丢失，长任务会继续执行。

**影响文件**:
- `server/apps/opspilot/utils/execution_interrupt.py`
- `server/apps/opspilot/views.py`
- `server/apps/opspilot/metis/llm/chain/node.py`
- `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py`
- `server/apps/opspilot/utils/agui_chat.py`

## 当前实现（问题代码）

### execution_interrupt.py

```python
INTERRUPT_CACHE_TTL = int(os.getenv("WORKFLOW_INTERRUPT_CACHE_TTL", "3600"))

def request_interrupt(execution_id: str, reason: str = "user_manual", ...):
    # 只写缓存
    cache.set(_get_interrupt_cache_key(execution_id), payload, INTERRUPT_CACHE_TTL)

def is_interrupt_requested(execution_id: str) -> bool:
    # 只查缓存，TTL 过期后返回 False
    return get_interrupt_request(execution_id) is not None
```

### views.py (行 674-679)

```python
# 同时写缓存和数据库，但执行引擎只读缓存
request_interrupt(execution_id, reason=kwargs.get("reason", "user_manual"))
task_result.status = WorkFlowTaskStatus.INTERRUPTED
task_result.save(update_fields=["status", "finished_at"])
```

## 修复方案

### 方案：双重检查（缓存 + 数据库）

中断状态同时写入缓存和数据库，检查时先查缓存（快），缓存未命中再查数据库（兜底）。

### execution_interrupt.py 修复

```python
from apps.opspilot.models import WorkFlowTaskResult, WorkFlowTaskStatus

def is_interrupt_requested(execution_id: str) -> bool:
    """检查是否已请求中断 - 双重检查机制"""
    if not execution_id:
        return False
    
    # 1. 先查缓存（快速路径）
    if get_interrupt_request(execution_id) is not None:
        return True
    
    # 2. 缓存未命中，查数据库（兜底路径）
    # 复用 views.py 已写入的 WorkFlowTaskResult.status
    try:
        return WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            status=WorkFlowTaskStatus.INTERRUPTED
        ).exists()
    except Exception as e:
        logger.warning(f"中断状态数据库查询失败: {e}")
        return False
```

## 数据一致性

- `views.py` 已经同时写入缓存和数据库
- 修复后执行引擎同时检查两者
- 缓存提供快速路径，数据库提供持久保障

## 性能影响

- 缓存命中时：无额外开销
- 缓存未命中时：增加一次数据库 `exists()` 查询
- `exists()` 查询很快，且只在缓存过期后执行
- 可通过索引优化 `execution_id` 字段

## 测试要点

1. 验证缓存有效时中断检查正常工作
2. 验证缓存过期后仍能检测到中断（从数据库）
3. 验证长时间运行任务（>1小时）的中断功能
4. 验证数据库查询失败时的降级处理
