# CMDB 实例写入生产级审查

## 1. Summary

实例写入有两套不同可靠性等级的路径。HTTP 单实例创建和更新先校验菜单/组织/实例权限，再创建 `CmdbOperation`，由数据库条件更新抢占唯一图写 owner；图节点携带 `_cmdb_operation_id`，图写成功后在同一 ORM 事务推进 `GRAPH_COMMITTED` 并创建变更记录、自动关系两个 Outbox。每 5 分钟的恢复任务可核对过期 `PENDING/GRAPH_WRITING` 的图事实并重建 Outbox；Outbox 自身有租约、旧 Worker owner 隔离和最多 5 次退避。

但这套状态机只覆盖单实例 create/update，且“图写”闭包还包含 Enterprise 文件台账提交。文件台账失败发生在图已提交之后，却会被统一标成 `ERROR`，而恢复器明确不扫描 `ERROR`。批量更新、单条/批量删除完全绕过 `CmdbOperation`：批量更新不使用唯一签名锁并全量读取同模型候选；删除则依次提交 SQL 审计、删除图节点、回收文件、查询并派发自动关系同步，任一步失败都没有补偿或可恢复阶段。

相同 Idempotency-Key 的同请求复用、冲突请求 409、`PENDING` 图写单 owner、图写后 SQL 提交失败的事实恢复、Outbox 旧 Worker 不能覆盖新 owner 等关键骨架是正确的。不过，自动关系 Outbox 只保证 Celery broker 接收，不保证 Worker 完成；Worker 失败后 Outbox 已是 SUCCESS，Operation 仍可成为 COMPLETED。该证据与 Task 2 主 Finding `CMDB-F04` 是同一“异步派发/传输 ack 被误当业务完成”的根因，本域只作跨域引用，不重复计数。Outbox 达到 FAILED 后，Operation 又会永久停在 GRAPH_COMMITTED，缺少失败终态和人工重放闭环。

本域确认 5 个主 Finding：P0 1 个、P1 2 个、P2 2 个、P3 0 个，编号为 `CMDB-F08`、`CMDB-F10`–`CMDB-F13`。Task 2 的 `CMDB-F01`（唯一规则管理授权）和 `CMDB-F02`（自动关联双端授权）是本域消费的上游契约；自动关系异步完成语义引用 Task 2 主 Finding `CMDB-F04`，不进入本域计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F08：图已成功时文件台账失败会被误置为不可恢复 ERROR

- Severity: P0
- Location: `server/apps/cmdb/services/instance.py:632-812`；`server/apps/cmdb/services/operation_service.py:131-180,346-372`
- Root cause category: 状态机设计缺陷
- Evidence: `instance_create` 和 `instance_update` 先完成 `create_entity/set_entity_properties`，随后在返回 `graph_write` 闭包前同步调用 Enterprise `commit_instance_files`。这里有两条不同状态路径。第一，文件 hook 主动抛异常时，异常会回到 `execute_graph` 的统一 `except`，Operation 从 `GRAPH_WRITING` 被写成 `ERROR`；图节点已经持久化 `_cmdb_operation_id`，但 `recover_pending`/周期扫描不接受 `ERROR`，相同 Idempotency-Key 也固定冲突。第二，进程在图写之后直接崩溃时，没有 Python `except` 执行，Operation 留在 `GRAPH_WRITING`；租约过期后恢复器能按 marker 推进图结果和两个 Outbox，却不会重新执行或创建任何文件 hook 事件。两条路径都会留下文件台账未收敛；更新 marker 还可能被后续更新覆盖。
- Trigger: 路径 A——Enterprise 文件台账数据库、文件引用校验或提交显式抛异常；路径 B——进程在图写已提交、文件 hook 完成前崩溃或被终止。
- Impact: 路径 A 中 API 返回失败、Operation=ERROR 且同 key 不可重放；路径 B 中 Beat 最终可把 Operation 推进至 GRAPH_COMMITTED/COMPLETED，但只补审计和自动关系，不补文件。两者都可能让引用文件保持 pending/orphaned，后续 GC 删除图实例正在引用的对象；路径 A 还不会产生审计和自动关系 Outbox。
- Why existing tests missed it: 社区默认扩展是 no-op；`test_instance_service_crud.py` 只验证成功 spy 被调用，BDD 明确把 Enterprise 扩展替换为空实现。Enterprise gitlink 在本 worktree 未初始化，真实 overlay 失败行为不可验证。
- Minimal safe fix: `graph_write` 只执行可由 `_cmdb_operation_id` 核对的图事实；文件落账作为带幂等事件 ID 的持久化 Outbox 消费者，或扩展 Operation 阶段明确区分 `GRAPH_COMMITTED/FILE_COMMITTED`。不得把图已成功后的投影失败写成不可恢复 `ERROR`。
- Required tests: 分别覆盖文件 hook 抛异常后 Operation=ERROR 且图事实存在，以及进程崩溃后 Operation=GRAPH_WRITING、Beat 能恢复图结果但当前实现不补文件；修复后断言两条路径都产生可重投文件事件、同 key 不重复图写，并覆盖 marker 被后续更新覆盖和重投幂等。
- Long-term design note: Operation 应以“主事实提交 + 多投影 checkpoint”表达跨存储状态，文件、审计和自动关系都是独立可重试消费者。

### 跨域证据：自动关系 Outbox 把 broker 接收当成业务完成（引用 CMDB-F04）

- 主 Finding: `CMDB-F04`（Task 2，P0）；本域不重复计数
- Location: `server/apps/cmdb/services/operation_service.py:216-312`；`server/apps/cmdb/tasks/celery_tasks.py:385-398`；`server/apps/cmdb/services/auto_relation_reconcile.py:27-98`
- Root cause category: 状态机设计缺陷
- Evidence: `auto_relation` Outbox 的 `_dispatch_outbox` 只调用 Celery `.delay()`；调用未抛异常便立即把事件置 SUCCESS。当两个 Outbox 都 SUCCESS 时 Operation 变为 COMPLETED。实际 `reconcile_instance_auto_association_task/full_sync_auto_association_rule_task` 是普通 `shared_task`，没有 durable delivery ID、结果回执或 `autoretry_for`；实例在目标侧时还会继续通过裸 `send_task` 派发规则级全量同步。Worker 运行失败或 worker 收到后丢失不会回写原 Outbox。
- Trigger: broker 已确认消息但 Worker 执行期间图连接失败、进程崩溃、任务超时，或目标侧二级全量同步派发失败。
- Impact: Operation 对外显示 COMPLETED，实例主属性已更新，但派生关系长期缺失或残留；没有周期任务能从 SUCCESS Outbox 重新发现该实例。
- Why existing tests missed it: `test_operation_outbox.py` 只模拟 `_dispatch_outbox` 在派发时抛错；没有运行真实 Worker 后失败并回看 Outbox/Operation。自动关系测试只断言函数或 task 被调用。
- Minimal safe fix: Outbox 消费者直接执行幂等 reconcile 并以实际结果完成事件，或创建持久化 auto-relation delivery，由 Worker 按 delivery ID 抢占、回写和重试；二级全量同步也必须进入同一 durable 链路。
- Required tests: broker 成功但 Worker 失败、Worker 崩溃租约恢复、重复投递、目标侧二级同步失败、最终成功回执，以及 Operation 在关系未收敛前不得 COMPLETED。
- Long-term design note: 明确区分“消息已派发”和“关系投影已收敛”，Operation 完成条件只能依赖后者；该跨域错误模型应随 `CMDB-F04` 统一治理，而不是为每个消费者建立重复主 Finding。

### Finding CMDB-F10：批量更新绕过唯一签名锁并全量扫描候选

- Severity: P1
- Location: `server/apps/cmdb/services/instance.py:813-904`
- Root cause category: 并发或幂等设计问题
- Evidence: 单实例 create/update 会构建 `UniqueWriteLockService` 锁键，并用规则字段定向查询候选；`batch_instance_update` 不构建或持有任何锁，直接按 `model_id` 无分页查询全部实例，再排除本批 IDs 后校验。批量与单实例写并发时都可能在对方提交前读到“无冲突”，随后写入相同唯一签名。该路径也重新引入历史 #0079 已从单实例路径移除的全模型线性扫描。
- Trigger: 两个批量更新，或批量更新与单实例 create/update，同时把不同实例改为相同内置/联合唯一值；大模型执行任意批量更新。
- Impact: 唯一规则可被并发突破；查询内存、网络和图校验成本随模型总量增长，热点模型批量编辑会超时或拖垮图服务。
- Why existing tests missed it: 批量测试把唯一规则构造替换为空规则，并让 Fake Graph 返回空候选；`test_unique_write_lock.py` 只直接测试单锁 owner 和过期接管，没有任何批量入口并发测试。
- Minimal safe fix: 为批量中每个最终实例值构建全量签名键，稳定排序后一次持有；按规则字段对本批最终值做有界候选查询，并先检测批内冲突，禁止全模型加载。
- Required tests: 批内重复、两个批量并发、批量与单写并发、联合规则、空值语义、锁顺序死锁规避，以及查询次数/返回量上限。
- Long-term design note: 唯一规则应只有一个写入门面，所有 API、采集、导入和批处理共享相同锁与候选查询契约。

### Finding CMDB-F11：批量更新与删除的跨存储副作用没有 Operation 状态机

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:416-624`；`server/apps/cmdb/services/instance.py:813-949`；`server/apps/cmdb/instance_ops/extensions.py:17-46`
- Root cause category: 状态机设计缺陷
- Evidence: 批量更新直接“图批量改写 → 逐实例文件落账 → SQL 批量审计 → 自动关系派发”；删除直接“SQL 审计 → 图批量删除 → 文件回收 → incoming 规则查询/派发”。这些入口没有 Idempotency-Key、operation ID、owner、Outbox 或恢复扫描。图更新后第 N 个文件落账失败会留下部分文件台账；图删除失败会留下声称已删除的审计；图删除后文件回收或 incoming 规则查询/派发失败会返回错误但节点已不可恢复。`destroy` 也复用同一批量删除实现。
- Trigger: 批量图写、SQL 审计、Enterprise 文件台账、incoming 规则图查询或 Celery broker 任一阶段暂时失败，或进程在任意两阶段之间退出。
- Impact: 调用方重试可能重复审计/副作用；实例、附件台账、审计与自动关系出现永久分叉。删除路径可能留下假删除审计，或实例已删除但附件未回收、反向关系未重算。
- Why existing tests missed it: Service/BDD 将审计、权限、自动关系和 Enterprise 扩展大量 monkeypatch；删除 BDD 的 `batch_delete_entity` then 步骤只检查“没有异常”，没有检查调用。现有 `test_instance_batch_delete_ok` 还因未 mock incoming 查询连接空 Neo4j URI失败（历史 #0076），没有任何阶段失败注入或跨存储终态断言。
- Minimal safe fix: 批量更新和删除也创建 durable Operation；为每个实例记录前后快照/墓碑和幂等事件，主图事实提交后由文件、审计、关系消费者分别收敛。删除前审计只能记录 intent，最终删除审计应由图事实确认后发布。
- Required tests: 每个阶段逐一失败、进程崩溃恢复、重复请求、部分批次、删除不存在实例、审计真假、文件回收和 incoming 自动关系最终收敛。
- Long-term design note: 单条删除、批量更新/删除与单实例 create/update 应复用同一 operation orchestration，而不是靠调用顺序表达一致性。

### Finding CMDB-F12：唯一写锁的固定租约没有续租或 fencing token

- Severity: P2
- Location: `server/apps/cmdb/services/unique_write_lock.py:14-80`；`server/apps/cmdb/models/operation.py:81-89`
- Root cause category: 并发或幂等设计问题
- Evidence: `hold` 默认只取得 60 秒租约，临界区中没有续租；过期后第二 owner 可条件更新接管。首 owner 的 release 因 owner token 不同不会删新锁，这是正确的，但首 owner 在失锁后仍继续查询和图写，没有 fencing token 让图层拒绝旧 owner。
- Trigger: 图查询/写入、Enterprise 文件处理或网络暂停超过 60 秒，第二个相同签名写入随后开始。
- Impact: 两个 owner 同时进入唯一性检查与图写，锁要保护的竞态重新出现；慢请求越多，越容易产生重复唯一值。
- Why existing tests missed it: `test_same_unique_signature_has_single_owner_and_stale_takeover` 手工过期后只验证 owner-specific release，不让旧 owner 在接管后继续写图。
- Minimal safe fix: 临界区定期续租并在续租失败时中止；更稳妥的是使用递增 fencing generation，在真正图写前/内验证当前 generation。租约上限应覆盖可观测 P99 并有超时边界。
- Required tests: 旧 owner 暂停超过租约、新 owner 接管、旧 owner 恢复后写入被拒；续租失败、长尾图调用、进程崩溃释放和多键锁顺序。
- Long-term design note: 租约只解决占用回收，不能单独阻止失去租约的执行者继续产生副作用；跨存储锁必须配 fencing。

### Finding CMDB-F13：Outbox 最终失败没有对应 Operation 终态与重放闭环

- Severity: P2
- Location: `server/apps/cmdb/models/operation.py:9-78`；`server/apps/cmdb/services/operation_service.py:216-312,375-391`
- Root cause category: 错误模型不清晰
- Evidence: Outbox 第 5 次失败后进入 FAILED；批处理只扫描 PENDING/RETRY/过期 SENDING，FAILED 不再处理。Operation 状态只有 ERROR（图写失败）和 COMPLETED（全部 Outbox SUCCESS）；`finish_outbox_success` 仅在所有事件 SUCCESS 时完成 Operation，没有任何逻辑把含 FAILED 的 Operation 推进到明确失败终态，也没有 reset/replay API 或告警记录。
- Trigger: change_record 或 auto_relation 连续 5 次派发失败。
- Impact: Operation 永久停在 GRAPH_COMMITTED，无法区分“仍在重试”和“已放弃”；运维无法按状态发现、恢复或量化丢失的投影，客户端相同 key 又只会获得旧结果快照。
- Why existing tests missed it: Outbox 测试只覆盖首次失败进入 RETRY、成功后 COMPLETED、旧 owner 不覆盖新 owner；没有跑满 5 次、Operation 终态、人工重放和告警断言。
- Minimal safe fix: 增加 `COMPLETED_WITH_ERRORS/OUTBOX_FAILED` 等明确终态和失败事件查询；提供受控、幂等的重放入口，并让周期任务输出/告警终态失败数量。
- Required tests: 第 5 次失败、混合 SUCCESS/FAILED、旧 Worker 晚到、人工重放成功、重复重放、告警与最终 Operation 状态。
- Long-term design note: 父 Operation 状态应由所有子事件状态确定，状态集合必须覆盖成功、进行中、可重试失败和终止失败。

## 3. Test Review

按简报在 `server/` 使用显式 SQLite、Celery 和 MinIO 测试环境运行五个文件，并添加 `--cov=apps.cmdb.services.instance --cov=apps.cmdb.services.operation_service --cov-report=term-missing`。沙箱内首次因无权读取 `~/.cache/uv/sdists-v9/.git` 退出 2，未进入收集；受控权限重跑最终为 **49 passed、1 failed in 28.76s，exit 1**。唯一失败是 `test_instance_batch_delete_ok` 未 mock 新增 incoming 自动关系查询，连接未配置 Neo4j URI；它与项目记忆历史 #0076 完全一致，属于既有夹具隔离缺陷，不是本次代码回归。

覆盖率输出：`apps/cmdb/services/instance.py` **37%**（905 statements / 567 missed）；`apps/cmdb/services/operation_service.py` **82%**（192 / 34 missed）；合计 **45%**（1097 / 601 missed）。因此 Operation 骨架达到普通模块 80% 目标，但实例服务与本域合计远低于 75%/核心 90% 门槛，不能据此批准生产。

有效证明包括：

- 相同 operator/key/same payload 复用，相同 key/different payload 冲突；单实例 View 另有同 key 不重放图写测试。
- `PENDING → GRAPH_WRITING` 只有一个 owner；同 Operation 成功后不重复图写，Outbox `(operation,event_type)` 唯一。
- 图写 SQL 提交前崩溃场景可通过 `_cmdb_operation_id` 事实恢复，并创建两个 Outbox；Beat 已注册每 5 分钟运行。
- Outbox 租约被新 owner 接管后，旧 Worker 不能完成新 owner 的事件；变更记录以 event ID 去重。
- broker 派发异常会进入 RETRY且错误文本脱敏；单实例唯一候选使用定向查询；组织范围越权创建被拒。

证明力不足包括：

- 没有真实并发线程/进程；owner 和锁测试是串行条件更新，未覆盖旧图 Worker 在恢复后晚到、唯一锁过期后旧 owner 继续图写。
- 没有覆盖 `_commit_graph_result` SQL 失败的实际异常注入；恢复测试直接构造过期行并 mock 图事实。
- 没有图成功/文件台账失败、Outbox Worker 运行失败、5 次 FAILED、Operation 失败终态或人工重放。
- 批量更新测试把唯一规则清空且候选设为空；未覆盖批内/跨请求冲突、资源上限、部分文件落账。
- 删除测试失败暴露夹具未隔离；BDD 的删除 then 步骤和 create_entity 次数步骤含空实现，无法证明图调用。所有删除副作用和回滚/恢复都未验证。
- View 权限测试主要用 superuser/monkeypatch；没有批量多组织、creator 快捷路径与 Service 二次权限的负向组合证明。
- Enterprise 子模块未初始化，社区测试主动使用 no-op 扩展；真实附件台账、GC 和 overlay 权限行为均为未验证项。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：单实例 Operation 状态较清晰，但 `graph_write` 名称实际包含文件 SQL 副作用，阶段名会误导维护者；批量/删除另走裸编排。
2. 新增同类插件是否需要复制代码：Enterprise 门面避免社区 import，但每个写路径仍需手工记得 normalize/commit/delete hook，已经出现不同可靠性等级。
3. 新增错误类型是否需改多个模块：是。图失败、文件失败、派发失败和 Worker 失败被不同层折叠或遗漏，状态与 HTTP 映射不统一。
4. 新增 callback 模式是否容易扩展：Outbox event type 可扩展，但父状态只有全 SUCCESS；异步消费者缺结果协议，新增 callback 会复制“派发即成功”。
5. 当前接口是否容易被误用：是。调用 `InstanceManage.batch_instance_update/instance_batch_delete` 会绕过 Idempotency 和恢复；`schedule_*` 的 on_commit 在无事务时立即执行，也容易被误认为 durable。
6. 日志是否足够且不泄密：Operation/Outbox 错误已脱敏；但 FAILED 无父终态/告警，自动关系 Worker 失败也无法关联回 Operation。
7. 状态异常时能否判断停在哪个阶段：单实例图写和派发阶段部分可以；文件投影、Worker 实际执行、批量更新和删除完全不能。
8. 设计是否降低复杂度：owner、outbox lease 和事实核对降低了单实例重放复杂度；状态机覆盖一半入口且阶段边界不真实，使整体复杂度转移到异常恢复和人工对账。

## 5. Recommendation

**Block**。

`CMDB-F08` 是本域发布阻断项：先把文件台账移出图写失败域，确保 hook 异常和进程崩溃两条路径都可恢复且不会删除用户文件。跨域主 Finding `CMDB-F04` 还必须让自动关系以实际 Worker 收敛作为完成条件。随后关闭两个本域 P1：让批量更新复用唯一锁和有界候选；让批量更新/删除进入统一 Operation/Outbox。P2 的锁 fencing 和 Operation 失败终态也应在生产前补齐，否则长尾并发和最终失败仍无可靠闭环。仅修复现有删除测试夹具或增加成功路径 Mock，不能降低上述生产风险。
