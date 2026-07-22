# Historical Superpowers change: 2026-07-20-cmdb-open-api

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-20-cmdb-open-api.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为外部系统提供使用 `Api-Authorization` 鉴权、固定 API Secret 绑定团队并继承用户当前 CMDB RBAC 的模型只读、实例单条/批量 CRUD 和实例关联 REST OpenAPI。

**Architecture:** 在 `apps.cmdb.open_api` 中建立独立 HTTP 门面，由认证上下文、动态请求校验、领域编排和 APIView 四个职责明确的单元组成。门面只调用现有 `ClassificationManage`、`ModelManage`、`InstanceManage`，不直接暴露控制台 ViewSet，也不调用会跳过权限的 CMDB NATS handler；批量创建能力在 `InstanceManage` 增加一个复用现有校验、审计和后处理的领域方法。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、pytest/pytest-django、FalkorDB GraphClient、现有 `UserAPISecret`/`APISecretMiddleware`/CMDB RBAC。

## Global Constraints

- 认证头固定为 `Api-Authorization: <api_secret>`，不新增第二套认证协议。
- API Secret 只能访问唯一绑定团队，不包含子团队，不接受客户端 `team`、`allowed_org_ids` 或 `include_children`。
- API Secret 同时继承所属用户当前 CMDB RBAC；权限数据缺失时 fail-closed。
- 模型相关接口只读；实例支持单条和批量 CRUD；实例关联支持查询、创建和删除。
- 创建实例时服务端强制写入 `organization: [绑定团队]`；更新禁止修改 `organization`。
- 实例列表使用 `{field, type, value}` 动态过滤，默认 `page_size=20`，最大 `200`；批量写入最多 `100` 条。
- 批量接口先完成全部预校验，只提供整体成功或整体错误契约；跨 FalkorDB、Django 数据库和异步后处理不宣称分布式事务。
- 不新增原生 SQL、NATS 外部入口、数据库 migration、API Secret scope 或写请求幂等存储。
- 只修改本计划列出的 CMDB 文件；不得格式化无关文件，现有 REST/NATS 契约必须保持不变。
- 每项功能严格按 TDD 红—绿—重构执行，改动代码覆盖率不低于 75%。

## File Structure

新增包与文件：

- `server/apps/cmdb/open_api/__init__.py`：OpenAPI 包标识，不承载业务逻辑。
- `server/apps/cmdb/open_api/errors.py`：稳定应用错误码和 `CMDBOpenAPIError`。
- `server/apps/cmdb/open_api/responses.py`：统一 `{result,data,message,code}` 响应。
- `server/apps/cmdb/open_api/auth.py`：仅 API Secret 访问、固定团队解析、菜单权限和对象权限 map。
- `server/apps/cmdb/open_api/serializers.py`：分页、过滤、动态实例字段、批量和关联请求校验。
- `server/apps/cmdb/open_api/services.py`：模型、实例、批量和关联领域编排；所有授权判断集中于此。
- `server/apps/cmdb/open_api/views.py`：薄 APIView，仅负责输入、service 调用和 HTTP 状态。
- `server/apps/cmdb/tests/test_open_api_auth_pure.py`：认证上下文和 fail-closed 权限单测。
- `server/apps/cmdb/tests/test_open_api_serializers_pure.py`：动态契约纯单测。
- `server/apps/cmdb/tests/test_open_api_model_views.py`：模型只读 HTTP 契约。
- `server/apps/cmdb/tests/test_open_api_instance_views.py`：实例单条 HTTP 契约。
- `server/apps/cmdb/tests/test_open_api_batch_service.py`：批量领域行为和回滚测试。
- `server/apps/cmdb/tests/test_open_api_batch_views.py`：批量 HTTP 契约。
- `server/apps/cmdb/tests/test_open_api_association_views.py`：关联双端授权与 HTTP 契约。
- `server/apps/cmdb/docs/open_api.md`：外部调用说明与 curl 示例。
- `server/apps/cmdb/docs/openapi.yaml`：可导入 OpenAPI 3.0 描述。

修改现有文件：

- `server/apps/cmdb/urls.py`：显式注册 `/api/open/...` 路由，并确保 batch 路由先于 `<int:inst_id>`。
- `server/apps/cmdb/services/instance.py`：增加批量创建领域方法；单实例已有签名保持不变。

---

### Task 1: OpenAPI 响应、认证上下文与动态请求校验

**Files:**
- Create: `server/apps/cmdb/open_api/__init__.py`
- Create: `server/apps/cmdb/open_api/errors.py`
- Create: `server/apps/cmdb/open_api/responses.py`
- Create: `server/apps/cmdb/open_api/auth.py`
- Create: `server/apps/cmdb/open_api/serializers.py`
- Test: `server/apps/cmdb/tests/test_open_api_auth_pure.py`
- Test: `server/apps/cmdb/tests/test_open_api_serializers_pure.py`

**Interfaces:**
- Consumes: `request.api_pass`、`request.user`、`get_permission_rules(...)`、`CmdbRulesFormatUtil.build_permission_rule_map(...)`。
- Produces: `CMDBOpenAPIContext.from_request(request)`、`context.require_feature(permission)`、`context.permission_map(model_id, permission_type)`、`validate_instance_payload(...)`、`InstanceListQuerySerializer`、`Batch*Serializer`、`open_api_success(...)`、`open_api_error(...)`。

- [ ] **Step 1: 写认证上下文失败测试**

```python
# server/apps/cmdb/tests/test_open_api_auth_pure.py
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.cmdb.open_api.auth import CMDBOpenAPIContext
from apps.cmdb.open_api.errors import CMDBOpenAPIError


def _request(*, api_pass=True, groups=None, permissions=None):
    user = SimpleNamespace(
        username="api-user",
        domain="domain.com",
        group_list=groups or [{"id": 7}],
        roles=["cmdb-reader"],
        permission={"cmdb": set(permissions or [])},
        is_superuser=False,
        locale="zh-CN",
    )
    return SimpleNamespace(api_pass=api_pass, user=user, COOKIES={"include_children": "1"})


def test_context_rejects_non_api_secret_request():
    with pytest.raises(CMDBOpenAPIError) as exc:
        CMDBOpenAPIContext.from_request(_request(api_pass=False))
    assert exc.value.status_code == 403
    assert exc.value.code == "cmdb.auth.api_secret_required"


def test_context_uses_only_secret_bound_team_and_ignores_child_cookie():
    context = CMDBOpenAPIContext.from_request(_request(groups=[{"id": 7}]))
    assert context.team_id == 7
    assert context.user_groups == [{"id": 7}]


@patch("apps.cmdb.open_api.auth.get_permission_rules")
def test_permission_map_is_fail_closed_and_never_includes_children(mock_rules):
    mock_rules.return_value = {}
    context = CMDBOpenAPIContext.from_request(_request())
    result = context.permission_map("host", "instances")
    assert set(result) == {7}
    assert result[7]["inst_names"]
    mock_rules.assert_called_once_with(
        user=context.user,
        current_team=7,
        app_name="cmdb",
        permission_key="instances.host",
        include_children=False,
    )
```

- [ ] **Step 2: 运行认证测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_auth_pure.py -q --no-cov`

Expected: collection FAIL，提示 `apps.cmdb.open_api` 不存在。

- [ ] **Step 3: 实现稳定错误、响应和认证上下文**

```python
# server/apps/cmdb/open_api/errors.py
class CMDBOpenAPIError(Exception):
    def __init__(self, code: str, message: str, status_code: int, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data or {}


# server/apps/cmdb/open_api/responses.py
from django.http import JsonResponse


def open_api_success(data=None, *, status_code=200):
    return JsonResponse(
        {"result": True, "data": data if data is not None else {}, "message": "", "code": "ok"},
        status=status_code,
    )


def open_api_error(error):
    return JsonResponse(
        {"result": False, "data": error.data, "message": error.message, "code": error.code},
        status=error.status_code,
    )


# server/apps/cmdb/open_api/auth.py
from dataclasses import dataclass

from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.utils.permission_utils import get_permission_rules

from .errors import CMDBOpenAPIError


@dataclass(frozen=True)
class CMDBOpenAPIContext:
    user: object
    team_id: int

    @property
    def user_groups(self):
        return [{"id": self.team_id}]

    @classmethod
    def from_request(cls, request):
        if not getattr(request, "api_pass", False):
            raise CMDBOpenAPIError("cmdb.auth.api_secret_required", "必须使用 API Secret", 403)
        groups = getattr(request.user, "group_list", []) or []
        if len(groups) != 1:
            raise CMDBOpenAPIError("cmdb.auth.invalid_team", "API Secret 团队绑定无效", 403)
        raw_team = groups[0].get("id") if isinstance(groups[0], dict) else groups[0]
        try:
            team_id = int(raw_team)
        except (TypeError, ValueError):
            raise CMDBOpenAPIError("cmdb.auth.invalid_team", "API Secret 团队绑定无效", 403) from None
        return cls(user=request.user, team_id=team_id)

    def require_feature(self, permission: str):
        if getattr(self.user, "is_superuser", False):
            return
        user_permissions = getattr(self.user, "permission", {}) or {}
        if permission not in set(user_permissions.get("cmdb", set())):
            raise CMDBOpenAPIError("cmdb.permission.denied", "权限不足", 403)

    def permission_map(self, model_id: str, permission_type: str):
        if getattr(self.user, "is_superuser", False):
            return {self.team_id: {"permission_instances_map": {}, "inst_names": []}}
        key = f"{permission_type}.{model_id}" if model_id else permission_type
        rules = get_permission_rules(
            user=self.user,
            current_team=self.team_id,
            app_name="cmdb",
            permission_key=key,
            include_children=False,
        )
        return CmdbRulesFormatUtil.build_permission_rule_map(
            user_teams=[self.team_id],
            permission_rules=rules if isinstance(rules, dict) else {},
            fallback_team_id=self.team_id,
        )
```

- [ ] **Step 4: 写动态过滤和实例载荷失败测试**

```python
# server/apps/cmdb/tests/test_open_api_serializers_pure.py
import json

import pytest
from rest_framework.exceptions import ValidationError

from apps.cmdb.open_api.serializers import (
    InstanceListQuerySerializer,
    validate_instance_payload,
)


ATTRS = [
    {"attr_id": "inst_name", "attr_type": "str", "editable": True},
    {"attr_id": "ip_addr", "attr_type": "str", "editable": True},
    {"attr_id": "serial", "attr_type": "str", "editable": False},
    {"attr_id": "organization", "attr_type": "organization", "editable": True},
]


def test_query_parses_filters_and_maps_public_order_field():
    serializer = InstanceListQuerySerializer(
        data={
            "page": "2",
            "page_size": "50",
            "order": "-updated_at",
            "filters": '[{"field":"ip_addr","type":"str*","value":"10."}]',
        },
        context={"attrs": ATTRS},
    )
    serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["order"] == "-_updated_at"
    assert serializer.validated_data["filters"][0]["field"] == "ip_addr"


@pytest.mark.parametrize("field", ["organization", "_creator", "unknown"])
def test_query_rejects_unsafe_or_unknown_filter_field(field):
    serializer = InstanceListQuerySerializer(
        data={"filters": json.dumps([{"field": field, "type": "str=", "value": "x"}])},
        context={"attrs": ATTRS},
    )
    assert not serializer.is_valid()


def test_query_rejects_operator_incompatible_with_attribute_type():
    serializer = InstanceListQuerySerializer(
        data={"filters": json.dumps([{"field": "ip_addr", "type": "int=", "value": 10}])},
        context={"attrs": ATTRS},
    )
    assert not serializer.is_valid()


def test_create_payload_forces_team_and_rejects_system_fields():
    assert validate_instance_payload({"inst_name": "h1"}, ATTRS, team_id=7, for_update=False)["organization"] == [7]
    with pytest.raises(ValidationError):
        validate_instance_payload({"_id": 1}, ATTRS, team_id=7, for_update=False)


def test_update_payload_rejects_organization_change():
    with pytest.raises(ValidationError):
        validate_instance_payload({"organization": [9]}, ATTRS, team_id=7, for_update=True)


def test_update_payload_rejects_readonly_attribute():
    with pytest.raises(ValidationError):
        validate_instance_payload({"serial": "changed"}, ATTRS, team_id=7, for_update=True)
```

- [ ] **Step 5: 运行 Serializer 测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_serializers_pure.py -q --no-cov`

Expected: FAIL，提示 `InstanceListQuerySerializer` 和 `validate_instance_payload` 未定义。

- [ ] **Step 6: 实现 Serializer 与纯校验器**

```python
# server/apps/cmdb/open_api/serializers.py
import json

from rest_framework import serializers

FILTER_TYPES = {"str=", "str*", "str[]", "int=", "int[]", "list[]"}
FORBIDDEN_FIELDS = {"_id", "model_id", "organization", "_creator", "_created_at", "_updated_at"}
ORDER_ALIASES = {"created_at": "_created_at", "updated_at": "_updated_at", "inst_id": "_id"}


class InstanceListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=20, min_value=1, max_value=200)
    order = serializers.CharField(default="", allow_blank=True)
    filters = serializers.CharField(default="[]", allow_blank=True)

    def validate_filters(self, raw):
        try:
            filters = json.loads(raw or "[]")
        except (TypeError, ValueError):
            raise serializers.ValidationError("filters 必须是 JSON 数组") from None
        if not isinstance(filters, list):
            raise serializers.ValidationError("filters 必须是 JSON 数组")
        attrs = {item["attr_id"]: item for item in self.context["attrs"] if item.get("attr_id")}
        for item in filters:
            if not isinstance(item, dict) or set(item) != {"field", "type", "value"}:
                raise serializers.ValidationError("过滤条件必须包含 field、type、value")
            if item["field"] in FORBIDDEN_FIELDS or item["field"] not in attrs:
                raise serializers.ValidationError("过滤字段不可用")
            if item["type"] not in FILTER_TYPES:
                raise serializers.ValidationError("过滤操作符不可用")
            attr_type = attrs[item["field"]].get("attr_type")
            compatible_types = {
                "str": {"str=", "str*", "str[]"},
                "int": {"int=", "int[]"},
                "list": {"list[]"},
            }
            if item["type"] not in compatible_types.get(attr_type, set()):
                raise serializers.ValidationError("过滤操作符与字段类型不兼容")
        return filters

    def validate_order(self, raw):
        descending = raw.startswith("-")
        field = raw[1:] if descending else raw
        if not field:
            return ""
        attrs = {item["attr_id"] for item in self.context["attrs"] if item.get("attr_id")}
        mapped = ORDER_ALIASES.get(field, field)
        if field not in attrs and field not in ORDER_ALIASES:
            raise serializers.ValidationError("排序字段不可用")
        return f"-{mapped}" if descending else mapped


def validate_instance_payload(data, attrs, *, team_id, for_update):
    if not isinstance(data, dict) or not data:
        raise serializers.ValidationError("实例属性必须是非空对象")
    allowed = {
        item["attr_id"]
        for item in attrs
        if item.get("attr_id")
        and (not for_update or item.get("editable", False))
        and not item.get("is_display_field", False)
    }
    invalid = set(data) - allowed
    if invalid or set(data) & FORBIDDEN_FIELDS:
        raise serializers.ValidationError({"fields": sorted(invalid | (set(data) & FORBIDDEN_FIELDS))})
    result = dict(data)
    if not for_update:
        result["organization"] = [team_id]
    return result


class BatchCreateSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)


class BatchUpdateSerializer(serializers.Serializer):
    inst_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100)
    update_data = serializers.DictField()


class BatchDeleteSerializer(serializers.Serializer):
    inst_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100)


class AssociationCreateSerializer(serializers.Serializer):
    model_asst_id = serializers.CharField(max_length=255)
    target_model_id = serializers.CharField(max_length=255)
    target_inst_id = serializers.IntegerField(min_value=1)
```

- [ ] **Step 7: 运行 Task 1 测试并提交**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_auth_pure.py apps/cmdb/tests/test_open_api_serializers_pure.py -q --no-cov`

Expected: PASS。

```bash
git add server/apps/cmdb/open_api server/apps/cmdb/tests/test_open_api_auth_pure.py server/apps/cmdb/tests/test_open_api_serializers_pure.py
git commit -m "功能：建立 CMDB OpenAPI 安全契约"
```

### Task 2: 模型只读 Service、View 与路由

**Files:**
- Create: `server/apps/cmdb/open_api/services.py`
- Create: `server/apps/cmdb/open_api/views.py`
- Modify: `server/apps/cmdb/urls.py`
- Test: `server/apps/cmdb/tests/test_open_api_model_views.py`

**Interfaces:**
- Consumes: Task 1 的 `CMDBOpenAPIContext`、响应和错误类。
- Produces: `CMDBOpenAPIService.list_classifications/list_models/get_model/get_model_attrs/get_model_associations` 及五个 GET 路由。

- [ ] **Step 1: 写模型只读 HTTP 失败测试**

```python
# server/apps/cmdb/tests/test_open_api_model_views.py
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.django_db


def _api_request(client, url):
    return client.get(url, HTTP_API_AUTHORIZATION="secret")


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.ModelManage.search_model")
def test_model_list_returns_only_service_visible_models(mock_search, mock_context, api_client):
    context = mock_context.return_value
    context.user.locale = "zh-CN"
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    mock_search.return_value = [{"model_id": "host", "classification_id": "infra"}]
    response = _api_request(api_client, "/api/v1/cmdb/api/open/models")
    assert response.status_code == 200
    assert response.json()["data"] == [{"model_id": "host", "classification_id": "infra"}]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info", return_value={})
def test_model_detail_missing_returns_stable_404(mock_info, mock_context, api_client):
    response = _api_request(api_client, "/api/v1/cmdb/api/open/models/missing")
    body = response.json()
    assert response.status_code == 404
    assert body["code"] == "cmdb.model.not_found"
```

- [ ] **Step 2: 运行模型测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_model_views.py -q --no-cov`

Expected: FAIL，路由返回 404 或 `views.py` 不存在。

- [ ] **Step 3: 实现模型授权和只读 service**

```python
# server/apps/cmdb/open_api/services.py
from apps.cmdb.constants.constants import PERMISSION_MODEL, VIEW
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil

from .errors import CMDBOpenAPIError


class CMDBOpenAPIService:
    def __init__(self, context):
        self.context = context

    def _model_permissions(self, model_id=""):
        permissions = self.context.permission_map(model_id, PERMISSION_MODEL)
        default_group_id = get_default_group_id()[0]
        permissions.setdefault(default_group_id, {"permission_instances_map": {}, "inst_names": [], "__default_model": [VIEW]})
        return permissions

    def list_models(self):
        self.context.require_feature("model_management-View")
        return ModelManage.search_model(
            language=self.context.user.locale,
            permissions_map=self._model_permissions(),
            include_hidden=False,
        )

    def list_classifications(self):
        visible_ids = {item["classification_id"] for item in self.list_models()}
        rows = ClassificationManage.search_model_classification(self.context.user.locale, include_hidden=False)
        return [row for row in rows if row.get("classification_id") in visible_ids]

    def get_model(self, model_id):
        self.context.require_feature("model_management-View")
        model = ModelManage.search_model_info(model_id)
        if not model:
            raise CMDBOpenAPIError("cmdb.model.not_found", "模型不存在", 404)
        if not CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=self._model_permissions(model_id),
            instance=model,
            default_group_id=get_default_group_id()[0],
        ):
            raise CMDBOpenAPIError("cmdb.model.not_found", "模型不存在", 404)
        return model

    def get_model_attrs(self, model_id):
        self.get_model(model_id)
        return ModelManage.search_model_attr(model_id)

    def get_model_associations(self, model_id):
        self.get_model(model_id)
        return ModelManage.model_association_search(model_id)
```

- [ ] **Step 4: 实现公共 APIView 基类、模型 Views 和显式路由**

```python
# server/apps/cmdb/open_api/views.py
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.core.exceptions.base_app_exception import BaseAppException

from .auth import CMDBOpenAPIContext
from .errors import CMDBOpenAPIError
from .responses import open_api_error, open_api_success
from .services import CMDBOpenAPIService


class APISecretRequired(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "api_pass", False))


class CMDBOpenAPIView(APIView):
    permission_classes = [APISecretRequired]

    def service(self, request):
        return CMDBOpenAPIService(CMDBOpenAPIContext.from_request(request))

    def handle_exception(self, exc):
        if isinstance(exc, CMDBOpenAPIError):
            return open_api_error(exc)
        if isinstance(exc, BaseAppException):
            return open_api_error(CMDBOpenAPIError("cmdb.validation.failed", exc.message, 400))
        return super().handle_exception(exc)


class OpenClassificationListView(CMDBOpenAPIView):
    def get(self, request):
        return open_api_success(self.service(request).list_classifications())


class OpenModelListView(CMDBOpenAPIView):
    def get(self, request):
        return open_api_success(self.service(request).list_models())


class OpenModelDetailView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model(model_id))


class OpenModelAttrsView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model_attrs(model_id))


class OpenModelAssociationsView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model_associations(model_id))
```

在 `server/apps/cmdb/urls.py` 的 router URLs 之前添加显式 `path`，最终使用 `urlpatterns = open_api_patterns + router.urls`：

```python
from django.urls import path
from apps.cmdb.open_api import views as open_views

open_api_patterns = [
    path("api/open/classifications", open_views.OpenClassificationListView.as_view()),
    path("api/open/models", open_views.OpenModelListView.as_view()),
    path("api/open/models/<str:model_id>", open_views.OpenModelDetailView.as_view()),
    path("api/open/models/<str:model_id>/attributes", open_views.OpenModelAttrsView.as_view()),
    path("api/open/models/<str:model_id>/associations", open_views.OpenModelAssociationsView.as_view()),
]
```

- [ ] **Step 5: 运行模型测试及既有模型回归并提交**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_model_views.py apps/cmdb/tests/bdd/test_model_management_bdd.py -q --no-cov`

Expected: PASS。

```bash
git add server/apps/cmdb/open_api/services.py server/apps/cmdb/open_api/views.py server/apps/cmdb/urls.py server/apps/cmdb/tests/test_open_api_model_views.py
git commit -m "功能：开放 CMDB 模型只读接口"
```

### Task 3: 实例查询与单条 CRUD

**Files:**
- Modify: `server/apps/cmdb/open_api/services.py`
- Modify: `server/apps/cmdb/open_api/views.py`
- Modify: `server/apps/cmdb/urls.py`
- Test: `server/apps/cmdb/tests/test_open_api_instance_views.py`

**Interfaces:**
- Consumes: Task 1 的查询/动态载荷校验，Task 2 的模型授权。
- Produces: `list_instances/get_instance/create_instance/update_instance/delete_instance`，以及实例集合和详情 REST 路由。

- [ ] **Step 1: 写固定团队、过滤和单条 CRUD 失败测试**

```python
# server/apps/cmdb/tests/test_open_api_instance_views.py
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.django_db


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_create_forces_bound_team(mock_model, mock_attrs, mock_create, mock_context, api_client):
    mock_context.return_value.team_id = 7
    mock_context.return_value.user.username = "api-user"
    mock_model.return_value = {"model_id": "host", "group": [7]}
    mock_attrs.return_value = [{"attr_id": "inst_name", "editable": True}]
    mock_create.return_value = {"_id": 11, "model_id": "host", "inst_name": "h1", "organization": [7]}
    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances",
        {"inst_name": "h1", "organization": [999]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 400
    assert mock_create.call_count == 0


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_cross_team_instance_is_hidden_as_404(mock_query, mock_context, api_client):
    mock_context.return_value.team_id = 7
    mock_query.return_value = {"_id": 12, "model_id": "host", "inst_name": "other", "organization": [8]}
    response = api_client.get(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_update")
def test_update_rejects_organization_before_domain_write(mock_update, mock_context, api_client):
    response = api_client.patch(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        {"organization": [8]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 400
    mock_update.assert_not_called()
```

- [ ] **Step 2: 运行实例测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_instance_views.py -q --no-cov`

Expected: FAIL，实例路由不存在。

- [ ] **Step 3: 实现实例格式化、对象权限和单条领域编排**

在 `services.py` 增加：

```python
from apps.cmdb.constants.constants import OPERATE, PERMISSION_INSTANCES, VIEW
from apps.cmdb.services.instance import InstanceManage


def _organization_ids(instance):
    result = set()
    for item in instance.get("organization", []) or []:
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            continue
    return result


def serialize_instance(instance):
    aliases = {"_id": "inst_id", "_creator": "creator", "_created_at": "created_at", "_updated_at": "updated_at"}
    hidden = {"_labels", "permission"}
    return {aliases.get(key, key): value for key, value in instance.items() if key not in hidden}


class CMDBOpenAPIService:
    # 保留 Task 2 方法
    def _instance_permission_map(self, model_id):
        return self.context.permission_map(model_id, PERMISSION_INSTANCES)

    def _get_instance(self, model_id, inst_id, operator):
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance or instance.get("model_id") != model_id or self.context.team_id not in _organization_ids(instance):
            raise CMDBOpenAPIError("cmdb.instance.not_found", "实例不存在", 404)
        creator_allowed = instance.get("_creator") == self.context.user.username
        if not creator_allowed and not CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=operator,
            model_id=model_id,
            permission_instances_map=self._instance_permission_map(model_id),
            instance=instance,
        ):
            raise CMDBOpenAPIError("cmdb.permission.denied", "权限不足", 403)
        return instance

    def list_instances(self, model_id, query):
        self.context.require_feature("asset_info-View")
        attrs = self.get_model_attrs(model_id)
        serializer = InstanceListQuerySerializer(data=query, context={"attrs": attrs})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        instances, count = InstanceManage.instance_list(
            model_id=model_id,
            params=list(data["filters"]),
            page=data["page"],
            page_size=data["page_size"],
            order=data["order"],
            permission_map=self._instance_permission_map(model_id),
            creator=self.context.user.username,
        )
        return {"count": count, "page": data["page"], "page_size": data["page_size"], "items": [serialize_instance(i) for i in instances]}

    def create_instance(self, model_id, payload):
        self.context.require_feature("asset_info-Add")
        attrs = self.get_model_attrs(model_id)
        data = validate_instance_payload(payload, attrs, team_id=self.context.team_id, for_update=False)
        result = InstanceManage.instance_create(model_id, data, self.context.user.username, allowed_org_ids=[self.context.team_id])
        return serialize_instance(result)

    def update_instance(self, model_id, inst_id, payload):
        self.context.require_feature("asset_info-Edit")
        self._get_instance(model_id, inst_id, OPERATE)
        data = validate_instance_payload(payload, self.get_model_attrs(model_id), team_id=self.context.team_id, for_update=True)
        result = InstanceManage.instance_update(
            self.context.user_groups,
            self.context.user.roles,
            int(inst_id),
            data,
            self.context.user.username,
            allowed_org_ids=[self.context.team_id],
        )
        return serialize_instance(result)

    def delete_instance(self, model_id, inst_id):
        self.context.require_feature("asset_info-Delete")
        self._get_instance(model_id, inst_id, OPERATE)
        InstanceManage.instance_batch_delete(self.context.user_groups, self.context.user.roles, [int(inst_id)], self.context.user.username)
        return {"deleted": [int(inst_id)]}
```

- [ ] **Step 4: 添加实例 Views 和路由**

```python
class OpenInstanceCollectionView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).list_instances(model_id, request.query_params))

    def post(self, request, model_id):
        return open_api_success(self.service(request).create_instance(model_id, request.data), status_code=201)


class OpenInstanceDetailView(CMDBOpenAPIView):
    def get(self, request, model_id, inst_id):
        service = self.service(request)
        service.context.require_feature("asset_info-View")
        return open_api_success(serialize_instance(service._get_instance(model_id, inst_id, VIEW)))

    def patch(self, request, model_id, inst_id):
        return open_api_success(self.service(request).update_instance(model_id, inst_id, request.data))

    def delete(self, request, model_id, inst_id):
        return open_api_success(self.service(request).delete_instance(model_id, inst_id))
```

路由：

```python
path("api/open/models/<str:model_id>/instances", open_views.OpenInstanceCollectionView.as_view()),
path("api/open/models/<str:model_id>/instances/<int:inst_id>", open_views.OpenInstanceDetailView.as_view()),
```

- [ ] **Step 5: 运行实例测试与现有 CRUD 回归并提交**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_instance_views.py apps/cmdb/tests/bdd/test_instance_crud_bdd.py -q --no-cov`

Expected: PASS。

```bash
git add server/apps/cmdb/open_api server/apps/cmdb/urls.py server/apps/cmdb/tests/test_open_api_instance_views.py
git commit -m "功能：开放 CMDB 实例单条接口"
```

### Task 4: 批量创建领域能力和批量 OpenAPI

**Files:**
- Modify: `server/apps/cmdb/services/instance.py`
- Modify: `server/apps/cmdb/open_api/services.py`
- Modify: `server/apps/cmdb/open_api/views.py`
- Modify: `server/apps/cmdb/urls.py`
- Test: `server/apps/cmdb/tests/test_open_api_batch_service.py`
- Test: `server/apps/cmdb/tests/test_open_api_batch_views.py`

**Interfaces:**
- Consumes: `InstanceManage.instance_create/update/batch_instance_update/instance_batch_delete` 的既有语义。
- Produces: `InstanceManage.instance_batch_create(model_id, instances, operator, allowed_org_ids)` 和三个 batch REST 入口。

- [ ] **Step 1: 写批量创建领域失败测试**

```python
# server/apps/cmdb/tests/test_open_api_batch_service.py
from unittest.mock import patch

import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException


pytestmark = pytest.mark.unit


@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
def test_batch_create_rolls_back_graph_when_one_item_fails(mock_attrs, mock_graph):
    mock_attrs.return_value = [{"attr_id": "inst_name", "attr_name": "名称", "is_required": True, "is_only": True}]
    graph = mock_graph.return_value.__enter__.return_value
    graph.query_entity.return_value = ([], 0)
    graph.batch_create_entity.return_value = [
        {"success": True, "data": {"_id": 1, "model_id": "host", "inst_name": "h1"}},
        {"success": False, "data": {"inst_name": "h1"}, "message": "名称 exist"},
    ]
    with pytest.raises(BaseAppException):
        InstanceManage.instance_batch_create("host", [{"inst_name": "h1"}, {"inst_name": "h1"}], "api-user", [7])
    graph.batch_delete_entity.assert_called_once_with("instance", [1])


@patch("apps.cmdb.services.instance.schedule_instance_auto_relation_reconcile")
@patch("apps.cmdb.services.instance.batch_create_change_record")
@patch("apps.cmdb.services.instance.GraphClient")
@patch("apps.cmdb.services.instance.ModelManage.search_model_attr")
def test_batch_create_writes_one_audit_batch_after_all_graph_rows_succeed(mock_attrs, mock_graph, mock_audit, mock_schedule):
    mock_attrs.return_value = []
    graph = mock_graph.return_value.__enter__.return_value
    graph.query_entity.return_value = ([], 0)
    graph.batch_create_entity.return_value = [
        {"success": True, "data": {"_id": 1, "model_id": "host", "inst_name": "h1"}},
        {"success": True, "data": {"_id": 2, "model_id": "host", "inst_name": "h2"}},
    ]
    result = InstanceManage.instance_batch_create("host", [{"inst_name": "h1"}, {"inst_name": "h2"}], "api-user", [7])
    assert [item["_id"] for item in result] == [1, 2]
    mock_audit.assert_called_once()
    mock_schedule.assert_called_once_with([1, 2])
```

- [ ] **Step 2: 运行领域测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_batch_service.py -q --no-cov`

Expected: FAIL，提示 `InstanceManage.instance_batch_create` 不存在。

- [ ] **Step 3: 实现批量创建领域方法**

在 `InstanceManage` 中增加方法，复用单条创建的 tag/enum/organization/字段/唯一性校验，并把审计和自动关联放到全部图写成功之后：

```python
@staticmethod
def instance_batch_create(model_id, instances, operator, allowed_org_ids=None):
    attrs = ModelManage.search_model_attr(model_id)
    check_attr_map = InstanceManage._build_unique_rule_check_attr_map(model_id, attrs, for_update=False)
    prepared = []
    for item in instances:
        data = {**item, "model_id": model_id}
        data = apply_tag_validation_for_instance(data, attrs, model_id)
        data = apply_enum_validation_for_instance(data, attrs)
        validate_instance_organization_scope(data, allowed_org_ids=allowed_org_ids)
        data = get_instance_enterprise_extension().normalize_file_fields(model_id, data, attrs, operator=operator)
        data = DisplayFieldHandler.build_display_fields(model_id, data, attrs)
        prepared.append(data)

    with GraphClient() as ag:
        exist_items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
        results = ag.batch_create_entity(INSTANCE, prepared, check_attr_map, exist_items, operator, attrs)
        failed = next((item for item in results if not item.get("success")), None)
        created = [item["data"] for item in results if item.get("success")]
        if failed:
            if created:
                ag.batch_delete_entity(INSTANCE, [item["_id"] for item in created])
            raise BaseAppException(failed.get("message") or "批量创建失败")

    extension = get_instance_enterprise_extension()
    for item in created:
        extension.commit_instance_files(model_id, item["_id"], item, attrs, operator=operator)
    changes = [
        {
            "inst_id": item["_id"],
            "model_id": model_id,
            "after_data": item,
            "model_object": OPERATOR_INSTANCE,
            "message": f"创建模型实例. 模型:{model_id} 实例:{item.get('inst_name') or item.get('ip_addr', '')}",
        }
        for item in created
    ]
    batch_create_change_record(INSTANCE, CREATE_INST, changes, operator=operator)
    schedule_instance_auto_relation_reconcile([item["_id"] for item in created])
    return created
```

实现时将 `DisplayFieldHandler` 和 `schedule_instance_auto_relation_reconcile` 提升到模块可 patch 的导入位置，单实例签名和行为不变；为 `subnet` 批量创建逐条执行 `validate_subnet_no_overlap`。

- [ ] **Step 4: 写批量 HTTP 失败测试**

```python
# server/apps/cmdb/tests/test_open_api_batch_views.py
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.django_db


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create")
def test_batch_create_caps_items_and_forces_team(mock_create, mock_context, api_client):
    mock_context.return_value.team_id = 7
    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": f"h{i}"} for i in range(101)]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 400
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update")
def test_batch_update_rejects_cross_team_member_before_write(mock_update, mock_context, api_client):
    service = mock_context.return_value
    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_ids": [1, 2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code in {403, 404}
    mock_update.assert_not_called()
```

- [ ] **Step 5: 实现批量 service、views 和优先路由**

`services.py` 增加三个方法：批量创建逐条调用 `validate_instance_payload` 后调用新领域方法；批量更新/删除先用 `_get_instance(..., OPERATE)` 校验每个 ID 和模型，再调用既有批量方法。批量错误捕获时把 `index` 或 `inst_id` 放入 `CMDBOpenAPIError.data`。

```python
def batch_create_instances(self, model_id, payload):
    self.context.require_feature("asset_info-Add")
    serializer = BatchCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    attrs = self.get_model_attrs(model_id)
    items = [
        validate_instance_payload(item, attrs, team_id=self.context.team_id, for_update=False)
        for item in serializer.validated_data["items"]
    ]
    created = InstanceManage.instance_batch_create(model_id, items, self.context.user.username, [self.context.team_id])
    return {"created": [serialize_instance(item) for item in created]}

def batch_update_instances(self, model_id, payload):
    self.context.require_feature("asset_info-Edit")
    serializer = BatchUpdateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    ids = serializer.validated_data["inst_ids"]
    for inst_id in ids:
        self._get_instance(model_id, inst_id, OPERATE)
    update_data = validate_instance_payload(
        serializer.validated_data["update_data"], self.get_model_attrs(model_id), team_id=self.context.team_id, for_update=True
    )
    result = InstanceManage.batch_instance_update(
        self.context.user_groups, self.context.user.roles, ids, update_data, self.context.user.username, [self.context.team_id]
    )
    return {"updated": [serialize_instance(item) for item in result]}

def batch_delete_instances(self, model_id, payload):
    self.context.require_feature("asset_info-Delete")
    serializer = BatchDeleteSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    ids = serializer.validated_data["inst_ids"]
    for inst_id in ids:
        self._get_instance(model_id, inst_id, OPERATE)
    InstanceManage.instance_batch_delete(self.context.user_groups, self.context.user.roles, ids, self.context.user.username)
    return {"deleted": ids}
```

batch 路由必须排在 `<int:inst_id>` 之前：

```python
path("api/open/models/<str:model_id>/instances/batch_create", open_views.OpenBatchCreateView.as_view()),
path("api/open/models/<str:model_id>/instances/batch_update", open_views.OpenBatchUpdateView.as_view()),
path("api/open/models/<str:model_id>/instances/batch_delete", open_views.OpenBatchDeleteView.as_view()),
```

- [ ] **Step 6: 运行批量测试和现有服务回归并提交**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_batch_service.py apps/cmdb/tests/test_open_api_batch_views.py apps/cmdb/tests/test_instance_service_crud.py apps/cmdb/tests/test_instance_service_graph_mock.py -q --no-cov`

Expected: PASS。

```bash
git add server/apps/cmdb/services/instance.py server/apps/cmdb/open_api server/apps/cmdb/urls.py server/apps/cmdb/tests/test_open_api_batch_service.py server/apps/cmdb/tests/test_open_api_batch_views.py
git commit -m "功能：开放 CMDB 实例批量接口"
```

### Task 5: 实例关联查询、创建和删除

**Files:**
- Modify: `server/apps/cmdb/open_api/services.py`
- Modify: `server/apps/cmdb/open_api/views.py`
- Modify: `server/apps/cmdb/urls.py`
- Test: `server/apps/cmdb/tests/test_open_api_association_views.py`

**Interfaces:**
- Consumes: `_get_instance(model_id, inst_id, operator)` 和 `InstanceManage.instance_association_*`。
- Produces: 关联列表、创建和删除三个 REST 行为，创建/删除均执行源目标双端授权。

- [ ] **Step 1: 写关联双端权限失败测试**

```python
# server/apps/cmdb/tests/test_open_api_association_views.py
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.django_db


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_create_association_rejects_cross_team_target(mock_query, mock_create, mock_context, api_client):
    mock_context.return_value.team_id = 7
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "model_id": "app", "inst_name": "a1", "organization": [8], "_creator": "other"},
    ]
    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_id": 2},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 404
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_by_asso_id")
def test_delete_association_requires_url_source_match(mock_association, mock_delete, mock_context, api_client):
    mock_association.return_value = {
        "_id": 10,
        "src": {"_id": 99, "model_id": "host", "organization": [7]},
        "dst": {"_id": 2, "model_id": "app", "organization": [7]},
    }
    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations/10",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 404
    mock_delete.assert_not_called()
```

- [ ] **Step 2: 运行关联测试确认 RED**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_association_views.py -q --no-cov`

Expected: FAIL，关联路由不存在。

- [ ] **Step 3: 实现关联 service 和 views**

```python
def list_instance_associations(self, model_id, inst_id):
    self.context.require_feature("asset_info-View")
    self._get_instance(model_id, inst_id, VIEW)
    return InstanceManage.instance_association_instance_list(model_id, int(inst_id))

def create_instance_association(self, model_id, inst_id, payload):
    self.context.require_feature("asset_info-Add Associate")
    serializer = AssociationCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    self._get_instance(model_id, inst_id, OPERATE)
    self._get_instance(data["target_model_id"], data["target_inst_id"], OPERATE)
    edge = InstanceManage.instance_association_create(
        {"src_inst_id": int(inst_id), "dst_inst_id": data["target_inst_id"], "model_asst_id": data["model_asst_id"]},
        self.context.user.username,
    )
    return {"association_id": edge["_id"], "model_asst_id": data["model_asst_id"]}

def delete_instance_association(self, model_id, inst_id, association_id):
    self.context.require_feature("asset_info-Delete Associate")
    association = InstanceManage.instance_association_by_asso_id(int(association_id))
    if not association or int((association.get("src") or {}).get("_id", 0)) != int(inst_id):
        raise CMDBOpenAPIError("cmdb.association.not_found", "关联关系不存在", 404)
    src = association.get("src") or {}
    dst = association.get("dst") or {}
    self._get_instance(model_id, src.get("_id"), OPERATE)
    self._get_instance(dst.get("model_id", ""), dst.get("_id"), OPERATE)
    InstanceManage.instance_association_delete(int(association_id), self.context.user.username)
    return {"deleted": int(association_id)}
```

views 只调用以上方法，路由为：

```python
path("api/open/models/<str:model_id>/instances/<int:inst_id>/associations", open_views.OpenInstanceAssociationsView.as_view()),
path(
    "api/open/models/<str:model_id>/instances/<int:inst_id>/associations/<int:association_id>",
    open_views.OpenInstanceAssociationDetailView.as_view(),
),
```

- [ ] **Step 4: 运行关联测试与既有关联回归并提交**

Run: `cd server && uv run pytest apps/cmdb/tests/test_open_api_association_views.py apps/cmdb/tests/test_model_assoc_nats.py -q --no-cov`

Expected: PASS。

```bash
git add server/apps/cmdb/open_api server/apps/cmdb/urls.py server/apps/cmdb/tests/test_open_api_association_views.py
git commit -m "功能：开放 CMDB 实例关联接口"
```

### Task 6: 文档、OpenAPI Schema、安全回归与最终门禁

**Files:**
- Create: `server/apps/cmdb/docs/open_api.md`
- Create: `server/apps/cmdb/docs/openapi.yaml`
- Modify: `server/apps/cmdb/tests/test_open_api_model_views.py`
- Modify: `server/apps/cmdb/tests/test_open_api_instance_views.py`
- Modify: `server/apps/cmdb/tests/test_open_api_batch_views.py`
- Modify: `server/apps/cmdb/tests/test_open_api_association_views.py`

**Interfaces:**
- Consumes: Tasks 1–5 的最终路由和错误码。
- Produces: 可交付文档、可导入 OpenAPI 3.0 schema、完整安全矩阵和验证证据。

- [ ] **Step 1: 补齐真实中间件认证与 RBAC 回归测试**

新增以下行为测试，测试名与断言保持明确：

```python
from django.test import RequestFactory

from apps.core.middlewares.api_middleware import APISecretMiddleware
from apps.core.middlewares.auth_middleware import AuthMiddleware


def test_missing_api_secret_returns_401():
    request = RequestFactory().get("/api/v1/cmdb/api/open/models")
    APISecretMiddleware(get_response=lambda req: None).process_request(request)
    response = AuthMiddleware(get_response=lambda req: None).process_view(
        request,
        lambda req: None,
        (),
        {},
    )
    assert response.status_code == 401


def test_session_auth_cannot_replace_api_secret(api_client):
    response = api_client.get("/api/v1/cmdb/api/open/models")
    assert response.status_code in {401, 403}


def test_client_team_and_include_children_never_expand_scope(api_client):
    response = api_client.get(
        "/api/v1/cmdb/api/open/models/host/instances",
        {"team": 999, "include_children": 1},
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 200
    assert all(7 in item["organization"] for item in response.json()["data"]["items"])


def test_revoked_write_permission_blocks_same_secret(api_client, api_secret_user):
    api_secret_user.permission = {"cmdb": {"asset_info-View"}}
    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances",
        {"inst_name": "blocked"},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )
    assert response.status_code == 403
```

测试 fixture 必须创建真实哈希 `UserAPISecret` 并使用 `APIClient` 请求；只在 service 已由单元测试覆盖的图库位置使用 patch，不允许 `force_authenticate` 绕过 API Secret 认证断言。

- [ ] **Step 2: 编写外部调用文档**

`server/apps/cmdb/docs/open_api.md` 必须逐项包含：

- Base URL 与 `Api-Authorization`。
- API Secret 绑定团队和 RBAC 双重约束。
- 全部路由、请求和响应示例。
- `filters` 支持的操作符表。
- 分页 200、批量 100 上限。
- 错误码和 HTTP 状态表。
- 写请求无幂等存储时的安全重试方法。
- 不记录或打印密钥的安全提醒。

至少提供以下可直接替换变量的示例：

```bash
curl -sS \
  -H "Api-Authorization: ${BK_LITE_API_SECRET}" \
  "${BK_LITE_URL}/api/v1/cmdb/api/open/models/host/instances?page=1&page_size=20&filters=%5B%7B%22field%22%3A%22ip_addr%22%2C%22type%22%3A%22str%2A%22%2C%22value%22%3A%2210.%22%7D%5D"
```

- [ ] **Step 3: 编写并校验 OpenAPI 3.0 YAML**

`server/apps/cmdb/docs/openapi.yaml` 以以下骨架覆盖全部路径，不使用未定义 `$ref`：

```yaml
openapi: 3.0.3
info:
  title: BK-Lite CMDB OpenAPI
  version: 1.0.0
servers:
  - url: /api/v1/cmdb/api/open
components:
  securitySchemes:
    ApiSecret:
      type: apiKey
      in: header
      name: Api-Authorization
  schemas:
    Error:
      type: object
      required: [result, data, message, code]
security:
  - ApiSecret: []
paths: {}
```

用 Python 解析 YAML，确认全部实际路由均存在：

Run: `cd server && uv run python -c "import yaml; p=yaml.safe_load(open('apps/cmdb/docs/openapi.yaml')); assert p['openapi']=='3.0.3'; assert len(p['paths'])==12"`

Expected: exit 0。

- [ ] **Step 4: 运行目标测试与覆盖率**

Run:

```bash
cd server && uv run pytest \
  apps/cmdb/tests/test_open_api_auth_pure.py \
  apps/cmdb/tests/test_open_api_serializers_pure.py \
  apps/cmdb/tests/test_open_api_model_views.py \
  apps/cmdb/tests/test_open_api_instance_views.py \
  apps/cmdb/tests/test_open_api_batch_service.py \
  apps/cmdb/tests/test_open_api_batch_views.py \
  apps/cmdb/tests/test_open_api_association_views.py \
  --cov=apps.cmdb.open_api --cov-report=term-missing --cov-fail-under=75 \
  -o addopts=''
```

Expected: 全部 PASS，`apps.cmdb.open_api` 覆盖率不低于 75%。

- [ ] **Step 5: 运行 CMDB 回归和格式门禁**

Run:

```bash
cd server && uv run pytest \
  apps/cmdb/tests/bdd/test_model_management_bdd.py \
  apps/cmdb/tests/bdd/test_instance_crud_bdd.py \
  apps/cmdb/tests/test_instance_service_crud.py \
  apps/cmdb/tests/test_instance_service_graph_mock.py \
  apps/cmdb/tests/test_model_assoc_nats.py \
  --no-cov
uv run black --check apps/cmdb/open_api apps/cmdb/services/instance.py apps/cmdb/tests/test_open_api_*.py
uv run isort --check-only apps/cmdb/open_api apps/cmdb/services/instance.py apps/cmdb/tests/test_open_api_*.py
uv run flake8 apps/cmdb/open_api apps/cmdb/services/instance.py apps/cmdb/tests/test_open_api_*.py
```

Expected: 全部 exit 0。

- [ ] **Step 6: 运行完整 Server 门禁**

Run: `cd server && make test`

Expected: exit 0。若被已记录的任务外 collection error 阻断，必须保存完整失败摘要，确认目标 OpenAPI 测试与 CMDB 回归仍为 PASS，不得把任务外失败描述成此次改动通过全量门禁。

- [ ] **Step 7: 提交文档与最终测试**

```bash
git add server/apps/cmdb/docs/open_api.md server/apps/cmdb/docs/openapi.yaml server/apps/cmdb/tests/test_open_api_*.py
git commit -m "文档：补充 CMDB OpenAPI 契约与验收"
```

## Completion Audit

实现完成后逐条核对设计文档 `docs/superpowers/specs/2026-07-20-cmdb-open-api-design.md`：

- 五个模型只读接口有路由、权限测试和 schema。
- 实例列表、单条 CRUD、三个批量接口有路由、服务、测试和 schema。
- 三个关联行为具备源目标双端授权测试。
- 所有查询只使用 API Secret 绑定团队，`include_children` 不生效。
- 创建强制团队，更新拒绝组织字段，跨团队详情返回 404。
- API Secret 所属用户 RBAC 撤销能够阻断同一密钥。
- 响应包含稳定 `result/data/message/code`，内部异常不泄露。
- 分页和批量上限生效。
- 审计、自动关联和企业附件后处理继续通过领域服务执行。
- 文档、YAML、目标覆盖率、CMDB 回归和完整 Server 门禁均有真实命令证据。

## specs: 2026-07-20-cmdb-open-api-design.md

日期：2026-07-20

## 1. 背景

BK-Lite 作业平台当前以两种方式开放能力：

- 作业执行、状态查询等通过 `@nats_client.register` 注册为 NATS Request-Reply 接口，默认信任内网 NATS，不承载外部用户身份鉴权。
- 文件上传、删除通过 `/api/v1/job_mgmt/api/open/` 下的 REST 接口开放，使用 `Api-Authorization` 和 `UserAPISecret` 鉴权，并以密钥绑定团队约束文件归属。

CMDB 已存在查询、实例写入和关联操作等 NATS 注册函数，但这些函数按可信机器调用设计，部分写路径会跳过用户权限检查，且允许调用方提供组织范围。它们不能直接作为面向外部系统的安全边界。

本设计为 CMDB 增加独立 REST OpenAPI 门面，复用现有认证、RBAC、领域服务、变更记录及自动关联能力，但不直接暴露控制台 ViewSet，也不包装 CMDB NATS 处理器。

## 2. 目标

首期提供以下外部能力：

- 模型相关只读：分类、模型、模型详情、模型字段、模型关联定义。
- 实例单条与批量 CRUD。
- 实例关联查询、创建和删除。
- 动态模型字段过滤、分页和排序。
- 通过 API Secret 绑定团队与所属用户当前 RBAC 实施双重授权。
- 保持现有 CMDB REST、NATS 和控制台行为不变。

## 3. 非目标

首期不包含：

- 分类、模型、字段、模型关联定义的创建、修改和删除。
- 采集任务、配置文件、导入导出和全文搜索。
- 绑定团队的子团队访问。
- API Secret 独立 scope。
- 对外开放 NATS。
- 写请求幂等键存储。
- 兼容旧入口或为现有内部接口增加别名。

## 4. 方案选择

### 4.1 采用方案：独立 CMDB OpenAPI 门面

新增专用 View、Serializer 和 Service：

- View 只负责 HTTP 方法、状态码及响应封装。
- Serializer 校验路径参数、动态过滤条件、实例字段和批量请求。
- Service 构建可信授权上下文，并委托现有 `ModelManage`、`InstanceManage` 等领域服务。

### 4.2 不采用的方案

不直接开放现有 CMDB ViewSet。现有接口包含 Cookie、`current_team`、`include_children` 及控制台响应约定，无法形成稳定的外部契约，也容易意外扩大开放面。

不直接包装 CMDB NATS 函数。NATS 写接口具有可信内网假设，部分路径会跳过用户权限检查或信任调用方传入的组织范围。

## 5. 架构与数据流

统一入口为：

```text
/api/v1/cmdb/api/open/
```

请求链路：

```text
外部系统
  -> Api-Authorization
  -> APISecretMiddleware
  -> 密钥所属用户与唯一绑定团队
  -> CMDB OpenAPI Serializer
  -> CMDB OpenAPI Service
  -> 当前用户 RBAC + 绑定团队过滤
  -> CMDB 领域服务
  -> FalkorDB / Django ORM / 变更记录 / 自动关联后处理
```

授权上下文完全由服务端生成。请求中的 `team`、`organization`、`allowed_org_ids` 或 `include_children` 均不能扩大访问范围。

## 6. 路由设计

### 6.1 模型只读接口

```text
GET /api/v1/cmdb/api/open/classifications
GET /api/v1/cmdb/api/open/models
GET /api/v1/cmdb/api/open/models/{model_id}
GET /api/v1/cmdb/api/open/models/{model_id}/attributes
GET /api/v1/cmdb/api/open/models/{model_id}/associations
```

分类与模型列表只返回密钥所属用户在绑定团队下可查看的对象。模型详情、字段和关联定义请求必须先通过模型查看权限校验。

### 6.2 实例接口

```text
GET    /api/v1/cmdb/api/open/models/{model_id}/instances
POST   /api/v1/cmdb/api/open/models/{model_id}/instances
GET    /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}
PATCH  /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}
DELETE /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}

POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_create
POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_update
POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_delete
```

实例详情、更新和删除统一通过 `model_id + inst_id` 定位。服务端必须确认实例的真实 `model_id` 与路径一致。

### 6.3 实例关联接口

```text
GET    /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations
POST   /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations
DELETE /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations/{association_id}
```

创建和删除关联时必须同时验证源实例与目标实例的团队范围和对象级权限，并验证模型关联定义及方向。

## 7. 认证与授权

### 7.1 认证

认证请求头与 Job 保持一致：

```http
Api-Authorization: <api_secret>
```

复用现有 `UserAPISecret`、`APISecretMiddleware` 和认证后端，不新增密钥表或认证协议。

### 7.2 团队范围

- 每个 API Secret 只允许访问其唯一绑定团队。
- 不包含绑定团队的子团队。
- 客户端不能选择或切换团队。
- 查询时只返回 `organization` 包含绑定团队的实例。
- 创建实例时服务端强制写入 `organization: [绑定团队]`。
- 更新实例时禁止修改 `organization`，不允许通过 OpenAPI 迁移实例组织。

### 7.3 RBAC

API Secret 同时继承所属用户当前的 CMDB RBAC：

- 模型接口检查模型查看权限。
- 实例列表和详情应用团队过滤及实例级查看规则。
- 创建、更新和删除分别检查现有 CMDB 新增、编辑和删除权限。
- 关联写操作同时检查源、目标实例及相应关联权限。
- 用户停用、角色撤销或权限变更后，后续密钥请求立即使用新的权限结果，不保留密钥创建时的权限快照。

团队范围与 RBAC 必须同时满足，任一条件失败均不得访问资源。

## 8. 请求契约

### 8.1 实例列表

实例列表支持分页、排序和动态字段过滤：

```text
page=1
page_size=20
order=-updated_at
filters=[{"field":"ip_addr","type":"str*","value":"10.0."}]
```

`filters` 使用 CMDB 现有 `{field, type, value}` 结构。OpenAPI Serializer 必须完成以下校验后才能调用领域服务：

- `field` 属于路径指定模型的可查询字段。
- `type` 属于 OpenAPI 明确允许的过滤操作符。
- `value` 与字段类型、操作符匹配。
- 不允许通过过滤条件读取内部系统字段。

默认 `page=1`、`page_size=20`，单页最大 `page_size=200`。

### 8.2 单实例创建

请求体直接提交可编辑实例属性：

```json
{
  "inst_name": "host-01",
  "ip_addr": "10.0.0.1"
}
```

服务端忽略客户端组织上下文并写入：

```json
{"organization": [1]}
```

其中 `1` 为 API Secret 的绑定团队。

### 8.3 单实例更新

更新采用 `PATCH`，只修改请求中出现的可编辑字段。以下字段禁止写入：

- `_id`
- `model_id`
- `organization`
- `_creator`
- 创建、更新时间等审计字段
- 模型定义为只读或计算生成的字段

### 8.4 批量请求

批量创建：

```json
{
  "items": [
    {"inst_name": "host-01", "ip_addr": "10.0.0.1"},
    {"inst_name": "host-02", "ip_addr": "10.0.0.2"}
  ]
}
```

批量更新沿用现有 CMDB 语义，所有实例应用同一份修改：

```json
{
  "inst_ids": [101, 102],
  "update_data": {"status": "active"}
}
```

批量删除：

```json
{"inst_ids": [101, 102]}
```

单次批量写入最多 100 个实例。批量操作先校验全部目标、权限、字段、组织范围和唯一性，再进入现有批量领域操作。接口只提供整体成功或整体错误，不提供逐条部分成功契约。

若任一项在执行前校验失败，响应必须指出失败项的索引或 `inst_id`，且不得开始批量写入。

### 8.5 实例关联

创建关联请求：

```json
{
  "model_asst_id": "host_run_app",
  "target_model_id": "app",
  "target_inst_id": 201
}
```

源模型和源实例来自 URL。服务端必须验证：

- 源、目标实例存在且模型匹配。
- 模型关联定义存在且方向匹配。
- 源、目标实例均属于绑定团队的可访问范围。
- 当前用户对源、目标实例均有相应操作权限。
- 不重复创建同一条关联。

删除关联时必须确认关联属于 URL 中的源实例，并对其目标实例执行同等权限校验。

## 9. 响应与错误契约

成功响应：

```json
{
  "result": true,
  "data": {},
  "message": "",
  "code": "ok"
}
```

分页响应：

```json
{
  "result": true,
  "data": {
    "count": 120,
    "page": 1,
    "page_size": 20,
    "items": []
  },
  "message": "",
  "code": "ok"
}
```

错误响应示例：

```json
{
  "result": false,
  "data": {
    "index": 2,
    "inst_id": 103,
    "field": "ip_addr"
  },
  "message": "字段值违反唯一性约束",
  "code": "cmdb.instance.unique_conflict"
}
```

HTTP 状态约定：

- `400`：参数、过滤条件或字段校验失败。
- `401`：缺少认证信息。
- `403`：密钥无效，或用户缺少对应操作权限。
- `404`：模型或实例不存在，或者资源不属于绑定团队。跨团队资源统一按不存在处理，避免枚举。
- `409`：唯一字段冲突、关联重复或批量请求内部冲突。
- `500`：脱敏后的内部错误。

应用错误码保持稳定，错误消息允许国际化。响应不得包含异常堆栈、数据库信息、图查询语句或密钥内容。

## 10. 审计与可观测性

- 实例与关联写操作继续调用现有领域服务，复用现有 CMDB 变更记录。
- 操作人记录 API Secret 所属用户名。
- 结构化请求日志记录方法、路径、用户名、绑定团队、批量数量、状态码和耗时。
- 日志不得记录 `Api-Authorization`、完整请求体或完整实例返回数据。
- 批量错误日志只记录错误码、失败索引或 `inst_id`，不输出可能包含凭据的动态属性值。

## 11. 一致性与重试

首期不新增写请求幂等键存储。创建请求在服务端已成功、但调用方未收到响应时，重试可能因唯一约束返回 `409`。调用方应根据模型唯一字段查询确认结果后再决定是否重试。

批量接口遵循现有 CMDB 的整体请求语义，不承诺 FalkorDB、Django 数据库及异步后处理之间的分布式事务。实现必须复用现有领域服务的执行顺序、审计与后处理策略，不在 OpenAPI 门面自行拼接跨存储写操作。

## 12. 测试策略

### 12.1 Serializer 单元测试

- 模型字段与过滤操作符校验。
- 动态字段类型和值校验。
- 系统字段和组织字段写入拒绝。
- 分页及批量数量上限。
- 批量错误位置返回。

### 12.2 权限矩阵测试

- 缺少和无效 API Secret。
- API Secret 固定绑定团队，不接受调用方团队参数。
- 用户 RBAC 变更后权限立即生效。
- 跨团队实例按 `404` 处理。
- 只读用户不能写实例。
- 源或目标任一实例无权限时关联写入失败。

### 12.3 API 行为测试

- 分类、模型、字段和模型关联只读查询。
- 实例单条创建、查询、更新和删除。
- 动态过滤、分页和排序。
- 批量创建、统一更新和删除。
- 批量校验失败不开始写入。
- 关联查询、创建、重复冲突和删除。
- 唯一约束、模型不匹配及非法关联方向。

### 12.4 回归与质量门禁

- 现有 CMDB REST ViewSet 行为不变。
- 现有 CMDB NATS 注册函数行为不变。
- 目标改动覆盖率不低于 75%。
- 执行后端相关最小测试，并在最终验收前运行 `cd server && make test`；若全量门禁被既有仓库问题阻断，必须记录具体阻断和目标测试结果。
- 数据访问继续使用现有 ORM 和图服务，禁止新增原生 SQL。

## 13. 文档与验收

实现同步提供：

- `server/apps/cmdb/docs/open_api.md`，包含认证、路由、过滤操作符、错误码和完整示例。
- 可导入的 OpenAPI/Swagger 描述，复用项目现有文档生成能力。
- API Secret 创建及用户权限配置说明。
- `curl` 示例和最小联调清单。

真实验收使用一个绑定测试团队的 API Secret 完成：

1. 查询可见分类、模型、字段和模型关联。
2. 创建、查询、更新和删除单个实例。
3. 执行批量创建、更新和删除。
4. 创建、查询和删除实例关联。
5. 验证跨团队实例不可枚举或操作。
6. 撤销所属用户写权限后，确认同一密钥不能继续写入。

## 14. 发布与回滚

该设计复用现有 `UserAPISecret`，不需要数据库迁移。新增路由和门面代码独立于现有 CMDB REST/NATS 契约。

回滚时移除 OpenAPI 路由注册和门面代码即可停止新入口；通过 OpenAPI 创建的实例属于正常 CMDB 数据，不随代码回滚删除。发布前不得把 NATS 端口或内部 CMDB NATS subject 暴露到外部网络。
