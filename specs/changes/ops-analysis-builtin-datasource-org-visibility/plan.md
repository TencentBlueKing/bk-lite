# 运营分析内置数据源组织可见性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 内置数据源空组织 = 全员可见；填了组织 = 白名单；仅超管可改名单；自定义源继续必选组织。

**Architecture:** 抽出单一可见性谓词，替换数据源列表/详情/预览/取数/连接测试等所有「当前组织必须在 `groups` 中」的判断。初始化不再把空名单补成 Default。一次性数据迁移只清「内置且仅为根 Default」的种子名单。前端超管可编辑内置源的组织字段，保存只 PATCH `{ groups }`。

**Tech Stack:** Django REST、JSONField `groups`、React/Ant Design 数据源设置页、pytest、Vitest。

产品契约：[`spec.md`](./spec.md)。冲突以 Spec 为准。

**Commit 约定：** 本仓库默认不主动 commit。各 Task 的 Commit 步骤仅在用户明确要求提交时执行。

---

## 0. 文件与职责

| 文件 | 职责 |
|---|---|
| `server/apps/operation_analysis/common/datasource_visibility.py` | 空名单 / 全员可见 / 当前组织可否访问 / 列表 Q 条件 |
| `server/apps/operation_analysis/views/datasource_view.py` | 列表、取数、预览、连接测试、提取连接、物化、更新、删除使用该谓词；内置组织 PATCH 仅超管 |
| `server/apps/operation_analysis/serializers/datasource_serializers.py` | 自定义源拒绝空 `groups` |
| `server/apps/operation_analysis/management/commands/init_source_api_data.py` | 新建内置 `groups=[]`，不再回填 Default |
| `server/apps/operation_analysis/management/commands/init_default_groups.py` | 跳过内置数据源 |
| `server/apps/operation_analysis/migrations/0030_clear_default_only_builtin_datasource_groups.py` | 一次性清种子 Default；实现时若 head 不是 0029，改依赖为当前 head |
| `web/src/app/ops-analysis/api/dataSource.ts` | 增加 PATCH |
| `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts` | 内置保存 payload 与只读判断 |
| `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx` | 超管内置走编辑，其他人走查看 |
| `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx` | 组织可空、提示、只提交 groups |
| `web/src/app/ops-analysis/utils/permissionChecker.ts` | 空名单仅内置视为全员 |
| `specs/capabilities/builtin-canvas-lifecycle.md` | 内置数据源 `groups` 与画布分流 |
| `specs/capabilities/legacy-prd-运营分析-管理.md` | 内置空名单语义 |

验证（均在对应目录跑）：

```bash
cd server
uv run pytest apps/operation_analysis/tests/test_datasource_visibility.py apps/operation_analysis/tests/test_datasource_view.py apps/operation_analysis/tests/test_management_commands.py apps/operation_analysis/tests/test_datasource_filters_serializers.py -v
```

```bash
cd web
pnpm exec vitest run src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/operateModalUtils.extract.test.ts src/app/ops-analysis/utils/__tests__/permissionChecker.test.ts src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/builtinVisibility.test.ts
```

---

### Task 1: 可见性谓词

**Files:**
- Create: `server/apps/operation_analysis/common/datasource_visibility.py`
- Create: `server/apps/operation_analysis/tests/test_datasource_visibility.py`

- [ ] **Step 1: 写失败测试**

```python
from types import SimpleNamespace

from django.db.models import Q

from apps.operation_analysis.common.datasource_visibility import (
    can_access_datasource_in_org,
    expand_datasource_org_query,
    is_builtin_globally_visible,
)


def _ds(**kwargs):
    defaults = {"is_build_in": False, "groups": [1]}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_empty_groups_is_global_only_for_builtin():
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=[])) is True
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=None)) is True
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=[2])) is False
    assert is_builtin_globally_visible(_ds(is_build_in=False, groups=[])) is False


def test_access_allows_any_org_for_global_builtin_and_allowlist_otherwise():
    global_builtin = _ds(is_build_in=True, groups=[])
    assert can_access_datasource_in_org(global_builtin, 1) is True
    assert can_access_datasource_in_org(global_builtin, 99) is True

    restricted = _ds(is_build_in=True, groups=[2])
    assert can_access_datasource_in_org(restricted, 2) is True
    assert can_access_datasource_in_org(restricted, 1) is False

    custom = _ds(is_build_in=False, groups=[])
    assert can_access_datasource_in_org(custom, 1) is False


def test_list_query_or_global_builtin_or_all_builtins_for_superuser():
    membership = Q(pk=1)
    expanded = expand_datasource_org_query(membership, include_all_builtins=False)
    assert expanded != membership
    superuser_q = expand_datasource_org_query(membership, include_all_builtins=True)
    assert superuser_q != expanded
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_visibility.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现谓词**

```python
from django.db.models import Q


def is_empty_groups(groups) -> bool:
    return not bool(groups)


def is_builtin_globally_visible(instance) -> bool:
    return bool(getattr(instance, "is_build_in", False)) and is_empty_groups(getattr(instance, "groups", None))


def can_access_datasource_in_org(instance, current_team) -> bool:
    if is_builtin_globally_visible(instance):
        return True
    groups = getattr(instance, "groups", None) or []
    return current_team in groups


def builtin_global_visibility_q() -> Q:
    return Q(is_build_in=True) & (Q(groups=[]) | Q(groups__isnull=True))


def expand_datasource_org_query(membership_query: Q, *, include_all_builtins: bool) -> Q:
    if include_all_builtins:
        return membership_query | Q(is_build_in=True)
    return membership_query | builtin_global_visibility_q()
```

- [ ] **Step 4: 再跑测试确认通过**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_visibility.py -v`

Expected: PASS

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 2: 列表与取数使用谓词

**Files:**
- Modify: `server/apps/operation_analysis/views/datasource_view.py`
- Modify: `server/apps/operation_analysis/tests/test_datasource_view.py`
- Modify: `server/apps/operation_analysis/tests/test_datasource_view.py` 中 `_build_instance`，补 `is_build_in=False`

现有 `current_team not in (instance.groups or [])` 出现在：`get_source_data`（非 render）、`preview`、`test_connection`、`extract_connection`、`submit_excel`、`retry_excel_materialization`、`destroy`。全部改成 `not can_access_datasource_in_org(instance, current_team)`。`destroy` 对自定义空名单仍应 403。

`get_source_data` 的 render 分支：先 `can_access_datasource_in_org`；若是全员内置则不再走 `get_has_permission`（它会因空 `groups` 交集失败）；受限内置与自定义仍走原 `get_has_permission`。

`list`：在 `filter_by_group` 得到 `membership_query` 后，用 `expand_datasource_org_query(..., include_all_builtins=user.is_superuser)` 再 filter。

- [ ] **Step 1: 写失败的列表/取数测试**（追加到 `test_datasource_view.py`）

```python
def _grant_view(user):
    user.permission = {"ops-analysis": {"data_source-View", "data_source-Edit"}}
    return user


@pytest.mark.django_db
@pytest.mark.integration
def test_list_includes_empty_groups_builtin_for_any_org(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    _grant_view(authenticated_user)
    global_ds = DataSourceAPIModel.objects.create(
        name="global-builtin",
        rest_api="builtin/global",
        groups=[],
        is_build_in=True,
        build_in_key="builtin::global",
    )
    hidden = DataSourceAPIModel.objects.create(
        name="restricted-builtin",
        rest_api="builtin/restricted",
        groups=[2],
        is_build_in=True,
        build_in_key="builtin::restricted",
    )
    factory = APIRequestFactory()
    request = factory.get("/operation_analysis/api/data_source/", {"page_size": -1})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"get": "list"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    items = payload.get("items") or payload
    ids = {item["id"] for item in items}
    assert global_ds.id in ids
    assert hidden.id not in ids


@pytest.mark.django_db
@pytest.mark.integration
def test_superuser_list_includes_restricted_builtin_from_other_org(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    authenticated_user.is_superuser = True
    hidden = DataSourceAPIModel.objects.create(
        name="restricted-builtin-super",
        rest_api="builtin/restricted-super",
        groups=[2],
        is_build_in=True,
        build_in_key="builtin::restricted-super",
    )
    factory = APIRequestFactory()
    request = factory.get("/operation_analysis/api/data_source/", {"page_size": -1})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"get": "list"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    items = payload.get("items") or payload
    assert hidden.id in {item["id"] for item in items}


@pytest.mark.django_db
@pytest.mark.integration
def test_get_source_data_allows_empty_groups_builtin(authenticated_user, monkeypatch):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    authenticated_user.is_superuser = True
    datasource = DataSourceAPIModel.objects.create(
        name="global-query",
        rest_api="monitor/query_latest_active_alerts",
        groups=[],
        is_build_in=True,
        build_in_key="builtin::global-query",
        params=[{"name": "limit", "type": "number", "value": 10, "filterType": "params"}],
    )
    captured = {}

    class FakeGetNatsData:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def get_data(self):
            return {"result": True, "data": [], "message": ""}

    monkeypatch.setattr(datasource_view, "GetNatsData", FakeGetNatsData)
    factory = APIRequestFactory()
    request = factory.post(
        f"/operation_analysis/api/data_source/get_source_data/{datasource.pk}/",
        data={},
        format="json",
    )
    request.COOKIES["current_team"] = "99"
    force_authenticate(request, user=authenticated_user)
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(
        request, pk=str(datasource.pk)
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.integration
def test_get_source_data_rejects_restricted_builtin_outside_allowlist(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    authenticated_user.is_superuser = True
    datasource = DataSourceAPIModel.objects.create(
        name="restricted-query",
        rest_api="builtin/restricted-query",
        groups=[2],
        is_build_in=True,
        build_in_key="builtin::restricted-query",
    )
    factory = APIRequestFactory()
    request = factory.post(
        f"/operation_analysis/api/data_source/get_source_data/{datasource.pk}/",
        data={},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(
        request, pk=str(datasource.pk)
    )
    response.render()
    payload = json.loads(response.rendered_content)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["message"] == "无权访问当前数据源"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_view.py -k "empty_groups_builtin or restricted_builtin or global_query" -v`

Expected: 列表不含空名单内置源，或取数 403。

- [ ] **Step 3: 改 view**

在 `datasource_view.py` 顶部增加：

```python
from apps.operation_analysis.common.datasource_visibility import (
    can_access_datasource_in_org,
    expand_datasource_org_query,
    is_builtin_globally_visible,
)
```

`list`：

```python
current_team, include_children, org_field, query = self.filter_by_group(queryset, request, request.user)
query = expand_datasource_org_query(
    query,
    include_all_builtins=bool(getattr(request.user, "is_superuser", False)),
)
queryset = queryset.filter(query).order_by(self.ORDERING_FIELD)
```

`get_source_data` 组织校验改为：

```python
if not can_access_datasource_in_org(instance, current_team):
    return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)
if render_scoped and not is_builtin_globally_visible(instance):
    if not self.get_has_permission(request.user, instance, current_team, is_check=True):
        return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)
```

把 render 分支里原来的 `get_has_permission` 整段收进上面的条件，避免空名单内置在报告渲染里被组织交集挡掉。

其余 `current_team not in (instance.groups or [])` 全部换成 `not can_access_datasource_in_org(...)`。`_build_instance` 增加 `is_build_in=False`。

- [ ] **Step 4: 再跑相关测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_view.py apps/operation_analysis/tests/test_datasource_preview_views.py apps/operation_analysis/tests/test_datasource_view_prometheus.py -v`

Expected: PASS，含新用例。预览/Prometheus 里「组织外 403」用例仍通过。

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 3: 仅超管可改内置组织，且允许空数组

**Files:**
- Modify: `server/apps/operation_analysis/views/datasource_view.py` 的 `update`
- Modify: `server/apps/operation_analysis/tests/test_datasource_view.py`

现有 `test_builtin_datasource_partial_update_allows_visibility_only` 是超管，保持通过。新增：有 Edit 的非超管 403；超管可 PATCH `groups: []`。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.django_db
@pytest.mark.integration
def test_builtin_visibility_update_rejects_nonsuperuser_with_edit_permission(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    datasource = DataSourceAPIModel.objects.create(
        name="builtin-edit-not-super",
        rest_api="builtin/edit-not-super",
        groups=[],
        is_build_in=True,
        build_in_key="builtin::edit-not-super",
    )
    factory = APIRequestFactory()
    request = factory.patch(
        f"/operation_analysis/api/data_source/{datasource.pk}/",
        data={"groups": [1]},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"patch": "partial_update"})(
        request, pk=str(datasource.pk)
    )
    datasource.refresh_from_db()
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert datasource.groups == []


@pytest.mark.django_db
@pytest.mark.integration
def test_superuser_can_clear_builtin_groups(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    authenticated_user.is_superuser = True
    datasource = DataSourceAPIModel.objects.create(
        name="builtin-clear",
        rest_api="builtin/clear",
        groups=[1],
        is_build_in=True,
        build_in_key="builtin::clear",
    )
    factory = APIRequestFactory()
    request = factory.patch(
        f"/operation_analysis/api/data_source/{datasource.pk}/",
        data={"groups": []},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"patch": "partial_update"})(
        request, pk=str(datasource.pk)
    )
    datasource.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert datasource.groups == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_view.py::test_builtin_visibility_update_rejects_nonsuperuser_with_edit_permission apps/operation_analysis/tests/test_datasource_view.py::test_superuser_can_clear_builtin_groups -v`

Expected: 非超管可能 200（现有 `_validate_update_access` 在空名单时会失败，但 `groups=[1]` 的旧数据上有 Edit 的成员可能成功）。以红测为准。

- [ ] **Step 3: 收口 update**

```python
if instance.is_build_in and visibility_only:
    if not getattr(request.user, "is_superuser", False):
        return Response({"detail": "只有超级管理员可以修改内置数据源的组织可见性"}, status=status.HTTP_403_FORBIDDEN)
    response = partial_update_groups_with_auth(self, request, instance)
```

`visibility_update._validate_groups_payload` 已允许空 list（`any(...)` 对空数组为 False）。不要改成拒绝空数组。

- [ ] **Step 4: 再跑内置更新相关测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_view.py -k "builtin" -v`

Expected: PASS

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 4: 自定义源拒绝空组织

**Files:**
- Modify: `server/apps/operation_analysis/serializers/datasource_serializers.py`
- Modify: `server/apps/operation_analysis/tests/test_datasource_filters_serializers.py`

- [ ] **Step 1: 写失败测试**

在 serializer 测试中：创建自定义源 `groups=[]` 返回 400；更新已有自定义源到 `[]` 返回 400；内置 PATCH `[]` 不走这条校验（Task 3 已覆盖）。

```python
@pytest.mark.django_db
def test_custom_datasource_rejects_empty_groups(authenticated_user):
    from rest_framework.test import APIRequestFactory, force_authenticate
    from apps.operation_analysis.views import datasource_view

    authenticated_user.is_superuser = True
    factory = APIRequestFactory()
    request = factory.post(
        "/operation_analysis/api/data_source/",
        data={
            "name": "custom-empty-groups",
            "rest_api": "custom/empty",
            "source_type": "nats",
            "params": [],
            "chart_type": ["table"],
            "groups": [],
            "namespaces": [],
            "tag": [],
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_datasource_filters_serializers.py -k empty_groups -v`

若该文件无 create 入口，把用例放 `test_datasource_view.py`。Expected: FAIL（当前可能 201）。

- [ ] **Step 3: serializer 校验**

在 `DataSourceAPIModelSerializer`：

```python
def validate_groups(self, value):
    groups = value or []
    if self.instance is not None and getattr(self.instance, "is_build_in", False):
        return groups
    if not groups:
        raise serializers.ValidationError("必须选择所属组织")
    return groups
```

- [ ] **Step 4: 再跑 serializer / create 测试**

Expected: PASS

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 5: 初始化不再回填 Default

**Files:**
- Modify: `server/apps/operation_analysis/management/commands/init_source_api_data.py`
- Modify: `server/apps/operation_analysis/management/commands/init_default_groups.py`
- Modify: `server/apps/operation_analysis/tests/test_management_commands.py`

- [ ] **Step 1: 把回填测试改成新期望（先跑应红）**

将 `test_init_source_api_data_backfills_empty_groups_on_existing_sources` 改名为 `test_init_source_api_data_keeps_empty_groups_on_existing_builtin`，断言 force-update 后 `groups == []`。

追加：

```python
@pytest.mark.django_db
def test_init_default_groups_skips_builtin_datasource():
    from apps.system_mgmt.models.user import Group
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    Group.objects.get_or_create(name="Default", parent_id=0)
    builtin = DataSourceAPIModel.objects.create(
        name="keep-empty",
        rest_api="keep/empty",
        groups=[],
        is_build_in=True,
        build_in_key="keep-empty",
    )
    custom = DataSourceAPIModel.objects.create(
        name="fill-custom",
        rest_api="fill/custom",
        groups=[],
        is_build_in=False,
    )
    call_command("init_default_groups")
    builtin.refresh_from_db()
    custom.refresh_from_db()
    assert builtin.groups == []
    assert custom.groups  # 自定义空名单仍补 Default
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_management_commands.py -k "empty_groups or skips_builtin" -v`

Expected: 内置被补成 Default。

- [ ] **Step 3: 改命令**

`init_source_api_data.py`：创建时 `defaults["groups"] = []`。删除 `if not obj.groups and default_groups` 的回填（force-update 与非 force 两条）。可删除仅为此服务的 `get_default_groups`。

`init_default_groups.py` 的 `_init_model_groups`：

```python
if getattr(record, "is_build_in", False):
    skipped_count += 1
    continue
```

- [ ] **Step 4: 再跑 management 测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_management_commands.py -v`

Expected: PASS。`test_init_source_api_data_keeps_existing_non_empty_groups` 仍断言 `[99]` 不变。

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 6: 存量 Default 种子一次性清理

**Files:**
- Create: `server/apps/operation_analysis/migrations/0030_clear_default_only_builtin_datasource_groups.py`（依赖当前 migration head；写前 `ls server/apps/operation_analysis/migrations/*.py` 核对）
- Create: `server/apps/operation_analysis/tests/test_clear_default_only_builtin_datasource_groups.py`

- [ ] **Step 1: 写失败测试**（直接调 forwards，不依赖 migration 文件名）

```python
import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_forwards_clears_default_only_and_keeps_custom_allowlist(settings):
    from apps.system_mgmt.models.user import Group
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
    from apps.operation_analysis.migrations.0030_clear_default_only_builtin_datasource_groups import forwards

    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    default, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    other, _ = Group.objects.get_or_create(name="Other", parent_id=0)
    call_command("init_default_namespace")

    only_default = DataSourceAPIModel.objects.create(
        name="seed",
        rest_api="seed/api",
        groups=[default.id],
        is_build_in=True,
        build_in_key="seed",
    )
    mixed = DataSourceAPIModel.objects.create(
        name="mixed",
        rest_api="mixed/api",
        groups=[default.id, other.id],
        is_build_in=True,
        build_in_key="mixed",
    )
    custom = DataSourceAPIModel.objects.create(
        name="custom",
        rest_api="custom/api",
        groups=[default.id],
        is_build_in=False,
    )
    forwards(None, None)
    only_default.refresh_from_db()
    mixed.refresh_from_db()
    custom.refresh_from_db()
    assert only_default.groups == []
    assert mixed.groups == [default.id, other.id]
    assert custom.groups == [default.id]
```

若 Django `apps.get_model` 写法与历史 migration 一致，测试改为 `call_command("migrate", "operation_analysis", ...)` 只在隔离库上跑；优先测 `forwards` 函数本身。

- [ ] **Step 2: 实现 migration**

```python
from django.db import migrations


def forwards(apps, schema_editor):
    DataSource = apps.get_model("operation_analysis", "DataSourceAPIModel")
    Group = apps.get_model("system_mgmt", "Group")
    default = Group.objects.filter(name="Default", parent_id=0).first()
    default_id = default.id if default else None
    for datasource in DataSource.objects.filter(is_build_in=True).iterator():
        groups = datasource.groups or []
        if not groups or (default_id is not None and list(groups) == [default_id]):
            datasource.groups = []
            datasource.save(update_fields=["groups"])


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0029_report_refresh_interval"),
        ("system_mgmt", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
```

`system_mgmt` 依赖改为该 app 里 Group 模型所在的真实 migration。实现时 `rg "class Group" server/apps/system_mgmt/migrations` 核对，不要抄错。

- [ ] **Step 3: 跑测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_clear_default_only_builtin_datasource_groups.py -v`

Expected: PASS。重复执行 forwards 幂等。

- [ ] **Step 4: Commit**（仅用户明确要求时）

---

### Task 7: 前端组织可空、内置只 PATCH groups

**Files:**
- Modify: `web/src/app/ops-analysis/api/dataSource.ts`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/__tests__/operateModalUtils.extract.test.ts`
- Create: `web/src/app/ops-analysis/(pages)/settings/dataSource/__tests__/builtinVisibility.test.ts`
- Create: `web/src/app/ops-analysis/utils/__tests__/permissionChecker.test.ts`
- Modify: `web/src/app/ops-analysis/utils/permissionChecker.ts`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: 写失败的纯函数测试**

`operateModalUtils.ts` 增加并测试：

```ts
export function isBuiltinDatasource(row?: { is_build_in?: boolean }): boolean {
  return Boolean(row?.is_build_in);
}

export function isDatasourceDefinitionReadOnly(
  mode: string,
  row?: { is_build_in?: boolean },
): boolean {
  return mode === "view" || isBuiltinDatasource(row);
}

export function canEditBuiltinDatasourceGroups(
  isSuperUser: boolean,
  row?: { is_build_in?: boolean },
): boolean {
  return isBuiltinDatasource(row) && isSuperUser;
}

export function buildBuiltinGroupsPayload(groups: unknown): { groups: number[] } {
  return { groups: Array.isArray(groups) ? groups.filter((id) => Number.isInteger(id) && id > 0) : [] };
}
```

`permissionChecker.ts`：空 `groups` 仅当 `is_build_in` 为真才全员；自定义空名单返回 false。

`builtinVisibility.test.ts` 覆盖上述函数。`permissionChecker.test.ts` 覆盖内置空 / 自定义空 / 白名单。

- [ ] **Step 2: 跑 Vitest 确认失败**

Run: `cd web && pnpm exec vitest run src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/builtinVisibility.test.ts src/app/ops-analysis/utils/__tests__/permissionChecker.test.ts`

Expected: FAIL，函数未导出。

- [ ] **Step 3: 实现函数与页面**

`dataSource.ts`：从 `useApiClient` 取出 `patch`，新增 `patchDataSource(id, data)`，并导出。

`page.tsx`：`useUserInfoContext()` 取 `isSuperUser`。内置行：超管按钮 `handleEdit('edit', row)` 文案用 `t('common.edit')`；非超管仍 `view`。

`operateModal.tsx`：

- `const { selectedGroup, isSuperUser } = useUserInfoContext();`
- `const definitionReadOnly = isDatasourceDefinitionReadOnly(mode, currentRow);`
- `const groupsReadOnly = definitionReadOnly && !canEditBuiltinDatasourceGroups(isSuperUser, currentRow);`
- 保存按钮：`mode !== "view" && (!currentRow?.is_build_in || isSuperUser)` 时显示确认。
- `Form` 不要用顶层 `disabled={readOnly}` 锁死内置编辑；定义字段 `disabled={definitionReadOnly}`，组织字段 `disabled={groupsReadOnly}`。
- 组织 `Form.Item`：自定义仍 `required`；内置去掉 required，`extra={currentRow?.is_build_in ? t("dataSource.emptyGroupsMeansAllOrgs") : undefined}`。
- `onFinish`：若 `currentRow?.is_build_in`，只 `await patchDataSource(currentRow.id, buildBuiltinGroupsPayload(values.groups))`，不要走预览/Excel/完整 PUT。

文案：

- zh：`"emptyGroupsMeansAllOrgs": "未选择组织表示所有组织可见"`
- en：`"emptyGroupsMeansAllOrgs": "If no organization is selected, all organizations can see this data source."`

- [ ] **Step 4: 再跑 Vitest**

Run: `cd web && pnpm exec vitest run src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/operateModalUtils.extract.test.ts src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/builtinVisibility.test.ts src/app/ops-analysis/utils/__tests__/permissionChecker.test.ts`

Expected: PASS。

- [ ] **Step 5: Commit**（仅用户明确要求时）

---

### Task 8: 长期能力与规格收口

**Files:**
- Modify: `specs/capabilities/builtin-canvas-lifecycle.md`
- Modify: `specs/capabilities/legacy-prd-运营分析-管理.md`
- Modify: `specs/changes/ops-analysis-builtin-datasource-org-visibility/spec.md`（Status 保持 ready，在 Further Notes 记录落地证据命令；不要把文件搬走）

- [ ] **Step 1: 改生命周期能力**

「种子内容与运营配置」改为：

- 内置画布 / 目录：新建仍用 Default，更新保留 `groups`，有编辑权可 PATCH 组织。
- 内置数据源：新建 `groups=[]`（全员可见）；更新保留已有名单，空名单不再回填 Default；仅超管可 PATCH `groups`；空 = 全员，非空 = 白名单。

验收补：新组织无需配置即可列出空名单内置数据源。

- [ ] **Step 2: 改管理 PRD 关键规则**

「数据源按组织分组隔离」改为：自定义数据源按组织隔离且组织必填；内置数据源空组织对全员可见，非空为白名单。命名空间仍全平台共享。

- [ ] **Step 3: 全量相关测试再跑一遍**

Run:

```bash
cd server
uv run pytest apps/operation_analysis/tests/test_datasource_visibility.py apps/operation_analysis/tests/test_datasource_view.py apps/operation_analysis/tests/test_management_commands.py apps/operation_analysis/tests/test_datasource_filters_serializers.py apps/operation_analysis/tests/test_datasource_preview_views.py apps/operation_analysis/tests/test_clear_default_only_builtin_datasource_groups.py -v
```

```bash
cd web
pnpm exec vitest run src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/operateModalUtils.extract.test.ts src/app/ops-analysis/\(pages\)/settings/dataSource/__tests__/builtinVisibility.test.ts src/app/ops-analysis/utils/__tests__/permissionChecker.test.ts
```

Expected: 全部 PASS。把命令与结果摘要写入 spec Further Notes。

- [ ] **Step 4: Commit**（仅用户明确要求时）

---

## Spec 覆盖核对

| 规格条目 | Task |
|---|---|
| 空名单 = 全员可见（仅内置） | 1, 2 |
| 非空白名单 | 2 |
| 超管改组织 / 非超管不能改 | 3 |
| 超管列表可见全部内置；取数无超管旁路 | 2 |
| 自定义拒绝空组织 | 4 |
| 初始化不回填、保留已有名单 | 5 |
| 存量 Default 单组织清空 | 6 |
| 前端只改组织、提示、PATCH | 7 |
| 能力文档分流画布 vs 数据源 | 8 |
| 不做内置画布空=全员 | 无任务（有意） |
| 不拦截同 path 自定义 NATS | 无任务（有意） |
