# Stargazer 指标标签基数治理

Status: phase-1-done

## 背景

Stargazer 当前把部分采集运行身份写入 VictoriaMetrics 标签。运行身份会随每次采集变化，
使同一资源、同一指标在每轮采集后都形成新的 series。Sangfor 已观测到采集周期稳定、发布
无失败，但单项指标在 90 分钟内形成 90 条单点 series，曲线表现为断续。

本变更治理的是指标标签基数，不删除采集协议中的幂等、fencing 或快照身份。指标、运行事件
和配置快照采用不同的承载语义：

- 指标标签只表达稳定资源身份或有限枚举；
- 运行身份保留在 NATS 参数、消息幂等键、采集事件和日志中；
- 配置快照身份及完整对象数据在第二阶段迁往快照载荷，不永久豁免为指标标签。

## 基数不变量

合理的 series 数量只能随资源数、指标数和有限状态数增长：

```text
series ~= resources * metrics * bounded_states
```

不得随采集轮次数增长：

```text
series != resources * metrics * collection_runs
```

标签按以下规则分类：

1. 稳定资源身份可以保留，例如 `instance_id`、`collection_task_id`、
   `collection_target`、`collection_plugin_ref`、`model_id`。
2. 有限枚举可以保留，例如 `collect_status`、`collection_role`、`monitor_type`、
   `event`、`status` 和稳定错误码。
3. 每轮、每次尝试或每次请求变化的身份不得进入指标标签，例如
   `collection_result_id`、`collection_fence`、`run_attempt_id`、
   `collection_run_attempt_id` 和 Host Remote callback `task_id`。
4. 无界正文不得进入指标标签，例如错误正文、响应正文、JSON manifest 和时间戳字符串。

## 第一阶段

### 1. 通用指标标签

从 Prometheus 与 StructuredMetrics 共用的 VictoriaMetrics 标签中删除：

- `collection_result_id`；
- `collection_fence`。

字段仍保留在采集执行和发布参数中，用于：

- Collection lease fencing；
- Host Remote callback 身份校验；
- JetStream 消息幂等；
- 批量发布结果关联和重试去重；
- 采集事件与日志关联。

同一指标仅改变上述运行身份时，编码后的 measurement 与 tag set 必须保持不变；消息 ID
仍必须在同一次结果重发时稳定、不同结果之间不同。

### 2. Host Remote 生命周期指标

`host_remote_state` 删除每次 callback 唯一的 `task_id` 标签，保留有限标签：

- `monitor_type`；
- `event`；
- `status`；
- 当前调用方传入的有限 `reason`。

`task_id` 继续作为 callback 上下文键、发布关联 ID 和日志关联字段，不改变远程采集处理流程。

### 3. CMDB 轮次完成标记

`cmdb_round_complete` 删除：

- `run_attempt_id`；
- `collection_run_attempt_id`。

保留 `instance_id`、`model_id`、`collection_role`、`channel_config_version` 和
`collect_task_id`。完成标记 value 继续使用 `round_ts`；Server 仍以最新 `round_ts` 判断新轮次、
幂等跳过和 pending 重放。

`channel_config_version` 虽不随每轮采集变化，但仍会随配置修改持续产生少量新 series。
第一阶段为保持现有拓扑版本 fencing 暂时保留；第二阶段应将它改为稳定标签 companion metric
的数值，或迁入运行完成事件/记录，最终使完成标记仅包含稳定资源标签和有限
`collection_role`。

旧标记可能仍携带 attempt 标签。Server 查询必须能够同时读取旧、新标记，并按最大
`round_ts` 选择最新轮次；新逻辑不再依赖 attempt 标签。此决定取代
`cmdb-network-topo-collection-split/spec.md` 中把运行 attempt 作为指标标签和完成标记必填字段
的要求。若未来需要按运行身份精确选取拓扑证据，应新增有幂等键的运行完成事件或持久化运行
记录，不得恢复无界指标标签。

### 4. 本阶段不修改快照标签

暂时保留 `snapshot_id`，因为 PC 软件归属、WinSphere manifest 校验和破坏性差集对账依赖
完整快照身份。第一阶段不得为了降低基数而弱化快照完整性或删除安全门。

## 第二阶段：配置快照迁移

`snapshot_id` 每轮变化，不是长期可接受的指标标签。结构化配置采集当前还把对象的全部非空
标量属性编码为 tag；任何版本、容量、状态或描述变化都会形成新 series。因此第二阶段需要
建立配置快照接口，例如：

```text
InventorySnapshotEnvelope
  snapshot_id
  snapshot_status
  snapshot_manifest
  chunk_index / chunk_count
  records[]
```

快照经版本化 NATS 消息或专用暂存存储传输，Server 按 `snapshot_id` 聚合完整批次并在完整性
确认后对账。迁移完成后：

- VictoriaMetrics 只保存数值监控指标和稳定标签；
- `snapshot_id`、manifest 和完整资产属性退出指标标签；
- 各模型使用显式 identity/bounded label 白名单，不再自动把任意标量属性变成 tag。

该阶段涉及跨服务协议和破坏性差集安全，必须支持混合版本、明确发布顺序与回滚路径，并覆盖
完整、部分、重复、乱序和旧版本消息。

## 验证

第一阶段必须覆盖以下行为：

1. 同一业务指标只改变 `collection_result_id`、`collection_fence` 时，series key 不变；
2. 上述字段仍能生成稳定且区分不同结果的 JetStream 消息 ID；
3. `host_remote_state` 不输出 `task_id`，其他有限标签和 callback 返回契约不变；
4. 两个不同 attempt 生成相同的轮次完成 marker series key；
5. Server 能从不带 attempt 标签的新标记选择最新 `round_ts`；
6. Server 能兼容读取保留 attempt 标签的历史标记；
7. PC 与 WinSphere 的现有 `snapshot_id` 契约测试继续通过。

## 上线与回滚

- 可先升级 Server，再升级 Stargazer；Server 同时兼容新旧 marker。
- 旧高基数 series 在保留期内仍存在。查询展示可临时使用
  `without(collection_result_id, collection_fence)` 聚合，不能把查询聚合视为存储治理。
- 新 Stargazer 上线后，新样本进入稳定 series；历史 series 随 VictoriaMetrics 保留期自然过期。
- 代码回滚不涉及数据库迁移，但会重新产生动态标签 series，因此回滚后必须保留基数告警。

## 第一阶段验证证据（2026-08-28）

- Stargazer 标签、NATS 发布、轮次标记与 WinSphere 快照契约：41 passed；
- Stargazer TargetCollectionExecutor 发布流程相关切片：3 passed；
- Server 网络双通道、拓扑重放与轮次守门：32 passed；
- 变更 Python 文件通过 Black 检查、Flake8（150 列）和 `git diff --check`；
- `snapshot_id`、`snapshot_manifest` 及现有配置快照处理未修改。
