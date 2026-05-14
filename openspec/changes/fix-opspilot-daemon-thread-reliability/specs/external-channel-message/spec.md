# 外部渠道消息可靠处理修复

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
