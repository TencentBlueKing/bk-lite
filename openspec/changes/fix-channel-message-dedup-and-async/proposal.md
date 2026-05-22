# 修复渠道消息去重竞态条件和微信公众号异步处理缺失

## 背景

GitHub Issues:
- [#3090](https://github.com/TencentBlueKing/bk-lite/issues/3090): 钉钉消息去重使用非原子 get/set，可能导致同一工作流重复执行
- [#3091](https://github.com/TencentBlueKing/bk-lite/issues/3091): 微信公众号入口调用不存在的异步处理函数，可能导致渠道消息全部静默丢失

## 问题分析

### Issue #3090: 钉钉消息去重竞态条件

**现状**：`dingtalk_chat_flow_utils.py` 的 `is_message_processed()` 方法使用非原子的 get/set 操作：

```python
status = cache.get(cache_key)      # 先读
if status == "completed":
    return True
if status == "processing":
    return True
cache.set(cache_key, "processing", ...)  # 后写
return False
```

**问题**：在高并发场景下，两个 worker 可能同时读取到 `None`，然后都设置为 `processing`，导致同一消息被处理两次。

```
Worker A: cache.get() → None
Worker B: cache.get() → None  (在 A 的 set 之前)
Worker A: cache.set("processing")
Worker B: cache.set("processing")  (覆盖 A 的设置)
→ 两个 worker 都开始处理同一消息
```

**对比**：基类 `BaseChatFlowUtils` 已经使用原子操作 `cache.add()` 修复了这个问题，但钉钉的实现没有继承基类的方法。

### Issue #3091: 微信公众号异步处理函数缺失

**现状**：`wechat_official_chat_flow_utils.py` 第 243 行调用了不存在的方法：

```python
self.process_message_async(
    self.async_process_and_reply,
    bot_chat_flow,
    wechat_config,
    message,
    openid,
    msg_id,
)
```

**问题**：`process_message_async` 方法在基类 `BaseChatFlowUtils` 中不存在，调用时会抛出 `AttributeError`，但被外层 `except Exception` 捕获后静默返回 `"success"`，导致所有微信公众号消息丢失。

**对比**：企业微信和钉钉都使用 Celery 任务：
- `process_wechat_message.delay(...)` - 企业微信
- `process_dingtalk_message.delay(...)` - 钉钉

微信公众号缺少对应的 `process_wechat_official_message` Celery 任务。

## 修复方案

### 方案 1: 钉钉去重修复

让 `DingTalkChatFlowUtils` 继承 `BaseChatFlowUtils`，复用已修复的原子去重逻辑。

**改动点**：
1. `DingTalkChatFlowUtils` 继承 `BaseChatFlowUtils`
2. 删除重复的 `is_message_processed`、`mark_message_completed`、`mark_message_failed` 方法
3. 设置正确的 `cache_key_prefix = "dingtalk_msg"`
4. 实现抽象方法 `send_reply()`

### 方案 2: 微信公众号异步处理修复

为微信公众号添加 Celery 任务，与企业微信和钉钉保持一致。

**改动点**：
1. 在 `tasks.py` 中添加 `process_wechat_official_message` Celery 任务
2. 修改 `wechat_official_chat_flow_utils.py`，将 `process_message_async()` 调用改为 `process_wechat_official_message.delay()`
3. 确保 `WechatOfficialChatFlowUtils` 正确继承 `BaseChatFlowUtils` 并实现所有抽象方法

## 影响范围

- `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py`
- `server/apps/opspilot/utils/wechat_official_chat_flow_utils.py`
- `server/apps/opspilot/tasks.py`
- `server/apps/opspilot/tests/` (新增测试)

## 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 修改后影响现有钉钉消息处理 | 低 | 保持 cache_key 格式不变，确保向后兼容 |
| Celery 任务参数不匹配 | 低 | 参考现有 `process_wechat_message` 任务实现 |
| 测试覆盖不足 | 中 | 添加单元测试验证原子去重和异步处理 |

## 验收标准

1. 钉钉消息去重使用原子操作 `cache.add()`
2. 微信公众号消息能正确触发 Celery 任务处理
3. 所有现有测试通过
4. 新增测试覆盖竞态条件场景
