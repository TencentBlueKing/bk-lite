# Stargazer NATS 发布失败日志所有权

关联 Issue：#4959

## 目标

同一次 callback 或 credential-result NATS 发布失败只产生一条带真实 traceback 的稳定 ERROR，并由知道采集运行与业务阶段的语义 helper 持有。

## 行为契约

1. `nats_publish` 继续按原顺序获取共享 control 连接、JSON 编码、publish 和 flush；任一步失败时原样抛出，不在传输层重复记录 ERROR。
2. `publish_callback_to_nats` 发布失败时记录一次 `event=callback_publish_failed`，包含 `task_id`、`subject`、`failed_stage=callback_publish` 和 `error_type`，并保留真实 `exc_info`。
3. `publish_credential_result_to_nats` 发布失败时记录一次 `event=credential_result_publish_failed`，包含同类关联字段和 `failed_stage=credential_result_publish`，并保留真实 `exc_info`。
4. 两个 helper 均继续原样抛出异常；不改变 subject、payload、返回值或调用次数。
5. Executor 的 `result_publish_failed` 限量 WARNING 和 Collection Run 汇总保持不变。

## 安全与容量

- ERROR 不记录 payload、采集结果、凭据、token 或异常消息；
- 只记录既有内部 task ID、NATS subject、稳定阶段和异常类型；
- 不把 traceback 手工拼入 message，由日志框架通过 `exc_info` 输出。

## 测试契约

- 从公开 callback helper 注入真实低层 publish 失败，断言只有一条 ERROR、字段稳定、有真实 `exc_info` 且异常传播；
- credential-result helper 使用同样的失败边界和断言；
- 保留现有发布器、Executor、凭据推送和 NATS 分通道测试。

## 排除范围

- `nats_request`、指标逐行发布、连接事件日志；
- NATS 重连、重试、超时、subject、payload 和序列化；
- Server 回调和任务状态机。
