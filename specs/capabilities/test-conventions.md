## ADDED Requirements

### Requirement: 标准测试目录结构
每个 app 的测试 SHALL 遵循统一的目录结构。

#### Scenario: 目录布局
- **WHEN** 查看 `apps/<app>/tests/` 目录
- **THEN** SHALL 包含以下结构：`conftest.py`、`factories.py`、`unit/`、`integration/`、`bdd/`（按需）

### Requirement: 测试文件命名约定
测试文件 SHALL 使用 `test_*.py` 命名格式。

#### Scenario: 文件名匹配
- **WHEN** 创建新的测试文件
- **THEN** SHALL 以 `test_` 前缀命名（如 `test_models.py`、`test_views.py`）

### Requirement: 测试类命名约定
测试类 SHALL 使用 `Test*` 命名格式，按被测对象分组。

#### Scenario: 模型测试类
- **WHEN** 测试 User 模型
- **THEN** 测试类 SHALL 命名为 `TestUserModel`

#### Scenario: 视图测试类
- **WHEN** 测试 UserAPISecretViewSet
- **THEN** 测试类 SHALL 命名为 `TestUserAPISecretViewSet`

### Requirement: Factory 模式规范
每个 app 的 factories.py SHALL 为该 app 的所有模型提供 Factory 类。

#### Scenario: Factory 注册
- **WHEN** `apps/<app>/tests/factories.py` 被创建
- **THEN** SHALL 为每个 model 定义一个对应的 `*Factory` 类，继承自 `factory.django.DjangoModelFactory`

#### Scenario: Factory 默认值
- **WHEN** Factory 被调用且不传参数
- **THEN** SHALL 生成所有必填字段的合理默认值，使用 `faker` 提供随机数据

### Requirement: Fixture 分层策略
Fixtures SHALL 按作用域分层：根级（全局）→ app 级 → test 级。

#### Scenario: 根级 fixture
- **WHEN** conftest.py 位于 server/ 根目录
- **THEN** SHALL 提供跨 app 共享的 fixtures（如 cache mock、authenticated_user）

#### Scenario: app 级 fixture
- **WHEN** conftest.py 位于 `apps/<app>/tests/` 目录
- **THEN** SHALL 提供该 app 特定的 fixtures（如 api_client with permissions）

### Requirement: Marker 使用规范
所有测试 SHALL 标记对应的 marker。

#### Scenario: Unit test marker
- **WHEN** 测试不需要数据库且无外部依赖
- **THEN** SHALL 标记 `@pytest.mark.unit`

#### Scenario: Integration test marker
- **WHEN** 测试涉及数据库操作或 HTTP 请求
- **THEN** SHALL 标记 `@pytest.mark.integration` 和 `@pytest.mark.django_db`

#### Scenario: BDD test marker
- **WHEN** 测试基于 .feature 文件
- **THEN** SHALL 标记 `@pytest.mark.bdd` 和 `@pytest.mark.django_db`

### Requirement: BDD Feature 文件规范
.feature 文件 SHALL 使用中文编写（与项目注释语言一致），放在 `bdd/features/` 目录。

#### Scenario: Feature 文件位置
- **WHEN** 创建 BDD 测试
- **THEN** .feature 文件 SHALL 放在 `apps/<app>/tests/bdd/features/` 目录

#### Scenario: Step 定义位置
- **WHEN** 创建 BDD step 实现
- **THEN** step 定义文件 SHALL 放在 `apps/<app>/tests/bdd/step_defs/` 目录，命名为 `test_*.py`
