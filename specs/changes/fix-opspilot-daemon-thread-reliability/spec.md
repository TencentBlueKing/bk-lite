# Fix Opspilot Daemon Thread Reliability

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/fix-opspilot-daemon-thread-reliability/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot 存在三个相关的可靠性问题，都涉及 daemon 线程 + best-effort 模式缺乏确认闭环：

1. **Issue #2959 - SSE 持久化依赖守护线程**：流式对话的 bot 回复、技能日志与 WorkFlowTaskResult 收尾统一延后到 daemon 线程做 best-effort 持久化，主流程不等待也不兜底；一旦流在落库前异常结束、worker 被回收或后台线程未跑完，审计日志和执行状态会直接丢失。

2. **Issue #2960 - 中断信号仅保存在带 TTL 的缓存**：执行中断只保存在带 TTL（默认 3600s）的缓存键里，运行中的 Agent/Tool/AGUI 轮询也只读这个缓存键，不读取任何持久状态；中断请求一旦过期或缓存丢失，长任务会继续执行，用户端"已中断"的状态只是表象。

3. **Issue #2961 - 外部渠道消息先去重后异步 ACK**：WeChat/DingTalk 外部渠道采用"先去重标记、立即 ACK、再用 daemon 线程异步处理"的 fire-and-forget 模式，且失败后没有重试或回滚去重标记；只要后台线程未真正完成，外部平台已经停止重试，消息会被永久吞掉。

这三个问题的共同模式是：**关键操作在 daemon 线程中执行，无确认机制，失败后无法恢复**。

## What Changes

### 修复 #2959 - SSE 持久化可靠性

- 将 SSE 流结束时的持久化操作从 daemon 线程改为同步执行或可靠的异步队列
- 确保 bot 对话历史、token 审计、WorkFlowTaskResult 状态在流结束前完成落库
- 失败时记录到可恢复的队列，支持后续补偿

### 修复 #2960 - 中断信号持久化

- 中断状态增加数据库持久化真源
- 执行引擎同时检查缓存（加速）和数据库（兜底）
- 缓存过期后仍能从数据库读取中断状态

### 修复 #2961 - 外部渠道消息可靠处理

- 去重标记改为两阶段：处理中 → 已完成
- 处理失败时清除去重标记，允许平台重试
- 或使用 Celery 任务替代 daemon 线程，确保有重试机制

## Capabilities

### Modified Capabilities

- `sse-persistence`: SSE 流式对话的持久化机制
- `execution-interrupt`: 执行中断控制模块
- `external-channel-message`: 外部渠道（WeChat/DingTalk）消息处理

## Impact

- **后端代码**:
  - `server/apps/opspilot/utils/sse_chat.py` (修改持久化逻辑)
  - `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py` (修改持久化逻辑)
  - `server/apps/opspilot/utils/execution_interrupt.py` (增加持久化)
  - `server/apps/opspilot/views.py` (修改中断接口)
  - `server/apps/opspilot/metis/llm/chain/node.py` (修改中断检查)
  - `server/apps/opspilot/utils/base_chat_flow_utils.py` (修改去重逻辑)
  - `server/apps/opspilot/utils/wechat_chat_flow_utils.py` (修改消息处理)
  - `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py` (修改消息处理)

- **数据库**: 可能需要新增中断状态表或字段

- **依赖**: 无新增依赖，复用现有 Celery/Redis 机制

## Implementation Decisions

## Context

OpsPilot 的多个模块使用 daemon 线程执行关键操作（持久化、消息处理），但缺乏确认闭环，导致可靠性问题。

**当前问题架构**:
```
主流程 → 返回响应 → daemon 线程执行关键操作
                           ↓
                    线程失败/进程退出 → 操作丢失，无法恢复
```

**目标架构**:
```
主流程 → 关键操作（同步或可靠队列） → 返回响应
                    ↓
              失败时有重试/补偿机制
```

**约束**:
- 不能影响前端流式对话的实时性
- 不引入新的外部依赖（复用现有 Celery）
- 渐进式修复，优先解决最严重的问题

## Goals / Non-Goals

**Goals:**
- 确保 SSE 流式对话的审计日志和执行状态不丢失
- 确保中断信号在缓存过期后仍然有效
- 确保外部渠道消息处理失败后可以重试
- 保持前端流式对话的实时性不受影响

**Non-Goals:**
- 完全重构消息处理架构 - 后续迭代
- 引入新的消息队列中间件 - 复用现有 Celery
- 修改外部平台的重试策略 - 不可控

## Decisions

### 1. SSE 持久化：流结束后同步落库

**决策**: 将 daemon 线程的持久化操作改为流结束后同步执行。

**当前代码** (`sse_chat.py`):
```python
# 注释说"避免阻塞流式响应"，但此时流已结束，无需异步
threading.Thread(target=log_in_background, daemon=True).start()
```

**修复方案**:
```python
# 同步执行（流已结束，不影响用户体验）
if final_stats["content"]:
    try:
        _log_and_update_tokens_sync(...)  # 直接同步调用
    except Exception as e:
        logger.error(f"SSE 持久化失败: {e}", exc_info=True)
```

**理由**:
- 流式输出已经完成，用户已看到回复，此时同步落库不影响体验
- 落库操作通常很快（<100ms），延迟可接受
- 简单可靠，无需引入新机制
- 原代码注释说"避免阻塞流式响应"，但 STATS 事件时流已结束，异步是不必要的

### 2. 中断信号：双重检查（缓存 + 数据库）

**决策**: 中断状态同时写入缓存和数据库，检查时先查缓存（快），缓存未命中再查数据库（兜底）。

**当前代码** (`execution_interrupt.py`):
```python
# 问题：只写缓存，TTL（默认3600s）过期后丢失
cache.set(_get_interrupt_cache_key(execution_id), payload, INTERRUPT_CACHE_TTL)
```

**修复方案**:
```python
def is_interrupt_requested(execution_id: str) -> bool:
    # 1. 先查缓存（快速路径）
    if cache.get(_get_interrupt_cache_key(execution_id)):
        return True
    # 2. 缓存未命中，查数据库（兜底路径）
    # 复用 views.py 已写入的 WorkFlowTaskResult.status
    from apps.opspilot.models import WorkFlowTaskResult, WorkFlowTaskStatus
    return WorkFlowTaskResult.objects.filter(
        execution_id=execution_id,
        status=WorkFlowTaskStatus.INTERRUPTED
    ).exists()
```

**理由**:
- 缓存提供快速路径，数据库提供持久保障
- 复用现有 WorkFlowTaskResult 表，无需新增表
- views.py 已经同时写入缓存和数据库，只需修改读取逻辑
- 数据库查询只在缓存未命中时执行，性能影响小

### 3. 外部渠道：Celery 任务 + 两阶段去重

**决策**: 使用 Celery 任务替代 daemon 线程处理外部渠道消息，同时使用两阶段去重确保可靠性。

**为什么必须异步**:
- WeChat/DingTalk webhook 有超时限制（通常 5 秒）
- ChatFlow 执行可能需要几十秒（LLM 调用、工具执行）
- 同步执行会导致 webhook 超时，平台会重试，导致重复处理

**为什么用 Celery 而不是 daemon 线程**:
| 维度 | daemon 线程 | Celery |
|------|-------------|--------|
| 任务持久化 | ❌ 进程退出丢失 | ✅ Redis 持久化 |
| 失败重试 | ❌ 无 | ✅ 自动重试 |
| 监控 | ❌ 无 | ✅ Flower/日志 |
| 资源隔离 | ❌ 占用 Web 进程 | ✅ 独立 Worker |

**项目现状**: opspilot 已有 Celery 任务（`apps/opspilot/tasks.py`），基础设施已就绪。

**修复方案**:

```python
# apps/opspilot/tasks.py 新增

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_message(self, bot_id, msg_id, message, sender_id, config):
    """处理企业微信消息的 Celery 任务"""
    handler = WeChatChatFlowUtils(bot_id)
    try:
        bot_chat_flow = get_bot_chat_flow(bot_id)
        reply_text = handler.execute_chatflow_with_message(
            bot_chat_flow, config["node_id"], message, sender_id
        )
        handler.send_reply(reply_text, sender_id, config)
        # 成功：标记完成
        handler.mark_message_completed(msg_id)
    except Exception as e:
        logger.error(f"微信消息处理失败: {e}")
        # 失败：清除去重标记，允许重试
        handler.mark_message_failed(msg_id)
        # 触发 Celery 重试
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_dingtalk_message(self, bot_id, msg_id, text_content, sender_id, webhook_url, config):
    """处理钉钉消息的 Celery 任务"""
    handler = DingTalkChatFlowUtils(bot_id)
    try:
        bot_chat_flow = get_bot_chat_flow(bot_id)
        reply_text = handler.execute_chatflow_with_message(
            bot_chat_flow, config["node_id"], text_content, sender_id, is_third_party=True
        )
        if webhook_url and reply_text:
            handler.send_message(webhook_url, "markdown", {"title": "机器人回复", "text": reply_text})
        handler.mark_message_completed(msg_id)
    except Exception as e:
        logger.error(f"钉钉消息处理失败: {e}")
        handler.mark_message_failed(msg_id)
        raise self.retry(exc=e)
```

```python
# wechat_chat_flow_utils.py 修改

def handle_wechat_message(self, request, bot_chat_flow, wechat_config):
    # ... 解析消息 ...

    if self.is_message_processed(msg_id):
        return HttpResponse("success")

    # 改用 Celery 任务（替代 daemon 线程）
    from apps.opspilot.tasks import process_wechat_message
    process_wechat_message.delay(
        bot_id=self.bot_id,
        msg_id=msg_id,
        message=message,
        sender_id=sender_id,
        config=wechat_config,
    )

    return HttpResponse("success")
```

**两阶段去重**（与 Celery 配合使用）:

```python
# base_chat_flow_utils.py

MESSAGE_PROCESSING_EXPIRE_SECONDS = 300   # 处理中状态 5 分钟超时
MESSAGE_COMPLETED_EXPIRE_SECONDS = 86400  # 已完成状态 24 小时

def is_message_processed(self, msg_id: str) -> bool:
    """两阶段去重检查"""
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    status = cache.get(cache_key)

    if status == "completed":
        return True  # 已完成，跳过
    if status == "processing":
        return True  # 处理中，跳过（防止并发）

    # 标记为处理中（短 TTL，超时后允许重试）
    cache.set(cache_key, "processing", MESSAGE_PROCESSING_EXPIRE_SECONDS)
    return False

def mark_message_completed(self, msg_id: str):
    """处理成功后调用"""
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    cache.set(cache_key, "completed", MESSAGE_COMPLETED_EXPIRE_SECONDS)

def mark_message_failed(self, msg_id: str):
    """处理失败后调用，清除标记允许重试"""
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    cache.delete(cache_key)
```

**理由**:
- Celery 提供任务持久化和自动重试，比 daemon 线程可靠
- 两阶段去重防止并发重复处理，失败后允许重试
- 项目已有 Celery 基础设施，无需引入新依赖
- Celery 重试 + 两阶段去重 = 双重保障

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 同步落库增加响应延迟 | 落库操作通常 <100ms，可接受；可监控延迟 |
| 数据库查询增加中断检查开销 | 只在缓存未命中时查询，影响小 |
| Celery Worker 不可用 | 监控 Worker 状态；任务会在 Redis 中排队等待 |
| 两阶段去重增加代码复杂度 | 封装为基类方法，子类无感知 |
| 处理中状态 TTL 设置不当 | 可配置，默认 5 分钟，覆盖大多数场景 |

## 数据流

### SSE 持久化（修复后）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SSE 持久化数据流（修复后）                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────┐    ┌──────────────────┐    ┌─────────────────────────────┐ │
│  │   LLM   │───▶│ 流式输出 chunk   │───▶│ 前端实时显示                 │ │
│  └─────────┘    └──────────────────┘    └─────────────────────────────┘ │
│                         │                                               │
│                         ▼                                               │
│                 ┌──────────────────┐                                    │
│                 │ 流结束（STATS）   │                                    │
│                 └──────────────────┘                                    │
│                         │                                               │
│                         ▼                                               │
│                 ┌──────────────────┐    ┌─────────────────────────────┐ │
│                 │ 同步落库         │───▶│ history_log.save()          │ │
│                 │ （不再用daemon） │    │ insert_skill_log()          │ │
│                 └──────────────────┘    │ update_task_result()        │ │
│                                         └─────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 中断检查（修复后）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         中断检查数据流（修复后）                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐                                                    │
│  │ is_interrupt_   │                                                    │
│  │ requested()     │                                                    │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────┐    Yes    ┌─────────────────────────────┐         │
│  │ 查缓存          │─────────▶│ return True（快速路径）      │         │
│  └────────┬────────┘           └─────────────────────────────┘         │
│           │ No                                                          │
│           ▼                                                             │
│  ┌─────────────────┐    Yes    ┌─────────────────────────────┐         │
│  │ 查数据库        │─────────▶│ return True（兜底路径）      │         │
│  │ (WorkFlowTask   │           └─────────────────────────────┘         │
│  │  Result.status) │                                                    │
│  └────────┬────────┘                                                    │
│           │ No                                                          │
│           ▼                                                             │
│  ┌─────────────────────────────┐                                        │
│  │ return False（未中断）      │                                        │
│  └─────────────────────────────┘                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 外部渠道消息处理（修复后）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 外部渠道消息处理数据流（修复后 - Celery）                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │ WeChat/DingTalk │───▶│ 检查去重状态     │───▶│ completed?        │  │
│  │ 回调到达        │    └──────────────────┘    │ → 跳过            │  │
│  └─────────────────┘                            │ processing?       │  │
│                                                 │ → 跳过            │  │
│                                                 │ 无状态?           │  │
│                                                 │ → 继续处理        │  │
│                                                 └─────────┬─────────┘  │
│                                                           │            │
│                                                           ▼            │
│                                                 ┌───────────────────┐  │
│                                                 │ 标记 "processing" │  │
│                                                 │ (TTL=5min)        │  │
│                                                 └─────────┬─────────┘  │
│                                                           │            │
│                                                           ▼            │
│  ┌─────────────────┐                            ┌───────────────────┐  │
│  │ ACK success     │◀───────────────────────────│ 投递 Celery 任务  │  │
│  │ 给外部平台      │                            │ (替代daemon线程)  │  │
│  └─────────────────┘                            └───────────────────┘  │
│                                                           │            │
│                                                           ▼            │
│                                                 ┌───────────────────┐  │
│                                                 │ Celery Worker     │  │
│                                                 │ 执行 ChatFlow     │  │
│                                                 │ (有重试机制)      │  │
│                                                 └─────────┬─────────┘  │
│                                                           │            │
│                                          ┌────────────────┴────────┐   │
│                                          │                         │   │
│                                          ▼                         ▼   │
│                                 ┌─────────────────┐    ┌───────────┐   │
│                                 │ 成功            │    │ 失败      │   │
│                                 │ → 标记completed │    │ → 清除标记│   │
│                                 │ (TTL=24h)       │    │ → Celery  │   │
│                                 └─────────────────┘    │   自动重试│   │
│                                                        └───────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 方案对比总结

| Issue | 问题 | 异步目的 | 是否必须异步 | 修复方案 |
|-------|------|----------|--------------|----------|
| #2959 SSE 持久化 | daemon 线程丢失 | "避免阻塞流式响应" | ❌ 流已结束 | **同步执行** |
| #2960 中断信号 | 缓存 TTL 过期 | N/A | N/A | **双重检查** |
| #2961 外部渠道 | daemon 线程丢失 | **避免 webhook 超时** | ✅ 必须异步 | **Celery + 两阶段去重** |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
issues:
  - https://github.com/TencentBlueKing/bk-lite/issues/2959
  - https://github.com/TencentBlueKing/bk-lite/issues/2960
  - https://github.com/TencentBlueKing/bk-lite/issues/2961
```

## Capability Deltas

### execution-interrupt

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

### external-channel-message

## 问题描述

WeChat/DingTalk 外部渠道采用"先去重标记、立即 ACK、再用 daemon 线程异步处理"的 fire-and-forget 模式，且失败后没有重试或回滚去重标记。只要后台线程未真正完成，外部平台已经停止重试，消息会被永久吞掉。

**影响文件**:
- `server/apps/opspilot/utils/base_chat_flow_utils.py`
- `server/apps/opspilot/utils/wechat_chat_flow_utils.py`
- `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py`
- `server/apps/opspilot/tasks.py` (新增 Celery 任务)

## 为什么必须异步

- WeChat/DingTalk webhook 有超时限制（通常 5 秒）
- ChatFlow 执行可能需要几十秒（LLM 调用、工具执行）
- 同步执行会导致 webhook 超时，平台会重试，导致重复处理

## 为什么用 Celery 而不是 daemon 线程

| 维度 | daemon 线程 | Celery |
|------|-------------|--------|
| 任务持久化 | ❌ 进程退出丢失 | ✅ Redis 持久化 |
| 失败重试 | ❌ 无 | ✅ 自动重试 |
| 监控 | ❌ 无 | ✅ Flower/日志 |
| 资源隔离 | ❌ 占用 Web 进程 | ✅ 独立 Worker |

**项目现状**: opspilot 已有 Celery 任务（`apps/opspilot/tasks.py`），基础设施已就绪。

## 当前实现（问题代码）

### base_chat_flow_utils.py

```python
def is_message_processed(self, msg_id: str) -> bool:
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    if cache.get(cache_key):
        return True
    # 问题：处理前就标记为"已处理"
    cache.set(cache_key, "1", MESSAGE_DEDUP_EXPIRE_SECONDS)
    return False

def process_message_async(self, process_func, *args, **kwargs):
    # 问题：daemon 线程，进程退出时丢失
    thread = threading.Thread(target=process_func, ..., daemon=True)
    thread.start()

def async_process_and_reply(self, ...):
    try:
        # 处理消息
    except Exception as e:
        # 问题：失败只记日志，不清除去重标记
        logger.error(...)
```

## 修复方案：Celery 任务 + 两阶段去重

### 1. 新增 Celery 任务 (`tasks.py`)

```python
from celery import shared_task


def get_bot_chat_flow(bot_id):
    """获取 Bot 的 ChatFlow 配置"""
    from apps.opspilot.models import Bot, BotWorkFlow
    bot = Bot.objects.get(id=bot_id)
    return BotWorkFlow.objects.filter(bot=bot, is_active=True).first()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_wechat_message(self, bot_id, msg_id, message, sender_id, config):
    """处理企业微信消息的 Celery 任务"""
    from apps.opspilot.utils.wechat_chat_flow_utils import WeChatChatFlowUtils
    from apps.core.logger import opspilot_logger as logger

    handler = WeChatChatFlowUtils(bot_id)
    try:
        bot_chat_flow = get_bot_chat_flow(bot_id)
        if not bot_chat_flow:
            logger.error(f"Bot {bot_id} 没有激活的 ChatFlow")
            handler.mark_message_failed(msg_id)
            return

        reply_text = handler.execute_chatflow_with_message(
            bot_chat_flow, config["node_id"], message, sender_id
        )
        handler.send_reply(reply_text, sender_id, config)

        # 成功：标记完成
        handler.mark_message_completed(msg_id)

    except Exception as e:
        logger.error(f"微信消息处理失败，Bot {bot_id}，MsgId {msg_id}，错误: {e}")
        # 失败：清除去重标记，允许重试
        handler.mark_message_failed(msg_id)
        # 触发 Celery 重试
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_dingtalk_message(self, bot_id, msg_id, text_content, sender_id, webhook_url, config):
    """处理钉钉消息的 Celery 任务"""
    from apps.opspilot.utils.dingtalk_chat_flow_utils import DingTalkChatFlowUtils
    from apps.core.logger import opspilot_logger as logger

    handler = DingTalkChatFlowUtils(bot_id)
    try:
        bot_chat_flow = get_bot_chat_flow(bot_id)
        if not bot_chat_flow:
            logger.error(f"Bot {bot_id} 没有激活的 ChatFlow")
            handler.mark_message_failed(msg_id)
            return

        reply_text = handler.execute_chatflow_with_message(
            bot_chat_flow, config["node_id"], text_content, sender_id, is_third_party=True
        )

        if webhook_url and reply_text:
            markdown_content = {"title": "机器人回复", "text": reply_text}
            handler.send_message(webhook_url, "markdown", markdown_content)

        handler.mark_message_completed(msg_id)

    except Exception as e:
        logger.error(f"钉钉消息处理失败，Bot {bot_id}，MsgId {msg_id}，错误: {e}")
        handler.mark_message_failed(msg_id)
        raise self.retry(exc=e)
```

### 2. 修改 base_chat_flow_utils.py

```python
# 常量定义
MESSAGE_PROCESSING_EXPIRE_SECONDS = 300   # 处理中状态 5 分钟超时
MESSAGE_COMPLETED_EXPIRE_SECONDS = 86400  # 已完成状态 24 小时


def is_message_processed(self, msg_id: str) -> bool:
    """检查消息是否已处理（两阶段去重）

    状态：
    - None: 未处理，可以处理
    - "processing": 处理中，跳过（防止并发）
    - "completed": 已完成，跳过
    """
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    status = cache.get(cache_key)

    if status == "completed":
        return True
    if status == "processing":
        return True

    # 标记为处理中（短 TTL，超时后允许重试）
    cache.set(cache_key, "processing", MESSAGE_PROCESSING_EXPIRE_SECONDS)
    return False


def mark_message_completed(self, msg_id: str):
    """标记消息处理完成"""
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    cache.set(cache_key, "completed", MESSAGE_COMPLETED_EXPIRE_SECONDS)


def mark_message_failed(self, msg_id: str):
    """标记消息处理失败，清除去重标记允许重试"""
    cache_key = f"{self.cache_key_prefix}:{self.bot_id}:{msg_id}"
    cache.delete(cache_key)


# 删除 process_message_async 方法（不再使用 daemon 线程）
# 删除 async_process_and_reply 方法（逻辑移到 Celery 任务）
```

### 3. 修改 wechat_chat_flow_utils.py

```python
def handle_wechat_message(self, request, bot_chat_flow, wechat_config):
    """处理企业微信消息"""
    try:
        # ... 解析消息（保持不变）...

        if self.is_message_processed(msg_id):
            return HttpResponse("success")

        # 改用 Celery 任务（替代 daemon 线程）
        from apps.opspilot.tasks import process_wechat_message
        process_wechat_message.delay(
            bot_id=self.bot_id,
            msg_id=msg_id,
            message=message,
            sender_id=sender_id,
            config=wechat_config,
        )

        return HttpResponse("success")

    except Exception as e:
        logger.error(f"企业微信消息处理失败: {e}")
        return HttpResponse("success")
```

### 4. 修改 dingtalk_chat_flow_utils.py

类似修改，使用 `process_dingtalk_message.delay(...)` 替代 daemon 线程。

## 状态转换

```
无状态 → processing (5min TTL) → completed (24h TTL)
                ↓
            失败时清除 → 无状态（允许 Celery 重试或平台重试）
```

## 重试机制

1. **Celery 自动重试**：任务失败后 60 秒自动重试，最多 3 次
2. **处理中超时**：5 分钟后 `processing` 状态自动过期，平台重试时可重新处理
3. **处理失败**：主动清除标记 + Celery 重试
4. **处理成功**：标记为 `completed`，24 小时内不再重复处理

## 测试要点

1. 验证 Celery 任务正确投递和执行
2. 验证处理成功后状态变为 `completed`
3. 验证处理失败后 Celery 自动重试
4. 验证处理超时（>5分钟）后消息可重试
5. 验证并发请求时的去重效果
6. 验证 Celery Worker 重启后任务不丢失
    try:
        node_id = config["node_id"]
        reply_text = self.execute_chatflow_with_message(bot_chat_flow, node_id, message, sender_id)
        self.send_reply(reply_text, sender_id, config)
        # 成功：标记为已完成
        self.mark_message_completed(msg_id)
    except Exception as e:
        logger.error(f"{self.channel_name}异步处理消息失败，Bot {self.bot_id}，MsgId {msg_id}，错误: {str(e)}")
        logger.exception(e)
        # 失败：清除去重标记，允许平台重试
        self.mark_message_failed(msg_id)
```

### dingtalk_chat_flow_utils.py 修复

钉钉有独立的去重实现，需要同步修改：

```python
def _is_message_processed(self, msg_id: str) -> bool:
    """检查消息是否已处理（两阶段去重）"""
    cache_key = f"dingtalk_msg:{self.bot_id}:{msg_id}"
    status = cache.get(cache_key)

    if status == "completed":
        return True
    if status == "processing":
        return True

    cache.set(cache_key, "processing", MESSAGE_PROCESSING_EXPIRE_SECONDS)
    return False

def _mark_message_completed(self, msg_id: str):
    """标记消息处理完成"""
    cache_key = f"dingtalk_msg:{self.bot_id}:{msg_id}"
    cache.set(cache_key, "completed", MESSAGE_COMPLETED_EXPIRE_SECONDS)

def _mark_message_failed(self, msg_id: str):
    """标记消息处理失败"""
    cache_key = f"dingtalk_msg:{self.bot_id}:{msg_id}"
    cache.delete(cache_key)

def _async_process_and_reply(self, ...):
    try:
        # 处理逻辑
        self._mark_message_completed(msg_id)
    except Exception as e:
        logger.error(...)
        self._mark_message_failed(msg_id)
```

## 状态转换

```
无状态 → processing (5min TTL) → completed (24h TTL)
                ↓
            失败时清除 → 无状态（允许重试）
```

## 重试机制

1. **处理中超时**：5 分钟后 `processing` 状态自动过期，平台重试时可重新处理
2. **处理失败**：主动清除标记，平台重试时可重新处理
3. **处理成功**：标记为 `completed`，24 小时内不再重复处理

## 测试要点

1. 验证正常处理流程：processing → completed
2. 验证处理失败后消息可重试
3. 验证处理超时（>5分钟）后消息可重试
4. 验证并发请求时的去重效果
5. 验证 completed 状态的消息被正确跳过

### sse-persistence

## 问题描述

SSE 流式对话的 bot 回复、技能日志与 WorkFlowTaskResult 收尾统一延后到 daemon 线程做 best-effort 持久化，主流程不等待也不兜底。

**影响文件**:
- `server/apps/opspilot/utils/sse_chat.py`
- `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py`

## 当前实现（问题代码）

### sse_chat.py (行 334-339)

```python
if final_stats["content"]:
    def log_in_background():
        _log_and_update_tokens_sync(...)
    # 问题：daemon 线程，进程退出时不等待
    threading.Thread(target=log_in_background, daemon=True).start()
```

### engine.py (行 551-561, 582-590, 616-624)

```python
# 对话历史
threading.Thread(
    target=lambda: self._record_conversation_history(...),
    daemon=True,
).start()

# 执行结果
threading.Thread(
    target=lambda: self._record_execution_result(...),
    daemon=True,
).start()
```

## 修复方案

### 方案：同步执行持久化

将 daemon 线程的持久化操作改为同步执行。流式输出已经完成，此时同步落库不影响用户体验。

### sse_chat.py 修复

```python
async def generate_stream():
    try:
        async for chunk in stream_gen:
            if isinstance(chunk, tuple) and chunk[0] == "STATS":
                _, final_stats["content"] = chunk
                # 修复：同步执行，不再使用 daemon 线程
                if final_stats["content"]:
                    try:
                        _log_and_update_tokens_sync(
                            final_stats, skill_name, skill_id,
                            current_ip, kwargs, user_message,
                            show_think, history_log
                        )
                    except Exception as e:
                        logger.error(f"SSE 持久化失败: {e}", exc_info=True)
                        # 可选：写入补偿队列
            else:
                yield chunk
    except Exception as e:
        logger.error(f"Stream chat error: {e}", exc_info=True)
        # ...
```

### engine.py 修复

```python
# 对话历史 - 同步执行
if accumulated_content:
    try:
        self._record_conversation_history(
            user_id, accumulated_content, "bot",
            entry_type, node_id, session_id,
        )
    except Exception as e:
        logger.error(f"对话历史持久化失败: {e}", exc_info=True)

# 执行结果 - 同步执行
if not next_nodes:
    try:
        self._record_execution_result(
            input_data, final_message, True, start_node_type
        )
    except Exception as e:
        logger.error(f"执行结果持久化失败: {e}", exc_info=True)
```

## 性能影响

- 落库操作通常 <100ms
- 流式输出已完成，用户已看到回复
- 同步落库不影响用户体验
- 可通过监控落库延迟评估影响

## 测试要点

1. 验证流结束后 bot 对话历史正确保存
2. 验证 token 审计日志正确记录
3. 验证 WorkFlowTaskResult 状态正确更新
4. 验证异常场景下的错误日志记录

## Work Checklist

## 1. Issue #2959 - SSE 持久化可靠性

### 1.1 sse_chat.py 修复

- [x] 1.1.1 将 `create_stream_generator()` 中的 daemon 线程持久化改为同步执行
- [x] 1.1.2 在 `_log_and_update_tokens_sync()` 调用前后添加异常处理和日志
- [x] 1.1.3 添加落库失败时的补偿记录（写入错误日志表或文件）

### 1.2 engine.py 修复

- [x] 1.2.1 将 `_record_conversation_history()` 从 daemon 线程改为同步执行
- [x] 1.2.2 将 `_record_execution_result()` 从 daemon 线程改为同步执行
- [x] 1.2.3 评估 `_execute_subsequent_nodes_async()` 是否需要修改（后续节点执行）
  - 结论：保持异步，因为这是执行后续工作流节点，不是持久化
- [x] 1.2.4 添加异常处理，确保落库失败不影响已发送的流式响应

### 1.3 测试

- [ ] 1.3.1 编写单元测试验证持久化在流结束后同步完成
- [ ] 1.3.2 测试异常场景下的补偿机制

---

## 2. Issue #2960 - 中断信号持久化

### 2.1 execution_interrupt.py 修复

- [x] 2.1.1 修改 `is_interrupt_requested()` 增加数据库兜底查询
- [x] 2.1.2 添加缓存未命中时查询 `WorkFlowTaskResult.status == INTERRUPTED` 的逻辑
- [x] 2.1.3 优化查询性能（使用 `exists()` 而非 `filter().first()`）

### 2.2 views.py 确认

- [x] 2.2.1 确认 `interrupt_chat_flow_execution` 已正确更新数据库状态（当前已实现）
- [x] 2.2.2 确保缓存和数据库状态一致性

### 2.3 node.py / engine.py / agui_chat.py 验证

- [x] 2.3.1 验证所有 `is_interrupt_requested()` 调用点都能正确获取中断状态
- [x] 2.3.2 添加日志记录中断检查来源（缓存/数据库）

### 2.4 测试

- [ ] 2.4.1 编写单元测试验证缓存过期后仍能检测到中断
- [ ] 2.4.2 测试长时间运行任务的中断场景

---

## 3. Issue #2961 - 外部渠道消息可靠处理

### 3.1 base_chat_flow_utils.py 修复

- [x] 3.1.1 修改 `is_message_processed()` 实现两阶段去重（processing/completed）
- [x] 3.1.2 添加 `mark_message_completed()` 方法
- [x] 3.1.3 添加 `mark_message_failed()` 方法（清除去重标记）
- [x] 3.1.4 修改 `async_process_and_reply()` 在成功时调用 `mark_message_completed()`
- [x] 3.1.5 修改 `async_process_and_reply()` 在失败时调用 `mark_message_failed()`

### 3.2 wechat_chat_flow_utils.py 修复

- [x] 3.2.1 更新 `handle_wechat_message()` 使用 Celery 任务替代 daemon 线程
- [x] 3.2.2 确保异步处理完成后正确更新去重状态

### 3.3 dingtalk_chat_flow_utils.py 修复

- [x] 3.3.1 修改 `_is_message_processed()` 实现两阶段去重
- [x] 3.3.2 添加 `mark_message_completed()` 和 `mark_message_failed()` 方法
- [x] 3.3.3 删除 `_async_process_and_reply()` 方法（逻辑移到 Celery 任务）
- [x] 3.3.4 更新 `handle_dingtalk_message()` 使用 Celery 任务替代 daemon 线程

### 3.4 tasks.py 新增 Celery 任务

- [x] 3.4.1 添加 `process_wechat_message` Celery 任务
- [x] 3.4.2 添加 `process_dingtalk_message` Celery 任务
- [x] 3.4.3 配置 `max_retries=3, default_retry_delay=60`

### 3.5 测试

- [ ] 3.5.1 编写单元测试验证两阶段去重逻辑
- [ ] 3.5.2 测试处理失败后消息可重试
- [ ] 3.5.3 测试处理超时后消息可重试

---

## 4. 集成测试

- [ ] 4.1 端到端测试 SSE 流式对话的审计日志完整性
- [ ] 4.2 端到端测试长时间任务的中断功能
- [ ] 4.3 端到端测试外部渠道消息的可靠处理（需要模拟 WeChat/DingTalk 回调）

---

## 5. 文档更新

- [ ] 5.1 更新 AGENTS.md 中的 Runbook，添加相关故障排查指南
- [ ] 5.2 添加配置说明（如 `WORKFLOW_INTERRUPT_CACHE_TTL`、去重 TTL 等）
