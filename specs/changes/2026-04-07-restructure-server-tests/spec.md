# 2026 04 07 Restructure Server Tests

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-07-restructure-server-tests/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前 server 端几乎没有有效的测试体系——仅存 3 个分散的测试文件，pytest.ini 硬编码只跑 `apps/core/tests`（实际为空），覆盖率统计也仅针对 `apps/core`。缺少统一的测试规范、数据工厂、BDD 场景测试和覆盖率门禁，导致代码质量无法保障、重构风险高。

## What Changes

- **删除所有现有测试文件**：移除 `apps/monitor/tests/`、`apps/system_mgmt/tests/` 下的旧测试，从零开始建立规范化测试体系
- **重建 pytest 基础设施**：重写 `pytest.ini`，配置全局 marker（unit/integration/bdd）、测试发现路径、覆盖率统计
- **引入新测试依赖**：添加 `factory-boy`、`faker`、`pytest-bdd` 到 dev dependencies
- **建立三层测试金字塔**：Unit (TDD) → Integration → BDD，定义标准目录结构
- **以 `apps/base` 为试点**：为 User 模型、UserAPISecret CRUD 全流程编写完整的三层测试
- **配置覆盖率报告**：`.coveragerc` 覆盖所有 apps，输出 terminal + HTML 报告，设置最低覆盖率门禁
- **建立根级 conftest.py**：提供全局 fixtures（DB 配置、cache mock、认证用户等）

## Capabilities

### New Capabilities

- `test-infrastructure`: pytest 全局配置、marker 定义、根级 conftest.py、.coveragerc 覆盖率配置、新依赖引入
- `test-base-app`: apps/base 完整三层测试——Unit Tests (models, serializers)、Integration Tests (API views)、BDD Tests (Gherkin feature 场景)
- `test-conventions`: 测试目录结构规范、命名约定、Factory 模式、fixture 分层策略，作为后续 app 推广的模板

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **配置文件**: `pytest.ini`、`.coveragerc`、`pyproject.toml`（dev dependencies）
- **删除文件**: `apps/monitor/tests/test_alert_name_template.py`、`apps/system_mgmt/tests/nats_api_test.py`、`apps/system_mgmt/tests/conftest.py`
- **新增文件**: `conftest.py`（根级）、`apps/base/tests/` 整个测试目录树
- **依赖变更**: 新增 `factory-boy`、`faker`、`pytest-bdd`、`pytest-factoryboy`
- **CI 影响**: Makefile 的 `test` target 行为会变化，覆盖率报告路径从 `coverage_html/` 改为 `htmlcov/`

## Implementation Decisions

## Context

BK-Lite server 是一个 Django 4.2 + DRF 项目，使用 split_settings 管理配置，支持多种数据库后端（PostgreSQL、MySQL、SQLite 等）。当前测试基础设施名存实亡：`pytest.ini` 只指向空的 `apps/core/tests`，散落的 3 个测试文件缺乏统一规范。

项目已安装 `pytest-django`、`pytest-cov`、`pytest-mock`、`pytest-asyncio` 等核心插件，但缺少数据工厂（factory-boy）和 BDD（pytest-bdd）支持。

`apps/base` 包含 `User`（自定义 AbstractUser）和 `UserAPISecret`（API 密钥管理）两个模型，以及一个完整的 DRF ViewSet，有权限装饰器、Cookie 解析、序列化器上下文依赖等典型测试场景，适合作为试点。

## Goals / Non-Goals

**Goals:**
- 建立可复用的 pytest 三层测试架构（Unit / Integration / BDD）
- 为 `apps/base` 编写完整测试，覆盖率 ≥ 90%
- 配置全局覆盖率报告（terminal + HTML），设置最低覆盖率门禁
- 形成标准化测试模板，供后续 app 推广使用

**Non-Goals:**
- 不在本次为其他 app（cmdb、job_mgmt、monitor 等）编写测试
- 不改动业务代码（纯测试侧变更）
- 不配置 CI/CD pipeline（本次只关注本地测试体系）
- 不引入 end-to-end 浏览器测试

## Decisions

### 1. 测试框架选择：pytest-bdd vs behave

**选择**: pytest-bdd

**理由**: 项目已完全使用 pytest 生态，pytest-bdd 可以复用所有现有 fixtures 和 plugins，无需维护两套测试运行器。behave 虽然更纯粹但需要独立运行，与 pytest-cov 等插件集成困难。

### 2. 数据工厂：factory-boy + faker

**选择**: factory-boy 作为主工厂，faker 提供随机数据

**理由**: factory-boy 是 Django 生态的事实标准，与 pytest-django 集成良好。相比手动 `Model.objects.create()`，factory 可以只声明测试关注的字段，其余自动填充，减少测试噪音。

**替代方案**: model-bakery——更轻量但定制性不足，不适合需要精确控制的场景。

### 3. 测试目录结构：app 内分层 vs 顶层 tests 目录

**选择**: 每个 app 内 `tests/` 目录，按 unit/integration/bdd 分层

**理由**: 测试与被测代码同位置，便于定位和维护。通过 pytest markers 实现按层运行（`pytest -m unit` 只跑单元测试）。

```
apps/<app>/tests/
├── conftest.py          # app 级 fixtures + factories
├── factories.py         # Factory Boy 工厂
├── unit/                # @pytest.mark.unit
├── integration/         # @pytest.mark.integration
└── bdd/                 # @pytest.mark.bdd
    ├── features/*.feature
    └── step_defs/test_*.py
```

### 4. 测试数据库策略

**选择**: 使用 pytest-django 默认的 transaction rollback + SQLite in-memory

**理由**: 单元测试和集成测试都在事务中运行并自动回滚，无需手动清理。本地开发可选 `--reuse-db` 加速。pytest.ini 中不再硬编码 `--reuse-db`，由开发者按需传入。

### 5. 权限装饰器测试策略

**选择**: 双层测试

- **Unit tests**: Mock 掉 `@HasPermission` 装饰器，只测 ViewSet 业务逻辑
- **Integration tests**: 构造真实带权限的 User，验证完整权限链路

**理由**: 分离关注点。单元测试验证"逻辑对不对"，集成测试验证"权限通不通"。

### 6. Serializer 上下文依赖处理

`UserAPISecretSerializer.__init__()` 直接访问 `self.context["request"].user.group_list`，无法脱离 request 上下文实例化。

**选择**: Unit test 中通过 `RequestFactory` + mock user 构造完整 context

### 7. BDD Feature 粒度

**选择**: 每个业务领域一个 .feature 文件，每个用户故事一个 Scenario

**理由**: .feature 文件是给人读的"活文档"，粒度过细会变成代码的翻译，失去沟通价值。

### 8. 覆盖率配置

**选择**:
- `--cov=apps` 覆盖所有 app
- `--cov-report=term-missing` 终端显示未覆盖行号
- `--cov-report=html:htmlcov` HTML 详细报告
- `.coveragerc` 中 `fail_under = 60`（初始门禁，逐步提高）
- 排除 migrations、admin.py、`__init__.py`

## Risks / Trade-offs

- **[Risk] SQLite 与 PostgreSQL 行为差异** → 仅影响数据库特定功能（如 JSONField 查询），base app 的测试场景不涉及。后续 app 如需 PG 特性可单独配置 test database。
- **[Risk] 删除旧测试丢失知识** → 旧测试仅 3 个文件且质量不高，迁移价值低于从零编写规范化测试的收益。
- **[Risk] pytest-bdd 的 feature 文件维护成本** → 只在 API 行为层面写 BDD，不下沉到内部实现。控制 feature 文件数量。
- **[Trade-off] `fail_under = 60` 门禁较低** → 初始值故意保守，避免引入测试体系时就因门禁过高阻塞开发。随着测试逐步补充再提高。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-07
```

## Capability Deltas

### test-base-app

## ADDED Requirements

### Requirement: User 模型 Factory
系统 SHALL 提供 `UserFactory`，基于 factory-boy 创建 `apps.base.models.User` 测试实例。

#### Scenario: 默认 User 创建
- **WHEN** 调用 `UserFactory()`
- **THEN** SHALL 创建一个 User，包含随机 username、默认 domain="domain.com"、空 group_list 和 roles

#### Scenario: 自定义字段
- **WHEN** 调用 `UserFactory(locale="en", roles=["admin"])`
- **THEN** SHALL 创建 User 并覆盖指定字段值

### Requirement: UserAPISecret 模型 Factory
系统 SHALL 提供 `UserAPISecretFactory`，基于 factory-boy 创建 `UserAPISecret` 测试实例。

#### Scenario: 默认 UserAPISecret 创建
- **WHEN** 调用 `UserAPISecretFactory()`
- **THEN** SHALL 创建一个 UserAPISecret，包含随机 username、有效 api_secret（64字符 hex）、team=0

#### Scenario: 关联用户创建
- **WHEN** 调用 `UserAPISecretFactory(username="alice", domain="test.com", team=1)`
- **THEN** SHALL 创建对应字段值的 UserAPISecret

### Requirement: generate_api_secret 单元测试
UserAPISecret.generate_api_secret() 的行为 SHALL 被完整测试。

#### Scenario: 返回格式
- **WHEN** 调用 `UserAPISecret.generate_api_secret()`
- **THEN** SHALL 返回一个 64 字符的十六进制字符串

#### Scenario: 唯一性
- **WHEN** 连续调用两次 `UserAPISecret.generate_api_secret()`
- **THEN** 两次返回值 SHALL 不同

### Requirement: User 模型约束测试

#### Scenario: unique_together 约束
- **WHEN** 创建两个 username 和 domain 都相同的 User
- **THEN** 第二次创建 SHALL 引发 IntegrityError

### Requirement: UserAPISecret 模型约束测试

#### Scenario: unique_together 约束
- **WHEN** 创建两个 username、domain、team 都相同的 UserAPISecret
- **THEN** 第二次创建 SHALL 引发 IntegrityError

### Requirement: UserAPISecretSerializer 序列化测试

#### Scenario: team_name 解析
- **WHEN** 序列化一个 team=1 的 UserAPISecret，且 request.user.group_list 包含 `{"id": 1, "name": "Team A"}`
- **THEN** 序列化输出 SHALL 包含 `team_name: "Team A"`

#### Scenario: team_name 找不到匹配
- **WHEN** 序列化一个 team=999 的 UserAPISecret，且 group_list 中无对应 id
- **THEN** team_name SHALL 返回 team 的数值（999）

### Requirement: _parse_current_team 工具函数测试

#### Scenario: 有效整数 cookie
- **WHEN** request.COOKIES["current_team"] = "5"
- **THEN** SHALL 返回 `(5, None)`

#### Scenario: 无效 cookie 值
- **WHEN** request.COOKIES["current_team"] = "abc"
- **THEN** SHALL 返回 `(None, JsonResponse)` 且 JsonResponse 状态码为 400

#### Scenario: 缺失 cookie
- **WHEN** request.COOKIES 中无 current_team
- **THEN** SHALL 返回 `(0, None)`（默认值为 "0"）

### Requirement: API Secret 列表接口测试

#### Scenario: 认证用户查看自己的 secrets
- **WHEN** 用户 "alice"（team=1）发起 GET /user_api_secret/
- **THEN** SHALL 仅返回属于 "alice" 且 team=1 的 secrets

#### Scenario: 不同用户数据隔离
- **WHEN** "alice" 和 "bob" 各有 secrets，"alice" 发起 GET 请求
- **THEN** SHALL 不包含 "bob" 的 secrets

#### Scenario: 未认证用户
- **WHEN** 未认证用户发起 GET /user_api_secret/
- **THEN** SHALL 返回 401 或 403

### Requirement: API Secret 创建接口测试

#### Scenario: 成功创建
- **WHEN** 认证用户 POST /user_api_secret/，且该用户在当前 team 下没有 secret
- **THEN** SHALL 返回 201，响应包含生成的 api_secret

#### Scenario: 重复创建被拒绝
- **WHEN** 用户已有 secret，再次 POST 创建
- **THEN** SHALL 返回 `result: false` 和"已存在"提示

#### Scenario: 无效 current_team cookie
- **WHEN** POST 请求的 current_team cookie 为 "abc"
- **THEN** SHALL 返回 400 错误

### Requirement: API Secret 删除接口测试

#### Scenario: 成功删除
- **WHEN** 认证用户 DELETE /user_api_secret/{id}/
- **THEN** SHALL 返回 204，数据库中该记录被删除

### Requirement: API Secret 更新被禁止

#### Scenario: PUT 请求被拒绝
- **WHEN** 发起 PUT /user_api_secret/{id}/
- **THEN** SHALL 返回 `result: false` 和"不支持修改"消息

### Requirement: generate_api_secret action 测试

#### Scenario: 生成新密钥
- **WHEN** POST /user_api_secret/generate_api_secret/
- **THEN** SHALL 返回 `result: true` 和一个 64 字符 hex 的 api_secret

### Requirement: BDD 场景 — API Secret 管理全流程

#### Scenario: 完整生命周期
- **WHEN** 用户创建 API Secret，然后查看列表，最后删除
- **THEN** 创建返回 201，列表包含该 secret，删除返回 204，再次列表为空

#### Scenario: 多团队隔离
- **WHEN** 同一用户在 team=1 和 team=2 分别创建 secret
- **THEN** 切换 current_team cookie 后，列表 SHALL 只显示对应 team 的 secret

### test-conventions

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

### test-infrastructure

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

## Work Checklist

## 1. 清理旧测试

- [x] 1.1 删除 `apps/monitor/tests/test_alert_name_template.py`
- [x] 1.2 删除 `apps/system_mgmt/tests/nats_api_test.py` 和 `apps/system_mgmt/tests/conftest.py`
- [x] 1.3 清理 `apps/core/tests/__init__.py`（删除空的 tests 目录或保留空 `__init__.py` 供后续使用）

## 2. 添加测试依赖

- [x] 2.1 在 `pyproject.toml` 的 `[project.optional-dependencies.dev]` 中添加 `factory-boy`、`faker`、`pytest-bdd`
- [x] 2.2 执行 `uv sync --extra dev` 验证依赖安装成功

## 3. 重写 pytest 全局配置

- [x] 3.1 重写 `pytest.ini`：testpaths 改为 `apps/`，添加 strict markers（unit/integration/bdd/slow），移除硬编码的 `--reuse-db` 和 `--html`，配置 `--cov=apps`
- [x] 3.2 重写 `.coveragerc`：source 设为 `apps`，omit 排除 tests/migrations/admin.py/__init__.py，设置 `fail_under = 60`，`show_missing = true`
- [x] 3.3 删除旧的 `report.html` 和 `coverage_html/` 输出（如存在），将 `htmlcov/` 加入 `.gitignore`

## 4. 创建根级 conftest.py

- [x] 4.1 在 `server/conftest.py` 中创建 `use_dummy_cache_backend` fixture（autouse），将 Django cache 替换为 DummyCache
- [x] 4.2 创建 `authenticated_user` fixture，返回带有默认 group_list、roles、locale、domain 的 User 实例
- [x] 4.3 创建 `api_client` fixture，返回已认证的 DRF APIClient

## 5. 创建 apps/base 测试目录结构

- [x] 5.1 创建目录结构：`apps/base/tests/{__init__.py, conftest.py, factories.py, unit/__init__.py, integration/__init__.py, bdd/__init__.py, bdd/features/, bdd/step_defs/__init__.py}`
- [x] 5.2 在 `factories.py` 中编写 `UserFactory` 和 `UserAPISecretFactory`（使用 factory-boy + faker）

## 6. 编写 Unit Tests

- [x] 6.1 `apps/base/tests/unit/test_models.py`：测试 `UserAPISecret.generate_api_secret()` 返回格式和唯一性
- [x] 6.2 `apps/base/tests/unit/test_models.py`：测试 User 和 UserAPISecret 的 `unique_together` 约束
- [x] 6.3 `apps/base/tests/unit/test_serializers.py`：测试 `UserAPISecretSerializer` 的 `team_name` 解析逻辑
- [x] 6.4 `apps/base/tests/unit/test_views.py`：测试 `_parse_current_team()` 工具函数（有效值、无效值、缺失值）

## 7. 编写 Integration Tests

- [x] 7.1 `apps/base/tests/integration/test_views.py`：测试 GET /user_api_secret/ 列表接口（数据隔离、未认证拒绝）
- [x] 7.2 测试 POST /user_api_secret/ 创建接口（成功创建、重复创建拒绝、无效 cookie）
- [x] 7.3 测试 DELETE /user_api_secret/{id}/ 删除接口
- [x] 7.4 测试 PUT /user_api_secret/{id}/ 更新被拒绝
- [x] 7.5 测试 POST /user_api_secret/generate_api_secret/ action

## 8. 编写 BDD Tests

- [x] 8.1 创建 `apps/base/tests/bdd/features/api_secret_management.feature`：API Secret 管理全流程场景（创建、查看、删除、重复创建、多团队隔离）
- [x] 8.2 创建 `apps/base/tests/bdd/step_defs/test_api_secret_steps.py`：实现 feature 文件中所有 step 定义
- [x] 8.3 在 `apps/base/tests/bdd/step_defs/conftest.py` 中配置 BDD 专用 fixtures

## 9. 验证与覆盖率

- [x] 9.1 执行 `pytest apps/base/` 确认所有测试通过
- [x] 9.2 执行 `pytest -m unit` / `pytest -m integration` / `pytest -m bdd` 确认 marker 筛选正常
- [x] 9.3 检查覆盖率报告：`apps/base/` 相关文件覆盖率 ≥ 90%
- [x] 9.4 检查 `htmlcov/index.html` 可正常打开
