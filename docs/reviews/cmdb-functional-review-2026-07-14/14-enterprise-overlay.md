# CMDB Enterprise Overlay 全范围生产级审查

## 1. Summary

本报告补审主工作区运行态 Enterprise Overlay，覆盖采集扩展、Stargazer Enterprise 插件、模型/实例扩展、附件存储与生命周期；自定义上报仍由 [10-custom-reporting.md](10-custom-reporting.md) 负责。审查对象不是隔离 worktree 中可由 Git 重建的源码，而是主工作区 ignored 安装态目录；完整 78 文件清单、逐文件 SHA-256 和运行态边界见 [enterprise-overlay-provenance.md](enterprise-overlay-provenance.md)。

确认 10 个主 Finding：**P0 3 / P1 6 / P2 1 / P3 0**。编号稳定映射为 `CMDB-F65`–`CMDB-F74`，按严重级别排序。整体 Recommendation 为 **Block**。

- `CMDB-F65`–`CMDB-F70`：Enterprise collect 与 Agent 执行链，来源草稿编号 EC-01–EC-06。
- `CMDB-F71`–`CMDB-F74`：模型/实例/附件扩展，来源草稿编号 EO-F01–EO-F04。
- 与既有 `CMDB-F01`–`CMDB-F64` 的交叉引用仅表示相似事故面，不重复计数；逐项去重理由保留在 Finding 的 Root cause、Trigger 与 Minimal safe fix 中。

## 2. Findings

### Finding CMDB-F65：Enterprise 凭据 schema 只加密 `password`，token/secret/community 可明文落库并经 API 返回

- Severity: P0
- Location: `server/apps/cmdb_enterprise/collect/new_collect_object_definitions.py:347-360`；`server/apps/cmdb_enterprise/collect/tree.py:26-40`；`server/apps/cmdb_enterprise/collect/remaining_node_params.py:39-53`；`server/apps/cmdb/services/encrypt_collect_password.py:9-16`；`server/apps/cmdb/models/collect_model.py:235-285`；`server/apps/cmdb/serializers/collect_serializer.py:210-223`
- Root cause category: 跨层契约不一致
- Evidence: Enterprise 树对“达梦 + 48 个新增对象”共 49 个对象都固定声明 `encrypted_fields=["password"]`。Generic protocol NodeParams 却明确接收并下发 `token/access_key/secret_key/community`；凭据池只校验 dict 形状，不限制字段。`CollectModels.save/decrypt_credentials` 只遍历树中声明的字段加解密，Serializer 也只遮蔽同一字段。直接只读复现输出对象数 49、`encrypted_fields=['password']` 与 accepted `access_key/community/secret_key/token`，exit 0。
- Trigger: 为 XSKY/ZStack/存储/SNMP/安全设备等 Enterprise protocol 任务提交 `token`、`secret_key`、`community`、`authkey`、`privkey` 或其他非 `password` 秘密字段。
- Impact: 秘密以明文写进 `CollectModels.credential`，并且详情 API 的 `credential` representation 不会将其替换为 `******`；数据库读取、备份、日志/调试或具备任务详情权限的调用方可直接获得设备/云凭据。
- Why existing tests missed it: Enterprise 测试只检查对象归属、密码下发和成功 formatter；社区凭据测试集中于 password 与池形状，没有遍历每个 Enterprise manifest 的 secret schema，也没有 token/community canary 的 DB-at-rest 与 API masking 断言。
- Minimal safe fix: 为每个采集对象定义版本化、闭合的 credential schema，字段需标注 `secret/required/type`；保存、展示、下发统一消费该 schema。短期至少把实际接受的 `token/secret_key/community/authkey/privkey/accessSecret` 全部纳入加密和遮蔽，并拒绝未声明字段；对已有明文数据做可审计迁移和密钥轮换。
- Required tests: 每个 Enterprise 对象遍历 credential schema；所有 secret 保存后均有加密前缀、读取后可解密、API/日志不含 canary；未知字段 400；旧明文迁移、重复保存不双重加密、多凭据池和 SNMP v2/v3 全覆盖。
- Long-term design note: secret classification 属于 credential DTO，而不是对象树展示 metadata；持久化、API 与 NodeParams 不应分别猜字段名。

### Finding CMDB-F66：21 个 Enterprise protocol collector 不访问目标仍返回成功并制造资产事实

- Severity: P0
- Location: `agents/stargazer/enterprise/plugins/inputs/{ambari,couchbase,emc_symmetrix,f5,h3c_cas,hds_vsp,ibm_ds,ibm_storwize,infinidat,iris,macrosan,netapp_cluster,oraclezfs,pure_array,sap_hana,security_device,tape_library,tdsql,tongrds,xsky,zstack}/*_info.py:5-37`；`server/apps/cmdb_enterprise/collect/remaining_plugins.py:26-43`；`server/apps/cmdb_enterprise/collect/remaining_collect_metrics.py:35-61`；`agents/stargazer/tests/test_remaining_collect_objects_plugins.py:57-65`
- Root cause category: 局部实现错误
- Evidence: 这些名为 “Read-only collector” 的类只从 kwargs 复制 `host/port/name`，用 `_to_int` 规范端口，随后无网络、认证、SDK 或设备查询就返回 `{"result": {model_id: [...]}, "success": True}`。直接对保留测试地址 `203.0.113.254` 和错误密码实例化 XSKY，未发任何 I/O 即返回 success，exit 0。现有测试反而明确断言这一行为为正确。
- Trigger: 对上述任一对象创建或执行 protocol 采集任务，无论目标不存在、端口关闭、凭据错误或实际设备类型不匹配。
- Impact: 任务显示成功，目标输入被当作已发现资产 add/update 到 CMDB；运营人员会看到并不存在或未经验证的存储、云、网络/安全设备事实，后续关联、清理、审计和容量决策均建立在伪数据上。
- Why existing tests missed it: 只抽样 XSKY 并断言回显 host/port 与 `success=True`，没有零 I/O 防伪断言、认证失败、连接失败、设备指纹/schema 验证或真实 fixture；其余 20 个只验证模块可 import。
- Minimal safe fix: 未实现的对象必须从树和 registry 中 fail-closed 隐藏；只有具备真实只读探测、认证、设备身份校验和结构化失败的 collector 才可注册。不能把占位回显包装成 success。
- Required tests: 每类 collector 的不存在目标、拒绝连接、错误凭据、错误设备类型均失败且零 CMDB 写；真实/模拟协议成功需证明至少一次目标交互与身份字段；对全部 manifest 做“禁止无 I/O success”契约门禁。
- Long-term design note: capability registry 应声明 `experimental/implemented/verified`，生产对象树只暴露 verified；占位代码不能通过与真实插件相同的成功协议进入事实写入层。

### Finding CMDB-F67：IBM MQ `object_type` 未路由成子模型 metric，真实链路只产生父 metric

- Severity: P0
- Location: `agents/stargazer/enterprise/plugins/inputs/ibmmq/ibmmq_default_discover.sh:25-65`；`agents/stargazer/plugins/script_executor.py:142-164,200-205`；`agents/stargazer/service/collection_service.py:238-265`；`server/apps/cmdb_enterprise/collect/ibmmq.py:12-66`；`server/apps/cmdb_enterprise/tests/test_new_collect_objects_formatters.py:103-142`；`agents/stargazer/tests/test_new_collect_objects_plugins.py:36-48`
- Root cause category: 跨层契约不一致
- Evidence: 脚本用 `object_type=ibmmq/channel/listener/localqueue/remotequeue` 区分 JSON 行；`SSHPlugin` 却把所有 parsed rows 固定包装在 `result[self.model_id]`，CollectionService 再按该唯一 key 生成同一 `ibmmq_info` metric。CMDB formatter 只依据五个不同 metric 名路由模型，从不读取 `object_type`。直接把 parent+channel 行穿过 `_process_result + convert_to_prometheus_format`，得到 `['ibmmq_info','ibmmq_info']` 且无 channel metric，exit 0。脚本父行还不提供 `ip_addr/port`，IP-range 任务没有 fallback `inst_name` 时父身份也不完整。
- Trigger: 执行任意 IBM MQ job，尤其是包含 channel/listener/queue 的正常队列管理器或 IP-range 发现任务。
- Impact: channel/listener/localqueue/remotequeue 永远不能到达对应 formatter；子资产和关系缺失，子行可能被当作父行形成空/错误父实例，任务仍可表现为成功或部分成功。
- Why existing tests missed it: Agent 测试只检查脚本包含只读命令，并在注释中把拆分留给后续 adapter；CMDB 测试直接注入现实链路不会产生的 `ibmmq_channel_info_gauge` 合成数据。没有脚本输出→SSHPlugin→Prom metric→CMDB formatter E2E。
- Minimal safe fix: 在 Agent 的类型化 adapter 中把受支持 `object_type` 映射到版本化模型 key/metric，未知类型 fail closed；为父记录补稳定 host/port/qmgr identity。禁止由通用 SSHPlugin 默默抹掉多对象类型。
- Required tests: 用真实脚本 fixture 的五类 JSON 行跑完整 E2E，断言五类 metric、父子 inst_name 与 relation；未知/缺失 object_type、空 qmgr、多个 qmgr、无 IP、脚本部分坏行均有结构化失败且不制造父资产。
- Long-term design note: 多对象路由属于 Agent adapter DTO，不应让 shell 的自由文本标签与 CMDB metric 命名约定隔层隐式耦合。

### Finding CMDB-F68：formatter 遇到首个过期样本就 `break`，无序结果中的后续 fresh 指标被静默丢弃

- Severity: P1
- Location: `server/apps/cmdb_enterprise/collect/new_objects.py:49-61`；`server/apps/cmdb_enterprise/collect/remaining_collect_metrics.py:35-46`；`server/apps/cmdb_enterprise/tests/test_new_collect_objects_formatters.py:6-24`
- Root cause category: 局部实现错误
- Evidence: 两个 formatter 都在 `timestamp_gt` 尚未置位时检查时间；若当前 row 超过一天，执行 `break` 终止整个 `data["result"]`，没有先按 metric/time 排序，也没有查询层保证跨 measurement 全局倒序。直接传入 `[stale, fresh]`，fresh row 未进入 `collection_metrics_dict`，输出空列表，exit 0。
- Trigger: Prometheus/Influx 查询结果把任一旧样本排在新样本之前；多 metric 查询、存储合并、重放或非稳定排序均可触发。
- Impact: 新鲜父/子资产、字段和关系被静默丢弃；采集可呈现空或残缺快照，且无错误记录表明 fresh 数据曾存在。
- Why existing tests missed it: 所有 formatter fixture 都用 `time.time()` 且按父后子固定顺序；没有 stale/fresh 混排、多 measurement 排序、边界时间或全旧数据测试。
- Minimal safe fix: 每行独立判断并 `continue` 过期样本，或在 query adapter 明确按稳定 `(timestamp, metric, identity)` 排序并按 measurement 分组取最新；禁止用单个 row 终止整个异构结果集。
- Required tests: stale→fresh、fresh→stale、跨 metric 混排、恰好 24h、毫秒/秒时间戳、重复 identity 取最新；断言 fresh 全保留且 stale 全过滤。
- Long-term design note: 时序窗口和“每 identity 最新值”应由 query/normalization 层定义，formatter 只消费确定性 snapshot。

### Finding CMDB-F69：Enterprise collector import 失败默认回退到 schema/认证不等价的 OSS 插件

- Severity: P1
- Location: `agents/stargazer/service/collection_service.py:103-139`；`agents/stargazer/core/plugin_executor.py:117-144`；`agents/stargazer/core/yaml_reader.py:134-207`；Enterprise/OSS 同名目录 `ambari,couchbase,dameng,highgo,iris,nacos,oceanbase,sap_hana,server_bmc,tdsql,tongrds`
- Root cause category: 错误模型不清晰
- Evidence: `strict_enterprise` 默认 false，CMDB NodeParams 没有设置它；Enterprise 被解析为首选后，只要 collector module/class import 抛异常且存在同名 OSS yml，执行器就切换 fallback。直接模拟缺失 Enterprise module，实际加载 `plugins.script_executor.SSHPlugin` fallback，exit 0。真实同名实现并不等价：例如 Enterprise Nacos 输出 parent/node/namespace/service 四模型并做 token 脱敏，OSS 实现的字段、认证默认值与错误处理不同；BMC 两侧也有不同认证字段和多对象输出。Stargazer 主依赖还未直接声明这些实现使用的 `requests`，本地 Stargazer venv 实例化 Enterprise Nacos 稳定 `ModuleNotFoundError`，说明 import/依赖失败并非纯理论（是否代表发布镜像仍需以镜像验证）。
- Trigger: Enterprise 文件缺失/损坏、类名漂移、可选依赖未装或 import-time 异常；同名 OSS plugin 存在且 `strict_enterprise` 未显式为 true。
- Impact: 商业能力悄然换成另一份 schema/认证实现；多对象可能降为单对象、凭据字段被忽略或采用不同默认账号，CMDB 仍按 Enterprise formatter/树解释结果，造成缺失、错误或假成功。
- Why existing tests missed it: Enterprise tests 只验证模块可 import 和单边 mapper；没有故障注入后断言 fail-closed，也没有 Enterprise/OSS schema 等价门禁、依赖锁/镜像 smoke 或 fallback 后 CMDB E2E。
- Minimal safe fix: Enterprise 对象默认 `strict_enterprise=true`；只有经过显式版本/schema 等价认证的实现才允许 fallback。启动阶段加载并实例化所有启用 collector、验证直接依赖与 DTO version，失败则摘除能力或阻断就绪。
- Required tests: module/class/dependency failure均 fail closed；同名 Enterprise/OSS 对每个 credential、result/error schema 做等价测试；生产镜像逐插件 instantiate smoke；fallback 必须携带 source/version 并禁止清理/事实写入直到 schema 验证通过。
- Long-term design note: fallback 是 capability routing 策略，不是 import exception 的通用 catch；它必须由 manifest 声明兼容版本和迁移条件。

### Finding CMDB-F70：注册发现不是原子启动契约，重复键和导入失败可静默形成部分能力

- Severity: P1
- Location: `server/apps/cmdb_enterprise/registry_hooks.py:7-17`；`server/apps/cmdb/extensions/registry.py:7-16`；`server/apps/cmdb/collection/plugins/registry.py:17-50`；`server/apps/cmdb/collection/plugins/loader.py:14-31,34-63`；`server/apps/cmdb/node_configs/__init__.py:11-37,40-58`；`server/apps/cmdb/node_configs/base.py:34-46`
- Root cause category: 架构职责放置错误
- Evidence: 扩展 slot 后注册无条件覆盖，社区测试明确把覆盖作为预期；NodeParams 同 `(model_id,driver_type)` 也无条件覆盖。Collection plugin 同优先级冲突仅 error log 且保留先加载者。NodeParams package walker 对任意子模块异常直接 `pass`，甚至没有日志；plugin loader 虽返回 false，但不撤销此前已注册的部分模块。没有最终 manifest 对树对象、plugin、NodeParams、Agent manifest 做一一完备性与唯一性校验。
- Trigger: 重复 app/overlay、同键新插件、模块 import 一半失败、加载顺序变化、可选依赖缺失或热重载。
- Impact: 进程仍可 ready，但某些对象缺 plugin/NodeParams，或实际实现由 import 顺序决定；不同 Worker 可能拥有不同 registry snapshot，任务只在运行时才报 unsupported，无法从健康检查识别发布残缺。
- Why existing tests missed it: 达梦测试只在已 warm 的单进程里递归找唯一 subclass；boundary 测试在全量 import 后查 registry。没有 fresh process、重复键、部分 import failure、跨 Worker snapshot digest 或 readiness 失败测试。覆盖率中 loader 64%、NodeParams loader 77%，异常分支未证明。
- Minimal safe fix: 构建不可变 capability manifest：启动时先导入到临时 registry，校验 slot/plugin/NodeParams 唯一、树与 Agent manifest 完备、版本兼容后一次发布；重复或必需模块失败应 fail-fast，允许缺失的可选能力需从树中摘除并暴露 readiness 状态。
- Required tests: 重复 slot/plugin/NodeParams 均启动失败；单模块 import error 不发布任何半成品；多进程 registry digest 一致；树中每个可见对象恰有一个 plugin、一个 NodeParams、一个可加载 Agent executor；热重载幂等。
- Long-term design note: discovery/registry 是框架职责；业务模块的 import side effect 不应同时承担声明、冲突决策和生产可用性证明。

### Finding CMDB-F71：文件台账无法表达图字段允许的一对多引用，批量/并发写会把归属覆盖给最后一个实例

- Severity: P1
- Location: `server/apps/cmdb_enterprise/instance_ops/service.py:135-226`；`server/apps/cmdb/services/instance.py:632-684,706-788,812-883`；`server/apps/cmdb_enterprise/models/file_object.py:28-46`
- Root cause category: 并发或幂等设计问题
- Evidence: `normalize_file_fields()` 只在写图前读取并检查 pending 的 uploader 或 committed 的 `inst_id`，没有占用锁/CAS，也不要求 `file_id` 在整份实例数据中唯一。图写完成后，`commit_instance_files()` 对 `new_ids` 执行不带旧状态、旧 owner、目标基数条件的批量 `UPDATE`，直接覆盖单行 `inst_id/attr_id/model_id`，且忽略 update count。`batch_instance_update()` 只规范化一次，却把同一个文件值写给全部目标实例，随后逐实例提交台账；同一实例的两个文件字段也可提交同一 `file_id`。最终台账只能记住最后一次写入，而此前图节点/字段仍保留同一元数据。
- Trigger: (1) 对两个实例执行带同一 pending `file_id` 的批量更新；(2) 同一实例的两个附件字段引用同一 pending `file_id`；(3) 两个并发创建/更新在 normalize 后、commit 前同时通过检查。
- Impact: 最后提交者取得台账归属；其他实例/字段仍展示附件，但下载按台账最终 `inst_id` 校权而被拒绝。后续从最终字段移除文件会把台账置 orphaned，GC 可删除仍被其他图字段引用的对象，造成确定的数据丢失和不可恢复悬空元数据。
- Why existing tests missed it: `test_commit_marks_referenced_committed_and_removed_orphaned` 只覆盖单实例单字段串行路径；`test_batch_instance_update_runs_file_field_hooks` 使用 fake extension，只断言 normalize 一次、commit 被调用，不运行真实台账逻辑；没有跨字段复用、两个目标实例、并发 interleaving、CAS update count 或 GC 后可下载性断言。
- Minimal safe fix: 明确文件引用基数。若要求独占，normalize/commit 必须在数据库事务内以 `select_for_update` 或条件 `UPDATE ... WHERE status=pending AND uploader=?` 原子 claim，验证 update count，并在写图前取得可回滚的 claim/fencing token；批量对多个实例使用文件字段时应拒绝。若允许复用，则把“对象”与“引用”拆表，用唯一 `(file_id, inst_id, attr_id)` 引用行和引用计数表达多归属，GC 仅删除零引用对象。
- Required tests: 同 file_id 跨两个字段、跨两个批量目标、两个并发创建、normalize 后临时删除/GC、条件更新失败、最后字段移除但仍有其他引用、对象删除前引用计数核对。
- Long-term design note: 图字段元数据与 SQL 台账当前都被描述为“真相”，但二者基数不同。应由一个 durable 文件引用状态机定义 claim/commit/release，而不是依赖图写后无条件修补 SQL。

### Finding CMDB-F72：删除附件/图片模型字段未进入文件生命周期，正文仍可下载且不会被 GC

- Severity: P1
- Location: `server/apps/cmdb/services/model.py:1197-1258`；`server/apps/cmdb/model_ops/extensions.py:10-50`；`server/apps/cmdb_enterprise/model_ops/provider.py:7-31`；`server/apps/cmdb_enterprise/instance_ops/tasks.py:25-39`
- Root cause category: 跨层契约不一致
- Evidence: `ModelManage.delete_model_attr()` 从模型 attrs 和全部实例图节点移除字段属性，但 `ModelEnterpriseExtension` 没有字段删除生命周期 hook，Enterprise provider 也无法把该 `model_id/attr_id` 的 `CmdbFileObject` 标为 orphaned。GC 只处理 stale pending 和已标记 orphaned 的行；原 committed 行因此永久保留。下载入口仍按该行 `inst_id` 查询现存实例并做实例读权限，字段已不存在并不会阻止预签名 URL 生成。
- Trigger: 模型管理员删除一个已被实例使用的 attachment/image 字段，然后原本有实例读权限的用户使用已知 `file_id` 调用下载接口。
- Impact: UI/图数据已表现为字段和附件被删除，但对象存储正文与 committed 台账无限期保留，并仍可下载；违反删除语义和数据最小保留原则，也造成不可回收存储增长。
- Why existing tests missed it: `test_delete_model_attr_ok` 只 mock 图层并验证 attrs/property 删除；Enterprise 文件测试只覆盖实例编辑移除和实例删除置 orphaned；没有“字段删除 → 台账状态 → 下载拒绝 → GC 删除”的端到端断言。
- Minimal safe fix: 给 model extension 增加字段删除前/后契约；在图属性删除成功后，为目标 `model_id/attr_id` 的 committed 行创建 durable deletion intent 或置 orphaned。若要求可回滚，先落删除 operation/outbox，再由幂等消费者移除图属性、撤销引用和删除对象；下载在 deletion intent 后立即 fail closed。
- Required tests: 有/无附件的字段删除、图删除失败、台账更新失败、重复删除、字段删除后下载、GC 部分失败重试、模型整体删除的同类生命周期。
- Long-term design note: 文件生命周期不能只挂在 instance CRUD；模型治理删除字段/模型同样是引用终止事件，应共享统一引用回收服务。

### Finding CMDB-F73：单文件校验晚于 multipart 全量解析，认证用户可用额外文件耗尽临时磁盘

- Severity: P1
- Location: `server/apps/cmdb/views/instance.py:333-347`；`server/apps/cmdb_enterprise/instance_ops/service.py:76-100`；`server/config/components/app.py:159-160`；Django 4.2 `django/http/multipartparser.py:253-264`
- Root cause category: 资源边界缺失
- Evidence: DRF/Django 在进入 `upload_file()` 前已解析整个 multipart 请求并把所有 FILE part 交给 upload handlers；仓库仅配置 `DATA_UPLOAD_MAX_NUMBER_FILES=100`，没有请求 body 总字节上限。Django 的 `DATA_UPLOAD_MAX_MEMORY_SIZE` 分支只限制普通 FIELD，FILE 分支只计数量。业务层随后只取 `request.FILES.get("file")` 并对这一项执行 50 MB/10 MB 校验，额外 99 个任意字段名文件不会进入 `validate_upload()`，但已经被接收并可能写入临时磁盘。仓库 deploy/server 配置中未找到 `client_max_body_size` 或等价总量限制。
- Trigger: 具有 `asset_info-Add` 的用户发送 multipart：一个合法小 `file` 加 99 个超大额外 FILE part，或一个在解析阶段已完整接收后才被判超限的巨大 `file`。
- Impact: 单请求可在业务校验前持续占用网络、临时磁盘和解析 worker；并发请求可耗尽磁盘/worker，影响整个控制台。应用的“单文件最大 50 MB”并不是实际入站资源上限。
- Why existing tests missed it: `test_validate_upload_*` 直接传 fake upload，`test_upload_file_full_path_view_to_ledger` 只发送一个很小的文件；没有 multipart parser 级总字节、额外 FILE part、临时上传 handler 或并发预算测试。
- Minimal safe fix: 在可信入口（Ingress/反向代理和 ASGI 请求层）设置与业务上限一致的 body 总量硬限制；视图拒绝 `FILES` 键/数量不等于唯一 `file`；如需支持流式大文件，使用能够在读取过程中计数并中止的 upload handler，而不是解析后检查 `.size`。
- Required tests: 超大单文件在写完前被中止、额外文件字段拒绝、99/100/101 文件边界、并发上传磁盘预算、代理与应用限制一致、临时文件异常清理。
- Long-term design note: 文件安全约束应在“字节进入系统”的最外层执行；扩展名和 ORM 台账校验不能替代传输/临时存储预算。

### Finding CMDB-F74：附件 GC 无工作预算，部分失败仍被 Celery 记录为成功

- Severity: P2
- Location: `server/apps/cmdb_enterprise/instance_ops/tasks.py:15-44`；`server/apps/cmdb_enterprise/config.py:3-13`；`server/apps/cmdb_enterprise/tasks/__init__.py:1-2`
- Root cause category: 状态机设计缺陷
- Evidence: 每日任务先一次性把全部过期 pending 改为 orphaned，再用 `.iterator()` 无 limit、批次 checkpoint、deadline/soft time limit 地遍历全部 orphaned 对象并逐个同步调用 MinIO。任一对象删除失败只递增 `failed` 并记日志；即使 `failed > 0`，任务仍正常返回 `{result: True, ...}`，Celery 终态为 SUCCESS，不触发失败告警或 task-level retry。失败行虽留待下一日再扫，但没有退避、尝试次数或死信状态。
- Trigger: orphaned backlog 很大、MinIO 长时间变慢，或某个对象持续返回权限/网络错误。
- Impact: 单个周期任务可长期占用 worker 并与业务任务争抢并发；持续失败对象每天无限重试且 Celery/监控仍显示成功，清理延迟和存储泄漏只能依赖人工阅读日志/返回字典发现。
- Why existing tests missed it: 聚焦覆盖率显示 `instance_ops/tasks.py` 0%；仓库无 `cleanup_attachment_files` 测试，未覆盖 backlog 上限、deadline、部分失败终态、重试或幂等。
- Minimal safe fix: 用稳定游标/主键窗口分批 claim，设置每轮条数、总耗时、MinIO 调用 timeout 和可观测 checkpoint；单对象保留幂等重试，但当轮存在未处理失败时应使用明确 PARTIAL/FAILED 结果并接入告警/后续任务，持久化 attempts/last_error/next_retry_at，达到阈值进入死信待处理。
- Required tests: 0/1/上限/超上限 backlog、对象删除超时、部分失败、持续失败退避、worker 中止后续跑、重复执行、对象已不存在、返回终态与 Celery state/告警一致。
- Long-term design note: 周期扫描应是可恢复的有界工作队列，而非“每天从头扫到尾”；业务终态不能藏在成功 task 的自定义字典中。

## 3. Test Review

### 3.1 Server 定向组合

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- 环境：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-collect-audit.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache`
- 首次沙箱命令：`uv run pytest -q -o addopts='' --cov=apps.cmdb_enterprise.collect --cov=apps.cmdb.collection.plugins --cov=apps.cmdb.node_configs --cov=apps.cmdb.collect.extensions --cov=apps.cmdb.services.collect_object_tree --cov-report=term-missing apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py apps/cmdb_enterprise/tests/test_dameng_node_params_service.py apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py apps/cmdb_enterprise/tests/test_new_collect_objects_formatters.py apps/cmdb_enterprise/tests/test_new_collect_objects_pipeline.py apps/cmdb/tests/test_enterprise_extensions.py apps/cmdb/tests/test_extensions_registry.py apps/cmdb/tests/test_new_collect_objects_model_config.py`
- 首次结果：exit 101，uv 在 macOS `system-configuration` 沙箱中 panic，未收集测试。
- 同命令经受控沙箱外重跑：exit 1，**26 passed / 1 failed in 5.69s**。
- 唯一失败：`test_new_collect_objects_are_added_by_enterprise_extension` 要求 `aix` 独立位于树中；`collect_object_tree.py:6,33-34` 明确把 `aix/hpux/domestic_linux` 合并到 host 并跳过 Enterprise child。属于测试与当前显式合并契约冲突，需产品确认独立对象还是 host 变体后统一，不作为本轮生产 Finding。
- Coverage：组合总计 **66%（2062 stmts / 701 miss）**；Enterprise collect **约 72%（491 stmts / 137 miss）**，未达 75%。关键短板：`remaining_collect_metrics.py` 25%、`remaining_node_params.py` 51%、Nacos/BMC NodeParams 55%、plugin loader 64%。

### 3.2 Stargazer Enterprise plugin 测试

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/agents/stargazer`
- 命令：`.venv/bin/python -m pytest -q -o addopts='' tests/test_new_collect_objects_plugins.py tests/test_remaining_collect_objects_plugins.py`
- 结果：exit 0，**9 passed / 1 warning in 0.36s**。
- Coverage 尝试：`.venv/bin/python -m pytest -q -o addopts='' --cov=enterprise.plugins.inputs --cov=core.plugin_executor --cov=core.yaml_reader --cov-report=term-missing tests/test_new_collect_objects_plugins.py tests/test_remaining_collect_objects_plugins.py`，exit 4；该 venv 未安装 pytest-cov，**无 Stargazer coverage，不能声称达标**。
- 证明力缺口：remaining 测试把 XSKY 不执行 I/O 即 success 当成正确；IBM MQ 只检脚本文本；没有 Agent→metric→CMDB E2E、fallback failure injection、真实依赖镜像 smoke、secret at-rest/API、stale/fresh 顺序或 registry fresh-process 测试。

### 3.3 只读直接复现

以下均不联网、不写生产文件；完整 fixture、绝对 cwd、环境、命令、退出码与原始关键输出见 [reproduction-commands.md §4.3](reproduction-commands.md#43-f65f69-直接探针)：

1. F65 credential schema：exit 0，输出对象数 49、`encrypted_fields=['password']` 与 accepted `access_key/community/secret_key/token`。
2. F68 stale→fresh formatter：exit 0，输出四类 Nacos 结果均为空。
3. F66 XSKY TEST-NET：exit 0，未 I/O 即 `success=True`。
4. F67 IBM MQ parent+channel：exit 0，metric names 为 `['ibmmq_info','ibmmq_info']`，无 child metric。
5. F69 Enterprise import failure + 非 strict fallback：exit 0，加载 `plugins.script_executor.SSHPlugin`。

两次审查探针自身的纠正记录：首次 IBM MQ 断言错误地假设 Prom 名带 `_gauge`，exit 1；输出已显示真实名为 `ibmmq_info`，修正为检查两行同名后 exit 0。首次用本地 Stargazer venv 选择 OSS Nacos 作为 fallback 时，OSS import 因该 venv 缺 `requests` 而 exit 1；随后用不依赖 requests 的 SSHPlugin 验证 fallback 控制流 exit 0。前者同时暴露插件直接依赖/镜像 smoke 缺口，但未把本地陈旧 venv等同于生产镜像事实。

### 3.4 未验证

- 未连接真实 FalkorDB/Neo4j、Influx/Prometheus、Celery broker、多 Worker、NodeMgmt、NATS executor、IBM MQ/Nacos/OceanBase/BMC/存储/SNMP/云设备。
- 未验证 MySQL/PostgreSQL/Dameng DB 方言、生产镜像依赖、TLS/证书、网络 deadline/cancel、真实大结果与清理策略。
- 未运行整个 `server make test`、整个 Stargazer test/lint，也未取得 Stargazer coverage。

### 3.5 Enterprise 附件、模型与实例扩展

#### 3.5.1 命令与结果

1. 首次附件/fulltext 覆盖率命令（沙箱内失败）

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- 环境：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise`
- 命令：`uv run pytest -q -o addopts='' apps/cmdb_enterprise/tests/test_file_field_service.py apps/cmdb_enterprise/tests/test_file_field_integration.py apps/cmdb_enterprise/tests/test_attachment_view_integration.py apps/cmdb_enterprise/tests/test_fulltext_exclude_file_fields.py --cov=apps.cmdb_enterprise.instance_ops --cov=apps.cmdb_enterprise.model_ops --cov=apps.cmdb_enterprise.models.file_object --cov-report=term-missing`
- 退出码：2
- 结果：`uv` 无权读取 `/Users/windyzhao/.cache/uv/sdists-v9/.git`；按审批流程使用已批准的 `uv run pytest` 前缀重跑，未联网。

2. 附件/file/fulltext 聚焦测试与覆盖率（批准读取 uv cache 后）

- 工作目录/环境/命令同上。
- 退出码：0
- 结果：`21 passed in 30.42s`
- 覆盖率：

| 模块 | 行覆盖率 |
|---|---:|
| `instance_ops/constants.py` | 100% |
| `instance_ops/provider.py` | 79% |
| `instance_ops/service.py` | 80% |
| `instance_ops/storage.py` | 41% |
| `instance_ops/tasks.py` | 0% |
| `model_ops/provider.py` | 89% |
| `models/file_object.py` | 97% |
| 合计 | 72% |

3. 社区实例 CRUD/BDD 接线测试

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- 环境：同上。
- 命令：`uv run pytest -q -o addopts='' apps/cmdb/tests/test_instance_service_crud.py apps/cmdb/tests/bdd/test_instance_crud_bdd.py`
- 退出码：0
- 结果：`37 passed in 26.10s`
- 证明力：确认 create/update/batch/delete 的门面 hook 已接线；文件 hook 测试使用 fake extension，只证明调用次数，不能证明文件台账语义。

4. schema/migration 一致性

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- 环境：同上。
- 命令：`uv run python manage.py makemigrations cmdb_enterprise --check --dry-run`
- 退出码：0
- 结果：`No changes detected in app 'cmdb_enterprise'`。

5. provider/AppConfig 顺序冒烟

- 工作目录：`/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- 环境：同上。
- 命令：`uv run python -c "...django.setup(); ... print cmdb/cmdb_enterprise app index and provider type..."`
- 退出码：0
- 结果：`enterprise_index=20`、`cmdb_index=21`、`provider=FileFieldModelExtension`。

#### 3.5.2 未验证项

- 未连接真实 MinIO：presign、Content-Disposition、删除超时/重试和对象已不存在语义只做代码审查/Mock 测试。
- 未连接真实 FalkorDB：文件 raw metadata 排除、文件名 `_display` 命中和模型字段删除后的实际索引刷新未做真实图 E2E。
- 未启动真实 Celery worker/beat：只确认任务 import/config 路径；附件 GC 注册、调度、任务 state 和 worker 争抢未做运行时 E2E。
- `instance_ops/tasks.py` 为 0% 覆盖，`storage.py` 仅 41%；`apps.py`、`registry_hooks.py`、`urls.py`、迁移文件不在本次 coverage 统计目标内。
- 0002/0003 迁移属于自定义上报 schema，本任务仅检查迁移图/当前模型一致性，不复审其业务实现。
- CodeGraph：仓库有 `.codegraph/`，但 `codegraph explore` 退出 1；原因是 platform bundle 缺失，CLI 尝试写 `/Users/windyzhao/.codegraph/bundles/.dl-*` 被沙箱拒绝。按仓库规则使用 `rg`/逐文件读取兜底，未联网补装。

测试证据的完整可复制命令、绝对 cwd、环境、退出码和关键输出统一收录于 [reproduction-commands.md](reproduction-commands.md)。上述测试只证明记录的局部行为，不覆盖真实设备、真实 FalkorDB/Neo4j、NATS、Celery 多 Worker、MinIO 故障、多数据库或生产镜像依赖完整性。

## 4. Maintainability Verdict

1. **契约是否单一且可追踪？** 否。credential secret 分类、Agent object type、metric 名、formatter 路由、附件引用与 SQL 台账分别维护，跨层没有版本化 DTO 或 manifest 完备性校验。
2. **未实现能力是否 fail closed？** 否。21 个占位 collector 无 I/O 返回成功，Enterprise import 失败还可静默回退到 schema 不等价的 OSS 实现。
3. **状态与所有权是否可恢复？** 否。附件 claim/commit 无原子所有权，字段删除绕过引用回收，GC 部分失败仍以 Celery SUCCESS 终结。
4. **资源边界是否在最外层执行？** 否。multipart 在业务 size 校验前已经接收全部文件，周期 GC 也没有批次、deadline 或失败队列。
5. **新增对象或插件的复制成本是否可控？** 不可控。对象树、NodeParams、plugin registry、Agent manifest、metric formatter 和 credential schema 需要多处同步，重复键和部分 import failure 又不会原子阻断启动。
6. **现有测试能否防止跨层回归？** 不能。测试大量直接注入 formatter metric、mock extension 或断言占位 success，缺少脚本输出→Agent→metric→CMDB、图引用→SQL 台账→MinIO、multipart parser→临时存储的端到端负向契约。

建议职责归属：framework 负责原子 capability manifest、可信 credential DTO 和 request budget；adapter 负责真实协议 I/O、设备身份、结构化错误和类型路由；service 负责授权、引用状态机与事实写入；task orchestration 负责 generation/checkpoint/deadline/部分失败；storage adapter 负责幂等删除与可观测重试。短期应先隐藏未验证能力、拒绝未声明秘密字段和多归属文件，再补跨层测试；长期再统一 manifest、ErrorEnvelope、ResourceBudget 与 durable file reference。

## 5. Recommendation

**Block**。

### Recommendation Block

- **发布阻断条件**：`CMDB-F65/F66/F67` 全部关闭；凭据存储/API 脱敏、真实 collector I/O、IBM MQ 多对象路由均有跨层负向回归。
- **合并前条件**：`CMDB-F68`–`CMDB-F73` 的错误成功、silent fallback、registry 原子性、附件所有权/删除生命周期和 multipart 总量边界完成最小安全修复。
- **运行条件**：`CMDB-F74` 的 GC 必须具有批次、deadline、失败终态和重试/死信可观测性。
- **证据条件**：取得 gitlink `7c7db340961d6b010d2c533de92970df253b545f` 对应内容后，按 provenance 清单重新映射并重跑 [reproduction-commands.md](reproduction-commands.md)；当前 ignored 运行态与 gitlink 的映射未知，不能宣称可重建。
- **复审条件**：P0 全部关闭、相关 P1/P2 回归通过，且真实或等价环境验证 FalkorDB/Neo4j、NATS、Celery、MinIO、多数据库和至少一个真实 Enterprise 设备/协议链路后重新评估。
