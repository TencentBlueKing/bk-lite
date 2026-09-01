# Stargazer 指标标签基数治理

Status: phase-1-done-phase-2-implemented-awaiting-deployment-validation

## 背景

Stargazer 当前把部分采集运行身份写入 VictoriaMetrics 标签。运行身份会随每次采集变化，
使同一资源、同一指标在每轮采集后都形成新的 series。Sangfor 已观测到采集周期稳定、发布
无失败，但单项指标在 90 分钟内形成 90 条单点 series，曲线表现为断续。

本变更治理的是指标标签基数，不删除采集协议中的幂等、fencing 或快照身份。指标、运行事件
和配置快照采用不同的承载语义：

- 指标标签只表达稳定资源身份或有限枚举；
- 运行身份保留在 NATS 参数、消息幂等键、采集事件和日志中；
- 配置快照身份和完整性元数据在第二阶段迁往 Redis + NATS 旁路；完整资产行继续存于 VM。

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

## 第二阶段：PC/WinSphere 快照元数据迁移

本阶段详细实施方案见
[`metric-label-cardinality-phase-2-design.md`](metric-label-cardinality-phase-2-design.md)。已实施方案不迁移
完整资产数据：PC/WinSphere 资产行继续保留在 VictoriaMetrics，仅把 `snapshot_id`、status、count
和 WinSphere manifest 等小型轮次元数据写入 Stargazer 自身 Redis，并由 CMDB 通过 NATS 精确查询。
CMDB 不直接连接 Stargazer Redis，也不要求两个服务共享 Redis。

`snapshot_id` 每轮变化，不是长期可接受的指标标签。结构化配置采集当前还把对象的全部非空
标量属性编码为 tag；任何版本、容量、状态或描述变化都会形成新 series。本阶段只治理以下快照标签：

```text
PC: snapshot_id / software_snapshot_status / software_expected_count / software_error_count
PC software: snapshot_id
WinSphere: snapshot_id / snapshot_status / snapshot_manifest
```

完整资产行继续由 VM 承载，并以同一目标结果共享的 sample timestamp 归属轮次；Server 取得小型元数据并
验证完整性后才允许差集删除。迁移完成后：

- 上述 snapshot 元数据退出指标标签；
- PC 软件清单和 WinSphere 八模型资产行仍保留在 VictoriaMetrics；
- 元数据缺失、过期、RPC 失败、计数或 hash 不一致时 fail closed，不删除资产且不前移轮次游标。

VMware `uptime_seconds`、其他动态业务属性以及 `0`/`False` 数据正确性问题不并入本次实施，后续独立治理。
本次功能当前无使用方，采用暂停相关任务后的硬切换，不双写、不双读、不回填历史数据；发布和回滚步骤
见详细实施文档。

## 验证

第一阶段必须覆盖以下行为：

1. 同一业务指标只改变 `collection_result_id`、`collection_fence` 时，series key 不变；
2. 上述字段仍能生成稳定且区分不同结果的 JetStream 消息 ID；
3. `host_remote_state` 不输出 `task_id`，其他有限标签和 callback 返回契约不变；
4. 两个不同 attempt 生成相同的轮次完成 marker series key；
5. Server 能从不带 attempt 标签的新标记选择最新 `round_ts`；
6. Server 能兼容读取保留 attempt 标签的历史标记；
7. PC 与 WinSphere 的 snapshot 完整性契约改由轮次元数据测试锁定，VM 行不再包含 snapshot 标签。

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

## 第二阶段代码验证（2026-08-31）

- PC/WinSphere snapshot 标签已从新生成的 VM 资产行移除；
- 快照控制元数据已迁入 Stargazer Redis，Server 通过 NATS 完整键批量查询；
- PC 和 WinSphere 在元数据缺失、超时或完整性错误时，均在图对账副作用前 fail closed；
- 企业版 Stargazer 权威源已同步生产者改动，WinSphere 已对齐异步 Collector 合同和结构化
  `winsphere_*_info` 指标名；
- 跨仓库完整流程已覆盖 PC 三轮安全删除和 WinSphere 八模型连续两轮 series 稳定；
- 代码定向测试已通过，生产灰度、VM series 数和 Redis/NATS 运行指标仍需按详细实施文档验收。
