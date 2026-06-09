# BK-Lite Server 测试开发规范（TDD / BDD）

本文是 `server/`（Django 后端）的统一测试规范，约定**目录结构、命名、测试分层、BDD 写法与运行方式**。
新增测试一律遵循本规范；存量测试在改动相关代码时顺手迁移到本规范。

技术栈：`pytest` + `pytest-django` + `pytest-bdd` + `factory_boy`。

---

## 1. 快速开始

```bash
cd server
make install                      # 安装依赖（含 pytest-bdd / factory-boy，均在 dev 组）

# 运行全部测试（默认扫描 apps/，带覆盖率）
make test                         # 等价于 uv run pytest

# 运行单个 app / 单个文件 / 单个用例
uv run pytest apps/cmdb/tests
uv run pytest apps/cmdb/tests/test_models.py -v
uv run pytest apps/cmdb/tests/test_models.py::TestModel::test_create -v

# 按 marker 过滤
uv run pytest -m unit             # 只跑纯单元
uv run pytest -m "not slow"       # CI 快速通道：跳过慢用例
uv run pytest -m bdd              # 只跑 BDD

# 调试时临时关掉覆盖率统计，输出更干净
uv run pytest apps/cmdb/tests/bdd/ --no-cov
```

常用 Make 快捷命令（见 `server/Makefile`）：

```bash
make test                # 全量
make test-app APP=cmdb   # 只跑某个 app
make test-unit           # -m unit
make test-bdd            # -m bdd
make test-fast           # -m "not slow"（CI 快速通道）
make test-debug APP=cmdb # 关覆盖率，输出更干净
make test-reset          # --create-db，改了 migration 后重建测试库
```

> 需要数据库的用例依赖 `DB_*` 环境变量（默认 PostgreSQL）。本地没有库时，仅 `@pytest.mark.unit`
> 这类不碰 DB / IO 的用例可独立运行。

### 本地测试数据库

DB 相关用例必须连 **PostgreSQL**：项目历史 migration 含 `RemoveField`/`AlterUniqueTogether`
等操作，SQLite 的“整表重建”语义无法从零构建测试库（生产用 PostgreSQL 增量迁移不受影响，
**不要为此改动 migration**）。本地用 Docker 一次性测试库即可：

```bash
make test-db-up      # 启动 Docker PostgreSQL(localhost:55432)
make test-db         # 连测试库跑全部用例
make test-db-down    # 用完销毁

# 跑单个 app（需先 test-db-up）：
DB_ENGINE=postgresql DB_NAME=bklite DB_USER=postgres DB_PASSWORD=testpass \
  DB_HOST=localhost DB_PORT=55432 uv run pytest apps/console_mgmt/tests --reuse-db
```

> 接口返回经全局封装为 `{"code","data","message","result"}`，**列表数据在 `data` 字段**；
> 写接口断言 `result` / 状态码。写视图测试时勿直接把 `resp.json()` 当作列表。

---

## 2. 标准目录结构（单一约定）

每个 app 的测试统一放在 `apps/<app>/tests/`（**复数 `tests`**，不要用 `test`）：

```
apps/<app>/tests/
  __init__.py
  conftest.py                 # app 级 fixtures / fakes（如 FakeGraphClient）
  factories.py                # factory_boy 工厂（推荐，见 apps/base/tests/factories.py）
  test_<x>_pure.py            # 纯单元：无 DB / 无外部 IO
  test_<x>_service.py         # service 层：mock 掉外部依赖
  test_<x>_views.py           # DRF 接口层：用 api_client 走 HTTP
  bdd/
    __init__.py
    conftest.py               # BDD 专用 fixtures（如 bdd_user / bdd_client）
    <feature>.feature         # 中文 Gherkin，与步骤文件同层
    test_<feature>_bdd.py     # scenarios(FEATURE) 一次性绑定整个 feature
```

**约定要点：**
- 测试目录名一律 `tests/`（历史上的 `alerts/test/` 已迁移）。
- BDD 采用**扁平式**：`feature` 与 `test_*_bdd.py` 同层，不再用 `features/` + `step_defs/` 分层。
- 文件名遵守 `pytest.ini` 的发现规则：`test_*.py`，类 `Test*`，函数 `test_*`。

---

## 3. 测试分层（测试金字塔）

按依赖范围从轻到重分三层，文件名后缀即层次标识：

| 后缀 | 层次 | 是否碰 DB/IO | 典型做法 |
|---|---|---|---|
| `_pure` | 纯单元 | 否 | 直接调用纯函数 / 算法 / 校验器，零 mock 或极少 mock |
| `_service` | 服务层 | 视情况 | 测 service 编排逻辑，外部依赖（图库、NATS、第三方）用 Fake/mock 替换 |
| `_views` | 接口层 | 是 | 用 `api_client` 走 DRF 路由，断言状态码与响应体 |

写新功能时优先按 **TDD 红-绿-重构** 推进：先写失败的测试（通常从 `_pure` 或 `_service` 起步），
再写实现让其变绿，最后重构。能在纯单元层覆盖的逻辑就不要下沉到接口层——金字塔越往下越慢越脆。

### 根级共享 fixtures（`server/conftest.py`）

所有测试可直接使用：
- `authenticated_user` — 创建带默认团队/角色的 `base.User`
- `api_client` — 已 `force_authenticate` 的 DRF `APIClient`
- `request_factory` — Django `RequestFactory`
- 另有 autouse fixture：测试期自动把缓存换成 `DummyCache`、移除自定义鉴权中间件（让 `force_authenticate` 生效）。

### 测试数据：factory_boy

优先用 `factory_boy` 工厂造数据，而不是手写 `Model.objects.create(...)`。范例见
`apps/base/tests/factories.py`（`UserFactory` / `UserAPISecretFactory`）。

---

## 4. BDD 规范（pytest-bdd，中文 Gherkin）

### 4.1 feature 文件

- 放在 `apps/<app>/tests/bdd/<feature>.feature`。
- 用**中文 Gherkin**：关键字 `功能 / 背景 / 场景 / 假设 / 当 / 那么 / 并且`。
  使用中文场景关键字时，文件首行加 `# language: zh-CN`；若沿用英文关键字（`Feature/Scenario`）配中文描述也可，保持单个文件内一致即可。
- 每个 feature 建议覆盖 **happy path + corner cases**（参照 cmdb 的「3 happy + 5 corner」惯例）。

示例（摘自 `apps/cmdb/tests/bdd/model_management.feature`）：

```gherkin
# language: zh-CN
功能: CMDB 模型管理（分类 + 模型）
  作为 CMDB 管理员
  为了维护资产模型的分类树和模型本身
  ClassificationManage / ModelManage 必须正确写入图库、维护引用完整性

  背景:
    假设 图库可以被 FakeGraphClient 替换

  场景: 正常路径 - 新建模型分类成功落库
    当 管理员创建模型分类 classification_id="biz" classification_name="业务"
    那么 应当对图库 "classification" 执行 1 次 create_entity
    并且 返回的分类应包含 classification_id="biz"
```

### 4.2 步骤定义文件

- 文件名 `test_<feature>_bdd.py`，与 feature 同层。
- **统一用 `scenarios(FEATURE)` 一次性绑定整个 feature**，不要逐个写 `@scenario` 装饰器。
- 用一个可变的 `ctx` fixture 在 `given/when/then` 之间传递状态。
- 步骤实现里复用 `conftest.py` 的 Fake / Factory。

骨架：

```python
from pathlib import Path

import pytest
from pytest_bdd import given, when, then, parsers, scenarios

FEATURE = str(Path(__file__).parent / "model_management.feature")
scenarios(FEATURE)            # 绑定整个 feature 的所有场景


@pytest.fixture
def ctx():
    """在同一场景的各步骤间共享的可变上下文。"""
    return {}


@given(parsers.parse('图库中已存在分类记录 _id={id:d}'), target_fixture="ctx")
def given_existing(ctx, id):
    ...

@when(parsers.parse('管理员创建模型分类 classification_id="{cid}"'))
def when_create(ctx, cid):
    ...

@then(parsers.parse('应当对图库 "{entity}" 执行 {n:d} 次 create_entity'))
def then_called(ctx, entity, n):
    ...
```

### 4.3 标记

BDD 用例统一打 `@pytest.mark.bdd`（可加在 `scenarios()` 所在模块或通过 `pytestmark = pytest.mark.bdd`）。
需要 DB 的场景加 `@pytest.mark.django_db` 或依赖 `db` fixture。

---

## 5. 配置说明（`pytest.ini`）

关键项：

- `testpaths = apps` — 不带参数时扫描全部 app（运行单个 app 直接 `pytest apps/<app>/tests`）。
- `markers` — 已注册 `unit / integration / bdd / slow`，使用未注册 marker 会告警。
- `--cov=apps` — 覆盖率统计全部 app（此前仅统计 `apps/core`）。
- `--reuse-db` — 复用测试库，加速重复运行；改了 migration 后用 `--create-db` 重建。
- `asyncio_mode = auto` — 异步用例无需手动加 `@pytest.mark.asyncio`。

---

## 6. 编写测试的检查清单

- [ ] 放在 `apps/<app>/tests/` 下，文件名 `test_*.py`。
- [ ] 选对层次后缀（`_pure` / `_service` / `_views`），能上浮就不下沉。
- [ ] 用 `factory_boy` 造数据，复用根级 `api_client` / `authenticated_user`。
- [ ] 外部依赖（图库 / NATS / 第三方 / MinIO）用 Fake 或 mock 隔离。
- [ ] BDD 用扁平式 `scenarios(FEATURE)` + 中文 Gherkin，覆盖 happy + corner。
- [ ] 打上正确的 marker（`unit` / `integration` / `bdd` / `slow`）。
- [ ] 本地 `uv run pytest <你的路径>` 跑通后再提交。
