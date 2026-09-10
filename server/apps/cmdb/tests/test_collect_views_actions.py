"""CollectModelViewSet / OidModelViewSet 视图动作单元测试。

对照 apps/cmdb/views/collect.py：
  - 静态辅助 _parse_positive_int / apply_visibility_filter
  - collect_task_names / model_instances / task_status / task_overview 聚合
  - nodes / list_regions（NodeMgmt 边界打桩）
  - model_doc 路径校验与读取
  - info 详情
  - OidModelViewSet create 的 oid 空白与重复校验

视图测试经 DRF as_view 完整 dispatch（force_authenticate + superuser 绕过 HasPermission）；
service / NodeMgmt / 权限规则在真实边界打桩，断言真实 JSON 响应与 DB 副作用。
"""
import json
import logging

import pydantic.root_model  # noqa: F401
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig
from apps.cmdb.views.collect import CollectModelViewSet, OidModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.roles = ["admin"]
    u.domain = "domain.com"
    return u


def _req(method, user, data=None, query=None, **cookies):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/"
    if query:
        path = "/x/?" + "&".join(f"{k}={v}" for k, v in query.items())
    request = fn(path) if data is None else fn(path, data=data, format="json")
    for k, v in cookies.items():
        request.COOKIES[k] = v
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _bypass_permission(monkeypatch):
    # 让 get_queryset_by_permission 与 AuthSerializer 退化为不裁剪（base_queryset）
    monkeypatch.setattr("apps.cmdb.views.collect.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr("apps.core.utils.permission_utils.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr(
        CollectModelViewSet,
        "get_queryset_by_permission",
        lambda self, request, queryset, permission_key=None: queryset,
    )


def _system_collect_task():
    return CollectModels.objects.create(
        name="节点管理系统采集",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        is_system=True,
        is_visible=False,
        system_code="node_mgmt_region_1",
    )


# --------------------------------------------------------------------------
# _parse_positive_int（纯静态）
# --------------------------------------------------------------------------
def test_parse_positive_int_default_on_empty():
    assert CollectModelViewSet._parse_positive_int("", "page", 1) == 1
    assert CollectModelViewSet._parse_positive_int(None, "page", 5) == 5


def test_parse_positive_int_valid():
    assert CollectModelViewSet._parse_positive_int("3", "page", 1) == 3


def test_parse_positive_int_non_integer_raises():
    with pytest.raises(ValueError, match="必须是整数"):
        CollectModelViewSet._parse_positive_int("abc", "page", 1)


def test_parse_positive_int_below_one_raises():
    with pytest.raises(ValueError, match="必须大于等于 1"):
        CollectModelViewSet._parse_positive_int("0", "page", 1)


# --------------------------------------------------------------------------
# apply_visibility_filter
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_apply_visibility_filter_excludes_hidden():
    CollectModels.objects.create(name="vis", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", is_visible=True, team=[1])
    CollectModels.objects.create(
        name="hid", task_type=CollectPluginTypes.HOST, model_id="host", driver_type="snmp", cycle_value_type="cycle", is_visible=False, team=[1]
    )
    qs = CollectModelViewSet.apply_visibility_filter(CollectModels.objects.all())
    names = sorted(qs.values_list("name", flat=True))
    assert names == ["vis"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "data"),
    [
        ("get", "retrieve", None),
        ("put", "update", {}),
        ("delete", "destroy", None),
        ("post", "exec_task", {}),
    ],
)
def test_regular_detail_actions_cannot_access_node_mgmt_system_task(superuser, monkeypatch, mocker, method, action, data):
    _bypass_permission(monkeypatch)
    task = _system_collect_task()
    submit = mocker.patch("apps.cmdb.views.collect.CollectModelService.exec_task")

    request = _req(method, superuser, data=data, current_team="1")
    response = CollectModelViewSet.as_view({method: action})(request, pk=task.id)

    assert response.status_code == 404
    assert CollectModels.objects.filter(pk=task.pk).exists()
    submit.assert_not_called()


@pytest.mark.django_db
def test_disabled_auto_collect_cannot_be_bypassed_through_regular_exec_endpoint(superuser, monkeypatch, mocker):
    _bypass_permission(monkeypatch)
    NodeMgmtSyncConfig.objects.create(auto_collect_enabled=False)
    task = _system_collect_task()
    submit = mocker.patch("apps.cmdb.views.collect.CollectModelService.exec_task")

    request = _req("post", superuser, data={}, current_team="1")
    response = CollectModelViewSet.as_view({"post": "exec_task"})(request, pk=task.id)

    assert response.status_code == 404
    submit.assert_not_called()


# --------------------------------------------------------------------------
# model_doc
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_model_doc_empty_id(superuser):
    request = _req("get", superuser, query={"id": ""})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "不能为空" in body["message"]


@pytest.mark.django_db
def test_model_doc_illegal_id(superuser):
    request = _req("get", superuser, query={"id": "abc.def"})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "非法" in body["message"]


@pytest.mark.django_db
def test_model_doc_not_found_returns_placeholder(superuser):
    request = _req("get", superuser, query={"id": "definitely_missing_doc_xyz"})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"] == "未找到对应的文档！"


@pytest.mark.django_db
def test_model_doc_pc_returns_operator_guide(superuser):
    request = _req("get", superuser, query={"id": "pc"})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)

    assert body["result"] is True
    assert "Windows" in body["data"]
    assert "macOS" in body["data"]
    assert "同步最新结果" in body["data"]
    assert "安装软件" in body["data"]
    assert "WinRM" in body["data"]
    assert "SSH" in body["data"]


# --------------------------------------------------------------------------
# nodes（NodeMgmt 打桩）
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_nodes_invalid_page(superuser):
    request = _req("get", superuser, query={"page": "abc"})
    resp = CollectModelViewSet.as_view({"get": "nodes"})(request)
    body = _body(resp)
    assert body["result"] is False


@pytest.mark.django_db
def test_nodes_success(superuser, monkeypatch):
    request = _req("get", superuser, query={"page": "1", "page_size": "10"}, current_team="1")
    captured_query = {}

    def fake_node_list(self, query_data):
        captured_query.update(query_data)
        return {"count": 1, "nodes": [{"id": "n1"}]}

    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.node_list", fake_node_list)
    resp = CollectModelViewSet.as_view({"get": "nodes"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"]["count"] == 1
    assert captured_query["is_container"] is True
    assert "node_type" not in captured_query


# --------------------------------------------------------------------------
# list_regions
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_list_regions_unknown_cloud_id(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    request = _req("post", superuser, data={"cloud_id": "unknown", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "cloud_id 不存在" in body["message"]


@pytest.mark.django_db
def test_list_regions_success(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    monkeypatch.setattr(CollectModelViewSet, "_build_region_query_credential", lambda self, req, params, task_id=None: {"k": "v"})
    monkeypatch.setattr(
        "apps.cmdb.views.collect.CollectModelService.list_regions",
        lambda credential, cloud_name: {"success": True, "result": [{"region": "cn-north"}]},
    )
    request = _req("post", superuser, data={"cloud_id": "aws", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"][0]["region"] == "cn-north"


@pytest.mark.django_db
def test_list_regions_service_failure(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    monkeypatch.setattr(CollectModelViewSet, "_build_region_query_credential", lambda self, req, params, task_id=None: {})
    monkeypatch.setattr(
        "apps.cmdb.views.collect.CollectModelService.list_regions",
        lambda credential, cloud_name: {"success": False, "message": "鉴权失败"},
    )
    request = _req("post", superuser, data={"cloud_id": "aws", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert body["message"] == "鉴权失败"


def _create_cloud_collect_task(model_id, access_key):
    return CollectModels.objects.create(
        name="ssss",
        task_type=CollectPluginTypes.CLOUD,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id=model_id,
        cycle_value_type="cycle",
        cycle_value="10",
        team=[1],
        access_point=[{"id": "fusion-collector-default", "cloud_region": "fusion-collector-default"}],
        instances=[{"endpoint": "cvm.tencentcloudapi.com"}],
        credential=[
            {
                "credential_id": "cred_edit",
                "accessKey": access_key,
                "accessSecret": "sk-real",
                "regions": {"resource_id": "ap-guangzhou", "resource_name": "华南地区(广州)"},
            }
        ],
        timeout=60,
        params={},
    )


def _capture_list_regions(monkeypatch, cloud_id="fusion-collector-default"):
    captured = {}
    monkeypatch.setattr(
        "apps.cmdb.views.collect.NodeMgmt.cloud_region_list",
        lambda self: [{"id": cloud_id, "name": "tencent"}],
    )

    def fake_list_regions(credential, cloud_name):
        captured["credential"] = credential
        captured["cloud_name"] = cloud_name
        if not credential.get("secret_id"):
            return {
                "success": False,
                "message": "[TencentCloudSDKException] code:InvalidCredential message:secret id should not be none or empty requestId:None",
            }
        return {"success": True, "result": [{"resource_id": "ap-guangzhou", "resource_name": "广州"}]}

    monkeypatch.setattr("apps.cmdb.views.collect.CollectModelService.list_regions", fake_list_regions)
    return captured


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model_id,access_key",
    [
        ("qcloud", "AKIDreal"),
        ("aliyun_account", "LTAIreal"),
    ],
)
def test_edit_list_regions_reuses_stored_secrets_instead_of_mask(model_id, access_key, superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _create_cloud_collect_task(model_id, access_key)
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": model_id,
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == access_key
    assert captured["credential"]["secret_key"] == "sk-real"
    assert captured["credential"].get("access_key") != "******"


@pytest.mark.django_db
def test_list_regions_saved_task_without_secrets_asks_user_to_refill(superuser, monkeypatch, caplog):
    _bypass_permission(monkeypatch)
    task = CollectModels.objects.create(
        name="ssss-empty",
        task_type=CollectPluginTypes.CLOUD,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="qcloud",
        cycle_value_type="cycle",
        cycle_value="10",
        team=[1],
        access_point=[{"id": "fusion-collector-default", "cloud_region": "fusion-collector-default"}],
        instances=[{"endpoint": "cvm.tencentcloudapi.com"}],
        credential=[
            {
                "credential_id": "cred_edit",
                "credential_version": 2,
                "regions": {"resource_id": "ap-guangzhou", "resource_name": "华南地区(广州)"},
            }
        ],
        timeout=60,
        params={},
    )
    captured = _capture_list_regions(monkeypatch)
    caplog.set_level(logging.INFO, logger="cmdb")
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert body.get("message") == "已保存任务中没有可用的云访问密钥，请重新填写 SecretId 和 SecretKey"
    assert "credential" not in captured
    records = [record for record in caplog.records if record.name == "cmdb" and record.msg.startswith("event=list_regions_missing_secret")]
    assert len(records) == 1
    record = records[0]
    template = "event=list_regions_missing_secret model_id=%s has_task_id=%s request_fields=%s"
    args = ("qcloud", True, "cloud_id,model_id")
    assert record.levelno == logging.INFO
    assert record.msg == template
    assert record.args == args
    assert record.getMessage() == template % args
    assert "AKIDreal" not in record.getMessage()
    assert "sk-real" not in record.getMessage()


@pytest.mark.django_db
def test_list_regions_without_task_or_keys_does_not_call_cloud_sdk(superuser, monkeypatch, caplog):
    captured = _capture_list_regions(monkeypatch)
    caplog.set_level(logging.INFO, logger="cmdb")
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "secret id should not be none or empty" not in (body.get("message") or "")
    assert body.get("message") == "缺少云访问密钥，请重新填写或打开已保存的任务后再刷新区域"
    assert "credential" not in captured
    records = [record for record in caplog.records if record.name == "cmdb" and record.msg.startswith("event=list_regions_missing_secret")]
    assert len(records) == 1
    record = records[0]
    template = "event=list_regions_missing_secret model_id=%s has_task_id=%s request_fields=%s"
    args = ("qcloud", False, "cloud_id,model_id")
    assert record.levelno == logging.INFO
    assert record.msg == template
    assert record.args == args
    assert record.getMessage() == template % args


@pytest.mark.django_db
def test_list_regions_rejects_masked_secrets_without_task(superuser, monkeypatch):
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "access_key": "******",
            "access_secret": "******",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "secret id should not be none or empty" not in (body.get("message") or "")
    assert "credential" not in captured


@pytest.mark.django_db
def test_list_regions_uses_page_secrets_when_user_changes_them(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    _create_cloud_collect_task("qcloud", "AKIDstored")
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "access_key": "AKIDchanged",
            "access_secret": "sk-changed",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == "AKIDchanged"
    assert captured["credential"]["secret_key"] == "sk-changed"


@pytest.mark.django_db
def test_list_regions_empty_keys_with_task_id_reuse_stored_secrets(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _create_cloud_collect_task("qcloud", "AKIDreal")
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
            "access_key": "",
            "access_secret": "",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == "AKIDreal"
    assert captured["credential"]["secret_key"] == "sk-real"


@pytest.mark.django_db
def test_list_regions_masks_with_task_id_reuse_stored_secrets(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _create_cloud_collect_task("qcloud", "AKIDreal")
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
            "access_key": "******",
            "access_secret": "******",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == "AKIDreal"
    assert captured["credential"]["secret_key"] == "sk-real"


@pytest.mark.django_db
def test_list_regions_decrypts_encrypted_db_secrets_before_calling_cloud(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _create_cloud_collect_task("qcloud", "AKIDreal")
    encrypted_credential = [
        {
            **task.credential[0],
            "accessKey": CollectModels.encrypt_password("AKIDreal"),
            "accessSecret": CollectModels.encrypt_password("sk-real"),
        }
    ]
    CollectModels.objects.filter(pk=task.id).update(credential=encrypted_credential)
    task.refresh_from_db()
    assert task.credential[0]["accessKey"].startswith("enc:")
    assert task.credential[0]["accessSecret"].startswith("enc:")

    monkeypatch.setattr(
        "apps.cmdb.models.collect_model.get_collect_model_passwords",
        lambda *args, **kwargs: [],
    )
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == "AKIDreal"
    assert captured["credential"]["secret_key"] == "sk-real"
    assert not str(captured["credential"]["secret_id"]).startswith("enc:")
    assert not str(captured["credential"]["secret_key"]).startswith("enc:")


@pytest.mark.django_db
def test_list_regions_prefers_page_secrets_when_task_id_and_keys_are_both_sent(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _create_cloud_collect_task("qcloud", "AKIDstored")
    captured = _capture_list_regions(monkeypatch)
    request = _req(
        "post",
        superuser,
        data={
            "model_id": "qcloud",
            "cloud_id": "fusion-collector-default",
            "task_id": task.id,
            "access_key": "AKIDchanged",
            "access_secret": "sk-changed",
        },
    )
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True, body
    assert captured["credential"]["secret_id"] == "AKIDchanged"
    assert captured["credential"]["secret_key"] == "sk-changed"


# --------------------------------------------------------------------------
# task_status / task_overview / model_instances / collect_task_names
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_status_aggregates_by_status(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(
        name="t1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", exec_status=CollectRunStatusType.SUCCESS, team=[1]
    )
    CollectModels.objects.create(
        name="t2",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.ERROR,
        team=[1],
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "task_status"})(request)
    body = _body(resp)
    assert body["result"] is True
    # driver_type 默认为 "protocol"（非空），故 key 形如 "<model_id>__<driver_type>"
    assert body["data"]["host__protocol"]["success"] == 1
    assert body["data"]["host__snmp"]["failed"] == 1


@pytest.mark.django_db
def test_task_overview_counts(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(
        name="o1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", exec_status=CollectRunStatusType.SUCCESS, team=[1]
    )
    CollectModels.objects.create(
        name="o2",
        task_type=CollectPluginTypes.HOST,
        model_id="switch",
        driver_type="snmp",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.ERROR,
        team=[1],
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "task_overview"})(request)
    body = _body(resp)["data"]
    assert body["total"] == 2
    assert body["normal"] == 1
    assert body["error"] == 1
    assert body["covered_models"] == 2


@pytest.mark.django_db
def test_model_instances_skips_legacy_targets_without_inst_uuid(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(
        name="mi1",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "h1", "inst_name": "10.0.0.1"}],
    )
    CollectModels.objects.create(
        name="mi-empty",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="x",
        cycle_value_type="cycle",
        team=[1],
        instances=[],
    )
    request = _req("get", superuser, query={"task_type": CollectPluginTypes.HOST}, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "model_instances"})(request)
    body = _body(resp)["data"]
    assert body == []


@pytest.mark.django_db
def test_model_instances_prefers_inst_uuid(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    CollectModels.objects.create(
        name="mi-uuid",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": 7, "inst_uuid": inst_uuid, "inst_name": "10.0.0.1"}],
    )
    request = _req("get", superuser, query={"task_type": CollectPluginTypes.HOST}, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "model_instances"})(request)
    body = _body(resp)["data"]
    assert body == [{"id": inst_uuid, "inst_name": "10.0.0.1"}]


@pytest.mark.django_db
def test_collect_task_names_includes_plugin_meta(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(name="ctn", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", team=[1], is_visible=True)
    monkeypatch.setattr(
        "apps.cmdb.views.collect.get_collect_obj_tree",
        lambda: [{"id": "compute", "name": "计算", "children": [{"id": "host", "name": "主机"}]}],
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "collect_task_names"})(request)
    body = _body(resp)["data"]
    assert len(body) == 1
    assert body[0]["plugin"] == "host"
    assert body[0]["category"] == "compute"
    assert body[0]["plugin_name"] == "主机"


@pytest.mark.django_db
def test_collect_task_names_distinguishes_physical_server_protocol_plugins(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(
        name="ssh",
        task_type=CollectPluginTypes.HOST,
        driver_type="job",
        model_id="physcial_server",
        cycle_value_type="cycle",
        team=[1],
        is_visible=True,
        params={},
    )
    common = {
        "task_type": CollectPluginTypes.PROTOCOL,
        "driver_type": "protocol",
        "model_id": "physcial_server",
        "cycle_value_type": "cycle",
        "team": [1],
        "is_visible": True,
    }
    CollectModels.objects.create(name="legacy-ipmi", params={}, **common)
    CollectModels.objects.create(name="redfish", params={"collection_protocol": "redfish"}, **common)
    monkeypatch.setattr(
        "apps.cmdb.views.collect.get_collect_obj_tree",
        lambda: [
            {
                "id": "host_manage",
                "name": "主机物理主机",
                "children": [
                    {"id": "physcial_server", "name": "物理服务器 SSH"},
                    {"id": "physcial_server_ipmi", "name": "物理服务器 IPMI"},
                    {"id": "physcial_server_redfish", "name": "物理服务器 Redfish"},
                ],
            }
        ],
    )
    request = _req("get", superuser, current_team="1")

    response = CollectModelViewSet.as_view({"get": "collect_task_names"})(request)

    by_name = {item["name"]: item for item in _body(response)["data"]}
    assert by_name["ssh"]["plugin"] == "physcial_server"
    assert by_name["ssh"]["plugin_name"] == "物理服务器 SSH"
    assert by_name["legacy-ipmi"]["plugin"] == "physcial_server_ipmi"
    assert by_name["legacy-ipmi"]["plugin_name"] == "物理服务器 IPMI"
    assert by_name["redfish"]["plugin"] == "physcial_server_redfish"
    assert by_name["redfish"]["plugin_name"] == "物理服务器 Redfish"


@pytest.mark.django_db
def test_tree_returns_obj_tree(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.get_collect_obj_tree", lambda: [{"id": "a"}])
    request = _req("get", superuser)
    resp = CollectModelViewSet.as_view({"get": "tree"})(request)
    assert _body(resp)["data"] == [{"id": "a"}]


@pytest.mark.django_db
def test_info_returns_instance_info(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = CollectModels.objects.create(
        name="info1",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        format_data={"add": [{"x": 1}], "update": [], "delete": [], "association": [], "__raw_data__": []},
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "info"})(request, pk=task.id)
    body = _body(resp)["data"]
    assert body["add"]["count"] == 1


# --------------------------------------------------------------------------
# OidModelViewSet 校验
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_oid_create_empty_oid(superuser):
    request = _req("post", superuser, data={"oid": "   "})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "不能为空" in body["message"]


@pytest.mark.django_db
def test_oid_create_with_whitespace_rejected(superuser):
    request = _req("post", superuser, data={"oid": " 1.3.6 "})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "首尾空格" in body["message"]


@pytest.mark.django_db
def test_oid_create_duplicate(superuser):
    # 同一 OID 的 POST 被拒绝；用户覆盖只能走 UPDATE 并把 built_in 设为 False。
    OidMapping.objects.create(oid="1.3.6.1", device_type="switch")
    request = _req("post", superuser, data={"oid": "1.3.6.1"})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "OID已存在" in body["message"]
