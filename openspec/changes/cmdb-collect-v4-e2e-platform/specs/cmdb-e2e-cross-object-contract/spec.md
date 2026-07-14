# Spec: cmdb-e2e-cross-object-contract

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