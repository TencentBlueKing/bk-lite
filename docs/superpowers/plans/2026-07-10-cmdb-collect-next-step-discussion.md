# CMDB 配置采集 — 下一步工作调研报告

> **调研日期**: 2026-07-10
> **决策路线**: 本机跑 → Gap-3 闭环 → v4
> **调研方式**: 3 个 sub-agent 并行调研,本会话整合

## 1. 背景

v3 路线图(2026-07-06 立项)已完成代码侧工作:

- catalog 注册 **57/57 MODEL_SPECS**(100%)
- pytest **160 passed**(全绿)
- 真实 fixture 落盘 **27/57**(main 分支 7 + worktree 20)
- 已 commit + push:`51c76aefa` 在 `feature-cmdb-collect-v3-gap4-validate`

**当前阻塞**:
- v3 路线图留的 Gap-3(采集产物 → 落库 → e2e 验证)未启动
- 30 个对象代码就绪但 fixture 空,本机没跑
- 用户决定不走 GitHub Actions CI(避免 fork Actions 启用问题)
- 本机 darwin arm64 Mac 限制:国产 binary 走 rosetta 慢

**目标**:确定 v3 之后的下一阶段做什么、怎么做。

## 2. 路线 A — 本机跑小对象(Sub-agent A 调研)

### 2.1 镜像可达性

`feature-cmdb-collect-v3-gap4-validate` worktree 的 catalog(1784 行 / 57 对象)中:
- **镜像全部为 multi-arch**:`docker.m.daocloud.io/library/ubuntu:22.04`(arm64 直接跑)
- 4 个官方多架构镜像:postgres:16-alpine / influxdb:2.7 / nacos-server:v2.3.2 / mysql:8.0
- 1 个 mssql 官方镜像(mcr.microsoft.com,支持 arm64)
- **唯一显式 `platform="linux/amd64"` 的对象**:mycat(spec 1022 行注明 wrapper 只支持 x86,走 rosetta 模拟)

### 2.2 跑通率排名(待补 30 个)

| 等级 | 对象 | 跑通率 | 原因 |
|---|---|---|---|
| 🟢 高 | influxdb / nacos / highgo | 高 | 官方 multi-arch 镜像 + env 完整,只需写 init_script |
| 🟡 中 | mssql | 中 | spec install_commands 10 步完整,但 start_commands 显式 `exit 1`(G1.4 arm64 阻塞) |
| 🟡 中 | tdsql / tongrds | 中 | 镜像可达,需手动装业务服务 |
| 🟢 镜像可达但 install 空 | ambari / couchbase / iris / oceanbase / sap_hana / server_bmc | 极低 | 无 install_commands,需本机装 4GB+ 企业版二进制 |
| 🔴 显式 BLOCKED | apusic / bes / domestic_linux / gbase8s / ihs / informix / inforsuite_as / oscar / sybase / tonggtp / tonglinkq / hdfs / storm / yarn / mycat / tuxedo / weblogic / websphere | 0 | install_commands 故意 `exit 1` + 国产/IBM/SAP/Hadoop license |

### 2.3 数量预期(1 周 × 30 分钟/天 = 2.5 小时)

- **乐观**:3 个高 + 1 个中 = 4 个 fixture
- **保守**:1 个高 + 1 个中 = 2 个 fixture
- **现实目标**:3 个(挑 3 个最高跑通率的)

### 2.4 推荐跑单(按"跑通率 × Gap-3 价值"排序)

| 序 | 对象 | platform | 跑通率 | Gap-3 价值 | 备注 |
|---|---|---|---|---|---|
| 1 | **influxdb** | arm64 native | 🟢 高 | 🟢 高 | **已有 e2e pipeline 文件**(`server/apps/cmdb/tests/e2e/test_influxdb_pipeline.py`),fixture 可直接转 raw_collector 模板 |
| 2 | **nacos** | arm64 native | 🟢 高 | 🟢 高 | test_new_collect_objects_plugins 已有 mock,缺真数据 |
| 3 | **highgo** | arm64 native | 🟢 高 | 🟡 中 | 国产 PG 兼容,init_script 缺失,30 分钟够写 |
| 4 | **tdsql** | arm64 native | 🟡 中 | 🟡 中 | 同 mysql 协议,可参考 mysql 已落盘 fixture 套壳 |
| 5 | **tongrds** | arm64 native | 🟡 中 | 🟡 中 | 国产人大金仓 |
| 6 | **mssql** | arm64 native | 🟡 中(代码 BLOCKED) | 🟢 高 | install 完整,只需重写 start_commands 跳过 exit 1 即可试 |
| 7 | **server_bmc** | arm64 native | 🟢 高(若 mock) | 🟡 中 | BMC/IPMI 可用 mock 服务代替真硬件 |
| 8 | **ambari** | arm64 native | 🟡 中 | 🟡 中 | Hadoop 全家桶大 |

### 2.5 失败预期(本机几乎跑不通)

1. **mssql**:spec `start_commands` 显式 `exit 1`(G1.4 arm64 vs amd64 平台冲突)
2. **mycat**:`platform="linux/amd64"`,wrapper 不支持 arm64 native,rosetta 慢且不一定成功
3. **tuxedo / weblogic / websphere**:install 依赖外部环境变量(license),本机无 Oracle/IBM 安装包
4. **couchbase / sap_hana / iris / oceanbase**:镜像可达但 install 空,需本机下载 4GB+ 企业版
5. **18 个国产 / 大数据 / IBM / SAP**:全部 install 显式 `exit 1`,代码侧故意留作后续工作

### 2.6 风险点

1. `docker_lifecycle.py:58` 显式 `platform=spec.platform`,catalog 30 个待补对象里 29 个 platform 为 `None`
2. **init_script 缺失**:11 个非 BLOCKED 候选 install_commands 为空,跑前必须先写 init_script
3. **vm_ssh.py 路径**:ssh 入口对象需要容器内启 sshd;influxdb/nacos 走 docker SDK 即可
4. **stargazer fixture ≠ e2e fixture 直接消费**:e2e 01_raw_collector.json 需手动对字段名复制
5. **amd64 模拟**:mycat 强制 amd64,Mac arm64 走 rosetta 慢 5-10 倍,**跳过**

## 3. 路线 B — Gap-3 e2e 验证(Sub-agent B 调研)

### 3.1 关键事实修正

- **fixture 实际落盘路径**:`agents/stargazer/tests/fixtures/collect/<model_id>.json`
- **真实落盘 7 个**(main 分支):mysql / postgresql / redis / mongodb / nginx / tomcat / rabbitmq
- **worktree 多 20 个**:elasticsearch / kafka / zookeeper / haproxy / keepalived / openresty / apache / activemq / dameng / tongweb 等
- 总数 27/57(本机已落盘 + worktree 待合并)

### 3.2 框架现状(几乎全套就绪)

**核心发现**:CMDB 端已有 4 段通用 e2e 流水线框架,不用从零搭。

```
[1] stargazer raw_stdout  ──→  load_fixture("<obj>/01_raw_collector.json")
        ↓ step1_stargazer_normalize_generic
[2] {success, result: {model_id: [items]}}
        ↓ step2_push_to_vm(extra_payload_keys=...)
[3] VictoriaMetrics PromQL 响应(走 mock)
        ↓ step3_cmdb_consume_generic(runner_cls, plugin_cls, ...)
[4] CMDB 实例字典(真实跑 CollectBase.format_data + format_metrics + bind_collection_mapping)
```

**关键代码**:`server/apps/cmdb/tests/e2e/pipeline.py:185` 的 `run_full_pipeline_generic()`

**mock 边界**:只在"VM PromQL"和"DB"两层用 monkeypatch,runner 和 plugin 真实跑。fixture 是**单一数据源**。

### 3.3 CMDB 端代码改造

**几乎不用改 production 代码**,只在 `server/apps/cmdb/tests/e2e/` 下加测试文件:

- 新建 `fixtures/<obj>/01_raw_collector.json` — 复制 stargazer fixture 的 `raw_stdout` 块
- 新建 `fixtures/<obj>/04_expected_cmdb_result.json` — 期望实例字段子集
- 新建 `schemas/<obj>/01_raw_collector.schema.json` + `04_cmdb_instance.schema.json` — jsonschema 校验
- 新建 `test_<obj>_pipeline.py` — 调 `pipeline.run_full_pipeline_generic(...)`(40-50 行/对象)

**Runner 选择**:
- middleware 类(nginx/tomcat/rabbitmq/zookeeper/kafka 等)→ `MiddlewareCollectMetrics` + `extra_payload_keys={"result":True}`
- db 类(mysql/postgresql/redis/mongodb/elasticsearch/hbase)→ `DatabasesCollectMetrics` + `extra_payload_keys=None`
- protocol 类(mssql/influxdb)→ `ProtocolCollectMetrics` + `extra_payload_keys=None`
- host 类(已有 `step1_stargazer_normalize_host` 专用路径)

### 3.4 跑通标准(三层递进)

1. **契约层**:`jsonschema.validate(raw, 01_raw_collector.schema.json)` 通过
2. **流水线层**:`pipeline.run_full_pipeline_generic` 返回非空 `cmdb_result[<model_id>]`,实例数 ≥ `instance_count_min`
3. **字段对齐层**:`actual.get(k) == expected[k]` 对 `expected_instance_subset` 子集字段 1:1 比对

### 3.5 工作量估算

| 项 | 人天 | 说明 |
|---|---|---|
| 通用框架已就绪 | 0 | `pipeline.py:185` + 9 个示范对象 |
| 1 个新对象 e2e 覆盖 | 0.4 | fixture 2 + schema 2 + test 1 = 5 文件;抄 `test_nginx_pipeline.py` 模板 30 分钟 |
| 27 个对象(含 worktree 真实落盘) | **11–12** | 含 schema 反复调整、字段对齐调优、CI 集成 |
| 漂移检测 + 跨对象公共断言 | 1 | 抽取 `test_drift_detection` 公共参数化 |
| **合计** | **11–13 人天** | 不含 amd64 CI 跑真采 |

### 3.6 推荐优先级

| 档 | 对象 | 选择依据 |
|---|---|---|
| **P0 必做(3)** | mysql / nginx / redis | 三个 runner(middleware/db/protocol)各一个代表,模板覆盖最大化 |
| **P1 高价值(8)** | postgresql / mongodb / tomcat / rabbitmq / elasticsearch / kafka / zookeeper / haproxy | 复用 P0 模板;worktree 已落盘可直接消费 |
| **P2 商业版补(16)** | dameng / ibmmq / redis_sentinel / tonglinkq 等 | 等 fixture 落盘 + enterprise overlay plugin 实现 |

### 3.7 复用点(几乎全套)

- **流水线驱动**:`apps/cmdb/tests/e2e/pipeline.py:185` 的 `run_full_pipeline_generic()`
- **conftest**:`apps/cmdb/tests/e2e/conftest.py:25-42` 的 `load_fixture` / `load_schema` fixtures
- **9 个对象模板**:`test_nginx_pipeline.py` / `test_mysql_pipeline.py` / `test_redis_pipeline.py` 等都可逐字参考
- **fake_graph**:`apps/cmdb/tests/conftest.py` 的 fake_graph fixture
- **fake_nats**:`conftest.py:50-79` 给 config_file 流水线用
- **jsonschema 断言模式**:`test_drift_detection_bad_raw_caught_by_schema` (`test_nginx_pipeline.py:73`)

**结论**:Gap-3 不需要新设计,只需按 P0/P1 顺序铺 fixture + schema + test。

## 4. 路线 C — v4 候选方向(Sub-agent C 调研)

### 4.1 v3 现状锚点

- catalog 注册 57 个 MODEL_SPECS(v2=7 → v3=57)
- Phase 1-5 共 26 个新对象阻塞在 amd64 模拟
- pytest 160 passed,但 0 真实采集跑通(本机路线补)
- Gap-3 e2e 消费侧没做(v3 路线图 §2.3 明确「fixture 无下游消费方」)
- v3 明确排除:K8s/VMware/云采集(aliyun/hwcloud/qcloud)/Network/IPAM/Storage/Host

### 4.2 方向对比表

| # | 方向 | 业务驱动力 | 工作量 | 风险 | v3 衔接 | 推荐 |
|---|---|---|---|---|---|---|
| 1 | **商业版国产化对象真实采集**(v3 留的 26 个补 fixture) | dameng/ibmmq/redis_sentinel/tonglinkq/ihs/kingbase/gbase8s 等客户场景刚需 | **2-3 人月**(amd64 CI runner 是前置条件) | 硬件依赖高;国产镜像/许可证/集群复杂对象 | **强承上** | ⭐⭐⭐⭐⭐ |
| 2 | **消费侧 e2e + 落库校验**(v3 明确 Gap-3) | fixture 落地了但 CMDB 端没消费,价值无法验证;落库 schema drift 是数据可信度问题 | **1.5-2 人月** | 需先确定 CMDB 端 e2e 入口;需明确「consume fixture」是哪个模块 | **强承上**(v3 路线图 §2.3) | ⭐⭐⭐⭐⭐ |
| 3 | **采集质量度量体系**(schema drift / 覆盖率 / 回归) | fixture 一致性、采集字段覆盖率、回归基线 | **1.5-2 人月** | 指标定义需和业务对齐;dashboard 工作量看选型 | **强承上** | ⭐⭐⭐⭐ |
| 4 | **云采集 / K8s / VMware**(v3 明确排除范围) | 客户场景确实有需求,但 v3 用户**明确不做** | **4-6 人月**(K8s 单算 2 人月起) | 与用户偏好直接冲突(历史 plan 多处标注「用户明确排除」) | **另起**,与 v3 几乎无关 | ⭐⭐ |
| 5 | **stargazer 插件扩展**(更多 collector / SDK) | catalog 已注册但 plugin stub 待补(influxdb/nacos/ambari/server_bmc 等 11 个) | **1-1.5 人月** | 与方向 1 部分重叠;独立价值低 | **中承上** | ⭐⭐⭐ |

### 4.3 推荐排序

1. **方向 1 — 商业版国产对象真实采集**(承上 + 客户刚需,**前置依赖 amd64 CI runner**)
2. **方向 2 — 消费侧 e2e + schema drift 校验**(填补 v3 留的 Gap-3,fixture 不再悬空)
3. **方向 3 — 采集质量度量**(让 fixture 平台化、可信化,接方向 1+2 产出)

### 4.4 下一步建议

**强烈建议 v4 启动两件并行**:

- **【立即可做,0 阻塞】方向 2 启动**:消费侧 e2e 不依赖 amd64 CI,纯 Python+ORM 改造,直接消化 v3 留的 Gap-3。建议先做小切片:**CMDB 端加载 fixture → 实例化 → 落库 → 自动比对实际采集字段差异**
- **【前置解锁,串行关键路径】方向 1 启动**:**第一周先把 amd64 CI runner 跑通**(`GitHub Actions ubuntu-22.04`),这是 v3 26 个对象全部解锁的开关

**不建议**:
- 方向 4(云/K8s/VMware):与用户历史偏好强冲突,任何 v4 周期都不该开
- 方向 5 单独做:插件 stub 补全是方向 1 的子任务,不该独立成方向

**节奏建议**:
- v4 Phase 1(2 人月):amd64 CI + 消费侧 e2e 雏形 + mycat/kingbase/highgo 真实 fixture
- v4 Phase 2(2 人月):dameng/ibmmq/redis_sentinel + 落库 schema drift 自动化
- v4 Phase 3(2 人月):采集质量度量 dashboard + 剩余国产对象

> **总周期估算 6 人月**;前置 1 周内必须验证 amd64 CI 可行性,否则 v4 与 v3 同源阻塞。

## 5. 串行衔接建议(三方共识)

按调研结果,最优路径是 **"本机跑 → Gap-3 闭环 → v4"** 一条线串起来:

```
本周(本机,2.5h)
  ↓
[1] influxdb 跑通 → fixture 落盘  ← 已有 e2e pipeline 模板,跑通直接闭环
[2] nacos 跑通 → fixture 落盘
[3] highgo 跑通 → fixture 落盘(可选)
  ↓
下周开始(Gap-3 闭环,1.5d)
  ↓
[4] influxdb fixture 复制成 01_raw_collector.json → 跑通 e2e → 第一闭环达成
[5] 复用模板扩到 mysql / nginx / redis(P0 三对象)
  ↓
v4 启动(方向 2 主导 + 方向 3 跟进)
  ↓
[6] 消费侧 e2e 平台化(11 对象 → 全量)
[7] 采集质量度量 dashboard
[8] amd64 CI 解锁后补方向 1 国产 fixture
```

**核心价值**:一周内就能看到第一个 Gap-3 闭环(采集产物 → 落库 → e2e 验证)。

## 6. 决策与下一步

**已确定路线**:本机跑 → Gap-3 闭环 → v4

**执行追踪**:见姊妹文档 `2026-07-10-cmdb-collect-execution-roadmap.md`

## 7. 参考资料

- v3 roadmap:`docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md`
- v3 phase1-5 执行报告:`docs/superpowers/plans/2026-07-0[7-8]-cmdb-collect-v3-phase[1-5]-execution-report.md`
- CMDB e2e 框架:`server/apps/cmdb/tests/e2e/pipeline.py:185`
- catalog 定义:`agents/stargazer/tests/collect_fixtures/catalog.py`
- docker_lifecycle:`agents/stargazer/tests/collect_fixtures/docker_lifecycle.py`
- init 脚本目录:`agents/stargazer/tests/collect_fixtures/init/`