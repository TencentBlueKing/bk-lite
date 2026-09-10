# CMDB 采集轮次完整性守门与统一对账调度

Status: done

## Problem Statement

配置采集的「采集」与「对账入库」是两条互不感知的时间线：Telegraf 按 interval 触发
stargazer 采集并经 NATS 分批推送到 VictoriaMetrics；server 的 Celery 任务按各任务的
`scan_cycle` 独立对账。由此产生四个问题：

1. **部分上报被消费**：大对象（如云账号全量资源）被 NATS 拆成多批推送，对账可能在
   只到了 1/3、2/3 时就执行，用不完整的快照做增删对比，`immediately` 清理策略下有
   误删风险。
2. **对账不知道采集完成与否**：没有轮次概念，全靠 `last_over_time[1h]` 时间窗口撞，
   实例下线后 1 小时内仍被视为存在；采集周期大于 1h 的任务查不到数据。
3. **按任务 beat 膨胀**：每个任务注册一条 `sync_collect_task_{id}` 周期任务，任务数
   增长时 beat 表和调度开销同步膨胀，且对账频率与采集频率耦合在同一个 `scan_cycle`。
4. **重复对账**：没有新数据也照常执行完整对账流水线，浪费查询与图库写入。

## Solution

1. **stargazer 每轮采集发布「轮次完成标记」**：所有数据批次发布成功后追加一条标记
   指标；任何批次失败则不发标记，本轮视为不完整。
2. **server 用全局 5 分钟守门任务统一对账**：只有出现新的完整轮次才执行对账流水线，
   否则跳过；移除按任务的对账 beat。
3. **页面手动执行直通对账，但复用最新完整轮次边界**，不受游标去重限制。
4. **对账数据按轮次时间戳过滤**，取代模糊的 1 小时窗口。

## Implementation Decisions

### 1. stargazer：轮次标识与完成标记

- 每轮采集开始时生成 `round_ts`（本轮采集开始的 Unix 时间戳，天然单调递增，不新造
  ID）。
- 数据行照旧按现有机制分批推 NATS（`MAX_NATS_LINES_PER_FLUSH=1000` /
  `MAX_NATS_BYTES_PER_FLUSH=900KB` 不动），数据行**不携带**批次或轮次标签——
  每轮变化的标签会造成时序库序列基数爆炸，且批次归属无业务意义。
- **所有批次发布完成并 NATS flush 确认后**，追加发布轮次完成标记指标：

  ```
  cmdb_round_complete_gauge{instance_id="cmdb_{task_id}", model_id="..."} <value = round_ts>
  ```

  标记只带稳定标签（`instance_id` / `model_id`），避免序列 churn；本轮批次数、行数等
  观测信息进 stargazer 日志（`collection_run_summary`），不进指标标签。
- **标记的语义 = 全部批次到齐**：任何一批发布失败 → 不发标记；下一轮按现有全量
  语义重传，天然幂等。
- 目标部分失败**不影响**发标记：轮次完整性 ≠ 目标全成功。失败行照旧携带
  `collect_status=failed` 进时序库，保留失败可见性。

### 2. server：全局 5 分钟守门任务

- 新增 beat `sync_collect_tasks_gate`（每 5 分钟），接管**所有走 VictoriaMetrics 对账
  的采集类型**（vm/云账号/k8s/网络等；范围为架构级，不区分插件）。
- **移除这些任务的按任务 beat** `sync_collect_task_{id}`：创建/更新任务不再注册，
  存量已注册的 beat 在运行期由守门任务或数据迁移幂等清理（遵守 server 启动约束，
  不在启动期做清理）。任务上的「采集周期」（`scan_cycle`/`cycle_value`）从此**只
  控制 Telegraf 触发采集的频率**，不再控制对账频率。
- 守门任务对每个任务的判定流程：

  ```
  查 cmdb_round_complete_gauge{instance_id="cmdb_{id}"} 最新值 → round_ts
  ├── 任务 exec_status == RUNNING        → 跳过（手动执行进行中，避免并发写）
  ├── 无标记（且任务曾有过标记）        → 跳过（本轮未完整上报）
  ├── round_ts == collect_digest["last_synced_round"] → 跳过（无新轮次）
  └── round_ts 为新轮次                  → 执行现有对账流水线
                                           → 成功后 last_synced_round = round_ts
  ```

- 同步游标存 `collect_digest["last_synced_round"]`（JSONField，无迁移）；同一轮次
  只对账一次，重复执行幂等。
- **升级兼容（关键）**：server 先升、stargazer 后升期间不存在标记指标。若守门任务
  发现任务**从未出现过标记**但时序库有该 `instance_id` 的数据（旧版 agent 上报），
  回退为现状行为直接对账；一旦该任务出现首个标记，即永久启用守门语义。避免升级
  顺序导致全部任务停止同步。

### 3. 手动执行直通

- `exec_task` 路径不比较 `last_synced_round`，每次点击都会派发对账；worker 在执行阶段
  解析最新设备完整轮次 `CompletedRound(T,C)`，不在 HTTP 请求事务内访问
  VictoriaMetrics。
- 手动对账按 `[T,C]` 消费与全局守门相同的完整快照；无新 role 标记时兼容
  旧的无 role 标记。标记查询失败必须将任务置为采集异常，不得误报为
  “未发现任何有效数据”。
- 确实无完整标记时才回退现有 1h 查询，并显式设为
  `snapshot_complete=false`，只允许 Upsert，不执行差集删除。
- 手动对账成功后同样刷新 `last_synced_round`，避免守门任务紧接着重复对账。

### 4. 对账数据按轮次过滤（增强，本期一并做）

- 拿到 `round_ts` 后，对账查询把数据行过滤为 `时间戳 >= round_ts`，取代
  `last_over_time[1h]` 的模糊窗口；`immediately` 清理的「权威快照完整」判定从
  "最近 1 小时的行"收紧为"本轮的行"。
- 手动执行优先使用最新完整轮次 `[T,C]`；只有无轮次标记的兼容回退路径维持
  现有 1h 窗口。已限定 `[T,C]` 的数据不再受格式化器“距当前时间超过一天”的
  旧鲜度判断影响。

## Testing Decisions

- 只断言外部行为：发布的指标行、beat 注册表、对账产生的图库实例与 `format_data`、
  跳过/执行的判定结果。
- **stargazer 侧**：
  - 全部批次发布成功 → 标记在所有数据行之后发出，value 为本轮 round_ts；
  - 任一批次发布失败 → 无标记发出；
  - 目标部分失败 → 标记照发，失败行带 `collect_status=failed`。
  - 先例：`test_nats_metrics_batch` 的发布断言写法。
- **server 侧**：
  - 无标记 + 曾有标记 → 跳过，不触达图库；
  - 同 round_ts → 跳过；新 round_ts → 对账并写游标；重复执行幂等；
  - `exec_status=RUNNING` → 跳过；
  - 手动 `exec_task` → 无条件派发，worker 按最新 `[T,C]` 执行并刷新游标；
  - 手动轮次标记查询失败 → 采集异常，不误报为无数据；
  - 轮次过滤：时序库同时存在旧轮与新轮数据时，对账只消费 `>= round_ts` 的行，
    `immediately` 不误删新轮缺失但属旧轮的实例以外的对象；
  - 兼容回退：从未有标记 + 有数据 → 按现状对账。
  - 先例：`test_network_pipeline` / vmware e2e fixtures 的数据驱动写法。
- 双租户要求不适用（不新增对外 API）。

## Out of Scope

- config_file 等经 NATS 直推 server 的结果链路（不走 VictoriaMetrics 对账），
  不在守门范围；实现时核实并登记不适用的任务类型清单。
- 不引入 JetStream 或 exactly-once 投递语义；批次丢失靠"不发标记 + 下轮全量重传"
  兜底。
- 不做跨轮增量对比；每轮仍是全量快照。
- `TASK_JOB_TIMEOUT` 状态收敛机制不动。

## Further Notes

- 与 `cmdb-collection-timeout-and-ip-precheck` 变更同期：该变更管"单目标怎么采"，
  本变更管"采完的结果何时可信地入库"，实现无交叉但测试可共用 e2e fixtures。
- **完成信号统一决定（2026-08-24）**：`cmdb-network-topo-collection-split` 的
  「运行完成事件」与本变更的「轮次完成标记」统一为同一个完成信号机制。拓扑通道复用
  轮次完成标记作为重放触发信号，标记需能携带通道角色（`collection_role`）、
  `channel_config_version` 与运行身份等 fencing 所需字段；不为拓扑另建事件通道。
- 移除按任务 beat 后，`CollectModelService` 中创建/更新/删除任务的 beat 注册逻辑
  需同步清理；删除任务时的 beat 清理路径也要覆盖。
- 守门任务单轮扫描的任务数有上界要求（分页遍历，避免任务数增长后单次扫描无界），
  遍历用稳定 keyset 游标。
- 标记指标名 `cmdb_round_complete_gauge` 为初拟，实现时与现有指标命名规范
  （`{model_id}_info_gauge`）对齐后可调整，调整不影响机制。

## Verification Evidence（2026-08-25）

- stargazer：`tests/test_round_complete.py` 及同批 collection 契约测通过。
- server：`apps/cmdb/tests/test_round_sync_gate.py` 通过（新轮次派发、兼容回退、
  RUNNING 跳过等）；守门触发拓扑重放见
  `test_gate_triggers_topology_replay_for_network`。
