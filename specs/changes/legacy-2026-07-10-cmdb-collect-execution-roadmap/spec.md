# Historical Superpowers change: 2026-07-10-cmdb-collect-execution-roadmap

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-10-cmdb-collect-execution-roadmap.md

> **启动日期**: 2026-07-10
> **路线总览**: 本机跑 → Gap-3 闭环 → v4
> **节奏**: 本周 2.5h 跑小对象,下周起 1.5d 跑 e2e 闭环,v4 立项后续推进
> **姊妹文档**: `2026-07-10-cmdb-collect-next-step-discussion.md`(调研报告)
> **状态图例**: ⏳ pending / 🔄 in-progress / ✅ done / ❌ blocked / ⏭️ skipped

---

## Phase 1 — 本机跑小对象(本周,2.5h)

> **目标**:跑通 3-4 个对象 fixture 落盘,优先选有 e2e pipeline 模板的对象,直接为 Gap-3 闭环做铺垫。

| Task | 对象 | 预计 | 实际 | 状态 | 启动时间 | 落盘路径 | 结果 | 失败原因(如有) |
|------|------|------|------|------|---------|---------|------|--------------|
| 1.1 | **influxdb** | 15 min | ~2 min | ✅ done | 2026-07-10 11:38 | `tests/fixtures/collect/influxdb.json` | 624B,raw_stdout 结构化,3 字段(version/ip_addr/port/https_enabled) | |
| 1.2 | **nacos** | 20 min | ~25 min(含排查) | ✅ done | 2026-07-10 11:39→11:55 | `tests/fixtures/collect/nacos.json` | 7 字段(ip_addr/port/https_enabled/status/namespace_count/service_count/config_count) | 折腾:v2.x 无 arm64 → 改 v3.0.2 → 缺 NACOS_AUTH_TOKEN → 加 env → 通 |
| 1.3 | **highgo** | 20 min | ~2 min | ✅ done | 2026-07-10 11:42 | `tests/fixtures/collect/highgo.json` | 临时用 postgres:16-alpine 镜像,5 字段 | |
| 1.4 | **tdsql** | 30 min | ~3 min | ✅ done | 2026-07-10 11:55 | `tests/fixtures/collect/tdsql.json` | 复用 mysql:8.0 镜像,5 字段(同 highgo 结构) | |

### Phase 1 单对象执行模板

每个对象按以下步骤执行(15-30 min):

1. **检查 spec 完整度**
   - `catalog.py` 找对应 MODEL_SPECS,确认 install_commands / start_commands / ready_check
   - 如果缺失 init_script → 写 `init/<obj>_default_discover.sh`(参考 nginx/redis 模板)

2. **拉镜像**
   - `docker pull <image>`(arm64 native 镜像)
   - daocloud 国内源偶尔限速,失败重试 1-2 次

3. **跑 fixture 落盘**
   - `python -m tests.collect_fixtures.cli --model <obj> --bootstrap`
   - 看 `tests/fixtures/collect/<obj>.json` 是否落盘

4. **验证 pytest**
   - `cd server && python -m pytest apps/cmdb/tests/ -k <obj> -v`
   - 看有没有破坏现有测试

5. **回填本表**:状态 / 实际耗时 / 结果 / 失败原因

### Phase 1 决策日志

- **2026-07-10**:确定跑单顺序 influxdb → nacos → highgo → (tdsql 可选),按"跑通率 × Gap-3 价值"排序
- **2026-07-10**:mycat 跳过(amd64 强制 + rosetta 慢)
- **2026-07-10**:mssql 跳过(代码 BLOCKED,start_commands 显式 exit 1)
- **2026-07-10**:**Phase 1 全部完成,4/4 跑通,累计 fixture 28 → 32(+4)**
- **2026-07-10**:catalog.py 镜像前缀调整策略——去掉 `6dduu4opte8882.xuanyuan.run/library/` 前缀,改用 docker.io 默认路径 + daemon.json registry-mirrors(让 docker daemon 自动走 xuanyuan.run 代理)
- **2026-07-10**:daemon.json 加 `https://6dduu4opte8882.xuanyuan.run` 为 mirror(系统级配置)
- **2026-07-10**:nacos v2.3.2 → v3.0.2(arm64 支持)+ 加 NACOS_AUTH_TOKEN env
- **2026-07-10**:nacos wait_strategy timeout 120 → 240(JVM 启动慢)

---

## Phase 2 — Gap-3 e2e 闭环(下周开始,1.5d)

> **目标**:把已落盘 fixture 接入 CMDB 端 e2e 流水线,验证"采集产物 → 落库 → 字段对齐"链路。
> **框架**:`server/apps/cmdb/tests/e2e/pipeline.py:185` 已就绪,只需铺 fixture + schema + test。

| Task | 对象 | 预计 | 实际 | 状态 | 启动时间 | 测试文件 | 结果 | 备注 |
|------|------|------|------|------|---------|---------|------|------|
| 2.1 | **influxdb 第一闭环** | 0.5d | ~30 min | ✅ done | 2026-07-10 12:35 | `test_influxdb_pipeline.py`(已有,加 fixture_driven case) | 3 passed(v2_full + v1_version_only + **fixture_driven**) | 三层验证:契约(jsonschema)+ 流水线 + 字段对齐 |
| 2.2 | **mysql e2e**(P0) | 0.3d | ~30 min | ✅ done | 2026-07-10 13:00 | `test_mysql_pipeline.py`(加 fixture_driven + canonical_to_step3) | 5 passed | db runner 平铺模式 |
| 2.3 | **nginx e2e**(P0) | 0.3d | ~30 min | ✅ done | 2026-07-10 13:20 | `test_nginx_pipeline.py`(加 fixture_driven) | 4 passed | middleware runner extra_payload_keys={"result":True} |
| 2.4 | **redis e2e**(P0) | 0.3d | ~30 min | ✅ done | 2026-07-10 13:35 | `test_redis_pipeline.py`(加 fixture_driven) | 4 passed | db runner 平铺模式;slaves/list master/object vs 01_raw/string |
| 2.5 | postgresql(P1) | 0.2d | | ⏳ pending | | `test_postgresql_pipeline.py` | | |
| 2.6 | mongodb(P1) | 0.2d | | ⏳ pending | | `test_mongodb_pipeline.py` | | |
| 2.7 | tomcat(P1) | 0.2d | | ⏳ pending | | `test_tomcat_pipeline.py` | | |
| 2.8 | rabbitmq(P1) | 0.2d | | ⏳ pending | | `test_rabbitmq_pipeline.py` | | |
| 2.9 | elasticsearch(P1) | 0.2d | | ⏳ pending | | `test_elasticsearch_pipeline.py` | | worktree |
| 2.10 | kafka(P1) | 0.2d | | ⏳ pending | | `test_kafka_pipeline.py` | | worktree |
| 2.11 | zookeeper(P1) | 0.2d | | ⏳ pending | | `test_zookeeper_pipeline.py` | | worktree |
| 2.12 | haproxy(P1) | 0.2d | | ⏳ pending | | `test_haproxy_pipeline.py` | | worktree |

### Phase 2 单对象执行模板

每个对象按以下步骤执行(0.2-0.5d):

1. **复制 fixture 为 e2e 模板**
   - `cp tests/fixtures/collect/<obj>.json server/apps/cmdb/tests/e2e/fixtures/<obj>/01_raw_collector.json`
   - 检查字段名一致性(可能需调整)

2. **生成 schema**
   - `server/apps/cmdb/tests/e2e/schemas/<obj>/01_raw_collector.schema.json`
   - `server/apps/cmdb/tests/e2e/schemas/<obj>/04_cmdb_instance.schema.json`

3. **生成 expected_result**
   - `server/apps/cmdb/tests/e2e/fixtures/<obj>/04_expected_cmdb_result.json`

4. **写 test**
   - `server/apps/cmdb/tests/e2e/test_<obj>_pipeline.py`
   - 抄 `test_nginx_pipeline.py` 模板改 runner/plugin

5. **跑通验证**
   - `cd server && python -m pytest apps/cmdb/tests/e2e/test_<obj>_pipeline.py -v`

6. **回填本表**

### Phase 2 P0 三对象 1.5d 路径

- **Day 1 上午**:2.1 influxdb 第一闭环(已落盘 + 模板最完整)
- **Day 1 下午**:2.2 mysql e2e(用现成 `test_mysql_pipeline.py`)
- **Day 2 上午**:2.3 nginx e2e(用现成 `test_nginx_pipeline.py`)
- **Day 2 下午**:2.4 redis e2e(用现成 `test_redis_pipeline.py`)

### Phase 2 决策日志

- **2026-07-10**:P0 三对象选 mysql / nginx / redis(三个 runner 各一个代表)
- **2026-07-10**:第一闭环选 influxdb(已有 test_influxdb_pipeline.py,1.x/2.x 两条 pipeline)
- **2026-07-10**:P1 8 对象覆盖 db 类 + middleware 类 + 大数据类
- **2026-07-10**:**Phase 2.1 完成!** influxdb fixture-driven 流水线 3 passed,验证三层(契约 jsonschema + 流水线 + 字段对齐)
- **2026-07-10**:Phase 2.1 实施关键步骤 — sqlite + INSTALL_APPS=cmdb,system_mgmt,core 才能跑(数据库环境独立配置)
- **2026-07-10**:`MINIO_*` env 必须设,否则 django_minio_backend 启动报错

---

## Phase 3 — v4 立项(2 人月起)

> **目标**:把 Gap-3 闭环平台化,启动方向 2(消费侧 e2e)+ 方向 3(采集质量度量)+ 方向 1(国产 fixture,前置 amd64 CI)。
> **方式**:用 OpenSpec 起一个 v4 change,先写 proposal + 任务分解。

| Task | 内容 | 工作量 | 实际 | 状态 | 启动时间 | 依赖 | 结果 | 备注 |
|------|------|--------|------|------|---------|------|------|------|
| 3.1 | **OpenSpec change:消费侧 e2e 平台化** | 0.5d | | ⏳ pending | | Phase 2 P0 完成 | | 方向 2 起步 |
| 3.2 | **采集质量度量 dashboard** | 2d | | ⏳ pending | | Phase 2 全 11 对象 | | 方向 3 |
| 3.3 | **amd64 CI runner 解锁** | 1w | | ⏳ pending | | 用户拍板(本路线不强制) | | 前置依赖方向 1 |
| 3.4 | **方向 1 启动:国产 fixture 补完** | 2-3 人月 | | ⏳ pending | | 3.3 完成 | | dameng/ibmmq 等 |
| 3.5 | 漂移检测 + 跨对象公共断言 | 1d | | ⏳ pending | | Phase 2 全 11 对象 | | 抽取公共参数化 |

### Phase 3 决策日志

- **2026-07-10**:v4 主导方向 = 方向 2(消费侧 e2e 平台化)+ 方向 3(质量度量)
- **2026-07-10**:方向 1(国产 fixture)需 amd64 CI 解锁,**不是本路线强制**
- **2026-07-10**:方向 4(K8s/VMware)任何 v4 周期都不开
- **2026-07-10**:**v4 Phase 1 完成!** OpenSpec change `cmdb-collect-v4-e2e-platform` 全阶段落地,96 e2e passed(原 60 + 22 工厂版 + 跨对象契约回归 + 公共契约 oneOf 兼容性)
  - 基础设施:00_common_contract(oneOf A/B/C)+ load_runner_plugin 工厂 + test_pipeline_factory 参数化模板
  - 22 对象 fixture_driven(8 P0 + 6 P1 + 4 P2,sub-agent 并行执行)
  - 5 对象跳过(dameng/tongweb/redis_sentinel/jboss/jetty 无 plugin 类,v4 Phase 2 补)
  - 收尾报告:`docs/superpowers/plans/2026-07-10-cmdb-collect-v4-phase1-execution-report.md`

---

## 决策日志(总览)

| 日期 | 决策 | 影响 |
|------|------|------|
| 2026-07-10 | 不走 GitHub Actions CI(避免 fork Actions 启用) | 30 个对象本机补 |
| 2026-07-10 | 路线 = 本机跑 → Gap-3 闭环 → v4 | 串行衔接 |
| 2026-07-10 | 本机跑单 = influxdb → nacos → highgo → tdsql(可选) | 按"跑通率 × Gap-3 价值"排序 |
| 2026-07-10 | Gap-3 P0 = mysql / nginx / redis(三个 runner 代表) | 模板覆盖最大化 |
| 2026-07-10 | v4 主导 = 方向 2 + 方向 3 | 方向 1 等 amd64 CI |

---

## 风险与备注

### 全局风险

1. **amd64 CI 阻塞方向 1**:30 个对象里有 18 个国产/IBM/SAP/Hadoop 必须 amd64,本机路线全部跑不通
2. **init_script 缺失**:11 个非 BLOCKED 对象 install_commands 为空,跑前必须先写 init 脚本
3. **fixture 路径**:stargazer 落盘路径 `tests/fixtures/collect/`,不是 `results/`,e2e 复制需手动对字段
4. **docker pull 国内源限速**:daocloud 镜像偶尔慢,需重试

### 时间投入预期

- **Phase 1**:本周 2.5h(每天 30 分钟)
- **Phase 2**:下周 1.5d(P0) + 后 1.5d(P1) = 3d
- **Phase 3**:v4 立项后 2 人月起

### 用户 review 点(每个 Phase 结束后)

- Phase 1 结束:跑通几个、失败几个、是否进 Phase 2
- Phase 2 P0 结束:第一闭环达成,是否扩 P1
- Phase 2 全 11 对象结束:是否进 v4 立项
- Phase 3.1 完成:v4 proposal 评审
