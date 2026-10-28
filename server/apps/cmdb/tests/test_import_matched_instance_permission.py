"""同步导入命中旧资产时，必须复用普通编辑的实例权限，不能按唯一键直接更新。"""

import io
import json
from types import SimpleNamespace

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import OPERATE
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.Import import Import
from apps.cmdb.views.instance import InstanceViewSet

ORG_A = 10
ORG_B = 20
PERMISSION_DENIED = "抱歉！您没有此实例的权限"
ATTRS = [
    {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
    {"attr_id": "serial", "attr_name": "序列号", "attr_type": "str", "is_only": True, "is_required": True, "editable": True},
    {"attr_id": "remark", "attr_name": "备注", "attr_type": "str", "is_only": False, "editable": True, "option": []},
    {
        "attr_id": "organization",
        "attr_name": "组织",
        "attr_type": "organization",
        "is_only": False,
        "editable": True,
        "option": [],
    },
]
ASSO = {
    "host_conn_sw": {
        "model_asst_id": "host_conn_sw",
        "asst_id": "conn",
        "src_model_id": "host",
        "dst_model_id": "sw",
    }
}


def _asset(inst_name, serial, organization, creator, asset_id):
    return {
        "_id": asset_id,
        "inst_name": inst_name,
        "serial": serial,
        "remark": "old",
        "organization": list(organization),
        "_creator": creator,
        "model_id": "host",
    }


def _excel(rows):
    headers = ["名称", "序列号", "备注", "组织", "关联"]
    types = ["字符串", "字符串", "字符串", "组织", "关联"]
    keys = ["inst_name", "serial", "remark", "organization", "host_conn_sw"]
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "host"
    sheet.append(headers)
    sheet.append(types)
    sheet.append(keys)
    for inst_name, serial, remark, asso in rows:
        sheet.append([inst_name, serial, remark, None, asso])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _upload(rows):
    return SimpleUploadedFile("host.xlsx", _excel(rows))


def _prepare_user(user, groups, *, superuser=False):
    user.is_superuser = superuser
    user.group_list = [{"id": group_id} for group_id in groups]
    user.group_tree = []
    user.permission = {"cmdb": {"asset_info-Add"}}
    return user


def _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names):
    def query_entity(label, params, **kwargs):
        return (list(existing), len(existing))

    def query_entity_by_inst_names(names, model_id=None):
        wanted = set(names or [])
        return [item for item in existing if item.get("inst_name") in wanted]

    fake_graph(
        "apps.cmdb.utils.Import",
        query_entity=query_entity,
        query_entity_by_inst_names=query_entity_by_inst_names,
    )
    monkeypatch.setattr(Import, "get_model_asso_map", lambda self: dict(ASSO))
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda model_id: SimpleNamespace(unique_rules=[], attrs_by_id={}),
    )
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda model_id, *args, **kwargs: ATTRS)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": "主机", "is_visible": True},
    )
    monkeypatch.setattr("apps.cmdb.services.instance.batch_create_change_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.views.instance.InstanceViewSet._get_allowed_org_ids",
        staticmethod(lambda request: [ORG_A, ORG_B]),
    )

    seen = []

    def has_permission(*args, **kwargs):
        instance = kwargs.get("instance")
        seen.append(instance)
        return kwargs.get("operator") == OPERATE and instance.get("inst_name") in operate_names

    monkeypatch.setattr("apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", has_permission)
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {},
    )

    def capture_update(self, rows):
        captured["rows"] = [dict(row) for row in rows]
        created = [
            {"success": True, "data": {**row, "_id": 80 + index, "model_id": "host"}}
            for index, row in enumerate(rows)
        ]
        return created, []

    def capture_asso(self, asso_key_map):
        captured["asso"] = {key: dict(value) for key, value in asso_key_map.items()}

    monkeypatch.setattr(Import, "inst_list_update", capture_update)
    monkeypatch.setattr(Import, "format_import_asso_data", capture_asso)
    monkeypatch.setattr(Import, "add_asso_data", lambda self, asso_key_map: [])
    return seen


def _import_via_view(user, rows, team):
    request = APIRequestFactory().post("/x/", data={"file": _upload(rows)}, format="multipart")
    request.COOKIES["current_team"] = str(team)
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    response = InstanceViewSet.as_view({"post": "inst_import"})(request, model_id="host")
    return json.loads(response.content)


def _names(captured):
    return [row.get("inst_name") for row in captured.get("rows", [])]


@pytest.mark.django_db
def test_cross_org_match_is_denied_and_new_row_stays_creatable(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A])
    existing = [_asset("asset-b", "SN-B", [ORG_B], "owner-b", 11)]
    captured = {}
    _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names=set())

    body = _import_via_view(
        user,
        [
            ("asset-b", "SN-B", "changed", "sw-b"),
            ("new-host", "SN-NEW", "fresh", "sw-new"),
        ],
        ORG_A,
    )

    assert _names(captured) == ["new-host"], body
    assert PERMISSION_DENIED in body["message"]
    assert "asset-b" not in captured["asso"].get("host_conn_sw", {})
    assert captured["asso"]["host_conn_sw"]["new-host"] == ["sw-new"]


@pytest.mark.django_db
def test_same_org_without_operate_is_denied(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A])
    existing = [_asset("asset-a", "SN-A", [ORG_A], "owner-a", 12)]
    captured = {}
    seen = _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names=set())

    body = _import_via_view(user, [("asset-a", "SN-A", "changed", "")], ORG_A)

    assert _names(captured) == [], body
    assert PERMISSION_DENIED in body["message"]
    assert seen and seen[0]["organization"] == [ORG_A]
    assert seen[0]["_creator"] == "owner-a"


@pytest.mark.django_db
def test_creator_in_current_org_can_update(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A])
    existing = [_asset("asset-a", "SN-A", [ORG_A], user.username, 12)]
    captured = {}
    _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names=set())

    body = _import_via_view(user, [("asset-a", "SN-A", "changed", "")], ORG_A)

    assert _names(captured) == ["asset-a"], body
    assert body["result"] is True
    assert captured["rows"][0]["remark"] == "changed"


@pytest.mark.django_db
def test_operate_on_old_organization_can_update_when_excel_org_is_blank(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A, ORG_B])
    existing = [_asset("asset-b", "SN-B", [ORG_B], "owner-b", 11)]
    captured = {}
    seen = _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names={"asset-b"})

    body = _import_via_view(user, [("asset-b", "SN-B", "changed", "sw-b")], ORG_A)

    assert _names(captured) == ["asset-b"], body
    assert body["result"] is True
    assert seen and seen[0]["organization"] == [ORG_B]
    assert "organization" not in captured["rows"][0]


@pytest.mark.django_db
def test_superuser_flag_without_creator_or_operate_is_denied(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A], superuser=True)
    existing = [_asset("asset-b", "SN-B", [ORG_B], "owner-b", 11)]
    captured = {}
    _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names=set())

    body = _import_via_view(user, [("asset-b", "SN-B", "changed", "")], ORG_A)

    assert _names(captured) == [], body
    assert PERMISSION_DENIED in body["message"]


@pytest.mark.django_db
def test_superuser_creator_in_current_org_can_update(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_A], superuser=True)
    existing = [_asset("asset-a", "SN-A", [ORG_A], user.username, 12)]
    captured = {}
    _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names=set())

    body = _import_via_view(user, [("asset-a", "SN-A", "changed", "")], ORG_A)

    assert _names(captured) == ["asset-a"], body
    assert body["result"] is True


@pytest.mark.django_db
def test_superuser_with_operate_on_old_organization_can_update(authenticated_user, monkeypatch, fake_graph):
    user = _prepare_user(authenticated_user, [ORG_B], superuser=True)
    existing = [_asset("asset-b", "SN-B", [ORG_B], "owner-b", 11)]
    captured = {}
    seen = _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names={"asset-b"})

    body = _import_via_view(user, [("asset-b", "SN-B", "changed", "")], ORG_A)

    assert _names(captured) == ["asset-b"], body
    assert body["result"] is True
    assert seen and seen[0]["organization"] == [ORG_B]


@pytest.mark.django_db
def test_missing_permission_check_rejects_every_matched_row(monkeypatch, fake_graph):
    existing = [_asset("asset-b", "SN-B", [ORG_B], "owner-b", 11)]
    captured = {}
    _install_import_fakes(monkeypatch, fake_graph, existing, captured, operate_names={"asset-b"})
    importer = Import("host", ATTRS, [], "testuser")

    add_results, update_results, _asso = importer.import_inst_list_support_edit(
        io.BytesIO(
            _excel(
                [
                    ("asset-b", "SN-B", "changed", "sw-b"),
                    ("new-host", "SN-NEW", "fresh", "sw-new"),
                ]
            )
        )
    )

    assert _names(captured) == ["new-host"]
    assert any(item.get("success") is False and PERMISSION_DENIED in item.get("message", "") for item in update_results)
    assert "asset-b" not in captured["asso"].get("host_conn_sw", {})
    assert all(item.get("data", {}).get("inst_name") != "asset-b" for item in add_results)
