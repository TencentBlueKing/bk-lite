"""CMDB 杂项视图覆盖测试：分类/展示字段/变更记录/用户个人配置 + 权限 Mixin。

对照 spec/prd/CMDB·模型管理与操作日志：分类增删改查、实例展示字段设置、
变更记录枚举与列表、用户个人配置 CRUD，以及 CmdbPermissionMixin 的对象级权限判定。
"""

import importlib
import hashlib
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.urls import router
from apps.cmdb.models.change_record import CUSTOM_REPORTING_CHANGE, ChangeRecord
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.views.classification import ClassificationViewSet
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.cmdb.views.show_field import ShowFieldViewSet
from apps.cmdb.views.user_personal_config import UserPersonalConfigViewSet
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.models import Group


class _EnterpriseUnavailable:
    def __init__(self, reason: str):
        self.reason = reason

    def __getattr__(self, _name):
        pytest.skip(self.reason)

    def __call__(self, *args, **kwargs):
        pytest.skip(self.reason)


try:
    from apps.cmdb.models.custom_reporting import (
        CustomReportingBatch,
        CustomReportingCleanupReview,
        CustomReportingCredential,
        CustomReportingPendingRelation,
        CustomReportingTask,
    )
    from apps.cmdb.services.custom_reporting_ingest_service import CustomReportingIngestService
    from apps.cmdb.services.custom_reporting_task_service import CustomReportingTaskService
    from apps.cmdb.views.custom_reporting import CustomReportingTaskViewSet
except (ImportError, ModuleNotFoundError) as exc:
    if getattr(exc, "name", None) not in {
        "apps.cmdb.enterprise",
        "apps.cmdb.enterprise.models",
        "apps.cmdb.enterprise.views",
        "apps.cmdb.enterprise.services",
        "apps.cmdb.enterprise.services.custom_reporting_ingest_service",
        "apps.cmdb.enterprise.services.custom_reporting_task_service",
    }:
        raise
    _enterprise_unavailable = _EnterpriseUnavailable("enterprise custom reporting unavailable")
    CustomReportingBatch = _enterprise_unavailable
    CustomReportingCleanupReview = _enterprise_unavailable
    CustomReportingCredential = _enterprise_unavailable
    CustomReportingPendingRelation = _enterprise_unavailable
    CustomReportingTask = _enterprise_unavailable
    CustomReportingIngestService = _enterprise_unavailable
    CustomReportingTaskService = _enterprise_unavailable
    CustomReportingTaskViewSet = _enterprise_unavailable


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.roles = ["admin"]
    u.locale = "zh-Hans"
    u.domain = "domain.com"
    return u


@pytest.fixture
def scoped_user(authenticated_user):
    u = authenticated_user
    u.is_superuser = False
    u.group_list = []
    u.group_tree = []
    u.roles = []
    u.permission = {
        "model_management-View",
        "model_management-Edit Model",
        "model_management-Delete Model",
    }
    u.locale = "zh-Hans"
    u.domain = "domain.com"
    return u


def _req(method, user=None, data=None, headers=None, **cookies):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request_kwargs = dict(headers or {})
    request = fn("/x/", **request_kwargs) if data is None else fn("/x/", data=data, format="json", **request_kwargs)
    for k, v in cookies.items():
        request.COOKIES[k] = v
    if user is not None:
        force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# ==========================================================================
# CmdbPermissionMixin（纯逻辑）
# ==========================================================================


def _mixin_request(group_list, username="admin", include_children="0", current_team="1", group_tree=None):
    user = SimpleNamespace(
        group_list=group_list, username=username, group_tree=group_tree or []
    )
    return SimpleNamespace(user=user, COOKIES={"include_children": include_children, "current_team": current_team})


def test_get_user_organizations_intersection():
    req = _mixin_request([{"id": 1}, {"id": 2}])
    out = CmdbPermissionMixin.get_user_organizations(req, {"organization": [2, 3]})
    assert out == [2]


def test_is_creator_with_org_access_true():
    req = _mixin_request([{"id": 1}], username="alice", current_team="1")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is True


def test_is_creator_with_org_access_wrong_team():
    req = _mixin_request([{"id": 9}], username="alice", current_team="9")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is False


def test_is_creator_with_org_access_not_creator():
    req = _mixin_request([{"id": 1}], username="bob", current_team="1")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is False


def test_check_instance_permission_no_org():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}], current_team="9")
    assert mixin.check_instance_permission(req, {"organization": [1], "model_id": "host"}) is False


def test_check_instance_permission_granted(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **k: {1: {"permission_instances_map": {}}},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: True
    )
    req = _mixin_request([{"id": 1}])
    assert mixin.check_instance_permission(req, {"organization": [1], "model_id": "host"}) is True


def test_check_model_permission_no_org():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}])
    assert mixin.check_model_permission(req, {"group": [1], "model_id": "host"}) is False


def test_require_instance_permission_creator_ok():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 1}], username="alice", current_team="1")
    instance = {"organization": [1], "_creator": "alice", "model_id": "host"}
    assert mixin.require_instance_permission(req, instance) is None


def test_require_instance_permission_no_org_denied():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}], username="bob", current_team="9")
    instance = {"organization": [1], "_creator": "alice", "model_id": "host"}
    resp = mixin.require_instance_permission(req, instance)
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


def test_require_model_permission_no_org_denied():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}])
    resp = mixin.require_model_permission(req, {"group": [1], "model_id": "host"})
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


def test_require_model_view_permission_default_group(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: True
    )
    req = _mixin_request([{"id": 9}])
    # default_group 模型即使无组织交集也可继续 VIEW 判定
    resp = mixin.require_model_view_permission(
        req, {"group": [1], "model_id": "host"}, default_group_id=1, permissions_map={1: {}}
    )
    assert resp is None


def test_require_model_view_permission_denied(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: False
    )
    req = _mixin_request([{"id": 1}])
    resp = mixin.require_model_view_permission(
        req, {"group": [1], "model_id": "host"}, default_group_id=1, permissions_map={1: {}}
    )
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


# ==========================================================================
# ClassificationViewSet
# ==========================================================================


@pytest.mark.django_db
def test_classification_create(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.create_model_classification",
        lambda data: {"classification_id": data.get("classification_id", "net")},
    )
    request = _req("post", superuser, data={"classification_id": "net", "classification_name": "网络"})
    response = ClassificationViewSet.as_view({"post": "create"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["classification_id"] == "net"


@pytest.mark.django_db
def test_classification_list(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
        lambda locale: [{"classification_id": "net"}],
    )
    request = _req("get", superuser)
    response = ClassificationViewSet.as_view({"get": "list"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"][0]["classification_id"] == "net"


@pytest.mark.django_db
def test_classification_destroy(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.check_classification_is_used", lambda pk: None
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification_info",
        lambda pk: {"_id": 12},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.delete_model_classification", lambda _id: None
    )
    request = _req("delete", superuser)
    response = ClassificationViewSet.as_view({"delete": "destroy"})(request, pk="net")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_classification_update(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification_info",
        lambda pk: {"_id": 12},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.update_model_classification",
        lambda _id, data: {"_id": _id, **data},
    )
    request = _req("put", superuser, data={"classification_name": "网络2"})
    response = ClassificationViewSet.as_view({"put": "update"})(request, pk="net")
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["classification_name"] == "网络2"


# ==========================================================================
# ShowFieldViewSet（真实 DB）
# ==========================================================================


@pytest.mark.django_db
def test_show_field_invalid_payload(superuser):
    request = _req("post", superuser, data={"show_fields": "notalist"})
    response = ShowFieldViewSet.as_view({"post": "create_or_update"})(request, model_id="host")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_show_field_create_then_get(superuser):
    request = _req("post", superuser, data={"show_fields": ["inst_name", "ip"]})
    response = ShowFieldViewSet.as_view({"post": "create_or_update"})(request, model_id="host")
    assert response.status_code == status.HTTP_200_OK

    get_req = _req("get", superuser)
    get_resp = ShowFieldViewSet.as_view({"get": "get_info"})(get_req, model_id="host")
    body = _body(get_resp)
    assert body["data"]["show_fields"] == ["inst_name", "ip"]


@pytest.mark.django_db
def test_show_field_get_none(superuser):
    request = _req("get", superuser)
    response = ShowFieldViewSet.as_view({"get": "get_info"})(request, model_id="absent")
    assert _body(response)["data"] is None


# ==========================================================================
# UserPersonalConfigViewSet（真实 DB）
# ==========================================================================


@pytest.mark.django_db
def test_user_config_create_bad_value(superuser):
    request = _req("post", superuser, data={"config_key": "k", "config_value": "notdict"})
    response = UserPersonalConfigViewSet.as_view({"post": "create"})(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_config_crud_flow(superuser):
    # create —— 视图自带 {"result","data"} 信封，外层 renderer 再包一层 data
    create_resp = UserPersonalConfigViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"config_key": "dashboard", "config_value": {"a": 1}})
    )
    assert create_resp.status_code == status.HTTP_200_OK
    cfg_id = _body(create_resp)["data"]["data"]["id"]

    # list
    list_resp = UserPersonalConfigViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert _body(list_resp)["data"]["result"] is True

    # retrieve
    ret_resp = UserPersonalConfigViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=cfg_id)
    assert _body(ret_resp)["data"]["data"]["config_key"] == "dashboard"

    # destroy
    del_resp = UserPersonalConfigViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=cfg_id)
    assert _body(del_resp)["data"]["result"] is True


@pytest.mark.django_db
def test_user_config_get_by_key_missing(superuser):
    response = UserPersonalConfigViewSet.as_view({"get": "get_by_key"})(
        _req("get", superuser), config_key="absent"
    )
    assert _body(response)["data"]["data"] == {}


@pytest.mark.django_db
def test_user_config_update_key(superuser):
    response = UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "layout", "config_value": {"x": 1}})
    )
    body = _body(response)
    assert body["result"] is True
    assert body["data"]["data"]["config_key"] == "layout"


@pytest.mark.django_db
def test_user_config_update_key_bad(superuser):
    response = UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "", "config_value": {"x": 1}})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_config_delete_key_and_list_keys(superuser):
    # 先建一个 key
    UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "to_del", "config_value": {"x": 1}})
    )
    # list_keys
    keys_resp = UserPersonalConfigViewSet.as_view({"get": "list_keys"})(_req("get", superuser))
    assert "to_del" in _body(keys_resp)["data"]["data"]
    # delete_key 返回裸 bool
    del_resp = UserPersonalConfigViewSet.as_view({"delete": "delete_key"})(
        _req("delete", superuser), config_key="to_del"
    )
    assert _body(del_resp)["data"] is True


@pytest.mark.django_db
def test_custom_reporting_task_list(superuser):
    current_group = Group.objects.create(name="默认组织")
    CustomReportingTask.objects.create(
        name="日报任务",
        team=[current_group.id],
        config={"metrics": ["count"]},
    )
    request = _req("get", superuser)
    request.COOKIES["current_team"] = str(current_group.id)
    response = CustomReportingTaskViewSet.as_view({"get": "list"})(request)
    body = _body(response)

    assert response.status_code == status.HTTP_200_OK
    assert body["result"] is True
    assert body["data"]["count"] == 1
    assert body["data"]["results"][0]["name"] == "日报任务"


@pytest.mark.django_db
def test_custom_reporting_task_create_rejects_cross_organization_team(superuser):
    current_group = Group.objects.create(name="默认组织")
    other_group = Group.objects.create(name="其他组织")
    request = _req(
        "post",
        superuser,
        data={"name": "日报任务", "team": [other_group.id], "config": {"metrics": ["count"]}},
    )
    request.COOKIES["current_team"] = str(current_group.id)

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(request)
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"


@pytest.mark.django_db
def test_custom_reporting_task_create_requires_current_team_before_scope_validation(
    superuser, monkeypatch
):
    target_group = Group.objects.create(name="默认组织")
    monkeypatch.setattr(
        CustomReportingTaskViewSet,
        "_validate_team_scope",
        lambda *args, **kwargs: pytest.fail("should not validate team scope"),
    )
    request = _req(
        "post",
        superuser,
        data={"name": "日报任务", "team": [target_group.id], "config": {"metrics": ["count"]}},
    )

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(request)
    body = _body(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert body["result"] is False
    assert body["message"] == "缺少 current_team 参数"


@pytest.mark.django_db
def test_custom_reporting_task_update_rejects_cross_organization_team(superuser):
    current_group = Group.objects.create(name="默认组织")
    other_group = Group.objects.create(name="其他组织")
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[current_group.id],
        config={"metrics": ["count"]},
    )
    request = _req(
        "put",
        superuser,
        data={"name": "日报任务", "team": [other_group.id], "config": {"metrics": ["count"]}},
    )
    request.COOKIES["current_team"] = str(current_group.id)

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(request, pk=task.pk)
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"


@pytest.mark.django_db
def test_custom_reporting_task_update_requires_current_team_before_scope_validation(
    superuser, monkeypatch
):
    target_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[target_group.id],
        config={"metrics": ["count"]},
    )
    monkeypatch.setattr(
        CustomReportingTaskViewSet,
        "_validate_team_scope",
        lambda *args, **kwargs: pytest.fail("should not validate team scope"),
    )
    request = _req(
        "put",
        superuser,
        data={"name": "日报任务", "team": [target_group.id], "config": {"metrics": ["count"]}},
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(request, pk=task.pk)
    body = _body(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert body["result"] is False
    assert body["message"] == "缺少 current_team 参数"


@pytest.mark.django_db
def test_custom_reporting_task_create_rejects_unauthorized_existing_current_team(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    unauthorized_group = Group.objects.create(name="未授权组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    request = _req(
        "post",
        scoped_user,
        data={"name": "日报任务", "team": [unauthorized_group.id], "config": {"metrics": ["count"]}},
        current_team=str(unauthorized_group.id),
        include_children="0",
    )

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(request)
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"


@pytest.mark.django_db
def test_custom_reporting_task_create_hides_duplicate_name_in_unauthorized_team(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    unauthorized_group = Group.objects.create(name="未授权组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    CustomReportingTask.objects.create(
        name="泄漏任务",
        team=[unauthorized_group.id],
        config={"metrics": ["count"]},
    )

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(
        _req(
            "post",
            scoped_user,
            data={"name": "泄漏任务", "team": [unauthorized_group.id], "config": {"metrics": ["count"]}},
            current_team=str(authorized_group.id),
            include_children="0",
        )
    )
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"


@pytest.mark.django_db
def test_custom_reporting_task_requires_current_team_for_list_retrieve_and_destroy(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[authorized_group.id],
        config={"metrics": ["count"]},
    )

    list_response = CustomReportingTaskViewSet.as_view({"get": "list"})(
        _req("get", scoped_user)
    )
    list_body = _body(list_response)

    assert list_response.status_code == status.HTTP_400_BAD_REQUEST
    assert list_body["result"] is False
    assert list_body["message"] == "缺少 current_team 参数"

    retrieve_response = CustomReportingTaskViewSet.as_view({"get": "retrieve"})(
        _req("get", scoped_user),
        pk=task.pk,
    )
    retrieve_body = _body(retrieve_response)

    assert retrieve_response.status_code == status.HTTP_400_BAD_REQUEST
    assert retrieve_body["result"] is False
    assert retrieve_body["message"] == "缺少 current_team 参数"

    destroy_response = CustomReportingTaskViewSet.as_view({"delete": "destroy"})(
        _req("delete", scoped_user),
        pk=task.pk,
    )
    destroy_body = _body(destroy_response)

    assert destroy_response.status_code == status.HTTP_400_BAD_REQUEST
    assert destroy_body["result"] is False
    assert destroy_body["message"] == "缺少 current_team 参数"

    task.refresh_from_db()
    assert task.name == "日报任务"


@pytest.mark.django_db
def test_custom_reporting_task_update_rejects_partial_overlap_on_shared_task(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    shared_group = Group.objects.create(name="共享组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    task = CustomReportingTask.objects.create(
        name="共享任务",
        team=[authorized_group.id, shared_group.id],
        config={"metrics": ["count"]},
    )

    retrieve_response = CustomReportingTaskViewSet.as_view({"get": "retrieve"})(
        _req("get", scoped_user, current_team=str(authorized_group.id), include_children="0"),
        pk=task.pk,
    )

    assert retrieve_response.status_code == status.HTTP_200_OK

    update_response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            scoped_user,
            data={"name": "被拒绝更新", "team": [authorized_group.id], "config": {"metrics": ["count"]}},
            current_team=str(authorized_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    update_body = _body(update_response)

    assert update_response.status_code == status.HTTP_403_FORBIDDEN
    assert update_body["result"] is False
    assert update_body["message"] == "抱歉！您没有该组织的权限或组织选择无效"
    task.refresh_from_db()
    assert task.name == "共享任务"
    assert task.team == [authorized_group.id, shared_group.id]


@pytest.mark.django_db
def test_custom_reporting_task_update_hides_duplicate_name_in_unauthorized_team(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    unauthorized_group = Group.objects.create(name="未授权组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    task = CustomReportingTask.objects.create(
        name="原任务",
        team=[authorized_group.id],
        config={"metrics": ["count"]},
    )
    CustomReportingTask.objects.create(
        name="泄漏任务",
        team=[unauthorized_group.id],
        config={"metrics": ["count"]},
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            scoped_user,
            data={"name": "泄漏任务", "team": [unauthorized_group.id], "config": {"metrics": ["count"]}},
            current_team=str(authorized_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"
    task.refresh_from_db()
    assert task.name == "原任务"
    assert task.team == [authorized_group.id]


@pytest.mark.django_db
def test_custom_reporting_task_destroy_rejects_partial_overlap_on_shared_task(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    shared_group = Group.objects.create(name="共享组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    task = CustomReportingTask.objects.create(
        name="共享任务",
        team=[authorized_group.id, shared_group.id],
        config={"metrics": ["count"]},
    )

    destroy_response = CustomReportingTaskViewSet.as_view({"delete": "destroy"})(
        _req("delete", scoped_user, current_team=str(authorized_group.id), include_children="0"),
        pk=task.pk,
    )
    destroy_body = _body(destroy_response)

    assert destroy_response.status_code == status.HTTP_403_FORBIDDEN
    assert destroy_body["result"] is False
    assert destroy_body["message"] == "抱歉！您没有该组织的权限或组织选择无效"
    task.refresh_from_db()
    assert task.name == "共享任务"
    assert task.team == [authorized_group.id, shared_group.id]


@pytest.mark.django_db
def test_custom_reporting_task_validate_current_team_rejects_unknown_org(superuser):
    request = _req("get", superuser)
    request.COOKIES["current_team"] = "999999"

    response = CustomReportingTaskViewSet._validate_current_team(request)
    body = _body(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert body["result"] is False
    assert body["message"] == "抱歉！您没有该组织的权限或组织选择无效"


@pytest.mark.django_db
def test_custom_reporting_task_denies_read_update_delete_with_forged_current_team(scoped_user):
    authorized_group = Group.objects.create(name="授权组织")
    unauthorized_group = Group.objects.create(name="未授权组织")
    scoped_user.group_list = [{"id": authorized_group.id}]
    foreign_task = CustomReportingTask.objects.create(
        name="跨组织任务",
        team=[unauthorized_group.id],
        config={"metrics": ["count"]},
    )

    list_response = CustomReportingTaskViewSet.as_view({"get": "list"})(
        _req("get", scoped_user, current_team=str(unauthorized_group.id), include_children="0")
    )
    list_body = _body(list_response)

    assert list_response.status_code == status.HTTP_200_OK
    assert list_body["data"]["count"] == 0
    assert list_body["data"]["results"] == []

    retrieve_response = CustomReportingTaskViewSet.as_view({"get": "retrieve"})(
        _req("get", scoped_user, current_team=str(unauthorized_group.id), include_children="0"),
        pk=foreign_task.pk,
    )
    assert retrieve_response.status_code == status.HTTP_404_NOT_FOUND

    update_response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            scoped_user,
            data={"name": "被绕过更新", "team": [unauthorized_group.id], "config": {"metrics": ["count"]}},
            current_team=str(unauthorized_group.id),
            include_children="0",
        ),
        pk=foreign_task.pk,
    )
    assert update_response.status_code == status.HTTP_404_NOT_FOUND

    delete_response = CustomReportingTaskViewSet.as_view({"delete": "destroy"})(
        _req("delete", scoped_user, current_team=str(unauthorized_group.id), include_children="0"),
        pk=foreign_task.pk,
    )
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND
    foreign_task.refresh_from_db()
    assert foreign_task.name == "跨组织任务"


def test_custom_reporting_router_registration():
    assert not any(item[0] == "api/custom_reporting/tasks" for item in router.registry)
    assert reverse("custom_reporting-list") == "/api/v1/cmdb/api/custom_reporting/tasks/"
    assert reverse("custom_reporting-onboarding-document", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/onboarding_document/"
    )
    assert reverse("custom_reporting-issue-credential", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/issue_credential/"
    )
    assert reverse("custom_reporting-rotate-credential", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/rotate_credential/"
    )
    assert reverse("custom_reporting-revoke-credential", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/revoke_credential/"
    )
    assert reverse("custom_reporting-batch-activity", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/batch_activity/"
    )
    assert reverse("custom_reporting-ingest", kwargs={"pk": 1}) == (
        "/api/v1/cmdb/api/custom_reporting/tasks/1/ingest/"
    )


def test_cmdb_urls_load_enterprise_urlpatterns_indirectly_without_hardcoded_custom_reporting_viewset(monkeypatch):
    import apps.cmdb.urls as cmdb_urls

    original_import = __import__
    imported_modules = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported_modules.append(name)
        if name == "apps.cmdb.enterprise.urls":
            return SimpleNamespace(urlpatterns=[])
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    reloaded_urls = importlib.reload(cmdb_urls)

    assert "apps.cmdb.enterprise.urls" in imported_modules
    assert "CustomReportingTaskViewSet" not in reloaded_urls.__dict__


def test_cmdb_urls_import_succeeds_without_enterprise_module(monkeypatch):
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "apps.cmdb.enterprise.urls":
            raise ModuleNotFoundError("No module named 'apps.cmdb.enterprise'", name="apps.cmdb.enterprise")
        return original_import(name, globals, locals, fromlist, level)

    sys.modules.pop("apps.cmdb.urls", None)
    sys.modules.pop("apps.cmdb.enterprise", None)
    sys.modules.pop("apps.cmdb.enterprise.urls", None)
    monkeypatch.setattr("builtins.__import__", fake_import)

    imported_urls = importlib.import_module("apps.cmdb.urls")

    assert imported_urls is not None
    assert not any("api/custom_reporting/tasks" in str(pattern.pattern) for pattern in imported_urls.urlpatterns)


@pytest.mark.django_db
def test_custom_reporting_task_create_quick_mode_bootstraps_model(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    bootstrap_calls = []

    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.bootstrap_custom_reporting_model",
        lambda quick_model, team, username="admin": bootstrap_calls.append((dict(quick_model), list(team), username))
        or {
            "model_id": "report_asset",
            "model_name": "上报资产",
            "classification_id": "server",
            "group": list(team),
            "identity_keys": ["asset_code"],
        },
    )

    request = _req(
        "post",
        superuser,
        data={
            "name": "快捷上报",
            "team": [current_group.id],
            "config": {"mode": "quick", "metrics": ["count"]},
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "identity_keys": ["asset_code"],
            },
        },
    )
    request.COOKIES["current_team"] = str(current_group.id)

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(request)
    body = _body(response)

    assert response.status_code == status.HTTP_200_OK
    assert bootstrap_calls == [
        (
            {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "identity_keys": ["asset_code"],
            },
            [current_group.id],
            superuser.username,
        )
    ]
    assert body["data"]["config"]["quick_model"] == {
        "model_id": "report_asset",
        "model_name": "上报资产",
        "classification_id": "server",
        "group": [current_group.id],
        "identity_keys": ["asset_code"],
    }
    assert body["data"]["config"]["identity_keys"] == ["asset_code"]


@pytest.mark.django_db
def test_custom_reporting_task_create_auto_issues_task_credential_and_returns_raw_token(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    monkeypatch.setattr(
        "apps.cmdb.models.custom_reporting.secrets.token_urlsafe",
        lambda size=32: "created-token",
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": "report_asset"} if model_id == "report_asset" else {},
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "create"})(
        _req(
            "post",
            superuser,
            data={
                "name": "普通上报",
                "team": [current_group.id],
                "config": {"mode": "manual", "model_id": "report_asset", "metrics": ["count"]},
            },
            current_team=str(current_group.id),
            include_children="0",
        )
    )
    body = _body(response)

    task = CustomReportingTask.objects.get(name="普通上报")
    credential = CustomReportingCredential.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["token"] == "created-token"
    assert body["data"]["credential"]["id"] == credential.id
    assert body["data"]["credential"]["name"] == "默认凭据"
    assert body["data"]["credential"]["credential_type"] == "api_token"
    assert body["data"]["credential"]["credential_data"]["token_hash"] == hashlib.sha256(
        "created-token".encode("utf-8")
    ).hexdigest()
    assert body["data"]["credential"]["credential_data"]["token_masked"] is True
    assert "token" not in credential.credential_data


@pytest.mark.django_db
def test_custom_reporting_task_credential_actions_and_onboarding_document(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "identity_keys": ["asset_code"],
            },
        },
    )
    issued_tokens = iter(["issued-token", "rotated-token"])
    monkeypatch.setattr(
        "apps.cmdb.models.custom_reporting.secrets.token_urlsafe",
        lambda size=32: next(issued_tokens),
    )

    issue_response = CustomReportingTaskViewSet.as_view({"post": "issue_credential"})(
        _req(
            "post",
            superuser,
            data={"name": "默认凭据"},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    issue_body = _body(issue_response)

    assert issue_response.status_code == status.HTTP_200_OK
    assert issue_body["data"]["token"] == "issued-token"
    credential_id = issue_body["data"]["credential"]["id"]
    credential = CustomReportingCredential.objects.get(id=credential_id)
    assert "token" not in credential.credential_data

    onboarding_response = CustomReportingTaskViewSet.as_view({"get": "onboarding_document"})(
        _req("get", superuser, current_team=str(current_group.id), include_children="0"),
        pk=task.pk,
    )
    onboarding_body = _body(onboarding_response)

    assert onboarding_response.status_code == status.HTTP_200_OK
    assert onboarding_body["data"]["endpoint"].endswith(f"/api/v1/cmdb/api/custom_reporting/tasks/{task.pk}/ingest/")
    assert onboarding_body["data"]["auth_header"] == {
        "name": "Authorization",
        "format": "Bearer <token>",
    }
    assert onboarding_body["data"]["identity_keys"] == ["asset_code"]
    assert onboarding_body["data"]["example_payload"] == {
        "instances": [
            {
                "identity": {"asset_code": "demo_asset_code"},
                "attributes": {"task_name": task.name},
            }
        ],
        "relations": [],
        "batch_metadata": {},
    }
    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: {
            "created": [
                {
                    "_id": 101,
                    "model_id": "report_asset",
                    "inst_name": "demo_asset_code",
                }
            ],
            "updated": [],
            "pending_relations": [],
        },
        raising=False,
    )

    ingest_response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data=onboarding_body["data"]["example_payload"],
            headers={"HTTP_AUTHORIZATION": "Bearer issued-token"},
        ),
        pk=task.pk,
    )
    ingest_body = _body(ingest_response)

    task.refresh_from_db()
    batch = CustomReportingBatch.objects.get(task=task)

    assert ingest_response.status_code == status.HTTP_200_OK
    assert ingest_body["data"] == {
        "task_id": task.pk,
        "batch_id": batch.pk,
        "accepted": True,
        "summary": {
            "instances_received": 1,
            "relations_received": 0,
            "created": 1,
            "updated": 0,
            "pending_relations": 0,
            "registered_fields": [],
        },
    }
    assert batch.status == CustomReportingBatch.STATUS_SUCCESS
    assert batch.summary == {
        "instances_received": 1,
        "relations_received": 0,
        "created": 1,
        "updated": 0,
        "pending_relations": 0,
        "registered_fields": [],
        "batch_metadata": {},
    }
    assert task.last_reported_at is not None

    rotate_response = CustomReportingTaskViewSet.as_view({"post": "rotate_credential"})(
        _req(
            "post",
            superuser,
            data={"credential_id": credential_id},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    rotate_body = _body(rotate_response)

    assert rotate_response.status_code == status.HTTP_200_OK
    assert rotate_body["data"]["token"] == "rotated-token"

    revoke_response = CustomReportingTaskViewSet.as_view({"post": "revoke_credential"})(
        _req(
            "post",
            superuser,
            data={"credential_id": credential_id},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    revoke_body = _body(revoke_response)
    credential.refresh_from_db()

    assert revoke_response.status_code == status.HTTP_200_OK
    assert revoke_body["data"] == {"credential_id": credential_id, "is_enabled": False}
    assert credential.is_enabled is False


@pytest.mark.django_db
def test_custom_reporting_task_issue_credential_reuses_existing_row(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "quick", "quick_model": {"model_id": "report_asset"}},
    )
    issued_tokens = iter(["issued-token", "reissued-token"])
    monkeypatch.setattr(
        "apps.cmdb.models.custom_reporting.secrets.token_urlsafe",
        lambda size=32: next(issued_tokens),
    )

    first_issue_response = CustomReportingTaskViewSet.as_view({"post": "issue_credential"})(
        _req(
            "post",
            superuser,
            data={"name": "默认凭据"},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    first_issue_body = _body(first_issue_response)

    second_issue_response = CustomReportingTaskViewSet.as_view({"post": "issue_credential"})(
        _req(
            "post",
            superuser,
            data={"name": "新的显示名"},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    second_issue_body = _body(second_issue_response)

    assert first_issue_response.status_code == status.HTTP_200_OK
    assert second_issue_response.status_code == status.HTTP_200_OK
    assert CustomReportingCredential.objects.filter(task=task).count() == 1
    assert second_issue_body["data"]["credential"]["id"] == first_issue_body["data"]["credential"]["id"]
    assert second_issue_body["data"]["credential"]["name"] == "新的显示名"
    assert first_issue_body["data"]["token"] == "issued-token"
    assert "token" not in second_issue_body["data"]


@pytest.mark.django_db
def test_custom_reporting_task_retrieve_and_batch_activity_include_stable_credential_and_review_data(
    superuser,
):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "quick", "quick_model": {"model_id": "report_asset"}},
        last_reported_at=timezone.now(),
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
        is_enabled=True,
    )
    credential.issue_token(token="stable-token")
    success_batch = CustomReportingBatch.objects.create(
        task=task,
        status=CustomReportingBatch.STATUS_SUCCESS,
        summary={
            "instances_received": 2,
            "relations_received": 1,
            "created": 1,
            "updated": 1,
            "pending_relations": 0,
            "registered_fields": ["asset_code"],
            "batch_metadata": {"source": "demo"},
        },
    )
    failed_batch = CustomReportingBatch.objects.create(
        task=task,
        status=CustomReportingBatch.STATUS_FAILED,
        summary={
            "instances_received": 1,
            "relations_received": 0,
            "created": 0,
            "updated": 0,
            "pending_relations": 0,
            "registered_fields": [],
            "batch_metadata": {},
            "error": "validation failed",
        },
    )
    approved_review = CustomReportingCleanupReview.objects.create(
        batch=success_batch,
        status=CustomReportingCleanupReview.STATUS_APPROVED,
        review_payload={"candidates": 2},
        reviewed_by="admin",
        reviewed_at=timezone.now(),
        created_by="admin",
        updated_by="admin",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    pending_review = CustomReportingCleanupReview.objects.create(
        batch=failed_batch,
        status=CustomReportingCleanupReview.STATUS_PENDING,
        review_payload={"candidates": 1},
        created_by="admin",
        updated_by="admin",
        domain="domain.com",
        updated_by_domain="domain.com",
    )

    retrieve_response = CustomReportingTaskViewSet.as_view({"get": "retrieve"})(
        _req("get", superuser, current_team=str(current_group.id), include_children="0"),
        pk=task.pk,
    )
    batch_activity_response = CustomReportingTaskViewSet.as_view({"get": "batch_activity"})(
        _req("get", superuser, current_team=str(current_group.id), include_children="0"),
        pk=task.pk,
    )

    retrieve_body = _body(retrieve_response)
    batch_activity_body = _body(batch_activity_response)

    assert retrieve_response.status_code == status.HTTP_200_OK
    assert retrieve_body["data"]["credential"]["id"] == credential.id
    assert retrieve_body["data"]["credential"]["is_enabled"] is True
    assert retrieve_body["data"]["credential"]["last_used_at"] is None
    assert "token" not in retrieve_body["data"]
    assert retrieve_body["data"]["recent_batches"][0]["id"] == failed_batch.id
    assert retrieve_body["data"]["recent_batches"][0]["cleanup_reviews"][0]["id"] == pending_review.id
    assert retrieve_body["data"]["recent_batches"][1]["id"] == success_batch.id
    assert retrieve_body["data"]["recent_batches"][1]["cleanup_reviews"][0]["id"] == approved_review.id
    assert retrieve_body["data"]["review_status_summary"] == {
        "pending": 1,
        "approved": 1,
        "rejected": 0,
        "total": 2,
    }

    assert batch_activity_response.status_code == status.HTTP_200_OK
    assert batch_activity_body["data"]["task_id"] == task.id
    assert [item["id"] for item in batch_activity_body["data"]["batches"]] == [
        failed_batch.id,
        success_batch.id,
    ]
    assert [item["id"] for item in batch_activity_body["data"]["cleanup_reviews"]] == [
        pending_review.id,
        approved_review.id,
    ]
    assert batch_activity_body["data"]["review_status_summary"]["total"] == 2


@pytest.mark.django_db
def test_custom_reporting_task_create_quick_mode_does_not_bootstrap_model_when_task_save_fails(monkeypatch):
    bootstrap_calls = []

    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.bootstrap_custom_reporting_model",
        lambda quick_model, team, username="admin": bootstrap_calls.append((dict(quick_model), list(team), username))
        or {
            "model_id": "report_asset",
            "model_name": "上报资产",
            "classification_id": "server",
            "group": list(team),
            "identity_keys": ["asset_code"],
        },
    )
    monkeypatch.setattr(
        CustomReportingTask,
        "save",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(IntegrityError("task save failed")),
    )

    with pytest.raises(IntegrityError, match="task save failed"):
        CustomReportingTaskService.create_task(
            {
                "name": "快捷上报",
                "team": [1],
                "config": {"mode": "quick", "metrics": ["count"]},
                "quick_model": {
                    "model_id": "report_asset",
                    "model_name": "上报资产",
                    "classification_id": "server",
                    "identity_keys": ["asset_code"],
                },
                "created_by": "admin",
                "updated_by": "admin",
                "domain": "domain.com",
                "updated_by_domain": "domain.com",
            }
        )

    assert bootstrap_calls == []


@pytest.mark.django_db
def test_custom_reporting_task_update_quick_mode_does_not_sync_model_group_when_task_save_fails(monkeypatch):
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[1],
        config={
            "mode": "quick",
            "metrics": ["count"],
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [1],
                "identity_keys": ["asset_code"],
            },
            "identity_keys": ["asset_code"],
        },
    )
    sync_calls = []

    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.sync_custom_reporting_model_group",
        lambda quick_model, team, username="admin": sync_calls.append((dict(quick_model), list(team), username))
        or {
            **dict(quick_model),
            "group": list(team),
        },
    )
    monkeypatch.setattr(
        CustomReportingTask,
        "save",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(IntegrityError("task save failed")),
    )

    with pytest.raises(IntegrityError, match="task save failed"):
        CustomReportingTaskService.update_task(
            task,
            {
                "name": "快捷上报-更新",
                "team": [2],
                "config": {"mode": "quick", "metrics": ["sum"]},
                "updated_by": "admin",
            },
        )

    assert sync_calls == []


@pytest.mark.django_db
def test_custom_reporting_task_update_quick_mode_reuses_existing_quick_model(superuser):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "metrics": ["count"],
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "identity_keys": ["asset_code"],
            },
            "identity_keys": ["asset_code"],
        },
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            superuser,
            data={
                "name": "快捷上报-更新",
                "team": [current_group.id],
                "config": {"mode": "quick", "metrics": ["sum"]},
            },
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)

    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["config"] == {
        "mode": "quick",
        "metrics": ["sum"],
        "quick_model": {
            "model_id": "report_asset",
            "model_name": "上报资产",
            "classification_id": "server",
            "identity_keys": ["asset_code"],
        },
        "identity_keys": ["asset_code"],
    }


@pytest.mark.django_db
def test_custom_reporting_task_update_quick_mode_syncs_existing_quick_model_group(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    target_group = Group.objects.create(name="目标组织")
    sync_calls = []
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "metrics": ["count"],
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [current_group.id],
                "identity_keys": ["asset_code"],
            },
            "identity_keys": ["asset_code"],
        },
    )
    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.sync_custom_reporting_model_group",
        lambda quick_model, team, username="admin": sync_calls.append((dict(quick_model), list(team), username))
        or {
            **dict(quick_model),
            "group": list(team),
        },
    )
    monkeypatch.setattr(
        CustomReportingTaskViewSet,
        "_get_allowed_org_ids",
        staticmethod(lambda request: [current_group.id, target_group.id]),
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            superuser,
            data={
                "name": "快捷上报-更新",
                "team": [target_group.id],
                "config": {"mode": "quick", "metrics": ["sum"]},
            },
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)
    task.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert sync_calls == [
        (
            {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [current_group.id],
                "identity_keys": ["asset_code"],
            },
            [target_group.id],
            superuser.username,
        )
    ]
    assert body["data"]["team"] == [target_group.id]
    assert body["data"]["config"]["quick_model"]["group"] == [target_group.id]
    assert task.config["quick_model"]["group"] == [target_group.id]


@pytest.mark.django_db
def test_custom_reporting_task_update_quick_mode_persists_identity_keys(superuser, monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    created_attrs = []
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "metrics": ["count"],
            "quick_model": {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [current_group.id],
                "identity_keys": ["asset_code"],
            },
            "identity_keys": ["asset_code"],
        },
    )
    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.search_model_attr",
        lambda model_id, language="en": [{"attr_id": "asset_code"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.custom_reporting_task_service.ModelManage.create_model_attr",
        lambda model_id, attr_info, username="admin": created_attrs.append(
            (model_id, dict(attr_info), username)
        )
        or attr_info,
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            superuser,
            data={
                "name": "快捷上报-更新",
                "team": [current_group.id],
                "config": {
                    "mode": "quick",
                    "metrics": ["sum"],
                    "identity_keys": ["serial_no", "asset_code"],
                },
            },
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)
    task.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["config"]["identity_keys"] == ["serial_no", "asset_code"]
    assert body["data"]["config"]["quick_model"]["identity_keys"] == [
        "serial_no",
        "asset_code",
    ]
    assert task.config["identity_keys"] == ["serial_no", "asset_code"]
    assert task.config["quick_model"]["identity_keys"] == ["serial_no", "asset_code"]
    assert created_attrs == [
        (
            "report_asset",
            {
                "attr_id": "serial_no",
                "attr_name": "serial_no",
                "attr_group": "default",
                "attr_type": "str",
                "is_only": True,
                "is_required": False,
                "editable": True,
                "option": {},
                "user_prompt": "",
                "default_value": [],
            },
            superuser.username,
        )
    ]


@pytest.mark.django_db
def test_custom_reporting_task_update_requires_quick_model_when_switching_to_quick_mode(superuser):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            superuser,
            data={
                "name": "普通上报",
                "team": [current_group.id],
                "config": {"mode": "quick", "metrics": ["count"]},
            },
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "quick 模式需要 quick_model 配置" in json.dumps(body, ensure_ascii=False)


@pytest.mark.django_db
def test_custom_reporting_task_rotate_and_revoke_missing_credential_return_404(superuser):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )

    rotate_response = CustomReportingTaskViewSet.as_view({"post": "rotate_credential"})(
        _req(
            "post",
            superuser,
            data={"credential_id": 999999},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    revoke_response = CustomReportingTaskViewSet.as_view({"post": "revoke_credential"})(
        _req(
            "post",
            superuser,
            data={"credential_id": 999999},
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )

    assert rotate_response.status_code == status.HTTP_404_NOT_FOUND
    assert revoke_response.status_code == status.HTTP_404_NOT_FOUND
    assert "凭据不存在" in json.dumps(_body(rotate_response), ensure_ascii=False)
    assert "凭据不存在" in json.dumps(_body(revoke_response), ensure_ascii=False)


@pytest.mark.django_db
def test_custom_reporting_task_ingest_rejects_invalid_bearer_token():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={"instances": [], "relations": [], "batch_metadata": {}},
            headers={"HTTP_AUTHORIZATION": "Bearer invalid-token"},
        ),
        pk=task.pk,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "token" in json.dumps(_body(response), ensure_ascii=False).lower()


@pytest.mark.django_db
def test_custom_reporting_task_ingest_rejects_disabled_task_even_with_valid_bearer_token():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
        is_enabled=False,
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={"instances": [], "relations": [], "batch_metadata": {}},
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    credential.refresh_from_db()

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert credential.last_used_at is None


@pytest.mark.django_db
def test_custom_reporting_task_ingest_rejects_revoked_bearer_token():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")
    credential.revoke_token()

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={"instances": [], "relations": [], "batch_metadata": {}},
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    credential.refresh_from_db()

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert credential.last_used_at is None


@pytest.mark.django_db
def test_custom_reporting_task_ingest_accepts_valid_bearer_token_without_user_rbac():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={"instances": [], "relations": [], "batch_metadata": {}},
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    body = _body(response)
    credential.refresh_from_db()
    task.refresh_from_db()

    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert body["data"] == {
        "task_id": task.pk,
        "batch_id": batch.pk,
        "accepted": True,
        "summary": {
            "instances_received": 0,
            "relations_received": 0,
            "created": 0,
            "updated": 0,
            "pending_relations": 0,
            "registered_fields": [],
        },
    }
    assert batch.status == CustomReportingBatch.STATUS_SUCCESS
    assert batch.summary == {
        "instances_received": 0,
        "relations_received": 0,
        "created": 0,
        "updated": 0,
        "pending_relations": 0,
        "registered_fields": [],
        "batch_metadata": {},
    }
    assert credential.last_used_at is not None
    assert credential.last_used_at <= timezone.now()
    assert task.last_reported_at is not None
    assert task.last_reported_at <= timezone.now()


@pytest.mark.django_db
def test_custom_reporting_task_ingest_quick_mode_registers_fields_and_persists_pending_relations(
    monkeypatch,
):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    register_calls = []
    merge_calls = []

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda model_id, instances, username="admin": register_calls.append(
            {
                "model_id": model_id,
                "instances": [dict(item) for item in instances],
                "username": username,
            }
        )
        or ["new_field"],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: merge_calls.append(dict(kwargs))
        or {
            "created": [{"_id": 101, "model_id": "report_asset", "inst_name": "asset-1"}],
            "updated": [],
            "pending_relations": [
                {
                    "source_model_id": "report_asset",
                    "target_model_id": "host",
                    "relation_payload": {
                        "source": {"asset_code": "asset-1"},
                        "target": {"inst_name": "host-1"},
                        "relation_type": "depends_on",
                    },
                }
            ],
        },
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [
                    {
                        "identity": {"asset_code": "asset-1"},
                        "attributes": {"new_field": "value-1"},
                    }
                ],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {"inst_name": "host-1"},
                        "relation_type": "depends_on",
                        "attributes": {},
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    body = _body(response)
    task.refresh_from_db()
    batch = CustomReportingBatch.objects.get(task=task)
    pending_relation = CustomReportingPendingRelation.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert register_calls == [
        {
            "model_id": "report_asset",
            "instances": [
                {
                    "identity": {"asset_code": "asset-1"},
                    "attributes": {"new_field": "value-1"},
                }
            ],
            "username": "custom-reporting-task-{}".format(task.pk),
        }
    ]
    assert merge_calls == [
        {
            "model_id": "report_asset",
            "instances": [
                {
                    "identity": {"asset_code": "asset-1"},
                    "attributes": {"new_field": "value-1"},
                }
            ],
            "relations": [
                {
                    "source": {"asset_code": "asset-1"},
                    "target": {"inst_name": "host-1"},
                    "relation_type": "depends_on",
                    "attributes": {},
                }
            ],
            "identity_keys": ["asset_code"],
            "operator": f"custom-reporting-task-{task.pk}",
            "allowed_org_ids": [current_group.id],
        }
    ]
    assert body["data"] == {
        "task_id": task.pk,
        "batch_id": batch.pk,
        "accepted": True,
        "summary": {
            "instances_received": 1,
            "relations_received": 1,
            "created": 1,
            "updated": 0,
            "pending_relations": 1,
            "registered_fields": ["new_field"],
        },
    }
    assert batch.status == CustomReportingBatch.STATUS_SUCCESS
    assert batch.summary == {
        "instances_received": 1,
        "relations_received": 1,
        "created": 1,
        "updated": 0,
        "pending_relations": 1,
        "registered_fields": ["new_field"],
        "batch_metadata": {"source": "agent"},
    }
    assert pending_relation.source_model_id == "report_asset"
    assert pending_relation.target_model_id == "host"
    assert pending_relation.relation_payload["relation_type"] == "depends_on"
    assert task.last_reported_at is not None


@pytest.mark.django_db
def test_custom_reporting_task_ingest_writes_custom_reporting_change_records(monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: {
            "created": [
                {
                    "_id": 201,
                    "model_id": "report_asset",
                    "inst_name": "asset-201",
                }
            ],
            "updated": [
                {
                    "_id": 202,
                    "model_id": "report_asset",
                    "inst_name": "asset-202",
                }
            ],
            "pending_relations": [],
        },
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [
                    {"identity": {"asset_code": "asset-201"}},
                    {"identity": {"asset_code": "asset-202"}},
                ],
                "relations": [],
                "batch_metadata": {},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )

    assert response.status_code == status.HTTP_200_OK
    assert ChangeRecord.objects.filter(
        scenario=CUSTOM_REPORTING_CHANGE,
        model_id="report_asset",
    ).count() == 2


def test_merge_custom_reporting_instances_rejects_missing_configured_identity_key(monkeypatch):
    create_calls = []

    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda *args, **kwargs: pytest.fail("should not query without full identity"),
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda *args, **kwargs: create_calls.append((args, kwargs)),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="identity"):
        InstanceManage.merge_custom_reporting_instances(
            model_id="report_asset",
            instances=[
                {
                    "identity": {"asset_code": "asset-1"},
                    "attributes": {"inst_name": "asset-1"},
                }
            ],
            relations=[],
            identity_keys=["asset_code", "serial_no"],
            operator="custom-reporting-task-1",
            allowed_org_ids=[1],
        )

    assert create_calls == []


def test_merge_custom_reporting_instances_defaults_inst_name_from_identity_when_omitted(monkeypatch):
    create_payloads = []

    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda *args, **kwargs: {},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda model_id, payload, *args, **kwargs: create_payloads.append(
            {"model_id": model_id, "payload": dict(payload)}
        )
        or {"_id": 501, "model_id": model_id, **payload},
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[
            {
                "identity": {"asset_code": "asset-1"},
                "attributes": {"new_field": "value-1"},
            }
        ],
        relations=[],
        identity_keys=["asset_code", "inst_name"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert create_payloads == [
        {
            "model_id": "report_asset",
            "payload": {
                "asset_code": "asset-1",
                "inst_name": "asset-1",
                "new_field": "value-1",
            },
        }
    ]
    assert result["created"][0]["inst_name"] == "asset-1"


def test_merge_custom_reporting_instances_quick_mode_synthesizes_inst_name_without_inst_name_identity_key(monkeypatch):
    create_payloads = []

    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda *args, **kwargs: {},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda model_id, payload, *args, **kwargs: create_payloads.append(
            {"model_id": model_id, "payload": dict(payload)}
        )
        or {"_id": 502, "model_id": model_id, **payload},
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[
            {
                "identity": {"asset_code": "asset-1"},
                "attributes": {"new_field": "value-1"},
            }
        ],
        relations=[],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert create_payloads == [
        {
            "model_id": "report_asset",
            "payload": {
                "asset_code": "asset-1",
                "inst_name": "asset-1",
                "new_field": "value-1",
            },
        }
    ]
    assert result["created"][0]["inst_name"] == "asset-1"


def test_query_entity_by_identity_rejects_non_unique_lookup(monkeypatch):
    queried = []

    class DummyGraphClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query_entity(self, label, params):
            queried.append({"label": label, "params": params})
            return (
                [
                    {"_id": 1, "model_id": "report_asset", "asset_code": "asset-1"},
                    {"_id": 2, "model_id": "report_asset", "asset_code": "asset-1"},
                ],
                2,
            )

    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", DummyGraphClient)

    with pytest.raises(BaseAppException, match="唯一"):
        InstanceManage.query_entity_by_identity("report_asset", {"asset_code": "asset-1"})

    assert queried and queried[0]["params"][0]["value"] == "report_asset"


def test_merge_custom_reporting_instances_resolves_relations_before_marking_pending(monkeypatch):
    association_calls = []

    def fake_query(model_id, identity):
        if model_id == "host" and identity == {"inst_name": "host-1"}:
            return {"_id": 301, "model_id": "host", "inst_name": "host-1"}
        return {}

    created_ids = iter([201, 202])

    monkeypatch.setattr(InstanceManage, "query_entity_by_identity", fake_query, raising=False)
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda model_id, payload, *args, **kwargs: {
            "_id": next(created_ids),
            "model_id": model_id,
            **payload,
        },
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_create",
        lambda data, operator, scenario=None: association_calls.append(
            {"data": dict(data), "operator": operator, "scenario": scenario}
        )
        or {"_id": len(association_calls)},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda **kwargs: False,
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[
            {"identity": {"asset_code": "asset-1"}, "attributes": {"inst_name": "asset-1"}},
            {"identity": {"asset_code": "asset-2"}, "attributes": {"inst_name": "asset-2"}},
        ],
        relations=[
            {
                "source": {"asset_code": "asset-1"},
                "target": {"asset_code": "asset-2"},
                "relation_type": "asset_depends_on_asset",
            },
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
            },
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "missing-host"},
                "relation_type": "asset_depends_on_host",
            },
        ],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert association_calls == [
        {
            "data": {
                "src_inst_id": 201,
                "dst_inst_id": 202,
                "model_asst_id": "asset_depends_on_asset",
                "attributes": {},
            },
            "operator": "custom-reporting-task-1",
            "scenario": CUSTOM_REPORTING_CHANGE,
        },
        {
            "data": {
                "src_inst_id": 201,
                "dst_inst_id": 301,
                "model_asst_id": "asset_depends_on_host",
                "attributes": {},
            },
            "operator": "custom-reporting-task-1",
            "scenario": CUSTOM_REPORTING_CHANGE,
        },
    ]
    assert result["pending_relations"] == [
        {
            "source_model_id": "report_asset",
            "target_model_id": "host",
            "relation_payload": {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "missing-host"},
                "relation_type": "asset_depends_on_host",
            },
        }
    ]


def test_merge_custom_reporting_instances_processes_relation_only_batches(monkeypatch):
    association_calls = []

    def fake_query(model_id, identity):
        if model_id == "report_asset" and identity == {"asset_code": "asset-1"}:
            return {"_id": 401, "model_id": "report_asset", "asset_code": "asset-1"}
        if model_id == "host" and identity == {"inst_name": "host-1"}:
            return {"_id": 402, "model_id": "host", "inst_name": "host-1"}
        return {}

    monkeypatch.setattr(InstanceManage, "query_entity_by_identity", fake_query, raising=False)
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_create",
        lambda data, operator, scenario=None: association_calls.append(
            {"data": dict(data), "operator": operator, "scenario": scenario}
        )
        or {"_id": 1},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda **kwargs: False,
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[],
        relations=[
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
            }
        ],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert association_calls == [
        {
            "data": {
                "src_inst_id": 401,
                "dst_inst_id": 402,
                "model_asst_id": "asset_depends_on_host",
                "attributes": {},
            },
            "operator": "custom-reporting-task-1",
            "scenario": CUSTOM_REPORTING_CHANGE,
        }
    ]
    assert result["pending_relations"] == []


def test_custom_reporting_ingest_marks_batch_failed_when_merge_raises(monkeypatch):
    batch = SimpleNamespace(
        pk=88,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyTask:
        pk = 7
        team = [1]
        config = {
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        }
        last_reported_at = None

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not be called on failed ingest")

    task = DummyTask()

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        CustomReportingPendingRelation.objects,
        "bulk_create",
        lambda items: pytest.fail("pending relations should not persist on merge failure"),
    )

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: ["new_field"],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("graph write failed")),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="graph write failed"):
        CustomReportingIngestService.ingest(
            task,
            {
                "instances": [{"identity": {"asset_code": "asset-1"}, "attributes": {"new_field": "value-1"}}],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert batch.summary["instances_received"] == 1
    assert batch.summary["relations_received"] == 0
    assert batch.summary["batch_metadata"] == {"source": "agent"}
    assert batch.summary["registered_fields"] == ["new_field"]
    assert batch.summary["error"] == "graph write failed"
    assert batch.summary["error_type"] == "RuntimeError"
    assert batch.saved_updates == [["status", "summary", "updated_at"]]


def test_custom_reporting_ingest_marks_batch_failed_when_change_record_write_fails(monkeypatch):
    batch = SimpleNamespace(
        pk=89,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 8
        team = [1]
        config = {
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            self.last_reported_at = timezone.now()

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: {
            "created": [{"_id": 701, "model_id": "report_asset", "inst_name": "asset-1"}],
            "updated": [],
            "pending_relations": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        CustomReportingIngestService,
        "_create_change_records",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("change record failed")),
        raising=False,
    )

    result = CustomReportingIngestService.ingest(
        DummyTask(),
        {
            "instances": [{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
            "relations": [],
            "batch_metadata": {"source": "agent"},
        },
    )

    assert result["accepted"] is True
    assert batch.status == CustomReportingBatch.STATUS_SUCCESS
    assert batch.summary["created"] == 1
    assert "error" not in batch.summary
    assert batch.saved_updates == [["status", "summary", "updated_at"]]


def test_custom_reporting_ingest_updates_pending_relations_after_metadata_steps(monkeypatch):
    batch = SimpleNamespace(
        pk=90,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )
    operations = []

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    existing_pending_relation = SimpleNamespace(
        id=11,
        relation_payload={
            "source": {"asset_code": "asset-1"},
            "target": {"model_id": "host", "inst_name": "host-1"},
            "relation_type": "asset_depends_on_host",
        },
    )

    class DummyPendingRelations:
        @staticmethod
        def all():
            return [existing_pending_relation]

    class DummyTask:
        pk = 9
        team = [1]
        config = {
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            operations.append("task_save")

    def fake_merge(**kwargs):
        if kwargs.get("instances"):
            return {"created": [], "updated": [], "pending_relations": []}
        return {
            "created": [],
            "updated": [],
            "pending_relations": [
                {
                    "source_model_id": "report_asset",
                    "target_model_id": "host",
                    "relation_payload": dict(existing_pending_relation.relation_payload),
                }
            ],
        }

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        fake_merge,
        raising=False,
    )
    monkeypatch.setattr(
        CustomReportingIngestService,
        "_create_change_records",
        lambda *args, **kwargs: operations.append("change_records"),
        raising=False,
    )
    monkeypatch.setattr(
        CustomReportingIngestService,
        "_persist_pending_relations",
        lambda *args, **kwargs: operations.append("persist_pending_relations"),
        raising=False,
    )

    result = CustomReportingIngestService.ingest(
        DummyTask(),
        {
            "instances": [{"identity": {"asset_code": "asset-2"}, "attributes": {}}],
            "relations": [],
            "batch_metadata": {"source": "agent"},
        },
    )

    assert result["accepted"] is True
    assert operations == ["change_records", "task_save", "persist_pending_relations"]


@pytest.mark.django_db
def test_custom_reporting_task_ingest_rejects_unbound_standard_mode_task_and_persists_failed_batch():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={"mode": "manual", "metrics": ["count"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    body = _body(response)
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "model_id" in body["message"]
    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert batch.summary["instances_received"] == 1
    assert batch.summary["batch_metadata"] == {"source": "agent"}
    assert "model_id" in batch.summary["error"]


@pytest.mark.django_db
def test_custom_reporting_task_ingest_manual_mode_ignores_quick_model_override(monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={
            "mode": "manual",
            "model_id": "report_asset",
            "quick_model": {"model_id": "wrong_quick_asset"},
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    merge_calls = []

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: pytest.fail("manual 模式不应注册 quick_model 字段"),
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": "report_asset"},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "asset_code"}],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: merge_calls.append(dict(kwargs))
        or {"created": [], "updated": [], "pending_relations": []},
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert merge_calls[0]["model_id"] == "report_asset"
    assert batch.summary["registered_fields"] == []


@pytest.mark.django_db
def test_custom_reporting_task_ingest_rejects_undeclared_fields_for_standard_mode(monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": "report_asset"},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [
            {"attr_id": "inst_name"},
            {"attr_id": "asset_code"},
        ],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("标准模式遇到未声明字段时不应进入图写入"),
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [
                    {
                        "identity": {"asset_code": "asset-1"},
                        "attributes": {"rogue_field": "value-1"},
                    }
                ],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    body = _body(response)
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "rogue_field" in json.dumps(body, ensure_ascii=False)
    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "rogue_field" in batch.summary["error"]


def test_custom_reporting_task_ingest_rejects_relation_source_missing_identity_for_standard_mode(monkeypatch):
    batch = SimpleNamespace(
        pk=91,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 10
        team = [1]
        config = {
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )

    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": model_id} if model_id in {"report_asset", "host"} else {},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "inst_name"}, {"attr_id": "asset_code"}]
        if model_id == "report_asset"
        else [{"attr_id": "inst_name"}],
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "model_association_info_search",
        lambda model_asst_id: {
            "model_asst_id": model_asst_id,
            "src_model_id": "report_asset",
            "dst_model_id": "host",
        },
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("标准模式关系 identity 非法时不应进入图写入"),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="asset_code"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [],
                "relations": [
                    {
                        "source": {"inst_name": "asset-1"},
                        "target": {"model_id": "host", "inst_name": "host-1"},
                        "relation_type": "asset_depends_on_host",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "asset_code" in batch.summary["error"]


def test_custom_reporting_task_ingest_rejects_relation_target_undeclared_fields_for_standard_mode(monkeypatch):
    batch = SimpleNamespace(
        pk=92,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 11
        team = [1]
        config = {
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )

    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": model_id} if model_id in {"report_asset", "host"} else {},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "inst_name"}, {"attr_id": "asset_code"}]
        if model_id == "report_asset"
        else [{"attr_id": "inst_name"}],
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "model_association_info_search",
        lambda model_asst_id: {
            "model_asst_id": model_asst_id,
            "src_model_id": "report_asset",
            "dst_model_id": "host",
        },
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("标准模式关系 identity 非法时不应进入图写入"),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="rogue_field"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {
                            "model_id": "host",
                            "inst_name": "host-1",
                            "rogue_field": "value-1",
                        },
                        "relation_type": "asset_depends_on_host",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "rogue_field" in batch.summary["error"]


def test_custom_reporting_task_ingest_rejects_quick_mode_relation_target_with_only_model_id(monkeypatch):
    batch = SimpleNamespace(
        pk=120,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 12
        team = [1]
        config = {
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on relation validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda *args, **kwargs: {},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda *args, **kwargs: {
            "_id": 801,
            "model_id": "report_asset",
            "asset_code": "asset-1",
            "inst_name": "asset-1",
        },
        raising=False,
    )
    monkeypatch.setattr(
        CustomReportingPendingRelation.objects,
        "bulk_create",
        lambda items: pytest.fail("缺少 target identity 时不应持久化待处理关系"),
    )

    with pytest.raises(BaseAppException, match="target.*identity"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {"model_id": "host"},
                        "relation_type": "asset_depends_on_host",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "target" in batch.summary["error"]
    assert batch.saved_updates == [["status", "summary", "updated_at"]]


def test_custom_reporting_task_ingest_rejects_blank_relation_type_for_standard_mode(monkeypatch):
    batch = SimpleNamespace(
        pk=93,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 12
        team = [1]
        config = {
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": model_id} if model_id in {"report_asset", "host"} else {},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "inst_name"}, {"attr_id": "asset_code"}]
        if model_id == "report_asset"
        else [{"attr_id": "inst_name"}],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("relation_type 非法时不应进入图写入"),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="relation_type"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {"model_id": "host", "inst_name": "host-1"},
                        "relation_type": "",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "relation_type" in batch.summary["error"]


def test_custom_reporting_task_ingest_rejects_invalid_relation_type_for_standard_mode(monkeypatch):
    batch = SimpleNamespace(
        pk=94,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 13
        team = [1]
        config = {
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": model_id} if model_id in {"report_asset", "host"} else {},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "inst_name"}, {"attr_id": "asset_code"}]
        if model_id == "report_asset"
        else [{"attr_id": "inst_name"}],
        raising=False,
    )
    monkeypatch.setattr(ModelManage, "model_association_info_search", lambda model_asst_id: {}, raising=False)
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("relation_type 非法时不应进入图写入"),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="relation_type"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {"model_id": "host", "inst_name": "host-1"},
                        "relation_type": "missing_association",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "relation_type" in batch.summary["error"]


def test_custom_reporting_task_ingest_rejects_unknown_relation_target_model_for_standard_mode(monkeypatch):
    batch = SimpleNamespace(
        pk=95,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    class DummyPendingRelations:
        @staticmethod
        def all():
            return []

    class DummyTask:
        pk = 14
        team = [1]
        config = {
            "mode": "manual",
            "model_id": "report_asset",
            "identity_keys": ["asset_code"],
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            pytest.fail("task.save should not run on validation failure")

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": model_id} if model_id == "report_asset" else {},
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_attr",
        lambda model_id: [{"attr_id": "inst_name"}, {"attr_id": "asset_code"}],
        raising=False,
    )
    monkeypatch.setattr(
        ModelManage,
        "model_association_info_search",
        lambda model_asst_id: {
            "model_asst_id": model_asst_id,
            "src_model_id": "report_asset",
            "dst_model_id": "host",
        },
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        lambda **kwargs: pytest.fail("target.model_id 非法时不应进入图写入"),
        raising=False,
    )

    with pytest.raises(BaseAppException, match="target.model_id"):
        CustomReportingIngestService.ingest(
            DummyTask(),
            {
                "instances": [],
                "relations": [
                    {
                        "source": {"asset_code": "asset-1"},
                        "target": {"model_id": "missing_host", "inst_name": "host-1"},
                        "relation_type": "asset_depends_on_host",
                    }
                ],
                "batch_metadata": {"source": "agent"},
            },
        )

    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert "target.model_id" in batch.summary["error"]


@pytest.mark.django_db
def test_custom_reporting_task_ingest_persists_failed_batch_for_authenticated_serializer_error():
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={"mode": "manual", "model_id": "report_asset", "metrics": ["count"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [{"identity": {"asset_code": "asset-1"}}],
                "relations": [{"relation_type": "depends_on"}],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    body = _body(response)
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert body["result"] is False
    assert batch.status == CustomReportingBatch.STATUS_FAILED
    assert batch.summary["instances_received"] == 1
    assert batch.summary["relations_received"] == 1
    assert batch.summary["batch_metadata"] == {"source": "agent"}
    assert batch.summary["error_type"] == "ValidationError"
    assert "source" in batch.summary["error"]


@pytest.mark.django_db
def test_custom_reporting_ingest_reconciles_existing_pending_relations_when_target_arrives(monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")
    CustomReportingPendingRelation.objects.create(
        task=task,
        source_model_id="report_asset",
        target_model_id="report_asset",
        relation_payload={
            "source": {"asset_code": "asset-1"},
            "target": {"asset_code": "asset-2"},
            "relation_type": "asset_depends_on_asset",
        },
    )

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )

    merge_calls = []

    def fake_merge(**kwargs):
        merge_calls.append(
            {
                "instances": [dict(item) for item in kwargs.get("instances", [])],
                "relations": [dict(item) for item in kwargs.get("relations", [])],
            }
        )
        if kwargs.get("instances"):
            return {
                "created": [{"_id": 601, "model_id": "report_asset", "inst_name": "asset-2"}],
                "updated": [],
                "pending_relations": [],
            }
        return {"created": [], "updated": [], "pending_relations": []}

    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        fake_merge,
        raising=False,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [{"identity": {"asset_code": "asset-2"}, "attributes": {}}],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert merge_calls == [
        {
            "instances": [{"identity": {"asset_code": "asset-2"}, "attributes": {}}],
            "relations": [],
        },
        {
            "instances": [],
            "relations": [
                {
                    "source": {"asset_code": "asset-1"},
                    "target": {"asset_code": "asset-2"},
                    "relation_type": "asset_depends_on_asset",
                }
            ],
        },
    ]
    assert CustomReportingPendingRelation.objects.filter(task=task).count() == 0
    assert batch.summary["pending_relations"] == 0


@pytest.mark.django_db
def test_custom_reporting_ingest_reconciles_pending_relations_without_double_persisting_unresolved_rows(monkeypatch):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="快捷上报",
        team=[current_group.id],
        config={
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        },
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="valid-ingest-token")
    existing_pending = CustomReportingPendingRelation.objects.create(
        task=task,
        source_model_id="report_asset",
        target_model_id="host",
        relation_payload={
            "source": {"asset_code": "asset-1"},
            "target": {"model_id": "host", "inst_name": "host-1"},
            "relation_type": "asset_depends_on_host",
        },
    )

    persisted_batches = []

    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )

    def fake_merge(**kwargs):
        if kwargs.get("instances"):
            return {"created": [], "updated": [], "pending_relations": []}
        return {
            "created": [],
            "updated": [],
            "pending_relations": [
                {
                    "source_model_id": "report_asset",
                    "target_model_id": "host",
                    "relation_payload": dict(existing_pending.relation_payload),
                }
            ],
        }

    def fake_bulk_create(items):
        persisted_batches.append(
            [
                {
                    "source_model_id": item.source_model_id,
                    "target_model_id": item.target_model_id,
                    "relation_payload": dict(item.relation_payload),
                }
                for item in items
            ]
        )
        return list(items)

    monkeypatch.setattr(
        InstanceManage,
        "merge_custom_reporting_instances",
        fake_merge,
        raising=False,
    )
    monkeypatch.setattr(
        CustomReportingPendingRelation.objects,
        "bulk_create",
        fake_bulk_create,
    )

    response = CustomReportingTaskViewSet.as_view({"post": "ingest"})(
        _req(
            "post",
            None,
            data={
                "instances": [{"identity": {"asset_code": "asset-2"}, "attributes": {}}],
                "relations": [],
                "batch_metadata": {"source": "agent"},
            },
            headers={"HTTP_AUTHORIZATION": "Bearer valid-ingest-token"},
        ),
        pk=task.pk,
    )
    batch = CustomReportingBatch.objects.get(task=task)

    assert response.status_code == status.HTTP_200_OK
    assert persisted_batches == [
        [
            {
                "source_model_id": "report_asset",
                "target_model_id": "host",
                "relation_payload": {
                    "source": {"asset_code": "asset-1"},
                    "target": {"model_id": "host", "inst_name": "host-1"},
                    "relation_type": "asset_depends_on_host",
                },
            }
        ]
    ]
    assert batch.summary["pending_relations"] == 1


def test_merge_custom_reporting_instances_skips_duplicate_resolved_relations(monkeypatch):
    association_calls = []

    def fake_query(model_id, identity):
        if model_id == "report_asset" and identity == {"asset_code": "asset-1"}:
            return {"_id": 401, "model_id": "report_asset", "asset_code": "asset-1"}
        if model_id == "host" and identity == {"inst_name": "host-1"}:
            return {"_id": 402, "model_id": "host", "inst_name": "host-1"}
        return {}

    monkeypatch.setattr(InstanceManage, "query_entity_by_identity", fake_query, raising=False)
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda **kwargs: False,
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_create",
        lambda data, operator, scenario=None: association_calls.append(
            {"data": dict(data), "operator": operator, "scenario": scenario}
        )
        or {"_id": len(association_calls)},
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[],
        relations=[
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
            },
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
            },
        ],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert association_calls == [
        {
            "data": {
                "src_inst_id": 401,
                "dst_inst_id": 402,
                "model_asst_id": "asset_depends_on_host",
                "attributes": {},
            },
            "operator": "custom-reporting-task-1",
            "scenario": CUSTOM_REPORTING_CHANGE,
        }
    ]
    assert result["pending_relations"] == []


def test_merge_custom_reporting_instances_skips_existing_relations_on_batch_retry(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda model_id, identity: {"_id": 401, "model_id": "report_asset", "asset_code": "asset-1"}
        if model_id == "report_asset"
        else {"_id": 402, "model_id": "host", "inst_name": "host-1"},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda *, src_inst_id, dst_inst_id, model_asst_id: (
            src_inst_id == 401 and dst_inst_id == 402 and model_asst_id == "asset_depends_on_host"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_create",
        lambda *args, **kwargs: pytest.fail("批次重试时已有边不应再次创建"),
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[],
        relations=[
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
            }
        ],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert result["pending_relations"] == []


def test_merge_custom_reporting_instances_updates_existing_relation_attributes(monkeypatch):
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda model_id, identity: {"_id": 401, "model_id": "report_asset", "asset_code": "asset-1"}
        if model_id == "report_asset"
        else {"_id": 402, "model_id": "host", "inst_name": "host-1"},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda **kwargs: True,
        raising=False,
    )
    updated_relations = []
    monkeypatch.setattr(
        "apps.cmdb.enterprise.services.custom_reporting_merge_service.CustomReportingMergeService._get_existing_relation",
        lambda **kwargs: {"edge": {"_id": 901, "attributes": {"role": "old"}}},
    )
    monkeypatch.setattr(
        "apps.cmdb.enterprise.services.custom_reporting_merge_service.CustomReportingMergeService._update_existing_relation",
        lambda edge_id, relation_attributes: updated_relations.append(
            {"edge_id": edge_id, "attributes": dict(relation_attributes)}
        ),
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[],
        relations=[
            {
                "source": {"asset_code": "asset-1"},
                "target": {"model_id": "host", "inst_name": "host-1"},
                "relation_type": "asset_depends_on_host",
                "attributes": {"role": "new"},
            }
        ],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert updated_relations == [{"edge_id": 901, "attributes": {"role": "new"}}]
    assert result["pending_relations"] == []


def test_merge_custom_reporting_instances_ignores_out_of_scope_identity_matches(monkeypatch):
    created_instances = []
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda model_id, identity: {
            "_id": 501,
            "model_id": "report_asset",
            "asset_code": "asset-1",
            "organization": [2],
        },
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda model_id, payload, operator, allowed_org_ids=None, scenario=None, record_change=False: created_instances.append(
            {
                "model_id": model_id,
                "payload": dict(payload),
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        or {"_id": 777, "model_id": model_id, **payload},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_update",
        lambda *args, **kwargs: pytest.fail("out-of-scope existing instance should not be updated"),
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
        relations=[],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert created_instances == [
        {
            "model_id": "report_asset",
            "payload": {"asset_code": "asset-1", "inst_name": "asset-1"},
            "allowed_org_ids": [1],
        }
    ]
    assert result["created"][0]["_id"] == 777


def test_merge_custom_reporting_instances_filters_non_unique_identity_matches_by_allowed_orgs(monkeypatch):
    updated_instances = []

    class FakeGraphClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query_entity(self, label, params):
            return (
                [
                    {"_id": 501, "model_id": "report_asset", "asset_code": "asset-1", "organization": [2]},
                    {"_id": 502, "model_id": "report_asset", "asset_code": "asset-1", "organization": [1]},
                ],
                2,
            )

    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda model_id, identity: (_ for _ in ()).throw(BaseAppException("identity 查询结果不唯一")),
        raising=False,
    )
    monkeypatch.setattr(
        "apps.cmdb.enterprise.services.custom_reporting_merge_service.GraphClient",
        FakeGraphClient,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_update",
        lambda _1, _2, inst_id, payload, operator, allowed_org_ids=None, scenario=None, skip_permission_check=False, record_change=False: updated_instances.append(
            {
                "inst_id": inst_id,
                "payload": dict(payload),
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        or {"_id": inst_id, "model_id": "report_asset", **payload},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_create",
        lambda *args, **kwargs: pytest.fail("in-scope unique hit should update existing instance"),
        raising=False,
    )

    result = InstanceManage.merge_custom_reporting_instances(
        model_id="report_asset",
        instances=[{"identity": {"asset_code": "asset-1"}, "attributes": {}}],
        relations=[],
        identity_keys=["asset_code"],
        operator="custom-reporting-task-1",
        allowed_org_ids=[1],
    )

    assert updated_instances == [
        {
            "inst_id": 502,
            "payload": {"asset_code": "asset-1", "inst_name": "asset-1"},
            "allowed_org_ids": [1],
        }
    ]
    assert result["updated"][0]["after_data"]["_id"] == 502


def test_custom_reporting_ingest_reconciles_pending_relations_idempotently_when_edge_exists(monkeypatch):
    batch = SimpleNamespace(
        pk=96,
        status=CustomReportingBatch.STATUS_RUNNING,
        summary={},
        saved_updates=[],
    )
    deleted_ids = []

    def _save_batch(*, update_fields):
        batch.saved_updates.append(list(update_fields))

    batch.save = _save_batch

    existing_pending_relation = SimpleNamespace(
        id=41,
        relation_payload={
            "source": {"asset_code": "asset-1"},
            "target": {"model_id": "host", "inst_name": "host-1"},
            "relation_type": "asset_depends_on_host",
        },
    )

    class DummyDeleteQuerySet:
        @staticmethod
        def delete():
            deleted_ids.append(41)

    class DummyPendingRelations:
        @staticmethod
        def all():
            return [existing_pending_relation]

        @staticmethod
        def filter(**kwargs):
            assert kwargs == {"id__in": [41]}
            return DummyDeleteQuerySet()

    class DummyTask:
        pk = 15
        team = [1]
        config = {
            "mode": "quick",
            "quick_model": {
                "model_id": "report_asset",
                "identity_keys": ["asset_code"],
            },
        }
        last_reported_at = None
        pending_relations = DummyPendingRelations()

        def save(self, *args, **kwargs):
            return None

    monkeypatch.setattr(
        CustomReportingBatch.objects,
        "create",
        lambda **kwargs: batch,
    )
    monkeypatch.setattr(
        ModelManage,
        "register_custom_reporting_model_fields",
        lambda *args, **kwargs: [],
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_identity",
        lambda model_id, identity: {"_id": 501, "model_id": "report_asset", "asset_code": "asset-1"}
        if model_id == "report_asset"
        else {"_id": 502, "model_id": "host", "inst_name": "host-1"},
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_exists",
        lambda *, src_inst_id, dst_inst_id, model_asst_id: (
            src_inst_id == 501 and dst_inst_id == 502 and model_asst_id == "asset_depends_on_host"
        ),
        raising=False,
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_create",
        lambda *args, **kwargs: pytest.fail("待处理关系重试时已有边不应再次创建"),
        raising=False,
    )
    monkeypatch.setattr("apps.cmdb.services.custom_reporting_ingest_service.transaction.atomic", lambda: nullcontext())

    result = CustomReportingIngestService.ingest(
        DummyTask(),
        {
            "instances": [],
            "relations": [],
            "batch_metadata": {"source": "agent"},
        },
    )

    assert result["accepted"] is True
    assert result["summary"]["pending_relations"] == 0
    assert deleted_ids == [41]


def test_custom_reporting_ingest_deduplicates_unresolved_pending_relations(monkeypatch):
    existing_payload = {
        "source": {"asset_code": "asset-1"},
        "target": {"model_id": "host", "inst_name": "host-1"},
        "relation_type": "asset_depends_on_host",
    }
    persisted_batches = []
    deleted_ids = []

    class DummyDeleteQuerySet:
        @staticmethod
        def delete():
            deleted_ids.append(11)

    class DummyPendingRelations:
        @staticmethod
        def filter(**kwargs):
            assert kwargs == {"id__in": [11]}
            return DummyDeleteQuerySet()

    class FakePendingRelation:
        class objects:
            @staticmethod
            def bulk_create(items):
                persisted_batches.append(
                    [
                        {
                            "source_model_id": item.source_model_id,
                            "target_model_id": item.target_model_id,
                            "relation_payload": dict(item.relation_payload),
                        }
                        for item in items
                    ]
                )

        def __init__(self, task, source_model_id, target_model_id, relation_payload):
            self.task = task
            self.source_model_id = source_model_id
            self.target_model_id = target_model_id
            self.relation_payload = relation_payload

    monkeypatch.setattr("apps.cmdb.services.custom_reporting_ingest_service.transaction.atomic", lambda: nullcontext())
    monkeypatch.setattr(
        "apps.cmdb.enterprise.services.custom_reporting_ingest_service.CustomReportingPendingRelation",
        FakePendingRelation,
    )

    task = SimpleNamespace(pending_relations=DummyPendingRelations())

    CustomReportingIngestService._persist_pending_relations(
        task,
        existing_pending_relation_ids=[11],
        pending_relations=[
            {
                "source_model_id": "report_asset",
                "target_model_id": "host",
                "relation_payload": dict(existing_payload),
            },
            {
                "source_model_id": "report_asset",
                "target_model_id": "host",
                "relation_payload": dict(existing_payload),
            },
        ],
    )

    assert deleted_ids == [11]
    assert persisted_batches == [
        [
            {
                "source_model_id": "report_asset",
                "target_model_id": "host",
                "relation_payload": existing_payload,
            }
        ]
    ]


@pytest.mark.django_db
def test_custom_reporting_task_update_rejects_clearing_standard_mode_binding(superuser):
    current_group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[current_group.id],
        config={"mode": "manual", "model_id": "report_asset", "metrics": ["count"]},
    )

    response = CustomReportingTaskViewSet.as_view({"put": "update"})(
        _req(
            "put",
            superuser,
            data={
                "name": "普通上报",
                "team": [current_group.id],
                "config": {},
            },
            current_team=str(current_group.id),
            include_children="0",
        ),
        pk=task.pk,
    )
    body = _body(response)
    task.refresh_from_db()

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "config.model_id" in json.dumps(body, ensure_ascii=False)
    assert task.config == {"mode": "manual", "model_id": "report_asset", "metrics": ["count"]}
