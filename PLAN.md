# Plan: 修复 CMDB 节点管理同步的数据汇总与原始指标展示
_Locked via grill — by Codex + user; revised after adversarial review_

## Goal

修复节点管理同步抽屉中原始指标字段缺失、同名进程行不稳定、失败原因空白，以及多云区域结果跨批次混合、总体状态和最新时间错误的问题。页面保留主机与进程两类原始指标并在同一张表展示；四张汇总卡片继续采用 CMDB 主机实例对账口径，原始数据页签采用原始指标口径。展示数据严格来自同一父级采集运行的区域子执行快照；采集进行中继续展示上一完整批次，不额外显示当前运行状态。只保留最新完整批次的逐行明细，旧批次仅保留摘要。

## Repair contract

### 最小复现

1. 一条 `host_proc_usage_info_gauge` 指标包含 `pid`、`collect_status=failed`、`cmdb_collect_error="permission denied"`，经过 `NodeMgmtSyncService.get_display_payload()` 后，当前结果缺少 `_status`、`_error`、`pid`；页面失败原因显示 `--`，两个同名进程产生相同 `rowKey`。
2. 区域 1 为失败，区域 2 为成功且更新时间更晚。当前接口合并两个区域明细，却把总体状态显示为 `success`。
3. 区域 1 的指标时间为 10:00，区域 2 为 09:00 且任务 ID 更大。当前接口返回 09:00，而不是最大指标时间 10:00。
4. 区域任务 A 完成后、父运行完成前，后续独立执行覆盖 A 的 `CollectModels.task_id/format_data`。当前展示读取可变的区域任务当前值，无法证明所有明细属于同一个父 `NodeMgmtSyncRun`。

已运行的诊断命令：

```bash
cd server
MINIO_ENDPOINT=localhost:9000 \
MINIO_ACCESS_KEY=test \
MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false \
INSTALL_APPS=system_mgmt,node_mgmt,cmdb \
uv run pytest -q -o addopts='' --reuse-db \
apps/cmdb/tests/test_node_mgmt_sync_raw_display_diagnostic.py
```

诊断结果为 3 个确定失败：`KeyError: _status`、跨区域失败被展示为 `success`、最大时间 10:00 被错误覆盖成 09:00。临时诊断文件已删除。

### 根因与因果链

1. **原始指标字段契约断裂**
   - VictoriaMetrics 使用 `collect_status`、`cmdb_collect_error`；进程身份依赖 `__name__`、IP、PID 和进程名；
   - `RAW_DATA_FIELDS` 只允许 `_status/_error`，不保留 PID，也没有语义映射；
   - 进程指标通常没有 `model_id`，现有逻辑会默认成 `host`；
   - 前端读取 `_status/_error`，并在缺少 ID 时退化为 `inst_name` 行键；
   - 导致状态/失败原因空白、进程类型错误、同名进程重复 key、刷新或分页时错行/少行。
2. **展示聚合可变的区域任务当前值**
   - `_build_collect_display_payload()` 合并所有有效区域 `CollectModels` 当前 `info/collect_digest`；
   - `CollectModels` 每区只保存最近一次结果，展示没有父运行、配置版本或 `child_execution_id` 边界；
   - 导致不同批次、不同时间的区域结果被称为“本次”。
3. **总体状态和错误只取单个区域**
   - 明细来自全部区域，`run.status/error_message/time` 却取一个 `latest_collect_task`；
   - `updated_at` 还会被同步任务保存动作更新，不等于采集时间；
   - 导致失败区域被成功区域掩盖。
4. **时间按遍历顺序覆盖**
   - `message.last_time` 按任务 ID 顺序反复赋值，没有解析后取最大值。
5. **计数口径未显式区分**
   - `all/add/update/delete` 是 CMDB 主机实例对账口径；
   - `raw_data` 包含主机指标与逐进程指标；
   - 页面未说明双口径，造成漏数或重复观感。

### 影响范围

- 后端服务与状态机：
  - `server/apps/cmdb/services/node_mgmt_sync_service.py`
  - `server/apps/cmdb/models/node_mgmt_sync.py`
  - 新增 migration：按区域批次快照及清理状态。
  - `server/apps/cmdb/views/node_mgmt_sync.py`
  - `server/apps/cmdb/tasks/celery_tasks.py` 的配置版本 fencing/任务终态 CAS。
  - 节点同步 recovery/management command 的清理补偿入口。
- 前端：
  - `nodeMgmtSyncDetail.tsx`
  - `nodeMgmtSyncViewModel.ts`
  - `api/nodeMgmtSync.ts`、类型定义、中英文文案和定向 `tsx` 测试脚本。
- 不改变：
  - 节点管理到 CMDB host 的匹配和写入字段；
  - `host_proc_usage_info_gauge` 聚合写入 `host.proc`；
  - 自动同步/自动采集开关、周期、权限边界；
  - CMDB host 删除和自动关联策略。

### 最小安全修复

#### 1. 新增按区域保存的不可变批次快照

新增 `NodeMgmtSyncRegionSnapshot`，至少包含：

- `run`、`region_state`、`cloud_region_id`、`child_execution_id`；
- `status/reason_code`；
- `capture_status=pending|capturing|complete`、`capture_token`、`capture_deadline`、`capture_attempt`；
- 父批次规划后持久化的 `row_quota/byte_quota`；
- `summary_json`：小体量区域摘要、真实/保留/丢弃行数、主机/进程分项、最大指标时间；
- `detail_retained`；
- `cleanup_status`：`retained/pending/summary_only/failed`；
- `byte_size`、`truncated`。

新增逐行 `NodeMgmtSyncSnapshotRow`：

- `snapshot`、`bucket`、`ordinal`、`row_type`、`row_key`；
- 用于 ORM 搜索/排序的受控标量列：`inst_name`、`ip_addr`、`cloud_name`、`pid`、`process_name`；
- `payload_json`：单条安全规范化展示数据；
- `byte_size`。

数据库约束：

- `region_state` 一对一，保证一个父运行区域只有一个终态快照；
- 唯一约束 `(run, cloud_region_id, child_execution_id)`；未提交即阻塞的占位快照使用稳定的空执行 ID/区域 scope；
- row 唯一约束 `(snapshot, bucket, ordinal)` 和 `row_key`；
- 为 `(snapshot, bucket, ordinal)`、`row_type`、IP、PID 及受支持搜索字段建立必要索引；
- snapshot 创建后业务内容不可覆盖；重复 refresh 只允许读回同一结果。

父 `NodeMgmtSyncRun` 只保存聚合摘要、快照 schema/version、generation、完整性状态和预期区域数，不保存区域大 JSON，避免父行大 JSON 锁竞争。

#### 2. 所有区域终态都必须产生快照

- 已提交区域：观察到子任务终态时，重新校验 `CollectModels.task_id == state.child_execution_id`，捕获对应结果。
- 无接入点、非法区域、提交失败、执行 ID 缺失、配置已变化：在区域进入 blocked/failed 的同一事务中创建空明细占位快照，保留稳定 reason code。
- 子执行在捕获前被覆盖：创建 `COLLECT_EXECUTION_SUPERSEDED` 占位快照，绝不读取新执行结果冒充旧批次。
- 零区域运行：在任何 `all()` 聚合判断前单独处理，父运行固定为 `blocked`、`reason_code=COLLECT_SUBMISSION_BLOCKED`，并写入 schema v2 的 complete 空摘要，不能静默回退到旧成功结果。

快照完整性谓词：

```text
run 为终态
AND snapshot_schema_version = 2
AND snapshot_status = complete
AND snapshot_count = region_state_count
```

全成功、部分失败、全失败、全阻塞、执行被覆盖和零区域都可成为“完整终态批次”；完整不等于成功，只表示该父运行所有区域都有确定终态证据。

#### 3. 锁顺序与并发边界

避免跨子系统长事务和反向锁：

- 父运行建立全部区域状态后，按稳定 `cloud_region_id/region_state_id` 排序，一次性确定性分配父级行数和字节额度：先取整份额，再按稳定顺序分配余数。每个 snapshot 持久保存自己的额度；并行捕获只能使用已分额度，结果不受 worker 调度顺序影响且总和不超过父上限。阻塞区域未使用的额度不再临时转借，接受少量容量浪费以换取确定性和简单并发边界。
- `pending → capturing` 使用带 `capture_token/deadline/attempt` 的条件更新领取；领取时校验父 run 的 generation、active status 和 deadline。重复 worker 只有持有当前 token 才能提交。
- 已提交结果先用短事务锁单个 `CollectModels`，校验 execution 后读取已经在持久化边界裁剪过的有界结果；捕获端使用迭代器规范化，不做第二份全量深拷贝。
- 最终提交采用一个原子事务，固定顺序为 `CollectModels → parent run → region state/snapshot`：再次校验 execution、父 generation/active/deadline 和 capture token，然后以有界 `batch_size` 执行 `bulk_create`，并同时把 snapshot/state 置为终态。任一步失败均回滚 rows，不能留下部分明细。
- 未提交阻塞路径：只锁对应 region state 后创建占位快照，不访问 `CollectModels`。
- 父运行聚合：确认所有 region state 已终态、snapshot 数相等且所有 `capture_status=complete` 后，单独锁父 run；只读取不可变 snapshot 摘要，不再锁任务或配置。
- 父超时 recovery 只先锁父 run，关闭该 generation 的 capture lease，再为未完成区域创建完整 timeout 占位证据；不得先锁 state/task 后回头锁父 run。
- 旧明细清理：在新父运行完成事务提交后执行，每次只处理有界数量的旧 snapshot，不持有当前 run、配置或 CollectModels 锁。
- 修改 `_node_mgmt_collect_version_allowed()`：读取配置版本/开关不持 `select_for_update`，不在配置锁内更新 `CollectModels`；版本不允许时以 `instance_id + execution_id + RUNNING` 条件 CAS 标记任务错误。现有配置版本和 collect-dispatch claim 仍是业务 fencing。
- 禁止在持有 `NodeMgmtSyncConfig`、父 run 或 region state 锁时等待 `CollectModels`。

用 PostgreSQL 两连接交错测试覆盖：采集结果 CAS 保存、snapshot 捕获、配置更新、新执行领取和重复 recovery；断言无死锁、无混批、无重复快照。

捕获崩溃恢复规则：

- 领取后、写行前崩溃：lease 到期后，若父 lease 仍有效且原 child execution 仍匹配终态结果，recovery 用新 token 重领并按原额度重试；
- child execution 已被覆盖：收敛成 `COLLECT_EXECUTION_SUPERSEDED` 的 complete 空占位，不读取新结果；
- rows 写入或终态更新中崩溃：因同一数据库事务整体回滚，不存在可见的部分 rows；snapshot 保持 capturing，随后按上述规则重领；
- 父运行已超时或 generation 失效：捕获 worker 的最终 fence 必须失败且不得修改区域终态；父 recovery 将未完成区域收敛为 complete timeout 占位；
- parent finalizer 仅接受全部 snapshot complete，任何 pending/capturing 都不能发布该批次。

#### 4. 安全规范化原始指标

引入纯函数生成展示行：

- 从严格指标名白名单派生 `row_type`：
  - `host_info_gauge → host`
  - `host_proc_usage_info_gauge → process`
  - 未知指标不进入逐行快照，不得因缺少 `model_id` 默认成 host；计入 `raw_dropped` 并触发安全告警摘要。
- `_status = _status || collect_status`。
- `_error = _error || cmdb_collect_error`，之后统一安全处理。
- 允许字段：对象类型、指标名、实例名、IP、云区域、组织、`__time__`、PID、进程名、arg、exe、cwd、ports、状态和错误。
- 所有自由文本字段均做控制字符清理、凭据模式脱敏和字段级限长，而不只是 `_error`：
  - error 最大 500 字符；
  - arg/ports 最大 1024 字符；
  - exe/cwd/实例名最大 512 字符；
  - 其他标量最大 255 字符。
- 至少覆盖 `password/passwd/token/secret/access_key/private_key/Authorization/DSN URI` 及 `--password value`、`--password=value`、环境变量式凭据；不记录脱敏前原文。
- 未知任意字段、嵌套凭据对象不得进入 API。

节点同步系统任务的输入边界：

- 在 `celery_tasks.py` 保存 `system_code` 为节点同步任务的结果时，先以流式/迭代方式记录截断前真实 host/process/dropped 计数，再把 `format_data.__raw_data__` 裁剪到配置上限后持久化；不得构造第二份无界完整列表。
- 捕获层只消费这份已裁剪输入，并继续受每区域 `row_quota/byte_quota` 限制；输入已截断与最终保留截断都合并反映到摘要。
- 通用采集器既有的上游 materialization 不在本修复中重写，但本改动不得再放大峰值内存；对超限节点同步结果必须留下真实计数和安全截断证据。

#### 5. 稳定持久行键

快照捕获时按规范化后的 canonical JSON 稳定排序；对相同 canonical row 计算批次内 occurrence。生成：

```text
_row_key = sha256(run_generation | region | child_execution_id |
                  bucket | canonical_row | occurrence)
```

`_row_key` 随快照持久保存。前端只使用 `_row_key`，不使用数组索引；搜索、排序、页大小变化或刷新均不改变。

#### 6. 确定性父批次聚合

父运行只从自己的不可变 snapshots 聚合：

- 主机对账数 `all/add/update/delete/association` 及成功/失败数求和；
- 原始指标分项写入固定 schema：

```json
{
  "message": {
    "all": 1,
    "add": 0,
    "update": 1,
    "delete": 0,
    "association": 0,
    "raw_total": 51,
    "raw_host": 1,
    "raw_process": 50,
    "raw_dropped": 0,
    "raw_retained": 51,
    "raw_truncated": false
  },
  "detail": {
    "raw_data": {
      "total_count": 51,
      "retained_count": 51,
      "truncated": false,
      "data": []
    }
  }
}
```

- 恒等式固定为 `raw_total = raw_host + raw_process + raw_dropped`；`raw_retained <= raw_host + raw_process`。
- `COUNT_FIELDS` 加入所有整数计数；`raw_truncated` 使用独立安全布尔投影，禁止交给 `_safe_count()`；普通用户保留计数和布尔截断状态但行数组为空。
- 总体状态按所有区域状态：全 success 为 success；全部 failed/blocked 为 failed；其余终态混合为 partial_success。
- 错误摘要按云区域和 snapshot ID 稳定排序聚合；父错误文本只使用稳定 reason code/安全摘要。
- `last_time`：
  - 接受带 `Z` 或显式 UTC offset 的 ISO 8601，以及现有 API `%Y-%m-%d %H:%M:%S%z`；
  - 统一转 UTC 比较，取最大值；
  - 无时区值和非法值忽略；
  - 输出现有 API 固定格式 `%Y-%m-%d %H:%M:%S%z`；
  - 无有效时间输出空字符串。

#### 7. 展示选择和服务端分页

- 自动采集开启：
  - 忽略 running/submitted 新运行；
  - 选择 `(finished_at, id)` 最大、满足完整性谓词的最新终态父 collect run，不论其成功、部分成功或失败；
  - 最新完整失败/零区域批次必须展示自身空结果和错误摘要，不能退回旧成功批次；
  - 没有 schema v2 完整批次时才走 legacy 汇总，下一完整批次后切换。
- 自动采集关闭：继续展示最新 sync run。
- `display` 返回摘要、bucket counts 和默认第一页，增加 `display_schema=host_collect_v2`。
- 新增/扩展受权限保护的服务端分页接口，参数限定：
  - 在执行任何搜索或行查询前要求超级管理员权限；普通用户不能调用该接口，避免通过 `matched_retained_count` 枚举 PID、进程名或 IP；
  - `run_id` 必须等于当前允许展示的完整批次；
  - `bucket` 枚举；
  - `page_size` 默认 20、最大 100；
  - 搜索只覆盖实例名、IP、云区域、PID、进程名；
  - 返回字段语义固定：
    - `total_count`：截断前该 bucket 的真实总数，不随搜索改变；
    - `retained_count`：资源上限后数据库实际保留行数，不随搜索改变；
    - `matched_retained_count`：当前搜索条件命中的已保留行数，前端用它计算页数；
    - `truncated/page/page_size/data`。
- 分页直接查询 `NodeMgmtSyncSnapshotRow`，不得从 JSON 数组加载后在 Python 全量扫描；前端不再对返回数据二次分页。

资源边界（可配置但不得超过硬上限）：

- 单父批次所有 bucket 合计默认最多 20,000 行，硬上限 50,000；
- 单父批次所有 snapshot rows 合计默认最多 32 MiB，硬上限 64 MiB；
- 父运行按稳定区域顺序预分配 `row_quota/byte_quota`，各区域不可借用或突破；配额总和不得超过父级硬上限，输出不受并发调度顺序影响；
- 达上限后停止保留更多行，但继续记录真实 `raw_total/raw_host/raw_process/raw_dropped`、`raw_retained` 和 `raw_truncated=true`；
- 截断状态在页面明确展示，不得伪装为完整数据。

#### 8. 最新完整明细保留与补偿

- 新 schema v2 父运行完成提交后，把同一配置下更老终态 run 的 retained snapshot 标记 `pending`，有界批量删除其 `NodeMgmtSyncSnapshotRow`，保留 region snapshot summary、状态、时间、原因、真实计数和截断信息，状态改为 `summary_only`。
- 清理失败只将对应 snapshot 标记 `failed`，不得回滚新运行完成状态。
- 现有 `recover_node_mgmt_sync` 周期任务重试 `pending/failed` 清理；管理命令 `reconcile_node_mgmt_sync` 复用同一幂等清理入口作为人工重试。
- recovery 结果返回待清理/成功/失败计数，并写稳定结构化日志；连续失败反映到现有 reconcile health 的安全 reason code，不记录原始明细。
- 清理只限同一 `NodeMgmtSyncConfig`、更老、终态、非当前展示 run 的 snapshots。

### 回归测试

先写失败测试，再改实现。

1. 原始行契约：
   - `collect_status/cmdb_collect_error` 映射；
   - 从 `__name__` 正确派生 host/process；
   - PID/批准字段保留，未知/嵌套凭据不返回；
   - error、arg、DSN、token、命令行密码脱敏和限长；
   - 规范化过程中日志不出现原文。
2. snapshot 模型和状态机：
   - region snapshot 与 row 数据库唯一约束、索引和 migration 回滚；
   - 成功、无接入点、非法区域、提交失败、执行覆盖、零区域均产生完整终态证据；
   - 不匹配 child execution 不读取新数据；
   - 重复 refresh 幂等；
   - capture 在领取后、写行中、终态 CAS 前崩溃均可恢复；
   - capture lease 过期、父 generation 变化、父超时与 child execution 覆盖均确定性收敛，且无部分 rows。
3. 并发：
   - PostgreSQL 两连接交错覆盖结果保存/捕获、配置更新、新执行领取、重复 recovery；
   - 多区域按稳定 scope 预分配额度，父级行数/字节总和不越界且不同调度顺序得到相同保留结果；
   - 捕获最终提交与父 timeout recovery 交错时，失效 worker 无法越过 lease fence；
   - 无死锁、无重复、无丢失、无跨批次。
4. 聚合：
   - 全成功、部分成功、全失败、全阻塞和零区域状态；
   - 错误区域不被成功区域覆盖；
   - 最大 aware 时间正确，Z/offset/非法/naive/空值覆盖；
   - 1 主机 + N 进程时 `all=1`、`raw_total=N+1`、分项正确；
   - 未知指标计入 dropped、不入行，并满足总数恒等式；
   - cap 前后真实计数、保留计数和截断状态正确。
   - 超大输入在任务持久化边界被有界裁剪，不产生第二份无界副本，且保留真实计数。
5. 展示和分页：
   - active 新运行不替换上一完整批次；
   - 最新完整失败批次替换旧成功；
   - `(finished_at,id)` 决胜；
   - legacy 仅在无 v2 时回退；
   - `total_count/retained_count/matched_retained_count` 在截断、搜索和最后一页时语义正确；
   - page/page_size/search/bucket/run_id 边界；
   - 使用真实进程 fixture 按 `process_name` 搜索；
   - 普通用户在任何查询前被拒绝分页/搜索，仅能读取不随查询变化的聚合投影。
6. 清理：
   - 只清旧终态 snapshot rows；
   - 当前、活跃、其他配置不受影响；
   - 失败持久化并由 recovery/管理命令重试；
   - 新运行完成状态不被清理失败回滚。
7. 前端 `tsx` 定向测试：
   - 同名不同 PID 和完全相同指标的 `_row_key` 均唯一、刷新/搜索/分页稳定；
   - 双口径计数文案；
   - 服务端分页参数和响应应用；
   - PID、状态、失败原因、展开字段与截断提示；
   - 旧 schema 回退。

必跑验证：

```bash
cd server
MINIO_ENDPOINT=localhost:9000 \
MINIO_ACCESS_KEY=test \
MINIO_SECRET_KEY=test \
MINIO_USE_HTTPS=false \
INSTALL_APPS=system_mgmt,node_mgmt,cmdb \
uv run pytest -q -o addopts='' --reuse-db \
apps/cmdb/tests/test_node_mgmt_sync_display.py \
apps/cmdb/tests/test_node_mgmt_sync_collection.py \
apps/cmdb/tests/test_node_mgmt_sync_views.py \
apps/cmdb/tests/test_node_mgmt_sync_persistence.py \
apps/cmdb/tests/test_node_mgmt_sync_snapshot.py

cd web
pnpm test:cmdb-node-mgmt-sync-detail
pnpm lint
pnpm type-check
```

### 验收标准

1. 同一 IP 下两个同名不同 PID 的进程稳定显示；完全相同行也有持久唯一键，刷新、搜索和翻页不丢行、不串行。
2. 失败指标显示安全处理后的状态和失败原因；错误、命令行及其他自由文本中的凭据不进入 API、日志或页面。
3. 四张卡片仅统计 CMDB 主机实例；原始数据明确显示总指标数、主机/进程/丢弃分项、保留数和截断状态。
4. 页面所有区域行均来自同一父 run，并有唯一 region snapshot 与登记的 child execution 证据；阻塞和零区域也有完整证据。
5. 任一区域失败时总体不得显示成功；最新完整失败批次不得被旧成功结果隐藏。
6. 最新采集时间为该批次所有合法 aware 指标时间的最大值，并按固定 API 格式输出。
7. 新批次执行期间仍展示上一完整批次；完成后整体切换。
8. API 与数据库在硬资源上限内；大数据采用服务端分页，截断可见。
9. 仅最新完整批次保留逐行明细，旧批次保留摘要；清理失败可查询、可自动和人工重试。
10. 普通用户不获得 PID、命令行、错误原文或其他原始行权限，但双口径计数正确。
11. 捕获 worker 崩溃、lease 过期或与父超时并发后，批次最终要么形成全 complete 快照，要么保持不可展示；不得存在部分行、跨 execution 行或永久 capturing。
12. 相同区域输入在不同并发调度顺序下得到相同配额和保留结果；节点同步任务保存及捕获过程不新增无界全量副本。

### 风险

- 新增 migration、region snapshot 和逐行 snapshot 模型扩大变更面；通过唯一约束、索引、可回滚 migration 和兼容读路径控制。
- 每轮复制最新区域结果会增加短期数据库写入；通过按区域行、父批次硬上限、只保留最新明细和有界清理控制。
- 资源上限意味着超大批次会截断逐行展示；真实计数和截断状态必须保留，避免误判完整性。
- 进程自由文本存在泄密风险；所有自由文本统一脱敏和限长，未知字段默认拒绝。
- 并发捕获与采集 CAS 可能竞争；用固定锁顺序、短事务、唯一约束和真实 PostgreSQL 双连接测试验证。
- 确定性区域配额可能因失败/阻塞区域未使用额度而少保留部分本可容纳的行；这是为避免调度依赖和复杂额度回收接受的保守取舍。
- 通用采集器上游仍可能先 materialize 原始结果；本修复在节点同步持久化边界限流，不能完全消除上游既有内存风险。
- 历史数据无执行关联，不能回填为严格批次；仅兼容展示，下一完整批次自然替换。
- 截图列与当前仓库 raw-data 分支存在差异；实现以当前接口/组件契约为准，并用定向 UI 测试锁定。

## Approach

1. 先加入诊断中已变红的服务层测试，以及 snapshot 模型/并发/权限/前端契约的失败测试。
2. 新增 region/row snapshot migration、确定性区域配额、capture lease/token、唯一约束、索引、清理状态和纯原始行规范化函数。
3. 先在节点同步任务结果持久化边界加入真实计数与输入裁剪，再将所有区域终态路径统一接入带 fence、可恢复的幂等 snapshot 捕获。
4. 从不可变 snapshots 确定性聚合父运行，加入完整性谓词、资源上限和时间规范化。
5. 切换 display 选择，增加服务端分页和 legacy 兼容读。
6. 实现最新完整明细保留、周期/人工补偿和结构化可观测性。
7. 更新前端混合表、PID/展开详情、持久行键、双口径计数、服务端分页和截断提示。
8. 运行全部必跑验证，保留无法验证的原始证据。

## Key decisions & tradeoffs

1. 保留主机和进程两类原始指标；换取排障能力，但必须双口径展示并强化脱敏。
2. 两类指标在同一张表；改动较小，但主机行 PID 为空。
3. 严格按父级批次汇总；触及状态机和 migration，但根治混批。
4. 采用按区域 snapshot + 逐行 snapshot 模型而不是父 run 大 JSON；增加表和 migration，换取唯一约束、ORM 服务端分页、较小锁粒度和清晰保留策略。
5. 新批次进行中继续显示上一完整批次，不展示当前运行状态；页面稳定，但用户无法从该表判断后台正在采集。
6. 最新完整失败同样是权威批次，不回退旧成功；避免隐藏故障，但表格可能为空。
7. 仅最新批次保留明细，旧批次保留摘要；控制增长，但不能历史逐行回看。
8. 超限时截断明细并保留真实计数；服务可用性优先于无限量原始行展示。
9. 不迁移历史数据；兼容回退降低发布风险。
10. 分页/搜索仅超级管理员可用；普通用户只看到固定聚合计数，牺牲普通用户明细检索以消除资产枚举通道。
11. 按稳定区域顺序预分配配额且不回收；可能降低极端批次的容量利用率，但确保可复现并简化并发恢复。

## Risks / open questions

- 没有待用户决定的产品问题。
- 实施前用失败的真实 PostgreSQL 并发测试验证所选锁顺序；若发现现有路径存在反向锁，必须先调整内部事务边界，不得绕过测试。
- 具体 migration 名称和内部 helper 划分由现有项目风格决定，不改变以上数据/权限/状态契约。

## Out of scope

- 重做通用配置采集详情页。
- 修改 Stargazer 主机采集脚本、VictoriaMetrics 指标格式或 `host.proc`。
- 为旧批次提供历史逐行查询。
- 修改节点同步的 host 删除策略、唯一键或自动关联规则。
- 新增当前采集运行状态展示。
