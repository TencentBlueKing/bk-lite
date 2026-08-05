# Plan Review Log: 修复 CMDB 节点管理同步的数据汇总与原始指标展示
Act 1 (grill) complete — plan locked with the user. MAX_ROUNDS=5.

## Round 1 — Codex

- 严重：计划把所有区域明细塞进父运行 `detail_json.region_snapshots`，每完成一个区域都重写并锁住整块大 JSON；进程数量大时会造成行锁串行、数据库膨胀和接口内存放大，且无法用数据库唯一约束保证 `(run, region, execution)` 幂等。修复：新增按区域存储的快照模型及唯一约束，父运行只保存聚合摘要，避免大 JSON 读改写。
- 严重：快照方案仅覆盖 `submitted → 终态`，但无接入点、区域编码非法、提交失败等状态会在提交前直接变成 `blocked`，没有 `region_snapshot`；这与“只从快照聚合全部区域状态”矛盾，可能漏掉失败区域。修复：为每个区域状态都创建不可变终态快照，包括未提交即阻塞的占位快照。
- 严重：`arg` 被列为可直接返回的批准字段，但进程命令行经常包含 `--password`、token、DSN 或访问密钥；计划只明确清洗 `_error`，无法满足“敏感凭据不出现在 API、日志或页面”。修复：对 `arg` 等所有自由文本字段实施字段级长度限制和凭据模式脱敏，并加入命令行凭据回归样例。
- 严重：进程指标实际只有 `__name__="host_proc_usage_info_gauge"`，通常没有 `model_id`；现有规范化会把缺失 `model_id` 默认成 `host`，因此计划中的主机/进程计数和对象类型仍可能全部算成主机。修复：从严格白名单指标名派生独立 `row_type=host|process`，计数和展示均使用该字段。
- 严重：以“当前页绝对索引”消除重复行冲突并不稳定；搜索、排序、页大小改变或刷新后索引会变化，直接违反“刷新、搜索和翻页不串行”的验收标准。修复：后端生成规范字段哈希加批次内重复序号的持久 `_row_key`，前端只使用该键。
- 严重：“最近一个具有完整批次快照的已完成运行”没有定义完整性谓词；全失败、部分阻塞、被覆盖或零区域运行是否可展示均不明确，可能永久显示旧成功结果并隐藏最新终态失败。修复：明确并测试可展示条件、终态优先级、零区域语义和 `(finished_at, id)` 决胜规则，同时单独暴露最新终态摘要。
- 严重：计划要求锁定父运行、区域状态和 `CollectModels`，但没有锁顺序；现有采集路径会先锁配置再更新 `CollectModels`，而刷新路径若按父运行→区域→任务锁定，容易与配置变更或下一次下发形成死锁。修复：在计划中锁定全链路统一顺序，并用两个真实数据库连接覆盖刷新、结果保存、配置变更和新执行领取的交错测试。
- 高：没有给原始进程行数量、单字段大小、快照总字节数或响应大小设置硬上限；当前接口一次返回全部数据，客户端分页并不能防止数据库、序列化或浏览器 OOM。修复：定义可配置但有硬上界的行数/字节数，记录总数与截断状态，并采用后端分页或分区快照读取。
- 高：`raw_host_count/raw_process_count` 放在 summary 还是 `raw_data` 中未定义，普通用户投影的 `COUNT_FIELDS` 也不会自动保留它们，可能导致管理员正常、普通用户计数归零。修复：锁定响应 schema，并同步更新超级管理员与普通用户投影、类型定义及契约测试。
- 高：清理失败被描述为“后续运行重试”，但没有持久待清理标记、定时补偿入口或告警指标；若长期没有新运行，大明细将永久残留。修复：增加可查询的 cleanup 状态、幂等补偿任务、失败计数日志/指标及人工重试入口。
- 中：`last_time` 只说“解析有效时间取最大值”，未定义支持格式、时区归一化和无有效时间时的行为；现有普通用户投影只接受一种严格格式，ISO 8601 时间可能再次被清空。修复：统一解析 ISO 8601 为 UTC、输出固定 API 格式，并测试时区偏移、无时区、非法值及普通用户投影。
- 中：计划把前端测试视为“若已有运行器再运行”，但仓库已经使用 `tsx` 脚本测试且已有节点同步 view-model 测试接缝；仅 lint/type-check 无法验证键稳定性、搜索和计数逻辑。修复：新增明确的节点同步脚本测试命令并列入必跑验证，而非条件执行。

VERDICT: REVISE

### Codex response

全部意见均有直接代码证据或会影响数据正确性、安全和资源边界，予以采纳。计划改为新增按区域快照模型与数据库唯一约束，父运行仅保存聚合摘要；所有区域终态均生成快照，占位失败也不遗漏。进程类型由指标名派生，后端生成持久行键；所有自由文本统一脱敏和限长。新增服务端分页、硬资源上限、明确响应 schema、批次完整性谓词、清理补偿状态和必跑前端脚本测试。锁策略改为避免持有配置锁或父运行锁时等待可被采集 worker 更新的 `CollectModels`，并以 CAS + 唯一约束替代跨子系统多行长事务。

## Round 2 — Codex

- 严重：服务端分页数据仍存于每个区域的 `detail_json` 数组；Django ORM 无法高效跨区域 JSON 数组完成搜索、排序和分页，实现很可能每次加载最多 64 MiB 后在 Python 中扫描，分页只限制响应而不限制服务端内存/CPU。修复：增加逐行快照表或有索引的固定大小 chunk 表，保存 bucket、row type、搜索字段、row key 和安全 payload，以 ORM 查询分页。
- 严重：50,000 行/64 MiB 是“父批次”上限，但多个区域可并发捕获且明确不锁父运行，各区域都会认为额度尚未耗尽，合计可突破硬上限。修复：设计短事务的 per-run quota CAS/锁定计数器，或在计划中给出不会超出父级上限的确定性区域配额算法及并发测试。
- 高：计划禁止持有配置锁时等待 `CollectModels`，但现有 `_node_mgmt_collect_version_allowed()` 正是先锁 `NodeMgmtSyncConfig` 再更新 `CollectModels`，且该文件未列入影响范围。修复：把该写入路径纳入改动范围，明确如何拆事务或改成与新锁序兼容的 CAS。
- 高：零区域运行虽要求完整终态证据，但聚合规则没有指定其确切 `status/reason_code`；直接执行“全 success”判断会因空集合的 vacuous truth 得到 success。修复：明确零区域固定为 `blocked` 或 `failed` 及稳定 reason code，并在通用聚合逻辑进入 `all()` 判断前单独处理。
- 高：“严格指标名白名单”与“未知指标保留为 unknown”相互矛盾，而且 schema 只有 `raw_host/raw_process`，未知行会导致 `raw_total != raw_host + raw_process`。修复：要么拒绝未知指标并记录安全 dropped count，要么增加 `raw_unknown` 并锁定总数恒等式及 UI 文案。
- 中：`message.raw_truncated` 示例是整数并准备加入 `COUNT_FIELDS`，但资源契约和 `detail.truncated` 使用布尔值；现有 `_safe_count()` 会拒绝布尔值。修复：统一为布尔 `raw_truncated` 并增加独立安全布尔投影，或改名为具有明确含义的整数计数。
- 中：分页响应中的 `count` 在截断和搜索场景下含义不明确：可能是真实总数、保留总数或过滤后的保留数，前端无法可靠计算页数。修复：分别返回 `total_count`、`retained_count`、`matched_retained_count`，并测试截断后搜索和最后一页。

VERDICT: REVISE

### Codex response

全部采纳。新增逐行 `NodeMgmtSyncSnapshotRow`，用普通 ORM 字段和索引实现跨区域分页；区域 snapshot 只保留摘要。父 run 增加短事务配额计数，先预留再写行，确保并发区域总和不突破硬上限。把 `celery_tasks._node_mgmt_collect_version_allowed()` 纳入范围并改成不持配置锁更新任务的 CAS。零区域固定 blocked/`COLLECT_SUBMISSION_BLOCKED`；未知指标拒绝入行并计入 `raw_dropped`。`raw_truncated` 固定布尔并单独投影；分页明确区分真实总数、保留数和搜索后的保留数。

## Round 3 — Codex

- 严重：普通用户保留计数，而分页接口又返回随搜索变化的 `matched_retained_count`；即使隐藏行数据，普通用户仍可通过枚举 PID、进程名或 IP 得到命中数量，形成敏感资产探测 oracle。修复：分页和搜索接口在查询前仅允许超级管理员访问，普通用户只能获得不随查询变化的聚合计数。
- 严重：`capturing` 快照没有完整的崩溃恢复状态机；进程可能在配额预留后、部分写行后或终态 CAS 前退出，而来源随后又被新执行覆盖，导致快照永久停留在 `capturing`、配额无法释放、父运行无法完整聚合。修复：增加 capture lease/deadline/attempt，行写入与最终 CAS 原子化，并定义 recovery 对完整写入、部分写入、来源被覆盖和超时捕获的确定性收敛规则。
- 高：捕获流程没有在配额预留和最终 CAS 时校验父运行的 generation、active status 与 deadline；现有 recovery 可并发把父运行置为 timeout，捕获 worker 随后仍可能写入 rows 并终结 region state。修复：配额预留与最终提交都加入父运行 lease fence，失效时删除未提交行、释放预留并禁止修改区域终态。
- 高：分页声明支持按“进程名”搜索，但逐行模型的可查询标量列只有 `inst_name/ip_addr/cloud_name/pid`；真实进程指标使用 `name`，没有 `inst_name`，因此只能退回 JSON 查询或根本搜不到。修复：新增规范化后的 `process_name` 标量列和相应索引，并在搜索测试中使用真实进程 fixture。
- 高：父级资源上限只约束最终 snapshot rows，但流程会先从 `CollectModels` 复制并在事务外完整规范化原始 `format_data`；超大进程结果仍可在额度计算前造成 worker 内存峰值或 OOM。修复：为捕获输入增加读取/序列化硬上限与流式规范化策略，超限时保留安全摘要和截断证据，不构造无界中间列表。
- 中：并发区域按“先抢到父配额者优先”保留数据，达到上限时保留哪些区域取决于调度时序，同一输入可能产生不同快照且后到区域被完全饿死。修复：按稳定 region scope 预分配额度或串行执行确定性配额规划，再允许并行写入已分配额度。

VERDICT: REVISE

### Codex response

全部采纳。分页/搜索端点改为超级管理员专用，普通用户只能获得固定聚合计数。父运行提交后按稳定 region scope 一次性预分配行/字节额度，消除调度时序差异。snapshot 增加 pending/capturing/complete、capture token/deadline/attempt；捕获 claim 和最终提交都校验父 generation/active/deadline，row 写入与 snapshot/state 终态在一个事务内完成，崩溃由 recovery 确定性收敛。新增 `process_name` 标量列。节点同步系统任务在采集结果持久化边界记录真实计数并限制保存的原始输入，捕获端以迭代器规范化，避免新增无界副本。

## Round 4 — Codex

- 上一轮六项问题均已解决：搜索接口禁止普通用户访问，捕获具备 lease/token 和崩溃恢复规则，父运行使用 generation/deadline fence，补充了 `process_name` 查询列，输入在持久化边界受限，并采用确定性区域配额。
- 未发现新的实质性阻塞问题。计划现已明确数据模型、权限边界、并发锁序、失败收敛、资源上限、兼容路径和可执行测试矩阵，足以进入实现。
- 实施提醒：大批量 `bulk_create` 设置有界 `batch_size`。

VERDICT: APPROVED

### Codex response

接受实施提醒，并已把有界 `bulk_create batch_size` 写入修复契约。两阶段方案加固完成，共 4 轮对抗审查，最终通过。
