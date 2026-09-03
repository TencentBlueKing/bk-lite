# 告警中心关联监控对象快照——TDD 测试方案

Status: implemented

Date: 2026-09-03

实施计划：[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)

## 1. TDD 执行约定

本方案是待执行的测试清单，不表示实现阶段会一次性写完全部测试。编码阶段按纵向切片执行：

1. 只写当前切片的第一个行为测试并确认失败原因正确；
2. 只实现使该测试通过的最小代码；
3. 运行当前切片和已完成切片的回归；
4. 再增加下一条行为测试；
5. 所有切片完成后进入代码审查，不在红绿循环中进行额外重构。

预期值使用需求中的固定示例，不复刻实现算法生成期望结果。

## 2. 待确认的测试 seam

| Seam | 公开可观察行为 | 测试位置 | 允许替身 |
|---|---|---|---|
| S1 监控告警中心投递 | `AlertLifecycleNotifier.enqueue_alert_center_deliveries` 产生不可变标准 payload | `server/apps/monitor/tests/test_alert_center_monitor_object_snapshot_service.py` | 仅替换外部投递调度；使用真实测试数据库和 outbox |
| S2 NATS 告警接入 | `receive_alert_events` 接收标准 envelope 后持久化可查询 Event | `server/apps/alerts/tests/test_monitor_object_snapshot_ingress_service.py` | NATS 网络可用进程内调用代替；不 mock Adapter |
| S3 对象归并 | `resolve_monitor_objects(events)` 返回稳定对象集合 | `server/apps/alerts/tests/test_monitor_object_snapshot_resolver_pure.py` | 不使用 mock，输入固定事件值对象 |
| S4 Alert 聚合 | `AlertBuilder.create_or_update_alert`、`InstantAlertDispatcher.dispatch` 生成可序列化 Alert | `server/apps/alerts/tests/test_monitor_object_snapshot_aggregation_service.py` | 外部生命周期分派可替换；ORM、M2M 和 fingerprint lease 使用测试数据库 |
| S5 告警读取接口 | Alert retrieve 和关联事件接口返回身份快照 | `server/apps/alerts/tests/test_monitor_object_snapshot_views.py` | 不 mock serializer/queryset；使用认证请求 |
| S6 页面展示 | 告警详情和事件表产生用户可见文本、隐藏或显示指定字段 | `web/src/app/alarm/components/__tests__/monitor-object-snapshot.test.tsx` | 只替换 i18n/浏览器外部环境；用 Testing Library 观察 DOM |

测试不直接断言私有 helper 调用次数或内部调用顺序；数据库查询次数只在批量查询属于明确性能契约时单独验证。

## 3. 固定验收样例

输入事件按到达顺序为：

```json
[
  {"resource_name":"ip1","resource_type":"Host","monitor_id":"0001","cmdb_id":"xxxx1"},
  {"resource_name":"ip1","resource_type":"Host","monitor_id":"0001","cmdb_id":"xxxx1"},
  {"resource_name":"ip1","resource_type":"Host","monitor_id":"0001","cmdb_id":"xxxx1"},
  {"resource_name":"ip2","resource_type":"Switch","monitor_id":"0002","cmdb_id":"xxxx2"}
]
```

Alert 的固定期望值：

```json
[
  {"monitor_id":"0001","cmdb_id":"xxxx1","resource_type":"Host","resource_name":"ip1"},
  {"monitor_id":"0002","cmdb_id":"xxxx2","resource_type":"Switch","resource_name":"ip2"}
]
```

页面固定期望：

```text
Host：ip1
Switch：ip2
```

详情中不得出现 `0001`、`0002`、`xxxx1`、`xxxx2`；关联事件表中应出现对应 ID。

## 4. 红绿切片与用例

### C1：监控产生发送时身份快照

首个红灯：`test_monitor_alert_center_payload_contains_monitor_and_cmdb_identity`

场景：创建 MonitorObject、一个已关联 CMDB 的 MonitorInstance 和对应 MonitorAlert，通过公开 outbox 投递 seam 入队。

断言：

- outbox payload 的 `monitor_id` 与 `resource_id` 都等于实例 ID；
- `cmdb_id` 等于实例的 CMDB `inst_uuid`；
- `resource_type` 等于 MonitorObject.name；
- `resource_name` 保持 MonitorAlert 中的实例名称；
- 原有 `external_id/action/organizations/tags/labels` 内容不变。

随后逐条增加：

| ID | 行为 |
|---|---|
| C1.2 | 未关联 CMDB 时 payload 显式携带 `cmdb_id: null`，其余身份仍存在 |
| C1.3 | 同批多个 Alert 只执行一次实例批量读取，不产生逐条查询 |
| C1.4 | outbox 创建后修改 MonitorInstance.cmdb_id，已保存 payload 保持原值 |
| C1.5 | MonitorInstance 已不存在时仍发送 `monitor_id/resource_id/resource_name`，`cmdb_id` 为空，类型按计划中的回退规则处理 |
| C1.6 | legacy 直发与 outbox payload 的四个对象字段一致 |

### C2：NATS 接收并持久化 Event

首个红灯：`test_receive_monitor_event_persists_explicit_identity_snapshot`

使用带内部签名的 `source_id=nats`、`pusher=lite-monitor` envelope 调用 `receive_alert_events`，读取落库 Event。

断言：

- `monitor_id/cmdb_id/resource_id/resource_type/resource_name` 逐项等于输入；
- `push_source_id == "lite-monitor"`；
- `raw_data` 仍保存收到的完整单事件 payload；
- 接入返回 `accepted=1`，幂等键与逐事件 ACK 行为不变。

随后逐条增加：

| ID | 行为 |
|---|---|
| C2.2 | 缺少 `monitor_id/cmdb_id` 的旧 payload 正常接收，两字段为 null |
| C2.3 | 第三方事件只有 `resource_id` 时不生成 monitor_id |
| C2.4 | `cmdb_id=null` 正常持久化，不导致整批失败 |
| C2.5 | 重复投递仍由原 ingest_key 去重，不产生第二条 Event |
| C2.6 | `init_alert_sources` 执行后内置 NATS source 映射包含两个新字段 |
| C2.7 | 100 字符 resource_type、100 字符 monitor/resource ID 不被截断 |
| C2.8 | 非字符串或超过 100 字符的身份字段按事件拒收，计入 `rejected` 而非 `errored`，且 NATS 不记录成功终态或原始值 |

### C3：对象集合确定性归并

首个红灯：`test_resolve_monitor_objects_deduplicates_requirement_example`

输入 §3 的四条事件，直接断言固定的两项结果及顺序。

随后逐条增加：

| ID | 行为 | 固定期望 |
|---|---|---|
| C3.2 | 两个不同 monitor_id 对应同名对象 | 保留两项，不按名称误去重 |
| C3.3 | monitor_id 存在、cmdb_id 为空 | 保留对象且 cmdb_id 为 null |
| C3.4 | 首条 cmdb/type/name 为空，后条补齐 | 原位置不变，空槽被补齐 |
| C3.5 | 后条携带不同的非空 cmdb/type/name | 首次非空值保持不变 |
| C3.6 | monitor_id 为空但 resource_id、cmdb_id 有值 | 返回空集合 |
| C3.7 | 来源字段不是 lite-monitor，但显式携带 monitor_id | 仍按显式身份契约参与集合 |
| C3.8 | monitor_id 首尾有空白 | 规范化后按同一 ID 去重 |
| C3.9 | 输入为空 | 返回 `[]` |

### C4：普通聚合持久化完整集合

首个红灯：`test_create_alert_persists_all_monitor_objects`

通过 `AlertBuilder.create_or_update_alert` 聚合 §3 的事件，读取 Alert serializer 输出。

断言：

- `monitor_objects` 等于固定期望；
- Alert 关联四条 Event，集合不受事件接口分页影响；
- 多对象导致旧 `resource_id/resource_type/resource_name` 不一致时，旧标量仍按现有规则置空；
- 事件 labels 不一致时，Alert.labels 仍按现有规则为 `{}`。

随后逐条增加：

| ID | 行为 |
|---|---|
| C4.2 | 已有 Alert 后到第二个 monitor_id，更新后集合包含两项 |
| C4.3 | 同一 monitor_id 的后到事件只补空，不覆盖非空值 |
| C4.4 | 全部 Event 没有 monitor_id 时 monitor_objects 为 `[]`，旧字段结果逐项不变 |
| C4.5 | 聚合混入第三方 resource_id 时只保留显式监控对象，不生成伪对象 |

### C5：即时告警保持同一契约

首个红灯：`test_instant_alert_contains_single_monitor_object_snapshot`

通过 `InstantAlertDispatcher.dispatch` 的公开入口创建即时 Alert。

断言：

- 有 monitor_id 的单事件生成一个对象项；
- 无 monitor_id 的单事件生成空列表；
- 即时告警的旧 `resource_*`、标题、级别和 labels 不变；
- 生命周期分派仍然只发生一次。

### C6：读取接口返回完整对象与单事件快照

首个红灯：`test_alert_retrieve_returns_full_monitor_object_collection`

通过有组织权限的认证请求访问 Alert retrieve。

断言：

- 返回完整、有序的 `monitor_objects`；
- 两个对象的 ID 和空 CMDB 值序列化正确；
- 没有集合的旧 Alert 返回 `monitor_objects: []`。

随后增加：

| ID | 行为 |
|---|---|
| C6.2 | 关联事件接口每行返回 monitor_id、cmdb_id |
| C6.3 | 事件分页只影响事件列表，不裁剪 Alert.monitor_objects |
| C6.4 | 既有组织权限仍阻止跨组织读取新增身份字段 |

### C7：页面展示与兼容回退

首个红灯：`renders_monitor_objects_as_separate_type_name_rows_without_ids`

使用 Testing Library 渲染告警详情可见界面。

断言：

- 页面可见 `Host`、`ip1`、`Switch`、`ip2`；
- 每个对象独占一行；
- DOM 文本中不存在 monitor_id 和 cmdb_id；
- 未关联 CMDB 的对象仍显示。

随后增加：

| ID | 行为 |
|---|---|
| C7.2 | monitor_objects 为空时继续显示旧 resource_type/resource_name |
| C7.3 | 事件表显示“监控实例 ID”和“CMDB 实例 ID”列及具体值 |
| C7.4 | cmdb_id 为空时事件表显示 `--` |
| C7.5 | 两套告警详情入口使用相同对象展示语义 |
| C7.6 | 两套事件表使用相同身份列语义 |

## 5. 非回归矩阵

| 范围 | 必须保持 |
|---|---|
| NATS transport | 内部签名、渠道组织交集、request/reply、逐事件 ACK 不变 |
| 接入幂等 | 相同 source/pusher/external/action/start_time 不重复落 Event |
| Event | 无新字段时仍能接收；raw_data 和 labels 不被重写 |
| 聚合 | 旧 resource 标量一致性和 labels 整包一致性规则不变 |
| 恢复 | external_id 恢复匹配和 Alert 状态推进不变 |
| 即时告警 | 无 monitor_id 的事件输出与基线一致 |
| 权限 | 新字段不绕过 Alert/Event 组织权限 |
| Web | 非监控告警继续展示旧对象字段；空值不出现 `undefined/null` 文案 |

## 6. 明确不测试的内容

- 不启动真实 NATS Broker；传输网络属于外部系统边界，使用进程内 request adapter 验证 envelope 和字段保真。
- 不连接真实 CMDB；MonitorInstance.cmdb_id 是本测试的来源事实。
- 不测试日志 labels、动作引擎和历史回填，因为不在本版本范围。
- 不断言私有函数是否被调用，也不通过源代码字符串匹配代替用户可见行为测试。

## 7. 建议运行命令

### 7.1 每个后端红绿循环

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
uv run pytest apps/monitor/tests/test_alert_center_monitor_object_snapshot_service.py --no-cov
```

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
uv run pytest \
  apps/alerts/tests/test_monitor_object_snapshot_ingress_service.py \
  apps/alerts/tests/test_monitor_object_snapshot_resolver_pure.py \
  apps/alerts/tests/test_monitor_object_snapshot_aggregation_service.py \
  apps/alerts/tests/test_monitor_object_snapshot_views.py \
  --no-cov
```

### 7.2 相关既有回归

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
uv run pytest \
  apps/monitor/tests/test_alert_lifecycle_notify_service.py \
  apps/monitor/tests/test_issue_3341_alert_center_retry_service.py \
  apps/alerts/tests/test_nats_handlers.py \
  apps/alerts/tests/test_source_adapter.py \
  apps/alerts/tests/test_alert_builder.py \
  apps/alerts/tests/test_instant_dispatcher.py \
  apps/alerts/tests/test_recovery_handler.py \
  apps/alerts/tests/test_incident_alert_views.py \
  --no-cov
```

### 7.3 Migration 检查

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
uv run python manage.py makemigrations --check --dry-run
```

### 7.4 Web 红绿循环与静态检查

```bash
cd web
pnpm exec vitest run src/app/alarm/components/__tests__/monitor-object-snapshot.test.tsx
pnpm lint
pnpm type-check
```

## 8. 完成门禁

- [x] S1–S6 的测试 seam 已由用户确认。
- [x] 每个纵向切片有可观察且原因正确的红灯记录。
- [x] §4 全部自动化测试通过。
- [x] §5 相关既有回归通过，或保留与本变更无关的原始失败证据。
- [x] migration check 无未提交漂移。
- [x] Web 目标测试、lint、type-check 通过。
- [x] 自动化复核详情对象分行、ID 隐藏、事件 ID 展示及旧告警回退。
- [x] 没有查询 Monitor/CMDB 的告警聚合或展示代码。

## 9. 确认栏

- [x] 同意以上测试 seam。
- [x] 同意按 C1 → C7 逐切片红绿实施。
- [x] 用户于 2026-09-03 确认测试方案。

## 10. 实施验证记录

2026-09-03 使用仓库现有 `server/.venv` 与 SQLite 完成验证：

| 验证项 | 结果 |
|---|---|
| S1-S5 新增后端用例 | 39 passed |
| S6 Web 可见行为用例 | 7 passed |
| 告警聚合、NATS 相关回归 | 177 passed，1 个既有查询数断言失败 |
| Monitor 生命周期相关回归 | 92 passed，2 个既有失败、1 个 SQLite 清理错误 |
| Django system check | 通过 |
| `makemigrations --check --dry-run` | 通过，无模型漂移 |
| `sqlmigrate alerts 0027` | 通过，可生成完整正向迁移 SQL |
| `sqlmigrate alerts 0027 --backwards` | 通过，可生成完整反向迁移 SQL |
| 混合版本协议 | 旧生产者→新消费者、新生产者→旧映射均通过 |
| NATS 接入终态与安全日志 | 成功/部分接收及非法身份字段相关回归 6 passed；非法值只记录字段名和有界计数 |
| Web 定向 ESLint | 通过 |
| Web TypeScript build config | 通过 |

环境说明：

- 本机没有 `uv` 命令，因此后端改用 `server/.venv/bin/pytest`；测试增加 `--no-migrations`，用于绕过仓库既有 `alerts.0009` 在 SQLite 上的 `NewSessionEventRelation.event` 迁移错误。
- 实际执行全量迁移时仍会在既有 `alerts.0009` 失败，尚未运行到本次 `alerts.0027`；本次迁移自身已通过模型漂移检查、迁移计划检查和 SQL 渲染。
- Web 默认 Node 14 不满足仓库要求，改用 Codex 工作区 Node 运行。仓库捆绑 pnpm 为 11.19、项目固定 11.20，因此正式脚本拆解为相同的 Next typegen、类型同步和 `tsc` 步骤执行。
- 回归失败均不涉及本次修改：一个旧测试桩未接收现有 `internal_caller` 参数，一个 SQLite 并发锁用例不具备目标数据库语义，一个告警来源分布用例存在既有额外查询。
