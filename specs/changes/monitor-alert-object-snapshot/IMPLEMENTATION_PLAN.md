# 告警中心关联监控对象快照——实施计划

Status: implemented

Date: 2026-09-03

测试方案：[TEST_PLAN.md](./TEST_PLAN.md)

## 1. 目标

监控中心通过告警中心 NATS 告警源发送事件副本时，补充监控实例与 CMDB 关联身份。告警中心保存单条事件快照，并在聚合后的 Alert 上保存完整监控对象集合。告警详情展示完整对象集合，关联事件表展示每条事件携带的 `monitor_id`、`cmdb_id`。

没有 `monitor_id` 的 Event 完全沿用当前 `resource_*`、`labels` 和聚合逻辑；禁止把第三方事件的 `resource_id` 推断成监控实例 ID。

## 2. 本版本范围

### 2.1 包含

- `lite-monitor` 的 NATS event payload 增加 `monitor_id`、`cmdb_id`、`resource_type`。
- `resource_id` 继续双写监控实例 ID；`resource_name` 继续使用监控实例名称。
- 告警中心 Event 将 `monitor_id`、`cmdb_id` 保存为独立可空字段。
- Alert 使用 `monitor_objects` JSON 集合保存全部关联监控对象。
- 普通窗口聚合、即时聚合均生成 `monitor_objects`。
- 同一 Alert 内按 `monitor_id` 去重；后到事件只补齐已有对象的空字段。
- 告警详情按对象分行展示 `resource_type: resource_name`，不展示身份 ID。
- 关联事件表增加 `monitor_id`、`cmdb_id` 两列。
- 旧事件、第三方事件以及没有 `monitor_id` 的新事件保持现有行为。

### 2.2 本版本不包含

- 日志中心的 `inst_uuid`、模型及原日志 labels；日志域尚未定义多样本 labels 的稳定投影规则。
- 修改监控原始指标 labels 的传输语义；本版本保持现有 `labels` 内容和告警级一致性规则。
- 动作引擎字段绑定、多对象作业目标展开。
- 按 `monitor_id`、`cmdb_id` 搜索、筛选或分组告警。
- 对历史 Event/Alert 做数据回填。
- 告警中心在聚合、展示或动作阶段回查 Monitor/CMDB。

上述内容是有意拆出的后续切片，不代表取消。若本次必须同时包含“原 labels”或动作绑定，应在编码前修改本计划和测试方案。

## 3. 已确认的当前链路

```text
MonitorAlert
  -> AlertLifecycleNotifier 构造标准 event payload
  -> MonitorAlertCenterDelivery 固化 outbox payload
  -> SystemMgmt.dispatch_notification
  -> NATS Channel(namespace + receive_alert_events)
  -> alerts.receive_alert_events
  -> NatsAdapter / AlertSourceAdapter
  -> Event 入库
  -> InstantAlertDispatcher 或 AggregationProcessor
  -> Alert 入库或更新
  -> Alert 详情与关联事件接口
```

系统管理的 `alert_event_copy` 通道会保留 event payload，仅收敛 `organizations` 并添加内部签名；告警中心接收后根据内置 NATS 告警源的 `event_fields_mapping` 将字段映射到 Event。

## 4. 数据契约

### 4.1 监控发送的事件

```json
{
  "monitor_id": "0001",
  "cmdb_id": "550e8400-e29b-41d4-a716-446655440000",
  "resource_id": "0001",
  "resource_type": "Host",
  "resource_name": "ip1"
}
```

字段规则：

| 字段 | 来源 | 空值规则 |
|---|---|---|
| `monitor_id` | `MonitorAlert.monitor_instance_id` | 监控告警正常情况下必有；不从其他字段推断 |
| `cmdb_id` | `MonitorInstance.cmdb_id` | 未关联 CMDB 时为 `null` |
| `resource_id` | `MonitorAlert.monitor_instance_id` | 保留当前双写兼容 |
| `resource_type` | `MonitorInstance.monitor_object.name` | 查询不到实例时可回退到策略的 `monitor_object.name` |
| `resource_name` | `MonitorAlert.monitor_instance_name` | 保留当前行为 |

本版本把“发生时”定义为“创建 NATS 投递 payload 的时刻”。outbox 保存 payload 后，重试不得重新查询或改写身份。

### 4.2 告警 Event

新增字段：

```python
monitor_id = models.CharField(max_length=100, null=True, blank=True)
cmdb_id = models.CharField(max_length=100, null=True, blank=True)
```

同时将内置 NATS 告警源的 `event_fields_mapping` 增加同名映射。`init_alert_sources` 已由 `batch_init` 调用，发布后会更新内置源配置。

本版本不提供按这两个字段搜索，所以暂不增加数据库索引。为避免上游合法长度在接入时失败，本次迁移同时对齐：

- `Event.resource_id` 从 64 扩到 100；`Alert.resource_id` 已有 128，无需修改；
- `Event.resource_type` 与 `Alert.resource_type` 扩到 100。

不得截断身份或监控对象名称。

### 4.3 聚合后的 Alert

新增：

```python
monitor_objects = models.JSONField(default=list, blank=True)
```

单项结构固定为：

```json
{
  "monitor_id": "0001",
  "cmdb_id": null,
  "resource_type": "Host",
  "resource_name": "ip1"
}
```

列表顺序按关联 Event 的数据库主键升序，即首次出现顺序。`cmdb_id` 未关联时必须保留为 JSON `null`，不能丢掉该对象。

## 5. 对象集合归并规则

在 `server/apps/alerts/service/` 新增一个纯归并模块，以一个公开函数作为测试 seam：

```python
def resolve_monitor_objects(events: Iterable[Event]) -> list[dict]:
    ...
```

规则如下：

1. 按 Event 主键升序处理；调用方负责提供稳定顺序。
2. 仅规范化后 `monitor_id` 非空的事件参与；显式字段本身就是身份契约，不额外耦合 `push_source_id`。
3. 不从 `resource_id`、`labels` 或 `raw_data` 推导 `monitor_id`。
4. 第一次看到某个 `monitor_id` 时创建对象项，即使 `cmdb_id` 为空也保留。
5. 再次看到同一 `monitor_id` 时，只补齐 `cmdb_id/resource_type/resource_name` 的空值。
6. 已有非空值与后到事件冲突时保留首次非空值，不覆盖。
7. 输入中没有合格事件时返回 `[]`。

该模块只做确定性数据变换，不访问 Monitor、CMDB 或数据库。

## 6. 实现切片

每个切片严格执行一个红灯测试、最小实现、转绿，再进入下一切片。详细用例见测试方案。

### T1：监控 NATS payload 快照

修改：

- `server/apps/monitor/services/alert_lifecycle_notify.py`
- `server/apps/monitor/services/alert_center_delivery.py`（仅在调用参数需要收敛时修改）
- 对应 monitor 测试

实现：

- 按本批 Alert 的 `monitor_instance_id` 一次性读取 MonitorInstance、CMDB UUID 和 MonitorObject 名称。
- 新增批量身份映射（建议命名 `_build_monitor_identity_map`），与现有 `_build_instance_org_map` 一样在 legacy 和 outbox 两条批量入口各查询一次。
- `_build_alert_center_payload` 只消费预构建映射并统一增加三个字段；legacy 发送和 outbox 共用同一构造逻辑。
- `monitor_id` 不依赖 MonitorInstance 查询是否命中。
- outbox 一旦创建，实例后来重新关联 CMDB也不能改变已保存 payload。

完成定义：监控公开投递 seam 产出符合 §4.1 的不可变 payload，且未关联 CMDB 时仍发送对象。

### T2：告警 Event 接入与兼容

修改：

- `server/apps/alerts/models/models.py`
- 新增 alerts migration
- `server/apps/alerts/common/source_adapter/constants.py`
- `server/apps/alerts/management/commands/init_alert_sources.py` 仅在现有更新机制不足时修改
- 对应 alerts NATS 接入测试

实现：

- 增加 Event 身份字段及长度对齐迁移。
- 内置 NATS source 映射两个新字段。
- 接入边界拒绝非字符串或超过字段上限的身份值，将其计入业务拒收而非系统错误；部分接收不得输出成功终态，也不得记录原始身份值。
- 保持 `raw_data`、幂等键、组织归属、屏蔽和生命周期处理顺序不变。

完成定义：标准 NATS 接收入口能持久化字段；缺字段事件的数据库值为 `null`，既有字段逐项不变。

### T3：监控对象归并模块

创建：

- `server/apps/alerts/service/monitor_object_snapshot.py`
- 对应纯函数测试

实现 §5 的全部确定性规则。禁止在此模块中查询数据库或调用 RPC。

完成定义：需求给出的四条事件得到两条稳定有序对象记录；空 CMDB、重复、补空和冲突规则均转绿。

### T4：普通聚合和即时聚合持久化

修改：

- `server/apps/alerts/models/models.py`
- 同一个 alerts migration
- `server/apps/alerts/aggregation/builder/alert_builder.py`
- `server/apps/alerts/aggregation/processor/instant_dispatcher.py`
- 对应聚合测试

实现：

- Alert 增加 `monitor_objects`。
- 新建 Alert 时从命中的 Event 计算集合。
- 更新现有 Alert 时从全部已关联 Event 重新计算，避免增量状态漂移。
- 即时 Alert 从单条 Event 生成零或一个对象。
- `resource_*` 和 `labels` 继续使用当前一致性逻辑，不因新集合改变。

恢复/关闭 Event 仍按当前恢复链路关联 Alert，但本版本不让终态事件新增监控对象；对象集合由触发/升级形成的 `created` Event 确定。这样避免恢复处理与聚合更新并发写同一 JSON 字段。

完成定义：普通聚合和即时聚合均落下正确集合，无 `monitor_id` 时结果为 `[]` 且旧字段结果不变。

### T5：接口与页面

修改：

- `server/apps/alerts/serializers/alert.py`（仅在 JSONField 自动输出不足时显式声明）
- `web/src/app/alarm/types/alarms.ts`
- `web/src/app/alarm/types/integration.ts`
- `web/src/app/alarm/components/alarm-base-info/index.tsx`
- `web/src/app/alarm/(pages)/alarms/components/baseInfo.tsx`
- `web/src/app/alarm/components/alarm-event-table/index.tsx`
- `web/src/app/alarm/components/eventTable/index.tsx`
- 对应 Web 测试与翻译资源

实现：

- Alert 详情响应携带完整 `monitor_objects`；关联事件响应携带单条身份字段。
- `monitor_objects` 非空时，对象区域逐行渲染 `resource_type: resource_name`，不把 ID 放入可见 DOM。
- `monitor_objects` 为空时保留当前“对象类型 / 对象”展示。
- 两套现存告警详情入口保持一致。
- 两套事件表增加监控实例 ID、CMDB 实例 ID；空值显示 `--`。

完成定义：用户示例显示为两行对象，详情不显示 ID，事件表可以逐条核对 ID。

### T6：契约回归与收口

- 运行 [TEST_PLAN.md](./TEST_PLAN.md) 的目标测试和静态检查。
- 检查 migration 无漂移。
- 若实现改变长期 capability，再更新相关 capability；本次不得顺手改日志或动作引擎。
- 记录基线失败和未运行项，不用无关修改掩盖失败。

## 7. 发布与兼容

发布顺序：

1. 先发布告警中心数据库迁移、接收字段、聚合和读接口；此时新字段为空，旧行为不变。
2. 发布 Web；空集合自动显示旧字段。
3. 最后发布 Monitor producer，开始发送身份字段。

回滚时可以先回滚 Monitor producer，告警中心新增可空字段和 JSONField 保留，不影响旧事件。不得在回滚时删除新列或清理已生成对象集合。

历史 Alert 不回填 `monitor_objects`；详情通过空集合兼容旧展示。禁止使用历史 `resource_id` 猜测监控身份。

## 8. 明确不变量

- Monitor 仍拥有自身告警生命周期；告警中心只接收事件副本。
- NATS 渠道配置、内部签名、组织收敛、逐事件 ACK 和 outbox 重试语义不变。
- 聚合阶段不回查 Monitor/CMDB。
- `resource_id` 继续参与当前聚合、恢复和兼容逻辑。
- 无 `monitor_id` 的 Event 不产生 `monitor_objects`，其他输出逐字段保持现状。
- 未关联 CMDB 的监控实例不会从对象集合中消失。

## 9. 确认栏

- [x] 确认“快照时点”为 NATS 投递 payload 创建时。
- [x] 确认本版本使用 Alert JSONField，不建立对象关系表。
- [x] 确认只有显式 `monitor_id` 才进入对象集合，不从来源或 `resource_id` 猜测。
- [x] 确认长度对齐迁移：`Event.resource_id` 64→100，`Event/Alert.resource_type` 64→100。
- [x] 确认恢复/关闭 Event 不新增或回填 `monitor_objects`。
- [x] 确认原 labels、日志来源和动作引擎留到后续切片。
- [x] 确认 TDD 测试 seam 与执行顺序，可以开始 T1。
- [x] 用户于 2026-09-03 确认方案并完成 T1-T6 实施。

## 10. 实施结果

- Monitor 的 legacy 直发和 outbox 共用批量身份快照，投递入队后不再回查或改写。
- Event 与 Alert 字段、内置告警源映射、普通/即时聚合及恢复边界均按本计划落地。
- 两套告警详情共用一个 app-local 对象列表组件；两套事件表共用一组身份列定义。
- 数据迁移为 `alerts.0027_alert_monitor_objects_event_cmdb_id_event_monitor_id_and_more`。
- 发布顺序和回滚约束保持 §7 不变。
