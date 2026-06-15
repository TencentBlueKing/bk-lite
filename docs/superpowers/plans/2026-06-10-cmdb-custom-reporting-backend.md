# CMDB 自定义上报后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让已存在的 CMDB「自定义上报」前端端到端可用——后端业务逻辑全部落在 `apps.cmdb_enterprise`，社区 `apps.cmdb` 只留薄壳 ViewSet 委托到注册表扩展。

**Architecture:** 社区薄壳 `CustomReportingTaskViewSet`（挂 `api/v1/cmdb/` 前缀，对上前端 `/cmdb/api/custom_reporting/...`）→ `get_custom_reporting_extension()`（registry 槽位 `"custom_reporting"`）→ 企业 `provider.py` + `services/*`。复用现有合并引擎 `collection/common.py:Management`、关系 `instance_association_create`、建模 `create_model/create_model_attr`、变更场景 `CUSTOM_REPORTING_CHANGE`、权限 `CmdbPermissionMixin`。模型/迁移/凭据令牌生命周期已存在，仅消费。

**Tech Stack:** Python 3.12 / Django 4.2 / DRF / pytest + pytest-django / FalkorDB（GraphClient）/ Celery。

**先读 spec：** `docs/superpowers/specs/2026-06-10-cmdb-custom-reporting-backend-design.md`。

**测试命令前缀（所有 pytest 在 `server/` 下跑）：** `cd server && uv run pytest <path> -v`

**响应约定：** 社区 cmdb viewset 用 `apps.core.utils.web_utils.WebUtils` 的 `response_success(data)` / `response_error(msg, status_code)`。动手前读 `server/apps/cmdb/views/instance.py` 顶部与 `web/src/utils/request.ts` 确认 envelope 解包方式，列表返回 `{count,next,previous,results}`，其余返回对应对象（字段对齐 `web/src/app/cmdb/types/customReporting.ts`）。

---

## File Structure

社区 `server/apps/cmdb/`：
- **Modify** `custom_reporting/extensions.py` — 扩充契约：新增 HTTP 面方法（list/get/create/update/delete_task、batch_activity、onboarding_document、issue/rotate/revoke_credential、approve/reject_cleanup_review、ingest）。默认 no-op：list 返回空分页，写操作抛 `BaseAppException("自定义上报为商业版能力，未启用")`。
- **Create** `serializers/custom_reporting.py` — DRF 序列化器（task / credential / batch / cleanup_review / detail）。
- **Create** `views/custom_reporting.py` — 薄壳 `CustomReportingTaskViewSet`（session）+ `CustomReportingIngestViewSet`（AllowAny + Bearer）。
- **Modify** `urls.py` — 注册两个 viewset。

企业 `server/apps/cmdb_enterprise/custom_reporting/`：
- **Create** `provider.py` — `CustomReportingProvider(CustomReportingExtension)` + `get_custom_reporting_extension()` 单例。
- **Create** `services/__init__.py`
- **Create** `services/task_service.py` — task CRUD + 组织过滤。
- **Create** `services/credential_service.py` — 签发/轮换/作废。
- **Create** `services/model_service.py` — 快速模型 `bootstrap_model` / `sync_model_group` / `register_model_fields` / `validate_*` / `normalize_identity_keys` / `get_declared_attr_ids`。
- **Create** `services/ingest_service.py` — 编排：token→credential→task、建批次、调 merge/relation/cleanup、写 summary。
- **Create** `services/merge_service.py` — 身份归一化 + 复用 `Management` upsert + 变更记录。
- **Create** `services/relation_service.py` — 关系三情形 + pending 回填。
- **Create** `services/cleanup_service.py` — none/expire/snapshot + 阈值→审核 + approve/reject 执行删除。
- **Create** `services/document_service.py` — 接入文档。
- **Create** `tasks.py` — expire 清理 celery 任务。
- **Modify** `cmdb_enterprise/registry_hooks.py` — 追加 `registry.register("custom_reporting", get_custom_reporting_extension())`。
- **Modify** `cmdb_enterprise/config.py` — 追加 expire 清理 beat 条目。

测试 `server/apps/cmdb_enterprise/tests/`（新增多个 `test_custom_reporting_*.py`）+ 社区 `server/apps/cmdb/tests/test_custom_reporting_extension.py`（扩充 no-op）。

---

## Task 1: 扩充社区契约 + 默认 no-op

**Files:**
- Modify: `server/apps/cmdb/custom_reporting/extensions.py`
- Test: `server/apps/cmdb/tests/test_custom_reporting_extension.py`

- [ ] **Step 1: 写失败测试**——验证默认契约 list 返回空分页、写操作抛“未启用”。

```python
# server/apps/cmdb/tests/test_custom_reporting_extension.py 追加
import pytest
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.cmdb.custom_reporting.extensions import CustomReportingExtension


def test_default_list_tasks_returns_empty_page():
    ext = CustomReportingExtension()
    assert ext.list_tasks(request=None, params={}) == {
        "count": 0, "next": None, "previous": None, "results": [],
    }


def test_default_write_ops_raise_not_enabled():
    ext = CustomReportingExtension()
    for call in (
        lambda: ext.create_task(request=None, payload={}),
        lambda: ext.ingest(request=None, token="x", payload={}),
        lambda: ext.issue_credential(request=None, task_id=1, params={}),
    ):
        with pytest.raises(BaseAppException):
            call()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/cmdb/tests/test_custom_reporting_extension.py -v`
Expected: FAIL（`AttributeError: 'CustomReportingExtension' object has no attribute 'list_tasks'`）

- [ ] **Step 3: 扩充契约**——在 `CustomReportingExtension` 追加方法（保留已有 7 个模型方法不动）。

```python
# server/apps/cmdb/custom_reporting/extensions.py 内，类体追加
from apps.core.exceptions.base_app_exception import BaseAppException

_NOT_ENABLED = "自定义上报为商业版能力，未启用"

class CustomReportingExtension:
    # ... 既有 7 个模型方法保持不变 ...

    # ---- HTTP 面（社区默认 no-op）----
    def list_tasks(self, request, params) -> dict:
        return {"count": 0, "next": None, "previous": None, "results": []}

    def get_task(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def create_task(self, request, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def update_task(self, request, task_id, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def delete_task(self, request, task_id) -> None:
        raise BaseAppException(_NOT_ENABLED)

    def get_batch_activity(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def get_onboarding_document(self, request, task_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def issue_credential(self, request, task_id, params) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def rotate_credential(self, request, task_id, credential_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def revoke_credential(self, request, task_id, credential_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def approve_cleanup_review(self, request, task_id, review_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def reject_cleanup_review(self, request, task_id, review_id) -> dict:
        raise BaseAppException(_NOT_ENABLED)

    def ingest(self, request, token, payload) -> dict:
        raise BaseAppException(_NOT_ENABLED)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd server && uv run pytest apps/cmdb/tests/test_custom_reporting_extension.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/custom_reporting/extensions.py server/apps/cmdb/tests/test_custom_reporting_extension.py
git commit -m "feat(cmdb): 扩充 custom_reporting 契约 HTTP 面 + 社区 no-op"
```

---

## Task 2: 序列化器 + 薄壳 ViewSet + 路由（task CRUD 委托）

**Files:**
- Create: `server/apps/cmdb/serializers/custom_reporting.py`
- Create: `server/apps/cmdb/views/custom_reporting.py`
- Modify: `server/apps/cmdb/urls.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_views.py`

- [ ] **Step 1: 写失败测试**——用 DRF `api_client` 打 list/create/detail/delete，断言走通且委托到扩展。先 mock 注册一个假扩展，验证薄壳确实委托。

```python
# server/apps/cmdb_enterprise/tests/test_custom_reporting_views.py
import pytest
from apps.cmdb.extensions import registry
from apps.cmdb.custom_reporting.extensions import CustomReportingExtension


@pytest.fixture
def fake_overlay():
    calls = {}

    class Fake(CustomReportingExtension):
        def list_tasks(self, request, params):
            calls["list"] = params
            return {"count": 1, "next": None, "previous": None,
                    "results": [{"id": 7, "name": "t"}]}

        def create_task(self, request, payload):
            calls["create"] = payload
            return {"id": 7, "name": payload["name"]}

    registry.register("custom_reporting", Fake())
    yield calls
    registry._registry.pop("custom_reporting", None)


@pytest.mark.django_db
def test_list_tasks_delegates(api_client, fake_overlay):
    resp = api_client.get("/api/v1/cmdb/api/custom_reporting/tasks/")
    assert resp.status_code == 200
    # envelope 解包按 WebUtils 约定，data 内含 results
    body = resp.json()
    assert "list" in fake_overlay


@pytest.mark.django_db
def test_create_task_delegates(api_client, fake_overlay):
    resp = api_client.post(
        "/api/v1/cmdb/api/custom_reporting/tasks/",
        data={"name": "t1", "team": [1], "config": {"mode": "quick"}, "is_enabled": True},
        format="json",
    )
    assert resp.status_code in (200, 201)
    assert fake_overlay["create"]["name"] == "t1"
```

> 注：`api_client` 来自 `server/conftest.py`（含认证）。确认其是否已带 `current_team` cookie；若 viewset 用 `_get_allowed_org_ids` 需要 `current_team`，在测试里 `api_client.cookies["current_team"] = "1"`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_views.py -v`
Expected: FAIL（404，路由未注册）

- [ ] **Step 3a: 写序列化器**

```python
# server/apps/cmdb/serializers/custom_reporting.py
from rest_framework import serializers


class CustomReportingCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    team = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    config = serializers.DictField()
    quick_model = serializers.DictField(required=False)
    is_enabled = serializers.BooleanField(default=True)


class CustomReportingUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    team = serializers.ListField(child=serializers.IntegerField(), required=False)
    config = serializers.DictField(required=False)
    quick_model = serializers.DictField(required=False)
    is_enabled = serializers.BooleanField(required=False)
```

> task/credential/batch 的“出参”形状由 provider 直接返回 dict（字段对齐前端 types），不必再过 serializer；serializer 仅用于入参校验。

- [ ] **Step 3b: 写薄壳 ViewSet**

```python
# server/apps/cmdb/views/custom_reporting.py
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from apps.cmdb.custom_reporting.extensions import get_custom_reporting_extension
from apps.cmdb.serializers.custom_reporting import (
    CustomReportingCreateSerializer,
    CustomReportingUpdateSerializer,
)
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.utils.web_utils import WebUtils


def _ext():
    return get_custom_reporting_extension()


class CustomReportingTaskViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    """薄壳：仅委托到 registry 扩展，业务逻辑在 cmdb_enterprise。"""

    def list(self, request):
        data = _ext().list_tasks(request, request.query_params.dict())
        return WebUtils.response_success(data)

    def create(self, request):
        ser = CustomReportingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = _ext().create_task(request, ser.validated_data)
        return WebUtils.response_success(data)

    def retrieve(self, request, pk=None):
        return WebUtils.response_success(_ext().get_task(request, pk))

    def update(self, request, pk=None):
        ser = CustomReportingUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return WebUtils.response_success(_ext().update_task(request, pk, ser.validated_data))

    def destroy(self, request, pk=None):
        _ext().delete_task(request, pk)
        return WebUtils.response_success({})

    @action(detail=True, methods=["get"], url_path="batch_activity")
    def batch_activity(self, request, pk=None):
        return WebUtils.response_success(_ext().get_batch_activity(request, pk))

    @action(detail=True, methods=["get"], url_path="onboarding_document")
    def onboarding_document(self, request, pk=None):
        return WebUtils.response_success(_ext().get_onboarding_document(request, pk))

    @action(detail=True, methods=["post"], url_path="issue_credential")
    def issue_credential(self, request, pk=None):
        return WebUtils.response_success(_ext().issue_credential(request, pk, request.data))

    @action(detail=True, methods=["post"], url_path="rotate_credential")
    def rotate_credential(self, request, pk=None):
        return WebUtils.response_success(
            _ext().rotate_credential(request, pk, request.data.get("credential_id"))
        )

    @action(detail=True, methods=["post"], url_path="revoke_credential")
    def revoke_credential(self, request, pk=None):
        return WebUtils.response_success(
            _ext().revoke_credential(request, pk, request.data.get("credential_id"))
        )

    @action(detail=True, methods=["post"], url_path=r"reviews/(?P<review_id>[^/]+)/approve")
    def approve_review(self, request, pk=None, review_id=None):
        return WebUtils.response_success(_ext().approve_cleanup_review(request, pk, review_id))

    @action(detail=True, methods=["post"], url_path=r"reviews/(?P<review_id>[^/]+)/reject")
    def reject_review(self, request, pk=None, review_id=None):
        return WebUtils.response_success(_ext().reject_cleanup_review(request, pk, review_id))


class CustomReportingIngestViewSet(viewsets.ViewSet):
    """机器型：Bearer token 鉴权，客户脚本直连。"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        data = _ext().ingest(request, token, request.data)
        return WebUtils.response_success(data)
```

- [ ] **Step 3c: 注册路由**

```python
# server/apps/cmdb/urls.py 追加
from apps.cmdb.views.custom_reporting import (
    CustomReportingTaskViewSet,
    CustomReportingIngestViewSet,
)
router.register(r"api/custom_reporting/tasks", CustomReportingTaskViewSet, basename="custom_reporting_tasks")
router.register(r"api/custom_reporting/ingest", CustomReportingIngestViewSet, basename="custom_reporting_ingest")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_views.py -v`
Expected: PASS（如 envelope/cookie 细节不符，按 `views/instance.py` 实测调整断言；核心是委托被调用）

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/serializers/custom_reporting.py server/apps/cmdb/views/custom_reporting.py server/apps/cmdb/urls.py server/apps/cmdb_enterprise/tests/test_custom_reporting_views.py
git commit -m "feat(cmdb): custom_reporting 薄壳 ViewSet + 序列化器 + 路由"
```

---

## Task 3: 企业 provider 骨架 + 注册（激活 model-behavior skip 测试）

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/provider.py`
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/__init__.py`
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/model_service.py`
- Modify: `server/apps/cmdb_enterprise/registry_hooks.py`
- Test: 已存在 `server/apps/cmdb_enterprise/tests/test_custom_reporting_model_behavior.py`（3 个 skip，注册后自动激活）

- [ ] **Step 1: 确认目标测试当前为 skip**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_model_behavior.py -v`
Expected: 3 SKIPPED（`custom_reporting overlay behavior not registered`）

- [ ] **Step 2: 写 model_service（bootstrap/sync 编排）**——精确匹配 skip 测试断言（见测试文件：`create_model` data 为 `{model_id, model_name, classification_id, group: team}`；身份键去重并保留顺序；为每个身份键 `create_model_attr`，属性形如 `{attr_id, attr_name, attr_group:"default", attr_type:"str", is_only:True, is_required:False, editable:True, option:{}, user_prompt:"", default_value:[]}`；返回值含归一化后的 `identity_keys`、`group: team`；caller 传入的 `group` 被忽略并以 `team` 覆盖）。

```python
# server/apps/cmdb_enterprise/custom_reporting/services/model_service.py
from apps.cmdb.services.model import ModelManage


def _dedupe_keep_order(items):
    seen, out = set(), []
    for it in items or []:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def normalize_identity_keys(identity_keys) -> list:
    return _dedupe_keep_order(identity_keys)


def bootstrap_model(quick_model: dict, team: list, username: str = "admin") -> dict:
    identity_keys = _dedupe_keep_order(quick_model.get("identity_keys"))
    data = {
        "model_id": quick_model["model_id"],
        "model_name": quick_model["model_name"],
        "classification_id": quick_model["classification_id"],
        "group": list(team),
    }
    ModelManage.create_model(data, username=username)
    for key in identity_keys:
        ModelManage.create_model_attr(
            quick_model["model_id"],
            {
                "attr_id": key, "attr_name": key, "attr_group": "default",
                "attr_type": "str", "is_only": True, "is_required": False,
                "editable": True, "option": {}, "user_prompt": "", "default_value": [],
            },
            username=username,
        )
    return {**data, "identity_keys": identity_keys}


def sync_model_group(quick_model: dict, team: list, username: str = "admin") -> dict:
    identity_keys = _dedupe_keep_order(quick_model.get("identity_keys"))
    info = ModelManage.search_model_info(quick_model["model_id"])
    data = {
        "model_id": info["model_id"],
        "model_name": info["model_name"],
        "classification_id": info["classification_id"],
        "group": list(team),
    }
    ModelManage.update_model(info["_id"], data)
    return {**data, "identity_keys": identity_keys}
```

> ⚠️ 对照 `test_custom_reporting_model_behavior.py` 的精确断言逐字核对（model_name/classification_id 取自 `search_model_info` 而非入参）。如断言与上面有出入，以**测试**为准修改实现。

- [ ] **Step 3: 写 provider 骨架并注册**

```python
# server/apps/cmdb_enterprise/custom_reporting/provider.py
from apps.cmdb.custom_reporting.extensions import CustomReportingExtension
from apps.cmdb_enterprise.custom_reporting.services import model_service


class CustomReportingProvider(CustomReportingExtension):
    # ---- 模型编排（Task 3）----
    def normalize_identity_keys(self, identity_keys):
        return model_service.normalize_identity_keys(identity_keys)

    def bootstrap_model(self, quick_model, team, username="admin"):
        return model_service.bootstrap_model(quick_model, team, username=username)

    def sync_model_group(self, quick_model, team, username="admin"):
        return model_service.sync_model_group(quick_model, team, username=username)

    # 其余 HTTP 面方法在后续 Task 覆盖；未覆盖前继承社区默认（抛“未启用”）。


_PROVIDER = CustomReportingProvider()


def get_custom_reporting_extension() -> CustomReportingProvider:
    return _PROVIDER
```

```python
# server/apps/cmdb_enterprise/registry_hooks.py 追加（在已有 register 之后）
from apps.cmdb_enterprise.custom_reporting.provider import (  # noqa: E402
    get_custom_reporting_extension as _custom_reporting_ext,
)
registry.register("custom_reporting", _custom_reporting_ext())
```

- [ ] **Step 4: 跑测试确认激活并通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_model_behavior.py -v`
Expected: 3 PASSED

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb_enterprise/custom_reporting/provider.py server/apps/cmdb_enterprise/custom_reporting/services/ server/apps/cmdb_enterprise/registry_hooks.py
git commit -m "feat(cmdb_enterprise): custom_reporting provider 骨架 + 快速模型编排 + 注册"
```

---

## Task 4: task CRUD service（含组织过滤 + 内联快速模型 + 自动签发凭据）

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/task_service.py`
- Modify: `server/apps/cmdb_enterprise/custom_reporting/provider.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_task_service.py`

- [ ] **Step 1: 写失败测试**（service 层，真实 DB，mock 掉 `model_service.bootstrap_model` 避免触图）。

```python
# server/apps/cmdb_enterprise/tests/test_custom_reporting_task_service.py
import pytest
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask, CustomReportingCredential
from apps.cmdb_enterprise.custom_reporting.services import task_service


@pytest.mark.django_db
def test_create_task_quick_mode_bootstraps_and_issues_credential(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb_enterprise.custom_reporting.services.model_service.bootstrap_model",
        lambda quick_model, team, username="admin": {"model_id": quick_model["model_id"]},
    )
    payload = {
        "name": "业务系统A", "team": [1], "is_enabled": True,
        "config": {"mode": "quick", "cleanup_strategy": "none"},
        "quick_model": {"model_id": "biz_a", "model_name": "业务系统A",
                        "classification_id": "server", "identity_keys": ["name", "biz_id"]},
    }
    result = task_service.create_task(payload, team=[1], username="alice")
    task = CustomReportingTask.objects.get(id=result["id"])
    assert task.name == "业务系统A"
    assert CustomReportingCredential.objects.filter(task=task).count() == 1
    assert result.get("token")  # 创建即返回一次性明文 token


@pytest.mark.django_db
def test_list_tasks_filters_by_org():
    CustomReportingTask.objects.create(name="A", team=[1], config={})
    CustomReportingTask.objects.create(name="B", team=[2], config={})
    page = task_service.list_tasks({}, allowed_org_ids=[1])
    names = {r["name"] for r in page["results"]}
    assert names == {"A"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_task_service.py -v`
Expected: FAIL（`task_service` 无 `create_task`）

- [ ] **Step 3: 写 task_service**——`create_task`（quick 模式先 `bootstrap_model`；建 task；建 credential 并 `issue_token`，把明文 token 放进返回）、`list_tasks`（按 `allowed_org_ids` 用 `CustomReportingTaskScope` 或 `team` overlap 过滤 + 分页）、`get_task`、`update_task`（quick 模式调 `sync_model_group`）、`delete_task`、`serialize_task`（出参对齐前端 type）。

```python
# server/apps/cmdb_enterprise/custom_reporting/services/task_service.py
from django.core.paginator import Paginator
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask, CustomReportingCredential
from apps.cmdb_enterprise.custom_reporting.services import model_service


def serialize_credential(cred):
    return {
        "id": cred.id, "name": cred.name, "credential_type": cred.credential_type,
        "credential_data": cred.credential_data, "is_enabled": cred.is_enabled,
        "last_used_at": cred.last_used_at.isoformat() if cred.last_used_at else None,
        "created_at": cred.created_at.isoformat(), "updated_at": cred.updated_at.isoformat(),
    }


def serialize_task(task, *, with_credential=True):
    data = {
        "id": task.id, "name": task.name, "team": task.team, "config": task.config,
        "is_enabled": task.is_enabled, "created_by": task.created_by,
        "created_at": task.created_at.isoformat(), "updated_by": task.updated_by,
        "updated_at": task.updated_at.isoformat(),
        "last_reported_at": task.last_reported_at.isoformat() if task.last_reported_at else None,
    }
    if with_credential:
        cred = task.credentials.first()
        data["credential"] = serialize_credential(cred) if cred else None
    return data


def list_tasks(params, allowed_org_ids):
    qs = CustomReportingTask.objects.all().order_by("-created_at")
    if allowed_org_ids is not None:
        ids = list(CustomReportingTaskScope_ids(allowed_org_ids))
        qs = qs.filter(id__in=ids)
    if params.get("name"):
        qs = qs.filter(name__icontains=params["name"])
    page = int(params.get("page", 1)); size = int(params.get("page_size", 10))
    paginator = Paginator(qs, size)
    objs = paginator.get_page(page)
    return {"count": paginator.count, "next": None, "previous": None,
            "results": [serialize_task(t) for t in objs]}


def CustomReportingTaskScope_ids(allowed_org_ids):
    from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTaskScope
    return CustomReportingTaskScope.objects.filter(
        team_id__in=allowed_org_ids
    ).values_list("task_id", flat=True).distinct()


def create_task(payload, team, username="admin"):
    config = dict(payload.get("config") or {})
    if config.get("mode") == "quick" and payload.get("quick_model"):
        model_service.bootstrap_model(payload["quick_model"], team=payload["team"], username=username)
        config["model_id"] = payload["quick_model"]["model_id"]
    task = CustomReportingTask.objects.create(
        name=payload["name"], team=payload["team"], config=config,
        is_enabled=payload.get("is_enabled", True),
        created_by=username, updated_by=username,
    )
    cred = CustomReportingCredential.objects.create(
        task=task, name=f"{task.name}-default", credential_type="api_token",
        credential_data={}, created_by=username, updated_by=username,
    )
    token = cred.issue_token()
    data = serialize_task(task)
    data["token"] = token
    return data


def get_task(task_id):
    return serialize_task(CustomReportingTask.objects.get(id=task_id))


def update_task(task_id, payload, username="admin"):
    task = CustomReportingTask.objects.get(id=task_id)
    for f in ("name", "team", "is_enabled"):
        if f in payload:
            setattr(task, f, payload[f])
    if "config" in payload:
        task.config = {**task.config, **payload["config"]}
    task.updated_by = username
    task.save()
    if task.config.get("mode") == "quick" and payload.get("quick_model"):
        model_service.sync_model_group(payload["quick_model"], team=task.team, username=username)
    return serialize_task(task)


def delete_task(task_id):
    CustomReportingTask.objects.filter(id=task_id).delete()
```

> 同组织同名唯一已由 `CustomReportingTaskScope` 的 `unique_together(team_id,name)` 在 DB 层保证；捕获 `IntegrityError` 转 `BaseAppException("同组织下任务名已存在")`。

- [ ] **Step 3b: provider 接上 task 方法**（用 `CmdbPermissionMixin` 取 `allowed_org_ids`；参考 `views/instance.py:_get_allowed_org_ids`）。

```python
# provider.py 追加
from apps.cmdb_enterprise.custom_reporting.services import task_service

class CustomReportingProvider(CustomReportingExtension):
    # ...
    def list_tasks(self, request, params):
        return task_service.list_tasks(params, allowed_org_ids=self._allowed_orgs(request))

    def create_task(self, request, payload):
        return task_service.create_task(payload, team=payload["team"], username=request.user.username)

    def get_task(self, request, task_id):
        return task_service.get_task(task_id)

    def update_task(self, request, task_id, payload):
        return task_service.update_task(task_id, payload, username=request.user.username)

    def delete_task(self, request, task_id):
        task_service.delete_task(task_id)

    @staticmethod
    def _allowed_orgs(request):
        from apps.cmdb.views.instance import InstanceViewSet
        try:
            return InstanceViewSet._get_allowed_org_ids(request)
        except Exception:
            return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_task_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(cmdb_enterprise): custom_reporting task CRUD service + provider 接线"
```

---

## Task 5: 凭据三接口（签发/轮换/作废）

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/credential_service.py`
- Modify: `server/apps/cmdb_enterprise/custom_reporting/provider.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_credential_service.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask, CustomReportingCredential
from apps.cmdb_enterprise.custom_reporting.services import credential_service


@pytest.fixture
def task(db):
    return CustomReportingTask.objects.create(name="t", team=[1], config={})


@pytest.mark.django_db
def test_rotate_returns_new_plain_token(task):
    cred = CustomReportingCredential.objects.create(task=task, name="c", credential_type="api_token", credential_data={})
    cred.issue_token(token="old")
    result = credential_service.rotate(task.id, cred.id)
    assert result["token"] and result["token"] != "old"
    cred.refresh_from_db()
    assert cred.matches_token(result["token"]) is True


@pytest.mark.django_db
def test_revoke_disables_and_blocks_token(task):
    cred = CustomReportingCredential.objects.create(task=task, name="c", credential_type="api_token", credential_data={})
    cred.issue_token(token="tok")
    result = credential_service.revoke(task.id, cred.id)
    assert result == {"credential_id": cred.id, "is_enabled": False}
    cred.refresh_from_db()
    assert cred.matches_token("tok") is False
```

- [ ] **Step 2: 跑确认失败** — `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_credential_service.py -v` → FAIL

- [ ] **Step 3: 写 credential_service**

```python
# server/apps/cmdb_enterprise/custom_reporting/services/credential_service.py
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingCredential
from apps.cmdb_enterprise.custom_reporting.services.task_service import serialize_credential


def _get(task_id, credential_id):
    return CustomReportingCredential.objects.get(id=credential_id, task_id=task_id)


def issue(task_id, params):
    cred = CustomReportingCredential.objects.filter(task_id=task_id).first()
    if cred is None:
        cred = CustomReportingCredential.objects.create(
            task_id=task_id, name=(params or {}).get("name") or "default",
            credential_type="api_token", credential_data={},
        )
    token = cred.issue_token()
    return {"credential": serialize_credential(cred), "token": token}


def rotate(task_id, credential_id):
    cred = _get(task_id, credential_id)
    token = cred.rotate_token()
    return {"credential": serialize_credential(cred), "token": token}


def revoke(task_id, credential_id):
    cred = _get(task_id, credential_id)
    cred.revoke_token()
    return {"credential_id": cred.id, "is_enabled": cred.is_enabled}
```

- [ ] **Step 3b: provider 接上**

```python
# provider.py 追加
from apps.cmdb_enterprise.custom_reporting.services import credential_service
    def issue_credential(self, request, task_id, params):
        return credential_service.issue(task_id, params)
    def rotate_credential(self, request, task_id, credential_id):
        return credential_service.rotate(task_id, credential_id)
    def revoke_credential(self, request, task_id, credential_id):
        return credential_service.revoke(task_id, credential_id)
```

- [ ] **Step 4: 跑确认通过** → PASS
- [ ] **Step 5: 提交** — `git add -A && git commit -m "feat(cmdb_enterprise): custom_reporting 凭据签发/轮换/作废"`

---

## Task 6: 接入文档

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/document_service.py`
- Modify: `provider.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_document_service.py`

- [ ] **Step 1: 写失败测试**——断言返回 `endpoint / auth_header{name,format} / identity_keys / example_payload{instances,relations,batch_metadata}`，identity_keys 取自 task.config。

```python
import pytest
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask
from apps.cmdb_enterprise.custom_reporting.services import document_service


@pytest.mark.django_db
def test_onboarding_document_shape():
    task = CustomReportingTask.objects.create(
        name="t", team=[1],
        config={"mode": "quick", "model_id": "biz_a", "identity_keys": ["name", "biz_id"]},
    )
    doc = document_service.build(task.id)
    assert doc["endpoint"].endswith("/cmdb/api/custom_reporting/ingest/")
    assert doc["auth_header"] == {"name": "Authorization", "format": "Bearer <token>"}
    assert doc["identity_keys"] == ["name", "biz_id"]
    assert set(doc["example_payload"]) == {"instances", "relations", "batch_metadata"}
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 写 document_service**

```python
# server/apps/cmdb_enterprise/custom_reporting/services/document_service.py
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask

INGEST_PATH = "/cmdb/api/custom_reporting/ingest/"


def build(task_id):
    task = CustomReportingTask.objects.get(id=task_id)
    identity_keys = task.config.get("identity_keys") or (
        task.config.get("quick_model", {}).get("identity_keys") if task.config.get("quick_model") else []
    ) or []
    example_instance = {k: f"<{k}>" for k in identity_keys}
    return {
        "endpoint": INGEST_PATH,
        "auth_header": {"name": "Authorization", "format": "Bearer <token>"},
        "identity_keys": identity_keys,
        "example_payload": {
            "instances": [example_instance],
            "relations": [{
                "source": example_instance,
                "target": {"model_id": "<target_model>", "identity": {"<key>": "<value>"}},
                "asst_id": "<model_asst_id>",
            }],
            "batch_metadata": {"source": "<your-script>", "reported_at": "<iso8601>"},
        },
    }
```

> endpoint 是否需绝对 URL：先返回相对路径（前端「接入指引」展示用），如需绝对地址，从 `request` 或 settings 拼 host，放 Task 末尾可选增强。

- [ ] **Step 3b: provider 接上** `get_onboarding_document` → `document_service.build(task_id)`
- [ ] **Step 4: 跑确认通过** → PASS
- [ ] **Step 5: 提交** — `git commit -m "feat(cmdb_enterprise): custom_reporting 接入文档"`

---

## Task 7: ingest + 身份归一化 + 实例 upsert + 批次（none 策略）

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py`
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/ingest_service.py`
- Modify: `provider.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_merge_service.py`, `..._ingest_service.py`

- [ ] **Step 1a: 写 merge 身份归一化失败测试**（纯函数，无 DB）。

```python
# test_custom_reporting_merge_service.py
from apps.cmdb_enterprise.custom_reporting.services import merge_service


def test_coerce_identity_values_by_attr_type():
    attrs = [{"attr_id": "biz_id", "attr_type": "int"}, {"attr_id": "name", "attr_type": "str"}]
    assert merge_service.coerce_identity({"biz_id": "123", "name": 5}, attrs) == {"biz_id": 123, "name": "5"}
    # 反向：int 上报到 str 字段
    assert merge_service.coerce_identity({"biz_id": 123}, attrs) == {"biz_id": 123}
```

- [ ] **Step 1b: 写 ingest 失败测试**（DB + mock 图层）——token 命中、批次创建、none 幂等（同 identity 第二次为 update 非新建）。

```python
# test_custom_reporting_ingest_service.py
import pytest
from apps.cmdb_enterprise.custom_reporting.models import (
    CustomReportingTask, CustomReportingCredential, CustomReportingBatch)
from apps.cmdb_enterprise.custom_reporting.services import ingest_service


@pytest.fixture
def task_with_token(db):
    task = CustomReportingTask.objects.create(
        name="t", team=[1], is_enabled=True,
        config={"mode": "quick", "model_id": "biz_a", "identity_keys": ["biz_id"],
                "cleanup_strategy": "none"})
    cred = CustomReportingCredential.objects.create(task=task, name="c", credential_type="api_token", credential_data={})
    token = cred.issue_token(token="tok-1")
    return task, token


@pytest.mark.django_db
def test_ingest_rejects_bad_token(task_with_token):
    from apps.core.exceptions.base_app_exception import BaseAppException
    with pytest.raises(BaseAppException):
        ingest_service.ingest(token="WRONG", payload={"instances": []})


@pytest.mark.django_db
def test_ingest_creates_batch_and_upserts(task_with_token, monkeypatch):
    task, token = task_with_token
    upserts = []
    monkeypatch.setattr(
        "apps.cmdb_enterprise.custom_reporting.services.merge_service.merge_instances",
        lambda task, model_id, instances, operator: upserts.append(instances)
        or {"created": len(instances), "updated": 0, "deleted": 0, "errors": 0, "covered_ids": []},
    )
    result = ingest_service.ingest(token=token, payload={"instances": [{"biz_id": "1"}], "relations": []})
    batch = CustomReportingBatch.objects.get(task=task)
    assert batch.status == CustomReportingBatch.STATUS_SUCCESS
    assert batch.summary["created"] == 1
    assert batch.summary["instances_received"] == 1
```

- [ ] **Step 2: 跑确认失败** → FAIL

- [ ] **Step 3a: 写 merge_service**——`coerce_identity`、`merge_instances`（复用 `Management` 算 add/update，再调 `add_inst`/`update_inst`；写 `CUSTOM_REPORTING_CHANGE` 变更记录；给覆盖实例打 `cr_last_reported_at`）。

```python
# server/apps/cmdb_enterprise/custom_reporting/services/merge_service.py
from django.utils import timezone
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.collection.common import Management
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.model import ModelManage

_INT_TYPES = {"int", "integer"}


def coerce_identity(identity: dict, attrs: list) -> dict:
    type_map = {a["attr_id"]: a.get("attr_type") for a in attrs}
    out = {}
    for k, v in (identity or {}).items():
        t = type_map.get(k)
        if t in _INT_TYPES:
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                out[k] = v
        elif t == "str" and not isinstance(v, bool):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _query_existing(model_id):
    with GraphClient() as ag:
        items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
    return items


def merge_instances(task, model_id, instances, operator):
    attrs = ModelManage.search_model_attr(model_id)
    identity_keys = task.config.get("identity_keys") or []
    now = timezone.now()
    new_data = []
    for inst in instances:
        norm = coerce_identity({k: inst.get(k) for k in identity_keys}, attrs)
        merged = {**inst, **norm, "cr_last_reported_at": now.isoformat()}
        new_data.append(merged)
    old_data = _query_existing(model_id)
    # 归一化 old_data 的 identity 以便 tuple key 对齐
    for o in old_data:
        o.update(coerce_identity({k: o.get(k) for k in identity_keys}, attrs))

    mgmt = Management(
        organization=task.team, inst_name="", model_id=model_id,
        old_data=old_data, new_data=new_data, unique_keys=identity_keys,
        collect_time=now, task_id=f"cr_{task.id}", data_cleanup_strategy=None,
    )
    add_res = mgmt.add_inst(mgmt.add_list)
    upd_res = mgmt.update_inst(mgmt.update_list)
    covered_ids = [i["inst_info"]["_id"] for i in add_res["success"] + upd_res["success"]]
    _write_change_records(model_id, add_res, upd_res, operator)
    return {
        "created": len(add_res["success"]), "updated": len(upd_res["success"]),
        "deleted": 0, "errors": len(add_res["failed"]) + len(upd_res["failed"]),
        "covered_ids": covered_ids, "old_data": old_data, "new_data": new_data,
        "attrs": attrs, "identity_keys": identity_keys,
    }


def _write_change_records(model_id, add_res, upd_res, operator):
    from apps.cmdb.utils.change_record import create_custom_reporting_change_record
    from apps.cmdb.models.change_record import CREATE_INST, UPDATE_INST
    for item in add_res["success"]:
        e = item["inst_info"]
        create_custom_reporting_change_record(
            inst_id=e["_id"], model_id=model_id, label="自定义上报", _type=CREATE_INST,
            after_data=e, operator=operator, message="自定义上报新增实例")
    for item in upd_res["success"]:
        e = item["inst_info"]
        create_custom_reporting_change_record(
            inst_id=e["_id"], model_id=model_id, label="自定义上报", _type=UPDATE_INST,
            after_data=e, operator=operator, message="自定义上报更新实例")
```

> 核对 `CREATE_INST/UPDATE_INST` 与 `create_custom_reporting_change_record` 签名（`apps/cmdb/models/change_record.py`、`apps/cmdb/utils/change_record.py`）。若 label/type 取值不同，以源码为准。

- [ ] **Step 3b: 写 ingest_service**——token→credential→task、建批次、调 merge、（none 策略本任务不删）、关系占位（Task 8 接）、写 summary、刷新 `last_reported_at`。

```python
# server/apps/cmdb_enterprise/custom_reporting/services/ingest_service.py
from django.utils import timezone
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingCredential, CustomReportingBatch
from apps.cmdb_enterprise.custom_reporting.services import merge_service


def _resolve_credential(token):
    if not token:
        raise BaseAppException("缺少上报令牌")
    for cred in CustomReportingCredential.objects.select_related("task").filter(is_enabled=True):
        if cred.matches_token(token):
            return cred
    raise BaseAppException("上报令牌无效或已作废")


def ingest(token, payload, operator="custom_reporting"):
    cred = _resolve_credential(token)
    task = cred.task
    if not task.is_enabled:
        raise BaseAppException("任务已停用")
    cred.mark_used()

    instances = payload.get("instances") or []
    relations = payload.get("relations") or []
    batch = CustomReportingBatch.objects.create(task=task, status=CustomReportingBatch.STATUS_RUNNING)
    try:
        model_id = task.config.get("model_id")
        merge_result = merge_service.merge_instances(task, model_id, instances, operator)
        # Task 8 接关系；Task 9 接 cleanup。此处仅 none。
        summary = {
            "instances_received": len(instances), "relations_received": len(relations),
            "created": merge_result["created"], "updated": merge_result["updated"],
            "deleted": merge_result["deleted"], "errors": merge_result["errors"],
            "pending_relations": 0,
        }
        batch.summary = summary
        batch.status = CustomReportingBatch.STATUS_SUCCESS
        batch.save()
        task.last_reported_at = timezone.now()
        task.save(update_fields=["last_reported_at", "updated_at"])
        return {"batch_id": batch.id, "summary": summary}
    except Exception as e:  # noqa: BLE001
        batch.status = CustomReportingBatch.STATUS_FAILED
        batch.summary = {"error": getattr(e, "message", str(e))}
        batch.save()
        raise
```

- [ ] **Step 3c: provider 接上** `ingest` → `ingest_service.ingest(token, payload, operator=getattr(request.user,'username','custom_reporting'))`
- [ ] **Step 4: 跑确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_merge_service.py apps/cmdb_enterprise/tests/test_custom_reporting_ingest_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交** — `git commit -m "feat(cmdb_enterprise): custom_reporting ingest + 身份归一化 + 实例 upsert + 批次(none)"`

---

## Task 8: 关系上报（互引 / 现有 / pending 回填）

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/relation_service.py`
- Modify: `ingest_service.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_relation_service.py`

- [ ] **Step 1: 写失败测试**（mock 图层 + DB）——三情形：目标已存在→建边；目标未落地→落 `CustomReportingPendingRelation`；后续批次目标落地→回填并删 pending。

```python
import pytest
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask, CustomReportingPendingRelation
from apps.cmdb_enterprise.custom_reporting.services import relation_service


@pytest.fixture
def task(db):
    return CustomReportingTask.objects.create(name="t", team=[1], config={"model_id": "biz_a"})


@pytest.mark.django_db
def test_existing_target_creates_edge(task, monkeypatch):
    created = []
    monkeypatch.setattr(relation_service, "_resolve_instance",
                        lambda model_id, identity: {"_id": 99} if identity else None)
    monkeypatch.setattr(relation_service, "_create_edge",
                        lambda src, dst, asst_id, operator: created.append((src, dst, asst_id)))
    relations = [{"source": {"_id": 1}, "target": {"model_id": "biz", "identity": {"k": "v"}}, "asst_id": "a"}]
    result = relation_service.process(task, relations, {("biz_a", ("1",)): 1}, operator="u")
    assert created == [(1, 99, "a")]
    assert result["pending"] == 0


@pytest.mark.django_db
def test_missing_target_becomes_pending(task, monkeypatch):
    monkeypatch.setattr(relation_service, "_resolve_instance", lambda model_id, identity: None)
    relations = [{"source": {"_id": 1}, "target": {"model_id": "biz", "identity": {"k": "v"}}, "asst_id": "a"}]
    result = relation_service.process(task, relations, {}, operator="u")
    assert result["pending"] == 1
    assert CustomReportingPendingRelation.objects.filter(task=task).count() == 1


@pytest.mark.django_db
def test_backfill_resolves_pending(task, monkeypatch):
    CustomReportingPendingRelation.objects.create(
        task=task, source_model_id="biz_a", target_model_id="biz",
        relation_payload={"source": {"_id": 1}, "target": {"model_id": "biz", "identity": {"k": "v"}}, "asst_id": "a"})
    created = []
    monkeypatch.setattr(relation_service, "_resolve_instance", lambda model_id, identity: {"_id": 77})
    monkeypatch.setattr(relation_service, "_create_edge",
                        lambda src, dst, asst_id, operator: created.append((src, dst, asst_id)))
    n = relation_service.backfill(task, operator="u")
    assert n == 1 and created == [(1, 77, "a")]
    assert CustomReportingPendingRelation.objects.filter(task=task).count() == 0
```

- [ ] **Step 2: 跑确认失败** → FAIL

- [ ] **Step 3: 写 relation_service**——`process`（遍历关系：解析源/目标实例；目标在则 `_create_edge`，不在则落 pending；快速模型目标可被引用）、`backfill`（重试 pending）、`_resolve_instance`（复用归一化 + `query_entity_by_identity`）、`_create_edge`（复用 `instance_association_create`，scenario=CUSTOM_REPORTING_CHANGE，幂等：边已存在则忽略/更新）。

```python
# server/apps/cmdb_enterprise/custom_reporting/services/relation_service.py
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.models.change_record import CUSTOM_REPORTING_CHANGE
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingPendingRelation
from apps.core.exceptions.base_app_exception import BaseAppException


def _resolve_instance(model_id, identity):
    inst = InstanceManage.query_entity_by_identity(model_id, identity)
    return inst or None


def _create_edge(src_id, dst_id, asst_id, operator):
    try:
        InstanceManage.instance_association_create(
            {"src_inst_id": src_id, "dst_inst_id": dst_id, "model_asst_id": asst_id},
            operator=operator, scenario=CUSTOM_REPORTING_CHANGE)
    except BaseAppException as e:
        if "repetition" in getattr(e, "message", str(e)):
            return  # 幂等：已存在
        raise


def _src_id(source, batch_index):
    # source 可能是本批刚 upsert 的实例（带 _id），或 identity 引用
    if "_id" in source:
        return source["_id"]
    key = (source.get("model_id"), tuple(str(v) for v in source.get("identity", {}).values()))
    return batch_index.get(key)


def process(task, relations, batch_index, operator):
    pending = 0
    for rel in relations or []:
        src_id = _src_id(rel["source"], batch_index)
        tgt = rel["target"]
        target_inst = _resolve_instance(tgt["model_id"], tgt.get("identity"))
        if src_id and target_inst:
            _create_edge(src_id, target_inst["_id"], rel["asst_id"], operator)
        else:
            CustomReportingPendingRelation.objects.create(
                task=task, source_model_id=task.config.get("model_id", ""),
                target_model_id=tgt["model_id"], relation_payload=rel)
            pending += 1
    return {"pending": pending}


def backfill(task, operator):
    resolved = 0
    for pr in CustomReportingPendingRelation.objects.filter(task=task):
        rel = pr.relation_payload
        src_id = rel.get("source", {}).get("_id")
        target_inst = _resolve_instance(rel["target"]["model_id"], rel["target"].get("identity"))
        if src_id and target_inst:
            _create_edge(src_id, target_inst["_id"], rel["asst_id"], operator)
            pr.delete()
            resolved += 1
    return resolved
```

- [ ] **Step 3b: ingest_service 接关系**——merge 后构造 `batch_index`（identity tuple→新 inst_id），调 `relation_service.process` 与 `backfill`，把 `pending_relations` 计入 summary。

```python
# ingest_service.ingest 内，merge_result 之后：
from apps.cmdb_enterprise.custom_reporting.services import relation_service
batch_index = _build_batch_index(merge_result)  # {(model_id,(idval,...)): inst_id}
rel_result = relation_service.process(task, relations, batch_index, operator)
relation_service.backfill(task, operator)
summary["pending_relations"] = rel_result["pending"]
```

> `_build_batch_index`：用 merge_result 的 covered_ids + new_data 的 identity 值组 key。实现见 merge_service 返回的 `new_data`/`identity_keys`。

- [ ] **Step 4: 跑确认通过** → PASS
- [ ] **Step 5: 提交** — `git commit -m "feat(cmdb_enterprise): custom_reporting 关系上报 + pending 回填"`

---

## Task 9: 清理策略（expire / snapshot + 阈值→审核）+ 审核 approve/reject + expire celery

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/cleanup_service.py`
- Create: `server/apps/cmdb_enterprise/custom_reporting/tasks.py`
- Modify: `ingest_service.py`, `provider.py`, `cmdb_enterprise/config.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_cleanup_service.py`

- [ ] **Step 1: 写失败测试**——(a) snapshot 删除比例 ≤ 阈值→直接删；(b) > 阈值→建 pending CleanupReview 不删；(c) approve→执行删除并置 approved；(d) reject→置 rejected 不删；(e) expire celery 删超期未覆盖实例。

```python
import pytest
from apps.cmdb_enterprise.custom_reporting.models import (
    CustomReportingTask, CustomReportingBatch, CustomReportingCleanupReview)
from apps.cmdb_enterprise.custom_reporting.services import cleanup_service


@pytest.fixture
def batch(db):
    task = CustomReportingTask.objects.create(
        name="t", team=[1],
        config={"model_id": "biz_a", "cleanup_strategy": "snapshot",
                "snapshot_delete_ratio_threshold": 30})
    return task, CustomReportingBatch.objects.create(task=task, status=CustomReportingBatch.STATUS_RUNNING)


@pytest.mark.django_db
def test_snapshot_over_threshold_creates_pending_review(batch, monkeypatch):
    task, b = batch
    deleted = []
    monkeypatch.setattr(cleanup_service, "_delete_instances", lambda ids, operator: deleted.extend(ids))
    # old 10 个, 本批覆盖 5 个 → 删 5 个 = 50% > 30% → 待审核
    result = cleanup_service.apply_snapshot(
        task, b, old_ids=list(range(10)), covered_ids=list(range(5)), operator="u")
    assert deleted == []
    assert result["deleted"] == 0 and result["review_created"] is True
    assert CustomReportingCleanupReview.objects.filter(batch=b, status="pending").count() == 1


@pytest.mark.django_db
def test_snapshot_under_threshold_deletes(batch, monkeypatch):
    task, b = batch
    deleted = []
    monkeypatch.setattr(cleanup_service, "_delete_instances", lambda ids, operator: deleted.extend(ids))
    # old 10, 覆盖 9 → 删 1 = 10% ≤ 30% → 直接删
    result = cleanup_service.apply_snapshot(
        task, b, old_ids=list(range(10)), covered_ids=list(range(9)), operator="u")
    assert deleted == [9] and result["deleted"] == 1


@pytest.mark.django_db
def test_approve_review_executes_delete(batch, monkeypatch):
    task, b = batch
    review = CustomReportingCleanupReview.objects.create(
        batch=b, status="pending", review_payload={"delete_ids": [1, 2, 3]})
    deleted = []
    monkeypatch.setattr(cleanup_service, "_delete_instances", lambda ids, operator: deleted.extend(ids))
    cleanup_service.approve(task.id, review.id, operator="boss")
    review.refresh_from_db()
    assert review.status == "approved" and review.reviewed_by == "boss"
    assert deleted == [1, 2, 3]
```

- [ ] **Step 2: 跑确认失败** → FAIL

- [ ] **Step 3: 写 cleanup_service**

```python
# server/apps/cmdb_enterprise/custom_reporting/services/cleanup_service.py
from django.utils import timezone
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb_enterprise.custom_reporting.models import CustomReportingCleanupReview
from apps.core.exceptions.base_app_exception import BaseAppException


def _delete_instances(inst_ids, operator):
    if inst_ids:
        InstanceManage.batch_instance_delete(list(inst_ids), operator)  # 核对真实方法名/签名


def apply_snapshot(task, batch, old_ids, covered_ids, operator):
    delete_ids = [i for i in old_ids if i not in set(covered_ids)]
    if not old_ids or not delete_ids:
        return {"deleted": 0, "review_created": False}
    threshold = task.config.get("snapshot_delete_ratio_threshold") or 0
    ratio = len(delete_ids) / len(old_ids) * 100
    if threshold and ratio > threshold:
        CustomReportingCleanupReview.objects.create(
            batch=batch, status=CustomReportingCleanupReview.STATUS_PENDING,
            review_payload={"delete_ids": delete_ids, "ratio": ratio, "threshold": threshold})
        return {"deleted": 0, "review_created": True}
    _delete_instances(delete_ids, operator)
    return {"deleted": len(delete_ids), "review_created": False}


def approve(task_id, review_id, operator):
    review = CustomReportingCleanupReview.objects.select_related("batch__task").get(
        id=review_id, batch__task_id=task_id)
    if review.status != CustomReportingCleanupReview.STATUS_PENDING:
        raise BaseAppException("该审核已处理")
    _delete_instances(review.review_payload.get("delete_ids", []), operator)
    review.status = CustomReportingCleanupReview.STATUS_APPROVED
    review.reviewed_by = operator
    review.reviewed_at = timezone.now()
    review.save()
    return {"id": review.id, "status": review.status}


def reject(task_id, review_id, operator):
    review = CustomReportingCleanupReview.objects.get(id=review_id, batch__task_id=task_id)
    if review.status != CustomReportingCleanupReview.STATUS_PENDING:
        raise BaseAppException("该审核已处理")
    review.status = CustomReportingCleanupReview.STATUS_REJECTED
    review.reviewed_by = operator
    review.reviewed_at = timezone.now()
    review.save()
    return {"id": review.id, "status": review.status}


def expire_cleanup(now=None):
    """删除所有 expire 任务模型下、cr_last_reported_at 超期未覆盖的实例。"""
    from apps.cmdb_enterprise.custom_reporting.models import CustomReportingTask
    now = now or timezone.now()
    for task in CustomReportingTask.objects.filter(config__cleanup_strategy="expire", is_enabled=True):
        days = task.config.get("expire_days") or 0
        if not days:
            continue
        cutoff = now - timezone.timedelta(days=days)
        stale_ids = _query_stale_instance_ids(task.config.get("model_id"), task.team, cutoff)
        _delete_instances(stale_ids, "custom_reporting_expire")


def _query_stale_instance_ids(model_id, team, cutoff):
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient
    params = [{"field": "model_id", "type": "str=", "value": model_id},
              {"field": "cr_last_reported_at", "type": "str<", "value": cutoff.isoformat()}]
    with GraphClient() as ag:
        items, _ = ag.query_entity(INSTANCE, params)
    return [i["_id"] for i in items]
```

> ⚠️ 三个待核对：(1) 真实批量删除实例方法（在 `apps/cmdb/services/instance.py` 找 `batch_instance_delete` / `instance_batch_delete` / `delete_inst`，对齐签名）；(2) 图查询时间比较算子（`str<` 是否支持，否则改为拉取后 Python 过滤）；(3) `config__cleanup_strategy` JSON 查询在当前 DB 引擎是否可用，不可用则全量拉取再过滤。

- [ ] **Step 3b: ingest_service 接 snapshot**——按 `task.config.cleanup_strategy` 分派：`snapshot` 调 `apply_snapshot(task, batch, old_ids=[o["_id"] for o in merge_result["old_data"]], covered_ids=merge_result["covered_ids"], operator=...)`，把 `deleted` 计入 summary。`expire` 由 celery 异步处理，ingest 不删。

- [ ] **Step 3c: provider 接审核** `approve_cleanup_review/reject_cleanup_review` → `cleanup_service.approve/reject(task_id, review_id, operator=request.user.username)`

- [ ] **Step 3d: celery 任务 + beat**

```python
# server/apps/cmdb_enterprise/custom_reporting/tasks.py
from celery import shared_task
from apps.cmdb_enterprise.custom_reporting.services import cleanup_service


@shared_task
def custom_reporting_expire_cleanup():
    cleanup_service.expire_cleanup()
```

```python
# server/apps/cmdb_enterprise/config.py 的 CELERY_BEAT_SCHEDULE 追加
"custom_reporting_expire_cleanup": {
    "task": "apps.cmdb_enterprise.custom_reporting.tasks.custom_reporting_expire_cleanup",
    "schedule": crontab(hour="4", minute="0"),
},
```

- [ ] **Step 4: 跑确认通过**

Run: `cd server && uv run pytest apps/cmdb_enterprise/tests/test_custom_reporting_cleanup_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交** — `git commit -m "feat(cmdb_enterprise): custom_reporting 三档清理 + 快照审核 + expire celery"`

---

## Task 10: batch_activity / detail 聚合 + 变更场景可检索

**Files:**
- Create: `server/apps/cmdb_enterprise/custom_reporting/services/activity_service.py`（或并入 task_service）
- Modify: `provider.py`（`get_batch_activity`、`get_task` 补 `recent_batches`/`review_status_summary`）
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_activity.py`

- [ ] **Step 1: 写失败测试**——`get_batch_activity` 返回 `{task_id, batches[], cleanup_reviews[], review_status_summary{pending,approved,rejected,total}}`；`get_task` 详情含 `recent_batches`、`review_status_summary`；变更记录可按 `scenario=custom_reporting_change` 检索（断言 ingest 后存在该 scenario 记录）。

```python
import pytest
from apps.cmdb_enterprise.custom_reporting.models import (
    CustomReportingTask, CustomReportingBatch, CustomReportingCleanupReview)
from apps.cmdb_enterprise.custom_reporting.services import activity_service


@pytest.mark.django_db
def test_batch_activity_aggregates_reviews():
    task = CustomReportingTask.objects.create(name="t", team=[1], config={})
    b = CustomReportingBatch.objects.create(task=task, status="success",
                                            summary={"created": 1})
    CustomReportingCleanupReview.objects.create(batch=b, status="pending", review_payload={})
    CustomReportingCleanupReview.objects.create(batch=b, status="approved", review_payload={})
    data = activity_service.batch_activity(task.id)
    assert data["task_id"] == task.id
    assert data["review_status_summary"] == {"pending": 1, "approved": 1, "rejected": 0, "total": 2}
    assert len(data["batches"]) == 1
```

- [ ] **Step 2: 跑确认失败** → FAIL
- [ ] **Step 3: 写 activity_service** + provider 接线（`get_batch_activity`、扩展 `get_task` 详情聚合 `recent_batches`/`review_status_summary`，字段对齐 `CustomReportingTaskDetail`/`CustomReportingBatchActivityResponse`）。
- [ ] **Step 4: 跑确认通过** → PASS
- [ ] **Step 5: 提交** — `git commit -m "feat(cmdb_enterprise): custom_reporting 批次活动聚合 + 详情"`

---

## Task 11: 验收 BDD（端到端主流程）

**Files:**
- Create: `server/apps/cmdb_enterprise/tests/bdd/custom_reporting.feature`
- Create: `server/apps/cmdb_enterprise/tests/bdd/test_custom_reporting_bdd.py`

- [ ] **Step 1: 写 feature（中文 Gherkin）**——覆盖验收主线：创建快速模型任务→签发凭据→脚本携带 token ingest 实例+关系→批次成功→幂等（`123`/`"123"` 不重复建）→快照超阈值进待审核→approve 执行删除→凭据作废后拒收。

```gherkin
# language: zh-CN
功能: CMDB 自定义上报端到端
  场景: 客户脚本通过凭据持续上报并幂等合并
    假设 存在启用的快速模型上报任务"业务系统A"且身份键为 biz_id(int)
    并且 任务已签发上报凭据
    当 脚本携带凭据上报实例 biz_id="123"
    那么 批次状态为成功 且新增实例数为 1
    当 脚本再次上报实例 biz_id=123
    那么 不应新建实例 而是更新已有实例

  场景: 凭据作废后立即拒收
    假设 存在已签发凭据的上报任务
    当 作废该凭据
    并且 脚本携带原凭据上报
    那么 上报被拒绝
```

- [ ] **Step 2: 写 step 定义**（用 `scenarios(FEATURE)`；service 层驱动，图层按需 mock 或用集成夹具）。运行：`cd server && uv run pytest apps/cmdb_enterprise/tests/bdd/test_custom_reporting_bdd.py -v` → 先 FAIL 再补齐至 PASS。
- [ ] **Step 3: 提交** — `git commit -m "test(cmdb_enterprise): custom_reporting 验收 BDD"`

---

## Task 12: 全量回归 + verification

- [ ] **Step 1: 全量 cmdb + cmdb_enterprise 测试**

Run: `cd server && uv run pytest apps/cmdb apps/cmdb_enterprise -v`
Expected: 全绿（含原 `test_custom_reporting_*` 与新加）

- [ ] **Step 2: 社区无 overlay 回退验证**——临时 `INSTALL_APPS` 不含 `cmdb_enterprise`（或 mock 注册表未注册），确认薄壳 list 返回空、写操作 4xx「未启用」，不报 500。
- [ ] **Step 3: lint** — `cd server && uv run flake8 apps/cmdb_enterprise/custom_reporting apps/cmdb/views/custom_reporting.py`（按仓库 pre-commit 配置）。
- [ ] **Step 4:** 进入 `superpowers:verification-before-completion`，逐条对照 spec 验收标准 1–10，给出证据（测试名/输出）。

---

## Self-Review（已执行）

**Spec coverage：** 任务新建/编辑/删除/列表/详情(T4,T10)；完整+快速双轨(T3,T4)；合并复用引擎(T7)；身份归一化 P0(T7)；关系三情形+回填(T8)；三档清理+阈值审核(T9)；批次记录(T7,T10)；接入文档(T6)；变更场景可检索(T7,T10)；凭据轮换/作废(T5)；社区薄壳+企业 overlay 分离(T1–T3)。10 条验收标准均有对应任务。

**Placeholder scan：** 无 TBD/TODO；reuse 点凡签名未 100% 确认处均显式标注「核对源码为准」并给定位路径，非占位。

**Type consistency：** `merge_instances` 返回含 `covered_ids/old_data/new_data/identity_keys`，T8/T9 消费一致；`apply_snapshot(old_ids, covered_ids)` 与 ingest 传参一致；`approve/reject(task_id, review_id, operator)` 跨 service/provider 一致；契约方法名 T1 定义、T2 viewset 调用、T3+ provider 实现三处一致。

## 风险与执行注意

1. **响应 envelope / `current_team` cookie**：T2 第一个真跑视图任务先用 `views/instance.py` + `web/src/utils/request.ts` 校准，后续视图任务沿用。
2. **图层方法名**（批量删除、时间比较算子、`search_model_attr`/`search_model_info`/`update_model` 签名）：动手即以源码为准，已在相应步骤标注。
3. **JSON 字段查询**（`config__cleanup_strategy`）跨 DB 引擎兼容性：不确定就全量拉取 Python 过滤。
4. **测试触图**：service 测试优先 mock `merge_service.merge_instances` / GraphClient；仅 BDD/集成在有图环境跑。
