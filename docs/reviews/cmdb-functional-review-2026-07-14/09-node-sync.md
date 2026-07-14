# CMDB Node Management 同步生产级审查

## 1. Summary

Node 同步由一张全局 `NodeMgmtSyncConfig`、两类 `NodeMgmtSyncRun` 和按云区域生成的隐藏 `CollectModels` 共同表达。HTTP `task/config` 读写配置，`latest_run/display` 展示同步或采集结果，`run_sync/run_collect` 同步执行 Service；Beat 任务也直接调用同一入口。同步链路通过 `NodeMgmt.cloud_region_list/node_list` 拉取非容器节点和容器接入点，以 `(ip_addr, cloud)` 查找 CMDB host，创建缺失实例，再创建或更新区域采集任务并向 Node Management 下发节点参数；采集链路调用 `CollectModelService.exec_task` 提交各区域任务。`NodeMgmtSyncRun` 保存本次摘要、明细、错误与结束时间，配置保存最近同步/采集时间。

授权和数据正确性不足以进入生产。`task/config` 的 PUT 与 GET 共用 `auto_collection-View`，只读角色可以改全局调度并删除/重推全部系统采集节点配置。更严重的是，`run_sync/run_collect/latest_run/display` 都没有请求组织上下文；同步 RPC 只传 `is_container`/`cloud_region_id`，不传 `organization_ids` 或 `permission_data`，随后以 `operator="system"` 和节点自报组织作为 `allowed_org_ids` 跨组织创建资产。任意拥有全局菜单 Execute 的非超管可触发全部节点同步，View 用户又能读取包含 IP、组织和任务结果的全局运行明细。作为对照，Alerts 的 `snmp_trap_nodes` 会把用户名、域、当前组织和可见组织传给 `NodeMgmt.node_list`；`k8s_meta` 只读 Alerts 本地 `AlertSource` 元数据，不调用 Node Management，也不持久化运行状态。

同步本身还会把已有 host 直接计为 `update_success`，却完全不调用 `instance_update`。Node Management 中组织、OS、名称或 node_id 变化不会回写 CMDB，节点跨组织迁移后旧组织仍可能继续看见资产，而页面显示已更新成功。运行模型没有单活约束、owner、租约、deadline 或 stale RUNNING 恢复；手工和 Beat 可重叠执行，硬退出会留下永久 RUNNING。Node Management 分页又完全信任远端 `count`，没有总页数、节点数或整次 deadline，异常服务持续返回非空页时可无限 RPC 并全量占用 Worker 内存。

配置 singleton 和区域系统任务也没有数据库唯一身份或版本。并发首次访问可创建多条配置；并发同步可对同一 `system_code` 执行先查后建。配置切换及区域任务更新在数据库写入周围直接做 Node Management delete→push，部分失败没有持久化补偿。不过“外部副作用无可恢复状态机”与既有 `CMDB-F04/CMDB-F11` 同根因，本报告只把 singleton/先查后写竞态登记为新主 Finding，并把 delete/push 分叉证据引用到既有 Finding。

本域确认 6 个主 Finding：P0 3 个、P1 2 个、P2 1 个、P3 0 个，编号为 `CMDB-F44`–`CMDB-F49`。采集提交即把父运行标成功引用 `CMDB-F04`；原始 NodeMgmt/采集异常进入日志、`error_message/detail_json` 和 API 引用 `CMDB-F25`，均不重复计数。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F44：只读权限可以修改全局同步配置和节点下发

- Severity: P0
- Location: `server/apps/cmdb/views/node_mgmt_sync.py:12-19,42-45`；`server/apps/cmdb/services/node_mgmt_sync_service.py:230-284`
- Root cause category: 局部实现错误
- Evidence: `task` 同时接受 GET/PUT，但方法统一装饰 `@HasPermission("auto_collection-View")`；`config` 兼容入口同样只要求 View 并直接委派 `task`。PUT 调用 `update_task` 后会更新全局 Celery Beat 同步/采集周期；`auto_collect_enabled` 变化还遍历全部系统区域采集任务，调用 `delete_butch_node_params`，启用时再调用 `push_butch_node_params`。现有 `server/apps/cmdb/tests.py:1469-1496` 明确用仅含 `auto_collection-View` 的用户断言 PUT 200，测试把越权行为固定为成功契约。
- Trigger: 只有 `auto_collection-View`、没有 Execute/Operator/管理员权限的已认证用户，对 `/api/v1/cmdb/api/node_mgmt_sync/task/` 或 `/config/` 发送 PUT，关闭自动采集或改变周期。
- Impact: 只读用户可停止全平台 Node 同步/采集、删除远端节点配置或制造高频周期任务，造成监控中断、配置抖动和 Worker 负载放大。
- Why existing tests missed it: brief 两文件完全未导入 View；仓库旧测试只验证“View 权限 PUT 会调用 Service”，没有无写权限 403、外部调用为零或 GET/PUT 分权断言。
- Minimal safe fix: GET 保留 View；PUT 独立要求配置管理权限，至少 `auto_collection-Execute`，更稳妥为专用 Manage/Operator 权限。拒绝路径必须在进入 Service 前返回 403，且周期表、配置和 NodeMgmt RPC 均零副作用。
- Required tests: 仅 View 的 task/config PUT 均 403 且 `update_task` 零调用；有 Manage/Operator 权限成功；GET 仍允许 View；兼容入口与主入口权限一致；superuser 明确行为。
- Long-term design note: 不要让多 HTTP method 的 action 共享最低权限装饰器；配置读写应拆成独立 action 或使用 method-aware permission policy。

### Finding CMDB-F45：全局执行与展示绕过请求组织范围

- Severity: P0
- Location: `server/apps/cmdb/views/node_mgmt_sync.py:21-40`；`server/apps/cmdb/services/node_mgmt_sync_service.py:314-350,429-493,783-965,968-1101`；对照 `server/apps/alerts/views/alert_source.py:174-232`
- Root cause category: 跨层契约不一致
- Evidence: `run_sync/run_collect` 只检查菜单 Execute，不把 `request.user`、当前组织或可见组织传给 Service；`_fetch_non_container_nodes` 调 `node_list({is_container: False,...})`，`_pick_access_point` 只传 cloud region 和 container 标志，均缺 `organization_ids/permission_data`。随后 `InstanceManage.instance_create(... operator="system", allowed_org_ids=payload.organization)` 以节点返回的组织自我授权。`latest_run/display` 只检查 View，读取全局最新 run 和全部系统 `CollectModels`，明细白名单仍包含 IP、cloud、organization。Alerts `snmp_trap_nodes` 则显式传用户、域、current_team 和组织列表；`k8s_meta` 不调用 NodeMgmt，因此不能为 CMDB 全局同步提供授权先例。
- Trigger: 仅拥有某一组织、但具备 `auto_collection-Execute` 的非超管触发 run_sync；或只有 View 的用户读取 latest_run/display，而 Node Management 中存在其他组织节点。
- Impact: 调用者可让 system 身份跨组织创建主机和隐藏采集任务，并读取其他组织的节点 IP、组织归属、采集结果与错误；这是权限提升和跨租户数据泄露/写入。
- Why existing tests missed it: View 测试只用 Mock Service 验证 200；同步测试直接构造 organization 并断言创建，未建立用户范围或负向组织；RPC helper 测试还固定断言 query 只有 `is_container/page/page_size`。
- Minimal safe fix: 把可信授权上下文显式传入 Service；NodeMgmt 查询必须使用当前用户的 `permission_data` 与 allowed organization IDs，并在 CMDB 写前求交复核。若该任务设计为全局系统作业，HTTP 手工执行和全局明细应只允许平台管理员，普通用户只能查看按组织裁剪的投影。
- Required tests: 非超管单组织执行只查询/写入该组织；伪造 NodeMgmt 返回其他组织时零图写；View 展示按组织裁剪；管理员全局路径；空/非法 current_team fail-closed；`snmp_trap_nodes` 的用户权限 payload 契约回归。
- Long-term design note: 系统级 Beat owner 与用户发起执行必须是两种主体；不要用 `operator="system"` 覆盖真实调用者并让外部返回值决定授权边界。

### Finding CMDB-F46：已有主机被误报更新成功但从未持久化变化

- Severity: P0
- Location: `server/apps/cmdb/services/node_mgmt_sync_service.py:665-695,984-1034,1075-1101`
- Root cause category: 局部实现错误
- Evidence: 每个 region 先加载全部现有 host map。命中 `(ip_addr, cloud)` 时，代码只把旧 `existing` 追加到 `detail["update"]`、递增 `message["update"]` 并 `continue`；没有比较 payload，也没有调用 `InstanceManage.instance_update`。终态又固定令 `update_success=update` 并保存 SUCCESS/PARTIAL_SUCCESS。只有不存在时才调用 `instance_create`。
- Trigger: Node Management 中既有节点保持相同 IP/cloud，但 organization、operating_system、name、node_id 或 cloud_name 变化后再次同步。
- Impact: CMDB 资产长期陈旧且页面宣称更新成功；节点移出组织后旧组织权限仍可保留，移入组织后新组织看不到，OS/节点映射错误还会影响后续采集下发与运维决策。
- Why existing tests missed it: brief resilience 只测试两条新建中一条失败；仓库 sync 成功测试把 existing map 固定为空。没有 existing 分支的字段差异、组织迁移、`instance_update` 调用或最终图事实断言。
- Minimal safe fix: 对现有实例构造受模型约束的字段 diff；有变化时通过统一实例写入 Operation 调用 update，并传真实/系统授权主体；无变化单独计 unchanged，不能计 update_success。部分更新失败必须保留节点级脱敏结果。
- Required tests: organization 增删、OS/name/node_id 变化会真正更新；无变化计 unchanged；单节点更新失败不误报成功；跨组织变更权限与审计；重复同步幂等；与 Task 3 Operation/唯一规则路径一致。
- Long-term design note: 同步结果应由持久化事实的 before/after diff 生成，不应由“进入哪个 if 分支”推导成功。

### Finding CMDB-F47：运行记录无单活、租约、deadline 和僵尸恢复

- Severity: P1
- Location: `server/apps/cmdb/models/node_mgmt_sync.py:22-53`；`server/apps/cmdb/services/node_mgmt_sync_service.py:353-396,968-1176`；`server/apps/cmdb/tasks/celery_tasks.py:401-421`
- Root cause category: 并发或幂等设计问题
- Evidence: 每次同步/采集都无条件 `objects.create(status=RUNNING)`；模型没有 active scope、owner、generation、heartbeat/deadline 或条件唯一约束。HTTP 与两个 `shared_task` 调同一同步方法，没有抢占和任务时间限制。Python 异常可被 `_mark_run_failed` 收敛，但进程 kill/OOM/机器掉电不会进入 except；没有 Beat 扫描 stale RUNNING。并发同步都先读 host map，再各自创建/更新区域任务和图资产。
- Trigger: 用户双击、HTTP 与 Beat 同时触发、broker 重投，或 Worker 在创建 run 后硬退出/长时间卡住。
- Impact: 重复 RPC、图写、隐藏任务更新和节点 delete/push 可互相覆盖；latest_run 可能展示较晚开始却较早/较晚完成的任意记录，僵尸永远显示 running，运维无法安全判断是否可重试。
- Why existing tests missed it: 测试只覆盖单次调用的普通异常和单节点/任务继续；没有双触发、同 run_type 原子 claim、硬退出、过期接管、旧 owner 晚到或 latest_run 并发顺序。
- Minimal safe fix: 为 sync/collect 分别建立数据库单活 active scope 和 owner generation；条件抢占、heartbeat/deadline、stale 恢复与旧 owner fencing。Celery 设置可观测 soft/hard time limit，最终状态更新带 owner 条件。
- Required tests: HTTP+Beat、broker 重投和两 Worker 只有一个 owner；硬退出后租约接管；旧 owner 不能覆盖新代次；timeout/failed/partial/success 完整终态；latest_run 稳定按开始/代次语义返回。
- Long-term design note: `NodeMgmtSyncRun` 应是可恢复 execution，而不是仅供 UI 展示的日志行；父 execution 应关联区域/节点 checkpoint。

### Finding CMDB-F48：远端分页和全量快照没有资源预算

- Severity: P1
- Location: `server/apps/cmdb/services/node_mgmt_sync_service.py:44,442-455,458-521,665-695,984-1059`
- Root cause category: 资源边界缺失
- Evidence: page size 可配但没有 max pages/max nodes/max bytes；循环只在远端返回空页或 `len(nodes) >= count` 时停止。远端持续返回重复非空页并声明更大 count 时会无限递增 page。节点全部累积在 list 后再分组；每个 region 又至少两次 `_load_existing_host_map`，其内部 `search_inst(model_id="host")` 无分页读取全量 host，形成 region 数乘全模型扫描。
- Trigger: NodeMgmt count 漂移/错误、重复页、数据持续增长；大量节点与大量云区域；恶意或故障 RPC 返回超大 count 和非空页。
- Impact: 一个周期任务可无限占用 Celery Worker 和 RPC、耗尽内存，并对图数据库产生 N×全量扫描，阻塞其他采集和在线请求；结合 F47 会叠加多个失控执行。
- Why existing tests missed it: helper 只验证 1200 条正常 count 三页；没有重复页、count 漂移、最大页、总节点、deadline、内存或 region 查询次数断言。
- Minimal safe fix: 配置硬性 max pages/nodes/bytes/deadline，校验 page token/节点 ID 单调或去重进度；超限 fail-closed 为明确终态。以稳定游标流式处理固定批次，host map 一次有界加载或按 region/IP 定向查询。
- Required tests: 重复页和 count 永不收敛会在上限终止；count 增减、空页、重复节点；节点/字节/deadline 边界零后续副作用；多 region 查询次数上限；大批量内存基准。
- Long-term design note: 外部分页协议必须由本地预算约束；page size 只是单次请求大小，不是业务资源上限。

### Finding CMDB-F49：singleton 与区域系统任务缺数据库唯一身份和并发版本

- Severity: P2
- Location: `server/apps/cmdb/models/node_mgmt_sync.py:7-19`；`server/apps/cmdb/models/collect_model.py:119-125`；`server/apps/cmdb/services/node_mgmt_sync_service.py:205-260,603-663`
- Root cause category: 并发或幂等设计问题
- Evidence: `NodeMgmtSyncConfig` 没有 singleton key/唯一约束，`get_task` 先 `first()` 后 create；并发首次访问可创建多条，之后固定取最小 ID。`CollectModels.system_code` 也不唯一，区域任务用 `filter(...).first()` 后 create。更新配置在加锁前读取旧开关；区域更新无 version compare。delete→push 的 NodeMgmt 副作用又没有事件 ID/补偿，该部分与既有 `CMDB-F04/CMDB-F11` 同根因，不另计主 Finding。
- Trigger: 空表时两个 API/Beat 并发首次进入；两个同步同时发现同一 region 尚无系统任务；两个配置 PUT 基于同一旧值交错执行；NodeMgmt push 在 delete 后失败。
- Impact: 客户端可更新并收到一个随后永远不再读取的配置，周期表与 GET 展示不一致；同 region 可产生重复/冲突隐藏任务或一方失败；数据库任务已更新而远端仍缺配置，且无状态可自动修复。
- Why existing tests missed it: `test_get_task` 只串行调用两次；ensure tests把 filter/create 全部 Mock，未执行数据库并发和约束；配置测试用假的 atomic context，只断言调用顺序。
- Minimal safe fix: 用固定 singleton key/主键和唯一 `system_code`，在事务内 `select_for_update`/版本条件更新；把 NodeMgmt 参数同步作为带 generation 与幂等键的持久化 delivery，在提交后重试并记录阶段。重复键冲突应回读 winner，而不是返回 500。
- Required tests: 多线程/多进程并发首次创建仅一条配置和一个区域任务；并发 PUT 版本冲突；重复同步复用同 task；delete 成功 push 失败可重试；旧 generation 不覆盖新参数；SQLite/MySQL/PostgreSQL 约束一致。
- Long-term design note: 系统内置资源需要数据库可证明的业务身份；`order_by("id").first()` 不是 singleton，也不能承担并发幂等。

### 跨域证据：采集提交即成功与外部错误泄露引用既有 Findings

- `CMDB-F04/CMDB-F11`：`collect_hosts` 调 `CollectModelService.exec_task` 后只要消息提交未抛异常，就把区域加入 executed，并立即将父 `NodeMgmtSyncRun` 写 SUCCESS/PARTIAL_SUCCESS 和 `last_collect_at`；实际 `CollectModels` 仍是 RUNNING，后续 Worker ERROR/TIME_OUT 不会回写父 run。配置与区域任务的 NodeMgmt delete→push 也无持久化 delivery/补偿。这与既有“传输 ack/跨存储副作用缺少可恢复状态机”同根因，不重复计数。
- `CMDB-F25`：`_mark_run_failed` 把原始 `str(error)` 写 error 日志、`NodeMgmtSyncRun.error_message` 并经 latest_run/display 返回；单采集任务失败又把原文写 `detail_json.failed[].message`。canary secret、连接串、RPC 响应正文可跨日志、数据库和用户界面传播，沿用既有统一脱敏 Finding，不重复计数。

## 3. Test Review

在 `server/` 使用显式 SQLite、MinIO、Celery 环境执行 brief 两文件并测量 View/Service/Model：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task10-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_resilience.py apps/cmdb/tests/test_node_mgmt_sync_helpers.py --cov=apps.cmdb.views.node_mgmt_sync --cov=apps.cmdb.services.node_mgmt_sync_service --cov=apps.cmdb.models.node_mgmt_sync --cov-report=term-missing
```

首次沙箱执行因无权读取 `~/.cache/uv/sdists-v9/.git` 退出 2、未进入收集；受控缓存权限重跑为 **36 passed in 2.90s，exit 0**。覆盖率为 `node_mgmt_sync_service.py` **64%**（702 statements / 250 missed）、`models/node_mgmt_sync.py` **100%**（36/0），合计 **66%**（738/250）。View 未被这两份测试导入，coverage 没有生成该模块行，不能宣称 View 有覆盖；本域低于相关模块 80% 与核心路径 90% 目标。

有效证明包括：

- 顶层 fetch/list 异常会把当前 run 置 FAILED、写 finished_at 并重新抛出。
- 单节点创建失败不会中断同区域下一节点，单区域任务提交失败不会中断下一任务，父 run 会成为 PARTIAL_SUCCESS。
- 正常远端 count 的多页读取、无 cloud region 节点过滤、最新容器接入点选择，以及 display 序列化/白名单有纯函数证明。
- `get_task` 串行两次复用同一配置；但这不是并发 singleton 证明。

证明力不足包括：

- brief 两文件没有任何 View 授权测试；仓库旧测试反而明确断言仅 View 的 PUT 成功，锁定 `CMDB-F44`。
- 没有请求用户/组织上下文、跨组织 NodeMgmt 返回、展示裁剪或 system operator 边界测试。
- 没有 existing host 字段变化与真实 `instance_update`，只覆盖新建和新建部分失败。
- 没有重复执行、数据库原子 claim、租约、hard kill、timeout 接管、旧 owner 晚到或 stale RUNNING 恢复。
- 没有远端重复页/异常 count、最大节点/字节/deadline、流式批次、region×host 查询预算或内存基准。
- 没有真实 NATS/NodeMgmt、Celery broker/多 Worker、FalkorDB/MySQL/PostgreSQL；所有 RPC/图/采集执行均为 Mock。
- 失败测试使用固定 `fetch boom/list boom/exec boom`，并明确断言原文进入 error_message，未使用 canary secret 检查日志、DB、latest_run/display 脱敏。
- `k8s_meta/snmp_trap_nodes` 不在 brief 两文件；只做静态调用链和既有 Alerts 测试复核。既有 SNMP 测试仅 superuser+FakeNodeMgmt 200，没有普通用户 permission payload/组织裁剪负向断言。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：入口集中，但一个 Service 同时承担权限外的全局编排、RPC 分页、实例同步、任务 CRUD、节点下发、展示兼容和运行状态，且 `update` 计数不代表写入事实。
2. 新增同类插件是否需要复制代码：是。新的系统同步源仍需复制 singleton、隐藏 CollectModels、NodeMgmt 下发、run/display 和 Beat 编排，没有通用 execution/delivery 框架。
3. 新增错误类型是否需改多个模块：是。RPC、实例、节点参数和采集 Worker 错误分别由 Node sync、Collect Service、Celery 与 display 自行拼接文本。
4. 新增 callback 模式是否容易扩展：否。父 run 没有子 delivery ID 或结果回执，当前只能把 submit 当完成，新增 callback 会继续复制状态桥接。
5. 当前接口是否容易被误用：是。`task` 的 GET/PUT 同权；Service 不要求授权主体；`operator="system"` 和 `allowed_org_ids=payload.organization` 容易把外部数据误当授权。
6. 日志是否足够且不泄密：有 run/task/region ID，但异常原文进入日志、DB 与 API；无 owner generation、page budget、batch checkpoint 和脱敏错误码。
7. 状态异常时能否判断停在哪个阶段：不能。RUNNING 没有 heartbeat；SUCCESS 可能只表示采集已提交；区域/节点写、节点参数推送和实际 Worker 终态无法从父 run 还原。
8. 设计是否降低复杂度：统一显示结构和节点字段白名单有价值，但全局权限、执行代次、资源预算和投递状态缺失，把复杂度转移到人工排障与跨系统对账。

## 5. Recommendation

**Block**。

生产前先关闭三个 P0：PUT 必须使用真正写权限；用户执行与展示必须按组织 fail-closed，系统 Beat 与用户主体分离；已有 host 必须真实更新并由持久化 diff 计算结果。随后为 sync/collect 建立单活租约、deadline、旧 owner fencing 和僵尸恢复，并对 NodeMgmt 分页、节点总量、字节、整次耗时及图查询设置硬预算。`CMDB-F49` 的 singleton/系统任务唯一身份应与持久化 NodeMgmt delivery 一并补齐；跨域 `CMDB-F04/F11/F25` 必须让采集实际终态回写父 execution，并在所有日志、DB、API 边界统一脱敏。仅让现有 36 个 Mock 测试继续通过、限制 page size 或把错误 catch 后写 FAILED，不能批准生产。
