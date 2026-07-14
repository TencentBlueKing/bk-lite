# CMDB 变更记录与订阅生产级审查

## 1. Summary

本域存在两条可靠性等级明显不同的事件链。变更记录本身由 ORM 持久化；普通属性变更只保留在 CMDB，模型管理、自动采集、自定义上报和关系变更还会镜像到平台 OperationLog。批量写已经使用 `ChangeRecordMirrorOutbox`，按 100 条分片、5 次重试、5 分钟租约和 Beat 补偿；单条写却仍在 `create_change_record` 内同步调用 SystemMgmt。订阅侧由 Beat 逐规则加行锁，查询当前图实例与 ChangeRecord 时间窗口，快照和 Delivery 在同一事务提交；Delivery 以 SHA-256 去重，发送侧有 `PENDING/RETRY → SENDING → SENT/FAILED`、15 分钟租约恢复、3 次退避和 `attempt_count` 代次条件，旧 Worker 不能覆盖新代次终态。

这些骨架没有形成端到端授权边界。订阅创建只检查 `asset_info-Add`，未证明规则组织、模型、实例、条件、用户、组织和渠道属于调用者范围；后台随后用 `permission_map={}` 读取图数据，并调用未带 actor context 的组织用户接口。变更记录 API 也只有菜单权限，模型没有组织列，列表、详情和 5 万行导出都从全局 queryset 读取。两条链都能把其他组织资产或审计前后快照交付给当前调用者或其指定收件人。

镜像链还存在一致性缺口：单条管理类记录在外层事务提交前同步 RPC，失败只写 warning 且没有重试，外层回滚时平台侧又可能保留不存在的操作；批量 Outbox 在第 N 条 RPC 失败时整批 RETRY，重投会重复前 N-1 条成功日志。订阅 Delivery 的至少一次发送在“外部发送成功、SENT 更新前崩溃”时同样可能重复，但项目已明确采用至少一次模型，本域将其列为需由下游幂等键收敛的已知限制，不另立 Finding。

本域新增 3 个主 Finding：`CMDB-F58`–`CMDB-F60`，P0 2 个、P1 1 个、P2/P3 0 个。订阅/镜像无规则数、实例数、关系数、ChangeRecord 数、Delivery 数、RPC 总量和 deadline 硬上限引用既有 `CMDB-F23`；原始非法 event、异常字符串及下游 message 写日志/`last_error` 引用既有 `CMDB-F25`，均不重复计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F58：订阅创建未绑定数据与收件人授权范围，后台可跨组织读取并外发资产变化

- Severity: P0
- Location: `server/apps/cmdb/views/subscription.py:23-76`；`server/apps/cmdb/serializers/subscription.py:61-227`；`server/apps/cmdb/services/subscription_trigger.py:187-218,390-439`；`server/apps/cmdb/services/subscription_task.py:134-147,416-479`；`server/apps/system_mgmt/nats/users.py:5-21,66-102`
- Root cause category: 跨层契约不一致
- Evidence: `SubscriptionViewSet.create` 只有 `asset_info-Add`，直接保存请求中的 `organization/model_id/instance_filter/recipients/channel_ids`；不同于 update/delete，它没有调用 `_check_manage_permission`。Serializer 只检查结构、非空和数量，不验证 organization 是当前组织/授权子组织、模型和实例可见、条件字段可读、recipient users/groups 或 channel IDs 属于该范围。Beat 后台 `_get_current_instances` 和关联名称查询均调用 `InstanceManage` 且固定 `permission_map={}`；收件人组织解析调用全局 `get_group_users` 而不是已有的 `get_group_users_scoped(actor_context, ...)`，直接用户名也不做组织校验。规则的 organization 只用于管理列表，不参与图查询或发送裁剪。
- Trigger: 拥有当前团队 `asset_info-Add` 的普通用户创建规则，填入任意 organization、其他组织实例 ID/可命中它们的条件、其他组织用户/组或未授权渠道；等待 5 分钟 Beat 检测。
- Impact: 后台 system 身份读取调用者无权查看的实例、关联名称、字段变化和配置文件事件，并把模型名、实例名、变化摘要及时间发送给任意指定用户/组织或渠道；伪造 organization 的规则创建后还会从创建者的列表消失，难以及时停用。跨组织资产信息可持续外泄。
- Why existing tests missed it: brief 四文件不包含 Subscription View。Serializer 测试只直接调用纯校验函数并明确接受任意 `users/groups/channel_ids`；Trigger 测试 mock `InstanceManage`，没有断言 permission map 或组织 scope；收件人测试固定调用不带上下文的 fake `get_group_users`，反而锁定全局接口。没有普通用户跨组织创建到真实发送的负向 E2E。
- Minimal safe fix: create/update 统一从请求 actor context 解析允许组织，拒绝未授权 organization；在保存前校验模型、显式实例、条件字段、关联模型、用户/组和渠道均属于该 scope。规则持久化不可伪造的授权快照/actor context；Worker 每次读取时仍以 rule organization 构造 fail-closed permission map，并使用 `get_group_users_scoped`/scoped channel API。禁止仅靠前端候选列表约束。
- Required tests: 普通用户创建父/子/旁系组织规则，跨组织 instance IDs 与条件、不可见模型/字段/关联、跨组织直接用户/组/渠道全部 4xx 且零规则/零 Delivery；合法子组织正向；后台断言非空 permission map 和 scoped RPC；规则 scope 变更/用户失权后停止发送；真实 Delivery 内容只包含授权资产。
- Long-term design note: 订阅不是纯后台报表，而是“授权数据读取 + 外部披露”能力；规则必须持久化并在检测、渲染、收件人解析、渠道发送四阶段重复验证同一授权上下文。

### Finding CMDB-F59：变更记录列表、详情和导出使用全局 queryset，无法按组织或实例权限裁剪

- Severity: P0
- Location: `server/apps/cmdb/views/change_record.py:23-114`；`server/apps/cmdb/models/change_record.py:45-67`；`server/apps/cmdb/serializers/change_record.py:6-22`
- Root cause category: 跨层契约不一致
- Evidence: `ChangeRecordViewSet.queryset = ChangeRecord.objects.all()`；list/retrieve/export 都只声明 `operation_log-View`，没有覆盖 `get_queryset`，也没有按当前团队、模型或实例调用权限服务。`retrieve` 直接 `get_object`，export 对同一全局过滤 queryset 截取 50000 行。`ChangeRecord` 模型没有 organization、owner scope 或可验证的资源引用；before/after JSON 中也不保证存在可信 organization，Serializer 原样返回完整前后数据。
- Trigger: 任一组织普通用户获得 `operation_log-View`，调用列表/按 model、operator、时间过滤、猜测主键详情或 export；数据库中同时存在其他组织的实例、采集任务、模型管理或自定义上报变更。
- Impact: 用户可枚举和批量下载全部组织的实例 ID、模型、操作者、消息以及完整 before/after 快照；字段可能包含地址、配置元数据和其他业务属性。由于记录缺少权威组织归属，事后无法可靠补做查询裁剪或证明一次导出只覆盖授权数据。
- Why existing tests missed it: brief 四文件不包含 View 测试且 coverage 没有 `views/change_record.py` 行。补充静态检查发现 `test_change_record_views.py` 所有 list/retrieve/export 正向用例都使用 superuser，只断言 200/文件头；没有两个组织、普通有权限用户、实例权限或不可见记录测试。
- Minimal safe fix: 在写入时持久化不可变 `organization`/资源 scope（创建、更新、删除均从可信服务上下文生成），为历史记录制定显式迁移/不可判定策略；View 统一从当前 actor 的组织与实例权限构造 queryset，详情和导出复用同一 scope。无法确定归属的历史行默认仅超管可见，不能从可伪造 JSON 猜测。
- Required tests: 两组织普通用户 list/retrieve/filter/export 隔离，子组织规则、实例级 deny、删除后记录、模型/采集/自定义上报场景、无 scope 历史行 fail closed、超管正向，以及导出行数/内容与列表同 scope。
- Long-term design note: 审计记录必须在产生时携带授权维度；“谁能看审计”不能依赖已删除图实体或不可信 before/after 投影。

### Finding CMDB-F60：ChangeRecord 镜像按单条/批量采用不同事务模型，既可能丢失、幽灵化也可能重复

- Severity: P1
- Location: `server/apps/cmdb/utils/change_record.py:33-125,153-196`；`server/apps/cmdb/services/change_record_mirror.py:30-109`；`server/apps/cmdb/services/collect_service.py:423-469`
- Root cause category: 重复逻辑导致的不一致
- Evidence: 单条 `create_change_record` 在本地行创建后立即 `_mirror_change_record → SystemMgmt.save_operation_log`；异常被吞并且没有 delivery、attempt 或 Beat 重放。该函数可在采集 CRUD 的 `transaction.atomic` 内调用，故外层事务之后回滚时平台 OperationLog 已不可回滚。批量与关系路径则创建 Outbox 并 `transaction.on_commit` 派发，避免该时序，但一个 Outbox 保存最多 100 个 payload；consumer 逐条 RPC，任一异常把整行置 RETRY/FAILED，不记录成功下标或每项幂等键。第 N 条失败后，前 N-1 条已成功写入平台，下一次从第 1 条重放。`event_id` 只标识本地 Outbox，不进入 `save_operation_log` payload，SystemMgmt 无法据此去重。
- Trigger: 单条管理/采集/自定义场景 RPC 暂时失败，或本地外层事务在 RPC 成功后回滚；批量 Outbox 的第 2–100 条暂时失败，或 Worker 在部分 RPC 成功后崩溃/租约过期。
- Impact: 同一业务类型因调用基数不同出现三种外部结果：源记录存在但平台镜像永久缺失、源事务不存在但平台留有幽灵操作、同一变更多次出现在平台日志。审计对账、告警和合规导出无法判断真实操作次数；5 次失败后整批进入 FAILED，既没有人工重放 API，也无法只补失败项。
- Why existing tests missed it: 单条测试明确只断言 RPC 失败“不影响 ChangeRecord”，未断言 durable retry 或事务回滚；批量测试只覆盖 100 次全成功、broker 失败保持 PENDING 和 Beat 字符串注册。没有第 N 条失败、进程崩溃、租约接管、attempt_count 代次、跑满 5 次、单/批 payload 等价或下游幂等断言；Mirror Service 覆盖率仅 75%。
- Minimal safe fix: 所有需镜像场景统一在 ChangeRecord 同一数据库事务创建“一条源记录对应一条 delivery”，提交后派发；payload 带稳定 event ID，下游 `save_operation_log` 以该 ID 幂等 upsert。若保留批发送，也必须逐项 checkpoint/结果并只重试失败项；FAILED 提供可审计重放入口和告警。
- Required tests: 单条 RPC 失败后 Beat 重试、外层事务回滚零外部发送、单/批 payload 完全一致；100 条第 2/50/100 条失败只补失败项；Worker 部分成功崩溃、租约接管、旧 owner 晚到、5 次终态、人工重放、相同 event ID 下游去重和敏感错误脱敏。
- Long-term design note: ChangeRecord 是源事实，OperationLog 是异步投影；投影协议应以 per-record event ID 和消费者幂等表达，不应由调用方按单条/批量选择可靠性语义。

### 跨域证据与不重复计数风险

- `CMDB-F23`：`check_rules` 一次性加载全部启用 rule IDs 和全部 ready delivery IDs；每条规则的实例分页没有最大页数/实例总量/deadline，随后关系、关联名称和 ChangeRecord 全量物化。Mirror 只限制每行 100 个 payload 和每轮恢复 100 个 event，却不限制调用方 change_records、Outbox 总行数或 RPC 总耗时。该“批次/扫描/内存/外部调用无统一预算”与自动采集主 Finding 同根因，本域不重复计数。修复须覆盖异常 count/重复页、大规则/实例/关系/变更/Delivery 积压、每轮 deadline 与公平游标。
- `CMDB-F25`：`_decode_event_dicts` warning 原样记录非法 `item`，Trigger/Task 多处记录 `error={exc}` 与 traceback，Delivery 把下游 `message` 原样写 `last_error`；现有测试输出实际展示完整非法 payload 和异常文本。该敏感错误面沿用既有主 Finding，不重复计数；应只记录 rule/delivery/event ID、阶段和白名单错误码，正文/字段值/下游响应经统一 sanitizer。
- Delivery 正向证据：SHA-256 对 canonical event group+rule+channel 去重；规则快照和 Delivery 同事务，delivery 写失败会回滚 checkpoint；broker 失败下轮扫描 PENDING；15 分钟 SENDING 恢复、claim 原子加 attempt、成功/失败按 attempt_count 条件收敛；规则停用/删除和事件无法解码首次即 FAILED。外部发送成功但进程在 SENT 更新前退出仍可能重复，这是已批准“至少一次”模型的固有限制；长期应把 `dedupe_key` 传给 SystemMgmt/渠道 provider 做幂等，不能把测试中的“第二次调用已 SENT 不再发送”等同于崩溃窗口 exactly-once。

## 3. Test Review

按简报在 `server/` 使用显式 SQLite、Celery 和 MinIO 环境运行四文件并测量七个目标模块：

`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task12-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_change_record_mirror_service.py apps/cmdb/tests/test_change_record_mirror_outbox.py apps/cmdb/tests/test_subscription_trigger_service.py apps/cmdb/tests/test_subscription_task_service.py --cov=apps.cmdb.views.change_record --cov=apps.cmdb.utils.change_record --cov=apps.cmdb.services.change_record_mirror --cov=apps.cmdb.services.subscription_trigger --cov=apps.cmdb.services.subscription_task --cov=apps.cmdb.models.change_record --cov=apps.cmdb.models.subscription_delivery --cov-report=term-missing`

首次在沙箱内因无权读取 `~/.cache/uv/sdists-v9/.git` 退出 2，未进入收集；受控权限重跑为 **82 passed in 3.28s，exit 0**。覆盖率：ChangeRecord Model 100%、SubscriptionDelivery Model 100%、Mirror Service 75%、SubscriptionTask Service 98%、SubscriptionTrigger Service 70%、ChangeRecord utils 74%，六个实际导入模块合计 **82%**（916 statements / 165 missed）。虽然指定了 ChangeRecord View，四文件未导入它，coverage 没有该模块行；因此不能声称查询/导出入口达到 80%。Trigger、Mirror 和 utils 也未达相关模块 80%，核心触发/镜像未达 90%。

有效证明：

- Delivery 唯一键、删除规则后快照保留、事件 canonical 分组和同事件不新增 delivery。
- checkpoint 与 Delivery 同事务，Delivery 持久化失败回滚快照；broker 失败后下一轮重新派发已有 PENDING。
- 首次 RPC 失败进入 60 秒 RETRY，第三次失败 FAILED；规则删除/停用和事件解码失败是永久错误。
- 过期 SENDING 可恢复；新租约把 attempt_count 推进后，旧 Worker 的终态条件更新失败。
- Mirror 批量 250 条分成 3 行、单 Worker 最多发送 100 次；broker 失败保留 PENDING，Beat 配置存在。
- 关联查询失败保留旧快照的局部分支、ChangeRecord 时间窗口、到期去重和通知聚合的若干纯函数/DB 行为。

证明力不足：

- “同一 delivery 重投只发送一次”只是在首轮已写 SENT 后再次调用；没有覆盖外部已发送、SENT 未落库的崩溃窗口，也没有向下游传幂等键。
- 旧 Worker 测试直接在 `_send_delivery` mock 内改 attempt_count，没有真实租约扫描/并发 RPC；没有旧 Worker 外部发送晚到、失败终态晚到或真实多进程。
- Trigger 的 `process` 只完整覆盖空实例；`_get_current_instances`、批量/逐实例关系 fallback、大量关联变化和配置文件成功事件大量未覆盖，Trigger 仅 70%。
- 没有规则 View、organization/model/instance/condition/recipient/channel 授权测试；现有收件人测试固定全局 `get_group_users` 行为。
- 没有 ChangeRecord 普通用户两组织 list/retrieve/export；补充静态测试文件全部使用 superuser。
- Mirror 没有单条事务回滚、失败重试、批内部分成功、租约接管、5 次 FAILED、人工重放、per-payload 幂等和 payload 一致性。
- 所有 SystemMgmt、Graph、broker 都是 Mock；未验证真实 NATS/渠道 provider、FalkorDB、MySQL/PostgreSQL、积压与资源上限。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：Subscription Delivery 状态枚举、退避和代次较集中；但授权只存在于 View 列表，后台 system 查询与收件人 RPC没有显式 scope，读代码容易误以为 rule.organization 已生效。
2. 新增同类插件是否需要复制代码：新增 Trigger type 需同时改常量、Serializer、Trigger、snapshot、内容格式和测试；Mirror 单/批还要选择两套路径，复制风险高。
3. 新增错误类型是否需改多个模块：是。图查询、事件解码、收件人解析、渠道返回和 broker 异常分别用跳过、ValueError、RuntimeError、字符串 message 表达，没有统一 error code/sanitizer。
4. 新增 callback 模式是否容易扩展：Delivery ID 是良好入口，但没有向下游传播幂等/回执协议；新增渠道仍只能把 RPC 返回当最终发送结果。
5. 当前接口是否容易被误用：是。Serializer 接受任意组织/用户/组/渠道，Trigger 的 `permission_map={}` 和 SystemMgmt 的非 scoped 方法都是看似方便但会绕过边界的接口。
6. 日志是否足够且不泄密：rule/delivery/event 数量日志有助定位；非法 event、异常和下游 message 原样记录/持久化，引用 `CMDB-F25`，未满足脱敏要求。
7. 状态异常时能否判断停在哪个阶段：Delivery 可以判断待发/发送/重试/终态；规则检测只有 last_check/snapshot，没有单轮 run/owner/deadline；单条 Mirror 完全无状态，批量 FAILED 无重放闭环。
8. 设计是否降低复杂度：事务内 checkpoint+Delivery、租约和代次降低了通知重投复杂度；授权上下文丢失、全规则长事务和两套 Mirror 语义把复杂度转移到数据泄露、重复日志和人工对账。

## 5. Recommendation

**Block**。

发布前先关闭两个 P0：订阅规则从创建到查询、收件人和渠道全链绑定同一 actor/organization scope；ChangeRecord 在写入时固化可信组织并让 list/detail/export 复用同一权限裁剪。随后关闭 `CMDB-F60`，把所有管理类镜像统一为 per-record durable、幂等的提交后投影。跨域 `CMDB-F23/F25` 的资源预算和脱敏也必须覆盖本域。82 个测试通过和 82% 聚焦总覆盖率不能抵消 View 零覆盖、Trigger 70% 及跨组织负向测试缺失。
