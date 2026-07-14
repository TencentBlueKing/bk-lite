# CMDB 配置文件生命周期生产级审查

## 1. Summary

本域从即时触发与 Stargazer `receive_config_file_result` 回调开始，追踪到 execution 校验、版本业务键、临时对象、DB `PENDING`、`transaction.on_commit` 发布、`READY/ERROR/DELETE_PENDING`、15 分钟补偿、读取/diff/手动上传/删除权限。采集版本的 `(collect_task, instance_id, version)` 唯一约束、同键同文幂等、同键异文拒绝、旧 execution 拒绝、跨实例/跨文件 diff 双边权限、删除失败保留待补偿状态均有当前代码与测试证据。

确认 3 个主 Finding：P0 2 个、P1 1 个，编号保持为 `CMDB-F33`–`CMDB-F35`。`cleanup_orphan_temp_objects` 全量物化 DB 引用键和 MinIO 目录，与 Task 5 `CMDB-F23` 的周期清理无界扫描同根因；配置 callback/base64、读取和 diff 的输入输出预算也引用 Task 6 `CMDB-F28`，不重复计数。任意 MinIO/外部错误进入日志、`content_error` 或 HTTP 错误正文的脱敏问题引用 `CMDB-F25`。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F33：任务先置 SUCCESS，正文发布失败被吞后 callback 仍返回 processed=True

- Severity: P0
- Location: `server/apps/cmdb/services/config_file_service.py:96-178,287-340,440-493`；`server/apps/cmdb/services/config_file_content_lifecycle.py:37-98,157-186`；`server/apps/cmdb/nats/nats.py:769-784`；`server/apps/cmdb/serializers/config_file_serializer.py:13-29`
- Root cause category: 状态机设计缺陷
- Evidence: `process_collect_result` 在最外层 `transaction.atomic()` 中创建带正式 `content.name` 的 `PENDING` 版本，并通过 `_update_task_lifecycle` 先把 `CollectModels.exec_status` 推进 `SUCCESS`。`_create_or_get_version` 注册 robust `on_commit`；handler 没有外层事务，因此退出该最外层 atomic 时同步调用 `publish_version`。发布遇到 MinIO/哈希/对象键异常时，`publish_version` 将版本改为 `ERROR` 并吞掉异常、返回 `False`，但回调返回值无人检查；随后 `process_collect_result` 无 `error` 返回，NATS handler 据此返回 `processed=True`。版本 serializer 不暴露 `content_status/content_error`，列表仍显示业务 `status=success`，而 content/diff 因非 `READY` 拒绝读取。若调用方确有更外层事务，on_commit 会进一步延后，此时 handler 还可能在正文仍 PENDING 时返回。
- Trigger: 临时对象已写入且 DB 提交成功后，MinIO 正式对象保存失败、正式键已有不同正文、临时对象缺失/哈希不匹配，且后续周期重试持续失败。
- Impact: 调用方、采集任务与列表均观察到成功，实际正文永久不可读且 diff 不可用；监控不会按任务失败告警，上游也不会重试采集，配置留存与审计结论失真。
- Why existing tests missed it: DB 流水线 fixture 把 `publish_version` 固定桩成 READY 成功；生命周期测试单独证明发布失败会进入 ERROR，却不连接 `CollectModels` 或 NATS envelope；NATS E2E 又直接 mock `process_collect_result`。没有一个测试贯穿“DB 提交成功 + 发布失败 → 任务/callback/列表/content”外部结果。
- Minimal safe fix: 只有版本确认 `READY` 后才推进任务 `SUCCESS`。当前同步发布若进入 `ERROR`，`process_collect_result` 必须返回稳定错误，NATS handler 返回 `processed=False/error`；若调用栈确有外层事务、发布尚未执行，则任务与 callback 必须显式返回 pending，不能把预填 formal key 当作正文可用。
- Required tests: on_commit 保存失败、正式键冲突、临时对象丢失及持续重试耗尽；逐一断言版本状态、任务终态、NATS `processed/error`、列表字段、content/diff 响应和恢复后从 pending/error 到 READY 的唯一合法转换；覆盖旧恢复 Worker 不得覆盖新 generation。
- Long-term design note: `ConfigFileVersion` 应是正文发布状态的权威实体，任务汇总只消费其持久化状态事件；异步恢复长期应增加 generation/owner fencing，防止超租约旧 Worker 覆盖新处理者。通用 broker/application ack 仍复用 `CMDB-F04`，本 Finding 聚焦本域已有恢复器下的错误终态发布。

### Finding CMDB-F35：超过 5 MB 的正文被完整接收后静默截断，仍以 success 参与版本读取与 diff

- Severity: P0
- Location: `server/apps/cmdb/models/config_file_version.py:16-31,57-82`；`server/apps/cmdb/services/config_file_service.py:90-165,403-423,495-503,792-820`；`server/apps/cmdb/views/config_file.py:62-139,174-221`
- Root cause category: 跨层契约不一致
- Evidence: 模型已经定义 `FILE_TOO_LARGE` 业务状态，但采集成功路径先对任意 base64 完整解码和 UTF-8 物化，再把超过 5 MB 的正文截断；随后仍以 `status=success`、截断内容哈希创建版本，采集路径的 `file_size` 还保留 payload 原值。手动上传同样先接收完整字符串再截断并返回成功。读取与 diff 无任何 `truncated` 标志，会把不完整正文作为真实配置比较。现有单测明确锁定“超限截断”，但没有证明该行为符合配置留存契约。
- Trigger: Stargazer/直连 callback 或手动上传提交大于 5 MB 的文本配置；恶意调用方还可声明小 `file_size`，实际正文仍只在完整解码后判断。
- Impact: 用户在成功版本上读取或比较的是被静默删尾的业务正文，截断部分对平台不可见，完整配置语义发生数据丢失，可能漏掉关键安全/网络配置变更。临时对象保存的也是截断后正文，并不存在可供恢复完整内容的原始对象；同时 5 MB 只限制最终存储，不限制请求、base64 解码、原始字符串与 diff 响应的内存放大。
- Why existing tests missed it: 纯函数测试只断言截断后的字节长度，等于把静默删尾锁定成实现行为，却没有验证“success 版本必须代表完整正文”的业务契约；四文件聚焦套件没有超限 callback/手动上传的任务状态、file_size、列表、content/diff 或资源占用测试，也没有断言 `FILE_TOO_LARGE`。Agent 大文件与 NATS 放大已在 `CMDB-F28` 登记，但服务端仍没有 fail-closed 契约测试。
- Minimal safe fix: 在入口按编码后长度、声明 size 与解码后长度多层校验，并在分配大对象前拒绝超限；超限返回/落地 `FILE_TOO_LARGE` 且不创建成功版本。若产品确需保存摘要，必须使用独立 `truncated` 状态、真实已存字节数和原始大小字段，并禁止把摘要作为完整正文参与 diff。
- Required tests: callback/手动入口上限−1、上限、上限+1，伪造 file_size、base64 放大、非法编码、超大 diff 输出；超限必须在 stage/MinIO 前失败，任务/NATS/HTTP 显式可见，零 success 版本。与 Agent `CMDB-F28` 联合验证端到端请求和输出预算。
- Long-term design note: 文件大小策略应是控制面、Agent、NATS schema、Service 和对象存储共享的版本化契约；“拒绝、流式存储或摘要”只能选择一个显式产品语义，不能由 Service 静默截断。

### Finding CMDB-F34：手动上传的毫秒版本与正式对象键可并发碰撞，后发布者失败但 HTTP 仍返回创建成功

- Severity: P1
- Location: `server/apps/cmdb/models/config_file_version.py:85-95`；`server/apps/cmdb/services/config_file_service.py:48-50,792-847`；`server/apps/cmdb/services/config_file_content_lifecycle.py:62-70`；`server/apps/cmdb/views/config_file.py:174-221`
- Root cause category: 并发或幂等设计问题
- Evidence: 手动版本用当前毫秒字符串作为 `version`，正式对象键只由 `model_id/instance_id/file_path_hash/version` 组成；数据库唯一约束包含 nullable `collect_task`，现有测试还明确允许两个 `collect_task=NULL` 的相同 `(instance_id, version)` 行。因此两个同实例、同路径、同毫秒的并发上传可各自落库但共享 formal key。首个发布成功后，第二个发现同键正文哈希不同并进入 `ERROR`；`create_manual_version` 不检查 on_commit 返回值，View 仍以 200 返回第二个版本 ID/版本号。
- Trigger: 两个请求在同一毫秒对同一实例与路径上传不同正文；或时间源回拨/冻结导致版本号复用。
- Impact: 至少一个用户收到成功响应但版本正文不可用；相同可见版本号对应两行不同元数据，恢复器会持续遇到正式键冲突，无法自动收敛。
- Why existing tests missed it: `test_manual_versions_without_collect_task_do_not_conflict` 只断言数据库允许重复行；View 成功测试完全 mock Service；并发测试只覆盖带 collect task 的唯一键，没有冻结时间并执行两个真实手动上传、对象发布和 HTTP 结果。
- Minimal safe fix: 为手动版本建立不可碰撞且可幂等的业务键（服务端 request/idempotency ID 或 UUID），正式对象键至少包含该唯一 ID；创建与响应必须依据发布状态，冲突时返回稳定的 409/失败结果，不能依赖毫秒时钟或 nullable 唯一约束。
- Required tests: 冻结同一毫秒并发上传不同/相同正文、重复 Idempotency-Key、时间回拨、不同实例/路径；断言 DB 行、对象键、READY/ERROR、HTTP 状态、重试和孤儿临时对象均可确定收敛，并在 SQLite/MySQL/PostgreSQL 验证 nullable unique 语义。
- Long-term design note: 展示版本号与存储身份应分离；展示可保留采集时间，持久身份必须是全局唯一且由 DB/协议产生，MinIO key 不应由非唯一业务时间拼接。

### 跨域证据与未计数风险

- `CMDB-F23`：`cleanup_orphan_temp_objects` 的 `batch_size` 只限制成功删除数，仍先全量加载所有非空 `temp_content_key` 为 set，并让 MinIO `listdir` 返回整个目录。积压增长时周期 Worker 的 DB/内存预算无界；与自动采集清理“先全量加载再批删”同根因，本域不重复建立 Finding。
- `CMDB-F28`：callback 在 Service 限制前已经由 Agent 读文件、base64 编码、NATS 传输并在 CMDB 完整解码；content 同时返回文本与 base64，diff 也无输出预算。统一 ResourceBudget 必须覆盖两端，不能只把存储常量设为 5 MB。
- `CMDB-F25`：`content_error` 保存截断后的任意 MinIO 异常，content/create_manual HTTP 又直接拼接异常正文，Task 6 callback/日志也传播外部错误。统一脱敏边界需覆盖日志、DB、NATS 与 HTTP，本域不重复计数。
- 读取与 diff 已对两个版本分别执行实例 VIEW 权限并拒绝跨实例/跨文件；删除和手动上传要求实例 OPERATE。当前证据未证明“可见实例还必须具备原 collect task 权限”这一额外产品约束，因此未把未使用的 `filter_queryset_by_task_permission` 升格为权限 Finding。

## 3. Test Review

- 执行命令：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task7-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run --with jsonschema pytest -q -o addopts='' apps/cmdb/tests/test_config_file_process_collect_db.py apps/cmdb/tests/test_config_file_content_lifecycle.py apps/cmdb/tests/test_config_file_views.py apps/cmdb/tests/e2e/test_config_file_pipeline.py --cov=apps.cmdb.services.config_file_service --cov=apps.cmdb.services.config_file_content_lifecycle --cov=apps.cmdb.views.config_file --cov=apps.cmdb.collection.collect_tasks.config_file_collect --cov=apps.cmdb.nats.nats --cov-report=term-missing`。
- 首次在沙箱退出 2，uv 无权读取 `~/.cache/uv/sdists-v9/.git`，未收集；受控缓存权限重跑退出 0：**66 passed in 8.21s**。
- 覆盖率：`config_file_content_lifecycle.py` 91%、`config_file_service.py` 73%、`views/config_file.py` 81%、`config_file_collect.py` 27%、`nats/nats.py` 整文件 16%，五目标合计 46%。生命周期局部达到核心 90%，主 Service、触发链和功能域整体未达到相关模块 80%/核心路径 90% 目标；NATS 数值被整文件大量无关 handler 稀释，但配置 handler 的 E2E 仍只 mock Service。
- 有效证明：采集业务键同文/异文、旧 execution 与终态回调、事务回滚不发布/删除、PENDING→READY、发布/删除失败状态、过期批量恢复、Beat 注册、双版本实例权限、跨实例/文件 diff 拒绝和传输 ack/业务错误 envelope。
- 关键漏检：没有贯穿发布失败后的任务/NATS/读取外部状态；没有手动上传真实 Service、同毫秒并发和 nullable unique/object key 碰撞；没有超限入口与静默截断语义；孤儿清理只用 3 个内存对象，不能证明分页/目录规模；未执行真实 MinIO/NATS/Celery worker、恢复并发、MySQL/PostgreSQL 或大文件/大目录。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：单个 Service 可读，但“采集成功”和“正文可用”分属 task status、version status、content status 三套状态，缺少一张权威转换图，容易误判。
2. 新增同类内容资产是否需复制：会。stage/publish/delete/recover、业务汇总与 View 错误映射仍需手工拼接，未形成通用对象生命周期组件。
3. 新增错误类型是否需改多处：会。Agent status、`STATUS_MAP`、task summary、content status、NATS envelope、serializer/View 需同步，且当前没有穷尽性校验。
4. 新增 callback 是否容易：表面容易注册，实质必须自行处理 execution、实例映射、传输 ack、业务状态与对象发布，误用成本高。
5. 接口是否易误用：是。`content.name` 在对象不存在时已像正式 key，`status=success` 又不代表 `content_status=READY`；毫秒版本看似唯一但手动路径并非如此。
6. 日志是否安全且可排障：否。能看到 version_id/temp key/阶段，但任意外部错误可进入日志与 DB/HTTP，且 task success 无法表达 publishing/error。
7. 状态异常能否定位阶段：版本行可以区分 PENDING/ERROR/DELETE_PENDING，但任务与 callback 不反映该阶段，跨层定位仍需人工查两张表和 MinIO。
8. 是否降低复杂度：临时对象 + DB 状态 + 周期恢复显著改善了回滚与删除可靠性；提前发布成功、非唯一手动 key 和静默截断又把复杂度转移到用户可见一致性。

## 5. Recommendation

**Block**。

先关闭两个 P0：`CMDB-F33` 使 READY 成为任务成功和 callback 业务成功的必要条件，`CMDB-F35` 将超限正文改为入口 fail-closed 或显式摘要语义；再用不可碰撞、可幂等的手动业务键/对象键修复 `CMDB-F34`。联合 `CMDB-F23/F28/F25` 补齐分页资源预算、端到端大小限制和错误脱敏。当前 66 项绿灯证明了局部状态转换，但不能证明 MinIO 失败、并发上传和超限配置下的外部真实性，尚不建议合并为生产可用。
