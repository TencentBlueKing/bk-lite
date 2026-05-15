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
# 问题：daemon 线程，进程退出时不等待
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
