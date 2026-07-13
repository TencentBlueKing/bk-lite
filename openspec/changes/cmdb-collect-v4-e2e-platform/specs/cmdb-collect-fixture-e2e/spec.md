# Spec: cmdb-collect-fixture-e2e

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