# Historical Superpowers change: 2026-07-16-log-alert-center-nats-event

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-16-log-alert-center-nats-event-design.md

- 日期：2026-07-16
- 状态：已确认
- 范围：日志中心、系统管理通知渠道、告警中心 NATS 接入

## 结论

日志中心复刻监控中心向告警中心推送 Event 的协议与可靠投递原则，但保持日志中心现有数据模型不变：不新增字段、不新增数据表、不生成 migration。

日志告警产生或级别变化时，复用现有 `Event.notified`、`Event.notice_retry_count` 和 `Event.notice_result` 完成持久化补偿；日志告警手动关闭时，复用现有 `Alert.status`、`Alert.end_event_time` 和 `Alert.notice` 表达关闭状态、稳定关闭时间和最近一次生命周期通知结果。

通知渠道与通知人继续实时读取当前 `Policy.notice_type_id`、`Policy.notice_type` 和 `Policy.notice_users`。这与日志告警列表和详情页当前展示语义一致，不引入历史配置快照。

## 背景与现状

### 监控中心现有链路

监控中心由 `AlertLifecycleNotifier` 识别指向 `receive_alert_events` 的 NATS 通道，构造标准 Event envelope 后通过 `SystemMgmtUtils.send_msg_with_channel` 发往告警中心：

```text
MonitorAlert 生命周期变化
  -> AlertLifecycleNotifier
  -> SystemMgmt NATS Channel
  -> receive_alert_events
  -> AlertSourceAdapter
  -> 告警中心 Event 入库与聚合
```

消息 envelope 为：

```json
{
  "source_id": "nats",
  "pusher": "lite-monitor",
  "events": []
}
```

系统管理已将 `method_name=receive_alert_events` 列入 NATS 原样透传方法，不会执行面向 IM 工作流的 `message/team/user_ids` 格式转换。

### 日志中心现有链路

日志策略扫描会创建或更新本地 `Alert` 和 `Event`，随后由 `LogPolicyScan.notice()` 发送通知：

```text
日志检测
  -> Log Alert / Log Event 入库
  -> send_notice()
  -> 所有渠道统一接收文本 title/content
```

这对邮件、企微、飞书等普通渠道有效，但与告警中心 NATS 通道要求的字典 payload 不兼容，因而无法向 `receive_alert_events` 传递标准 Event。

现有模型已经提供本设计需要的状态：

- `Policy.notice`：是否启用通知。
- `Policy.notice_type_id` / `notice_type`：当前通知渠道。
- `Policy.notice_users`：当前通知人；NATS 告警中心通道不要求通知人。
- `PolicyOrganization.organization`：策略归属组织。
- `Alert.notice`：最近一次显著告警变化是否通知成功。级别变化时现有代码已经将其重置为 `False`。
- `Alert.start_event_time` / `end_event_time`：告警开始时间和最新事件/关闭时间。
- `Event.notified` / `notice_retry_count` / `notice_result`：事件通知状态、次数和结果。

告警页面的通知人由 `AlertSerializer` 通过 `policy.notice_users` 实时返回，通知状态直接读取 `Alert.notice`。因此本设计不需要在 `Alert` 上冗余通知配置。

## 目标

1. 日志告警首次产生时向告警中心传递标准 `created` Event。
2. 活跃日志告警级别变化时，以同一 `external_id` 传递新的 `created` Event。
3. 日志告警手动关闭时向告警中心传递 `closed` Event。
4. 普通通知渠道保持现有文本通知行为。
5. 复用现有状态实现首次投递、失败重试、幂等和关闭补偿。
6. `lite-log` 作为明确的可信内部推送方，仍受告警源组织白名单约束。
7. 不改变日志中心数据库结构和页面数据契约。

## 非目标

- 不增加日志告警自动恢复语义，不发送 `recovery` Event。
- 不为日志告警保存通知渠道或通知人的历史快照。
- 不新增关闭通知的独立重试次数、失败原因字段或通知审计表。
- 不抽取监控和日志共用的跨模块通知框架。
- 不改变告警中心现有 Event 模型、聚合规则或恢复处理模型。
- 不调整邮件、企微、飞书、钉钉和自定义 Webhook 的正文模板。

## 设计原则

### 独立实现，协议对齐

日志中心新增独立的生命周期通知服务，例如 `LogAlertLifecycleNotifier`。它复用监控中心的 Event 契约、渠道识别方式、级别映射和结果解析原则，但不直接依赖监控模块业务类，也不重构已经运行的监控链路。

### 当前策略配置即有效配置

发送时读取关联 Policy 的当前通知配置：

- 当前渠道为告警中心 NATS 通道时发送标准 Event。
- 当前渠道为普通通知渠道时沿用现有文本通知。
- 策略在告警生命周期内修改渠道或通知人后，后续通知使用修改后的配置。

这一语义与当前日志告警页面展示当前 Policy 通知人的行为一致。

### 本地状态先落库，外部发送后执行

任何 NATS 发送都不得放在持有数据库事务的过程中。状态先提交，再通过 `transaction.on_commit` 或事务外调用触发发送，避免数据库回滚但告警中心已经收到 Event。

## 总体架构

```text
                         +----------------------+
                         | 当前 Log Policy      |
                         | channel/users/orgs   |
                         +----------+-----------+
                                    |
                                    v
+------------------+      +----------------------+      +----------------------+
| LogPolicyScan    |----->| LogAlertLifecycle   |----->| SystemMgmt NATS      |
| AlertViewSet     |      | Notifier            |      | Channel              |
+--------+---------+      +----------+-----------+      +----------+-----------+
         |                           |                             |
         |                           | standard Event envelope     |
         v                           v                             v
+------------------+      +----------------------+      +----------------------+
| Log Alert/Event  |      | 本地通知状态/补偿    |      | receive_alert_events |
| 现有字段         |      | 现有字段             |      | AlertSourceAdapter   |
+------------------+      +----------------------+      +----------+-----------+
                                                                  |
                                                                  v
                                                       +----------------------+
                                                       | 告警中心 Event/Alert |
                                                       +----------------------+
```

## 组件设计

### LogAlertLifecycleNotifier

该服务只承担以下职责：

1. 判断当前渠道是否为告警中心通道：`channel_type=nats` 且 `config.method_name=receive_alert_events`。
2. 从 Log Event 或 Log Alert 构造标准 Event。
3. 从 `PolicyOrganization` 读取组织列表。
4. 通过 `SystemMgmtUtils.send_msg_with_channel` 发送 envelope。
5. 将不同下游响应归一化为成功或失败及精简原因。

建议提供两个明确入口：

```python
notify_created(event)
notify_closed(alert)
```

服务不直接创建或修改 Log Alert/Event，不负责策略扫描，也不拥有定时任务。

### 渠道分流

现有 `send_notice()` 在发送前区分渠道：

```text
告警中心 NATS 通道
  -> 构造 Event dict
  -> receivers=[]
  -> 原样透传 receive_alert_events

其他渠道
  -> 保留现有 title/content 文本
  -> 保留现有 notice_users
```

NATS 告警中心通道不得因为 `Policy.notice_users` 为空而提前返回。普通渠道仍遵守现有通知人校验。

## Event 契约

### Envelope

```json
{
  "source_id": "nats",
  "pusher": "lite-log",
  "events": [
    {
      "external_id": "<log-alert-id>",
      "rule_id": "<log-policy-id>",
      "title": "<rendered-alert-name>",
      "description": "<log-alert-content>",
      "level": "2",
      "value": 12,
      "action": "created",
      "start_time": "1784188800",
      "end_time": null,
      "resource_id": "policy_12_host_abcd",
      "resource_type": "log_alert",
      "resource_name": "nginx",
      "organizations": [3],
      "tags": {},
      "labels": {
        "policy_name": "Nginx 错误日志",
        "alert_type": "keyword",
        "collect_type_id": "8",
        "log_alert_id": "abc123",
        "status": "new"
      }
    }
  ]
}
```

### 字段映射

| 告警中心字段 | `created` 来源 | `closed` 来源 |
|---|---|---|
| `external_id` | `event.alert_id` | `alert.id` |
| `rule_id` | `event.policy_id` | `alert.policy_id` |
| `title` | `event.content`，空时使用 `policy.alert_name` | `alert.content`，空时使用 `policy.alert_name` |
| `description` | `event.content` | `alert.content` |
| `level` | `event.level` 经过统一映射 | `alert.level` 经过统一映射 |
| `value` | `event.value` | `alert.value` |
| `action` | `created` | `closed` |
| `start_time` | `event.event_time` | `alert.end_event_time` |
| `end_time` | 空 | `alert.end_event_time` |
| `resource_id` | `event.source_id` | `alert.source_id` |
| `resource_type` | `log_alert` | `log_alert` |
| `resource_name` | 采集类型名称，空时使用策略名称 | 采集类型名称，空时使用策略名称 |
| `organizations` | `PolicyOrganization.organization` | `PolicyOrganization.organization` |
| `tags` | 可安全提取的日志分组维度；无法取得时为空 | 空字典 |
| `labels` | 策略、告警类型、采集类型、Log Alert ID、状态 | 在 created labels 基础上增加操作人和关闭原因（若有） |

级别映射与监控中心一致：

| 日志级别 | 告警中心级别 |
|---|---|
| `critical` | `0` |
| `error` | `1` |
| `warning` | `2` |
| `info` | `3` |

`info` 事件继续遵守日志中心现有逻辑，不主动通知。

### 幂等

告警中心接入幂等键由以下字段组成：

```text
source_id + push_source_id + external_id + action + start_time
```

本设计保证：

- 首次产生和失败重试使用同一 Log Event 的 `event_time`，幂等键稳定。
- 级别变化创建新的 Log Event，`external_id` 不变但 `start_time` 不同，因此能产生新的告警中心 Event。
- 关闭时先把实际关闭时间写入 `Alert.end_event_time`，所有关闭重试复用该时间。
- 重复关闭同一个已关闭 Alert 不重新生成关闭时间，也不产生新的生命周期 Event。

## 生命周期流程

### 首次产生

1. 策略扫描检测到异常。
2. 按现有逻辑创建 Log Alert 和 Log Event。
3. 数据库提交后执行通知。
4. 若当前渠道是告警中心 NATS 通道，构造 `created` Event。
5. 成功后设置 `Event.notified=True`、保存精简 `notice_result`，并设置 `Alert.notice=True`。
6. 失败后保留 `Event.notified=False`，累计 `notice_retry_count`，由现有补偿任务重投。

### 级别变化

1. 现有活跃 Alert 的 level 发生变化。
2. 现有逻辑将 `Alert.notice=False` 并创建新的 Log Event。
3. 新 Log Event 以 `action=created`、新的 `event_time` 发送。
4. 成功与失败处理复用首次产生流程。

告警中心没有 `updated` EventAction，因此级别变化使用新的 `created` Event。这与监控中心当前将 upgraded 映射为 created 的行为一致。

### 持续命中但级别未变化

继续使用现有 `Alert.notice` 去重：新的 Log Event 标记为已结清但不重复发送，避免每个扫描周期产生通知。

### 手动关闭

当前前端列表和详情均通过 `PATCH /log/alert/{id}/`、`status=closed` 关闭告警，而不是调用自定义 `closed` action。因此生命周期接入点必须覆盖 `AlertViewSet.partial_update()` 的真实状态转换。

关闭流程：

1. 读取数据库中的旧状态并执行现有告警操作权限校验。
2. 仅当状态从 `new` 转为 `closed` 时进入关闭流程。
3. 在同一事务内设置：
   - `status=closed`
   - `operator=request.user.username`
   - `end_event_time=timezone.now()`
   - `notice=False`
4. 提交事务。
5. 在 `transaction.on_commit` 后向告警中心发送 `closed` Event。
6. 成功后以条件更新方式将 `Alert.notice=True`；失败时保持 `False`，等待关闭补偿。
7. 已关闭 Alert 再次收到关闭请求时幂等返回，不重写 `end_event_time`，不重复发送。

自定义 `closed` action 如果继续保留，必须复用同一关闭服务，避免形成两套状态转换和通知逻辑。

## 补偿与并发

### created 补偿

保留现有 Event 补偿机制：按时间窗口查询 `Event.notified=False` 且重试未超限的记录，使用原 Event 重建相同 payload。

需要收紧成功回写：只有关联 Alert 仍为 `new` 时，created 补偿成功才设置 `Alert.notice=True`。这样旧 created Event 的迟到补偿不会覆盖关闭通知的待发送状态。

### closed 补偿

在现有补偿任务中增加独立查询，或新增不涉及模型变更的关闭补偿任务：

```text
Alert.status = closed
Alert.notice = False
Alert.end_event_time 位于补偿窗口内
Policy.notice = True
当前 Policy 渠道为告警中心 NATS 通道
```

按现有批量上限处理。由于没有关闭重试计数字段，关闭补偿以时间窗口作为资源边界：窗口内周期性重试，超过窗口后停止自动重投并保留 `notice=False`。

首次发送和补偿可能发生 at-least-once 重复，告警中心使用幂等键消除重复。

### 条件回写

发送成功后的状态更新必须带上预期生命周期条件：

- created：仅更新 `status=new` 的 Alert。
- closed：仅更新 `status=closed` 且 `end_event_time` 等于本次 payload 时间的 Alert。

避免迟到响应覆盖更新后的生命周期状态。

## 告警中心接入与安全

`receive_alert_events` 当前仅把 `pusher=lite-monitor` 视为可信内部推送。调整为明确 allowlist：

```python
TRUSTED_INTERNAL_PUSHERS = {"lite-monitor", "lite-log"}
```

不得使用前缀匹配，也不得让调用方自行声明可信状态。

`lite-log` 事件携带的 `organizations` 仍必须满足 NATS 告警源的 `team_secrets.keys()` 白名单：

- 合法组织保留。
- 越权组织过滤并记录安全告警日志。
- 告警源未注册任何组织时，不允许退化为全放行。
- 非法组织格式不得写入 Event.team。

本设计不新增密钥，不在日志中心传递或记录 team secret。

## 错误处理与可观测性

### 结果归一化

通知器至少识别：

- `result=True`：成功。
- `result=False`：失败，提取 `message`。
- RPC/NATS 超时或异常：失败，记录异常类别和脱敏后的精简消息。
- 渠道不存在、渠道不是 NATS、method 不匹配：按当前渠道语义分流或记录配置错误。

### 日志要求

服务端日志记录：

- Log Alert ID / Event ID。
- lifecycle action。
- Policy ID / channel ID。
- 首发或补偿。
- 成功、失败或跳过原因。

禁止记录：

- 原始日志样本。
- 完整 Event payload。
- 完整下游响应。
- secret、token、密码或其他凭据。

### 页面语义

页面继续使用现有字段：

- `notice=True`：最近一次显著生命周期通知成功。
- `notice=False`：最近一次显著生命周期通知尚未成功或已经超过补偿窗口。
- `notice_users`：当前 Policy 的通知人。

不新增前端字段，不改变列表或详情接口结构。

## 数据模型与兼容性

本设计不修改任何 Django model：

- 不新增字段。
- 不修改字段类型或默认值。
- 不新增表、索引或约束。
- 不生成 schema migration 或 data migration。
- 不回填历史 Alert/Event。

历史 `Event.notified=True` 的数据不会重新发送。历史已关闭且 `notice=False` 的 Alert 只有在实现明确限定的近期补偿窗口内才可能进入关闭补偿，必须通过上线时间或 created/updated 时间边界避免历史重发风暴。

## 预期代码影响

| 位置 | 设计影响 |
|---|---|
| `server/apps/log/tasks/services/policy_scan.py` | 渠道分流、created Event 构造与现有通知状态复用 |
| `server/apps/log/services/` | 新增独立日志生命周期通知服务 |
| `server/apps/log/views/policy.py` | 在真实 PATCH 关闭状态转换中写关闭时间、重置 notice、提交后发送 |
| `server/apps/log/tasks/policy.py` | 收紧 created 回写并增加 closed 补偿 |
| `server/apps/alerts/nats/nats.py` | 将 `lite-log` 加入可信内部 pusher allowlist |
| `server/apps/log/tests/` | 日志 payload、分流、状态转换、补偿和幂等测试 |
| `server/apps/alerts/tests/` | `lite-log` 接入、组织白名单与安全边界测试 |

系统管理 `receive_alert_events` 原样透传逻辑原则上无需修改；实现阶段应通过现有测试确认没有回归。

## 测试设计

### 日志中心单元测试

1. created payload 字段映射完整且时间稳定。
2. closed payload 使用 `Alert.end_event_time` 作为稳定发生时间。
3. critical/error/warning/info 级别映射与监控中心一致。
4. NATS 告警中心渠道在 `notice_users=[]` 时仍发送。
5. 普通渠道仍发送原有 title/content 和 notice_users。
6. 非告警中心 NATS 方法不误用告警 Event envelope。
7. 组织列表来自 PolicyOrganization 且去重、顺序稳定。
8. 下游失败和异常被归一化为失败，不把完整 payload 写入日志。

### 生命周期与补偿测试

1. 首次 created 成功后 Event 与 Alert 均为已通知。
2. 首次 created 失败后保留 Event 待补偿，补偿使用相同幂等字段。
3. 持续命中且级别不变时不重复发送。
4. 级别变化产生新 created Event，external_id 相同、start_time 不同。
5. PATCH 从 new 变为 closed 时保存 operator、关闭时间并发送 closed。
6. 重复关闭不重写关闭时间、不重复发送。
7. closed 首发失败后保持 notice=False，补偿成功后变为 True。
8. created 迟到补偿不能把 closed Alert 的 notice 改成 True。
9. 超过关闭补偿窗口的 Alert 不再自动重投。
10. 没有操作权限的用户不能通过 PATCH 触发关闭或 NATS 发送。

### 告警中心接入测试

1. `pusher=lite-log` 被识别为可信内部推送。
2. `push_source_id` 和 raw_data 中记录 `lite-log`。
3. 合法 organizations 写入 Event.team。
4. 未注册组织被过滤，不能跨组织写入。
5. team_secrets 为空时不允许 organizations 直接通过。
6. 同一 payload 重投只产生一条幂等 Event。
7. created 后的 closed Event 能按 external_id 关联并关闭对应告警。

### 门禁

实现阶段至少运行：

```bash
cd server
uv run pytest apps/log/tests -q
uv run pytest apps/alerts/tests/test_nats_handlers.py apps/alerts/tests/test_source_adapter.py apps/alerts/tests/test_recovery_handler.py -q
```

最终按仓库要求执行 `make test`；若被任务外环境问题阻断，需记录阻断证据并保证目标测试全部通过。

## 验收标准

1. 配置告警中心 NATS 渠道且通知人为空时，日志告警仍能在告警中心生成 Event。
2. 告警中心 Event 的 `push_source_id` 为 `lite-log`，字段映射符合本设计。
3. 同一次发送的重复投递不会产生重复 Event。
4. 日志告警级别变化会生成新的告警中心 Event，但仍关联同一 external_id。
5. 日志告警关闭后，告警中心收到 `closed` Event 并完成对应告警关闭。
6. NATS 瞬时失败后，created 和 closed 均能通过各自补偿路径再次发送。
7. 当前 Policy 从告警中心渠道切换为普通渠道后，后续通知按新渠道执行。
8. 普通通知渠道行为无回归。
9. 越权组织不能通过伪造 `lite-log` payload 写入未授权 Event.team。
10. 实现不包含任何日志中心 model 或 migration 变更。

## 已否决方案

### 在 Log Alert 上新增通知快照和生命周期字段

否决原因：当前页面和发送逻辑明确使用 Policy 的实时配置，现有 Alert/Event 字段已足以表达本次状态；新增字段会引入迁移、双写和历史语义，超出需求。

### 新增统一跨模块生命周期通知框架

否决原因：会同时重构已经运行的监控链路，扩大回归面。本次先保持日志和监控业务实现独立，仅统一协议。

### 将关闭动作编码进 Event.content、source_id 或 notice_result

否决原因：属于隐式字段复用，会污染业务数据并让查询、补偿和审计依赖脆弱字符串约定。

### 只做同步 NATS 发送

否决原因：NATS 瞬时故障会永久丢失生命周期事件，不能形成可运营闭环。

## 后置能力

- 通知渠道和通知人的告警级历史快照。
- closed 独立重试次数、失败原因和完整发送审计。
- 日志告警自动恢复及 `recovery` Event。
- 监控、日志及其他模块共享的通用生命周期通知框架。
