# Proposal: CMDB 采集 v4 — 消费侧 e2e 平台化

Status: ready

## Migration Context

- Legacy source: `openspec/changes/cmdb-collect-v4-e2e-platform/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

v3 已完成代码侧(57/57 catalog + 160 pytest),但 fixture 落盘与 CMDB 端 e2e 验证**脱节**:

- **fixture 端**:32/57 真实落盘,但每个 fixture 缺乏自动验证
- **CMDB 端**:已有 4 段通用 e2e 流水线(`server/apps/cmdb/tests/e2e/pipeline.py:185`),但**只有 4 个对象**有 fixture_driven 测试
- **断链风险**:stargazer 改了一个字段名,CMDB 端要等生产环境踩坑才发现

**机会**:v3 已经把 e2e 框架搭好,4 个对象的 fixture_driven 测试模板(protocol/db/middleware 三种 runner)已验证通过。**铺到 27 个真实落盘对象的工作量很小**(每个 30 分钟),但能**首次实现"采集产物 → 落库 → 字段对齐"全链路自动验证**。

**为什么现在**:
- v3 worktree 5 个新 commit(Phase 1+2)已落,代码侧稳态
- 4 个 runner 模板就绪,铺到其他对象 = 重复工作,可批量
- 后续 v4 阶段(质量度量 / schema drift 检测)都依赖这个 e2e 平台

## What Changes

- **新增**:`server/apps/cmdb/tests/e2e/fixtures/<model_id>/01_stargazer_raw.json` × 23(覆盖剩余 23 个真实落盘对象)
- **新增**:`server/apps/cmdb/tests/e2e/schemas/<model_id>/01_stargazer_raw.schema.json` × 23
- **新增**:`server/apps/cmdb/tests/e2e/fixtures/<model_id>/04_expected_cmdb_result.json` × 23
- **新增**:`test_<model_id>_pipeline.py` × 23(每对象 fixture_driven 测试,3 层验证)
- **新增**:`server/apps/cmdb/tests/e2e/conftest.py` 扩展 — `load_runner_plugin_for_model_id()` 工厂函数(根据 model_id 自动选 runner + plugin)
- **新增**:`server/apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json` — 跨对象公共契约(所有 fixture 必须满足的基础结构)
- **修改**:`test_influxdb_pipeline.py / test_mysql_pipeline.py / test_nginx_pipeline.py / test_redis_pipeline.py` — 抽出 `test_pipeline_fixture_driven` 为公共参数化 fixture(避免 23 份重复)
- **新增**:`specs/capabilities/cmdb-e2e-authoring.md` — 给后续对象写 e2e 的 step-by-step 文档(对齐用户"偏好文档支持 review"风格)

**BREAKING**:无(纯新增 + 测试基础设施)

## Capabilities

### New Capabilities

- `cmdb-collect-fixture-e2e`:为每个有 stargazer 真实落盘的对象,提供"采集 fixture → CMDB 端实例"全链路自动验证。包含 3 层验证(契约 jsonschema / 流水线 run / 字段 1:1 对齐)和 inst_name 规则 `{ip}-{model_id}-{port}` 兜底校验。
- `cmdb-e2e-runner-plugin-factory`:基于 model_id 自动选 runner + plugin + extra_payload_keys,屏蔽三个 runner 形态(protocol 平铺 / db 平铺 / middleware metric.result JSON)的差异。
- `cmdb-e2e-cross-object-contract`:所有 fixture 必须满足的公共契约(必须有 model_id / captured_at / raw_stdout.success / raw_stdout.result.{model_id}[] 至少 1 条),用于早期发现 fixture 漂移。

### Modified Capabilities

(暂无。v4 不修改 v3 已有 spec 的需求,只新增基础设施。)

## Impact

- **代码影响**:
  - `server/apps/cmdb/tests/e2e/` 新增 ~80 个文件(23 对象 × 3 fixture + 1 test + 共享工厂)
  - `server/apps/cmdb/tests/e2e/pipeline.py` 加 1 个工厂函数(单方法,≤30 行)
  - `server/apps/cmdb/tests/e2e/conftest.py` 加 1 个 fixture(≤20 行)
- **依赖影响**:无(纯 Python + 已有 jsonschema)
- **运行时影响**:本地开发跑 `pytest apps/cmdb/tests/e2e/ -v` 时间从 ~25s → 预计 ~3-4 min(23 个对象 × 8-10s/对象)
- **CI 影响**:v3 已有 CI(GitHub Actions),新增 e2e 测试加进去(增量 < 3 min)
- **风险**:
  - 23 个对象 plugin field_mapping 不全(role / master_host 等不入实例)→ 已在 Phase 2 摸到,test 走 expected_subset 子集比对
  - 部分对象 fixture 真实落盘版本为空字段(highgo version="")→ expected_subset 留空 + jsonschema 校验字段可选
  - middleware runner 的 extra_payload_keys 必须正确设置 → 工厂函数按 model_id 预设
- **可逆性**:高(纯新增,失败可逐对象回滚)
- **依赖前置**:
  - Phase 1 已完成(32/57 fixture 落盘)
  - Phase 2 P0 已完成(4 个对象 e2e 模板就绪)
  - **本 change 目标**:把 4 个对象扩到 27 个对象

## 验证标准(交付时)

- [ ] 23 个对象的 `test_<model_id>_pipeline.py::test_pipeline_fixture_driven` 全部 passed
- [ ] 全部 e2e 跑通(预计 ~100+ tests passed,包括 23 个 fixture_driven)
- [ ] `server/apps/cmdb/tests/e2e/conftest.py` 的 `load_runner_plugin_for_model_id()` 工厂就绪并被使用
- [ ] 跨对象公共契约 schema 验证 27 个 fixture(主分支 + worktree)全部命中
- [ ] 文档 `specs/capabilities/cmdb-e2e-authoring.md` 完成,包含"加一个新对象 e2e 只需 5 步"的模板
- [ ] pytest 增量覆盖率 ≥ 75%(specs/capabilities/engineering-quality.md 红线)
- [ ] 在 v3 路线图文档追加 v4 章节 + 链接

## 不在范围内(明确排除)

- **方向 1**(国产 fixture 真实采集)— 需 amd64 CI runner,前置依赖未达成
- **方向 4**(K8s / VMware / 云采集)— 用户历史偏好明确排除
- **方向 5**(stargazer 插件扩展)— 是方向 1 的子任务,不在本 change 范围
- **生产环境 schema drift dashboard** — 留 v4 Phase 2
- **fixture 覆盖率 dashboard** — 留 v4 Phase 2

## Implementation Decisions

## Context

v3 已完成代码侧 100%(commit `51c76aefa` + 5 个新 commit),32/57 fixture 真实落盘。Phase 2 P0 已在 v3 worktree 跑通 4 个对象的 fixture_driven e2e 测试(commit `f59351609` + 后续 3 个),共 51 passed。

**当前状态**:
- `server/apps/cmdb/tests/e2e/pipeline.py:185` — 4 段通用流水线(`step1_stargazer_normalize_generic` / `step2_push_to_vm` / `step3_cmdb_consume_generic` / `run_full_pipeline_generic`)就绪
- 3 个 runner 形态已验证:ProtocolCollectMetrics(平铺)/ DBCollectCollectMetrics(平铺)/ MiddlewareCollectMetrics(metric.result JSON 编码)
- 4 个对象有 fixture_driven 测试:influxdb(protocol)/ mysql(db)/ nginx(middleware)/ redis(db)
- **断链**:23 个有真实落盘的对象(主分支 7 + worktree 20 = 27,已做 4 个)无 e2e 验证

**约束**:
- 测试必须离线可跑(`DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core` + monkeypatch)
- 不引入新依赖(只用 Python + 已有 jsonschema + pytest-django)
- 必须按用户偏好"先文档后动手 + 支持回填" — 作者文档必出
- 复用 v3 已有的 4 个对象模板(不重写,只抽取公共部分)

**stakeholders**:
- 用户本人(两边 owner,既要消费又要采集)
- 团队其他人(后续接手需要写新对象 e2e → 文档驱动)
- 未来 v4 Phase 2(质量度量 / schema drift)依赖此平台

## Goals / Non-Goals

### Goals

- 27 个真实落盘对象 100% 有 fixture_driven e2e 测试
- 跨对象公共契约自动验证(`test_common_contract.py` 自动遍历)
- 新对象加 e2e ≤ 5 步(按 author guide)
- 全部 e2e 跑通时间 ≤ 5 min
- pytest 增量覆盖率 ≥ 75%(QUALITY_SCORE 红线)
- 4 个对象的现有测试**不破坏**(回归)

### Non-Goals

- 方向 1(国产 fixture 真实采集)— 需 amd64 CI,前置未达成
- 方向 4(K8s / VMware / 云采集)— 用户偏好明确排除
- 生产环境 schema drift dashboard — v4 Phase 2
- fixture 覆盖率 dashboard — v4 Phase 2
- 修改 stargazer / CMDB production 代码 — 本 change 纯测试

## Decisions

### D1:工厂函数放 conftest.py 而非新建 plugin_registry

**决策**:`server/apps/cmdb/tests/e2e/conftest.py` 加 `load_runner_plugin_for_model_id()` 函数(单文件,≤30 行),不新建 `plugin_registry.py`。

**理由**:
- 27 个对象 × 1 行三元组 = 27 行表,放 conftest 自然
- 工厂是测试设施,不是 production 代码
- 不引入新的模块边界,降低 review 成本

**Alternatives considered**:
- 新建 `apps/cmdb/collection/plugin_registry.py`(production 模块)— 拒绝,因为是测试设施
- 用 decorator 自动注册(import 时副作用)— 拒绝,隐式行为难调试
- YAML 配置驱动(`plugin_registry.yaml`)— 拒绝,TypeScript 风格的动态类型带来额外复杂度

### D2:不重写 4 个对象现有 test,只抽公共参数化

**决策**:`test_influxdb_pipeline.py` 等 4 个对象的现有 test **保留不动**,新增 `test_pipeline_fixture_driven_via_factory` 参数化版本作为"工厂"模板。

**理由**:
- 4 个对象的现有 test 是已验证的"金标准",重写有回归风险
- 新增参数化版本作为后续 23 对象的可复用模板
- 现有 test 失败 = 工厂版本也失败(自然形成交叉验证)

**Alternatives considered**:
- 重写 4 个对象的 test 用工厂— 拒绝,增加回归面
- 删除 4 个对象原 test 只留工厂版— 拒绝,丢掉金标准

### D3:跨对象公共契约用 `$ref` 而非复制

**决策**:`schemas/00_common_contract.schema.json` 集中定义公共字段(必填 model_id / captured_at / raw_stdout 结构),对象级 schema 用 `$ref` 引用,不复制定义。

**理由**:
- 公共字段改了 = 改一处(避免 27 个 schema 同步修改)
- 符合 JSON Schema 规范
- 公共契约变更影响范围 = 1 个文件

**Alternatives considered**:
- 公共字段 inline 在每个对象 schema — 拒绝,维护灾难
- Python 端校验公共契约(不走 schema)— 拒绝,丢失 schema 验证的强类型保证

### D4:不写 conftest 跨对象 fixture 自动发现 — 用显式列举

**决策**:`test_common_contract.py` 用 `pytest.mark.parametrize` 显式列举 27 个 model_id(参数化列表),不靠 `os.listdir` 自动发现。

**理由**:
- 显式列举 = review 时一眼看出"哪些对象已覆盖 / 哪些漏了"
- 新增对象时 CI 必然 fail(参数化列表与新 fixture 不匹配),强制更新 test
- 自动发现会让"漏加 fixture"无法被发现

**Alternatives considered**:
- `os.listdir('fixtures/')` 自动发现 — 拒绝,失去"哪些覆盖了"的可视化
- glob pattern `fixtures/*/01_stargazer_raw.json` — 拒绝,同理由

### D5:作者文档 `specs/capabilities/cmdb-e2e-authoring.md` 用 step-by-step 模板

**决策**:作者文档按"5 步加新对象 e2e"写,每步给具体命令 + 期望输出 + 注意事项。

**理由**:
- 用户偏好"文档支持 review + 回填"
- 团队其他人接手时 5 分钟就能上手
- 与 v3 路线图风格一致(看 v3 plan 文档就能感受到)

**Alternatives considered**:
- 只写 README 几行 — 拒绝,信息密度不够
- 视频教程 — 拒绝,需要外部存储且不便 review

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **27 个对象的 plugin field_mapping 不全**(如 mysql 缺 role)→ expected_subset 不一致 | Phase 2 已踩过,test 用 expected_subset 子集比对,只断言 plugin 实际映射的字段 |
| **stargazer 真实 fixture 字段值可能不准确**(如 highgo version="") | expected_subset 留空字符串 + schema `type: ["string", "null"]`,不强制值 |
| **27 个对象 e2e 跑通时间 > 5 min** | factory 用 model_id 直接跳到 step3(避免重复 step1/step2),每个对象 8-10s 预计 |
| **新增对象 e2e 模板** | author guide 详细 + Phase 2 已铺 4 个可参考 |
| **公共契约 schema 改了 → 大量 test fail** | schema 改前先在 1 个对象试跑,确认无回归再推广 |
| **工厂函数 import 失败**(plugin 路径改了) | 工厂 import 集中在 conftest,失败时明确抛 `ImportError(f"plugin for {model_id} not found")` |
| **CI runner 环境差异**(Mac vs Linux) | 已有 e2e 在 sqlite 跑,跨平台一致 |
| **27 个对象 e2e 不能完全照搬 4 个模板**(各对象 plugin 字段不同) | author guide 留"自定义 expected_subset 模板"段,显式列常见情况 |

## Migration Plan

### 阶段 1:基础设施(0.5d,优先)

1. 写 `00_common_contract.schema.json`
2. 写 `load_runner_plugin_for_model_id()` 工厂(conftest.py)
3. 写 `test_common_contract.py` 跨对象公共契约测试
4. 写 `specs/capabilities/cmdb-e2e-authoring.md`

### 阶段 2:参数化工厂模板(0.3d)

5. 抽 `test_pipeline_fixture_driven_via_factory` 参数化模板(conftest 或独立文件)
6. 跑通 4 个现有对象的工厂版本,确认不破坏现有 test

### 阶段 3:批量铺 23 个对象(1.5-2d)

按"已落盘 / 高价值"优先级:

| 优先 | 对象 | 模板参考 | 预计 |
|---|---|---|---|
| P0 | postgresql / mongodb / tomcat / rabbitmq | mysql / redis / nginx 模板 | 30 min/对象 |
| P1 | elasticsearch / kafka / zookeeper / haproxy | influxdb(protocol) + mysql(db) | 30 min/对象 |
| P2 | keepalived / openresty / apache / activemq / dameng / tongweb / minio / consul / etcd / memcached / squid / rocketmq / redis_sentinel / jboss / jetty | 同上 | 30 min/对象 |
| (worktree 中已有 fixture 但未在主分支) | 18 个对象 | 同上 | 30 min/对象 |

每对象 5 步:
1. `cp` stargazer fixture → `fixtures/<obj>/01_stargazer_raw.json`
2. 写 `schemas/<obj>/01_stargazer_raw.schema.json` + `04_cmdb_instance.schema.json`(用 `$ref` 公共契约)
3. 写 `fixtures/<obj>/04_expected_cmdb_result.json`(从 fixture raw 抽出关键字段,标注数据源)
4. 写 `test_<obj>_pipeline.py` 调工厂 + 三层验证
5. 跑 `pytest -v`,失败修 expected_subset

### 阶段 4:验证 + commit(0.3d)

27. `pytest apps/cmdb/tests/e2e/ -v` 全跑(预计 ~100+ tests passed)
28. 提交 commit:feat / docs 拆开
29. 写 v4 收尾报告

### Rollback 策略

- 每个对象 commit 独立,失败可 `git revert <commit>` 单对象回滚
- 工厂函数放 conftest.py 不放新建文件,回滚 1 个 commit 即可
- 公共契约 schema 集中 1 个文件,回滚简单
- 4 个对象原 test 不动,即使新代码坏也不影响

## Open Questions

1. **工厂函数的 import 失败处理**:`ImportError` 还是 `pytest.skip`?
   - 倾向 `pytest.skip` + warning,避免某对象 plugin 没装导致整个 e2e 套件 fail
   - 需 review 时确认

2. **27 个对象 e2e 是否分批 commit 还是一个 commit?**
   - 倾向每对象 1 commit(原子性好,review 友好)
   - 阶段 1 基础设施可独立 1 commit
   - 阶段 3 批量阶段每对象 1 commit

3. **跨对象参数化模板放 conftest 还是 `test_pipeline_factory.py`?**
   - 倾向 `test_pipeline_factory.py`(独立文件,符合 pytest 自动发现)
   - conftest 只放 fixture + 工厂函数

4. **文档放 docs/ 还是 `server/apps/cmdb/tests/e2e/README.md`?**
   - 倾向 `specs/capabilities/cmdb-e2e-authoring.md`(跨模块文档统一)
   - 也可加 `server/apps/cmdb/tests/e2e/README.md` 作为本地入口

5. **作者指南用什么工具写?** Markdown(默认) vs Docusaurus(若后续接 docs 站)
   - 倾向 Markdown(v4 不引入新工具)

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-10
```

## Capability Deltas

### cmdb-collect-fixture-e2e

## ADDED Requirements

### Requirement: 每个有 stargazer 真实落盘的对象必须有 fixture_driven e2e 测试

对于任何 `agents/stargazer/tests/fixtures/collect/<model_id>.json` 存在的对象,CMDB 端测试套件 MUST 包含 `apps/cmdb/tests/e2e/test_<model_id>_pipeline.py::test_pipeline_fixture_driven`。

#### Scenario: 全部真实落盘对象都有 fixture_driven 测试
- **WHEN** v3+ 阶段有 stargazer cli 真实落盘的 fixture
- **THEN** 该对象的 `test_<model_id>_pipeline.py::test_pipeline_fixture_driven` 在 CMDB 端测试套件中存在并 passed

#### Scenario: 全部 fixture_driven 测试通过
- **WHEN** 运行 `pytest apps/cmdb/tests/e2e/test_<model_id>_pipeline.py::test_pipeline_fixture_driven -v`
- **THEN** 返回 0 failures(单对象),CI 阶段运行 `pytest apps/cmdb/tests/e2e/` 时所有对象的 fixture_driven 测试全部 passed

### Requirement: fixture_driven 测试必须验证三层

每个 `test_pipeline_fixture_driven` MUST 按顺序验证三层(任一层失败即 fail):

1. **契约层**:stargazer fixture 必须命中 `schemas/<model_id>/01_stargazer_raw.schema.json`(`jsonschema.validate` 不抛 `ValidationError`)
2. **流水线层**:`pipeline.run_full_pipeline_generic()` 返回的 `cmdb_result[<model_id>]` 必须有 ≥ `instance_count_min` 个实例
3. **字段对齐层**:实例的关键字段(`expected_instance_subset` 子集)必须 1:1 等于 `fixtures/<model_id>/04_expected_cmdb_result.json` 中声明的值

#### Scenario: 契约层拦截字段漂移
- **WHEN** stargazer 端字段类型从 string 改成 int(例如 `port` 从 `"8086"` 变成 `8086`)
- **THEN** `jsonschema.validate(stargazer_raw, schema)` 抛 `ValidationError`,test fail
- **THEN** CI 立刻报警,无需等生产环境踩坑

#### Scenario: 流水线层拦截空跑
- **WHEN** runner / plugin 配置错误导致 `cmdb_result[<model_id>]` 为空
- **THEN** `assert len(instances) >= 1` 失败,test fail

#### Scenario: 字段对齐层拦截 mapping 漂移
- **WHEN** plugin field_mapping 改了某个字段名(例如 `version` → `app_version`)
- **THEN** `actual.get(field) == expected_value` 失败,test fail

### Requirement: inst_name 规则 `{ip}-{model_id}-{port}` 兜底校验

每个 fixture_driven 测试 MUST 断言最终实例的 `inst_name` 满足 `f"{ip_addr}-{model_id}-{port}"` 模式,避免 runner 重写 inst_name 规则后未被发现。

#### Scenario: inst_name 规则被破坏时 fail
- **WHEN** runner 的 `get_inst_name` 改了规则
- **THEN** `assert inst["inst_name"] == f"{ip_addr}-{model_id}-{port}"` 失败,test fail

### Requirement: fixture 数据源必须可追溯

每个 fixture 的 `04_expected_cmdb_result.json` MUST 在文件中声明 fixture 数据源(便于 review 时追溯):

- `fixture_source_end_to_end`:人造 raw 的来源(通常 `fixtures/<model_id>/01_raw_collector.json`)
- `fixture_source_fixture_driven`:stargazer cli 真实落盘的来源(通常 `agents/stargazer/tests/fixtures/collect/<model_id>.json`)

#### Scenario: 期望数据来源明确
- **WHEN** review `04_expected_cmdb_result.json`
- **THEN** `fixture_source_*` 字段清晰指出每个 expected_subset 用的是哪个 fixture

### Requirement: 测试运行无需真实 docker / 网络

fixture_driven 测试 MUST 在 `DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core` 环境下独立跑通,无需真实 docker / stargazer 容器 / 网络访问。

#### Scenario: 离线跑测试
- **WHEN** 开发者本地无 docker / 无网络
- **THEN** `pytest apps/cmdb/tests/e2e/test_<model_id>_pipeline.py::test_pipeline_fixture_driven` 仍能 passed(只用已落盘的 fixture + sqlite in-memory + monkeypatch)

### cmdb-e2e-cross-object-contract

## ADDED Requirements

### Requirement: 所有 fixture 必须满足公共契约

任何 `apps/cmdb/tests/e2e/fixtures/<model_id>/01_stargazer_raw.json` MUST 满足 `apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json` 中定义的公共契约。

#### Scenario: 公共契约必填字段
- **WHEN** 任意 fixture 被 `test_pipeline_fixture_driven` 加载
- **THEN** fixture MUST 包含 `model_id`(string,匹配文件夹名)、`captured_at`(ISO8601 string)、`raw_stdout`(object,含 `success: true` 和 `result: {<model_id>: [...]}`)

#### Scenario: 公共契约校验失败时 fail
- **WHEN** fixture 缺少 `raw_stdout.result.<model_id>` 字段
- **THEN** `jsonschema.validate(fixture, common_contract_schema)` 抛 `ValidationError`,test fail
- **THEN** 错误信息明确指出"公共契约违规:缺少 raw_stdout.result.<model_id>"

### Requirement: 公共契约由跨对象测试自动验证

`apps/cmdb/tests/e2e/test_common_contract.py` MUST 存在,自动遍历所有 `fixtures/*/01_stargazer_raw.json` 并验证公共契约。

#### Scenario: 跨对象公共契约测试
- **WHEN** 运行 `pytest apps/cmdb/tests/e2e/test_common_contract.py -v`
- **THEN** 测试自动发现所有真实落盘对象的 fixture(无需手动列举)
- **THEN** 每个 fixture 都通过公共契约 schema 校验

#### Scenario: 新增 fixture 立即被公共契约覆盖
- **WHEN** 团队成员新增 `fixtures/new_obj/01_stargazer_raw.json`
- **THEN** `test_common_contract.py` 自动覆盖,无需修改测试代码

### Requirement: 公共契约 schema 集中维护

`apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json` MUST 集中定义公共契约,且 SHALL NOT 在每个对象的 `01_stargazer_raw.schema.json` 中重复定义公共字段(用 `$ref` 引用)。

#### Scenario: 公共字段不重复
- **WHEN** 任意对象的 `01_stargazer_raw.schema.json` 需要定义 `model_id` / `captured_at` / `raw_stdout.success` / `raw_stdout.result`
- **THEN** MUST 用 `"$ref": "../00_common_contract.schema.json"` 引用,不在对象级 schema 重复

### Requirement: 公共契约不允许跨对象的 runner 行为假设

公共契约 MUST 只描述 fixture 数据形态(原始 JSON 结构),不假设任何 runner / plugin / extra_payload_keys 行为。

#### Scenario: 公共契约与 runner 解耦
- **WHEN** 公共契约 schema 校验通过
- **THEN** 不代表任何 runner 能消费该 fixture(runner 行为由对象级 e2e 测试验证)

### cmdb-e2e-runner-plugin-factory

## ADDED Requirements

### Requirement: 基于 model_id 自动选 runner / plugin / extra_payload_keys

`server/apps/cmdb/tests/e2e/conftest.py` MUST 提供 `load_runner_plugin_for_model_id(model_id)` fixture 或工厂函数,根据 model_id 返回 `(runner_cls, plugin_cls, extra_payload_keys)` 三元组。

#### Scenario: protocol 类对象(无 metric.result 解析)
- **WHEN** model_id 在 `{influxdb, mssql, ibmmq, ...}`(protocol 大类)中
- **THEN** `load_runner_plugin_for_model_id("influxdb")` 返回 `(ProtocolCollectMetrics, InfluxdbCollectionPlugin, None)`
- **THEN** `extra_payload_keys=None` 表示业务字段平铺到 labels

#### Scenario: db 类对象(平铺)
- **WHEN** model_id 在 `{mysql, postgresql, redis, mongodb, ...}`(db 大类)中
- **THEN** `load_runner_plugin_for_model_id("mysql")` 返回 `(DBCollectCollectMetrics, MysqlCollectionPlugin, None)`
- **THEN** `extra_payload_keys=None` 表示业务字段平铺到 labels

#### Scenario: middleware 类对象(metric.result JSON 编码)
- **WHEN** model_id 在 `{nginx, tomcat, rabbitmq, kafka, ...}`(middleware 大类)中
- **THEN** `load_runner_plugin_for_model_id("nginx")` 返回 `(MiddlewareCollectMetrics, NginxCollectionPlugin, {"result": True})`
- **THEN** `extra_payload_keys={"result": True}` 表示业务字段经 metric.result JSON 编码

### Requirement: 工厂函数覆盖所有 27 个真实落盘对象

`load_runner_plugin_for_model_id` MUST 覆盖 v3 阶段所有 27 个真实落盘对象(main 7 + worktree 20),否则抛 `KeyError` 并给出明确错误信息("model_id X 不在 factory 覆盖范围")。

#### Scenario: 未知 model_id 明确报错
- **WHEN** 调用 `load_runner_plugin_for_model_id("unknown_obj")`
- **THEN** 抛 `KeyError("unknown_obj")` 或工厂自定义异常,错误信息明确指出"未在 factory 覆盖范围,需先在 `apps/cmdb/collection/plugin_registry.py` 注册"

### Requirement: 工厂函数不引入新的 plugin 依赖

`load_runner_plugin_for_model_id` MUST 只 import 已经在 `apps/cmdb/collection/plugins/` 目录存在的 plugin 类,不引入新的依赖。

#### Scenario: 不引入新依赖
- **WHEN** 工厂被调用
- **THEN** 所有 import 路径在 `apps/cmdb/collection/plugins/{community,enterprise}/{protocol,db,middleware}/<model_id>.py` 范围
- **THEN** pyproject.toml / requirements.txt 不变

## Work Checklist

> 实施任务清单,按依赖顺序排列。每对象独立 commit,失败可单对象回滚。

## 1. 基础设施搭建(0.5d)

- [ ] 1.1 写 `server/apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json`(公共契约:必填 model_id / captured_at / raw_stdout 结构)
- [ ] 1.2 写 `server/apps/cmdb/tests/e2e/conftest.py::load_runner_plugin_for_model_id(model_id)` 工厂函数(覆盖 27 个对象,返回 (runner_cls, plugin_cls, extra_payload_keys) 三元组)
- [ ] 1.3 写 `server/apps/cmdb/tests/e2e/test_common_contract.py` 跨对象公共契约测试(用 `pytest.mark.parametrize` 显式列举 27 个 model_id,自动校验所有 fixture 满足公共契约)
- [ ] 1.4 写 `specs/capabilities/cmdb-e2e-authoring.md` 作者指南(5 步加新对象 e2e + 常见 expected_subset 模式 + 失败排查)

## 2. 参数化工厂模板(0.3d)

- [ ] 2.1 抽 `server/apps/cmdb/tests/e2e/test_pipeline_factory.py::test_pipeline_fixture_driven_via_factory` 参数化模板(基于 model_id 调工厂 + 三层验证 + inst_name 规则)
- [ ] 2.2 把 4 个现有对象(influxdb / mysql / nginx / redis)的 fixture 也加进工厂参数化列表,确认工厂版本跑通且**不破坏现有 test**
- [ ] 2.3 跑 `pytest apps/cmdb/tests/e2e/ -v`,确认 51+ tests 仍 passed

## 3. P0 批量(8 个对象 × 30 min ≈ 4h)

> 按"已落盘 + 业务高价值"排序。模板参考已存在的 4 个对象(每对象 5 步)

- [ ] 3.1 **postgresql** e2e — db runner 平铺,模板参考 mysql
- [ ] 3.2 **mongodb** e2e — db runner 平铺
- [ ] 3.3 **tomcat** e2e — middleware runner metric.result JSON,模板参考 nginx
- [ ] 3.4 **rabbitmq** e2e — middleware runner
- [ ] 3.5 **elasticsearch** e2e — protocol runner,模板参考 influxdb
- [ ] 3.6 **kafka** e2e — middleware runner
- [ ] 3.7 **zookeeper** e2e — middleware runner
- [ ] 3.8 **haproxy** e2e — middleware runner

## 4. P1 批量(8 个对象 × 30 min ≈ 4h)

- [ ] 4.1 **keepalived** e2e — middleware runner
- [ ] 4.2 **openresty** e2e — middleware runner
- [ ] 4.3 **apache** e2e — middleware runner
- [ ] 4.4 **activemq** e2e — middleware runner
- [ ] 4.5 **dameng** e2e — db runner(国产化优先)
- [ ] 4.6 **tongweb** e2e — middleware runner(国产化)
- [ ] 4.7 **minio** e2e — protocol runner
- [ ] 4.8 **consul** e2e — middleware runner

## 5. P2 批量(7 个对象 × 30 min ≈ 3.5h)

- [ ] 5.1 **etcd** e2e
- [ ] 5.2 **memcached** e2e
- [ ] 5.3 **squid** e2e
- [ ] 5.4 **rocketmq** e2e
- [ ] 5.5 **redis_sentinel** e2e
- [ ] 5.6 **jboss** e2e
- [ ] 5.7 **jetty** e2e

## 6. 验证 + 收尾(0.3d)

- [ ] 6.1 跑 `pytest apps/cmdb/tests/e2e/ -v` 全量(预计 ~100+ tests passed)
- [ ] 6.2 跑 `pytest apps/cmdb/tests/e2e/ --cov=apps/cmdb/tests/e2e --cov-report=term`,确认增量覆盖率 ≥ 75%
- [ ] 6.3 跑 `pre-commit run --all-files`(black / isort / flake8 / check_migrate)确认无格式问题
- [ ] 6.4 按 commit 粒度拆 commit(基础设施 1 个 / 工厂模板 1 个 / 每对象 1 个 / docs 1 个)
- [ ] 6.5 写 v4 收尾报告 `docs/superpowers/plans/2026-07-10-cmdb-collect-v4-phase1-execution-report.md`
- [ ] 6.6 跑 `openspec validate cmdb-collect-v4-e2e-platform` 确认仍 valid
- [ ] 6.7 在 `docs/superpowers/plans/2026-07-10-cmdb-collect-execution-roadmap.md` 追加 v4 章节 + 链接到本 OpenSpec change

## 验证标准汇总

- [ ] 27 个真实落盘对象 100% 有 fixture_driven e2e 测试
- [ ] 4 个对象现有 test 不破坏(51 passed 起步 → ~100+ passed 收尾)
- [ ] `pytest --cov` 增量覆盖率 ≥ 75%
- [ ] 跨对象公共契约测试自动发现新 fixture
- [ ] 作者指南 5 步模板可让新人 5 分钟上手
- [ ] OpenSpec 仍 valid
- [ ] commit 粒度可逐对象回滚

## 总工作量估算

| 阶段 | 时间 | 累计 |
|---|---|---|
| 1. 基础设施 | 0.5d | 0.5d |
| 2. 工厂模板 | 0.3d | 0.8d |
| 3. P0 批量 | 4h | 1.3d |
| 4. P1 批量 | 4h | 1.8d |
| 5. P2 批量 | 3.5h | 2.2d |
| 6. 验证收尾 | 0.3d | **2.5d** |

**总周期**:2.5 个工作日(对比调研报告的 1.5-2 人月估算,本 change 是 Phase 1 切片,聚焦"e2e 平台化"主线)
