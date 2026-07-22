# Historical Superpowers change: 2026-06-09-cmdb-enterprise-sibling-app

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-09-cmdb-enterprise-sibling-app.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CMDB 商业版从嵌套 `apps/cmdb/enterprise/` 重构为同级 overlay app `apps/cmdb_enterprise/`，社区 cmdb 通过注册表（IoC）与之解耦到「互不 import」，商业 app 自带 models/migrations/tasks/beat/urls。

**Architecture:** 社区 cmdb 定义「通用注册表 + 各域默认空契约 + 调用点」，零企业知识；商业 app 在 `AppConfig.ready()` 把实现注册进社区注册表；模型/任务/beat/URL 全靠 Django/Celery 自动发现。商业 app 被 `.gitignore` 忽略（overlay，对齐 `license_mgmt`），目录存在即由现有 `apps/` 扫描自动加载。

**Tech Stack:** Python 3.12 / Django / DRF / Celery / pytest（`uv run pytest`，`testpaths=apps`）。

**前置事实（实施前必读）：**
- `apps/cmdb/enterprise/` 与目标 `apps/cmdb_enterprise/` 均被 `.gitignore` 忽略 → 这些目录里的文件**不进 git**。提交步骤只 stage 社区 cmdb 的改动（含被删除的社区文件）。移动 overlay 文件用普通 `mv`（非 `git mv`）。
- `enterprise/` 当前含：`instance_ops/`（附件/图片）、`model_ops/`、`collect/`（达梦）、`beat.py`、`bootstrap.py`、`tasks/`。**不含** custom_reporting 的企业行为（`CustomReportingModelService` 等由 overlay 单独交付，不在本仓 checkout）。
- custom_reporting 现状：社区有 fallback 模型 `models/custom_reporting.py`（6 模型）+ 迁移 `0024_custom_reporting.py` + 壳文件（views/serializers/services）；`services/model.py:565-643` 的 7 个方法**裸惰性导入**不存在的企业服务。
- 无生产数据前提：删社区 `0024_*` 迁移后，本地 dev 库需 `DROP` 旧表 / 重置（下文给命令）。

**执行约定：** 每个测试先看它失败再实现（TDD）。社区改动频繁提交。overlay（`cmdb_enterprise/`、`enterprise/`）文件不提交。每个 Task 末尾的 `git add` 只列社区路径。

---

## Phase 0：社区注册表基建（不动 overlay，纯社区 TDD）

### Task 0.1：通用注册表

**Files:**
- Create: `server/apps/cmdb/extensions/registry.py`
- Test: `server/apps/cmdb/tests/test_extensions_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# server/apps/cmdb/tests/test_extensions_registry.py
"""社区扩展注册表纯单测（IoC：社区定义槽位，谁注册由调用方决定）。"""

from apps.cmdb.extensions import registry


def test_get_returns_default_when_unregistered():
    assert registry.get("nonexistent_slot", "fallback") == "fallback"


def test_register_then_get():
    sentinel = object()
    registry.register("demo_slot", sentinel)
    assert registry.get("demo_slot") is sentinel


def test_register_overwrites():
    registry.register("demo_slot2", 1)
    registry.register("demo_slot2", 2)
    assert registry.get("demo_slot2") == 2
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd server && uv run pytest apps/cmdb/tests/test_extensions_registry.py -o addopts="-p no:randomly -q" -v`
Expected: FAIL —— `ModuleNotFoundError: apps.cmdb.extensions.registry`。

- [ ] **Step 3: 实现注册表**

```python
# server/apps/cmdb/extensions/registry.py
"""社区扩展点注册表（IoC）。

社区定义具名槽位与默认空契约；商业 app 在 AppConfig.ready() 注册实现。
社区代码只 get(name, default)，从不 import 任何企业模块。
"""

_registry: dict = {}


def register(name: str, impl) -> None:
    """注册某扩展槽位的实现（后注册覆盖先注册）。"""
    _registry[name] = impl


def get(name: str, default=None):
    """取某扩展槽位的实现；未注册返回 default。"""
    return _registry.get(name, default)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd server && uv run pytest apps/cmdb/tests/test_extensions_registry.py -o addopts="-p no:randomly -q" -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/extensions/registry.py server/apps/cmdb/tests/test_extensions_registry.py
git commit -m "feat(cmdb): add community extension registry (IoC)"
```

---

### Task 0.2：三域 facade 从 load_provider 改为 registry

**Files:**
- Modify: `server/apps/cmdb/model_ops/extensions.py`
- Modify: `server/apps/cmdb/instance_ops/extensions.py`
- Modify: `server/apps/cmdb/collect/extensions.py`
- Test: `server/apps/cmdb/tests/test_enterprise_extensions.py`（现有，改造）

- [ ] **Step 1: 写失败测试（无注册时返回默认空契约）**

在 `server/apps/cmdb/tests/test_enterprise_extensions.py` 顶部替换原 loader 相关用例为：

```python
# 替换文件内容为以下（删除原 load_provider / 企业 provider 断言相关用例）
"""社区域 facade 经注册表取实现的纯单测（无注册→默认空契约）。"""

import pytest

from apps.cmdb.extensions import registry
from apps.cmdb.model_ops.extensions import (
    ModelEnterpriseExtension,
    get_model_enterprise_extension,
)
from apps.cmdb.instance_ops.extensions import (
    InstanceEnterpriseExtension,
    get_instance_enterprise_extension,
)
from apps.cmdb.collect.extensions import (
    CollectEnterpriseExtension,
    get_collect_enterprise_extension,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    # 每个用例前清空相关槽位，保证默认契约路径
    for slot in ("model_ops", "instance_ops", "collect"):
        registry._registry.pop(slot, None)
    yield
    for slot in ("model_ops", "instance_ops", "collect"):
        registry._registry.pop(slot, None)


def test_model_default_when_unregistered():
    ext = get_model_enterprise_extension()
    assert isinstance(ext, ModelEnterpriseExtension)
    assert ext.file_attr_types() == set()
    assert ext.unsupported_unique_attr_types() == set()


def test_model_uses_registered_impl():
    class Custom(ModelEnterpriseExtension):
        def file_attr_types(self):
            return {"attachment", "image"}

    registry.register("model_ops", Custom())
    assert get_model_enterprise_extension().file_attr_types() == {"attachment", "image"}


def test_instance_default_is_noop():
    ext = get_instance_enterprise_extension()
    assert isinstance(ext, InstanceEnterpriseExtension)
    data = {"x": 1}
    assert ext.normalize_file_fields("m", data, [], operator="u") == data


def test_collect_default_empty():
    ext = get_collect_enterprise_extension()
    assert isinstance(ext, CollectEnterpriseExtension)
    assert ext.collect_tree == [] and ext.plugin_packages == ()
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py -o addopts="-p no:randomly -q" -v`
Expected: FAIL —— `get_*_enterprise_extension` 仍走 load_provider，`registry` 路径未接通（或导入错误）。

- [ ] **Step 3: 改三域 facade**

`server/apps/cmdb/model_ops/extensions.py` —— 把 `get_model_enterprise_extension()` 替换为：

```python
from apps.cmdb.extensions import registry  # 替换原 from ...loader import load_provider

# ... ModelEnterpriseExtension 与 _EMPTY_MODEL_EXTENSION 不变 ...

def get_model_enterprise_extension() -> ModelEnterpriseExtension:
    return registry.get("model_ops", _EMPTY_MODEL_EXTENSION)
```

`server/apps/cmdb/instance_ops/extensions.py` —— 同理：

```python
from apps.cmdb.extensions import registry  # 替换 loader 导入

def get_instance_enterprise_extension() -> InstanceEnterpriseExtension:
    return registry.get("instance_ops", _EMPTY_INSTANCE_EXTENSION)
```

`server/apps/cmdb/collect/extensions.py` —— 同理：

```python
from apps.cmdb.extensions import registry  # 替换 loader 导入

def get_collect_enterprise_extension() -> CollectEnterpriseExtension:
    return registry.get("collect", _EMPTY_COLLECT_EXTENSION)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py -o addopts="-p no:randomly -q" -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 删 loader（不再被任何社区代码引用）**

Run（确认无引用后删除）：
```bash
cd server && grep -rn "load_provider\|extensions.loader" apps/cmdb --include=*.py | grep -v test_
```
Expected: 无输出。然后 `rm apps/cmdb/extensions/loader.py`。

- [ ] **Step 6: 提交**

```bash
git add server/apps/cmdb/model_ops/extensions.py server/apps/cmdb/instance_ops/extensions.py \
        server/apps/cmdb/collect/extensions.py server/apps/cmdb/tests/test_enterprise_extensions.py
git rm server/apps/cmdb/extensions/loader.py
git commit -m "refactor(cmdb): route domain facades through registry, drop load_provider"
```

---

### Task 0.3：新增 custom_reporting 社区契约

**Files:**
- Create: `server/apps/cmdb/custom_reporting/__init__.py`
- Create: `server/apps/cmdb/custom_reporting/extensions.py`
- Test: `server/apps/cmdb/tests/test_custom_reporting_extension.py`

- [ ] **Step 1: 写失败测试**

```python
# server/apps/cmdb/tests/test_custom_reporting_extension.py
"""custom_reporting 社区契约：无注册时默认 no-op，社区不依赖企业实现。"""

import pytest

from apps.cmdb.extensions import registry
from apps.cmdb.custom_reporting.extensions import (
    CustomReportingExtension,
    get_custom_reporting_extension,
)


@pytest.fixture(autouse=True)
def _clear():
    registry._registry.pop("custom_reporting", None)
    yield
    registry._registry.pop("custom_reporting", None)


def test_default_noop():
    ext = get_custom_reporting_extension()
    assert isinstance(ext, CustomReportingExtension)
    assert ext.register_model_fields("m", []) == []
    assert ext.get_declared_attr_ids("m") == set()
    assert ext.normalize_identity_keys(None) == []
    # validate_* 默认不抛
    ext.validate_instance_fields("m", [])
    ext.validate_relation_fields("m", [])
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd server && uv run pytest apps/cmdb/tests/test_custom_reporting_extension.py -o addopts="-p no:randomly -q" -v`
Expected: FAIL —— 模块不存在。

- [ ] **Step 3: 实现契约**

```python
# server/apps/cmdb/custom_reporting/__init__.py
"""CMDB 自定义上报能力域社区门面。"""
```

```python
# server/apps/cmdb/custom_reporting/extensions.py
"""custom_reporting 能力域企业版扩展契约（社区侧门面，默认 no-op）。

社区从不 import 企业实现；商业 app 在 ready() 注册实现到 "custom_reporting" 槽位。
"""

from apps.cmdb.extensions import registry


class CustomReportingExtension:
    """自定义上报契约。社区默认全部 no-op（社区版不具备该商业能力）。"""

    def register_model_fields(self, model_id: str, instances: list, username: str = "admin") -> list:
        return []

    def validate_instance_fields(self, model_id: str, instances: list) -> None:
        return None

    def get_declared_attr_ids(self, model_id: str) -> set:
        return set()

    def validate_relation_fields(self, model_id: str, relations: list, identity_keys=None) -> None:
        return None

    def normalize_identity_keys(self, identity_keys) -> list:
        return []

    def bootstrap_model(self, quick_model: dict, team: list, username: str = "admin"):
        return None

    def sync_model_group(self, quick_model: dict, team: list, username: str = "admin"):
        return None


_EMPTY_CUSTOM_REPORTING = CustomReportingExtension()


def get_custom_reporting_extension() -> CustomReportingExtension:
    return registry.get("custom_reporting", _EMPTY_CUSTOM_REPORTING)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd server && uv run pytest apps/cmdb/tests/test_custom_reporting_extension.py -o addopts="-p no:randomly -q" -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/custom_reporting/__init__.py server/apps/cmdb/custom_reporting/extensions.py \
        server/apps/cmdb/tests/test_custom_reporting_extension.py
git commit -m "feat(cmdb): add custom_reporting community contract (default no-op)"
```

---

## Phase 1：搭 cmdb_enterprise overlay app 骨架（不提交，gitignore）

### Task 1.1：.gitignore + app 骨架

**Files:**
- Modify: `.gitignore`（提交）
- Create（不提交，overlay）: `server/apps/cmdb_enterprise/{__init__.py,apps.py,config.py,urls.py,models/__init__.py,migrations/__init__.py,tests/__init__.py}`

- [ ] **Step 1: 忽略新 app**

在 `.gitignore` 末尾追加（`**/enterprise/` 不匹配 `cmdb_enterprise`，需显式）：

```gitignore
# CMDB 商业版 overlay（同级 app，单独交付，不进开源仓）
/server/apps/cmdb_enterprise/
```

- [ ] **Step 2: 建 app 骨架（overlay，不提交）**

```python
# server/apps/cmdb_enterprise/__init__.py
default_app_config = "apps.cmdb_enterprise.apps.CmdbEnterpriseConfig"
```

```python
# server/apps/cmdb_enterprise/apps.py
from django.apps import AppConfig


class CmdbEnterpriseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cmdb_enterprise"

    def ready(self):
        # 各商业域实现注册到社区注册表（随后续 Task 逐步填充）
        from apps.cmdb_enterprise import registry_hooks  # noqa: F401
```

```python
# server/apps/cmdb_enterprise/registry_hooks.py
"""把商业实现注册进社区注册表 + 运行时配置（在 AppConfig.ready() 触发）。
后续 Task 逐步往这里加 register(...) 与桶注册。"""
```

```python
# server/apps/cmdb_enterprise/config.py
CELERY_BEAT_SCHEDULE = {}
```

```python
# server/apps/cmdb_enterprise/urls.py
urlpatterns = []
```

空包标记：`models/__init__.py`、`migrations/__init__.py`、`tests/__init__.py` 各写 `"""cmdb_enterprise overlay."""`。

- [ ] **Step 3: 验证 app 自动加载且 ready() 执行**

Run:
```bash
cd server && uv run python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','settings'); django.setup()
from django.apps import apps
print('cmdb_enterprise installed:', apps.is_installed('apps.cmdb_enterprise'))
"
```
Expected: `cmdb_enterprise installed: True`。

- [ ] **Step 4: 提交 .gitignore（overlay 文件不提交）**

```bash
git add .gitignore
git commit -m "chore: gitignore cmdb_enterprise overlay app"
```

---

## Phase 2：迁移附件/图片到 cmdb_enterprise

### Task 2.1：移动 instance_ops + model_ops 实现（overlay）

**Files（overlay，普通 mv，不提交）:**
- Move: `enterprise/instance_ops/*` → `cmdb_enterprise/instance_ops/*`
- Move: `enterprise/model_ops/*` → `cmdb_enterprise/model_ops/*`

- [ ] **Step 1: 移动并修正包内导入**

```bash
cd server/apps/cmdb
mkdir -p ../cmdb_enterprise/instance_ops ../cmdb_enterprise/model_ops
mv enterprise/instance_ops/* ../cmdb_enterprise/instance_ops/
mv enterprise/model_ops/* ../cmdb_enterprise/model_ops/
# 修正自包内绝对导入路径
grep -rl "apps.cmdb.enterprise.instance_ops\|apps.cmdb.enterprise.model_ops" ../cmdb_enterprise \
  | xargs perl -pi -e 's/apps\.cmdb\.enterprise\.instance_ops/apps.cmdb_enterprise.instance_ops/g; s/apps\.cmdb\.enterprise\.model_ops/apps.cmdb_enterprise.model_ops/g'
```

- [ ] **Step 2: 把 CmdbFileObject 引用从社区路径改为 app 自有模型（见 Task 2.2 先建模型再回填）**

先跳到 Task 2.2 建好 app 模型，再回到此处把 `service.py`/`tasks.py` 中 `from apps.cmdb.models.file_object import ...` 改为 `from apps.cmdb_enterprise.models.file_object import ...`。

- [ ] **Step 3: 冒烟导入**

Run: `cd server && uv run python -c "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','settings'); django.setup(); import apps.cmdb_enterprise.instance_ops.provider, apps.cmdb_enterprise.model_ops.provider; print('ok')"`
Expected: 先报 file_object 导入错（Task 2.2 解决），完成 2.2 后 `ok`。

（overlay 文件不提交）

---

### Task 2.2：CmdbFileObject 模型迁入 app + 迁移 + 删社区

**Files:**
- Create（overlay）: `server/apps/cmdb_enterprise/models/file_object.py`、`server/apps/cmdb_enterprise/migrations/0001_initial.py`（makemigrations 生成）
- Delete（社区，提交）: `server/apps/cmdb/models/file_object.py`、`server/apps/cmdb/migrations/0024_cmdbfileobject.py`
- Modify（社区，提交）: `server/apps/cmdb/models/__init__.py`（移除 file_object 导入）

- [ ] **Step 1: 把社区模型搬到 app（保留类定义，去掉社区定位注释）**

```bash
cd server/apps/cmdb
mv models/file_object.py ../cmdb_enterprise/models/file_object.py
```
编辑 `../cmdb_enterprise/models/file_object.py` 的 `class Meta` 增加 `app_label = "cmdb_enterprise"`（其余字段不变）。在 `cmdb_enterprise/models/__init__.py` 加 `from apps.cmdb_enterprise.models.file_object import *  # noqa`。

- [ ] **Step 2: 社区 models/__init__ 移除 file_object 导入**

删除 `server/apps/cmdb/models/__init__.py` 中的 `from apps.cmdb.models.file_object import *  # noqa` 行。

- [ ] **Step 3: 删社区迁移 + 回填 overlay 服务的模型导入**

```bash
cd server/apps/cmdb
git rm migrations/0024_cmdbfileobject.py
# 回填 Task 2.1 Step 2：
grep -rl "apps.cmdb.models.file_object" ../cmdb_enterprise | xargs perl -pi -e 's/apps\.cmdb\.models\.file_object/apps.cmdb_enterprise.models.file_object/g'
```

- [ ] **Step 4: 生成 app 迁移**

Run:
```bash
cd server && uv run python manage.py makemigrations cmdb_enterprise
```
Expected: `Create model CmdbFileObject`（迁移落 `apps/cmdb_enterprise/migrations/0001_initial.py`，overlay 不提交）。

- [ ] **Step 5: 本地库重建（无生产数据）**

Run（删旧表 + 应用新迁移）：
```bash
cd server && uv run python manage.py dbshell -c "DROP TABLE IF EXISTS cmdb_cmdbfileobject;" 2>/dev/null || true
uv run python manage.py migrate cmdb_enterprise
```
Expected: 新表 `cmdb_enterprise_cmdbfileobject` 创建。

- [ ] **Step 6: makemigrations cmdb 干净（社区已无该模型）**

Run: `cd server && uv run python manage.py makemigrations cmdb --check --dry-run`
Expected: `No changes detected in app 'cmdb'`。

- [ ] **Step 7: 提交社区删除**

```bash
git add server/apps/cmdb/models/__init__.py
git rm server/apps/cmdb/models/file_object.py server/apps/cmdb/migrations/0024_cmdbfileobject.py
git commit -m "refactor(cmdb): move CmdbFileObject ownership to cmdb_enterprise app"
```

---

### Task 2.3：附件接口迁到 app urls + 删社区 view/urls 接缝 + 注册实现

**Files:**
- Modify（社区，提交）: `server/apps/cmdb/views/instance.py`（删 upload_file/download_file/delete_file 三个 action 及其 import）、`server/apps/cmdb/urls.py`（删 enterprise urls 接缝）
- Create（overlay）: `server/apps/cmdb_enterprise/views.py`、`server/apps/cmdb_enterprise/urls.py`（实现三接口）、`server/apps/cmdb_enterprise/registry_hooks.py`（注册 instance_ops/model_ops）

- [ ] **Step 1: overlay 实现接口 + 注册**

`cmdb_enterprise/registry_hooks.py` 追加：

```python
from apps.cmdb.extensions import registry
from apps.cmdb_enterprise.model_ops.provider import get_model_enterprise_extension as _model
from apps.cmdb_enterprise.instance_ops.provider import get_instance_enterprise_extension as _inst

registry.register("model_ops", _model())
registry.register("instance_ops", _inst())
```

`cmdb_enterprise/urls.py` 实现 upload_file/download_file/delete_file（把原社区 `views/instance.py` 里三个 action 的逻辑搬到 overlay 的 DRF view/函数视图，挂到 `urlpatterns`，最终路径 `api/v1/cmdb_enterprise/...`）。下载校权回调复用社区实例读权限工具。

- [ ] **Step 2: 删社区三 action + urls 接缝**

`server/apps/cmdb/views/instance.py`：删除 `upload_file`、`download_file`、`delete_file` 三个 `@action` 方法、`_check_instance_read_permission`（若仅服务下载则移到 overlay）、`get_instance_enterprise_extension` 与 `HttpResponseRedirect` 等仅服务这些 action 的 import。

`server/apps/cmdb/urls.py`：删除第 40-46 行 enterprise urls 的 guarded 块。

- [ ] **Step 3: 验证（有 overlay）**

Run: `cd server && uv run python -c "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','settings'); django.setup(); from django.urls import get_resolver; print([str(p.pattern) for p in get_resolver().url_patterns if 'cmdb_enterprise' in str(p.pattern)])"`
Expected: 含 `api/v1/cmdb_enterprise/`。

- [ ] **Step 4: 提交社区改动**

```bash
git add server/apps/cmdb/views/instance.py server/apps/cmdb/urls.py
git commit -m "refactor(cmdb): move attachment endpoints to cmdb_enterprise app"
```

---

### Task 2.4：前端接口路径跟随 + 测试搬迁

**Files:**
- Modify（提交）: `web/src/app/cmdb/api/instance.ts`、`web/src/app/cmdb/components/file-field/index.tsx`
- Move（overlay）: `apps/cmdb/tests/test_file_field_service.py`、`test_file_field_integration.py` → `apps/cmdb_enterprise/tests/`
- Modify（提交）: 从社区 tests 删除上述文件 + `test_instance_views.py` 中 file 相关 view 用例（移到 overlay）

- [ ] **Step 1: 前端路径改 cmdb_enterprise 命名空间**

`web/src/app/cmdb/api/instance.ts`：`uploadFile`/`deleteFile` 的 URL `/cmdb/api/instance/upload_file/`、`/cmdb/api/instance/delete_file/${id}/` 改为 `/cmdb_enterprise/...`（与 overlay urls 一致）。`file-field/index.tsx` 的 `fileDownloadUrl` 改 `/api/proxy/cmdb_enterprise/.../download_file/${id}/`。

- [ ] **Step 2: 前端类型/lint**

Run:
```bash
cd web && export PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH"
node node_modules/.bin/tsc -p tsconfig.lint.json --noEmit 2>&1 | grep -cE "error TS"
node node_modules/eslint/bin/eslint.js src/app/cmdb/api/instance.ts src/app/cmdb/components/file-field/index.tsx
```
Expected: `0` 且 eslint 退出 0。

- [ ] **Step 3: 测试搬到 overlay**

```bash
cd server/apps/cmdb
mv tests/test_file_field_service.py tests/test_file_field_integration.py ../cmdb_enterprise/tests/
```
移除两文件里的 `pytest.importorskip`/skip 守卫（overlay 里 enterprise 必在）。把 `test_instance_views.py` 中 4 个 file 接口用例移到 overlay 的 `cmdb_enterprise/tests/test_views.py`（按新 URL）。社区 `test_instance_views.py` 删除这 4 个用例。

- [ ] **Step 4: 跑 overlay 测试 + 社区测试**

Run:
```bash
cd server && uv run pytest apps/cmdb_enterprise/tests apps/cmdb/tests/test_instance_views.py -o addopts="-p no:randomly -q"
```
Expected: 全绿。

- [ ] **Step 5: 提交（社区改动 + 前端）**

```bash
git add web/src/app/cmdb/api/instance.ts web/src/app/cmdb/components/file-field/index.tsx \
        server/apps/cmdb/tests/test_instance_views.py
git rm server/apps/cmdb/tests/test_file_field_service.py server/apps/cmdb/tests/test_file_field_integration.py
git commit -m "refactor(cmdb): point attachment frontend to cmdb_enterprise, move enterprise tests"
```

---

## Phase 3：迁移达梦/采集

### Task 3.1：collect 实现迁入 app + 注册

**Files:**
- Move（overlay）: `enterprise/collect/*` → `cmdb_enterprise/collect/*`
- Modify（overlay）: `cmdb_enterprise/registry_hooks.py`

- [ ] **Step 1: 移动 + 修导入 + 注册**

```bash
cd server/apps/cmdb
mkdir -p ../cmdb_enterprise/collect
mv enterprise/collect/* ../cmdb_enterprise/collect/
grep -rl "apps.cmdb.enterprise.collect" ../cmdb_enterprise | xargs perl -pi -e 's/apps\.cmdb\.enterprise\.collect/apps.cmdb_enterprise.collect/g'
```
`cmdb_enterprise/collect/provider.py` 内 `_COLLECT_PACKAGE` 改为 `"apps.cmdb_enterprise.collect"`。`registry_hooks.py` 追加：

```python
from apps.cmdb_enterprise.collect.provider import get_collect_enterprise_extension as _collect
registry.register("collect", _collect())
# 触发采集插件/NodeParams 自注册
from apps.cmdb_enterprise.collect import dameng  # noqa: F401
```

- [ ] **Step 2: 验证达梦树/插件/NodeParams**

Run:
```bash
cd server && uv run python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','settings'); django.setup()
from apps.cmdb.services.collect_object_tree import get_collect_obj_tree
print('dameng in tree:', any(ch.get('model_id')=='dameng' for cat in get_collect_obj_tree() for ch in cat.get('children',[])))
from apps.cmdb.collection.plugins.loader import CollectionPluginLoader
CollectionPluginLoader._loaded=False; CollectionPluginLoader.load_plugins()
from apps.cmdb.node_configs.base import BaseNodeParams
print('dameng nodeparam:', any('dameng' in str(k) for k in BaseNodeParams._registry))
"
```
Expected: 两者均 `True`。

- [ ] **Step 3: 社区采集测试回归**

Run: `cd server && uv run pytest apps/cmdb/tests/test_collect_object_tree.py apps/cmdb/tests/test_node_params_multicred.py -o addopts="-p no:randomly -q"`
Expected: 全绿（社区用例本就 mock 注册表/facade，不依赖路径）。

（collect 社区侧 hooks 已在 Phase 0 走 registry，无需再改；overlay 文件不提交）

---

## Phase 4：迁移 custom_reporting

> 注意：custom_reporting 的企业**行为实现**（`CustomReportingModelService`）由 overlay 单独交付、不在本仓。本 Phase 在本仓做的是：①schema 归属转移到 app；②社区 model.py 7 方法改走契约；③删社区 fallback 与裸导入。行为实现的 overlay 落点与注册由你在 overlay 仓补齐（落 `cmdb_enterprise/custom_reporting/`，在 registry_hooks 注册 "custom_reporting"）。

### Task 4.1：custom_reporting 6 模型迁入 app + 迁移 + 删社区

**Files:**
- Move（overlay）: `apps/cmdb/models/custom_reporting.py` → `apps/cmdb_enterprise/custom_reporting/models.py`
- Delete（社区，提交）: `apps/cmdb/models/custom_reporting.py`、`apps/cmdb/migrations/0024_custom_reporting.py`、`models/__init__.py` 的 guarded 块
- Create（overlay）: `cmdb_enterprise/migrations/000X_custom_reporting.py`

- [ ] **Step 1: 模型搬到 app**

```bash
cd server/apps/cmdb
mkdir -p ../cmdb_enterprise/custom_reporting
mv models/custom_reporting.py ../cmdb_enterprise/custom_reporting/models.py
```
给每个模型 `class Meta` 加 `app_label = "cmdb_enterprise"`（若已有 Meta 则追加该行）。`cmdb_enterprise/models/__init__.py` 追加 `from apps.cmdb_enterprise.custom_reporting.models import *  # noqa`。

- [ ] **Step 2: 删社区 models/__init__ 的 guarded 块**

把 `server/apps/cmdb/models/__init__.py` 第 13-22 行（`try: __import__("apps.cmdb.enterprise.models")...except...custom_reporting`）整段删除。

- [ ] **Step 3: 生成 app 迁移 + 删社区迁移 + 重建表**

```bash
cd server
git rm apps/cmdb/migrations/0024_custom_reporting.py
uv run python manage.py makemigrations cmdb_enterprise
uv run python manage.py dbshell -c "DROP TABLE IF EXISTS cmdb_custom_reporting_task, cmdb_custom_reporting_task_scope, cmdb_custom_reporting_credential, cmdb_custom_reporting_batch, cmdb_custom_reporting_pending_relation, cmdb_custom_reporting_cleanup_review CASCADE;" 2>/dev/null || true
uv run python manage.py migrate cmdb_enterprise
uv run python manage.py makemigrations cmdb --check --dry-run
```
Expected: 新迁移生成 6 表；最后一行 `No changes detected in app 'cmdb'`。

- [ ] **Step 4: 提交社区删除**

```bash
git add server/apps/cmdb/models/__init__.py
git rm server/apps/cmdb/models/custom_reporting.py server/apps/cmdb/migrations/0024_custom_reporting.py
git commit -m "refactor(cmdb): move custom_reporting models to cmdb_enterprise app"
```

---

### Task 4.2：model.py 7 方法改走契约 + 删社区壳

**Files:**
- Modify（社区，提交）: `server/apps/cmdb/services/model.py:565-643`
- Delete（社区，提交）: `views/custom_reporting.py`、`serializers/custom_reporting.py`、`services/custom_reporting_{ingest,document,task}_service.py`（若仅是 guarded 企业导入壳）

- [ ] **Step 1: 写失败测试（社区方法默认 no-op，不再硬依赖企业）**

```python
# server/apps/cmdb/tests/test_model_custom_reporting_delegation.py
"""ModelManage 的 custom_reporting 方法经契约委托；无注册时安全 no-op。"""

import pytest
from apps.cmdb.extensions import registry
from apps.cmdb.services.model import ModelManage


@pytest.fixture(autouse=True)
def _clear():
    registry._registry.pop("custom_reporting", None)
    yield
    registry._registry.pop("custom_reporting", None)


def test_register_fields_noop_without_overlay():
    assert ModelManage.register_custom_reporting_model_fields("m", []) == []


def test_declared_attr_ids_empty_without_overlay():
    assert ModelManage._get_custom_reporting_declared_attr_ids("m") == set()


def test_delegates_to_registered_extension():
    from apps.cmdb.custom_reporting.extensions import CustomReportingExtension

    class Impl(CustomReportingExtension):
        def get_declared_attr_ids(self, model_id):
            return {"a", "b"}

    registry.register("custom_reporting", Impl())
    assert ModelManage._get_custom_reporting_declared_attr_ids("m") == {"a", "b"}
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_custom_reporting_delegation.py -o addopts="-p no:randomly -q" -v`
Expected: FAIL —— 现有方法仍裸 `from apps.cmdb.enterprise.services...` → `ModuleNotFoundError`。

- [ ] **Step 3: 改 7 方法走契约**

把 `services/model.py:565-643` 的 7 个方法体改为委托 `get_custom_reporting_extension()`。示例（其余同构）：

```python
from apps.cmdb.custom_reporting.extensions import get_custom_reporting_extension  # 文件顶部 import

@staticmethod
def register_custom_reporting_model_fields(model_id, instances, username="admin"):
    return get_custom_reporting_extension().register_model_fields(model_id, instances, username=username)

@staticmethod
def validate_custom_reporting_instance_fields(model_id, instances):
    get_custom_reporting_extension().validate_instance_fields(model_id, instances)

@staticmethod
def _get_custom_reporting_declared_attr_ids(model_id):
    return get_custom_reporting_extension().get_declared_attr_ids(model_id)

@staticmethod
def validate_custom_reporting_relation_fields(model_id, relations, identity_keys=None):
    get_custom_reporting_extension().validate_relation_fields(model_id, relations, identity_keys=identity_keys)

@staticmethod
def normalize_custom_reporting_identity_keys(identity_keys):
    return get_custom_reporting_extension().normalize_identity_keys(identity_keys)

@staticmethod
def bootstrap_custom_reporting_model(quick_model, team, username="admin"):
    return get_custom_reporting_extension().bootstrap_model(quick_model, team=team, username=username)

@staticmethod
def sync_custom_reporting_model_group(quick_model, team, username="admin"):
    return get_custom_reporting_extension().sync_model_group(quick_model, team=team, username=username)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_custom_reporting_delegation.py -o addopts="-p no:randomly -q" -v`
Expected: PASS。

- [ ] **Step 5: 处理社区壳文件**

检查 `views/custom_reporting.py`、`serializers/custom_reporting.py`、`services/custom_reporting_*_service.py`：若仅是 `try: from apps.cmdb.enterprise.* import *` 壳，则其 URL/路由也应迁到 overlay；删除社区壳并移除 `urls.py`/serializers 注册中对它们的引用。如这些壳承载社区可用逻辑，则保留并改走契约（按实际内容判断；保持「社区无该商业能力」目标）。

- [ ] **Step 6: 提交**

```bash
git add server/apps/cmdb/services/model.py server/apps/cmdb/tests/test_model_custom_reporting_delegation.py
git rm server/apps/cmdb/views/custom_reporting.py server/apps/cmdb/serializers/custom_reporting.py \
       server/apps/cmdb/services/custom_reporting_ingest_service.py \
       server/apps/cmdb/services/custom_reporting_document_service.py \
       server/apps/cmdb/services/custom_reporting_task_service.py
git commit -m "refactor(cmdb): route custom_reporting through contract, drop community shells"
```

---

## Phase 5：最终净身 + 平台资源迁移 + agnostic 验证

### Task 5.1：beat/tasks/bootstrap 迁入 app + 删三接缝

**Files:**
- Move（overlay）: `enterprise/beat.py`→`cmdb_enterprise/config.py`（合并 schedule）、`enterprise/tasks/*`→`cmdb_enterprise/tasks/*`、`enterprise/bootstrap.py` 桶注册逻辑→`cmdb_enterprise/registry_hooks.py`
- Modify（社区，提交）: `apps/cmdb/tasks/__init__.py`、`apps/cmdb/config.py`、`apps/cmdb/apps.py`

- [ ] **Step 1: overlay 承接 beat/tasks/桶**

把 `enterprise/beat.py` 的 `ENTERPRISE_BEAT_SCHEDULE` 内容并入 `cmdb_enterprise/config.py` 的 `CELERY_BEAT_SCHEDULE`（task 名改 `apps.cmdb_enterprise.tasks...`）。`enterprise/tasks/*` 移到 `cmdb_enterprise/tasks/`，修导入。`enterprise/bootstrap.py` 的 `_register_minio_buckets` 逻辑搬进 `registry_hooks.py`（ready 时执行）。

- [ ] **Step 2: 删社区三接缝**

`apps/cmdb/tasks/__init__.py`：删第 19-23 行 enterprise 任务 guarded 导入。
`apps/cmdb/config.py`：删第 22-28 行 enterprise beat 合并块。
`apps/cmdb/apps.py`：删 ready() 里第 12-17 行 enterprise bootstrap guarded 块。

- [ ] **Step 3: 验证 beat/task 注册（有 overlay）**

Run:
```bash
cd server && uv run python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','settings'); django.setup()
from django.conf import settings
print('cleanup beat:', 'cleanup_attachment_files' in settings.CELERY_BEAT_SCHEDULE)
print('bucket:', 'cmdb-attachment' in settings.MINIO_PRIVATE_BUCKETS)
"
```
Expected: 两者 `True`。

- [ ] **Step 4: 提交社区接缝删除**

```bash
git add server/apps/cmdb/tasks/__init__.py server/apps/cmdb/config.py server/apps/cmdb/apps.py
git commit -m "refactor(cmdb): drop enterprise task/beat/bootstrap seams"
```

---

### Task 5.2：删除旧 enterprise/ 目录

**Files:**
- Delete（社区跟踪的仅 `enterprise/README.md`，提交其删除；其余 overlay 文件 `rm`）

- [ ] **Step 1: 确认 enterprise/ 已空（实现都迁走）**

Run: `cd server/apps/cmdb && find enterprise -type f -not -path "*/__pycache__/*"`
Expected: 仅余 `enterprise/__init__.py`、`enterprise/README.md`（及空目录）。若还有实现文件，回到对应 Phase 迁移。

- [ ] **Step 2: 删目录**

```bash
cd server/apps/cmdb
git rm enterprise/README.md
rm -rf enterprise
```

- [ ] **Step 3: 提交**

```bash
git rm -r --cached --ignore-unmatch server/apps/cmdb/enterprise 2>/dev/null || true
git add -A server/apps/cmdb
git commit -m "refactor(cmdb): remove nested enterprise/ dir (superseded by cmdb_enterprise app)"
```

---

### Task 5.3：enterprise-agnostic 验证（核心验收）

- [ ] **Step 1: 社区代码零企业路径**

Run: `cd server && grep -rn "cmdb.enterprise\|cmdb_enterprise" apps/cmdb --include=*.py`
Expected: 无输出（社区只剩 registry/契约，不含任何企业模块路径）。

- [ ] **Step 2: 有 overlay 全量回归**

Run: `cd server && uv run pytest apps/cmdb apps/cmdb_enterprise --ignore=apps/cmdb/tests/bdd --ignore=apps/cmdb/tests/e2e -o addopts="-p no:randomly -q"`
Expected: 全绿（达梦/附件/custom_reporting 契约行为均通过）。

- [ ] **Step 3: 无 overlay 社区独立绿（模拟删 overlay）**

Run:
```bash
cd server && mv apps/cmdb_enterprise /tmp/cmdb_enterprise_bak
uv run python manage.py makemigrations cmdb --check --dry-run
uv run pytest apps/cmdb --ignore=apps/cmdb/tests/bdd --ignore=apps/cmdb/tests/e2e -o addopts="-p no:randomly -q"
mv /tmp/cmdb_enterprise_bak apps/cmdb_enterprise
```
Expected: makemigrations 干净；`pytest apps/cmdb` 全绿（社区无附件/custom_reporting/达梦能力且无报错；注册表空 → 默认契约）。

- [ ] **Step 4: 更新规范文档**

把 `docs/superpowers/plans/2026-06-08-cmdb-enterprise-layering.md` 与（已删的）`enterprise/README.md` 的规范内容,改写/迁移到 `docs/` 下的「商业版 overlay app 规范 v3」(反映 cmdb_enterprise + 注册表)。提交。

```bash
git add docs/
git commit -m "docs(cmdb): enterprise overlay app architecture v3"
```

---

## 验收总览

- 社区 `grep -rn "enterprise" apps/cmdb/*.py apps/cmdb/**/*.py` 仅余通用 registry/契约（无企业路径）。
- 有 overlay：三商业功能行为与重构前一致；企业测试在 `apps/cmdb_enterprise/tests` 全绿。
- 无 overlay：社区 cmdb 启动正常、`pytest apps/cmdb` 全绿、`makemigrations cmdb --check` 干净。
- 模型/迁移/任务/beat/URL 均归 `cmdb_enterprise` app；社区零企业模型、零 guarded 企业导入、零双模型。

## specs: 2026-06-09-cmdb-enterprise-sibling-app-design.md

- 日期：2026-06-09
- 状态：已确认，待写实施计划
- 取代：`apps/cmdb/enterprise/` 嵌套式分层（v2 规范）；本设计为 v3 架构方向

## Context（为什么重构）

CMDB 商业版能力当前**嵌套**在 `server/apps/cmdb/enterprise/` 内，社区版通过「guarded 导入 + load_provider facade」与之耦合。随着商业功能增多，这套方案的代价在真实累积，且伤到了社区版的核心（模型层）：

- **模型污染（核心痛点）**：`custom_reporting` 把 6 个模型的**完整定义**放进社区 `apps/cmdb/models/custom_reporting.py` 作为「fallback」，再被企业版**覆盖**；`models/__init__.py` 里有一段 guarded `apps.cmdb.enterprise.models` 导入 + 社区 fallback 的**双模型**逻辑。社区版实打实地包含并维护着商业模型——「容易把社区模型搞乱」。
- **接缝蔓延**：`tasks/__init__.py`、`config.py`、`apps.py`、`urls.py` 四处 guarded 接缝 + 三个域的 `extensions.py` load_provider；custom_reporting 还在 `views/`、`serializers/`、3 个 service、`services/model.py` 的 **7 个方法**里散落导入（部分**无 try/except 守卫**）。
- **迁移混放**：`0024_cmdbfileobject.py`、`0024_custom_reporting.py` 等商业表迁移落在社区 `apps/cmdb/migrations/`。

**已有先例**：本仓库 `config/components/app.py:91-100` 已有「同级商业 app」模式——`license_mgmt`：目录存在即加载、挂自己的中间件。商业版抽成同级 app 在本仓库是被验证过的做法。

**目标**：把商业版变成一个**自包含、可插拔、自带表/任务/路由/迁移的独立 app**，社区 cmdb 通过**注册表**与它解耦到「互不 import」，从根上消除模型污染与接缝蔓延。

## 已确认决策

1. **交付方式**：独立同级 app `server/apps/cmdb_enterprise/`，被 `.gitignore` 忽略（overlay，对齐 license_mgmt）；目录存在即由现有 `apps/` 扫描自动加载，不在则社区版正常运行。
2. **集成机制**：注册表 / 钩子（IoC）。社区定义扩展点接口与默认空契约；商业 app 在 `AppConfig.ready()` 注册实现。社区代码**不出现任何 enterprise / cmdb_enterprise 字样**。
3. **范围**：全量迁移 —— 达梦 + 附件/图片 + custom_reporting 三个现有商业功能全部迁入新 app，删除社区侧对应模型与 0024 迁移，由新 app 自有迁移重建表（**前提：三者尚未上生产、无需保留数据**）。

## 架构

### 1. 目录结构与加载

```
server/apps/
  cmdb/                         # 社区版：只有「扩展点接口 + 调用点」，零企业知识
    extensions/registry.py      #   通用具名注册表（社区拥有）
    model_ops/extensions.py     #   ModelEnterpriseExtension 默认空契约 + get_*()→registry
    instance_ops/extensions.py  #   InstanceEnterpriseExtension 默认空契约 + get_*()
    collect/extensions.py       #   CollectEnterpriseExtension 默认空契约 + get_*()
    custom_reporting/extensions.py  # CustomReportingExtension 默认空契约 + get_*()（新增）

  cmdb_enterprise/              # 商业版 overlay（.gitignore 忽略）
    apps.py                     #   AppConfig.ready()：向社区注册表注册各域实现
    config.py                   #   CELERY_BEAT_SCHEDULE（celery 组件按 app 自动合并）
    urls.py                     #   接口（url 自动发现 → api/v1/cmdb_enterprise/）
    models/ + migrations/       #   自有表，app_label=cmdb_enterprise，自有迁移目录
    tasks/                      #   @shared_task（Celery autodiscover）
    instance_ops/               #   附件/图片：provider/service/storage/constants
    model_ops/                  #   字段类型规则 provider
    collect/                    #   达梦 tree/dameng/provider
    custom_reporting/           #   models/views/serializers/services 等
    tests/                      #   企业测试（随 app 走，gitignore）
```

加载：`config/components/app.py` 现有逻辑已自动注册 `apps/` 下所有子目录（除 base/core/rpc）。`cmdb_enterprise` 存在即装、缺失即跳，**无需改 app.py**。字母序在 `cmdb` 之后 → 其 `ready()` 在 cmdb 加载后执行，注册时机正确。

### 2. 集成：注册表 IoC（社区零企业知识）

社区 `apps/cmdb/extensions/registry.py`（通用、不含任何企业名）：

```python
_registry = {}

def register(name: str, impl) -> None:
    _registry[name] = impl

def get(name: str, default=None):
    return _registry.get(name, default)
```

各域 `extensions.py`：保留**契约类**（社区拥有的接口，默认全 no-op），把 `get_*_enterprise_extension()` 从 load_provider 改为 `registry.get(name, _DEFAULT)`。调用点不变（如 `get_instance_enterprise_extension().normalize_file_fields(...)`）。

商业 `cmdb_enterprise/apps.py`：

```python
class CmdbEnterpriseConfig(AppConfig):
    name = "apps.cmdb_enterprise"

    def ready(self):
        from apps.cmdb.extensions import registry
        from apps.cmdb_enterprise.model_ops.provider import FileFieldModelExtension
        from apps.cmdb_enterprise.instance_ops.provider import FileFieldInstanceExtension
        from apps.cmdb_enterprise.collect.provider import get_collect_enterprise_extension
        from apps.cmdb_enterprise.custom_reporting.provider import CustomReportingExtension

        registry.register("model_ops", FileFieldModelExtension())
        registry.register("instance_ops", FileFieldInstanceExtension())
        registry.register("collect", get_collect_enterprise_extension())
        registry.register("custom_reporting", CustomReportingExtension())

        # 采集插件/NodeParams：import 本域模块触发既有 __init_subclass__ 自注册
        from apps.cmdb_enterprise.collect import dameng  # noqa: F401
        # MinIO 桶运行时注册
        self._register_buckets()
```

结果：社区代码中**搜不到 enterprise/cmdb_enterprise**，无 guarded import、无 load_provider 路径、无双模型。社区只认「注册表 + 契约」，谁来填它不知道。

### 3. 资源归属（Django/Celery 自动发现，无社区接缝）

| 资源 | 归属 | 机制 |
|---|---|---|
| 模型 + 迁移 | `cmdb_enterprise` app | app 自带 migrations，`app_label=cmdb_enterprise`，社区零企业模型 |
| 异步任务 | `cmdb_enterprise/tasks` | Celery `autodiscover_tasks()` |
| beat 调度 | `cmdb_enterprise/config.py` | celery 组件按 INSTALLED_APPS 合并 `CELERY_BEAT_SCHEDULE` |
| 接口 URL | `cmdb_enterprise/urls.py` | url 自动发现 → `api/v1/cmdb_enterprise/` |
| MinIO 桶 | app `ready()` 运行时注册 | 向 `settings.MINIO_PRIVATE_BUCKETS` 追加，不改社区 minio.py |
| 行为钩子 | 注册表（§2） | 社区调用点 → `registry.get()` |
| 采集 tree | 注册表（懒取） | `get_collect_obj_tree()` 请求时读 registry |
| 采集插件/NodeParams | 既有全局注册表 | app `ready()` import collect 模块触发 `__init_subclass__` |

时机说明：beat/tasks/urls/models 走 settings 加载或 autodiscover（早于或独立于 ready()），均为真 app 机制；行为钩子在请求时读注册表（晚于 ready()，已就绪）；采集 tree 请求时懒取（安全），插件/NodeParams 在 enterprise `ready()` 时 import 自注册。

### 4. 注册表暴露的扩展点（来自现有契约）

- `model_ops`（`ModelEnterpriseExtension`）：`file_attr_types()`、`validate_attr(attr)`、`unsupported_unique_attr_types()`、`unsupported_auto_relation_attr_types()`
- `instance_ops`（`InstanceEnterpriseExtension`）：`normalize_file_fields(...)`、`commit_instance_files(...)`、`on_instance_delete(...)`、`handle_upload/download/delete_temp(...)`
- `collect`（`CollectEnterpriseExtension`）：`collect_tree`、`plugin_packages`、`node_param_packages`
- `custom_reporting`（`CustomReportingExtension`，新建社区契约）：把 `services/model.py:565-643` 现有 7 个方法（`register_custom_reporting_model_fields`、`validate_custom_reporting_instance_fields`、`_get_custom_reporting_declared_attr_ids`、`validate_custom_reporting_relation_fields`、`normalize_custom_reporting_identity_keys`、`bootstrap_custom_reporting_model`、`sync_custom_reporting_model_group`）收敛为契约方法，社区方法体改为 `get_custom_reporting_extension().xxx(...)`，默认契约 no-op。

## 迁移：三个现有功能

### 附件/图片
- `apps/cmdb/enterprise/instance_ops` + `model_ops` → `apps/cmdb_enterprise/{instance_ops,model_ops}`。
- `CmdbFileObject` 模型移到 `cmdb_enterprise/models/`；**删** `apps/cmdb/models/file_object.py` 与迁移 `0024_cmdbfileobject.py`；新 app 迁移重建表。
- 上传/下载/删除接口移到 `cmdb_enterprise/urls.py`（社区 `views/instance.py` 的三个 action 移除，社区 `urls.py` 接缝删除）。前端改调 `api/v1/cmdb_enterprise/...`（见风险 R3）。

- 6 个模型 + views/serializers/services 全移到 `cmdb_enterprise/custom_reporting/`；**删**社区双模型 fallback（`models/custom_reporting.py`）、`views/custom_reporting.py`、`serializers/custom_reporting.py`、3 个社区 service 壳、迁移 `0024_custom_reporting.py`。
- `services/model.py` 的 7 个方法改走 `custom_reporting` 注册表契约。
- **明确**：删除社区 fallback 后，custom_reporting 自此为**商业版独占**能力——社区版不再具备该功能（与 overlay 定位一致）。若需保留社区可用的基础版，则属另案，本次不做。

### 达梦
- `apps/cmdb/enterprise/collect` → `apps/cmdb_enterprise/collect`。
- 社区 `services/collect_object_tree.py`、`collection/plugins/loader.py`、`node_configs/__init__.py` 改为从 `collect` 注册表取 `collect_tree`/`plugin_packages`/`node_param_packages`（默认空）。

## 社区清理（净身）

删除：
- 整个 `apps/cmdb/enterprise/` 目录。
- `models/__init__.py` 的 guarded enterprise 块（恢复为纯社区导入，移除 file_object/custom_reporting 企业相关导入）。
- 四接缝：`tasks/__init__.py`、`config.py`、`apps.py`、`urls.py` 中的 guarded enterprise 导入。
- 三域 `extensions.py` 里的 `load_provider`，改为 `registry.get`。
- custom_reporting 的社区 fallback 文件与 `services/model.py` 的裸惰性导入。

保留（社区拥有的通用接口）：`extensions/registry.py`、各域契约类与 `get_*_enterprise_extension()`、调用点。

## 范围边界（本次只动后端）

- **前端不动**：附件前端已在社区 `web/`，本次聚焦后端 app 化。前端商业 overlay（`web/enterprise` 已 gitignore）是独立话题，后续单独议。唯一前端联动：附件接口 URL 命名空间变化（见 R3）。
- **本地 dev 库**：无生产数据前提下，删社区 0024 迁移后，本地需重置/删旧表（新 app 迁移重建）。

## 测试

- 企业测试随 app 走（`apps/cmdb_enterprise/tests/`，gitignore），有 overlay 才跑（`testpaths = apps` 会自动发现）。
- 社区测试改为验证「**无 overlay 时社区行为正常**」：注册表空 → 默认契约 no-op；移除社区 tracked 测试对 enterprise 的硬依赖（现有 `test_file_field_*`、`test_enterprise_extensions` 的企业断言迁入 app 测试）。
- 验收：删掉 `cmdb_enterprise` 目录后，`uv run pytest apps/cmdb` 全绿、`makemigrations cmdb --check` 干净、社区 `grep -r "enterprise" apps/cmdb` 仅余通用注册表/契约（无路径）。

## 风险与缓解

- **R1 删除已提交迁移**：`0024_*` 已提交，删除后已应用它们的本地 dev 库会出现「有记录无文件」。缓解：无生产数据，提供 DB 重置说明；新 app 迁移重建表。
- **R2 跨 app 外键**：custom_reporting 模型若 FK 到社区 cmdb 模型，跨 app FK Django 支持；`CmdbFileObject` 仅存图库 inst_id（无 FK），无碍。实施前核对 custom_reporting 模型的 FK。
- **R3 接口命名空间变化**：附件接口从 `api/v1/cmdb/...` 变 `api/v1/cmdb_enterprise/...`，前端 `api/instance.ts` 的 upload/download/delete 路径需同步改（本次后端改、前端跟一处路径）。
- **R4 采集注册时机**：node_configs/plugins 若在 enterprise `ready()` 前 finalize 会漏达梦。缓解：collect_tree 懒取；插件/NodeParams 在 enterprise `ready()` import 自注册；必要时令社区加载器幂等可重入。
- **R5 app 加载顺序**：依赖 `cmdb_enterprise` 在 `cmdb` 之后 ready()。字母序天然满足；如不放心可在 AppConfig 显式声明依赖或在 ready() 内惰性取注册表。

## 非目标

- 不动前端商业 overlay 化（仅跟随 R3 改一处路径）。
- 不引入独立商业仓库 / 子模块（overlay 目录由现有打包流程交付）。
- 不改其他 app（monitor/opspilot 等）的 enterprise 子目录。

## Verification（端到端）

1. 有 overlay：`apps/cmdb_enterprise` 在位 → 附件/custom_reporting/达梦功能与现状一致；`makemigrations` 干净；企业测试全绿。
2. 无 overlay：删 `apps/cmdb_enterprise` → 社区 cmdb 启动正常、`pytest apps/cmdb` 全绿、无附件/custom_reporting/达梦能力且无报错；`grep -rn "cmdb_enterprise\|enterprise" apps/cmdb` 只剩通用注册表/契约。
3. `makemigrations cmdb_enterprise` 生成自有迁移；新库 `migrate` 重建全部商业表。
