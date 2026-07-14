# CMDB Stargazer 边界生产级审查

## 1. Summary

CMDB 下发到 Stargazer 的主链路已经形成：`CollectModelService` 生成 Node 参数和 HTTP header，Stargazer `collect_info` 解析 `cmdb*` 参数并按 host/凭据拆任务，ARQ Worker 进入 `collect_plugin_task`，`CollectionService` 解析 `plugin.yml` 后由 `PluginExecutor` 执行 job/protocol 插件，结果再被归一化为 Prometheus metrics 或配置文件 callback，经 core NATS `publish + flush` 发往 CMDB。当前代码还保留了两个正确行为：配置文件多 host 拆分时，task 的 `host` 会覆盖旧 `instance_name`，callback identity 按拆分后的 host 构造；`execution_id` 也会随候选任务保留。历史 `#0025` 的实例错配线索在本基线已不成立，不形成 Finding。

生产边界仍不合格。CMDB 与 Stargazer 各维护一份网络命令 denylist，Agent 侧缺少 `write/request/do/shell/ssh` 等已在后端禁止的远程高危前缀；更直接的是空命令没有被 Agent 拒绝，插件仍连接设备并成功回调空配置。配置文件与 IP 扫描又共用“任务参数直接进入插件、Agent 无统一资源预算”的架构根因：前者整文件读取并 base64 放大，后者初始化时全量展开 CIDR，随后一次性为每个目标创建 gather 协程；单独的 semaphore 只限制在途 probe，不限制目标列表和协程数量。

错误与投递闭环也有确定缺口。PowerShell 脚本复用了 POSIX 单引号转义；IP 插件配置和测试仍引用不存在的 `plugins.inputs.ip_discovery`；NATS 指标发布遇到未知异常时，即使 `success_count=0` 也强制标记 `delivery_detected=True`，上层会跳过失败指标和凭据失败处理；凭据结果批推只用 `finished_at` 作为 exclusive cursor，超过批次上限的同时间戳事件会被永久跳过。core NATS `flush` 后即推进 cursor、没有 CMDB 应用确认的通用状态机问题与 `CMDB-F04` 同根因，本报告不重复建立第二个主 Finding，只把它作为 `CMDB-F32` 的放大条件。

本域确认 7 个主 Finding：P0 3 个、P1 4 个、P2/P3 0 个，编号 `CMDB-F26`–`CMDB-F32`。`CollectionService` 完整记录 raw result、callback/凭据缓存传播任意外部错误文本，与 `CMDB-F25` 的敏感错误面完全同根因，仅登记交叉证据。Recommendation 为 **Block**。

## 2. Findings

### Finding CMDB-F26：Agent 远程命令策略落后于 CMDB，已拒绝的高危前缀可在执行边界被放行

- Severity: P0
- Location: `server/apps/cmdb/services/network_config_file_policy.py:32-71,103-120`；`agents/stargazer/plugins/inputs/network_config_file/constants.py:1-21`；`agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py:19-29,85-125`
- Root cause category: 重复逻辑导致的不一致
- Evidence: CMDB denylist 已禁止 `write/request/do/sudo/bash/sh/python/perl/ruby/rm/telnet/ssh`，Stargazer 的独立常量没有这些前缀；Agent 只按第一词检查自己的集合，然后把命令逐条交给 `net_connect.send_command`。直接复现 `validate_safe_command("request system reboot")` 返回原命令。即使正常 Serializer 会先走后端校验，重放的旧 Node 配置、直接请求 Agent、版本错配或其他下发方都能到达最终执行边界；高危下发红线不能依赖单一上游版本。
- Trigger: 向 Stargazer 下发 `request system reboot`、`write memory`、`do ...`、`ssh ...` 等 CMDB 已禁止但 Agent 未禁止的命令，并使用受支持设备类型与有效凭据。
- Impact: Agent 可在生产网络设备执行重启、写配置、模式/命令逃逸或横向连接，造成设备中断、配置损坏或扩大远程执行范围。
- Why existing tests missed it: Agent 测试只参数化 `reload/configure terminal/write erase/delete`，没有以 CMDB 策略集合做一致性测试，也没有覆盖 `request/do/shell/ssh`；后端测试只证明自己的 denylist，不证明最终执行端同步。
- Minimal safe fix: 把只读命令策略变成一个版本化、可校验的共享策略工件；短期先让 Agent 完整同步 CMDB 前缀，并在执行前 fail-closed 校验策略版本。禁止仅依赖 HTTP/Serializer 前置校验。
- Required tests: CMDB 与 Agent 危险集合逐项一致；上述全部高危前缀在 Agent 零连接、零 `send_command`；大小写/空白变体、旧策略版本、直接 Agent 请求和合法 show/display 命令回归。
- Long-term design note: 远程执行授权必须由最终执行边界强制，控制面只负责提前反馈；策略应有单一权威来源、版本和审计摘要，不能复制常量。

### Finding CMDB-F27：空命令列表仍被标记为成功并回调空配置

- Severity: P0
- Location: `server/apps/cmdb/services/network_config_file_policy.py:116-120`；`agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py:48-49,85-125`
- Root cause category: 跨层契约不一致
- Evidence: CMDB `validate_commands` 明确拒绝空列表；Agent `_commands` 对空值返回 `[]`，`list_all_resources` 仍建立 Netmiko 连接、跳过循环、`failures=[]`，最终将 `merge_command_outputs([])==""` 编码为 success callback。直接复现 `_commands()` 返回 `[]`，代码没有后续非空断言。
- Trigger: 旧任务/直连 Agent/版本错配提供空白 `commands`，且设备连接成功。
- Impact: CMDB 收到成功状态和空正文，可能创建空配置版本、掩盖任务参数错误，并把“未执行任何采集命令”展示为采集成功。
- Why existing tests missed it: Agent 10 个网络配置测试全部使用非空命令，只覆盖单命令失败；没有断言空命令零连接、失败 callback 和零版本写入。
- Minimal safe fix: Agent `_commands` 在规范化后为空时立即抛稳定参数错误，必须发生在 `_connect_params`/`ConnectHandler` 前；callback 使用结构化 `invalid_commands` 错误码而非成功空正文。
- Required tests: `None`、空串、纯换行均失败且 Netmiko 零调用；CMDB E2E 不新增版本、任务失败可见；至少一个合法命令保持成功。
- Long-term design note: 参数契约应由共享 schema 在控制面和执行面双重验证，Agent 不能把“无工作”隐式解释为成功。

### Finding CMDB-F28：插件执行边界缺少统一资源预算，配置文件与 CIDR 两条路径均可耗尽 Agent

- Severity: P0
- Location: `agents/stargazer/plugins/inputs/config_file/config_file_discover.sh:14-27`；`agents/stargazer/plugins/inputs/config_file/config_file_discover.ps1:15-25`；`agents/stargazer/plugins/inputs/config_file/config_file_info.py:86-120`；`agents/stargazer/plugins/inputs/ip/ip_discovery_scanner.py:43-75,134-138`
- Root cause category: 资源边界缺失
- Evidence: Linux 在得到 `FILE_SIZE` 后没有上限，仍通过命令替换整文件 base64；PowerShell `ReadAllBytes` 整文件进入内存，再生成第二份 base64 字符串；Python callback 又完整解码计算 hash。IP scanner 在构造器中遍历每个 `network.hosts()` 并保存 target dict，`list_all_resources` 再一次性构造全部 `_probe_one` coroutine 并 `gather`；`Semaphore(50)` 只约束 probe 临界区。二者不是偶然的两个局部漏判，而是同一执行架构把未预算的外部数据直接物化、编码和投递；当前没有 Agent 级最大输入、输出、任务内存或 deadline 策略。
- Trigger: 采集超大配置文件；提供 `/8`、IPv6 大网段或大量显式 targets；并发运行多个此类任务。
- Impact: 单任务即可放大为多份文件内存或数百万 target/coroutine，耗尽 Agent 内存/事件循环，并继续放大 NATS、Redis/ARQ 与 CMDB callback 负载，影响同节点其他采集任务。
- Why existing tests missed it: 没有 config_file 文件大小测试；IP 测试仍引用不存在的旧模块且仅检查 `/24`、`/30` 纯逻辑，没有超限、IPv6、并发任务、协程数量或输出大小断言。
- Minimal safe fix: 在插件进入物化前应用统一预算：配置文件先按 `FILE_SIZE` 拒绝并限制 base64/回调大小；IP 先按网络地址数和累计目标数拒绝，使用有界 producer/worker 队列流式探测并限制结果数、总时长和输出字节。上限需由产品/可靠性配置给出安全默认值。
- Required tests: 上限边界±1、超大/稀疏文件、base64 放大、`/8`/IPv6/多 CIDR/大量显式目标、任务并发、deadline、取消和输出上限；超限必须在分配/连接/探测前失败且不致 Agent 崩溃。
- Long-term design note: 文件与 CIDR 的业务形态不同，但直接根因相同：插件框架没有统一 ResourceBudget。长期应在 `PluginExecutor` 提供输入计数、内存/输出、并发与 deadline 契约，插件仅声明自己的单位成本。

### Finding CMDB-F29：配置文件路径对 PowerShell 复用 POSIX 转义，含单引号路径会破坏脚本边界

- Severity: P1
- Location: `agents/stargazer/plugins/inputs/config_file/config_file_info.py:20-53,153-155`；`agents/stargazer/plugins/inputs/config_file/config_file_discover.ps1:1`；`agents/stargazer/plugins/script_executor.py:68-88`
- Root cause category: 跨层契约不一致
- Evidence: `_escape_script_value` 无条件把 `'` 替换为 POSIX 的 `'"'"'`，但 Windows 模板是 PowerShell 单引号字符串 `$FilePath='{{config_file_path}}'`。直接复现 Windows 路径输出 `C:\\ops\\o'"'"'Brien.conf`；渲染后该文本不是 PowerShell 的 `''` 转义，脚本扩展名虽然已能识别 powershell，却没有传给渲染器选择语法。
- Trigger: Windows 配置文件路径包含单引号，或恶意路径在单引号后拼接 PowerShell 语句。
- Impact: 合法路径采集稳定失败；在路径来源边界失守时可打断字符串并扩大到远程脚本注入，callback 只返回外部异常文本。
- Why existing tests missed it: 当前没有 ConfigFileInfo 渲染/Windows 脚本测试；现有零散测试只检查文件名提取，未覆盖 shell 类型与引号矩阵。
- Minimal safe fix: 依据 `script_path`/shell type 使用独立编码器；PowerShell 单引号字符串把 `'` 编码为 `''`，POSIX 保留 `shlex.quote` 等价策略；更安全的是把路径作为执行参数/编码数据传递，不做模板源码拼接。
- Required tests: POSIX 与 PowerShell 的空格、单引号、双引号、反斜杠、换行和注入载荷；在真实 shell/pwsh 解析下只访问目标字面路径且无额外命令。
- Long-term design note: 数据值不应通过字符串替换进入可执行源码；Executor 应提供类型化参数通道，shell-specific serialization 归框架层。

### Finding CMDB-F30：IP 插件声明与测试仍指向不存在的模块，配置驱动入口无法加载

- Severity: P1
- Location: `agents/stargazer/plugins/inputs/ip/plugin.yml:13-19`；`agents/stargazer/plugins/inputs/ip/ip_discovery_scanner.py`；`agents/stargazer/tests/test_ip_discovery_targets.py:4`；`agents/stargazer/tests/test_ip_discovery_scanner.py:6,93-100`
- Root cause category: 跨层契约不一致
- Evidence: 实际包为 `plugins.inputs.ip`，但 `plugin.yml` 的 collector module、两个 IP 测试 import 和其中的 yml 路径都写成 `plugins.inputs.ip_discovery`。brief 组合 pytest 在收集阶段直接 `ModuleNotFoundError`；`CollectionService`/`PluginExecutor` 同样按 yml 动态 import，因此真实任务不会进入 scanner。
- Trigger: 以 model `ip`/IP discovery 走 protocol executor，或运行 brief 指定 IP 聚焦测试。
- Impact: IP 发现任务在 Agent 侧加载失败，CMDB 无法得到任何发现结果；资源边界修复也没有可执行回归保护。
- Why existing tests missed it: 测试自身复制了旧目录名，导致不是红灯证明业务行为，而是在收集阶段完全无法运行；没有遍历所有 plugin.yml 并真实 import collector 的契约门禁。
- Minimal safe fix: 同步 yml 和测试到真实 `plugins.inputs.ip...` 路径，并增加扫描全部 OSS plugin.yml 的 import smoke gate。
- Required tests: yml 路径存在、module/class 可 import/实例化；brief 两个 IP 文件可收集；从 `CollectionService` 走真实配置解析到 scanner 的最小 E2E。
- Long-term design note: module path 不应在实现、yml 和测试三处手工复制；插件注册时应生成/校验 registry，启动阶段 fail-fast。

### Finding CMDB-F31：NATS 未知投递状态被伪装成已投递，失败指标与凭据闭环被跳过

- Severity: P1
- Location: `agents/stargazer/core/nats_utils.py:203-234`；`agents/stargazer/tasks/utils/nats_helper.py:61-198`；`agents/stargazer/tasks/handlers/plugin_handler.py:91-97,105-175`
- Root cause category: 错误模型不清晰
- Evidence: `nats_publish_lines` 的专用异常能给出 `delivery_detected=count>0`；但 helper 捕获任意其他异常且异常没有 delivery 标志时，文本承认 `publish state unknown`，构造 `MetricsPublishError` 却硬编码 `delivery_detected=True`。直接用首次 publish 抛 `RuntimeError` 复现得到 `success_count=0, delivery_detected=True`。handler 据此令 `real_metrics_delivered=True`；若采集本身成功，就跳过 `_handle_multicred_post_execute`，也因 `not real_metrics_delivered` 为假而不发 error metrics。
- Trigger: NATS publish/flush/连接层抛出非 `NatsLinesPublishError` 的异常，且没有明确 delivery 元数据；采集结果本身为成功。
- Impact: 实际零投递也可被当成已投递，调用方看不到成功指标或失败指标，凭据 success/failure event 不落缓存、不推 CMDB，任务返回 failed 但业务结果闭环缺失。
- Why existing tests missed it: 现有 host 测试构造已经带 `delivery_detected=True/False` 的 `MetricsPublishError`，没有从 generic exception 穿过 `_publish_lines_with_retry` 再验证 handler 的外部行为；brief 的 multicred 测试也不覆盖 NATS 未知态。
- Minimal safe fix: delivery 使用三态 `confirmed/none/unknown`，禁止用布尔 true 代表 unknown；只有确认至少一条被服务端接受时才跳过全批重投，并且 unknown 必须保留可恢复 delivery 记录、执行凭据结果收敛和明确告警。
- Required tests: generic exception 在首条前失败、部分 publish 后 flush 失败、明确零投递、明确部分投递；分别断言 metrics/outbox、凭据 event、任务终态和重复风险，不能只断言异常属性。
- Long-term design note: 指标逐行 core NATS 发布无法同时提供批次原子性和 exactly-once；应使用带 batch/event ID 的 durable stream 与消费者幂等，而非从异常文本猜测投递事实。

### Finding CMDB-F32：凭据结果以非唯一时间戳推进 exclusive cursor，同刻超批事件会永久丢失

- Severity: P1
- Location: `agents/stargazer/core/credential_state_cache.py:92-118,153-189`；`agents/stargazer/service/collect_credential_result_push_service.py:39-59`；`agents/stargazer/core/nats_utils.py:176-200`
- Root cause category: 并发或幂等设计问题
- Evidence: 每个 event 有唯一 `event_id`，但 Redis score 和 push cursor 只使用毫秒级 `finished_at`。查询下一批采用排他的 `min=f"({score}"`；若同一毫秒事件数超过 batch limit，第一批把 cursor 推进到该时间，剩余同 score 事件永远不会再返回。`push_once` 还在 core NATS `publish+flush` 后立即更新 cursor，没有 CMDB handler 业务 ack；该通用 fire-and-forget 状态问题与 `CMDB-F04` 同根因，本报告不重复计数，但会进一步扩大 cursor 丢失窗口。
- Trigger: 多 Worker 同毫秒写入超过 `COLLECT_CREDENTIAL_RESULT_PUSH_BATCH_LIMIT` 的结果；或 core NATS 已 flush 但 CMDB handler 未处理/失败。
- Impact: 某些凭据成功/失败永远不回写 CMDB，命中状态、冷却和调度选择漂移；失败设备可能持续使用错误凭据，或健康凭据无法被优先复用，平台没有待重放记录。
- Why existing tests missed it: `test_collect_credential_push` 只提供两个不同 finished_at 事件并 mock `nats_publish` 成功，然后断言 cursor 更新；没有同 score 分页、进程重启、CMDB handler 失败、重复投递或 event_id 幂等。
- Minimal safe fix: cursor 使用稳定复合位置 `(score,event_id)` 或 Redis Stream ID，并仅在 CMDB 应用级 ack 后 checkpoint；同批事件用 event_id 去重，未确认保持 pending 并可重试。若暂不解决通用 ack，至少先关闭同 score 跳过并暴露 pending/retention 告警。
- Required tests: `limit+1` 个同 finished_at 跨两批全量送达；重复 ack 幂等；publish 成功但 handler 失败不推进；重启恢复、7 天 retention 临界、乱序 finished_at、多 Worker 并发 append。
- Long-term design note: 凭据执行结果是控制面状态事件，不应只存 7 天 Redis 排序集并以时间游标 best-effort 推送；应使用 durable event/outbox、唯一事件键和消费者 checkpoint。通用 NATS 投递状态机复用 `CMDB-F04` 的修复方向。

### 跨域证据与未计数风险

- `CMDB-F25`：`CollectionService.collect` 在 info 级别记录完整 `result`；配置正文、网络命令输出、插件/SDK 错误随后又进入 traceback、callback、credential event 和 Redis failure state。它与 Task 5 的“凭据、节点参数与外部错误缺少统一脱敏边界”是同一根因，不新增 Finding。修复必须同时覆盖 Agent 日志、error metrics、callback 和缓存，不能只删除一条日志。
- `CMDB-F04`：callback 和 credential push 都使用 core NATS `publish+flush`，这只确认客户端缓冲写出，不确认 CMDB handler 处理；持久化 outbox、应用 ack 与恢复扫描属于既有异步状态机主 Finding。本报告只对 `CMDB-F31` 的错误分类和 `CMDB-F32` 的非唯一 cursor 建立独立主项。
- `plugin_handler.py:142-164` 的通用非 config callback 异常分支构造 identity 时没有 `instance_name`，随后却必取该键。当前仓库所有 plugin callback 下发均为 `receive_config_file_result`，会进入完整 identity 分支，因此缺少已注册生产调用方，不满足主 Finding 准入门槛；新增第二种 callback 前必须先补契约测试。
- `network_topo` 当前 plugin module/class 与源码一致，SNMP 凭据未直接写入所审行的日志；其 traceback/错误正文仍受 `CMDB-F25` 统一约束。本任务未连接真实 SNMP 设备验证 fallback、响应规模或超时。

## 3. Test Review

- brief 原始命令：`uv run pytest -q tests/test_collect_multicred.py tests/test_collect_credential_push.py tests/test_ip_discovery_targets.py tests/collect_fixtures/`。结果在收集期退出 2：`test_ip_discovery_targets.py` 导入不存在的 `plugins.inputs.ip_discovery`，未执行任何测试。
- 拆分后 `test_collect_multicred.py + test_collect_credential_push.py` 为 49 passed；它们证明 host/credential 候选、部分 cooldown 和成功 publish 后 cursor 更新，但大量使用 fake cache/publish，不能证明真实 Redis/NATS、未知投递、应用 ack、同 score 分页或日志脱敏。
- `tests/collect_fixtures/` 为 203 passed、6 failed：测试要求 mssql 和 57 个 MODEL_SPECS，实际 catalog 无 mssql 且为 56；真实 Docker/VM/SSH fixture 依赖也未在本机启动。该失败与 7 个主 Findings 不同根因，但说明 brief 基线并非全绿。
- 额外 `test_network_config_file_info.py` 为 10 passed，却没有命令策略集合一致性和空命令用例；`test_ip_discovery_scanner.py` 同样因旧模块路径收集失败。
- `make lint` 退出 2：Makefile 执行 `pre-commit run --all-files`，但 `agents/stargazer/.pre-commit-config.yaml` 不存在；同时无法写用户缓存日志。不能声明 lint 通过。
- 覆盖率未获得：当前 Stargazer 环境未安装 pytest-cov，`--cov` 命令退出 4，不能声称达到相关模块 80%/核心路径 90%。
- 未执行真实 Redis/ARQ、NATS broker/消费者失败、Netmiko 设备、SSH/PowerShell、SNMP、ICMP privileged、Docker/VM fixture、大文件/大 CIDR 和多 Worker 并发；P0/P1 所列 Required tests 均是修复阻断回归。

## 4. Maintainability Verdict

1. 六个月后能否快速理解：局部文件可读，但 callback identity、错误分类、凭据状态和 delivery 判断跨 API/handler/helper/cache 四层，缺少统一状态图，不能快速核对。
2. 新增同类插件是否需复制：会。资源限制、错误 payload、脚本渲染和 callback identity 由各插件自行实现。
3. 新增错误类型是否需改多处：会。插件异常、Prometheus 文本解析、关键词 failure kind、callback 和 CMDB hit state 都需同步。
4. 新增 callback 是否容易：不容易。当前通用非 config 异常分支已经存在未覆盖的 `instance_name` KeyError，且没有 schema/ack 协议。
5. 接口是否易误用：是。Agent 可直收旧/绕过后端的命令与空参数，`delivery_detected` 又混合确认、部分和未知语义。
6. 日志是否安全且可排障：否。raw result/任意错误会泄露正文；同时缺少 delivery/event ID/pending 阶段信息。
7. 状态异常能否定位阶段：不能。无法区分 broker flush、CMDB handler、credential checkpoint 和 callback 落库阶段。
8. 是否降低复杂度：host 拆分和执行器注册有价值，但复制安全策略、插件自管预算和布尔投递推断把复杂度转移到边界故障。

## 5. Recommendation

**Block**。

远程执行 P0 必须先关闭：`CMDB-F26` 将安全策略收敛到最终执行边界，`CMDB-F27` 空命令 fail-closed，`CMDB-F28` 为文件与 IP 扫描建立统一硬预算。随后修复 shell-specific 参数传递、IP 注册路径、投递三态和凭据复合 checkpoint，并补齐每个 P0/P1 的真实回归。`CMDB-F25` 与 `CMDB-F04` 也必须在跨层统一方案中一起关闭；只同步一份常量、增加 semaphore、截断日志或保留 core NATS flush，均不足以上线。
