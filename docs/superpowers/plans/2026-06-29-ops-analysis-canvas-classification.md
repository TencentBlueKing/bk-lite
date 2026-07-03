# Ops Analysis Canvas Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `screen` and `report` as first-class ops-analysis canvas types while keeping `dashboard`, `topology`, and `architecture` intact and removing big-screen presentation behavior from topology.

**Architecture:** Keep the existing three backend models and add `Screen` and `Report` with the same ownership/directory fields. Introduce a lightweight canvas registry so directory tree, import/export, frontend API, sidebar, and view routing can expand by type instead of scattering new hard-coded branches. Move fixed-resolution, screen theme, title/clock/background/chrome behavior into the new Screen page; Report starts as a basic content-shell page.

**Tech Stack:** Django 4.2 + DRF + pytest on backend; Next.js 16 + React 19 + TypeScript + Ant Design on frontend.

---

## Product Judgment

No blockers in the agreed MVP scope. The smallest commercially useful slice is:

- `Architecture` remains a normal canvas type with its create/edit/view entry.
- `Screen` and `Report` appear in the directory tree and have API CRUD.
- `Screen` owns fixed resolution and screen visual theme.
- `Topology` stops exposing presentation configuration and stops saving `viewport/presentation` as its normal contract.
- `Report` is a first-class object shell only; scheduling/export/history are later work.

MVP improvements that should be included now:

- Centralize canvas type metadata before adding new types.
- Add backend tests before model/service/view changes.
- Add frontend type registry before extending Sidebar/ViewPage.
- Keep widget rendering reusable through `WidgetRenderer`.

Later:

- Scene container.
- Advanced Screen templates/rotation.
- Report snapshot/export/schedule/history.
- External datasource connector framework.

## File Structure

### Backend

- Modify `server/apps/operation_analysis/models/models.py`  
  Add `Screen` and `Report`.
- Create migration under `server/apps/operation_analysis/migrations/0014_screen_report.py`  
  Add the two tables.
- Create `server/apps/operation_analysis/services/canvas/__init__.py`
- Create `server/apps/operation_analysis/services/canvas/registry.py`  
  Central type metadata: model path, serializer name, permission key, section name, label.
- Create `server/apps/operation_analysis/services/canvas/viewset_mixins.py`  
  Shared builtin visibility, validation cleanup, partial update helper, and CRUD/audit behavior for dashboard-like canvas ViewSets. Keep these helpers outside `views/view.py` so the new shared mixin does not import back from the view module.
- Modify `server/apps/operation_analysis/serializers/directory_serializers.py`  
  Add shared serializer base, `ScreenModelSerializer`, `ReportModelSerializer`.
- Modify `server/apps/operation_analysis/filters/filters.py`  
  Add `ScreenModelFilter`, `ReportModelFilter`.
- Modify `server/apps/operation_analysis/views/view.py`  
  Add `ScreenModelViewSet`, `ReportModelViewSet`, use shared mixin for new types.
- Modify `server/apps/operation_analysis/urls.py`  
  Register `/operation_analysis/api/screen/` and `/operation_analysis/api/report/`.
- Modify `server/apps/operation_analysis/services/node_tree.py`  
  Add generic canvas node builder.
- Modify `server/apps/operation_analysis/services/directory_service.py`  
  Include screen/report in tree and module data.
- Modify `server/apps/operation_analysis/filters/base_filters.py`  
  Extend permission filter map for screen/report.
- Modify `server/apps/operation_analysis/constants/import_export.py`  
  Add object types, sections, canvas set, schema version `1.1.0`.
- Modify `server/apps/operation_analysis/schemas/import_export_schema.py`  
  Add `ScreenItem`, `ReportItem`, extend `YAMLDocument`, object counts.
- Modify `server/apps/operation_analysis/services/import_export/view_sets.py`  
  Remove topology presentation/viewport normalization; add screen/report normalization.
- Modify `server/apps/operation_analysis/services/import_export/export_service.py`
- Modify `server/apps/operation_analysis/services/import_export/import_service.py`
- Modify `server/apps/operation_analysis/services/import_export/precheck_service.py`
- Modify backend tests:
  - `server/apps/operation_analysis/tests/test_directory_views.py`
  - `server/apps/operation_analysis/tests/test_export_and_viewsets.py`
  - `server/apps/operation_analysis/tests/test_import_service.py`

### Frontend

- Create `web/src/app/ops-analysis/constants/canvasTypes.ts`  
  Shared frontend type registry.
- Modify `web/src/app/ops-analysis/types/index.ts`  
  Add `screen` and `report` to type unions.
- Create `web/src/app/ops-analysis/types/screen.ts`
- Create `web/src/app/ops-analysis/types/report.ts`
- Modify `web/src/app/ops-analysis/api/index.ts`  
  Add endpoints via registry/type map.
- Create `web/src/app/ops-analysis/api/screen.ts`
- Create `web/src/app/ops-analysis/api/report.ts`
- Modify `web/src/app/ops-analysis/api/importExport.ts`  
  Extend `ObjectType`, summary counts.
- Modify `web/src/app/ops-analysis/components/sidebar.tsx`  
  Use registry for create menu/icon/export type.
- Modify `web/src/app/ops-analysis/(pages)/view/page.tsx`  
  Use registry-aware selection state and render Screen/Report.
- Create `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/screen/index.module.scss`
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`
- Create `web/src/app/ops-analysis/(pages)/view/report/index.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/report/index.module.scss`
- Create `web/src/app/ops-analysis/(pages)/view/report/components/reportToolbar.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/report/components/reportEditor.tsx`
- Create `web/src/app/ops-analysis/(pages)/view/report/components/reportSection.tsx`
- Modify topology files to clean presentation:
  - `web/src/app/ops-analysis/types/topology.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/index.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/components/canvasShell.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/components/chartNode.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphData.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useTopologyLifecycle.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/index.module.scss`
- Delete:
  - `web/src/app/ops-analysis/(pages)/view/topology/components/presentationModal.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useTopologyPresentation.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/utils/viewport.ts`
- Modify `web/src/app/ops-analysis/locales/zh.json`
- Modify `web/src/app/ops-analysis/locales/en.json`
- Modify `web/src/app/ops-analysis/design.md`

## Task 1: Backend Canvas Models And Registry

**Files:**

- Modify: `server/apps/operation_analysis/models/models.py`
- Create: `server/apps/operation_analysis/services/canvas/__init__.py`
- Create: `server/apps/operation_analysis/services/canvas/registry.py`
- Modify: `server/apps/operation_analysis/tests/test_directory_views.py`

- [ ] **Step 1: Write failing tests for model registry coverage**

Add this near the model/tree tests in `server/apps/operation_analysis/tests/test_directory_views.py`:

```python
def test_canvas_registry_contains_all_first_class_canvas_types():
    from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY

    assert set(CANVAS_TYPE_REGISTRY.keys()) == {
        "dashboard",
        "topology",
        "architecture",
        "screen",
        "report",
    }
    assert CANVAS_TYPE_REGISTRY["screen"].permission_key == "directory.screen"
    assert CANVAS_TYPE_REGISTRY["report"].section_name == "reports"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py::test_canvas_registry_contains_all_first_class_canvas_types -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.operation_analysis.services.canvas'`.

- [ ] **Step 3: Add `Screen` and `Report` models**

Append after `Architecture` in `server/apps/operation_analysis/models/models.py`:

```python
class Screen(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="大屏名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="screen", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="大屏其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="大屏视图集配置", default=dict)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_screen"
        verbose_name = "大屏"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Report(MaintainerInfo, TimeInfo, Groups):
    name = models.CharField(max_length=128, verbose_name="报表名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name="report", verbose_name="所属目录", null=True, blank=True)
    other = JSONField(help_text="报表其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="报表视图集配置", default=dict)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    build_in_key = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="内置标识键")

    class Meta:
        db_table = "operation_analysis_report"
        verbose_name = "报表"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None
```

- [ ] **Step 4: Add registry**

Create `server/apps/operation_analysis/services/canvas/__init__.py` as an empty package marker.

Create `server/apps/operation_analysis/services/canvas/registry.py`:

```python
from dataclasses import dataclass

from apps.operation_analysis.models.models import Architecture, Dashboard, Report, Screen, Topology


@dataclass(frozen=True)
class CanvasTypeMeta:
    object_type: str
    model: type
    permission_key: str
    section_name: str
    node_label: str


CANVAS_TYPE_REGISTRY = {
    "dashboard": CanvasTypeMeta("dashboard", Dashboard, "directory.dashboard", "dashboards", "仪表盘"),
    "topology": CanvasTypeMeta("topology", Topology, "directory.topology", "topologies", "拓扑图"),
    "architecture": CanvasTypeMeta("architecture", Architecture, "directory.architecture", "architectures", "架构图"),
    "screen": CanvasTypeMeta("screen", Screen, "directory.screen", "screens", "大屏"),
    "report": CanvasTypeMeta("report", Report, "directory.report", "reports", "报表"),
}
```

- [ ] **Step 5: Generate migration**

Run:

```bash
cd server && uv run python manage.py makemigrations operation_analysis
```

Expected: creates `server/apps/operation_analysis/migrations/0014_screen_report.py` with `CreateModel` operations for `Screen` and `Report`.

- [ ] **Step 6: Run registry test**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py::test_canvas_registry_contains_all_first_class_canvas_types -q
```

Expected: PASS.

## Task 2: Backend Serializers, Filters, ViewSets, URLs

**Files:**

- Modify: `server/apps/operation_analysis/serializers/directory_serializers.py`
- Modify: `server/apps/operation_analysis/filters/filters.py`
- Modify: `server/apps/operation_analysis/filters/base_filters.py`
- Create: `server/apps/operation_analysis/services/canvas/viewset_mixins.py`
- Modify: `server/apps/operation_analysis/views/view.py`
- Modify: `server/apps/operation_analysis/urls.py`
- Modify: `server/apps/operation_analysis/tests/test_directory_views.py`

- [ ] **Step 1: Write failing API tests for Screen/Report create and builtin protection**

Add to `server/apps/operation_analysis/tests/test_directory_views.py`:

```python
@pytest.mark.django_db
def test_screen_and_report_create_with_directory_succeed(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="内容目录", groups=[1], created_by="testuser")

    screen_request = _request("post", "/screen/", user, data={"name": "值班大屏", "groups": [1], "directory": directory.id})
    screen_response = view_module.ScreenModelViewSet.as_view({"post": "create"})(screen_request)
    screen_payload = _render(screen_response)

    report_request = _request("post", "/report/", user, data={"name": "周报", "groups": [1], "directory": directory.id})
    report_response = view_module.ReportModelViewSet.as_view({"post": "create"})(report_request)
    report_payload = _render(report_response)

    assert screen_response.status_code == status.HTTP_201_CREATED
    assert screen_payload["data"]["view_sets"] == {}
    assert report_response.status_code == status.HTTP_201_CREATED
    assert report_payload["data"]["view_sets"] == {}


@pytest.mark.django_db
def test_screen_create_without_directory_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/screen/", user, data={"name": "无目录大屏", "groups": [1]})
    response = view_module.ScreenModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "directory" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_report_update_builtin_forbidden(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="报表目录", groups=[1], created_by="testuser")
    from apps.operation_analysis.models.models import Report

    report = Report.objects.create(
        name="内置报表",
        groups=[1],
        directory=directory,
        is_build_in=True,
        build_in_key="builtin-report",
    )
    request = _request("put", f"/report/{report.id}/", user, data={"name": "改名", "groups": [1], "directory": directory.id})
    response = view_module.ReportModelViewSet.as_view({"put": "update"})(request, pk=str(report.id))
    _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py::test_screen_and_report_create_with_directory_succeed apps/operation_analysis/tests/test_directory_views.py::test_screen_create_without_directory_returns_400 apps/operation_analysis/tests/test_directory_views.py::test_report_update_builtin_forbidden -q
```

Expected: FAIL with `AttributeError` for missing `ScreenModelViewSet`.

- [ ] **Step 3: Move shared helper behavior into canvas ViewSet mixins**

Create `server/apps/operation_analysis/services/canvas/viewset_mixins.py`:

```python
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.audit_log import get_response_name, log_ops_analysis_success
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response


def _raise_if_builtin(instance, action_name="修改"):
    if getattr(instance, "is_build_in", False):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied(f"内置对象不允许{action_name}")


def _partial_update_with_auth(viewset, request, *args, **kwargs):
    user = getattr(request, "user", None)
    data = request.data
    instance = viewset.get_object()
    org_field = viewset.ORGANIZATION_FIELD
    instance_org_value = getattr(instance, org_field, [])
    if not isinstance(instance_org_value, list):
        instance_org_value = []

    if getattr(user, "is_superuser", False):
        if org_field in data:
            org_values = viewset._normalize_org_values(data, org_field)
            delete_team = [i for i in instance_org_value if i not in org_values]
            viewset.delete_rules(instance.id, delete_team)

        serializer = viewset.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        viewset.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    return AuthViewSet.update(viewset, request, *args, partial=True, **kwargs)


def _build_validation_error_response(error):
    detail = getattr(error, "detail", None)
    if not isinstance(detail, dict) or "detail" not in detail or "data" not in detail:
        raise error

    message = detail.get("detail")
    if isinstance(message, list):
        message = message[0] if message else "请求失败"

    return Response({"detail": str(message), "data": detail.get("data")}, status=400)


def _execute_with_clean_validation_error(handler):
    try:
        return handler()
    except ValidationError as error:
        return _build_validation_error_response(error)


class BuiltinVisibleMixin:
    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        builtin_qs = queryset.filter(is_build_in=True)
        normal_qs = queryset.filter(is_build_in=False)
        _ct, _ic, _of, org_query = self.filter_by_group(builtin_qs, request, request.user)
        builtin_filtered = builtin_qs.filter(org_query)
        normal_filtered = super().get_queryset_by_permission(request, normal_qs, permission_key)
        return (normal_filtered | builtin_filtered).distinct()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if getattr(instance, "is_build_in", False):
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        return super().retrieve(request, *args, **kwargs)


class CanvasCrudAuditMixin(BuiltinVisibleMixin):
    canvas_label = "画布"

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        response = _execute_with_clean_validation_error(lambda: super().create(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增{self.canvas_label}: {name}")
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: super().update(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑{self.canvas_label}: {name}")
        return response

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑{self.canvas_label}: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super().destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除{self.canvas_label}: {name}")
        return response
```

- [ ] **Step 4: Update `view.py` imports to avoid circular imports**

In `server/apps/operation_analysis/views/view.py`, delete the local definitions of:

- `_raise_if_builtin`
- `_partial_update_with_auth`
- `_build_validation_error_response`
- `_execute_with_clean_validation_error`
- `BuiltinVisibleMixin`

Import them from the new mixin module, keeping the same names in `view.py` so existing tests that call `view_module._raise_if_builtin` still pass:

```python
from apps.operation_analysis.services.canvas.viewset_mixins import (
    BuiltinVisibleMixin,
    CanvasCrudAuditMixin,
    _build_validation_error_response,
    _execute_with_clean_validation_error,
    _partial_update_with_auth,
    _raise_if_builtin,
)
```

- [ ] **Step 5: Add serializers**

In `server/apps/operation_analysis/serializers/directory_serializers.py`, import `Report` and `Screen`, then add a shared base and serializers:

```python
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Report, Screen, Topology


class CanvasObjectSerializer(DirectoryChainVisibilityMixin, BuiltinPermissionMixin, BaseFormatTimeSerializer, AuthSerializer):
    class Meta:
        fields = "__all__"
        extra_kwargs = {
            "is_build_in": {"read_only": True},
            "build_in_key": {"read_only": True},
        }

    def create(self, validated_data):
        if "directory" not in validated_data:
            raise serializers.ValidationError({"directory": ["directory is required for creation."]})
        return super().create(validated_data)


class ScreenModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.screen"

    class Meta(CanvasObjectSerializer.Meta):
        model = Screen


class ReportModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.report"

    class Meta(CanvasObjectSerializer.Meta):
        model = Report
```

Do not refactor existing serializers in this step; keep diff small.

- [ ] **Step 6: Add filters and permission map**

In `server/apps/operation_analysis/filters/filters.py`, import `Screen` and `Report` and add:

```python
class ScreenModelFilter(BaseGroupFilter):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Screen
        fields = ["name"]


class ReportModelFilter(BaseGroupFilter):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Report
        fields = ["name"]
```

In `server/apps/operation_analysis/filters/base_filters.py`, extend the existing filter-class permission map:

```python
"ScreenModelFilter": "directory.screen",
"ReportModelFilter": "directory.report",
```

- [ ] **Step 7: Add ViewSets and routes**

In `server/apps/operation_analysis/views/view.py`, import the new classes and add:

```python
class ScreenModelViewSet(CanvasCrudAuditMixin, AuthViewSet):
    """大屏"""

    queryset = Screen.objects.all()
    serializer_class = ScreenModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = ScreenModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory.screen"
    ORGANIZATION_FIELD = "groups"
    canvas_label = "大屏"


class ReportModelViewSet(CanvasCrudAuditMixin, AuthViewSet):
    """报表"""

    queryset = Report.objects.all()
    serializer_class = ReportModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = ReportModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory.report"
    ORGANIZATION_FIELD = "groups"
    canvas_label = "报表"
```

In `server/apps/operation_analysis/urls.py`, import and register:

```python
router.register(r"api/screen", ScreenModelViewSet, basename="screen")
router.register(r"api/report", ReportModelViewSet, basename="report")
```

- [ ] **Step 8: Run API tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py::test_screen_and_report_create_with_directory_succeed apps/operation_analysis/tests/test_directory_views.py::test_screen_create_without_directory_returns_400 apps/operation_analysis/tests/test_directory_views.py::test_report_update_builtin_forbidden -q
```

Expected: PASS.

## Task 3: Directory Tree And Module Data

**Files:**

- Modify: `server/apps/operation_analysis/services/node_tree.py`
- Modify: `server/apps/operation_analysis/services/directory_service.py`
- Modify: `server/apps/operation_analysis/tests/test_directory_views.py`

- [ ] **Step 1: Write failing tests for directory tree and module lookup**

Add:

```python
@pytest.mark.django_db
def test_tree_endpoint_includes_screen_and_report(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="目录", groups=[1], created_by="testuser")
    from apps.operation_analysis.models.models import Report, Screen

    Screen.objects.create(name="大屏A", groups=[1], directory=directory, created_by="testuser")
    Report.objects.create(name="报表A", groups=[1], directory=directory, created_by="testuser")

    request = _request("get", "/directory/tree/", user)
    response = view_module.DirectoryModelViewSet.as_view({"get": "tree"})(request)
    payload = _render(response)

    child_types = {child["type"] for child in payload["data"][0]["children"]}
    assert {"screen", "report"}.issubset(child_types)


@pytest.mark.django_db
def test_get_directory_modules_data_screen_and_report(authenticated_user):
    directory = Directory.objects.create(name="目录Y", groups=[1], created_by="testuser")
    from apps.operation_analysis.models.models import Report, Screen

    Screen.objects.create(name="屏1", groups=[1], directory=directory, created_by="testuser")
    Report.objects.create(name="表1", groups=[1], directory=directory, created_by="testuser")

    screen_result = DictDirectoryService.get_directory_modules_data("screen", page=1, page_size=10, group_id=1)
    report_result = DictDirectoryService.get_directory_modules_data("report", page=1, page_size=10, group_id=1)

    assert screen_result["items"][0]["name"] == "【目录Y】屏1"
    assert report_result["items"][0]["name"] == "【目录Y】表1"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py::test_tree_endpoint_includes_screen_and_report apps/operation_analysis/tests/test_directory_modules_data_screen_and_report -q
```

Expected: FAIL because tree/module data excludes `screen` and `report`.

- [ ] **Step 3: Add generic node builder**

In `server/apps/operation_analysis/services/node_tree.py`, add:

```python
    @staticmethod
    def get_canvas_nodes(instances, parent_children_map, object_type):
        nodes = {}
        for instance in instances:
            node_key = f"{object_type}_{instance.id}"
            nodes[node_key] = {
                "id": node_key,
                "data_id": instance.id,
                "name": instance.name,
                "desc": instance.desc,
                "type": object_type,
                "groups": instance.groups,
                "is_build_in": instance.is_build_in,
                "children": [],
            }
            parent_key = f"directory_{instance.directory_id}"
            parent_children_map.setdefault(parent_key, []).append(node_key)
        return nodes
```

Then make `get_dashboard_nodes`, `get_topology_nodes`, and `get_architecture_nodes` delegate to it.

- [ ] **Step 4: Expand directory service via registry**

In `server/apps/operation_analysis/services/directory_service.py`, import registry and replace per-type duplicated blocks with:

```python
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY


def _get_visible_canvas_queryset(meta, directories, current_team, request, group_ids):
    base = meta.model.objects.filter(directory__in=directories)
    return (
        GroupPermissionMixin.apply_group_filter(
            base.filter(is_build_in=False),
            current_team,
            request.user,
            meta.permission_key,
            group_ids=group_ids,
        )
        | GroupPermissionMixin.apply_group_filter(base.filter(is_build_in=True), current_team, group_ids=group_ids)
    ).distinct().order_by("id")
```

Inside `get_dict_trees`, after directory nodes:

```python
for object_type, meta in CANVAS_TYPE_REGISTRY.items():
    instances = _get_visible_canvas_queryset(meta, directories, current_team, request, group_ids)
    all_nodes.update(TreeNodeBuilder.get_canvas_nodes(instances, parent_children_map, object_type))
```

In `get_directory_modules_data`, replace model map with:

```python
model_class = CANVAS_TYPE_REGISTRY.get(child_module).model if child_module in CANVAS_TYPE_REGISTRY else None
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py -q
```

Expected: PASS.

## Task 4: Import/Export Contract For Screen/Report And Topology Cleanup

**Files:**

- Modify: `server/apps/operation_analysis/constants/import_export.py`
- Modify: `server/apps/operation_analysis/schemas/import_export_schema.py`
- Modify: `server/apps/operation_analysis/services/import_export/view_sets.py`
- Modify: `server/apps/operation_analysis/services/import_export/export_service.py`
- Modify: `server/apps/operation_analysis/services/import_export/import_service.py`
- Modify: `server/apps/operation_analysis/services/import_export/precheck_service.py`
- Modify: `server/apps/operation_analysis/tests/test_export_and_viewsets.py`
- Modify: `server/apps/operation_analysis/tests/test_import_service.py`

- [ ] **Step 1: Write failing tests for view_sets normalization**

In `server/apps/operation_analysis/tests/test_export_and_viewsets.py`, replace tests that assert topology keeps `viewport/presentation` with:

```python
def test_normalize_topology_drops_presentation_fields():
    view_sets = {
        "nodes": [{"id": "n1"}],
        "edges": [],
        "filters": [],
        "viewport": {"width": 1920},
        "presentation": {"theme": "tech-blue"},
    }

    out = vs.normalize_canvas_view_sets_for_storage(view_sets, ObjectType.TOPOLOGY)

    assert out == {"nodes": [{"id": "n1"}], "edges": [], "filters": []}


def test_normalize_screen_fills_viewport_and_items():
    out = vs.normalize_canvas_view_sets_for_storage({}, ObjectType.SCREEN)

    assert out == {
        "viewport": {
            "width": 1920,
            "height": 1080,
            "background": {"type": "preset", "key": "screen-dark"},
            "theme": "screen-dark",
        },
        "items": [],
        "decorations": {"showTitle": True, "showClock": True, "title": ""},
    }


def test_normalize_report_fills_sections():
    out = vs.normalize_canvas_view_sets_for_storage({}, ObjectType.REPORT)

    assert out == {"time_range": None, "sections": []}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_export_and_viewsets.py::test_normalize_topology_drops_presentation_fields apps/operation_analysis/tests/test_export_and_viewsets.py::test_normalize_screen_fills_viewport_and_items apps/operation_analysis/tests/test_export_and_viewsets.py::test_normalize_report_fills_sections -q
```

Expected: FAIL because `ObjectType.SCREEN` does not exist and topology still keeps presentation.

- [ ] **Step 3: Extend constants**

In `server/apps/operation_analysis/constants/import_export.py`:

```python
class ObjectType(str, Enum):
    DASHBOARD = "dashboard"
    TOPOLOGY = "topology"
    ARCHITECTURE = "architecture"
    SCREEN = "screen"
    REPORT = "report"
    DATASOURCE = "datasource"
    NAMESPACE = "namespace"


CANVAS_TYPES = {ObjectType.DASHBOARD, ObjectType.TOPOLOGY, ObjectType.ARCHITECTURE, ObjectType.SCREEN, ObjectType.REPORT}
YAML_SCHEMA_VERSION = "1.1.0"

OBJECT_TYPE_TO_SECTION = {
    ObjectType.DASHBOARD: "dashboards",
    ObjectType.TOPOLOGY: "topologies",
    ObjectType.ARCHITECTURE: "architectures",
    ObjectType.SCREEN: "screens",
    ObjectType.REPORT: "reports",
    ObjectType.DATASOURCE: "datasources",
    ObjectType.NAMESPACE: "namespaces",
}
```

- [ ] **Step 4: Update view_sets normalization**

In `server/apps/operation_analysis/services/import_export/view_sets.py`, remove `_normalize_topology_presentation` usage and use:

```python
DEFAULT_SCREEN_VIEW_SETS = {
    "viewport": {
        "width": 1920,
        "height": 1080,
        "background": {"type": "preset", "key": "screen-dark"},
        "theme": "screen-dark",
    },
    "items": [],
    "decorations": {"showTitle": True, "showClock": True, "title": ""},
}


def _normalize_screen_view_sets(view_sets: Any) -> dict:
    if not isinstance(view_sets, dict):
        return DEFAULT_SCREEN_VIEW_SETS.copy()
    viewport = view_sets.get("viewport", {})
    decorations = view_sets.get("decorations", {})
    return {
        "viewport": {
            "width": int(viewport.get("width") or 1920) if isinstance(viewport, dict) else 1920,
            "height": int(viewport.get("height") or 1080) if isinstance(viewport, dict) else 1080,
            "background": viewport.get("background", {"type": "preset", "key": "screen-dark"}) if isinstance(viewport, dict) else {"type": "preset", "key": "screen-dark"},
            "theme": viewport.get("theme", "screen-dark") if isinstance(viewport, dict) else "screen-dark",
        },
        "items": view_sets.get("items", []) if isinstance(view_sets.get("items", []), list) else [],
        "decorations": decorations if isinstance(decorations, dict) else {"showTitle": True, "showClock": True, "title": ""},
    }
```

Change topology branch to:

```python
if object_type == ObjectType.TOPOLOGY:
    if not isinstance(view_sets, dict):
        return {"nodes": [], "edges": [], "filters": []}
    return {
        "nodes": view_sets.get("nodes", []) if isinstance(view_sets.get("nodes", []), list) else [],
        "edges": view_sets.get("edges", []) if isinstance(view_sets.get("edges", []), list) else [],
        "filters": view_sets.get("filters", []) if isinstance(view_sets.get("filters", []), list) else [],
    }
```

Add:

```python
if object_type == ObjectType.SCREEN:
    return _normalize_screen_view_sets(view_sets)

if object_type == ObjectType.REPORT:
    if not isinstance(view_sets, dict):
        return {"time_range": None, "sections": []}
    return {
        "time_range": view_sets.get("time_range"),
        "sections": view_sets.get("sections", []) if isinstance(view_sets.get("sections", []), list) else [],
    }
```

In rewrite functions, add Screen item rewriting and Report section rewriting; keep Dashboard existing behavior.

- [ ] **Step 5: Update schema models**

In `server/apps/operation_analysis/schemas/import_export_schema.py`, add:

```python
class ScreenItem(BaseModel):
    key: str
    name: str
    desc: str = Field(default="")
    other: dict = Field(default_factory=dict)
    view_sets: dict = Field(default_factory=dict)
    refs: CanvasRefs = Field(default_factory=CanvasRefs)

    @field_validator("key", "name")
    @classmethod
    def validate_required_non_empty_fields(cls, v: Any, info) -> str:
        value = "" if v is None else str(v).strip()
        if not value:
            raise ValueError(f"字段 '{info.field_name}' 不能为空")
        return value

    @field_validator("desc", mode="before")
    @classmethod
    def normalize_desc(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.SCREEN)


class ReportItem(ScreenItem):
    @field_validator("view_sets", mode="before")
    @classmethod
    def normalize_view_sets(cls, v: Any) -> dict:
        return _normalize_canvas_view_sets_for_storage(v, ObjectType.REPORT)
```

Extend `YAMLDocument`:

```python
screens: list[ScreenItem] = Field(default_factory=list)
reports: list[ReportItem] = Field(default_factory=list)
```

Update `count_objects` to include `screen` and `report`.

- [ ] **Step 6: Update services maps and loops**

In export/import/precheck services:

```python
from apps.operation_analysis.models.models import Architecture, Dashboard, Report, Screen, Topology

MODEL_MAP = {
    ObjectType.DASHBOARD: Dashboard,
    ObjectType.TOPOLOGY: Topology,
    ObjectType.ARCHITECTURE: Architecture,
    ObjectType.SCREEN: Screen,
    ObjectType.REPORT: Report,
    ObjectType.DATASOURCE: DataSourceAPIModel,
    ObjectType.NAMESPACE: NameSpace,
}
```

Add `screens` and `reports` sections to export data, sorting list, counts, precheck conflict loops, dependency loops, import execution loops, and log message.

- [ ] **Step 7: Run import/export tests**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_export_and_viewsets.py apps/operation_analysis/tests/test_import_service.py -q
```

Expected: PASS.

## Task 5: Frontend Canvas Type Registry, API, Sidebar, View Routing

**Files:**

- Create: `web/src/app/ops-analysis/constants/canvasTypes.ts`
- Modify: `web/src/app/ops-analysis/types/index.ts`
- Modify: `web/src/app/ops-analysis/api/index.ts`
- Create: `web/src/app/ops-analysis/api/screen.ts`
- Create: `web/src/app/ops-analysis/api/report.ts`
- Modify: `web/src/app/ops-analysis/api/importExport.ts`
- Modify: `web/src/app/ops-analysis/components/sidebar.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/page.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: Write a lightweight frontend registry smoke script**

Create `web/scripts/ops-analysis-canvas-type-registry-test.ts`:

```ts
import { canvasTypeRegistry, contentCanvasTypes } from '../src/app/ops-analysis/constants/canvasTypes';

const keys = Object.keys(canvasTypeRegistry).sort();
const expected = ['architecture', 'dashboard', 'report', 'screen', 'topology'];

if (JSON.stringify(keys) !== JSON.stringify(expected)) {
  throw new Error(`Unexpected registry keys: ${keys.join(',')}`);
}

if (!contentCanvasTypes.includes('screen') || !contentCanvasTypes.includes('report')) {
  throw new Error('screen/report missing from contentCanvasTypes');
}

if (canvasTypeRegistry.architecture.apiPath !== '/operation_analysis/api/architecture/') {
  throw new Error('architecture api path changed unexpectedly');
}
```

- [ ] **Step 2: Run script to verify failure**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-canvas-type-registry-test.ts
```

Expected: FAIL because `constants/canvasTypes.ts` does not exist.

- [ ] **Step 3: Add registry**

Create `web/src/app/ops-analysis/constants/canvasTypes.ts`:

```ts
import {
  ApartmentOutlined,
  BarChartOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
} from '@ant-design/icons';

export type CanvasContentType =
  | 'dashboard'
  | 'topology'
  | 'architecture'
  | 'screen'
  | 'report';

export const canvasTypeRegistry = {
  dashboard: {
    type: 'dashboard',
    labelKey: 'opsAnalysisSidebar.objectTypeLabel.dashboard',
    addLabelKey: 'opsAnalysisSidebar.addDash',
    editLabelKey: 'opsAnalysisSidebar.editDash',
    apiPath: '/operation_analysis/api/dashboard/',
    permissionKey: 'directory.dashboard',
    iconComponent: BarChartOutlined,
    iconClassName: 'mr-1 text-purple-600',
  },
  topology: {
    type: 'topology',
    labelKey: 'opsAnalysisSidebar.objectTypeLabel.topology',
    addLabelKey: 'opsAnalysisSidebar.addTopo',
    editLabelKey: 'opsAnalysisSidebar.editTopo',
    apiPath: '/operation_analysis/api/topology/',
    permissionKey: 'directory.topology',
    customIconType: 'tuoputu',
    iconClassName: 'mr-1',
  },
  architecture: {
    type: 'architecture',
    labelKey: 'opsAnalysisSidebar.objectTypeLabel.architecture',
    addLabelKey: 'opsAnalysisSidebar.addArch',
    editLabelKey: 'opsAnalysisSidebar.editArch',
    apiPath: '/operation_analysis/api/architecture/',
    permissionKey: 'directory.architecture',
    iconComponent: ApartmentOutlined,
    iconClassName: 'mr-1 text-green-600 text-sm',
  },
  screen: {
    type: 'screen',
    labelKey: 'opsAnalysisSidebar.objectTypeLabel.screen',
    addLabelKey: 'opsAnalysisSidebar.addScreen',
    editLabelKey: 'opsAnalysisSidebar.editScreen',
    apiPath: '/operation_analysis/api/screen/',
    permissionKey: 'directory.screen',
    iconComponent: FundProjectionScreenOutlined,
    iconClassName: 'mr-1 text-cyan-600',
  },
  report: {
    type: 'report',
    labelKey: 'opsAnalysisSidebar.objectTypeLabel.report',
    addLabelKey: 'opsAnalysisSidebar.addReport',
    editLabelKey: 'opsAnalysisSidebar.editReport',
    apiPath: '/operation_analysis/api/report/',
    permissionKey: 'directory.report',
    iconComponent: FileTextOutlined,
    iconClassName: 'mr-1 text-orange-600',
  },
} as const;

export const contentCanvasTypes = Object.keys(canvasTypeRegistry) as CanvasContentType[];

export const isContentCanvasType = (type?: string): type is CanvasContentType =>
  Boolean(type && type in canvasTypeRegistry);
```

- [ ] **Step 4: Extend types and API**

In `web/src/app/ops-analysis/types/index.ts`:

```ts
export type DirectoryType = 'directory' | 'dashboard' | 'topology' | 'architecture' | 'screen' | 'report' | 'settings';
export type CreateDirectoryType = 'directory' | 'dashboard' | 'topology' | 'architecture' | 'screen' | 'report';
```

In `web/src/app/ops-analysis/api/index.ts`, build endpoints from registry:

```ts
import { canvasTypeRegistry } from '@/app/ops-analysis/constants/canvasTypes';

const API_ENDPOINTS = {
  directory: '/operation_analysis/api/directory/',
  ...Object.fromEntries(
    Object.entries(canvasTypeRegistry).map(([type, meta]) => [type, meta.apiPath]),
  ),
} as const;
```

Create `screen.ts` and `report.ts` with the same get/save shape as architecture:

```ts
import useApiClient from '@/utils/request';

export const useScreenApi = () => {
  const { get, put } = useApiClient();
  return {
    getScreenDetail: async (id: string | number) => get(`/operation_analysis/api/screen/${id}/`),
    saveScreen: async (id: string | number, data: any) => put(`/operation_analysis/api/screen/${id}/`, data),
  };
};
```

Use the same pattern for `useReportApi`.

- [ ] **Step 5: Update Sidebar**

Replace hard-coded canvas checks with `isContentCanvasType` and `contentCanvasTypes`:

```ts
if (modalAction === 'addChild' && currentDir?.data_id) {
  if (isContentCanvasType(newItemType)) {
    itemData.directory = parseInt(currentDir.data_id, 10);
  } else if (newItemType === 'directory') {
    itemData.parent = parseInt(currentDir.data_id, 10);
  }
}
```

Render create menu by looping `contentCanvasTypes` and excluding none:

```tsx
{contentCanvasTypes.map((type) => (
  <Menu.Item
    key={`add-${type}`}
    onClick={(e) => {
      stopEventPropagation(e.domEvent);
      if (!hasPermission(['AddChart'])) return;
      setNewItemType(type);
      showModal('addChild', t(canvasTypeRegistry[type].addLabelKey), '', item, type);
    }}
  >
    <PermissionWrapper requiredPermissions={['AddChart']}>
      {t(canvasTypeRegistry[type].addLabelKey)}
    </PermissionWrapper>
  </Menu.Item>
))}
```

Replace `getDirectoryIcon` with JSX rendering in `sidebar.tsx` because `canvasTypes.ts` is a `.ts` file and must not contain JSX:

```tsx
const getDirectoryIcon = (type: DirectoryType) => {
  if (isContentCanvasType(type)) {
    const meta = canvasTypeRegistry[type];
    if ('customIconType' in meta && meta.customIconType) {
      return <Icon type={meta.customIconType} className={meta.iconClassName} />;
    }
    const IconComponent = meta.iconComponent;
    return <IconComponent className={meta.iconClassName} />;
  }
  if (type === 'directory') {
    return <FolderOutlined className="mr-1" />;
  }
  return '';
};
```

- [ ] **Step 6: Update ViewPage selection state**

Change selected item state to:

```ts
const [selectedItem, setSelectedItem] = useState<Partial<Record<CanvasContentType, DirItem | null>>>({});
```

Replace hard-coded checks with `isContentCanvasType(selectedType)`.

Render components explicitly:

```tsx
{selectedType === 'architecture' ? (
  <Architecture ref={architectureRef} selectedArchitecture={selectedItem.architecture} />
) : selectedType === 'topology' ? (
  <Topology ref={topologyRef} key={selectedItem.topology?.data_id ?? 'topology-empty'} selectedTopology={selectedItem.topology} />
) : selectedType === 'dashboard' ? (
  <Dashboard ref={dashboardRef} key={selectedItem.dashboard?.data_id ?? 'dashboard-empty'} selectedDashboard={selectedItem.dashboard} />
) : selectedType === 'screen' ? (
  <Screen ref={screenRef} key={selectedItem.screen?.data_id ?? 'screen-empty'} selectedScreen={selectedItem.screen} />
) : selectedType === 'report' ? (
  <Report ref={reportRef} key={selectedItem.report?.data_id ?? 'report-empty'} selectedReport={selectedItem.report} />
) : (
  <Empty className="w-full mt-[20vh]" description={t('opsAnalysisSidebar.selectItem')} />
)}
```

- [ ] **Step 7: Add locale keys**

In zh/en locale files add:

```json
"addScreen": "新增大屏",
"editScreen": "编辑大屏",
"addReport": "新增报表",
"editReport": "编辑报表"
```

and object labels:

```json
"screen": "大屏",
"report": "报表"
```

- [ ] **Step 8: Run registry smoke script**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-canvas-type-registry-test.ts
```

Expected: PASS.

## Task 6: Screen Minimal Page

**Files:**

- Create: `web/src/app/ops-analysis/types/screen.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/index.module.scss`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`

- [ ] **Step 1: Create viewport utility test script first**

Create `web/scripts/ops-analysis-screen-viewport-test.ts`:

```ts
import { calculateScreenScale, normalizeScreenViewSets } from '../src/app/ops-analysis/(pages)/view/screen/utils/viewport';

const normalized = normalizeScreenViewSets({});
if (normalized.viewport.width !== 1920 || normalized.viewport.height !== 1080) {
  throw new Error('default viewport should be 1920x1080');
}

const scale = calculateScreenScale({ width: 1920, height: 1080 }, { width: 960, height: 540 });
if (scale !== 0.5) {
  throw new Error(`expected scale 0.5, got ${scale}`);
}

const fit = calculateScreenScale({ width: 1920, height: 1080 }, { width: 1000, height: 1000 });
if (Math.round(fit * 1000) !== 521) {
  throw new Error(`expected width-bound scale about 0.521, got ${fit}`);
}
```

- [ ] **Step 2: Run script to verify failure**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-screen-viewport-test.ts
```

Expected: FAIL because screen utility does not exist.

- [ ] **Step 3: Add Screen types and utility**

Create `web/src/app/ops-analysis/types/screen.ts`:

```ts
import type { DirItem } from './index';
import type { ValueConfig } from './dashBoard';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';

export interface ScreenViewport {
  width: number;
  height: number;
  theme: OpsChartThemeMode;
  background?: {
    type?: string;
    key?: string;
  };
}

export interface ScreenItem {
  id: string;
  type: 'widget' | 'text' | 'frame';
  x: number;
  y: number;
  w: number;
  h: number;
  zIndex?: number;
  title?: string;
  valueConfig?: ValueConfig;
  frame?: {
    variant?: 'plain' | 'glass' | 'tech';
    showTitle?: boolean;
  };
}

export interface ScreenViewSets {
  viewport: ScreenViewport;
  items: ScreenItem[];
  decorations: {
    title?: string;
    showTitle?: boolean;
    showClock?: boolean;
  };
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
}
```

Create utility:

```ts
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';

export const DEFAULT_SCREEN_VIEW_SETS: ScreenViewSets = {
  viewport: {
    width: 1920,
    height: 1080,
    theme: 'screen-dark',
    background: { type: 'preset', key: 'screen-dark' },
  },
  items: [],
  decorations: {
    title: '',
    showTitle: true,
    showClock: true,
  },
};

export const normalizeScreenViewSets = (value: unknown): ScreenViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return DEFAULT_SCREEN_VIEW_SETS;
  }
  const record = value as Partial<ScreenViewSets>;
  return {
    viewport: {
      width: Number(record.viewport?.width) || 1920,
      height: Number(record.viewport?.height) || 1080,
      theme: record.viewport?.theme || 'screen-dark',
      background: record.viewport?.background || { type: 'preset', key: 'screen-dark' },
    },
    items: Array.isArray(record.items) ? record.items : [],
    decorations: {
      title: record.decorations?.title || '',
      showTitle: record.decorations?.showTitle !== false,
      showClock: record.decorations?.showClock !== false,
    },
  };
};

export const calculateScreenScale = (
  viewport: { width: number; height: number },
  container: { width: number; height: number },
) => Math.min(container.width / viewport.width, container.height / viewport.height);
```

- [ ] **Step 4: Add minimal Screen page**

Implement `screen/index.tsx` with:

- `forwardRef` exposing `hasUnsavedChanges`.
- Detail load using `useScreenApi`.
- Edit mode, save, cancel.
- Config modal for width/height/theme/title/clock.
- Empty canvas with fixed viewport scaled to available space.

Minimal save payload:

```ts
await saveScreen(selectedScreen.data_id, {
  name: selectedScreen.name,
  desc: selectedScreen.desc || '',
  groups: selectedScreen.groups || [],
  directory: Number(selectedScreen.id.split('_')[1]) || undefined,
  view_sets: viewSets,
});
```

If directory cannot be derived from selected item, omit `directory` on `PUT` and keep backend existing value through full serializer payload from fetched detail.

- [ ] **Step 5: Add Screen canvas and frame components**

`screenCanvas.tsx` renders a constrained stage:

```tsx
<div className={styles.stageWrap} ref={containerRef}>
  <div
    className={styles.stage}
    style={{
      width: viewSets.viewport.width,
      height: viewSets.viewport.height,
      transform: `scale(${scale})`,
      transformOrigin: 'top left',
    }}
  >
    {viewSets.decorations.showTitle && <div className={styles.title}>{viewSets.decorations.title || selectedName}</div>}
    {viewSets.decorations.showClock && <div className={styles.clock}>{clockText}</div>}
    {viewSets.items.map((item) => <ScreenWidgetFrame key={item.id} item={item} />)}
  </div>
</div>
```

`screenWidgetFrame.tsx` uses `WidgetRenderer` and passes `chartThemeMode: viewSets.viewport.theme`.

- [ ] **Step 6: Run viewport script and type-check**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-screen-viewport-test.ts
cd web && pnpm type-check
```

Expected: both PASS.

## Task 7: Report Minimal Page

**Files:**

- Create: `web/src/app/ops-analysis/types/report.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/report/index.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/report/index.module.scss`
- Create: `web/src/app/ops-analysis/(pages)/view/report/components/reportToolbar.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/report/components/reportEditor.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/report/components/reportSection.tsx`

- [ ] **Step 1: Create report normalization script first**

Create `web/scripts/ops-analysis-report-viewsets-test.ts`:

```ts
import { normalizeReportViewSets } from '../src/app/ops-analysis/types/report';

const normalized = normalizeReportViewSets({});
if (normalized.sections.length !== 0) {
  throw new Error('default report sections should be empty');
}

const withBadSections = normalizeReportViewSets({ sections: 'bad' });
if (withBadSections.sections.length !== 0) {
  throw new Error('bad report sections should normalize to empty array');
}
```

- [ ] **Step 2: Run script to verify failure**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-report-viewsets-test.ts
```

Expected: FAIL because report types do not exist.

- [ ] **Step 3: Add Report type and normalization**

Create `web/src/app/ops-analysis/types/report.ts`:

```ts
import type { DirItem } from './index';
import type { ValueConfig } from './dashBoard';

export interface ReportSection {
  id: string;
  type: 'text' | 'chart' | 'table' | 'summary';
  title: string;
  content?: string;
  valueConfig?: ValueConfig;
}

export interface ReportViewSets {
  time_range: null | {
    start?: number;
    end?: number;
  };
  sections: ReportSection[];
}

export interface ReportProps {
  selectedReport?: DirItem | null;
}

export const normalizeReportViewSets = (value: unknown): ReportViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { time_range: null, sections: [] };
  }
  const record = value as Partial<ReportViewSets>;
  return {
    time_range: record.time_range || null,
    sections: Array.isArray(record.sections) ? record.sections : [],
  };
};
```

- [ ] **Step 4: Add minimal Report page**

Implement Report with:

- `forwardRef` exposing `hasUnsavedChanges`.
- Detail load using `useReportApi`.
- Read view shows report title/desc and empty state.
- Edit mode can add text section and save.
- No schedule/export/history UI.

- [ ] **Step 5: Run report script and type-check**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-report-viewsets-test.ts
cd web && pnpm type-check
```

Expected: PASS.

## Task 8: Topology Presentation Cleanup

**Files:**

- Modify: `web/src/app/ops-analysis/types/topology.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/index.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/components/canvasShell.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/components/chartNode.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphData.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/hooks/useTopologyLifecycle.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/index.module.scss`
- Delete: `web/src/app/ops-analysis/(pages)/view/topology/components/presentationModal.tsx`
- Delete: `web/src/app/ops-analysis/(pages)/view/topology/hooks/useTopologyPresentation.ts`
- Delete: `web/src/app/ops-analysis/(pages)/view/topology/utils/viewport.ts`

- [ ] **Step 1: Create static cleanup check script**

Create `web/scripts/ops-analysis-topology-screen-cleanup-test.ts`:

```ts
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const root = join(process.cwd(), 'src/app/ops-analysis');
const forbiddenFiles = [
  '(pages)/view/topology/components/presentationModal.tsx',
  '(pages)/view/topology/hooks/useTopologyPresentation.ts',
  '(pages)/view/topology/utils/viewport.ts',
];

for (const file of forbiddenFiles) {
  if (existsSync(join(root, file))) {
    throw new Error(`Forbidden topology presentation file still exists: ${file}`);
  }
}

const checkedFiles = [
  '(pages)/view/topology/index.tsx',
  '(pages)/view/topology/components/toolbar.tsx',
  '(pages)/view/topology/hooks/useGraphData.ts',
  'types/topology.ts',
];

const forbiddenPatterns = [
  'TopologyPresentation',
  'useTopologyPresentation',
  'presentationConfig',
  'viewportConfig',
  'screen-title',
  'screen-clock',
  'decorative-frame',
  'tech-blue',
  'showChartThemeMode={true}',
];

for (const file of checkedFiles) {
  const content = readFileSync(join(root, file), 'utf8');
  for (const pattern of forbiddenPatterns) {
    if (content.includes(pattern)) {
      throw new Error(`${file} still contains ${pattern}`);
    }
  }
}
```

- [ ] **Step 2: Run script to verify failure**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-topology-screen-cleanup-test.ts
```

Expected: FAIL because presentation files and strings still exist.

- [ ] **Step 3: Remove topology presentation types**

In `web/src/app/ops-analysis/types/topology.ts`:

- Delete `TopologyViewportConfig`.
- Delete `TopologyPresentationConfig`.
- Remove `presentationRole` from `TopologyNodeData`.
- Remove `renderEffect`, `frameVariant`, and screen-oriented style fields if only used for presentation.
- Remove `presentation` from topology view-set related interfaces.
- Remove `chartThemeMode?: OpsChartThemeMode` from topology-only form values if it only powers topology node config.

- [ ] **Step 4: Remove toolbar presentation entry**

In `toolbar.tsx`:

- Remove `DesktopOutlined` import.
- Remove `onPresentationConfig` prop usage.
- Remove the button rendering `topology.presentationConfig`.

- [ ] **Step 5: Clean `index.tsx`**

Remove:

- Presentation imports.
- `SCREEN_TITLE_NODE_IDS`, `SCREEN_CLOCK_NODE_IDS`.
- `buildDefaultScreenTitleNodes`.
- `buildDefaultScreenClockNode`.
- `applyPresentationChromeNodes`.
- `isCanvasBackgroundEnabled`.
- `screenDarkTheme`.
- `presentationHostRef`.
- `viewportConfig`, `presentationConfig`, chrome draft states.
- `useTopologyPresentation`.
- `handleConfirmPresentationConfig`.
- Screen clock interval.
- `techBluePresentation` class application.
- `TopologyPresentationModal`.
- `showChartThemeMode={true}` on `ViewConfig`.

Keep:

- Standard full screen via `useAppViewFullscreen`.
- Fit view/zoom/edit/save/filter/refresh.
- Node/edge graph editing.

- [ ] **Step 6: Clean graph serialization**

In `useGraphData.ts`:

- Stop serializing `presentationRole`.
- Save topology as:

```ts
{
  nodes,
  edges,
  filters,
}
```

- Load topology by reading only `nodes`, `edges`, `filters`.

In `useTopologyLifecycle.ts`, remove original viewport/presentation state snapshots from unsaved-change calculation.

- [ ] **Step 7: Clean chart node screen chrome**

In `chartNode.tsx`:

- Replace `getOpsChartThemeByMode(valueConfig?.chartThemeMode)` with `getOpsChartThemeByMode('default')` or `getOpsChartTheme(resolveOpsChartThemeName())` following dashboard’s normal mode.
- Remove `panelChrome*` usage and use neutral panel styles:

```ts
const panelBg = chartTheme.panelBg;
const panelBorderColor = chartTheme.panelBorderColor;
```

- [ ] **Step 8: Remove tech-blue CSS**

In `index.module.scss`, delete `.techBluePresentation` and `.ops-screen-empty` blocks. Keep ordinary topology graph background and minimap styling.

- [ ] **Step 9: Run cleanup script and type-check**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-topology-screen-cleanup-test.ts
cd web && pnpm type-check
```

Expected: PASS.

## Task 9: Full Verification

**Files:**

- Modify: `web/src/app/ops-analysis/design.md`
- Modify: `web/src/app/ops-analysis/public/versions/ops-analysis/zh/2026-06-12.md` or create a current release-note file if the project uses dated release notes for this change.
- Modify: `web/src/app/ops-analysis/public/versions/ops-analysis/en/2026-06-12.md` or matching current file.

- [ ] **Step 1: Backend focused test gate**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_directory_views.py apps/operation_analysis/tests/test_export_and_viewsets.py apps/operation_analysis/tests/test_import_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Backend full module gate**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests -q
```

Expected: PASS.

- [ ] **Step 3: Frontend focused scripts**

Run:

```bash
cd web && pnpm exec tsx scripts/ops-analysis-canvas-type-registry-test.ts
cd web && pnpm exec tsx scripts/ops-analysis-screen-viewport-test.ts
cd web && pnpm exec tsx scripts/ops-analysis-report-viewsets-test.ts
cd web && pnpm exec tsx scripts/ops-analysis-topology-screen-cleanup-test.ts
```

Expected: all PASS.

- [ ] **Step 4: Frontend gate**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: PASS.

- [ ] **Step 5: Manual browser verification**

Run dev server:

```bash
cd web && pnpm dev
```

Verify:

- Directory context menu shows Add Dashboard, Add Topology, Add Architecture, Add Screen, Add Report.
- Creating Architecture still opens Architecture view.
- Creating Screen opens Screen view with 1920x1080 default stage.
- Creating Report opens Report view with empty report shell.
- Topology toolbar has no presentation/big-screen configuration button.
- Topology node chart config has no Screen Dark/Screen Light theme option.
- Export modal accepts screen/report object types.
- Import precheck recognizes `screens` and `reports` sections.

- [ ] **Step 6: Documentation update**

Update `web/src/app/ops-analysis/design.md` with:

- Current canvas types.
- Topology no longer owns presentation.
- Screen owns fixed resolution and big-screen visual theme.
- Report is basic object shell.

Do not document old topology big-screen behavior as supported.

## Self-Review Checklist

- Spec coverage: The plan covers backend model/API, directory tree, import/export, frontend entry/routing, Screen, Report, topology cleanup, and verification.
- User boundary: `Architecture` remains first-class and is not redirected to Screen.
- User boundary: No legacy topology presentation migration is planned.
- Scope boundary: Report is only an object shell; no schedule/snapshot/export/history.
- Type consistency: Backend and frontend both use `screen` and `report`; YAML sections are `screens` and `reports`.
- Test-first: Each implementation task starts with a failing backend test or frontend script before production code.
- Commit policy: Do not commit automatically in this thread. If the user later asks for commits, commit by completed task with focused messages.
