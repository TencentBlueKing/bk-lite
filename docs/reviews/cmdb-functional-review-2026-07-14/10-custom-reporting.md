# CMDB Enterprise 自定义上报生产级审查

## 1. Summary

社区层提供稳定 URL、序列化和扩展门面：登录态任务接口委派给 `custom_reporting` registry，公开 ingest 明确使用 `OpenAPIViewSet`、`AllowAny`、空 DRF authentication，真实认证完全由 Bearer/raw token 承担。未安装 Overlay 时，读列表/统计为空，任务写、凭据、审核和 ingest 明确返回“商业版能力未启用”，不会偷偷落入社区写路径；安装 Overlay 时，`CmdbEnterpriseConfig.ready()` 注册 provider，链路进入任务/组织、凭据、批次、快速模型字段、实例合并、关系待处理、快照/过期清理和审核。

本次 Overlay 证据不是当前审查分支可独立复现的仓库内容。根仓库 `enterprise` 只记录 gitlink `7c7db340961d6b010d2c533de92970df253b545f`，`git submodule status enterprise` 前缀为 `-`；指定 worktree 没有 `server/apps/cmdb_enterprise/`。主工作区存在被 `.gitignore:59` 整目录忽略的安装态 Overlay，本报告对其只读审查并只读运行测试：15 个 `custom_reporting` Python 源文件清单聚合 SHA-256 为 `1c4d5f1b9e3cbfb17798faf119779565e33bc1d23db7bba61e04cf519ff25ed9`，简报六测试文件聚合 SHA-256 为 `0e4b7eee9e8361f1479546444287ae2c540f303edfc8658c7d9f2ec5f47c8043`。因此结论代表 2026-07-14 主工作区的运行态安装内容，不能声称仅从当前主仓库 branch/gitlink checkout 即可重建；发布前必须把 Overlay commit、制品版本和上述内容哈希建立可追溯映射。

认证 token 的签发、轮换和作废采用随机明文一次返回、SQL 只保存 SHA-256、常量时间比较；作废凭据和停用任务会拒收。任务详情等既有对象接口也校验请求组织与 task.team 交集。但控制面创建/改组未验证新 team，数据面又仅按 model_id 读取全图实例；这两个边界可让低权限登录用户或合法任务 token 跨组织写入、覆盖和删除资产。快照路径还会把本次更新失败的旧实例当成“未覆盖”直接清理，同时批次仍标 SUCCESS。空 identity_keys 则使整批以空元组折叠，只落最后一条且 errors=0。

本域新增 6 个主 Finding：`CMDB-F52`–`CMDB-F57`，P0 3/P1 3/P2 0/P3 0。关系双端授权引用 `CMDB-F14`，批次写唯一锁引用 `CMDB-F10`，清理跨存储恢复引用 `CMDB-F11`，所有请求/实例/关系/字段/扫描预算引用 `CMDB-F23`，不重复计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F52：任务创建和改组不校验新组织范围，可签发跨组织写 token

- Severity: P0
- Location: `server/apps/cmdb/views/custom_reporting.py:11-32,79-89`；`server/apps/cmdb/serializers/custom_reporting.py:4-17`；`server/apps/cmdb_enterprise/custom_reporting/provider.py:30-62,79-81,112-117`；`server/apps/cmdb_enterprise/custom_reporting/services/task_service.py:211-263,279-318`
- Root cause category: 跨层契约不一致
- Evidence: 任务 ViewSet 没有 `HasPermission` 等显式功能权限；create serializer 接受任意非空 `team`，provider.create_task 直接下传，不调用 `_allowed_orgs`。update 只用 `_require_task` 校验调用者与“修改前 task.team”相交，随后允许把 team 替换为任意 ID。create 在同一响应返回新 token；ingest 是 AllowAny 且不依赖 request.user/cookie，token 解析成功后 `Management(organization=task.team)` 写入该 team。现有 `_require_task` 只能保护已经存在对象的管理接口，不能证明新绑定组织属于调用者。
- Trigger: 任意已登录用户创建 `team=[受害组织]` 的 standard/quick 任务，或先访问自己组织任务再 update 为受害组织；取得 create 返回或既有凭据 token 后调用公开 ingest。
- Impact: 调用者不需要受害组织的模型/实例权限即可创建跨组织任务、快速模型和实例；update 后即使管理接口因新 team 不相交而失去访问，已知 token 仍可持续写入，直到另一个有权用户作废凭据或停用任务。
- Why existing tests missed it: `test_custom_reporting_authz.py` 只验证“已有 team=[1] 的任务由 allowed=[2] 访问”被拒，并明确不覆盖 create；update 负向用空 payload，在调用 service 前就被旧 team guard 拒绝。六个简报测试没有真实 View 功能权限、create team、update team 或 token 后续 ingest 组合。
- Minimal safe fix: Task ViewSet 声明显式 View/Edit/Execute 权限；create 和 update 在任何模型/任务副作用前，以统一组织解析器验证 payload.team 非空且是调用者允许组织的子集。改组应作废或重新绑定旧 token，并让模型 group、task scope 和凭据绑定在一个可恢复的持久化状态机中。
- Required tests: 普通用户创建他组织任务 403 且零模型/任务/凭据写；update 自组织→他组织 403 且旧 scope/token 不变；混合 team、include_children、管理员正向；权限关闭入口；成功改组时旧 token 立即失效且新 token 只能写新范围。
- Long-term design note: “任务控制权限、组织绑定、凭据能力范围”应由一个 capability policy 统一签发和校验，不能让 HTTP provider、task service 和 ingest 分别推断。

### Finding CMDB-F53：实例合并和清理只按 model_id 扫描，任务组织隔离在数据面失效

- Severity: P0
- Location: `server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py:57-105`；`server/apps/cmdb_enterprise/custom_reporting/services/cleanup_service.py:70-108,187-240`
- Root cause category: 跨层契约不一致
- Evidence: `merge_instances` 以 `model_id` 无分页加载全部 `old_items`，没有 task ID、`collect_task=cr_<task.id>` 或 organization 条件；Management 以 identity 匹配后会把命中的旧节点更新为当前 `task.team`。snapshot 直接用这份全模型 old_ids 减本批 covered_ids 并删除。每日 expire 也对每个任务按 model_id 加载全模型，仅比较公共 `cr_last_reported_at`，没有验证节点属于当前任务/组织。同模型被多个组织、多个上报任务或人工/采集路径共享时，task.team 只控制写入的新 organization，不能控制候选和删除集合。
- Trigger: 两个组织/任务共享 model_id 且 identity 相同或 cleanup_strategy=snapshot/expire；任一合法 token 上报部分快照，或过期 Beat 处理其中一个任务。
- Impact: 合并可把他组织同 identity 节点改组并覆盖；快照可删除本任务从未拥有的全模型节点；expire 可由一个任务删除另一任务/组织的旧上报资产。合法凭据因此具备超出 task.team 的跨租户图写和批删能力。
- Why existing tests missed it: ingest 测试完全 monkeypatch merge；merge 测试只断言 collect_time 类型且 fake graph 返回空集合；cleanup 测试注入单任务 IDs 并 monkeypatch `_delete_instances`，没有同模型多任务、多组织或人工实例。没有测试断言 Graph 查询必须包含 task/organization scope。
- Minimal safe fix: 为每个自定义上报实例持久化不可伪造的 owner task ID/组织 scope；merge 候选、snapshot 和 expire 都必须用 owner+organization 有界查询。历史无 owner 节点应 fail closed 并进入显式迁移/审核，不能被现任务默认接管或删除。
- Required tests: 同 model 不同 task/team 相同 identity 不互相覆盖；snapshot/expire 只处理 owner scope；人工/自动采集节点不受影响；任务改组、历史无 owner、混合组织、并发上报和大模型分页边界。
- Long-term design note: organization 是访问范围而不是数据来源身份；自定义上报需要稳定 source ownership，清理只能针对该 source 的完整快照。

### Finding CMDB-F54：部分更新失败仍成功结批，snapshot 会把失败实例当陈旧数据删除

- Severity: P0
- Location: `server/apps/cmdb_enterprise/custom_reporting/services/ingest_service.py:81-115`；`server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py:104-166`；`server/apps/cmdb_enterprise/custom_reporting/services/cleanup_service.py:70-108`
- Root cause category: 状态机设计缺陷
- Evidence: Management 对每条 add/update 捕获异常并返回 failed；merge 只把 success 的 `_id` 放入 covered_ids，同时把失败数放入 errors。ingest 不因 errors>0 失败或进入 PARTIAL，而是继续 snapshot。apply_snapshot 以 `old_ids - covered_ids` 清理，所以本次明确尝试更新但失败的旧实例也进入 delete_ids；低于阈值或阈值为 0 会立即删除，高于阈值只靠人工发现。随后 batch 无条件置 SUCCESS，last_reported_at 也推进。
- Trigger: snapshot 任务上报包含已有实例，其中至少一条因字段、唯一约束或图调用失败；删除比例不超过审核阈值（默认/配置 0 表示全部直删）。
- Impact: 暂时性更新失败被转换为不可逆删除，调用方只看到 HTTP 成功和 summary.errors；批次/任务时间戳宣称已接收，重投没有持久化失败项或恢复游标，用户可能在下次完整快照前永久丢失资产和关系。
- Why existing tests missed it: ingest fake merge 固定 errors=0、old_data=[]；cleanup 测试自行提供 covered_ids，不构造“payload 中存在但更新失败”的实例；BDD 用内存 fake 只返回全成功。没有 partial batch 状态、失败项持久化或失败后不得 cleanup 的断言。
- Minimal safe fix: 只在本批实例合并和必要关系阶段全部成功、且具有完整快照证明时才运行 cleanup；任何 per-item failure 应进入 PARTIAL/FAILED，持久化失败 identity 与可重投状态，并禁止推进完整快照游标。删除操作仍需独立 durable operation/审核。
- Required tests: update/add 各阶段单条失败、混合成功失败、阈值 0/等于/超过、重投成功、重复重投、Batch/last_reported_at 状态，以及失败项不进入 delete_ids；修复后验证 cleanup 只消费已确认完整的 snapshot generation。
- Long-term design note: snapshot 是一份带 generation 的完整性声明，不是“HTTP 收到一个列表”；merge、关系和 cleanup 应共享同一批次状态机和可恢复 checkpoint。

### Finding CMDB-F55：空 identity_keys 把整批静默折叠为最后一条实例

- Severity: P1
- Location: `server/apps/cmdb/serializers/custom_reporting.py:4-17`；`server/apps/cmdb_enterprise/custom_reporting/services/task_service.py:224-263,279-318`；`server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py:57-105`；`server/apps/cmdb/collection/common.py:54-73`
- Root cause category: 局部实现错误
- Evidence: 任务 serializer 只把 config 当任意 DictField，create/update 不验证 `identity_keys` 非空、存在于模型或值非空。merge 在空 keys 时跳过 coercion，但仍构造 Management；Management.format_data 对每条 new_data 使用 `tuple(info[key] for key in []) == ()` 作为 dict key，后记录覆盖前记录。最终 add/update 只处理最后一条，errors 为 0，summary.instances_received 仍是原始数量。
- Trigger: 创建/更新 standard 或 quick 任务时省略 identity_keys 或设置 `[]`，随后一次上报两条以上实例。
- Impact: 接口和批次成功但 N 条只落 1 条；snapshot 模式还会把其余旧实例视为未覆盖并触发删除/审核。数据丢失没有失败项可重投，调用方只能通过事后数量对账发现。
- Why existing tests missed it: ingest/BDD fixture 一律配置 `['biz_id']`；merge 纯函数只覆盖类型转换；任务配置测试不在简报六文件内，且没有 serializer→Management 的空键集成断言。
- Minimal safe fix: create/update 时校验规范化后的 identity_keys 至少一个、字段已声明且配置与 quick_model 一致；ingest 再做防御性校验并在建 Batch/写图前拒绝。每条实例必须包含全部 identity 且值满足明确空值规则。
- Required tests: 缺失/空/重复/未知 identity_keys，实例缺键/空值，update 把有效配置改空，两个实例 identity 相同，以及无任何图/字段/cleanup 副作用的 4xx 失败。
- Long-term design note: identity schema 应成为版本化任务契约并随 token/batch 固化，不能每次从可任意浅合并的 JSON config 动态解释。

### Finding CMDB-F56：字段与关系 schema 校验扩展已声明但未接线，非法载荷可直接写图

- Severity: P1
- Location: `server/apps/cmdb/custom_reporting/extensions.py:18-25`；`server/apps/cmdb/services/model.py:591-609`；`server/apps/cmdb_enterprise/custom_reporting/provider.py:16-148`；`server/apps/cmdb_enterprise/custom_reporting/services/ingest_service.py:60-86`；`server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py:61-105`；`server/apps/cmdb_enterprise/custom_reporting/services/relation_service.py:24-49`；`server/apps/cmdb/services/instance.py:1062-1150`
- Root cause category: 跨层契约不一致
- Evidence: 社区 `CustomReportingExtension` 和 ModelManage 已分别声明 `validate_instance_fields`、`validate_relation_fields` 委托点；Enterprise provider 没有覆盖这两个方法，ingest 也从未调用。standard 模式不自动注册字段，Management.add_inst 调 `create_entity` 时只传 required/unique/editable 的 `check_attr_map`，没有 attrs schema，未知字段及 `_` 前缀保留字段会随 properties 入图。关系服务从关联元数据填充 src/dst model_id，但不查询实际 source/target 节点模型是否匹配；下游 `check_asso_mapping` 只检查关联存在和 1:1/1:n/n:1 基数，不校验端点实体模型。
- Trigger: standard 任务上报模型未声明字段或 `_id/model_id/organization/collect_task` 等保留字段；或 relation 指定一个真实 source._id/target identity，但实际节点模型与 model_asst_id 声明端点不一致。
- Impact: 图节点可出现模型 schema 外属性或覆盖框架保留元数据；关系边声明的 src/dst_model_id 与真实端点类型不一致，后续拓扑、权限、清理和关联格式化基于错误 schema 工作。该缺陷即使调用者对两端都有权限也成立，因此不同于 `CMDB-F14` 的关系授权根因。
- Why existing tests missed it: 六文件没有调用社区 validate 委托；ingest 测试把字段注册和 merge 替换为 fake；merge 测试只验证 collect_time；relation 测试 mock `_resolve_instance/_create_edge`，`test_create_edge_enriches_model_ids` 只断言元数据被复制，不构造实际端点模型错配。没有“校验失败时零字段/实例/边写入”的断言。
- Minimal safe fix: 由 Enterprise provider/adapter 实现唯一 schema validator，并在创建 Batch、自动字段或任何图写前调用；quick 模式只允许经策略批准的新业务字段，standard 模式拒绝未声明/保留字段。关系 validator 必须读取关联定义和实际端点，验证 source 属于 task model、src/dst 实体模型及 identity schema 全部匹配。
- Required tests: standard 未知字段、全部保留字段、quick 新字段 allowlist、字段类型/缺失 identity、source/target 端点模型错配、关联方向错配；每个拒绝场景断言 4xx/明确错误且零模型字段、零实例、零 pending、零边、零 cleanup 副作用。
- Long-term design note: schema 验证是 provider/adapter 的接入契约，应在 payload 进入通用 Management/InstanceManage 前一次完成，图驱动不应猜测业务 schema。

### Finding CMDB-F57：Beat 已配置过期清理，但 Celery 自动发现入口没有注册该任务

- Severity: P1
- Location: `server/apps/cmdb_enterprise/config.py:3-13`；`server/apps/cmdb_enterprise/tasks/__init__.py:1-2`；`server/apps/cmdb_enterprise/custom_reporting/tasks.py:1-11`；`server/apps/core/celery.py:12-14`
- Root cause category: 架构职责放置错误
- Evidence: Enterprise config 把 Beat task path 配为 `apps.cmdb_enterprise.custom_reporting.tasks.custom_reporting_expire_cleanup`；Celery 只执行 `app.autodiscover_tasks()`，对 app 自动导入约定入口 `apps.cmdb_enterprise.tasks`。该入口当前只导入 `instance_ops.tasks.cleanup_attachment_files`，没有导入 custom_reporting task。只读复现调用 `app.loader.import_default_modules()` 后，目标 task `registered=False`，Enterprise 已注册任务列表只有附件 cleanup。
- Trigger: 启用 `cmdb_enterprise` 和 Celery/Beat，配置 expire cleanup 任务后到达每日 04:00 调度时间。
- Impact: Beat 可持久化并发送一个 Worker 未注册的 task name，Worker 报 unregistered task 并丢弃；expire 策略从未自动清理，页面却持续展示已配置策略，过期资产无限残留且没有本域状态/告警回写。
- Why existing tests missed it: 简报 cleanup 测试直接调用 `cleanup_service.expire_cleanup()`；没有启动 Celery autodiscover 或断言 Beat schedule 中每个 task name 都存在于 `app.tasks`。`tasks.py` 覆盖率为 0%，config 和 `tasks/__init__.py` 不在六文件断言内。
- Minimal safe fix: 在标准 Celery app 入口显式导入/注册 custom_reporting tasks（例如 `apps.cmdb_enterprise.tasks.__init__` 导入该模块），并以统一任务注册表生成/校验 Beat schedule；启动时发现 schedule 引用未注册任务应 fail fast 或告警。
- Required tests: Django/Celery 集成测试执行 autodiscover 后断言目标全限定名在 `app.tasks`；Beat schedule 的每个 Enterprise task 都可解析；eager Worker 实际执行 expire service；未注册回归、重复 import 幂等和 Overlay 缺失模式不产生悬空 schedule。
- Long-term design note: 任务定义、自动发现和 Beat 配置应同属一个可验证 registry，不能靠相隔目录的字符串路径和隐式 import 约定维持一致性。

### 跨域证据与未重复计数风险

- `CMDB-F14`：relation payload 可直接给任意 `source._id`，target 又用 model_id+identity 全局解析，随后直接调用 `instance_association_create`，没有验证 source 属于 task model/team 或关联两端组织；这是既有“关系写只信中心/单端上下文”的同一根因，本域不重复计数。
- `CMDB-F10`：custom reporting 的 Management 批写同样绕过单实例 `UniqueWriteLockService`；并发相同 identity 或重投可同时读到不存在并重复建图，归入既有批量写唯一锁根因。
- `CMDB-F11`：snapshot/expire/approve 都直接“读图快照→删图→写 SQL 审计/审核状态”，无 Operation、幂等 key、owner 或崩溃恢复；approve 并发/图删后进程退出可重复删或让审核永久 pending，归入既有批量删除跨存储状态机根因。
- `CMDB-F23`：公开 ingest 没有 body bytes、instances、relations、字段数/字段名长度、pending 或 deadline 上限；token 认证扫描全部 enabled credential，merge 全量物化模型，backfill 每次遍历全 task pending，expire 再逐任务全模型加载。该资源边界与自动采集执行/清理无批次和内存预算是同一主根因，本域不重复计数。
- 重投确定行为：ingest 没有 idempotency key、payload hash 或 snapshot generation，相同请求每次都新建 Batch，并再次写实例变更审计；未解析关系每次都直接插入 `CustomReportingPendingRelation`，模型没有业务唯一约束，故重复重投会积累相同 pending。并发相同 identity 的图写竞态引用 `CMDB-F10`；Batch、重复审计、pending 和 cleanup 的副作用/恢复闭环引用 `CMDB-F11`，不新增计数。修复必须测试相同 key 同 payload 复用、同 key 冲突、无 key 的明确语义、并发重投单 owner、pending/审计去重、snapshot generation 只提交一次，以及失败后按原 generation 安全续跑。
- 凭据正向证据：token 只在签发/轮换响应中返回，持久化前转 SHA-256，序列化去掉 token/token_hash；`compare_digest` 比较，revoke 清 hash 并禁用，停用任务也拒收。当前仍缺 credential ID 前缀索引、轮换/作废并发代次和速率限制证明。

## 3. Test Review

Overlay 启用模式在主工作区 `server/` 只读运行简报六文件，并设置 `PYTHONDONTWRITEBYTECODE=1`。首次因沙箱不能读 `~/.cache/uv/sdists-v9/.git` 未进入收集；受控权限重跑命令为：

`PYTHONDONTWRITEBYTECODE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run pytest -q -o addopts='' apps/cmdb_enterprise/tests/test_custom_reporting_authz.py apps/cmdb_enterprise/tests/test_custom_reporting_ingest_service.py apps/cmdb_enterprise/tests/test_custom_reporting_merge_service.py apps/cmdb_enterprise/tests/test_custom_reporting_relation_service.py apps/cmdb_enterprise/tests/test_custom_reporting_cleanup_service.py apps/cmdb_enterprise/tests/bdd/test_custom_reporting_bdd.py --cov=apps.cmdb_enterprise.custom_reporting --cov-report=term-missing`

结果 **38 passed in 25.02s，exit 0**。15 个 Overlay 模块合计 **59%**（808 statements / 333 missed）；models 92%、provider 67%、activity 21%、cleanup 81%、credential 32%、document 27%、field 27%、ingest 78%、merge 73%、model 20%、relation 84%、task 17%、tasks 0%。相关模块 80% 和核心路径 90% 均未达到。

Overlay 缺失模式在指定 worktree 运行社区扩展与委托测试：`PYTHONDONTWRITEBYTECODE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_custom_reporting_extension.py apps/cmdb/tests/test_model_custom_reporting_delegation.py`，结果 **6 passed in 0.07s，exit 0**。它有效证明默认列表为空、写入口明确拒绝、模型字段 no-op 和 registry 委托；不证明 Overlay 打包版本或企业注册成功。

Celery 注册补充复现命令：`PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise ENABLE_CELERY=true uv run python -c "import django; django.setup(); from apps.core.celery import app; app.loader.import_default_modules(); name='apps.cmdb_enterprise.custom_reporting.tasks.custom_reporting_expire_cleanup'; print('registered=', name in app.tasks); print('enterprise_tasks=', sorted(k for k in app.tasks if k.startswith('apps.cmdb_enterprise')))"`。结果为 `registered=False`，Enterprise 任务只有 `apps.cmdb_enterprise.instance_ops.tasks.cleanup_attachment_files`。

六文件有效证明：已有 task 的错误组织被 provider 拒绝；坏/作废 token 与停用任务拒收；成功 ingest 建 Batch；身份类型 coercion；关系可建/进入 pending/backfill；快照阈值和审核基本行为。BDD 的“端到端”合并实际是有状态内存 fake，图、Management、权限、字段、关系和 cleanup 均未穿透。

证明力不足：没有 create/update 新 team、View 功能权限、同模型跨任务/组织、真实 partial failure、空 identity、schema/保留字段/端点模型、真实并发重投与幂等 key/generation、请求/字段预算、token 大表、PendingRelation 去重、崩溃恢复、FalkorDB/Neo4j、多数据库和真实 Beat→broker→Worker。测试输出还含预期 BaseAppException 的 ERROR 日志和根 pyproject 无 project table 的 uv warning；虽不影响退出码，但生产日志分类和测试噪声仍需治理。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：社区门面和 provider 分层清晰；但 Overlay 仅是 ignored 安装态，来源 commit/制品不可追溯，维护者无法从主仓库 branch 重建审查对象。
2. 新增同类插件是否需要复制代码：provider 合约降低社区耦合；任务、token、Batch、merge、关系和 cleanup 仍是自定义专用编排，若新增上报源会复制身份、scope、重投和资源控制。
3. 新增错误类型是否需改多个模块：是。Management 把单条异常压成 failed，ingest 再解释为 success；字段、关系和 cleanup 异常则整批 failed，没有统一 partial/error taxonomy。
4. 新增 callback 模式是否容易扩展：没有 callback/outbox 或批次 generation；关系 pending 只是无唯一键的载荷表，无法安全扩展结果确认与重投。
5. 当前接口是否容易被误用：是。config 是任意 JSON；create_task 默认信任 team，relation 信任 source._id，cleanup 接受裸 ID 列表，调用者很容易绕过真实 ownership。
6. 日志是否足够且不泄密：批次只持久化异常字符串和摘要，没有逐项失败/阶段/owner；token hash 未序列化是优点，但预期鉴权拒绝统一打 ERROR 会产生噪声。
7. 状态异常时能否判断停在哪个阶段：不能。Batch 只有 running/success/failed，字段已创建、部分实例写入、关系 pending、图已删/审计未写等阶段均无 checkpoint。
8. 设计是否降低复杂度：稳定社区接口和 one-per-task credential 降低了接入复杂度；跨组织 scope、身份、批次完整性和清理恢复没有统一框架，复杂度被推迟到数据对账和人工修复。

## 5. Recommendation

**Block**。

发布前必须先关闭三个 P0：任务新组织绑定必须 fail closed；所有 merge/cleanup 候选必须以不可伪造 owner+organization 裁剪；任何部分失败都不得启动 snapshot 或标 SUCCESS。随后修复空 identity 静默折叠，接通字段/关系 schema validator，确保 Worker 实际注册过期清理，并落实跨域 `CMDB-F10/F11/F14/F23` 的唯一锁、删除状态机、关系双端授权和资源预算。Overlay 还必须给出可 checkout 的确切 commit 或不可变制品清单；38 个通过测试和 59% 覆盖率不足以批准当前运行态进入生产。
