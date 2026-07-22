# CMDB IPAM 生产级审查

## 1. Summary

IPAM 已形成三条主链：子网详情经 `asset_info-View` 与实例级 VIEW 权限进入 IP 视图；IP 发现设计上复用采集任务、NodeMgmt、Stargazer/VM 指标与系统身份回写，但当前 Agent 插件路径受 `CMDB-F30` 阻断；人工与每小时 Beat 共用 `IPAMReconcileRun`，以 nullable unique `active_scope="global"` 裁决单活，Worker 用 owner token 抢占并保存统计或安全错误摘要。来源 CI 采用图节点 ID 递增游标、默认 500/最大 5000 的批次，子网与已有 IP 参考集也有显式上限。手工记录只读保护、非法子网跳过、失败释放 `active_scope`、Broker/作业错误不回显原文等骨架是正确的。

但执行边界仍有两个 P0。第一，IP 发现任务只校验采集任务菜单/任务对象权限，没有校验 `params.subnet_ids` 对应子网的实例与组织权限；当前可确定的是越权 ID 会被持久化，NodeParams 会以系统上下文读取目标 CIDR 并下发扫描范围。由于 `CMDB-F30` 当前阻断正常 Agent 加载，不能声称普通 create/update/execute 必然完成扫描与图回写；只有已有/延迟 VM rows、其他合法生产者，或 F30 修复后的正常链路到达回写层时，system 写才会进一步跨组织修改 IP 台账。第二，IPAM 作业的两小时租约没有续租或写副作用 fencing；新 owner 接管后，旧 owner 仍可继续创建/更新 IP、关联与离线状态，只是最后不能覆盖新 owner 的 ORM 终态。

另有三项 P1：失败/缺失扫描行被当成完整空快照并批量置离线；occupant 上限只统计唯一 `(subnet, ip)` 键，不能约束单 IP 的占用者列表、来源总扫描量和关联写；CIDR 重叠检查在锁外全量读取，两个并发但取不同唯一键的重叠网段可同时通过。在线 IP 视图的对端授权和无界返回分别引用 `CMDB-F14/CMDB-F16`；外部错误脱敏及 Agent IP 插件不可加载分别引用 `CMDB-F25/CMDB-F30`，不重复计数。

本域确认 5 个主 Finding：P0 2 个、P1 3 个、P2/P3 0 个，编号 `CMDB-F36`–`CMDB-F40`。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F36：IP 发现任务可持久化无权子网并下发其 CIDR 扫描范围

- Severity: P0
- Location: `server/apps/cmdb/serializers/collect_serializer.py:121-132`；`server/apps/cmdb/views/collect.py:210-242`；`server/apps/cmdb/node_configs/ipam/ip_discovery.py:50-92`；`server/apps/cmdb/services/ipam_discovery.py:50-65,142-190,205-296`
- Root cause category: 跨层契约不一致
- Evidence: 通用 `CollectModelSerializer.validate` 对 IP 任务在 125–132 行直接返回，只为网络拓扑做参数校验，没有解析、限量或授权 `subnet_ids`。采集 View 校验的是 `auto_collection-*` 与采集任务自身权限，因此组织 B 的子网 ID 可作为普通 JSON 持久化到组织 A 的任务。`IPDiscoveryNodeParams._load_subnet_scopes` 随后按这些 ID 查询子网，不带用户、组织或 permission map，并把目标 `cidr/gateway/reserved_addresses` 写入 NodeMgmt 下发参数。当前 `CMDB-F30` 使正常 Agent 插件加载失败，所以普通任务不必然产生扫描或 VM rows；若已有/延迟 VM rows、其他合法生产者，或 F30 修复后结果到达，回写层才会再次按 ID 加载子网，并由 `_system_create_or_update/_system_update` 以 `system`、`skip_permission_check=True` 条件性创建/更新 IP 和关系。此时 `allowed_org_ids` 来自目标子网而不是发起者授权范围，不能阻止跨组织回写。
- Trigger: 确定触发——仅有组织 A 自动采集新增/编辑权限的用户，在任务 `params.subnet_ids` 中提交组织 B 的子网实例 ID并保存任务，NodeParams 同步读取组织 B 的 CIDR 后写入 NodeMgmt 扫描配置。条件触发——该任务的已有/延迟 VM rows、其他合法生产者结果到达，或 `CMDB-F30` 修复后正常执行产出结果。
- Impact: 当前确定影响是跨组织子网引用被持久化，目标 CIDR、网关和保留地址进入无权任务及其 NodeMgmt 下发配置，破坏租户网络范围授权。若条件性结果到达，影响进一步扩大为扫描其他组织网段，并在组织 B 中创建、更新、置离线 IP 及建立关系；不能把这一后半段表述为当前普通 create/update/execute 的必然结果。
- Why existing tests missed it: `test_ipam_discovery_node_params.py` 用固定子网 ID并直接 Mock `_load_subnet_scopes`；`test_ipam_discovery_service.py` 把“所选子网”只当字符串白名单，测试还明确证明 system helper 跳过权限。五文件没有经过采集 create/update Serializer 的跨组织正反向用例。
- Minimal safe fix: IP 任务 Serializer/Service 必须在持久化前解析唯一且有硬上限的子网 ID，按当前用户和组织逐实例要求 VIEW/OPERATE（产品需明确扫描所需操作级别）；持久化授权快照或稳定 scope，NodeParams 和回写再次验证子网仍在该 scope 内。拒绝路径必须发生在 NodeMgmt 下发前。
- Required tests: 组织 A 用户引用组织 B 子网时 create/update 403/400 且零持久化、零 NodeMgmt；同组织实例权限允许/拒绝、include_children、子网被转组/删除、重复/非法/超限 ID；分别覆盖当前 F30 阻断时零扫描/零图写，以及已有/延迟 VM rows、其他合法生产者、F30 修复后结果到达时仍只回写授权子网。
- Long-term design note: 采集任务权限不等于任务内资源权限；所有“任务引用实例 ID”字段应复用统一 `AuthorizedResourceScope`，执行时消费不可伪造的授权快照，而不是让插件用 system 权限重新解释请求参数。

### Finding CMDB-F38：IPAM 租约过期接管只保护终态，旧 owner 仍可继续写图副作用

- Severity: P0
- Location: `server/apps/cmdb/services/ipam_reconcile_job.py:71-160`；`server/apps/cmdb/services/ipam_reconcile.py:127-213,220-297`；`server/apps/cmdb/tests/test_ipam_reconcile_job.py:88-110`
- Root cause category: 并发或幂等设计问题
- Evidence: `claim` 一次性发放默认 7200 秒租约，运行期间没有 renew；`execute` 抢占后直接调用完整 `run_reconciliation()`，该函数及 `_upsert_ip_instance/_mark_offline/_ensure_associations/_writeback_subnet_utilization` 均不接收 owner/generation，也不在批次前后核对持有权。租约过期后新 owner 可接管；旧 owner 的 `finish_success/finish_error` 因 token 条件只能返回 false，但此前所有图写已经发生。现有接管测试只直接调用旧 owner 的 `finish_success`，没有让旧执行继续图写。
- Trigger: 全量来源扫描、图写或网络暂停超过两小时；时钟/负载异常使租约提前失效；下一次每小时 Beat 或人工请求复用过期 RUNNING 并派发新 Worker，旧 Worker 随后恢复。
- Impact: 两代 Worker 可并发创建/更新 IP、关系、冲突状态、离线状态和子网利用率；旧快照可在新快照后落地，最终 `IPAMReconcileRun` 只显示新 owner 统计，实际图事实无法按 run 定位或回滚。
- Why existing tests missed it: `test_expired_owner_can_be_replaced_but_cannot_finish_new_generation` 只证明 ORM 终态不会被旧 token 覆盖；`run_reconciliation` 测试全部 Mock IO，没有租约过期、批次接管、旧 owner 晚到和真实并发进程。
- Minimal safe fix: 运行中定期续租，续租失败立即停止；每个来源/写批次前后验证 owner + 单调 generation，并让所有 IP/关系写经带 run generation 的可恢复 Operation 执行。仅增加租约时长不构成修复。
- Required tests: 旧 owner 在扫描、create/update、关联、offline、利用率各阶段暂停过期，新 owner 接管后旧 owner 零后续写；续租成功/失败、进程崩溃恢复、相同消息重投、多进程竞争与时钟边界；最终统计必须能对应唯一 generation。
- Long-term design note: 租约只回收所有权，不会撤销旧执行者；跨存储作业需要 generation fencing、批次 checkpoint 和幂等写事件，不能只在父任务终态做 token 条件更新。

### Finding CMDB-F37：失败或缺失扫描结果被当成完整空快照并批量置离线

- Severity: P1
- Location: `server/apps/cmdb/services/ipam_discovery.py:205-296,299-330`；`server/apps/cmdb/collection/plugins/community/ipam/ip.py:21-55`；`server/apps/cmdb/tests/test_ipam_discovery_service.py:14-51,53-82,334-358`
- Root cause category: 错误模型不清晰
- Evidence: `apply_ip_discovery_vm_rows` 丢弃 `collect_status=failed`、缺字段和未出现的子网行，却仍对每个 `selected_subnet_id` 调用 `apply_discovery_result(..., [])`。后者把空 `alive_addrs` 当权威完整快照，遍历该子网全部 `auto_collect=True` IP 并逐条置 offline。测试 `test_按任务所选子网回写_空子网也会触发离线` 明确把未返回任何行的子网置离线锁定为通过行为；失败行测试没有选择子网，因此绕开了该路径。
- Trigger: 某子网扫描整体失败、超时、指标延迟/过期、VM 查询漏行，或部分子网没有任何成功行但任务仍选择该子网。
- Impact: 网络仍在线的整段自动发现 IP 会被批量标为 offline，子网利用率与告警/冲突判断失真；任务摘要还可能把这类状态变更视为成功 update，运维无法区分“确认未存活”和“没有可信扫描结果”。
- Why existing tests missed it: 测试把“空子网触发离线”写成正向期望；没有 scan completeness、子网级成功/失败终态、VM 水位/批次 ID 或失败时保持旧状态的断言。
- Minimal safe fix: 指标契约必须为每个所选子网提供结构化完成标记和成功/部分/失败计数；只有确认完整且成功的快照才能执行 offline 差集，失败或不完整时保持旧状态并把任务置 PARTIAL_SUCCESS/ERROR。单个失败 target 也不能被静默丢弃。
- Required tests: 全失败、超时、无指标、部分目标失败、指标延迟、合法“扫描成功且零存活”六种场景；仅最后一种允许批量 offline；断言任务终态、失败摘要、旧 IP 状态和利用率。
- Long-term design note: “空集合”与“没有结果”必须在采集协议中类型化区分；所有快照型采集共享 completeness/watermark 契约，不能由消费者从数据行缺失反推成功。

### Finding CMDB-F39：occupant 上限可被单 IP 大量来源绕过，来源扫描与关联写仍无总预算

- Severity: P1
- Location: `server/apps/cmdb/services/ipam_reconcile.py:17-30,76-124,220-245,250-290`；`server/apps/cmdb/tests/test_ipam_reconcile_service.py:42-114`
- Root cause category: 资源边界缺失
- Evidence: 子网与已有 IP 参考集会以 `limit+1` 失败关闭，来源按 ID 游标分批；但 `IPAM_RECONCILE_OCCUPANT_LIMIT` 只在新建 `(subnet_id, ip_addr)` key 时比较 `len(occupants)`。同一个 IP 被任意数量 CI 引用时，`info["ips"]` 会无限追加 `model:id`，随后为每个引用逐条创建关系；来源 CI 的累计扫描行数、每 IP 占用者数、总关联尝试和 deadline 都没有上限。现有 limit 测试用两个不同 IP，恰好只证明唯一 key 数量。
- Trigger: 大量 CI 共用一个 IP（配置错误、NAT/VIP、脏数据或恶意上报），或启用来源模型包含海量实例；子网与已有 IP 数仍低于 200000。
- Impact: 单个 key 即可占用大量内存并触发海量逐条关系写；全量来源扫描与每 CI 线性遍历子网还可持续占用 Worker/图连接超过租约，放大 `CMDB-F38` 的双 owner 窗口并影响其他任务。
- Why existing tests missed it: `test_occupant_aggregation_fails_closed_above_limit` 使用两个不同 IP；没有同 IP `limit+1`、总来源行、每 key 引用、关联调用次数、执行 deadline、峰值内存或大数据基准。
- Minimal safe fix: 分别限制并计量来源总行数、唯一 IP 数、每 IP 占用者数、总关联数、运行时长与输出字节；达到任一预算时在任何图写前失败关闭或按持久化批次 checkpoint。子网匹配应使用前缀索引/区间结构，避免 CI×subnet 线性扫描。
- Required tests: `limit+1` 个 CI 共用同 IP、唯一 IP 边界、来源总行边界、关联预算、多个来源累计、deadline/取消、超限零部分写；真实规模基准记录峰值内存与查询次数。
- Long-term design note: batch size 只限制一次读取，不限制整项工作；使用统一 `ReconcileBudget` 和持久化 source/cursor/checkpoint，使内存、图写与租约在同一预算模型内收敛。

### Finding CMDB-F40：CIDR 重叠校验缺少并发范围锁，重叠子网可同时落库

- Severity: P1
- Location: `server/apps/cmdb/services/ipam_subnet.py:11-33`；`server/apps/cmdb/services/instance.py:632-676,706-770`；`server/apps/cmdb/services/unique_write_lock.py:21-79`
- Root cause category: 并发或幂等设计问题
- Evidence: create/update 在进入唯一签名锁之前调用 `validate_subnet_no_overlap`，该函数无分页读取全部 subnet 后在进程内比较。随后 `UniqueWriteLockService` 仅按实际唯一字段值生成哈希；`10.0.0.0/16` 与 `10.0.1.0/24` 的地址/掩码值不同，会取得不同锁。两个并发请求都可在对方图提交前看到“无重叠”并继续创建/更新；锁也没有表达地址区间冲突。
- Trigger: 并发创建包含关系的两个新子网，或创建与更新、两个更新并发把不同实例改成重叠范围。
- Impact: IP 归属不再唯一，`match_subnet_for_ip` 返回列表中第一个命中子网；对账、发现、冲突状态和利用率会因图返回顺序产生错误归属，且现有 API 没有自动修复冲突网段。
- Why existing tests missed it: `test_ipam_subnet_service.py` 仅用 Mock 旧列表串行验证重叠/不重叠/排除自身；brief 五文件不包含该测试，也没有线程/进程竞争、锁键或提交交错测试。
- Minimal safe fix: 把 CIDR 归一化为可比较区间并在权威存储建立原子冲突裁决；若图数据库无法提供区间约束，使用数据库持久化 subnet range registry，在事务内按地址族/范围序列化检查与登记，并以 operation/outbox 同图事实收敛。
- Required tests: create/create、create/update、update/update 的提交交错；包含、相同、相邻不重叠、IPv4/IPv6（若支持）与回滚；两驱动下只允许一个成功，失败方零图事实且可重试。
- Long-term design note: CIDR 不重叠是集合级不变量，不能用请求前全量读加值唯一锁实现；应由单一权威范围索引原子维护。

### 跨域证据与未重复计数风险

- `CMDB-F14`：`ipam_view` 只校验 subnet 中心实例，随后通过 `subnet_group_ip` 关系和 `subnet_id` 旧字段兜底返回对端完整 IP 实体，没有逐 IP 权限裁剪；属于既有“关系只授权中心实例”主 Finding。
- `CMDB-F16`：`ipam_view` 两条查询均无分页/rows/bytes 上限并在响应中返回全部 IP；属于既有在线实例查询无请求级预算，本域不新增 Finding。
- `CMDB-F25`：发现单 IP 写失败日志仍输出原始 `err`，对账关联失败也输出 `message`；敏感外部错误统一脱敏复用采集主 Finding。
- `CMDB-F30`：当前 Stargazer `ip/plugin.yml` 仍指向不存在的 `plugins.inputs.ip_discovery`，正常配置驱动 IP 发现入口会先加载失败；本域 `CMDB-F36/F37` 是该路径修复后仍会发生的独立授权与快照语义缺陷，不重复登记插件路径问题。
- `IPAMReconcileSource` 只有 ORM 模型、数据迁移种子和直接 ORM 测试，没有 HTTP/admin 管理入口、字段存在性校验或变更审计。本次未找到必须向普通用户开放来源配置的批准契约，因此只记录维护风险，不形成 Finding。

## 3. Test Review

在 `server/` 使用显式 SQLite、Celery、MinIO 与 `SECRET_KEY` 环境运行 brief 的五个文件，并对六个 IPAM 模块采集 coverage：

`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task8-review.sqlite3 uv run pytest -q -o addopts='' apps/cmdb/tests/test_ipam_views.py apps/cmdb/tests/test_ipam_discovery_service.py apps/cmdb/tests/test_ipam_reconcile_service.py apps/cmdb/tests/test_ipam_reconcile_job.py apps/cmdb/tests/test_ipam_reconcile_task.py --cov=apps.cmdb.services.ipam_view --cov=apps.cmdb.services.ipam_subnet --cov=apps.cmdb.services.ipam_discovery --cov=apps.cmdb.services.ipam_reconcile --cov=apps.cmdb.services.ipam_reconcile_job --cov=apps.cmdb.models.ipam_models --cov-report=term-missing`

首次沙箱执行因无权读取 `~/.cache/uv/sdists-v9/.git` 退出 2、未收集；受控缓存权限重跑为 **54 passed in 2.97s，exit 0**。覆盖率：`ipam_models.py` 100%、`ipam_discovery.py` 77%、`ipam_reconcile.py` 79%、`ipam_reconcile_job.py` 90%、`ipam_view.py` 40%，聚焦合计 **78%**。`ipam_subnet.py` 没有被 brief 五文件导入，coverage 表没有可声明数据；相关模块合计未达到 80%，视图明显不足，只有作业状态机达到核心 90% 目标。

有效证明包括：View 菜单权限与 subnet 实例 VIEW 拒绝；人工入口只入队；SQLite 上 active_scope 唯一冲突；owner 抢占、失败清理 `active_scope`、安全错误摘要、旧 token 不能覆盖终态；默认 ID 游标参数、existing IP `limit+1` 失败关闭；手工 IP 保护、关联方向、部分单条写失败继续和 system helper 契约。

证明力不足包括：没有 IP 任务 create/update 的子网实例授权；测试反而锁定空结果置离线；owner 接管只测终态，不测旧 Worker 图副作用；occupant 测试只数唯一 IP；没有 CIDR 并发、来源总预算、真实 FalkorDB/broker/VM/NodeMgmt/Stargazer、多 Worker、MySQL/PostgreSQL nullable unique 和异常恢复。SQLite 唯一测试不能单独证明所有受支持数据库的 nullable unique 语义；迁移使用标准 Django `unique=True, null=True`，本次仅完成静态跨数据库审查。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：IP 视图、发现、全量对账分层尚可，但授权 scope、快照完整性与 owner generation 没有显式领域对象，异常链路必须跨采集框架理解。
2. 新增同类插件是否需复制：会。子网 ID 解析、权限、预算、VM 完整性和 system 回写由 IP 插件自行约定。
3. 新增错误类型是否需改多处：会。Stargazer 行状态、VM 指标、发现 summary、采集任务终态和 IP 状态没有统一错误枚举。
4. 新增 callback 是否容易：不应新增；当前正式链路已迁到 VM，但缺少 snapshot ID/completeness，新增消费者会复制“空即成功”判断。
5. 接口是否易误用：是。`subnet_ids` 是未授权自由 JSON；`run_reconciliation()` 不要求 owner context；occupant limit 名称会误导为总占用者预算。
6. 日志是否安全且可排障：Broker/作业顶层错误已脱敏，但单 IP/关联错误仍原样输出；日志没有 source/cursor/generation/checkpoint 的完整关联。
7. 状态异常能否定位阶段：只能区分 PENDING/RUNNING/SUCCESS/ERROR，无法定位来源批次、图写、关系、离线或利用率阶段，也不能识别旧 owner 已写副作用。
8. 是否降低复杂度：数据库单活、稳定读游标和手工保护降低了正常路径复杂度；未统一的授权、快照语义和 fencing 把复杂度转移到生产故障与跨租户风险。

## 5. Recommendation

**Block**。

上线前必须先关闭两个 P0：`CMDB-F36` 在任务保存、下发和条件性回写三处绑定真实授权子网 scope；`CMDB-F38` 为租约续租、generation fencing 与批次 Operation 建立端到端单 owner。随后修复空/失败快照误离线、真实总资源预算和 CIDR 原子范围约束。跨域 `CMDB-F14/F16/F25/F30` 也必须一起收敛；仅延长租约、增加 semaphore、继续以选中 ID 作为授权、或把失败行过滤掉，均不能批准生产。
