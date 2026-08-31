"""告警源视图集覆盖测试。

对照当前集成页面契约：告警源只读查询、对接指引、组织密钥管理、事件统计。
"""

import json
import subprocess
from pathlib import Path

import pytest
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level
from apps.alerts.views.alert_source import AlertSourceModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture
def permission_user(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {}
    return authenticated_user


@pytest.fixture
def event_level(db):
    Level.objects.create(level_id=3, level_name="Info", level_display_name="信息", level_type="event")


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _make_source(source_id="s1", source_type="restful", **over):
    defaults = dict(name="源1", source_id=source_id, source_type=source_type, secret="src-secret")
    defaults.update(over)
    return AlertSource.objects.create(**defaults)


# --------------------------------------------------------------------------
# read-only interface and permissions
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_alert_source_list(superuser):
    _make_source(
        "s1",
        config={"url": "/receiver", "auth": {"token": "CONFIG-TOKEN-SENTINEL"}},
        team_secrets={"1": "TEAM-SECRET-SENTINEL"},
    )
    _make_source("s2")
    request = _request("get", "/alert_source/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 2
    assert all("config" not in item for item in items)
    assert "CONFIG-TOKEN-SENTINEL" not in json.dumps(payload)
    assert "TEAM-SECRET-SENTINEL" not in json.dumps(payload)


@pytest.mark.django_db
def test_alert_source_retrieve(superuser):
    src = _make_source(
        "s1",
        secret="SOURCE-SECRET-SENTINEL",
        team_secrets={"1": "TEAM-SECRET-SENTINEL"},
        config={
            "url": "/receiver",
            "method": "POST",
            "auth": {"password": "CONFIG-PASSWORD-SENTINEL"},
            "headers": {"SECRET": "SOURCE-SECRET-SENTINEL", "Content-Type": "application/json"},
            "examples": {"CURL": "curl -H 'SECRET: SOURCE-SECRET-SENTINEL'"},
        },
    )
    request = _request("get", f"/alert_source/{src.id}/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(request, pk=str(src.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["source_id"] == "s1"
    assert payload["data"]["config"]["headers"] == {"Content-Type": "application/json"}
    assert "{{TEAM_SECRET}}" in payload["data"]["config"]["examples"]["CURL"]
    serialized = json.dumps(payload)
    assert "SOURCE-SECRET-SENTINEL" not in serialized
    assert "TEAM-SECRET-SENTINEL" not in serialized
    assert "CONFIG-PASSWORD-SENTINEL" not in serialized


@pytest.mark.django_db
def test_alert_source_integration_guide(superuser, event_level):
    src = _make_source("s1", source_type="zabbix", secret="SOURCE-SECRET-SENTINEL")
    request = _request("get", f"/alert_source/{src.id}/integration-guide/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(request, pk=str(src.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["source_id"] == "s1"
    assert payload["data"]["headers"]["SECRET"] == "{{TEAM_SECRET}}"
    assert "SOURCE-SECRET-SENTINEL" not in json.dumps(payload)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "permission",
    [
        "Integration-View",
        "Alarms-View",
        "alert_assign-View",
        "shield_strategy-View",
        "alert_enrichment-View",
        "correlation_rules-View",
        "action_rules-View",
    ],
)
def test_alert_source_options_allow_cross_page_view_without_exposing_config(permission_user, permission):
    _make_source("s1", config={"auth": {"token": "CONFIG-TOKEN-SENTINEL"}})
    permission_user.permission = {"alarm": {permission}}

    response = AlertSourceModelViewSet.as_view({"get": "options"})(_request("get", "/alert_source/options/", permission_user))
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert items == [{"id": items[0]["id"], "name": "源1", "source_id": "s1", "source_type": "restful"}]
    assert "CONFIG-TOKEN-SENTINEL" not in json.dumps(payload)


@pytest.mark.django_db
def test_alert_source_options_reject_user_without_calling_page_permission(permission_user):
    _make_source("s1")
    response = AlertSourceModelViewSet.as_view({"get": "options"})(_request("get", "/alert_source/options/", permission_user))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_api_token_permission_context_uses_same_alert_source_matrix(permission_user):
    src = _make_source("s1")
    permission_user.permission = {"alarm": {"Alarms-View"}}
    options_request = _request("get", "/alert_source/options/", permission_user)
    options_request.api_pass = True
    detail_request = _request("get", f"/alert_source/{src.id}/", permission_user)
    detail_request.api_pass = True

    options_response = AlertSourceModelViewSet.as_view({"get": "options"})(options_request)
    detail_response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(detail_request, pk=str(src.id))

    assert options_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_integration_view_only_allows_overview_queries(permission_user, event_level):
    src = _make_source("s1", source_type="zabbix")
    permission_user.permission = {"alarm": {"Integration-View"}}

    list_response = AlertSourceModelViewSet.as_view({"get": "list"})(_request("get", "/alert_source/", permission_user))
    stats_response = AlertSourceModelViewSet.as_view({"get": "daily_event_stats"})(
        _request("get", "/alert_source/daily_event_stats/", permission_user)
    )
    retrieve_response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(
        _request("get", f"/alert_source/{src.id}/", permission_user),
        pk=str(src.id),
    )
    guide_response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(
        _request("get", f"/alert_source/{src.id}/integration-guide/", permission_user),
        pk=str(src.id),
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert stats_response.status_code == status.HTTP_200_OK
    assert retrieve_response.status_code == status.HTTP_403_FORBIDDEN
    assert guide_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_integration_detail_allows_detail_and_guide(permission_user, event_level):
    src = _make_source("s1", source_type="zabbix")
    permission_user.permission = {"alarm": {"Integration-Detail"}}

    retrieve_response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(
        _request("get", f"/alert_source/{src.id}/", permission_user),
        pk=str(src.id),
    )
    guide_response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(
        _request("get", f"/alert_source/{src.id}/integration-guide/", permission_user),
        pk=str(src.id),
    )

    assert retrieve_response.status_code == status.HTTP_200_OK
    assert guide_response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "path", "kwargs"),
    [
        ("get", "list", "/alert_source/", {}),
        ("get", "retrieve", "/alert_source/{id}/", {"pk": "{id}"}),
        ("get", "integration_guide", "/alert_source/{id}/integration-guide/", {"pk": "{id}"}),
        ("get", "daily_event_stats", "/alert_source/daily_event_stats/", {}),
    ],
)
def test_alert_source_queries_reject_user_without_integration_permission(
    permission_user,
    event_level,
    method,
    action,
    path,
    kwargs,
):
    src = _make_source("s1", source_type="zabbix")
    path = path.format(id=src.id)
    kwargs = {key: value.format(id=src.id) for key, value in kwargs.items()}
    response = AlertSourceModelViewSet.as_view({method: action})(
        _request(method, path, permission_user),
        **kwargs,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "path", "data", "kwargs"),
    [
        ("get", "k8s_meta", "/alert_source/k8s_meta/", None, {}),
        ("post", "snmp_trap_nodes", "/alert_source/snmp_trap_nodes/", {"page": 1}, {}),
        ("post", "k8s_render", "/alert_source/k8s_render/", {}, {}),
        ("post", "k8s_install_command", "/alert_source/k8s_install_command/", {}, {}),
        (
            "post",
            "k8s_download",
            "/alert_source/k8s_download/deploy_yaml/",
            {},
            {"file_key": "deploy_yaml"},
        ),
    ],
)
def test_integration_view_cannot_call_detail_guide_actions(
    permission_user,
    method,
    action,
    path,
    data,
    kwargs,
):
    permission_user.permission = {"alarm": {"Integration-View"}}
    response = AlertSourceModelViewSet.as_view({method: action})(
        _request(method, path, permission_user, data=data),
        **kwargs,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("post", "/alert_source/", {"name": "new", "source_id": "new", "source_type": "restful"}),
        ("put", "/alert_source/{id}/", {"name": "updated"}),
        ("patch", "/alert_source/{id}/", {"name": "patched"}),
        ("delete", "/alert_source/{id}/", None),
    ],
)
def test_alert_source_default_write_methods_are_not_exposed(superuser, method, path, data):
    src = _make_source("s1")
    path = f"/api/v1/alerts/api{path.format(id=src.id)}"
    client = APIClient()
    client.force_authenticate(user=superuser)
    request_method = getattr(client, method)
    response = request_method(path) if data is None else request_method(path, data=data, format="json")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert not AlertSource.objects.filter(source_id="new").exists()
    src.refresh_from_db()
    assert src.name == "源1"


# --------------------------------------------------------------------------
# team_secrets actions
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_team_secret_add_list_remove(superuser):
    src = _make_source("s1")

    # add
    req_add = _request("post", f"/alert_source/{src.id}/team_secrets/add/", superuser, data={"team_id": 5})
    resp_add = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(req_add, pk=str(src.id))
    payload_add = _render(resp_add)
    assert resp_add.status_code == status.HTTP_200_OK
    assert payload_add["data"]["team_id"] == "5"

    # list
    req_list = _request("get", f"/alert_source/{src.id}/team_secrets/", superuser)
    resp_list = AlertSourceModelViewSet.as_view({"get": "list_team_secrets"})(req_list, pk=str(src.id))
    payload_list = _render(resp_list)
    assert len(payload_list["data"]) == 1
    assert payload_list["data"][0] == {"team_id": "5", "team_name": "", "has_secret": True}
    assert payload_add["data"]["secret"] not in json.dumps(payload_list)

    # remove
    req_rm = _request("post", f"/alert_source/{src.id}/team_secrets/remove/", superuser, data={"team_id": 5})
    resp_rm = AlertSourceModelViewSet.as_view({"post": "remove_team_secret"})(req_rm, pk=str(src.id))
    _render(resp_rm)
    assert resp_rm.status_code == status.HTTP_200_OK
    src.refresh_from_db()
    assert src.team_secrets == {}


@pytest.mark.django_db
def test_integration_detail_allows_team_secret_operations(permission_user):
    src = _make_source("s1")
    permission_user.permission = {"alarm": {"Integration-Detail"}}

    add_response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(
        _request("post", f"/alert_source/{src.id}/team_secrets/add/", permission_user, data={"team_id": 1}),
        pk=str(src.id),
    )
    list_response = AlertSourceModelViewSet.as_view({"get": "list_team_secrets"})(
        _request("get", f"/alert_source/{src.id}/team_secrets/", permission_user),
        pk=str(src.id),
    )
    regenerate_response = AlertSourceModelViewSet.as_view({"post": "regenerate_team_secret"})(
        _request("post", f"/alert_source/{src.id}/team_secrets/regenerate/", permission_user, data={"team_id": 1}),
        pk=str(src.id),
    )
    remove_response = AlertSourceModelViewSet.as_view({"post": "remove_team_secret"})(
        _request("post", f"/alert_source/{src.id}/team_secrets/remove/", permission_user, data={"team_id": 1}),
        pk=str(src.id),
    )

    assert add_response.status_code == status.HTTP_200_OK
    assert list_response.status_code == status.HTTP_200_OK
    assert regenerate_response.status_code == status.HTTP_200_OK
    assert remove_response.status_code == status.HTTP_200_OK
    src.refresh_from_db()
    assert src.team_secrets == {}


@pytest.mark.django_db
def test_team_secret_mutation_locks_source_and_does_not_log_secret(permission_user, mocker, caplog):
    src = _make_source("s1")
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    lock_spy = mocker.spy(AlertSource.objects, "select_for_update")

    response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(
        _request(
            "post",
            f"/alert_source/{src.id}/team_secrets/add/",
            permission_user,
            data={"team_id": 1},
        ),
        pk=str(src.id),
    )
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    lock_spy.assert_called_once_with()
    assert payload["data"]["secret"] not in caplog.text
    audit_records = [record for record in caplog.records if record.msg.startswith("event=alert_source_team_secret_")]
    assert len(audit_records) == 1
    assert audit_records[0].msg == "event=alert_source_team_secret_%s actor=%s source_id=%s team_id=%s"
    assert audit_records[0].args == ("added", "testuser", "s1", "1")


@pytest.mark.django_db
def test_team_secret_scope_filters_list_and_rejects_foreign_team(permission_user):
    src = _make_source("s1", team_secrets={"1": "team-secret-1", "5": "team-secret-5"})
    permission_user.permission = {"alarm": {"Integration-Detail"}}

    list_response = AlertSourceModelViewSet.as_view({"get": "list_team_secrets"})(
        _request("get", f"/alert_source/{src.id}/team_secrets/", permission_user),
        pk=str(src.id),
    )
    reveal_response = AlertSourceModelViewSet.as_view({"post": "reveal_team_secret"})(
        _request(
            "post",
            f"/alert_source/{src.id}/team_secrets/reveal/",
            permission_user,
            data={"team_id": 1},
        ),
        pk=str(src.id),
    )
    foreign_response = AlertSourceModelViewSet.as_view({"post": "regenerate_team_secret"})(
        _request(
            "post",
            f"/alert_source/{src.id}/team_secrets/regenerate/",
            permission_user,
            data={"team_id": 5},
        ),
        pk=str(src.id),
    )

    list_payload = _render(list_response)
    reveal_payload = _render(reveal_response)
    assert list_payload["data"] == [{"team_id": "1", "team_name": "Default Team", "has_secret": True}]
    assert "team-secret-1" not in json.dumps(list_payload)
    assert "team-secret-5" not in json.dumps(list_payload)
    assert reveal_payload["data"] == {"team_id": "1", "secret": "team-secret-1"}
    assert foreign_response.status_code == status.HTTP_403_FORBIDDEN
    src.refresh_from_db()
    assert src.team_secrets == {"1": "team-secret-1", "5": "team-secret-5"}


@pytest.mark.django_db
def test_integration_material_only_contains_authorized_team_secret(permission_user, event_level):
    src = _make_source(
        "s1",
        source_type="zabbix",
        secret="SOURCE-SECRET-SENTINEL",
        team_secrets={"1": "team-secret-1", "5": "team-secret-5"},
    )
    permission_user.permission = {"alarm": {"Integration-Detail"}}

    response = AlertSourceModelViewSet.as_view({"post": "integration_material"})(
        _request(
            "post",
            f"/alert_source/{src.id}/integration-material/",
            permission_user,
            data={"team_id": 1},
        ),
        pk=str(src.id),
    )
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["headers"]["SECRET"] == "team-secret-1"
    serialized = json.dumps(payload)
    assert "SOURCE-SECRET-SENTINEL" not in serialized
    assert "team-secret-5" not in serialized


@pytest.mark.django_db
def test_snmp_integration_material_uses_source_secret_only_for_default_team(permission_user, event_level):
    src = _make_source("snmp_trap", secret="SNMP-SOURCE-SECRET-SENTINEL")
    permission_user.permission = {"alarm": {"Integration-Detail"}}

    response = AlertSourceModelViewSet.as_view({"post": "integration_material"})(
        _request(
            "post",
            f"/alert_source/{src.id}/integration-material/",
            permission_user,
            data={"team_id": 1},
        ),
        pk=str(src.id),
    )
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["headers"]["SECRET"] == "SNMP-SOURCE-SECRET-SENTINEL"


@pytest.mark.django_db
@pytest.mark.parametrize("permission", ["Integration-View", "Integration-Edit"])
def test_team_secret_operations_reject_non_detail_permissions(permission_user, permission):
    src = _make_source("s1")
    permission_user.permission = {"alarm": {permission}}
    response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(
        _request("post", f"/alert_source/{src.id}/team_secrets/add/", permission_user, data={"team_id": 5}),
        pk=str(src.id),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    src.refresh_from_db()
    assert src.team_secrets == {}


def test_k8s_deploy_yaml_skips_tls_only_when_flag_set():
    """insecure_skip_verify=True 时渲染产物含 tls.insecureSkipVerify；默认/未传时不含。"""
    yaml_off = AlertSourceModelViewSet._build_k8s_deploy_yaml(
        receiver_url="https://h/api",
        secret="s",
        cluster_name="c",
        push_source_id="k8s",
    )
    yaml_on = AlertSourceModelViewSet._build_k8s_deploy_yaml(
        receiver_url="https://h/api",
        secret="s",
        cluster_name="c",
        push_source_id="k8s",
        insecure_skip_verify=True,
    )
    assert "insecureSkipVerify" not in yaml_off
    assert "insecureSkipVerify: true" in yaml_on
    # 缩进对齐 ConfigMap 内嵌 config.yaml 层级，避免 YAML 解析错误
    assert "          tls:\n            insecureSkipVerify: true" in yaml_on


def test_k8s_deploy_yaml_embeds_secret_hash_for_rolling_restart():
    """渲染后的 YAML 把 secret 的 short hash 写进 Deployment template annotation，
    保证 secret 变更后 kubectl apply 自动滚动 Pod。"""
    import hashlib

    yaml_a = AlertSourceModelViewSet._build_k8s_deploy_yaml(
        receiver_url="https://h/api",
        secret="secret-A",
        cluster_name="c",
        push_source_id="k8s",
    )
    yaml_b = AlertSourceModelViewSet._build_k8s_deploy_yaml(
        receiver_url="https://h/api",
        secret="secret-B",
        cluster_name="c",
        push_source_id="k8s",
    )
    yaml_a2 = AlertSourceModelViewSet._build_k8s_deploy_yaml(
        receiver_url="https://h/api",
        secret="secret-A",
        cluster_name="c",
        push_source_id="k8s",
    )

    hash_a = hashlib.sha256(b"secret-A").hexdigest()[:16]
    hash_b = hashlib.sha256(b"secret-B").hexdigest()[:16]

    assert "PLACEHOLDER_SECRET_HASH" not in yaml_a
    assert f"bk-lite.tencent.com/secret-hash: {hash_a}" in yaml_a
    assert f"bk-lite.tencent.com/secret-hash: {hash_b}" in yaml_b
    # 幂等：相同 secret 同 hash → apply 不会无谓滚动
    assert yaml_a == yaml_a2


@pytest.fixture
def k8s_image_export_paths(monkeypatch, tmp_path):
    from apps.alerts.views import alert_source as alert_source_module

    exported_paths = []

    def fake_docker_save(command, **kwargs):
        output_path = Path(command[3])
        output_path.write_bytes(b"image-tar")
        exported_paths.append(output_path)

    monkeypatch.setattr(alert_source_module.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(alert_source_module.subprocess, "run", fake_docker_save)
    return exported_paths


@pytest.fixture
def k8s_image_response(monkeypatch):
    from django.http import response as django_response

    from apps.core.utils.web_utils import WebUtils

    monkeypatch.setattr(django_response.signals.request_finished, "send", lambda **kwargs: [])
    return lambda: WebUtils.response_file(
        AlertSourceModelViewSet._build_k8s_image_tar_file(),
        "kubernetes-event-exporter.tar",
    )


@pytest.mark.unit
def test_k8s_image_tar_is_removed_after_response_stream_finishes(k8s_image_export_paths, k8s_image_response):
    response = k8s_image_response()
    exported_path = k8s_image_export_paths[0]

    assert b"".join(response.streaming_content) == b"image-tar"
    assert exported_path.exists()

    response.close()

    assert not exported_path.exists()


@pytest.mark.unit
def test_k8s_image_tar_is_removed_when_response_closes_early(k8s_image_export_paths, k8s_image_response):
    response = k8s_image_response()
    exported_path = k8s_image_export_paths[0]

    response.close()

    assert not exported_path.exists()


@pytest.mark.unit
def test_k8s_image_tar_is_removed_when_docker_save_fails(monkeypatch, k8s_image_export_paths):
    from apps.alerts.views import alert_source as alert_source_module

    def failing_docker_save(command, **kwargs):
        output_path = Path(command[3])
        output_path.write_bytes(b"partial-image-tar")
        k8s_image_export_paths.append(output_path)
        raise subprocess.CalledProcessError(1, command, stderr="docker save failed")

    monkeypatch.setattr(alert_source_module.subprocess, "run", failing_docker_save)

    with pytest.raises(RuntimeError, match="docker save failed"):
        AlertSourceModelViewSet._build_k8s_image_tar_file()

    assert not k8s_image_export_paths[0].exists()


@pytest.mark.unit
def test_k8s_image_tar_is_removed_when_export_is_interrupted(monkeypatch, k8s_image_export_paths):
    from apps.alerts.views import alert_source as alert_source_module

    def interrupted_docker_save(command, **kwargs):
        output_path = Path(command[3])
        output_path.write_bytes(b"partial-image-tar")
        k8s_image_export_paths.append(output_path)
        raise KeyboardInterrupt

    monkeypatch.setattr(alert_source_module.subprocess, "run", interrupted_docker_save)

    with pytest.raises(KeyboardInterrupt):
        AlertSourceModelViewSet._build_k8s_image_tar_file()

    assert not k8s_image_export_paths[0].exists()


@pytest.mark.django_db
def test_team_secret_add_rejected_for_snmp_trap(superuser):
    """SNMP Trap 源不允许配置组织密钥。"""
    src = _make_source("snmp_trap")
    request = _request("post", f"/alert_source/{src.id}/team_secrets/add/", superuser, data={"team_id": 5})
    response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    src.refresh_from_db()
    assert src.team_secrets == {}


@pytest.mark.django_db
def test_team_secret_regenerate_rejected_for_snmp_trap(superuser):
    src = _make_source("snmp_trap", team_secrets={"5": "old"})
    request = _request("post", f"/alert_source/{src.id}/team_secrets/regenerate/", superuser, data={"team_id": 5})
    response = AlertSourceModelViewSet.as_view({"post": "regenerate_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_team_secret_add_requires_team_id(superuser):
    src = _make_source("s1")
    request = _request("post", f"/alert_source/{src.id}/team_secrets/add/", superuser, data={})
    response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_team_secret_add_duplicate(superuser):
    src = _make_source("s1", team_secrets={"5": "existing"})
    request = _request("post", f"/alert_source/{src.id}/team_secrets/add/", superuser, data={"team_id": 5})
    response = AlertSourceModelViewSet.as_view({"post": "add_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_team_secret_regenerate(superuser):
    src = _make_source("s1", team_secrets={"5": "old"})
    request = _request("post", f"/alert_source/{src.id}/team_secrets/regenerate/", superuser, data={"team_id": 5})
    response = AlertSourceModelViewSet.as_view({"post": "regenerate_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    src.refresh_from_db()
    assert src.team_secrets["5"] != "old"


@pytest.mark.django_db
def test_team_secret_regenerate_missing(superuser):
    src = _make_source("s1")
    request = _request("post", f"/alert_source/{src.id}/team_secrets/regenerate/", superuser, data={"team_id": 99})
    response = AlertSourceModelViewSet.as_view({"post": "regenerate_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_team_secret_remove_missing(superuser):
    src = _make_source("s1")
    request = _request("post", f"/alert_source/{src.id}/team_secrets/remove/", superuser, data={"team_id": 99})
    response = AlertSourceModelViewSet.as_view({"post": "remove_team_secret"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --------------------------------------------------------------------------
# daily_event_stats
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_snmp_trap_nodes(permission_user, monkeypatch):
    from apps.alerts.views import alert_source as as_mod

    class FakeNodeMgmt:
        def node_list(self, query):
            return {"count": 1, "nodes": [{"id": "n1"}]}

    monkeypatch.setattr(as_mod, "NodeMgmt", FakeNodeMgmt)
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    request = _request("post", "/alert_source/snmp_trap_nodes/", permission_user, data={"page": 1})
    request.COOKIES["current_team"] = "1"
    response = AlertSourceModelViewSet.as_view({"post": "snmp_trap_nodes"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["count"] == 1


@pytest.mark.django_db
def test_k8s_install_command(permission_user):
    # K8s 接入只接收组织 ID，由服务端在授权后解析组织密钥。
    _make_source(
        "k8s",
        source_type="webhook",
        config={"url": "/recv"},
        team_secrets={"1": "team-sec-1"},
    )
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    data = {"server_url": "https://host:8000", "cluster_name": "prod", "team_id": 1}
    request = _request("post", "/alert_source/k8s_install_command/", permission_user, data=data)
    response = AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["command"]
    assert payload["data"]["token"]


@pytest.mark.django_db
def test_k8s_install_command_requires_team_id(permission_user):
    _make_source(
        "k8s",
        source_type="webhook",
        config={"url": "/recv"},
        team_secrets={"1": "team-sec-1"},
    )
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    data = {"server_url": "https://host:8000", "cluster_name": "prod"}
    request = _request("post", "/alert_source/k8s_install_command/", permission_user, data=data)
    response = AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_k8s_install_command_rejects_foreign_team(permission_user):
    _make_source(
        "k8s",
        source_type="webhook",
        config={"url": "/recv"},
        team_secrets={"5": "team-sec-5"},
    )
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    request = _request(
        "post",
        "/alert_source/k8s_install_command/",
        permission_user,
        data={"server_url": "https://host:8000", "cluster_name": "prod", "team_id": 5},
    )
    response = AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_k8s_meta_not_found(permission_user):
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    request = _request("get", "/alert_source/k8s_meta/", permission_user)
    response = AlertSourceModelViewSet.as_view({"get": "k8s_meta"})(request)
    _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_k8s_meta_found(permission_user):
    _make_source("k8s", source_type="webhook", config={"url": "/recv", "method": "POST"})
    permission_user.permission = {"alarm": {"Integration-Detail"}}
    request = _request("get", "/alert_source/k8s_meta/", permission_user)
    response = AlertSourceModelViewSet.as_view({"get": "k8s_meta"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["source_id"] == "k8s"


@pytest.mark.django_db
def test_daily_event_stats(superuser):
    from django.utils import timezone

    from apps.alerts.models.models import Event

    src = _make_source("s1")
    Event.objects.create(source=src, raw_data={}, title="t", level="0", start_time=timezone.now(), event_id="E1")
    request = _request("get", "/alert_source/daily_event_stats/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "daily_event_stats"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert "today" in json.dumps(payload, ensure_ascii=False) or payload["data"] is not None


@pytest.mark.django_db
def test_daily_event_stats_user_timezone_day_boundary(superuser):
    """daily_event_stats 的"今日"应按用户时区日界切分，而非 UTC 日界。

    场景：UTC 2026-07-24 16:30（Asia/Shanghai 2026-07-25 00:30）收到事件。
    UTC+8 用户在本地 7-25 00:35 查询时，该事件应计入"今日"（7-25），
    而非按 UTC 日界计入"昨日"（7-24）。
    """
    import zoneinfo
    from unittest.mock import patch

    from django.utils import timezone as dj_timezone

    from apps.alerts.models.models import Event

    src = _make_source("s-tz")
    # UTC 7-24 16:30 = Asia/Shanghai 7-25 00:30（用户时区的"今天"）
    utc_dt = dj_timezone.datetime(2026, 7, 24, 16, 30, 0, tzinfo=dj_timezone.utc)
    event = Event.objects.create(source=src, raw_data={}, title="t", level="0", start_time=utc_dt, event_id="E-tz")
    Event.objects.filter(pk=event.pk).update(received_at=utc_dt)

    shanghai = zoneinfo.ZoneInfo("Asia/Shanghai")
    dj_timezone.activate(shanghai)
    try:
        # 模拟用户在 Asia/Shanghai 7-25 00:35 查询（即 UTC 7-24 16:35）
        fake_now_utc = dj_timezone.datetime(2026, 7, 24, 16, 35, 0, tzinfo=dj_timezone.utc)
        with patch("apps.alerts.views.alert_source.timezone.now", return_value=fake_now_utc):
            request = _request("get", "/alert_source/daily_event_stats/", superuser)
            response = AlertSourceModelViewSet.as_view({"get": "daily_event_stats"})(request)
            payload = _render(response)
    finally:
        dj_timezone.deactivate()

    assert response.status_code == status.HTTP_200_OK
    # 按用户时区日界，UTC 7-24 16:30 属于 Asia/Shanghai 7-25（今日），today_count >= 1
    assert payload["data"]["today_count"] >= 1, f"按用户时区日界，事件应计入今日，实际 today_count={payload['data']['today_count']}"
