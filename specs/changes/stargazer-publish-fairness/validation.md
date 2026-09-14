# 发布链路修复验收（2026-09-11）

## 第二阶段：按用户确认补齐排队与发送预算分离

本节对应最新 `spec.md`；下方“第一阶段历史记录”中的队列包含在 120 秒绝对截止内的方案已被替代。

### 已补齐的问题

1. 默认 NATS Run 不再有从入队开始的 120 秒绝对截止，也不再用 60 秒入队超时淘汰目标。容量满时等待，120 秒仅约束累计活动发送；并行 ACK 取时间并集，chunk、重试沿用剩余额度。
2. 首投等待、编码准入/执行、元数据准备、信贷等待、实际发送和端到端耗时分开记录。信贷等待可与已有 ACK 重叠，不可把各阶段 P99 相加；活动单元驻留较久不再被容量提示认定为发送超时。
3. 汇总按已完成回执事件进行，有界注册且固定 worker；前四个慢回执不再挡住后续终态。Coordinator 入队返回的是采集摘要，上游 Pending 不再保留托管 payload。
4. 元数据先写入再发送，默认最多 2 次幂等尝试，独立准备阶段 30 秒上限；未调用 SDK 的连接失败归为失败，非法编码归为永久失败，部分投递/未确认才归为未知。异常身份及链仍保留，退出帧、编码闭包不再延长 payload 生命周期。
5. 编码提交前准入 2 个线程任务，逐行协作取消；不超过每目标 900KB 实际内存上限的小结果复用验证后的编码，超过上限回退原有有界重编码。保留发送前完整校验及结果大小限制。
6. 显式 Core NATS fallback 也使用累计预算，SDK 调用前标记首投，并在连接前、逐条发送前、flush 前后检查截止。Core flush 与 JetStream PubAck 的确认语义仍不同。

### 测试方式与证据

新增/增强测试继续在 Publisher/receipt、Coordinator 和真实 Run 链路测试，只替换外部探测、采集插件、SDK 或可控时间。
关键缺陷均先出现失败再修复：排队超预算、四个慢回执阻塞汇总、元数据未发送却未知、取消编码后仍持续遍历、重复编码、连接前失败误报未知、Core fallback 绕过预算及同步 SDK 越过截止继续发送。

完整基准使用 `--pipeline run`：**CollectionScheduler → TargetCollectionExecutor → RunResultSink → Publisher → 编码 → JetStream**。
7 个 Run、3838 个合成目标、Worker/Payload 各 120、4 个 Writer、256 条/32MiB 全局信贷、64 条单调用额度、2 个编码线程。
8 个大目标各 2048 行、3830 个小目标各 1 行，共 20214 行。并发量不再使用事故日志的 160。

完整链路三种场景分别验证吞吐、慢 ACK 与排队语义，最终顺序复跑数据如下（只在 121 秒信贷阻塞阶段同时运行回归，恢复发送阶段无并行测试）：

| 指标 | 正常 ACK 15ms | 慢 ACK 1384ms | 信贷阻塞 121 秒后恢复 |
|---|---:|---:|---:|
| 采集 / 发布成功目标 | 3838 / 3838 | 3838 / 3838 | 3838 / 3838 |
| 已确认行 / 期望行 | 20214 / 20214 | 20214 / 20214 | 20214 / 20214 |
| 整轮耗时（秒） | 3.8851 | 113.0637 | 122.9379 |
| 小结果端到端 P99（秒） | 1.6360 | 5.0200 | 121.0680 |
| 大结果端到端 P99（秒） | 3.6136 | 107.7002 | 122.8148 |
| 首次发送前 P99（秒） | 1.6195 | 3.6311 | 121.0488 |
| 累计活动发送 P99（秒） | 0.0465 | 1.4339 | 0.0383 |
| 事件循环 P99（秒） | 0.0672 | 0.0130 | 0.0220 |
| CPU 时间（秒） | 2.9426 | 7.9208 | 5.0623 |
| RSS 峰值（MiB） | 85.08 | 80.11 | 82.62 |

三组均无截止超时，Worker / Payload 峰值均 120，全局消息峰值 256；结束时 Payload、消息、字节、SDK future、后台任务全部为 0。
121 秒阻塞组的首投等待 P99 超过 120 秒，但活动发送 P99 只有 0.0383 秒，所有目标仍成功，实际验证了排队不消耗发送预算。
同场景本机样本会受调度和合成插件构造影响，事件循环 P99 尚非严格改善保证，不能宣称原日志中的 CPU / SNMP 资源争用已在生产消除。

复跑命令（`agents/stargazer`）：

```bash
.venv/bin/python scripts/benchmark_publish_fairness.py --pipeline run --ack-ms 15
.venv/bin/python scripts/benchmark_publish_fairness.py --pipeline run --ack-ms 1384
.venv/bin/python scripts/benchmark_publish_fairness.py --pipeline run --credit-pause-seconds 121 --ack-ms 15
```

信贷阻塞由外部 SDK 替身占满 256 条全局信贷模拟；为保持这些测试占位消息 121 秒，测试窗口 ACK 上限为 126 秒，目标累计发送预算仍为 120 秒。正常/慢 ACK 基准的 ACK 上限仍为 30 秒。此参数仅在测试脚本中，不改生产配置。
压力工具的任务峰值为 50ms 间隔采样，CPU 时间包含合成插件及监测开销，不能直接和旧 producer 工具计算客户端 CPU 改善比例。

### 同口径 producer 基准补充比较

仍以固定提交 `2164b6be04e7a55ec9532297ad13de34576312ea` 为基线，使用同一工具的 `--pipeline producer --ack-ms 15`、相同 3838 目标/120 并发参数顺序比较。此模式不经过 Scheduler/Sink，不与上表混算；它只用于与旧实现同口径比较发布路径。验证期间用户已提交其他 CMDB 错峰工作，当前 HEAD 前进至 `eece86699`，本报告基线没有随 HEAD 移动。

| 指标 | 固定基线 | 最新实现 |
|---|---:|---:|
| 整轮耗时（秒） | 7.2328 | 2.3724 |
| 小结果 P99（秒） | 1.5907 | 0.5509 |
| 大结果 P99（秒） | 5.5183 | 2.2467 |
| CPU 时间（秒） | 2.5595 | 2.3435 |
| RSS 峰值（MiB） | 74.80 | 87.34 |
| 事件循环 P99（秒） | 0.0150 | 0.0220 |
| 成功目标 / 确认消息 | 3838 / 20214 | 3838 / 20214 |

本机单次整轮耗时下降约 67.2%，小结果 P99 下降约 65.4%；但 RSS 和事件循环 P99 高于基线，不能只报告吞吐改善或声称消除了生产 CPU 争用。两版本结束时的 Payload/信贷/SDK future 均为 0。

### 最终回归与覆盖率

- 最终完整综合命令 **202 passed，74.61 秒**；`test_publish_fairness.py` 现有 31 项，包含累计预算、并行 ACK、chunk 间长等待、完整 Run、Core fallback、实际引用释放、失败阶段、取消与敏感日志哨兵。
- 测试过程中修正了一处计时断言：原先从 enqueue 开始睡眠，错误地要求纯信贷等待也达到完整 0.2 秒；现在先确认进入信贷队列再开始计时，未放宽生产预算。
- Coverage.py 分支采集，固定基线 diff 新增行与可执行语句相交：生产改动行 **437/470 = 92.98%**；新文件 `publish_budget.py` 全部可执行行纳入。分文件：publisher 180/197、delivery 52/57、window 39/39、budget 33/34、helper 95/105、nats_utils 35/35、application 3/3。不是整仓覆盖率。
- 最终 14 个 Python 文件 Black 检查通过，核心变更 isort 检查、`git diff --check` 通过。完整回归命令沿用下方历史记录中的综合命令（已包含新用例）。
- 本机未安装 pytest-cov；借用现有 Server venv 的 Coverage.py，通过 Stargazer venv 执行；未安装依赖或修改锁文件。

### 独立审查与限制

Standards：最终未解决 0 项；Spec：最终未解决 0 项。两路均发现 Core fallback 兼容遗漏，已补共享预算、首投标记及同步截止检查并通过复审。
`make lint` 已执行，仍被现有缺失 `.pre-commit-config.yaml` 和不可写 pre-commit 缓存阻断；不会为本次修复改动全仓门禁配置。
没有部署、扫描真实设备、引入持久化补发或独立进程，也没有修改用户正在实施的 Server 错峰逻辑。
shutdown grace 为排空宽限；协作取消不等于强杀线程，不响应取消的外部阻塞调用仍可能延长安全 join。
192.168.198.* 的 128→61 差集与真实 CMDB 入库仍需同一轮 IP 清单和消费端日志，不能用本机合成压测代替。

## 第一阶段历史记录（不作为最新超时契约）

### 历史结论

按用户最新要求，修改前后均使用单 Worker **120** 目标并发和 **120** Payload 额度，不使用历史日志的 160。
在相同的 1.384 秒模拟 ACK、7 个运行、3838 个目标、120 秒逐目标发布总截止下，
旧链路 3830 个确认、8 个未知；新链路 3838 个全部确认。小结果 P99 从 65.98 秒降到 4.33 秒。

这验证了客户端批次独占和结果生命周期耦合会放大发布截止问题，不证明生产 NATS broker 没有瓶颈，
也不是 192.168.198.* 的 SNMP 或 CMDB 入库重放。

### 第一阶段已实施（历史）

- 保持采集完成一个目标即可入队，不等整个 Run 结束。
- 默认 NATS 发布改为单目标有界 chunk 轮转，每次最多 64 行，消息协议仍是一行一消息。
- 4 个 Writer 调度发布单元；ACK 等待不占住 Writer。每个 Payload 最多一个活动发布单元，最多 120 个；全局消息 256 条、字节 32MiB、单调用 64 条、编码线程 2 个的约束不变。
- 最后一块确认即产生目标终态，不再为探测迭代结束多等一轮；关闭该目标游标、清理引用后释放 Payload。
- 编码线程尚未退出时，取消协程不能提前释放 Payload。异常保留身份、异常链与堆栈位置，但清理已退出帧中的大对象引用。
- 发布器托管重试时，Run 不再重试已经释放的结果；部分投递后截止仍为未知，不伪装成明确失败或成功。
- 首次投递标记只记录一次，并移到取得信贷之后。总截止仍包含排队、编码、信贷等待、发送与 ACK，未延长 120 秒。
- 增加 `publish_delivery_duration_seconds`，终态时刻与观察回执时刻分离；容量日志改为“首次投递前P99”和“未确认”。
- 保留兼容字段 `timeout_stage`，增加 `timeout_phase`：例如 `deadline / puback` 表示总截止到达时正在等 ACK。
  历史 `rejected_total` 与 `event=nats_metrics_publish_rejected` 名称保留兼容，含义是未确认，不能一概解释为 broker 拒绝。

### 第一阶段比较方法与数据

基线为提交 `2164b6be04e7a55ec9532297ad13de34576312ea` 的 Stargazer 代码，通过 `git archive` 提取到临时目录；
未切换当前工作区、未回滚用户文件。两个版本调用同一个新基准工具。

合成数据：8 个大结果各 2048 行，3830 个小结果各 1 行，共 20214 条消息；7 个逻辑运行轮流分配目标。
每次先取得 Payload 额度再生成结果，使用真实 Coordinator → BufferedPublisher → NatsPublisher → 编码 → JetStream 信贷窗口链路。
只在 SDK 边界模拟 ACK，采集等待为 1ms；不模拟 SNMP、broker 磁盘、网络带宽、消费者或生产 CPU 配额。
1.384 秒取自日志中成功 PubAck P99 的量级，**固定所有 ACK 为该值只是敏感性实验，不是生产延迟分布**。

| 指标 | 旧链路，ACK 15ms | 新链路，ACK 15ms | 旧链路，ACK 1384ms | 新链路，ACK 1384ms |
|---|---:|---:|---:|---:|
| 整轮耗时（秒） | 6.8586 | 3.3540 | 353.8696 | 111.2869 |
| 确认目标 | 3838 | 3838 | 3830 | 3838 |
| 明确失败目标 | 0 | 0 | 0 | 0 |
| 未知目标 | 0 | 0 | 8 | 0 |
| 已确认消息 | 20214 | 20214 | 8822 | 20214 |
| 小结果发布 P99（秒） | 1.3948 | 0.4453 | 65.9787 | 4.3322 |
| 大结果发布 P99（秒） | 5.2677 | 3.1877 | 120.0037 | 108.5539 |
| Payload 峰值 | 120 | 120 | 120 | 120 |
| 在途消息峰值 | 75 | 256 | 76 | 256 |
| RSS 峰值（MiB） | 63.89 | 67.25 | 63.19 | 67.17 |
| CPU 时间（秒） | 2.3539 | 2.8615 | 5.0499 | 3.9304 |
| 事件循环 P99（秒） | 0.0060 | 0.1005 | 0.0078 | 0.0086 |
| 抽样异步任务峰值 | 198 | 600 | 201 | 543 |
| 结束时 Payload / 消息 / 字节 / SDK future | 全部 0 | 全部 0 | 全部 0 | 全部 0 |

慢 ACK 场景耗时下降约 68.6%，小结果 P99 下降约 93.4%。新链路利用了原本未充分利用的全局信贷窗口。
代价也需保留：快 ACK 场景 CPU 时间及事件循环 P99 上升，活动发布协程更多；因此**不能宣称 CPU/事件循环问题已完全解决**。
这些是本机单次样本，非容量保证。生产仍应观察 CPU 限流、编码耗时、首投等待和失败阶段。
旧的“等待 P99”被每行覆盖，本报告不把它与修复后的首投等待直接计算改善比例。

慢 ACK 基线还出现了后台回执 `Future exception was never retrieved`；新链路显式消费已结束 Run 的后台终态异常，
同时保留再次 await 回执时的原异常。

### 第一阶段回归与边界测试

新增 `agents/stargazer/tests/test_publish_fairness.py`，覆盖：

- 小结果在大结果结束前取得发送机会（旧实现先发送 1024 行，新实现不超过一个 64 行窗口）。
- 慢结果未结束时，已完成结果的实际对象可被回收，额度同步释放。
- 首次投递计时不被后续消息覆盖；总截止日志不误报为 60 秒入队超时；Prometheus 分开暴露各阶段耗时。
- 托管重试的投递前异常，不会触发 `retryable publish receipt lost its payload`。
- 过期信贷等待不提前标记投递；`deadline` 保留 `puback` 阶段；部分确认后截止归为未知。
- 7 个真实 Run 共享 CollectionScheduler / Executor / RunResultSink，峰值达到 120，3838 个目标全部完成采集与发布。
- 3838 目标混合发布，以及 120 并发下的短截止/注入 ACK 失败；无额度、消息信贷及 SDK future 泄漏。
- shutdown 必须等编码线程释放引用；失败 traceback 不保留 Payload。

TDD 已执行红/绿反馈：首次公平性回归为 `1024 <= 64` 失败；首投时间被覆盖和丢失 Payload 的重试异常均先复现；
新增截止阶段、信贷前误标记及取消后线程仍持有数据的问题也先红后修复。

最终验证：

- 综合回归 **185 passed**（77.86 秒），覆盖 publisher、delivery、JetStream、编码、容量、执行器、Run 汇总与原有负载测试。
- 随后补充信贷回收的两个边界用例，专项文件完整复跑 **16 passed**（9.61 秒）；去重后共 **187 项**相关测试通过。
- Coverage.py 7.11.0 以 branch 模式采集，将 `git diff --unified=0` 新增行与覆盖数据的可执行语句相交：生产改动行 **185/203 = 91.13%**，超过 75% 门槛。未把整文件旧逻辑覆盖率冒充改动行覆盖率。
- 分文件改动可执行行覆盖：delivery 9/9、publisher 122/135、JetStream window 18/18、nats_helper 36/41。
  日志模板和 health allowlist 的常量修改不单独计可执行行，已由日志格式/参数/敏感哨兵和 Prometheus 行为断言覆盖。
- 本地 Stargazer venv 未安装 pytest-cov；测试使用现有 Python 环境，在末尾追加 Server venv 的包搜索路径借用现有 coverage，未修改依赖文件或安装生产依赖。

综合回归命令（在 `agents/stargazer` 目录执行）：

```bash
.venv/bin/python -m pytest tests/test_publish_fairness.py tests/test_result_publisher.py tests/test_nats_metrics_batch.py tests/test_jetstream_publish_window.py tests/test_nats_metrics_stream_contract.py tests/test_target_collection_executor.py tests/test_capacity_usage_reporter.py tests/test_collection_load.py tests/test_run_result_sink.py tests/test_collection_metrics.py -q
```

格式检查：本次 13 个 Python 文件 Black 检查通过；关键改动文件 isort 检查通过；`git diff --check` 通过。
仓库要求的 `cd agents/stargazer && make lint` 已执行但失败：当前仓库缺少 `.pre-commit-config.yaml`，
且默认 pre-commit 缓存日志位置不可写。这是现有门禁配置/环境问题，本次没有擅自补配置或格式化无关文件。

### 第一阶段复跑

在 `agents/stargazer` 目录：

```bash
.venv/bin/python scripts/benchmark_publish_fairness.py
.venv/bin/python scripts/benchmark_publish_fairness.py --ack-ms 1384
.venv/bin/python -m pytest tests/test_publish_fairness.py -q
```

参数默认值即 120 并发、7 个运行、3838 个目标、120 秒总截止。基线对比使用同一个脚本，
设置 `STARGAZER_BENCHMARK_ROOT` 指向旧版本的 `agents/stargazer` 目录，使用当前 venv 保持依赖一致。

### 上线后仍需核实

1. 实际运行镜像与环境覆盖值：每个 Worker 的目标槽位及 Payload 应为 120；错峰改动由用户已有工作负责。
2. 按同一个 task/run 对比采集成功、发布确认、失败/未知和 CMDB 消费/入库数量；PubAck 不等于 CMDB 入库成功。
3. 对 192.168.198.* 补齐同轮 `snmp_connectivity_check.py` 输出、逐目标采集终态及消费端日志，定位 128 与 61 的差集。
4. 若仍超时，用新增 `timeout_phase` 区分编码/首次投递前、信贷、调用及 ACK 等待，结合 broker 监控确认是否需要进程隔离或 broker 扩容。

未连接或修改生产环境，未提交或推送代码，未修改现有 Server 错峰、采集 fixture 或 Web 图标工作。
