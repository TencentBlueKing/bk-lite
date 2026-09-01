# Stargazer 配置采集失败交付与有界日志实施方案

Status: implemented (2026-08-28)

## 1. 背景与结论

配置采集目标失败时，Stargazer 变更前会合成 Prometheus `collection_status` gauge。该数据经
Influx Line Protocol 编码后，由 JetStream `CMDB_METRICS` Stream、Telegraf 和
VictoriaMetrics 落成 `collection_status_gauge`。它只包含弱 `status=error` 与异常类型，不能表达
稳定 `error_code`、失败阶段或安全诊断上下文。

在 5000 个目标中只有数百个可采集的场景，大量失败占位指标会与成功业务指标共同占用：

- `BufferedResultPublisher` 有界队列；
- 指标编码、公平轮转和分块预算；
- JetStream 在途消息/字节窗口与服务端存储；
- Telegraf 消费与 VictoriaMetrics 写入容量。

本次变更删除配置采集失败时合成 `collection_status_gauge` 的实现。失败结果在 Stargazer 内部以
`TargetCollectionResult`、结果事件、Run 汇总和有界日志闭环，不进入指标传输链路。

## 2. 范围

### 2.1 本次实施

1. `plugin_family=configuration` 的 `failed` / `unreachable` 结果不生成指标，不进入
   `publish_metrics_batch_to_nats`；
2. 删除配置采集通用 `collection_status` / `collection_error` 合成逻辑；
3. 失败目标仍记录 credential/result event，扫描进度与凭据状态协议保持不变；
4. 失败结果的指标交付语义为 `not_applicable`，结果事件成功后发布回执仍为确认；
5. 生产默认级别输出有界失败样本和 Run 汇总，不增加 DEBUG 环境开关；
6. 更新与旧行为冲突的规格、README 和自动化测试。

### 2.2 明确不改

- `plugin_family=monitor` 的 `monitor_collection_status`；
- Host Remote 的 `host_remote_state` 和处理失败指标；
- callback / deferred 控制协议；
- 成功业务指标上的 `collect_status=success` 标签；
- round-complete marker；
- JetStream PublishWindow、NATS subject、Telegraf 和 VictoriaMetrics 配置；
- 插件异常 traceback 策略。本次只收口结构化的目标失败结果，异常日志治理另行评估。

## 3. 当前与目标数据流

当前：

```text
TargetCollectionResult(failed/unreachable)
  -> NatsResultPublisher._error_metrics
  -> collection_status gauge
  -> Influx Line Protocol
  -> JetStream PubAck
  -> Telegraf
  -> VictoriaMetrics collection_status_gauge
  -> result event
```

目标：

```text
TargetCollectionResult
  |-- success              -> metrics publisher -> JetStream -> Telegraf -> VM
  |-- failed/unreachable   -> result event only -> bounded Run diagnostics
  `-- callback/deferred    -> existing control protocol
```

行为路由放在 `TargetCollectionResult -> NatsResultPublisher` Seam。通用 NATS/JetStream Adapter 不
识别业务指标名，也不增加末端过滤规则。

## 4. 交付状态契约

配置采集失败不是指标发布失败：

```text
collection_status = failed | unreachable
metrics_delivery = not_applicable
result_event_delivery = confirmed | event_failed
```

现有 `ResultPublisher` Interface 尚未单独暴露 `metrics_delivery`。本次保持调用方兼容：失败目标的
结果事件记录成功后返回 `CONFIRMED`；只有结果事件失败才返回 `EVENT_FAILED`。Run 的
`collection_failed/unreachable` 继续表达业务失败；现有 `publish_succeeded` 表达整个结果交付已确认，
因此 event-only 结果也会计入，但不会增加 NATS 指标行数或 JetStream 指标发布成功/失败计数。

一个失败目标不得因没有指标消息而进入重试，也不得被计为 NATS/JetStream 发布成功或失败。

## 5. 日志契约

不增加 `STARGAZER_LOG_LEVEL`，也不要求 Docker 开启 Sanic `--debug`。

### 5.1 默认可见且有界

- `collection_run_started`：INFO；
- `collection_progress`：INFO，约每 10% 一条，保持现有上界；
- `collection_failure_samples`：INFO，每个 Run 最多一条，最多 3 个样本；
- `collection_run_summary`：存在业务失败时 WARNING，否则 INFO；
- `collection_run_terminal`：INFO；
- 真正的框架、Redis、结果事件或 JetStream 故障：保留现有 WARNING/ERROR 所有权。

不再为每个 `failed/unreachable` 输出 `target_collection_failed` WARNING/INFO。

### 5.2 样本与汇总上界

失败样本只包含：

```text
target | failed_stage | error_code
```

样本总数最多 3。不得记录 `result.detail`、payload、响应正文、凭据正文或无界目标列表。

失败类型按数量降序、错误码升序输出 Top 8；其余合并为 `other:<count>`。因此日志长度不随目标数
或错误码种类无界增长。

## 6. 兼容性与发布

- 新 Stargazer -> 旧 Server：Server 本来就会过滤失败 VM 行；不再产生该行不会改变成功快照计算；
- 旧 Stargazer -> 新 Server：旧失败行仍可被现有过滤逻辑忽略；
- 扫描进度：继续使用 credential/result event，不依赖 VM 失败行；
- 回滚：回滚到上一 Stargazer 镜像即可恢复旧失败指标，不需要数据库或 Stream 迁移；
- 历史 `collection_status_gauge` 时序不删除，按 VictoriaMetrics 保留策略自然过期。

## 7. TDD Seam 与验收

### 7.1 ResultPublisher Seam

1. 混合 1 个成功、多个配置失败时，指标 Adapter 只收到成功结果；
2. 配置失败/不可达仍各记录一个结果事件；
3. 失败结果事件成功时回执确认，事件失败时返回 `EVENT_FAILED`；
4. monitor 失败仍生成 `monitor_collection_status`，避免扩大范围；
5. callback/deferred 行为保持不变；
6. 配置采集服务异常返回结构化失败，不再构造通用 `collection_status` 文本。

### 7.2 CollectionRun Seam

1. 25 个或 5000 个同类失败不产生逐目标失败日志；
2. 每个 Run 最多一条 `collection_failure_samples` INFO，样本最多 3；
3. `collection_run_summary` 的失败类型最多 Top 8 + `other`；
4. 完整格式化日志不包含 `result.detail` 或敏感哨兵；
5. RunSummary、采集状态、凭据尝试、结果事件和发布错误状态保持原契约。

## 8. 实施顺序

1. 先新增 ResultPublisher 和 CollectionRun 行为测试并确认红灯；
2. 在 `NatsResultPublisher` 路由配置失败为 event-only；
3. 删除 `generate_plugin_error_metrics` 与配置采集旧错误指标生成；
4. 将逐目标失败日志收口到 Executor 的有界样本和汇总；
5. 更新规格、README 和旧测试；
6. 运行定向测试、覆盖率和 Stargazer lint。

## 9. 实施与验证记录

已按上述顺序完成：

- `NatsResultPublisher` 将配置采集 `failed/unreachable` 路由为 result event-only；
- 删除配置采集通用 `collection_status` / `collection_error` 指标生成函数；
- `CollectionService` 运行时异常返回空数据加结构化错误，不再生成失败指标文本；
- 删除逐目标失败日志，增加每 Run 一条、最多 3 个样本的 INFO 日志；
- Run 汇总失败类型限制为 Top 8，其余合并为 `other`；
- monitor、WinSphere、callback/deferred 和 round-complete 契约保持原路径。

验证结果：

- 定向回归：87 passed；
- 其中两条 150/256 目标全失败压测确认指标发布数为 0，Run 正常收口；
- Black 检查、Flake8（沿用项目 Black 兼容的 `E501/W503` 忽略）和 `git diff --check` 通过；
- 当前虚拟环境未安装 `pytest-cov/coverage`，无法生成覆盖率报告；
- 当前 shell 直接执行 `make lint` 时找不到 `pre-commit` 命令；提交阶段仓库 hook 使用已安装环境完成
  pyupgrade、Black、isort、Flake8、迁移检查和依赖检查，全部通过；
- 首次 `pytest tests -q` 结果为 958 passed、6 skipped、71 failed；其中两条是本次行为变化导致的旧压测
  断言，更新后已通过；其余 69 条来自当前分支既有的缺失旧模块、过期 fixture/配置契约，与本变更
  文件无交集。
