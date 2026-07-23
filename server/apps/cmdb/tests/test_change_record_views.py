"""CMDB 变更记录视图覆盖测试（真实 ChangeRecord DB）。

对照 specs/capabilities/legacy-prd-cmdb-操作日志.md：变更记录列表/详情、变更类型与场景枚举、按过滤条件导出 Excel。
"""

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.change_record import CUSTOM_REPORTING_CHANGE, ChangeRecord
from apps.cmdb.utils import change_record as change_record_utils
from apps.cmdb.views.change_record import ChangeRecordViewSet


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.locale = "zh-Hans"
    return u


@pytest.fixture
def record(db):
    return ChangeRecord.objects.create(
        inst_id=1, model_id="host", label="主机", type="create_entity",
        operator="admin", model_object="主机", message="创建实例",
        before_data={}, after_data={"inst_name": "h1"}, scenario="ordinary_attribute_change",
    )


def _req(method, user, query=""):
    factory = APIRequestFactory()
    path = "/x/" + (f"?{query}" if query else "")
    request = getattr(factory, method)(path)
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.mark.django_db
def test_list(superuser, record):
    response = ChangeRecordViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert response.status_code == 200


@pytest.mark.django_db
def test_retrieve(superuser, record):
    response = ChangeRecordViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=record.id)
    assert response.status_code == 200
    assert _body(response)["data"]["model_id"] == "host"


@pytest.mark.django_db
def test_enum_data(superuser):
    response = ChangeRecordViewSet.as_view({"get": "enum_data"})(_req("get", superuser))
    body = _body(response)
    assert "create_entity" in body["data"]


@pytest.mark.django_db
def test_enum_scenarios(superuser):
    response = ChangeRecordViewSet.as_view({"get": "enum_scenarios"})(_req("get", superuser))
    body = _body(response)
    assert "ordinary_attribute_change" in body["data"]
    assert CUSTOM_REPORTING_CHANGE in body["data"]


@pytest.mark.django_db
def test_export(superuser, record):
    response = ChangeRecordViewSet.as_view({"get": "export"})(_req("get", superuser))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    assert b"PK" == response.content[:2]  # xlsx 是 zip 容器


@pytest.mark.django_db
def test_custom_reporting_change_record_helper_writes_custom_scenario():
    assert hasattr(change_record_utils, "create_custom_reporting_change_record")

    change_record_utils.create_custom_reporting_change_record(
        inst_id=99,
        model_id="report_asset",
        label="主机",
        _type="update_entity",
        after_data={"inst_name": "asset-99"},
        operator="custom-reporting-task-1",
        message="自定义上报更新",
    )

    record = ChangeRecord.objects.get(inst_id=99, model_id="report_asset")
    assert record.scenario == CUSTOM_REPORTING_CHANGE
