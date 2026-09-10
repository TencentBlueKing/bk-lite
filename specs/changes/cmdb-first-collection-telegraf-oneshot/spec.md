# CMDB 首次采集切换为 Telegraf one-shot

Status: implemented

## Problem Statement

CMDB 周期采集任务创建或关键采集参数更新后，需要立即触发一次采集，避免必须等待首个
Telegraf 周期。现有首次采集由 Server 直接调用 Stargazer，绕过了实际 Telegraf 子配置；
同时首次采集投递和 NodeMgmt 配置推送分别注册 `transaction.on_commit` 回调，存在首次采集
早于配置可用的竞态。

Stargazer 的配置采集入口按异步接纳语义返回：

- `accepted` / `duplicate_active`：HTTP 202；
- `busy`：HTTP 429。

真实环境验证表明，Telegraf 1.34.4 的 `inputs.prometheus --once` 会在收到 HTTP 202 时
把本次 scrape 判为失败，即使 Stargazer 已经接纳请求；临时使用 `inputs.http` 并配置
`success_status_codes = [202]`、`data_format = "prometheus"` 后，可以正确解析接纳指标并以
成功状态退出。

## Goals

1. 创建任务及影响采集内容的更新，在现有首次采集策略允许时，通过目标节点上的 Telegraf
   one-shot 立即触发一次。
2. one-shot 只负责触发 Stargazer 采集，不等待本轮资产结果完成，不改变 CMDB 主任务
   `exec_status`。
3. 常驻 Telegraf 配置、进程和 Stargazer 协议保持不变。
4. 配置推送先于 one-shot，触发意图可幂等重试和补偿，网络双通道支持部分成功后只重试
   未接纳通道。
5. 目标主机执行具有严格资源边界，凭据、配置正文和响应正文不进入日志或持久化结果。

## Out of Scope

- 不修改 `agents/stargazer/`。
- 不修改常驻 ChildConfig 的 `inputs.prometheus`。
- 不重启或停止常驻 Telegraf。
- 不切换页面手工“执行采集”入口。
- 不改变采集结果回传、VictoriaMetrics、轮次完成标记和 round-sync 链路。
- 不增加对外 HTTP API。

## Confirmed Testing Seams

用户已在确认本方案后要求按 TDD 实施。测试只跨以下两个已确认 Interface，不以私有函数和
内部调用次数作为主要行为断言：

1. **NodeMgmt Telegraf one-shot Interface**

   ```python
   run_telegraf_child_configs_once(
       request_id: str,
       config_ids: list[str],
       expected_node_id: str,
       organization_ids: list[int],
   ) -> dict
   ```

   通过该 Interface 验证配置准入、受控转换、环境合并、目标节点执行、资源边界、每通道
   接纳结果和敏感信息隔离。

2. **CMDB 首次采集编排 Interface**

   以“创建/更新任务产生触发意图”和 Celery `trigger_first_collection` 为入口，验证
   fingerprint 幂等、配置先行、claim/fencing、通道级重试、终态收敛及主任务状态不变。

## Solution

### 1. 调用顺序

```text
保存 CollectModels + FirstCollectionRun(waiting_config)
  -> transaction.on_commit
  -> 推送/更新 NodeMgmt ChildConfig
  -> 标记 FirstCollectionRun pending 并投递 Celery
  -> CMDB Worker 领取 run
  -> NodeMgmt.run_telegraf_child_configs_once
  -> 目标节点 telegraf --once
  -> Stargazer 202/429
  -> 按通道持久化 accepted/retry_wait/partial/failed
```

首次采集不再单独注册一个可能抢跑的 `on_commit`。创建/更新链路的外部配置同步成功后才把
run 置为可执行；配置同步或 Celery 投递失败时保留持久化意图，由有界补偿入口恢复。

### 2. FirstCollectionRun

新增独立运行记录，不复用 `CollectModels.exec_status` 或图写入 Operation：

- `collect_task`：关联 CMDB 采集任务；
- `fingerprint`：现有 `FirstCollectionPolicy` HMAC 指纹；
- `task_revision`：本次任务保存产生的 `updated_at` 修订号，区分 A→B→A 回切；
- `reason`：`create` 或 `update:<changed_fields>`；
- `status`：`waiting_config/pending/running/retry_wait/accepted/partial/failed/skipped`；
- `config_attempt`、`dispatch_attempt`：配置补偿和 Celery 发布尝试次数；
- `attempt`、`claim_token`、`lease_expires_at`：one-shot 业务尝试及领取租约；
- `channel_results`：最多两个通道的有界结构化结果；
- `failed_stage`、`error_type`；
- `started_at/finished_at`。

唯一约束为 `(collect_task, fingerprint, task_revision)`：同一次保存的重复调度幂等，而配置从 A
变为 B 再回到 A 时产生新的首次采集意图。领取、超时回收和结果提交必须使用 claim token；
旧 Worker 不能覆盖新 Worker 结果。任务缺失、策略关闭、不再符合策略或 fingerprint 变化时
终止为 `skipped`，reason code 分别为 `missing/disabled/ineligible/stale`。

### 3. 通道

- 普通任务：`cmdb_<task_id>`；
- Network 设备通道：`cmdb_<task_id>`；
- Network 拓扑通道：`cmdb_<task_id>_topology`，仅在任务启用拓扑时包含。

一次请求只允许 1～2 个配置。部分成功时，下一次只向 NodeMgmt 传入尚未明确接纳的配置。

### 4. NodeMgmt one-shot

NodeMgmt 根据 ID 读取已保存的 ChildConfig，不接收任意 TOML、命令、可执行路径或环境变量。
执行前必须校验：

- 配置存在且 ID 与 `cmdb_<task_id>` / `_topology` 约定一致；
- 属于同一 Node、同一父 CollectorConfiguration 和 Telegraf Collector；
- `expected_node_id` 与实际唯一关联节点一致；
- 原配置只有受支持的 `inputs.prometheus`，无 output 和未知 input；
- URL 为 Stargazer 配置采集入口；
- 配置数量、配置大小、环境数量和执行超时均不超过上限。
- NATS 请求必须带 120 秒有效期的 CMDB 调用能力签名，签名绑定 request/config/node/org，且
  目标节点必须属于签名组织范围。

环境沿用运行时优先级：云区域环境 < 父配置环境 < 本次选中子配置环境。只加载本次子配置；
同名变量值冲突时失败，不静默覆盖。加密变量只在 NodeMgmt 内解密，绝不返回 CMDB。

### 5. 受控 TOML 转换

one-shot 临时配置按结构转换：

- `[[inputs.prometheus]]` -> `[[inputs.http]]`；
- `http_headers` -> `headers`；
- 保留 URL、timeout、headers 和 tags；
- 移除 `response_timeout` 等 `inputs.http` 不支持字段；
- 增加 `success_status_codes = [202]`；
- 增加 `data_format = "prometheus"`；
- 固定 `prometheus_metric_version = 2`，输出 measurement 为 `prometheus`；
- 为每个 input 增加仅作用于输出的 `oneshot_channel_id=<config_id>`；
- 统一追加 `outputs.file` 到 stdout，格式为 Influx line protocol。

转换不得采用无边界全局字符串替换。原配置若存在未知结构，直接返回永久失败。

### 6. 执行边界

- 每节点同一时刻最多一个 CMDB one-shot；
- 首期只支持 Linux 节点；Windows 在具备同等级硬内存约束前返回永久失败；
- 每次最多两个 input，合并配置最大 64 KiB，环境最多 256 项且总计最大 128 KiB；
- HTTP timeout 夹在 3～30 秒，进程总超时 60 秒；
- nats-executor 在目标侧对 stdout+stderr 合计保留 1 MiB，NodeMgmt 只解析前 256 KiB stdout，
  返回 CMDB 前进一步缩减为结构化结果；
- Linux 使用 60 秒 CPU 上限、8 GiB 虚拟地址空间硬上限及 Go `GOMEMLIMIT=384MiB`；
- Linux 临时目录由 `mktemp -d` 创建，权限 0700；同节点互斥使用原子 `mkdir`，避免固定 lock
  文件的软链接截断风险；
- 所有退出路径都清理临时文件；
- 只使用 Node 和 Collector 元数据解析出的 Telegraf 路径；
- 不停止、不重启或覆盖常驻 Collector 文件。
- 临时 TOML 经专用短生命周期环境变量传给 Executor，命令文本只包含变量名，避免 Executor
  DEBUG command 日志记录配置正文；Telegraf 启动前即清除该变量。

### 7. 结果判定

每个通道必须解析到：

```text
oneshot_channel_id=<config_id>
collection_request_accepted=1
status=accepted|duplicate_active
task_id=<stargazer task id>
```

- `accepted` 和 `duplicate_active` 均为成功；
- Executor 非零退出、HTTP 429、连接错误和超时按有界次数重试；
- 互斥退出码 75 映射为 `NodeBusy`；这是节点资源竞争而非本次采集失败，不消耗 one-shot
  的三次业务尝试，按 10 秒间隔使用独立的 8 次 Celery 重试预算，覆盖 70 秒 watchdog 窗口；
- 进程成功退出但缺少合法接纳指标、非法状态、配置校验失败为永久失败；
- 不能只依据进程退出码；已经有明确接纳证据的通道不再重试；
- 全通道成功为 `accepted`，部分通道在重试耗尽后为 `partial`，全失败为 `failed`。

### 8. 重试与补偿

- 首次执行后最多重试两次，退避 10 秒、20 秒；
- request/run 身份在重试间保持稳定，使不确定响应能由 Stargazer 收敛为
  `duplicate_active`；
- `waiting_config`、`pending` 及租约过期 `running` 由每分钟恢复任务扫描，每批最多 100 条；
  失败项刷新恢复时间并轮转到队尾，避免固定的最旧 100 条阻塞后续意图；
- `waiting_config` 恢复在锁定当前任务修订期间先删除预期 ChildConfig、再重新创建，兼容“配置已
  落库但 RPC ACK 丢失”，并阻止旧修订恢复覆盖并发的新配置；配置恢复最多尝试 3 次，之后终止
  为 `failed/config_sync`；
- 有 FirstCollectionRun 的创建/更新在外部同步失败时保留持久化意图并由上述任务补偿，不回滚
  已创建任务；没有恢复意图的 K8S、配置文件或短周期任务不得静默成功，明确返回“任务已保存但
  外部资源同步失败”，由用户重新保存触发重试；
- Celery 发布失败同样刷新恢复时间并最多尝试 3 次；耗尽后，无已接纳通道则终止为
  `failed/dispatch`，已有已接纳通道则终止为 `partial/dispatch`；
- 更新任务始终执行外部资源对账回调，即使新状态不再需要周期任务，也会删除遗留 Beat；
  VM 对账任务的遗留 Beat 另有全局守门清理作为最终兜底。
- 新执行任务使用独立 Celery 名 `execute_first_collection_run(run_id)`；旧三参数
  `trigger_first_collection` 仅安全消费并返回 `retired`，不再直连 Stargazer，避免滚动升级时
  新旧消息协议互相误解。

### 9. 日志

INFO 只记录 run 生命周期与终态，逐通道过程使用 DEBUG。失败由编排边界唯一持有 traceback
ERROR，并包含 `run_id/task_id/failed_stage/error_type`。不得记录 TOML、env、headers、凭据、
payload、完整 stdout/stderr 或 Stargazer 响应正文。

## TDD Vertical Slices

1. NodeMgmt：一个合法普通 ChildConfig 经 Interface 转成 one-shot 并返回 accepted。
2. NodeMgmt：duplicate_active、429、超时和缺失接纳指标。
3. NodeMgmt：双通道部分成功及 channel correlation。
4. NodeMgmt：非法节点、未知 input/output、环境冲突、大小/数量/超时边界与临时文件清理。
5. CMDB：创建/更新生成唯一 run，回滚不投递，配置同步后才 pending。
6. CMDB：领取 fencing、stale/disabled/ineligible/missing、主任务 `exec_status` 不变。
7. CMDB：10/20 秒通道级重试、partial/failed 终态和敏感日志回归。
8. 跨模块：普通单通道与 Network 双通道调用契约。

每个切片遵循 red -> 最小 green；完成所有行为切片后再做集中重构与代码审查。

## Rollout and Rollback

- 使用现有 `CMDB_FIRST_COLLECTION_ENABLED` 作为 kill switch；
- 新 Celery 消息协议要求两阶段滚动发布：发布前先将 kill switch 关闭，完成数据库迁移并部署全部
  Server、Celery worker 和 Beat；确认所有 worker 已注册新任务后再统一开启；
- 直接替换首次采集旧路径，不双写，也不在 one-shot 失败后回退 Server 直连 Stargazer；
- `StargazerCollectTriggerClient.admit()` 等仍被扫描链使用的能力保留；
- 回滚必须先在全部新进程关闭 kill switch 并停止 Beat 恢复投递，等待并确认 active、reserved、
  scheduled/ETA 中的 `execute_first_collection_run`（含 10/20 秒重试）全部消费或撤销，队列计数归零后
  才能回退全部进程；旧三参数消息只允许由新 worker 安全退休，不能发送给已回退的旧 worker。周期采集
  及常驻配置不受影响；临时文件无持久残留。

## Verification

- Server SQLite 定向测试：CMDB + NodeMgmt 新增测试及原首次采集测试；
- 相关 CMDB/NodeMgmt 回归测试；
- `makemigrations --check` 与迁移测试；
- 日志敏感哨兵和单一 traceback 所有权测试；
- 开发环境最终回归：普通单通道、Network 双通道、202 accepted/duplicate_active、临时文件清理；
- 不以开发环境已有 NATS 下游错误否定“触发已被 Stargazer 接纳”，本变更验收终点为 one-shot
  接纳结果，不宣称资产已完成入库。

### 实施落点

- CMDB 状态机与恢复：`server/apps/cmdb/models/first_collection_run.py`、
  `server/apps/cmdb/services/first_collection_orchestrator.py`；
- 创建/更新配置先行编排：`server/apps/cmdb/services/collect_service.py`；
- 新旧 Celery 协议隔离：`server/apps/cmdb/tasks/celery_tasks.py`；
- NodeMgmt 受控转换、授权与执行：`server/apps/node_mgmt/services/telegraf_oneshot.py`、
  `server/apps/node_mgmt/nats/node.py`、`server/apps/rpc/node_mgmt.py`；
- 数据库迁移：`server/apps/cmdb/migrations/0054_first_collection_telegraf_oneshot.py`。

### 已完成验证

- TDD 定向测试覆盖真实 Telegraf 1.34.4 line protocol、202 accepted/duplicate_active、双通道
  partial、签名及组织越权拒绝、未知 TOML、严格解密、资源上限、配置清理、状态机 fencing、
  10/20 秒重试及恢复。
- 开发环境真实 one-shot 返回 `exit_code=0`，解析到
  `prometheus ... collection_request_accepted=1 status=accepted task_id=...`；临时目录和互斥目录
  均已清理。
- 开发环境互斥竞争返回约定退出码 75，未创建或删除竞争者资源。
- 开发环境 Linux watchdog 对模拟卡死进程在约 1 秒后终止，返回 143，且锁目录、临时目录和子进程
  均无残留；本地 macOS 对应用例按平台跳过，并由该远端验证覆盖。
- SQLite 定向回归共 121 项通过、2 项 Linux 专属行为测试按本机平台跳过；其中卡死终止与清理已在
  开发环境 Linux 实测，PID 身份变化保护由 Linux CI/部署前测试执行。
- `makemigrations cmdb --check --dry-run` 无模型漂移；在全新独立 SQLite 库上从 CMDB 0001
  顺序迁移到 0054 成功。仓库当前全应用迁移测试仍受既有 Alerts 迁移状态不一致阻塞，因此
  本变更定向测试使用 SQLite `--nomigrations --create-db` 隔离验证业务行为。
