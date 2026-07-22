## ADDED Requirements

### Requirement: pytest 全局配置
系统 SHALL 提供统一的 pytest 配置文件（`pytest.ini`），自动发现所有 `apps/` 下的测试文件。

#### Scenario: 自动发现所有 app 测试
- **WHEN** 在 server 目录执行 `pytest`
- **THEN** pytest SHALL 递归扫描 `apps/` 目录下所有 `test_*.py` 文件

#### Scenario: 支持按 marker 筛选测试
- **WHEN** 执行 `pytest -m unit`
- **THEN** 仅运行标记为 `@pytest.mark.unit` 的测试

#### Scenario: 支持 marker 组合
- **WHEN** 执行 `pytest -m "not slow"`
- **THEN** 排除标记为 `@pytest.mark.slow` 的测试

### Requirement: 覆盖率报告配置
系统 SHALL 配置 pytest-cov 生成测试覆盖率报告，覆盖所有 apps 目录。

#### Scenario: 终端覆盖率输出
- **WHEN** 执行 `pytest`
- **THEN** 终端 SHALL 显示每个文件的覆盖率百分比和未覆盖行号

#### Scenario: HTML 覆盖率报告
- **WHEN** 执行 `pytest`
- **THEN** SHALL 在 `htmlcov/` 目录生成 HTML 格式的覆盖率报告

#### Scenario: 覆盖率门禁
- **WHEN** 总体覆盖率低于 60%
- **THEN** pytest SHALL 返回非零退出码（测试失败）

#### Scenario: 覆盖率排除规则
- **WHEN** 计算覆盖率时
- **THEN** SHALL 排除 migrations、admin.py、`__init__.py`、tests 目录自身

### Requirement: Marker 定义
`pytest.ini` SHALL 定义以下 strict markers：`unit`、`integration`、`bdd`、`slow`。

#### Scenario: 未注册 marker 报错
- **WHEN** 测试使用了未在 `pytest.ini` 中注册的 marker
- **THEN** pytest SHALL 报错（`--strict-markers`）

### Requirement: 根级 conftest.py
server 根目录 SHALL 提供 `conftest.py`，包含全局共享的 test fixtures。

#### Scenario: DummyCache fixture
- **WHEN** 任意测试运行时
- **THEN** Django cache backend SHALL 被替换为 DummyCache（autouse）

#### Scenario: 认证用户 fixture
- **WHEN** 测试需要一个已认证的用户
- **THEN** SHALL 提供 `authenticated_user` fixture，返回一个带有默认 group_list、roles、domain 的 User 实例

#### Scenario: API Client fixture
- **WHEN** 测试需要发起 HTTP 请求
- **THEN** SHALL 提供 `api_client` fixture，返回已认证的 DRF `APIClient`

### Requirement: 新测试依赖
`pyproject.toml` 的 dev dependencies SHALL 包含 `factory-boy`、`faker`、`pytest-bdd`。

#### Scenario: 依赖安装
- **WHEN** 执行 `uv sync --extra dev`
- **THEN** factory-boy、faker、pytest-bdd SHALL 被安装
