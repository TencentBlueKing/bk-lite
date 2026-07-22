# 修复渠道消息去重竞态条件和微信公众号异步处理缺失

Status: done

## Migration Context

- Legacy source: `openspec/changes/fix-channel-message-dedup-and-async/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-21
```

## Work Checklist

## Phase 1: 钉钉消息去重修复 (Issue #3090)

### 1.1 重构 DingTalkChatFlowUtils 继承基类
- [x] **Task 1.1.1**: 修改 `DingTalkChatFlowUtils` 继承 `BaseChatFlowUtils`
  - 文件: `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py`
  - 添加 `from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils`
  - 修改类定义: `class DingTalkChatFlowUtils(BaseChatFlowUtils):`
  - 设置类属性:
    ```python
    channel_name = "钉钉"
    channel_code = "dingtalk"
    cache_key_prefix = "dingtalk_msg"
    ```

- [x] **Task 1.1.2**: 删除重复的去重方法
  - 文件: `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py`
  - 删除 `is_message_processed()` 方法 (约第 250-274 行)
  - 删除 `mark_message_completed()` 方法 (约第 276-284 行)
  - 删除 `mark_message_failed()` 方法 (约第 286-294 行)
  - 这些方法将从基类继承，使用原子操作 `cache.add()`

- [x] **Task 1.1.3**: 实现 `send_reply()` 抽象方法
  - 文件: `server/apps/opspilot/utils/dingtalk_chat_flow_utils.py`
  - 添加方法实现，封装现有的钉钉消息发送逻辑
  - 参考 `WechatOfficialChatFlowUtils.send_reply()` 的签名

- [x] **Task 1.1.4**: 更新 `handle_dingtalk_message()` 方法
  - 确保调用基类的 `is_message_processed()` 方法
  - 验证 cache_key 格式保持兼容: `dingtalk_msg:{bot_id}:{msg_id}`

### 1.2 验证钉钉修复
- [x] **Task 1.2.1**: 运行现有钉钉相关测试
  - 命令: `cd server && make test` (过滤钉钉相关测试)
  - 确保所有现有测试通过

- [x] **Task 1.2.2**: 添加竞态条件测试
  - 文件: `server/apps/opspilot/tests/react_agent/cases/test_external_channel_message_dedup.py`
  - 添加测试用例验证 `cache.add()` 原子操作
  - 模拟并发场景，确保只有一个 worker 获取处理权

---

## Phase 2: 微信公众号异步处理修复 (Issue #3091)

### 2.1 添加 Celery 任务
- [x] **Task 2.1.1**: 添加 `process_wechat_official_message` Celery 任务
  - 文件: `server/apps/opspilot/tasks.py`
  - 参考 `process_wechat_message` 任务实现
  - 任务签名:
    ```python
    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def process_wechat_official_message(self, bot_id, msg_id, message, sender_id, config):
        """处理微信公众号消息的 Celery 任务"""
    ```
  - 内部调用 `WechatOfficialChatFlowUtils` 的 `async_process_and_reply()` 方法

### 2.2 修复 WechatOfficialChatFlowUtils
- [x] **Task 2.2.1**: 修改 `handle_wechat_message()` 方法
  - 文件: `server/apps/opspilot/utils/wechat_official_chat_flow_utils.py`
  - 删除对不存在的 `process_message_async()` 的调用 (第 243-250 行)
  - 替换为:
    ```python
    from apps.opspilot.tasks import process_wechat_official_message
    process_wechat_official_message.delay(
        self.bot_id,
        msg_id,
        message,
        openid,
        wechat_config,
    )
    ```

- [x] **Task 2.2.2**: 验证 `WechatOfficialChatFlowUtils` 继承关系
  - 确保正确继承 `BaseChatFlowUtils`
  - 确保 `send_reply()` 方法已实现
  - 确保类属性已设置:
    ```python
    channel_name = "微信公众号"
    channel_code = "wechat_official_account"
    cache_key_prefix = "wechat_official_msg"
    ```

### 2.3 验证微信公众号修复
- [x] **Task 2.3.1**: 添加微信公众号消息处理测试
  - 文件: `server/apps/opspilot/tests/react_agent/cases/test_wechat_official_message.py` (新建)
  - 测试 Celery 任务正确触发
  - 测试消息去重逻辑
  - 测试失败重试机制

- [x] **Task 2.3.2**: 运行完整测试套件
  - 命令: `cd server && make test`
  - 结果: 158 passed, 1 failed (pre-existing failure in test_approval.py unrelated to our changes)
  - 64 dedup-specific tests all passed

---

## Phase 3: 集成验证

- [x] **Task 3.1**: 代码审查
  - LSP diagnostics: All errors are pre-existing Django ORM type issues (Pyright doesn't understand Django's `objects` manager)
  - No new errors introduced by our changes
  - Python syntax validation passed for all modified files

- [x] **Task 3.2**: 文档更新
  - No documentation changes needed - the fix is internal implementation detail
  - The channel message handling mechanism remains the same from user perspective

- [x] **Task 3.3**: 最终验证
  - `lsp_diagnostics`: No new errors (all errors are pre-existing Django ORM type issues)
  - Tests: 158 passed, 1 pre-existing failure unrelated to changes
  - Dedup tests: All 64 tests passed
  - Python syntax: All modified files pass `py_compile` validation

---

## 任务依赖关系

```
Phase 1 (钉钉)          Phase 2 (微信公众号)
    │                        │
    ├─ 1.1.1 ──┐             ├─ 2.1.1 ──┐
    ├─ 1.1.2 ──┼─ 1.1.4      ├─ 2.2.1 ──┼─ 2.2.2
    └─ 1.1.3 ──┘             └──────────┘
         │                        │
         ▼                        ▼
      1.2.1                    2.3.1
         │                        │
         ▼                        ▼
      1.2.2                    2.3.2
         │                        │
         └────────────┬───────────┘
                      ▼
                 Phase 3
                 (集成验证)
```

## 预估工时

| Phase | 任务数 | 预估时间 |
|-------|--------|---------|
| Phase 1 | 6 | 2-3 小时 |
| Phase 2 | 5 | 2-3 小时 |
| Phase 3 | 3 | 1 小时 |
| **总计** | **14** | **5-7 小时** |
