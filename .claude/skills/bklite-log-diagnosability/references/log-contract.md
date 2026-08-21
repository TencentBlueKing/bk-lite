# BK-Lite 日志可诊断性契约

## 目录

- [目标](#目标)
- [事件所有权](#事件所有权)
- [日志等级](#日志等级)
- [关键字段](#关键字段)
- [当前格式兼容](#当前格式兼容)
- [异常与降级](#异常与降级)
- [批量与高频路径](#批量与高频路径)
- [安全与容量](#安全与容量)
- [测试契约](#测试契约)
- [判定示例](#判定示例)

## 目标

日志必须帮助值班人员回答：

1. 哪个业务操作失败？
2. 失败发生在哪个阶段、哪个组件、哪个下游？
3. 该操作最终成功、部分成功、降级、跳过还是失败？
4. 是否重试，当前是第几次，是否已经耗尽？
5. Server 与 Stargazer 中哪些记录属于同一次操作？
6. 下一步应检查配置、凭据、网络、插件、执行器、回调还是持久化？

异步操作必须区分两个结果：

- `execution_outcome`：业务执行本身成功、失败、部分成功或降级；
- `delivery_outcome`：结果/指标/回调是否成功送达和持久化。

“成功发送失败结果”只能表示 `execution_outcome=failed`、
`delivery_outcome=success`，不能笼统记录为“任务成功”。

不能回答这些问题的日志数量再多，也不算可诊断。

## 事件所有权

每个操作只设一个终态所有者：最了解业务结果、且决定返回/持久化状态的边界。

| 场景 | 下层 | 终态所有者 |
|---|---|---|
| 下层失败并继续上抛 | 添加异常上下文并 `raise ... from exc`，通常不记 ERROR | 记录一次带 traceback 的 ERROR |
| 下层失败并成功降级 | 返回显式 degraded/partial 结果或抛给拥有者 | 记录一次 WARNING，包含原失败阶段与降级结果 |
| 可重试失败 | 单次尝试记 DEBUG；异常重试可记 WARNING | 重试耗尽后由拥有者记一次 ERROR |
| 批量部分失败 | 单项失败保留在结果明细；必要时 DEBUG | 汇总记一次 WARNING/ERROR，包含成功/失败/跳过计数 |
| 预期输入拒绝 | 返回明确错误，不记 ERROR | HTTP/NATS 边界按需要记低噪声 WARNING 或依赖统一访问日志 |

禁止同一个异常在插件、执行器、服务、NATS handler 和 Server 回调层层打印 ERROR。

## 日志等级

| Level | BK-Lite 语义 | 不应使用 |
|---|---|---|
| DEBUG | 分支选择、缓存命中、插件解析、单项/单次尝试、受控且有界的诊断信息 | 生产必需的唯一失败证据 |
| INFO | 服务启动完成、任务被接收、一次操作的终态成功摘要 | 每个函数开始/结束、循环逐项、装饰分隔线、完整返回值 |
| WARNING | 操作仍可完成但发生重试、降级、部分失败、跳过或可行动的异常状态 | 正常分支、无行动价值的提示 |
| ERROR | 操作终态失败，需要调查或补偿；由终态所有者记录 | 推测性“可能原因”、同一异常多次记录、预期校验失败 |

`CRITICAL` 仅用于进程无法继续且即将退出的启动失败。不要用日志级别代替告警策略。

## 关键字段

优先传播已有业务标识，不要先造新的全局 ID。

### 所有操作

- 稳定事件名或稳定消息模板；变量不能成为模板的一部分。
- `component`：server、stargazer、plugin、executor、callback 等。
- `operation` 或等价稳定事件名。
- `outcome`：success、failed、partial、degraded、skipped、cancelled、timeout。
- `duration_ms`：终态摘要需要；纯配置事件可省略。
- `error_type`、`failed_stage`：失败/降级事件需要。

### 采集与调试链路

尽可能包含：

- `collect_task_id` / `task_id` / `debug_id`；
- `model_id` / `target_model_id`；
- `instance_id`；
- `host` 或经过脱敏的目标标识；
- `plugin_name` / `plugin_source`；
- `executor_type`；
- `subject`；
- `attempt` / `max_attempts`；
- 批量的 `total_count` / `success_count` / `failed_count` / `skipped_count`。

审计时为每个 ID 写清“创建点、语义、传输载体、消费点”。`task_id` 常被不同
组件复用，不能仅按字段同名推断它们属于同一操作。若链路同时存在 worker/job
标识和 `collect_task_id`，终态日志至少保留一个本地执行标识与一个跨 Server ↔
Stargazer 的业务标识。不要生成多个含义相同但名字不同的关联字段。

## 当前格式兼容

Server 当前主要使用 stdlib logging 和文本 formatter。`extra={}` 中的字段只有在 formatter/collector 确实保留时才可查询，不能假设它们已输出。

在未改造 formatter 前，使用稳定模板与有界的 `key=value` 参数：

```python
logger.info(
    "collection.completed task_id=%s model_id=%s outcome=%s duration_ms=%s",
    task_id,
    model_id,
    "success",
    duration_ms,
)
```

如果经静态配置和采集链路验证，JSON/结构化字段会被完整保留，才使用项目统一的结构化字段形式。不要在同一改动中同时替换框架、格式和业务日志，除非用户明确要求该迁移。

消息模板要求：

- 使用稳定事件名，如 `collection.completed`、`nats.request.failed`。
- 参数值使用 logging 的惰性参数，不使用 f-string、拼接或 `.format()`。
- 不依赖 emoji、横线或换行表达状态。
- 不把异常类型、host、task ID 等动态值拼进事件名。

## 异常与降级

### 终态失败

```python
try:
    result = await execute_collection()
except Exception:
    logger.exception(
        "collection.failed task_id=%s model_id=%s failed_stage=%s",
        task_id,
        model_id,
        "plugin_execute",
    )
    raise
```

### 添加上下文但不重复记录

```python
try:
    return client.fetch()
except ClientError:
    raise CollectionTransportError(
        f"collection transport failed for model {model_id}"
    ) from exc
```

### 明确降级

```python
try:
    data = client.fetch()
except ClientError as exc:
    logger.warning(
        "collection.degraded task_id=%s model_id=%s failed_stage=%s outcome=%s",
        task_id,
        model_id,
        "fetch",
        "degraded",
        exc_info=True,
    )
    return CollectionResult.degraded(reason="fetch_failed")
```

只有调用契约明确把空集合视为降级，才能返回 `[]`。否则 `logger.error(...); return []` 会把故障伪装成“没有数据”。

禁止：

- `logger.error(str(exc))` 后返回默认成功值；
- `logger.error(traceback.format_exc())`；
- 记录后 `raise RuntimeError(...)` 且丢失 `from exc`；
- 多条 ERROR 分别写“可能是网络、服务、DNS、防火墙”；
- 捕获 `Exception` 后仅输出异常文本，没有 stack。

## 批量与高频路径

- 循环内逐项成功：默认不记；需要诊断时用 DEBUG。
- 循环内逐项失败：保存在失败列表；高数量时采样前 N 个，终态输出汇总。
- 进度：只在长任务且用户/值班人员需要时记录，按时间或百分比限频。
- 重试：首次或每次失败可用 DEBUG；异常重试和退避策略变化用 WARNING；耗尽用 ERROR。
- 原始 result/response/payload：禁止 INFO；DEBUG 也必须脱敏、截断并确认序列化成本。

推荐终态摘要：

```python
logger.warning(
    "collection.batch_completed task_id=%s outcome=%s total=%d success=%d failed=%d skipped=%d duration_ms=%d",
    task_id,
    "partial",
    total,
    success,
    failed,
    skipped,
    duration_ms,
)
```

## 安全与容量

禁止记录：

- password、token、secret、cookie、authorization、private key；
- 完整 credential/config/request/response/payload/result/kwargs；
- SQL、Shell、Ansible 等命令的完整参数或输出，除非已确认脱敏与长度上界；
- LLM prompt/response、用户上传内容或设备完整配置；
- 可无限增长的集合、堆栈之外的全对象 `repr`。

允许记录“是否存在”而不是值，例如 `token_present=true`。目标地址、用户名、文件路径和对象名称也要按实际数据分类评估，不默认安全。

## 测试契约

日志测试应验证行为而非渲染细节：

- 使用 `caplog` 或 mock logger 捕获 `LogRecord`；
- 断言稳定事件/消息、level、业务 ID、outcome、failed_stage；
- 终态失败断言 `exc_info` 存在；
- 断言同一失败只有一个拥有者 ERROR；
- 断言 secret、password、token、credential 和完整 payload 不出现在消息、args、extra、exc_info 的可序列化内容中；
- 批量路径断言汇总计数，避免断言每项日志；
- 同时断言原返回值、状态转换、回调或重试语义未变。

## 判定示例

| 现象 | 默认判断 | 必须进一步确认 |
|---|---|---|
| f-string 日志 | 候选：模板不稳定、急切求值 | 是否低频、是否当前采集器只索引 message |
| `logger.error` 后 `raise` | 候选：重复 ERROR | 上层是否真的记录；本层是否拥有唯一上下文 |
| `except` 后返回 `[]` | 候选：误导/吞异常 | 空集合是否是明确的降级契约 |
| INFO 在循环内 | 候选：噪声 | 循环上界、调用频率、是否生产必需进度 |
| 完整 data/result | 高风险候选 | 数据大小、凭据/PII、日志级别、截断与脱敏 |
| `logger.exception` | 通常正确 | 是否位于 except 中、是否又被上层重复记录 |
| 健康检查无日志 | 通常正确 | 统一访问日志是否足够；失败是否有独立信号 |
