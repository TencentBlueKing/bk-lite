# SNMP 采集 SnmpEngine 每目标泄漏修复报告（2026-09-02）

## 结论

- 8-31 生产事故（250 并发、事件循环延迟 14 s、RSS 4.8 GiB 不回落）的根因是 `snmp_facts.py`
  与 `snmp_topo.py` **每个目标新建 pysnmp `SnmpEngine`**（collect / probe / bulk / next / get 共 5 处）。
- 修复：新增 `core/infra/snmp_engine_pool.py`，同一事件循环内按凭据作用域共享 engine
  （v1/v2c 共用一个，v3 按用户名+协议+密钥摘要各一个），进程内只构建一次 pysmi/PLY MIB 编译器，
  engine 按不同目标数代际轮换（`SNMP_ENGINE_MAX_TARGETS`，默认 2000）、空闲释放
  （`SNMP_ENGINE_IDLE_SECONDS`，默认 300）、Sanic `after_server_stop` 统一关闭。
- builder A/B 实测（1 worker，`SNMP_MAX_IN_FLIGHT=100`，2×400 个 10.255.0.0/16 不可达目标）：

| 指标 | 修复前（master `fd8d598ae`） | 修复后（本分支） |
|---|---|---|
| RSS 基线 | 73 MiB | 73 MiB |
| 400 目标后 RSS | 930 MiB | 105 MiB |
| 800 目标后 RSS | 1747 MiB | 115 MiB |
| 空闲 60 s 后 RSS | 1784 MiB | 115 MiB |
| `malloc_trim(0)` 后 RSS | 1742 MiB | 113 MiB |
| 存活 `ply.yacc.LRParser` / `LRItem` | 800 / 807 200 | 1 / 1 009 |
| gc 跟踪对象数 | 4 930 546 | 173 145 |
| 忙碌期 CPU%（max / p90 / 中位） | 99.7 / 99.7 / 0.9 | 18.0 / 9.5 / 0.1 |
| 忙碌期事件循环 P99 延迟 ms（max / p90 / 中位） | 7304 / 1260 / 492 | 25.2 / 2.5 / 1.5 |
| 400 目标批次墙钟 | ≈110 s | ≈85 s |

修复后 800 目标 RSS 增长 42 MiB（验收阈值 <200 MiB），`ply/yacc.py` 存活对象只有一份
（1 009 个 LRItem，而非修复前的 80 万），空闲与 trim 后不再有可回收的碎片（115→113 MiB）。

## 根因链（pysnmp 5.1.0 / pysmi 1.2.1 / ply 3.11 / uvloop 0.21）

1. 每个 `SnmpEngine()` 自带独立 `MibBuilder` 并加载一整套 MIB 模块（`SNMPv2-SMI`、`SNMPv2-TM`、
   `SNMP-TARGET-MIB`……）；`ObjectIdentity.resolveWithMib` 调 `addMibCompiler(ifNotAdded=True)`，
   短路条件 `mibBuilder.getMibCompiler()` 是 per-engine 的，所以每个 engine 都会新建 `MibCompiler`，
   pysmi 解析器构造时 `yacc.yacc(write_tables=False)` 现场重算 LR 表。`lookupMib=False` 只管响应侧，挡不住。
   预热后单个 engine 的成本：`SnmpEngine()` ≈20 ms + 编译器/LR 表 ≈25 ms，合计 ≈50 ms 纯 Python CPU、
   ≈2.1 MiB 常驻；100 并发一批同时到期就是 5 s 以上的事件循环阻塞（实测 P99 7.3 s）。
2. **为什么关闭后不回落**：`gc.get_referrers` 从 `LRParser` 向上追到的引用链是
   `LRParser ← SmiParser.parser ← MibCompiler ← MibBuilder ← MIB 模块命名空间 ← SnmpUDPAddress 类
   ← SnmpUDPAddress 实例 ← UdpTransportAddress._localAddress ← uvloop.loop.LruCache`。
   uvloop 在 `dns.pyx` 里用模块级 `sockaddrs = LruCache(maxsize=2048)` 缓存 sendto 的 Python 地址→sockaddr，
   键就是 pysnmp 传给 `transport.sendto()` 的 `UdpTransportAddress`（tuple 子类，带 `_localAddress`），
   而该属性是本 engine 生成的 MIB 类实例，于是每个不同目标地址都把一个**已经 closeDispatcher 的 engine**
   整棵 MIB 树拖住，直到 2048 项 LRU 把它挤出去。2048 × 2.1 MiB ≈ 4.3 GiB，与生产 4.8 GiB 不回落吻合；
   `gc.collect()` 返回 0 也因此正常——它们都是可达的。
3. 共享 engine 后，缓存键指向的是长期存活的共享 engine；代际轮换关闭的旧 engine 仍可能被最多
   2048 条地址键短暂拖住（每代 ≤ `SNMP_ENGINE_MAX_TARGETS` 条 LCD 行 ≈ 21 KiB/目标），
   属于有界残留（实测第二代出现后 RSS 仅 +10 MiB）。

## 代码变更

- `core/infra/snmp_engine_pool.py`（新增）：`shared_snmp_engine(auth, target=(host, port))` 异步上下文借用
  engine；`snmp_engine_scope()` 派生作用域键（密钥材料只做 blake2b 摘要、只留在内存，日志用 `community` /
  `v3#N` 标签）；代际轮换、空闲关闭、`close_shared_snmp_engines()`、`register_snmp_engine_lifecycle(app)`；
  `create_snmp_engine()` 装配进程内唯一的 MIB 编译器。生命周期日志
  `event=snmp_engine_opened|closed|close_failed|dropped`，模板 + 惰性参数，无 traceback、无凭据。
- `plugins/inputs/network/snmp_facts.py`、`plugins/inputs/network_topo/snmp_topo.py`：5 处 `SnmpEngine()`
  改为借用共享 engine，删除 `_close_snmp_engine`；超时/重试语义（`timeout=10, retries=1`、probe 固定 10 s×1）不变。
- `server.py`：注册 engine 池生命周期（启动时校验阈值配置，非法则启动失败；停止时关闭）。
- `scripts/snmp_connectivity_check.py`、`scripts/benchmark_snmp_scheduler.py`：改走池（benchmark 的
  `peak_live_snmp_engines` 语义变为池内 engine 数）。
- 文档：`README.md` 并发与超时段、`docs/configuration-plugin-async-matrix.md`。

## 测试

- 新增 `tests/test_snmp_engine_pool.py`（18 例）：同作用域复用、v3 密钥隔离、空闲关闭与重开、代际轮换
  排空、循环结束丢弃、异常/取消归还、全量关闭、日志模板/惰性参数/敏感哨兵/单一告警无 traceback、
  环境变量校验、Sanic 生命周期，以及真实 pysnmp：进程内 `yacc.yacc` 只调用一次且两代 engine 共用
  同一编译器、单 engine 并发 8 目标独立超时。
- 更新 `tests/test_snmp_plugins_native_async.py`、`tests/test_snmp_facts_probe.py`：断言同一进程内多次
  collect/probe（串行、并发、不同目标）共用同一 engine 实例且不按目标关闭；拓扑插件三条路径共用 engine；
  源码级断言插件不再出现 `SnmpEngine()` / `closeDispatcher`；真实 pysnmp 32 目标并发取消后关闭共享 engine
  无事件循环回调错误。
- 命令：`cd agents/stargazer && uv run pytest tests/test_snmp_engine_pool.py tests/test_snmp_facts_probe.py
  tests/test_snmp_plugins_native_async.py`（33 passed）。全量 `tests/`：修复后 939 passed / 86 failed / 37 errors，
  失败与错误集合是 master 基线（916 passed / 88 failed / 37 errors）的子集，均为缺少可选云 SDK
  （`oss2` 等）与主机采集环境相关的既有失败，无回归。

## 复现与测量方法

见 claude_space memory `stargazer-builder-concurrency-testbed`（builder `/data/snmp-engine-fix/`：
`setup_testbed.sh` 起 before/after 两容器，`/__memdump`、`/__trim`、`/__referrers` 诊断路由，
`run_load.sh` + `finish_load.sh` 驱动，`summarize_logs.py` 解析 `collection_capacity` 日志得到 CPU/延迟/RSS 时间线）。

## 后续

- `SANIC_WORKERS` 默认值（PR #5109 已撤回）应按修复后的曲线重评：单 worker 800 目标仅 +42 MiB。
- 共享一个 UDP socket 服务全部目标：在途 ≤ `SNMP_MAX_IN_FLIGHT`（100）时接收缓冲区余量充足，
  若未来把在途放大到数千，需评估 `SO_RCVBUF`。
- 若需进一步压缩旧代 engine 残留，可在轮换时用 `lcd.unconfigure` 清 LCD 行，但只能在该代在途为 0 时做。
