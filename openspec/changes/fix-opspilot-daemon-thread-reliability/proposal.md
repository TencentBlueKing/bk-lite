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
