# CMDB 自动采集生产级审查

## 1. Summary

自动采集已有一组值得保留的正确骨架：create/update 的数据库变更和审计先提交，再通过 `transaction.on_commit` 同步周期任务与节点参数，避免数据库回滚产生幽灵外部配置；手动执行生成 `task_id` 作为 execution ID；结果、异常与 timeout 都以 `id + task_id + RUNNING` 条件写回，现有测试证明旧 execution 不能覆盖新 execution 的任务摘要；超时由 Beat 每 5 分钟巡检，deadline 优先任务参数、其次环境变量、默认 600 秒。凭据池限制为 3 组，编辑/删除凭据会清除对应命中状态；实例 diff 已从全模型扫描改为按本批唯一值查询候选；批量实例审计已通过持久化 outbox 与有界 worker 下沉。

生产阻断点在 execution ownership。`_claim_collect_task_execution` 对“当前已是 RUNNING 且 task_id 相同”的消息仍执行同值 `UPDATE` 并返回成功，因此 broker 重投同一 execution ID 时多个 Worker 都会进入采集。即使 timeout 后新 execution 已接管，execution ID 也只保护 `CollectModels` 最终结果；实例 add/update/delete、association、自动关系派发和审计均不携带 execution fencing，旧 Worker 仍可继续修改图事实。现有“旧 Worker 不能覆盖结果”的测试只证明最后一张 ORM 摘要表，不证明业务副作用隔离。

多凭据派发还有确定的错误成功。最终聚合只保留成功 attempt，失败目标不会进入 `format_data`；只要同批另一个目标成功，Celery 摘要看不到任何失败并写 `SUCCESS`。失败类型又只靠英文字符串关键词判定：中文认证错误不会轮换，含 `password/auth` 文本的业务错误会错误冷却凭据，错误模型不能稳定驱动轮换。

资源与审计同样不满足生产边界。IP 范围在 CMDB Worker 内无上限展开为列表，目标×凭据逐个执行并把全部 collect/format/raw 数据聚合后写入单行 JSON；过期清理按任务全量查询图实例、全量收集 ID 并一次批删，失败批次返回的完整 `expired_ids` 又被日报聚合进 `delete_ids` 并写日志。即时和过期删除都没有实例删除审计。敏感信息风险不止节点下发 debug 日志中的完整解密 `node_params`：dispatch、凭据回调、hit state 和 Celery 摘要还会让任意外部错误文本跨日志、数据库与用户界面传播。

本域确认 6 个主 Finding：P0 3 个、P1 3 个、P2/P3 0 个，编号为 `CMDB-F20`–`CMDB-F25`。采集 CRUD 外部同步无持久化恢复、实例 merge 绕过统一批写编排、关联按名称裸解析分别与既有 `CMDB-F04/F11`、`CMDB-F10/F11`、`CMDB-F14` 同根因，仅记录跨域证据，不重复计数。Recommendation 为 **Request changes**。

## 2. Findings

### Finding CMDB-F20：execution ID 未形成单 owner 与图副作用 fencing

- Severity: P0
- Location: `server/apps/cmdb/tasks/celery_tasks.py:73-92,129-260`；`server/apps/cmdb/collection/common.py:128-278`
- Root cause category: 并发或幂等设计问题
- Evidence: 抢占首先执行 `filter(exec_status=RUNNING, task_id=execution_id).update(...)`；同 token 重投时该更新每次都返回 1，所有 Worker 都取得任务。timeout/新 execution 后，`_save_collect_result_if_current` 能拒绝旧结果，但 `Management` 的图实体、边、自动关系和审计调用只携带持久任务 ID，不读取当前 execution ID，也没有 lease owner/fencing token。已有旧 Worker 测试在采集函数内部把 ORM task_id 改为 B，随后仅断言 A 的摘要未覆盖 B，没有让 A 执行真实图写。该证据不依赖 `CMDB-F12` 的唯一写锁固定 TTL：此处即使唯一写锁完全正确，采集消息同 token 双 owner 与 timeout 后旧 execution 的非唯一字段/删除/关联副作用仍然存在。
- Trigger: broker 对手动执行消息至少一次重投；Worker A 超时后 Beat 置 TIME_OUT，用户或周期任务启动 B，而 A 继续运行；同 token 的两个 Worker 并发消费。
- Impact: 同一批实例可被重复新增/更新/删除和建边；旧采集结果可在新代次之后写入图、发自动关系、生成审计，最终 UI 却只显示新 execution 摘要，事实与状态不可核对。
- Why existing tests missed it: 测试覆盖“无 token 的第二次抢占失败”和“旧 token 不能写回 CollectModels”，未覆盖相同 token 重投、timeout 后真实图写、审计/关联/自动关系副作用或多进程并发。
- Minimal safe fix: 为 execution 建立原子 owner 状态转换和租约；同 token 也只能一个 delivery owner。所有实例/关联写入批次在提交前验证 owner + generation，图实体携带 execution generation，并以可恢复 Operation/Outbox 收敛；旧 owner 在每批前后 fail-closed。
- Required tests: 相同 token 两 Worker 仅一个进入插件和图写；timeout 后旧 Worker 在 add/update/delete/association 各阶段均被拒；broker 重投、Worker 崩溃、租约恢复、旧审计/自动关系零投递；真实并发进程测试。
- Long-term design note: `task_id` 不能同时承担持久采集任务 ID 和 execution owner 语义；使用独立 execution 记录保存 owner、generation、deadline、阶段和批次进度。`CMDB-F12` 约束的是唯一写锁固定 TTL、无续租/fencing；本 Finding 约束独立的采集 execution owner、同 token 重投和全链路副作用 fencing，二者边界不同，不重复计数。

### Finding CMDB-F21：多凭据混合失败目标被聚合丢弃并误报 SUCCESS

- Severity: P0
- Location: `server/apps/cmdb/services/collect_dispatch_service.py:64-135,169-200`；`server/apps/cmdb/tasks/celery_tasks.py:187-248`
- Root cause category: 跨层契约不一致
- Evidence: `merge_attempt_results` 用 object_key 保留最终 attempt 后，对 `not attempt.success` 直接 `continue`，只把成功 payload 合入 `format_data`。Celery 的 PARTIAL_SUCCESS 判断只统计 `format_data` 四类中的 `_status != success`；因此一个目标最终失败、另一个目标成功时，失败计数为 0，状态保持 SUCCESS。全部失败则退化为“未发现任何有效数据”，真实失败目标和凭据尝试原因也不在任务摘要中。
- Trigger: 多目标、多凭据任务中至少一个目标最终失败且至少一个成功；或全部目标认证/业务失败。
- Impact: 资产缺失或陈旧时平台仍显示采集成功，运维无法从任务详情定位失败目标；自动清理和后续拓扑可能基于不完整快照继续运行。
- Why existing tests missed it: 派发测试只覆盖单目标“第一凭据失败、第二凭据成功”；Celery 测试手工返回成功格式或空格式，没有成功/最终失败混合目标。
- Minimal safe fix: 聚合结果必须为每个最终失败目标生成结构化 failure 行，包含 object_key、failure_kind、稳定错误码与脱敏摘要；Celery 直接消费目标级 outcome 计算 SUCCESS/PARTIAL_SUCCESS/ERROR，不能从成功 payload 反推失败。
- Required tests: 1 成功+1 失败为 PARTIAL_SUCCESS；全部失败为 ERROR；失败目标在摘要可见且无 secret；凭据回退成功不误计最终失败；association-only 失败契约明确。
- Long-term design note: 持久化 execution-target-attempt 状态，而非把调度结果压进一个无 schema 的 JSON 聚合。

### Finding CMDB-F25：凭据、节点参数与外部错误缺少统一脱敏边界

- Severity: P0
- Location: `server/apps/cmdb/services/collect_service.py:390-412`；`server/apps/cmdb/node_configs/base.py:51-56,167-188,235-247`；`server/apps/cmdb/services/collect_dispatch_service.py:93-128,203-226`；`server/apps/cmdb/services/collect_credential_result_service.py:34-60`；`server/apps/cmdb/services/collect_hit_state_service.py:59-79`；`server/apps/cmdb/tasks/celery_tasks.py:170-210,253-266`
- Root cause category: 跨层契约不一致
- Evidence: NodeParams 从 `instance.decrypt_credentials` 构建；`push_params` 包含 `env_config`，各驱动将 password、access secret、SNMP community/authkey/privkey 放入其中，`push_butch_node_params` 又直接记录完整 node_params 和 RPC result。dispatch 捕获任意异常后保留 `str(err)`，失败 warning 原样输出前 500 字符并把同一 error_message 交给 hit state；Stargazer 凭据结果回调同样把任意 `data.error_message` 原样写 warning，再由 `CollectHitStateService.mark_failure` 无脱敏写入 `last_error`。普通 Celery 采集异常则由 `_build_safe_error_message` 保留异常文本，写入 `collect_digest.message`；任务 `info`/状态消费者可读取该用户可见摘要。当前没有统一契约保证插件、SDK 或 RPC 异常不含口令、连接串、token、设备输出或远端响应正文。
- Trigger: create/update 非 K8s 任务并启用 debug 日志；插件/SDK/NodeMgmt/Stargazer 把凭据、连接串或敏感响应放入 exception/error_message；用户查看采集详情或下游读取 hit state。
- Impact: 节点参数中的 SSH/数据库/云/SNMP 密钥可进入应用日志；dispatch 或凭据回调携带的敏感外部错误可进入 warning 与 `CollectTaskCredentialHit.last_error`；普通 Celery 异常中的敏感文本可进入用户可见 `collect_digest`。三条实际路径分别扩大日志泄露、持久化泄露和越权查看面，不要求同一次执行同时命中三处。
- Why existing tests missed it: CRUD 测试 Mock 掉 push；dispatch 测试只用固定 `auth failed`；凭据回调、hit state 和 Celery 异常测试没有 canary secret，也未断言日志、DB、API/任务摘要三处均脱敏。
- Minimal safe fix: 在采集错误进入日志或持久化前使用同一递归 redaction/安全错误映射；日志只保留 task/execution/object/credential ID、阶段与稳定错误码；`last_error` 和 `collect_digest` 只保存脱敏摘要，原始诊断若确需保留则进入受控、加密、限时且细粒度授权的存储。
- Required tests: 各驱动 NodeParams 的 canary secret 不出现在 debug/info/warning/error 日志；dispatch 和凭据回调的嵌套/list error_message 在 warning 与 `last_error` 中脱敏；Celery exception 在日志、`collect_digest.message/traceback`、任务 info/API 响应中脱敏；password/token/community/authkey/privkey/access secret/连接串/远端正文及大小上限均覆盖。
- Long-term design note: 脱敏应集中在采集错误边界与 `SecretValue/RedactedPayload` 职责层，日志、命中状态和用户摘要只消费安全类型，避免各调用方重复维护字段黑名单并继续分叉。

### Finding CMDB-F22：凭据与业务错误靠英文文本关键词分类

- Severity: P1
- Location: `server/apps/cmdb/services/collect_dispatch_service.py:44-55,203-270`；`server/apps/cmdb/services/collect_hit_state_service.py:59-79`
- Root cause category: 错误模型不清晰
- Evidence: 捕获异常后仅取 `str(err)`，`_classify_failure_kind` 对小写文本匹配 `auth/password/credential/login/...`。中文“认证失败”、SSH/数据库驱动的结构化错误码或超时无法稳定轮换；业务校验消息只要含 password/auth 就会被当凭据失败，进入 1/4/24 小时冷却。分类结果直接决定是否尝试下一凭据以及 hit state。
- Trigger: 插件/SDK 返回本地化消息、非预期措辞、包装异常；业务字段或脚本错误消息含凭据关键词。
- Impact: 可用备用凭据不再尝试，或健康凭据被长期冷却；相同外部错误因文案变化产生不同控制流，无法形成可靠告警和统计。
- Why existing tests missed it: 测试硬编码 `failure_kind="credential"`，未调用真实异常分类；coverage 显示 267–270 未覆盖。
- Minimal safe fix: 插件边界返回枚举错误码（AUTHENTICATION、CONNECTIVITY、TIMEOUT、PAYLOAD、CMDB_WRITE 等）与 retryable；未知错误按业务失败且不自动污染凭据健康度，文本仅作脱敏展示。
- Required tests: 中英文认证错误、超时、连接拒绝、解析/校验/CMDB 写失败；false-positive 关键词；未知异常；不同驱动到统一错误码的契约测试。
- Long-term design note: 错误分类属于插件协议，不能由调度器解析人类文案猜测。

### Finding CMDB-F23：执行与过期清理均缺少批次、内存和持久化上限

- Severity: P1
- Location: `server/apps/cmdb/services/collect_target_service.py:31-59,135-160`；`server/apps/cmdb/services/collect_dispatch_service.py:64-200,285-299`；`server/apps/cmdb/tasks/celery_tasks.py:187-248`；`server/apps/cmdb/services/data_cleanup_service.py:31-131`
- Root cause category: 资源边界缺失
- Evidence: IP start-end 用 Python `range` 全量扩为 list，没有地址数上限；派发把 targets、pending keys、attempts、collect_data、format_data、raw_data 全量留在内存，最多再乘 3 组凭据，最终写进 `CollectModels` 单行 JSON。过期清理 `query_entity` 全量读一个任务的实例，构建全量 expired_ids 并一次 `batch_delete_entity`；只有批删异常时结果才带完整 `expired_ids`，`run_daily_cleanup` 将这些失败批次 ID 聚合进 `delete_ids` 并在总结日志原样输出。没有 rows/bytes/attempts/deadline/JSON 大小预算或游标。
- Trigger: 大 IP 段、大 instances 列表、高失败率三凭据任务；大模型启用 AFTER_EXPIRATION；插件返回超大 raw payload。
- Impact: Celery Worker 内存和时长无界、数据库大 JSON 行、图连接长时间占用；清理任务可能 OOM、超时或用巨量日志放大存储，其他采集和在线请求受拖累。
- Why existing tests missed it: target 的 IP 展开分支、dispatch 单目标执行、BaseCollect 格式化和 cleanup 主体均低覆盖；没有边界、峰值内存、查询预算、批次恢复或超限测试。
- Minimal safe fix: 入口限制目标/地址数量和请求字节；按稳定游标与固定批次执行、提交和释放内存；原始数据设 rows/bytes/保留期上限并转对象存储；cleanup 按 ID 游标小批删除，不返回/日志输出完整 ID。
- Required tests: IP 数、instances 数、凭据×目标 attempts、raw rows/bytes 边界；批次中断续跑；cleanup 多页、单批上限与峰值内存；超限零图写/零删除；真实大批量基准。
- Long-term design note: execution-target-batch 是状态机的一等实体，Celery 单任务只处理一个受限批次。

### Finding CMDB-F24：自动清理删除没有实例级审计

- Severity: P1
- Location: `server/apps/cmdb/collection/change_records.py:10-29`；`server/apps/cmdb/collection/common.py:192-212,268-278`；`server/apps/cmdb/services/data_cleanup_service.py:31-131`
- Root cause category: 跨层契约不一致
- Evidence: `write_collect_instance_change_records` 只构造 add/update records，没有读取 `result["delete"]`；IMMEDIATELY 删除成功后仍调用该函数，但不会产生日志。AFTER_EXPIRATION 直接 `batch_delete_entity`，同样没有 ChangeRecord、删除原因、execution/batch ID 或 before snapshot。
- Trigger: 采集新快照缺少旧实例并启用 IMMEDIATELY；实例超过 expire_days 后被日清任务删除。
- Impact: 生产资产消失后无法回答由哪个任务、哪次 execution、何种策略删除，影响事故追溯、合规和错误清理恢复。
- Why existing tests missed it: 管理 hook 测试把 change record writer 整体 Mock；现有审计测试只覆盖 update；cleanup 测试在 brief 中只验证 Celery 委派。
- Minimal safe fix: 两条删除路径均写持久化批量审计 outbox，记录 task/execution/batch、策略、阈值与最小 before snapshot；审计成功可重投且不阻塞图删除，最终失败告警。
- Required tests: 即时/过期删除成功与部分失败；审计 outbox broker 故障、重投幂等、批次上限；删除实例可按 task+execution 回查。
- Long-term design note: add/update/delete 共享同一采集 Operation 与审计事实源，避免清理任务另建旁路。

### 跨域证据：采集 CRUD/实例 merge/关联解析引用既有 Findings

- `CMDB-F04/CMDB-F11`：create/update 的 on_commit 回调提交后仍可部分失败且无持久化重试；destroy 在 DB 事务内先删除周期和节点配置，DB 后续失败不能回滚外部副作用；exec dispatch 也没有持久化 delivery。它们与“异步传输/跨存储副作用无可恢复状态机”同根因，不重复计数。
- `CMDB-F10/CMDB-F11`：`Management.add_inst/update_inst/delete_inst` 直接逐条图写、建边、审计和自动关系，不进入 Task 3 的唯一签名锁与 Operation/Outbox。候选查询已按批次唯一值收敛，但并发唯一性和部分副作用恢复仍复用既有主 Findings。
- `CMDB-F14`：`setting_assos` 仅按 `(model_id, inst_name)` 裸查询目标，不带 organization 或稳定 ID；跨组织同名和关系对端契约引用 Task 4，不重复计数。

## 3. Test Review

在 `server/` 使用显式 `SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task5-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false` 运行 brief 的四个社区测试文件，并对九个核心模块采集 coverage。首次沙箱执行因 uv cache 无权限退出 2、未收集；受控缓存权限重跑为 **82 passed in 3.61s，exit 0**。

覆盖率：`collect_service.py` 85%、`collect_dispatch_service.py` 73%、`collect_credential_pool_service.py` 61%、`collect_target_service.py` 61%、`collect_hit_state_service.py` 76%、`collection/common.py` 38%、`collect_tasks/base.py` 17%、`celery_tasks.py` 84%、`data_cleanup_service.py` 23%，合计 **65%**，未达到改动代码 75%/核心业务 90% 门槛。

Enterprise gitlink `enterprise` 显示前缀 `-`，确认子模块未初始化；brief 指定的 `server/apps/cmdb_enterprise/tests/test_new_collect_objects_pipeline.py` 在本 worktree 不存在，因此没有假装执行 E2E。若初始化后验证，必须按 brief 使用 `uv run --with jsonschema pytest -q -o addopts='' server/apps/cmdb_enterprise/tests/test_new_collect_objects_pipeline.py`，并先以子模块实际目录核对路径；本次 Enterprise pipeline、overlay merge 与审计扩展明确为 **未验证**。

有效证明包括：

- create/update 在事务内失败不会提前同步外部副作用；提交后 callback 才调用周期/节点系统。
- 不同 token 的重复抢占会跳过；旧 execution 成功/异常摘要和 timeout 快照不能覆盖新 token；配置文件 callback 终态不会被 pending 写回覆盖。
- timeout 使用任务 deadline、环境变量与 600 秒默认值；Beat 使用 iterator 200 扫描 RUNNING 任务。
- 单目标凭据回退、成功命中优先、已知失败冷却、凭据池编辑清 hit state 有基础覆盖。

证明力不足包括：

- 没有相同 token broker 重投、多进程 claim、timeout 后旧 Worker 图写/审计/自动关系 fencing。
- 没有成功与最终失败目标混合、全部失败原因保留、凭据/业务结构化错误分类测试。
- 没有 IP/instances/attempt/raw JSON 上限、批次、内存、清理分页和中断恢复；`common`、`base`、cleanup 覆盖率尤其低。
- 没有即时/过期删除审计、外部 on_commit callback 部分失败恢复、broker 故障/重投或敏感日志 canary。
- 未连接真实 FalkorDB、Celery broker/多 Worker、NodeMgmt/Stargazer；未执行 MySQL/PostgreSQL、大规模任务和 Enterprise E2E。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：任务生命周期分散在 View、Service、Celery、plugin、Management 和 cleanup，execution 阶段没有单一持久化实体。
2. 新增同类插件是否需要复制代码：是。插件需自行返回松散 collect/format dict，并依赖调度器猜测错误类型。
3. 新增错误类型是否需改多个模块：是。插件异常、dispatch 文本分类、hit state、Celery 摘要和 UI JSON 都要同步改。
4. 新增 callback 模式是否容易扩展：Enterprise hook 有注册表，但 hook 无 execution/outbox 契约；异常会发生在图写后。
5. 当前接口是否容易被误用：是。`task_id` 同时表示持久任务和 execution 相关字段；裸 Management 不要求 owner；失败 attempt 可被静默丢弃。
6. 日志是否足够且不泄密：execution_id、batch、target outcome 指标不足；节点参数日志确定包含 secret 风险，cleanup 还打印失败批次的完整 ID 集合。
7. 状态异常时能否判断停在哪个阶段：不能。只能看到一张最终 JSON，无法区分目标、凭据、图写、关系、审计、节点同步和 cleanup 批次。
8. 设计是否降低复杂度：局部 token 条件写回、凭据池和 outbox 审计有价值，但未统一到端到端 execution 状态机。

## 5. Recommendation

**Request changes**。

先关闭三个 P0：`CMDB-F20` 建立真正单 owner 的 execution、同 token 重投幂等和覆盖所有图/审计副作用的 fencing；`CMDB-F21` 保留每个目标的最终 outcome，禁止任务失败却成功；`CMDB-F25` 统一日志、hit state、Celery digest 与用户摘要的 secret/error 脱敏。随后以结构化错误码驱动凭据轮换，为执行与清理建立批次、内存、JSON 和 deadline 预算，并补齐删除审计。跨域 `CMDB-F04/F10/F11/F14` 也必须在统一采集 Operation 中收敛。仅保留当前结果 token 条件更新、提高 timeout 或增加成功路径 Mock，不能批准生产。
