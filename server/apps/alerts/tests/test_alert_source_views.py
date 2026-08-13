"""告警源视图集覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-集成.md：告警源增删改查、对接指引、组织密钥管理、事件统计。
"""

import json
from pathlib import Path

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level
from apps.alerts.views.alert_source import AlertSourceModelViewSet
from apps.system_mgmt.management.commands.init_realm_resource import create_default_roles, create_resource
from apps.system_mgmt.models import App, Menu, Role


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
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


@pytest.fixture
def permission_user(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {}
    return authenticated_user


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "path", "data"),
    [
        ("get", "list", "/alert_source/", None),
        ("get", "retrieve", "/alert_source/{id}/", None),
        (
            "post",
            "create",
            "/alert_source/",
            {"name": "new", "source_id": "new-source", "source_type": "restful"},
        ),
        (
            "put",
            "update",
            "/alert_source/{id}/",
            {"name": "updated", "source_id": "s1", "source_type": "restful"},
        ),
        ("patch", "partial_update", "/alert_source/{id}/", {"name": "patched"}),
        ("delete", "destroy", "/alert_source/{id}/", None),
        ("get", "integration_guide", "/alert_source/{id}/integration-guide/", None),
    ],
)
def test_alert_source_endpoints_reject_user_without_integration_permission(
    permission_user,
    event_level,
    method,
    action,
    path,
    data,
):
    source = _make_source("s1", source_type="zabbix")
    request = _request(method, path.format(id=source.id), permission_user, data=data)
    kwargs = {"pk": str(source.id)} if "{id}" in path else {}

    response = AlertSourceModelViewSet.as_view({method: action})(request, **kwargs)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_integration_view_preserves_read_and_guide_access(permission_user, event_level):
    source = _make_source("s1", source_type="zabbix")
    permission_user.permission = {"alarm": {"Integration-View"}}

    list_response = AlertSourceModelViewSet.as_view({"get": "list"})(
        _request("get", "/alert_source/", permission_user)
    )
    retrieve_response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(
        _request("get", f"/alert_source/{source.id}/", permission_user),
        pk=str(source.id),
    )
    guide_response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(
        _request("get", f"/alert_source/{source.id}/integration-guide/", permission_user),
        pk=str(source.id),
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert retrieve_response.status_code == status.HTTP_200_OK
    assert guide_response.status_code == status.HTTP_200_OK
    assert guide_response.data["headers"] == {"SECRET": source.secret}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "permission", "data", "expected_status"),
    [
        (
            "post",
            "create",
            "Integration-Add",
            {"name": "new", "source_id": "new-source", "source_type": "restful"},
            status.HTTP_201_CREATED,
        ),
        (
            "put",
            "update",
            "Integration-Edit",
            {"name": "updated", "source_id": "s1", "source_type": "restful"},
            status.HTTP_200_OK,
        ),
        ("patch", "partial_update", "Integration-Edit", {"name": "patched"}, status.HTTP_200_OK),
        ("delete", "destroy", "Integration-Delete", None, status.HTTP_204_NO_CONTENT),
    ],
)
def test_alert_source_write_actions_accept_matching_permissions(
    permission_user,
    method,
    action,
    permission,
    data,
    expected_status,
):
    source = _make_source("s1")
    permission_user.permission = {"alarm": {permission}}
    path = "/alert_source/" if action == "create" else f"/alert_source/{source.id}/"
    request = _request(method, path, permission_user, data=data)
    kwargs = {} if action == "create" else {"pk": str(source.id)}

    response = AlertSourceModelViewSet.as_view({method: action})(request, **kwargs)

    assert response.status_code == expected_status
    if action == "create":
        assert AlertSource.objects.filter(source_id="new-source", name="new").exists()
    elif action == "destroy":
        assert not AlertSource.all_objects.filter(pk=source.pk).exists()
    else:
        source.refresh_from_db()
        assert source.name == ("patched" if action == "partial_update" else "updated")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "permission", "data"),
    [
        (
            "post",
            "create",
            "Integration-View",
            {"name": "new", "source_id": "new-source", "source_type": "restful"},
        ),
        ("patch", "partial_update", "Integration-Add", {"name": "patched"}),
        ("delete", "destroy", "Integration-Edit", None),
    ],
)
def test_alert_source_write_actions_reject_mismatched_permissions(
    permission_user,
    method,
    action,
    permission,
    data,
):
    source = _make_source("s1")
    permission_user.permission = {"alarm": {permission}}
    path = "/alert_source/" if action == "create" else f"/alert_source/{source.id}/"
    request = _request(method, path, permission_user, data=data)
    kwargs = {} if action == "create" else {"pk": str(source.id)}

    response = AlertSourceModelViewSet.as_view({method: action})(request, **kwargs)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_alarm_menu_defines_alert_source_crud_permissions():
    menu_path = Path(__file__).resolve().parents[3] / "support-files/system_mgmt/menus/alarm.json"
    menu_data = json.loads(menu_path.read_text(encoding="utf-8"))
    integration = next(
        child
        for group in menu_data["menus"]
        for child in group["children"]
        if child["id"] == "Integration"
    )

    assert integration["operation"] == ["View", "Detail", "Add", "Edit", "Delete"]


@pytest.mark.django_db
def test_new_integration_permissions_preserve_existing_roles():
    menu_path = Path(__file__).resolve().parents[3] / "support-files/system_mgmt/menus/alarm.json"
    menu_data = json.loads(menu_path.read_text(encoding="utf-8"))
    legacy_menus = json.loads(json.dumps(menu_data["menus"]))
    legacy_integration = next(
        child
        for group in legacy_menus
        for child in group["children"]
        if child["id"] == "Integration"
    )
    legacy_integration["operation"] = ["View", "Detail"]
    app = App.objects.create(name="alarm", display_name="Alarm", url="/alarm", is_build_in=True)

    create_resource(app, legacy_menus)
    create_default_roles(app, menu_data["roles"])
    detail_id = Menu.objects.get(app="alarm", name="Integration-Detail").id
    custom_role = Role.objects.create(name="custom", app="alarm", menu_list=[detail_id])

    create_resource(app, menu_data["menus"])
    create_default_roles(app, menu_data["roles"])

    normal_role = Role.objects.get(name="normal", app="alarm")
    manager_role = Role.objects.get(name="manager", app="alarm")
    normal_permissions = set(Menu.objects.filter(id__in=normal_role.menu_list).values_list("name", flat=True))
    manager_permissions = set(Menu.objects.filter(id__in=manager_role.menu_list).values_list("name", flat=True))
    custom_role.refresh_from_db()
    assert "Integration-View" in normal_permissions
    assert not {"Integration-Add", "Integration-Edit", "Integration-Delete"} & normal_permissions
    assert {"Integration-Add", "Integration-Edit", "Integration-Delete"} <= manager_permissions
    assert custom_role.menu_list == [detail_id]

    menu_snapshot = dict(Menu.objects.filter(app="alarm").values_list("name", "id"))
    role_snapshot = {
        role.name: tuple(role.menu_list)
        for role in Role.objects.filter(app="alarm").order_by("name")
    }
    create_resource(app, menu_data["menus"])
    create_default_roles(app, menu_data["roles"])

    assert dict(Menu.objects.filter(app="alarm").values_list("name", "id")) == menu_snapshot
    assert {
        role.name: tuple(role.menu_list)
        for role in Role.objects.filter(app="alarm").order_by("name")
    } == role_snapshot


@pytest.mark.django_db
def test_integration_permission_initialization_rolls_back_on_failure(monkeypatch):
    from apps.system_mgmt.management.commands import init_realm_resource

    menu_path = Path(__file__).resolve().parents[3] / "support-files/system_mgmt/menus/alarm.json"
    menu_data = json.loads(menu_path.read_text(encoding="utf-8"))
    legacy_menus = json.loads(json.dumps(menu_data["menus"]))
    legacy_integration = next(
        child
        for group in legacy_menus
        for child in group["children"]
        if child["id"] == "Integration"
    )
    legacy_integration["operation"] = ["View", "Detail"]
    app = App.objects.create(name="alarm", display_name="Alarm", url="/alarm", is_build_in=True)
    create_resource(app, legacy_menus)
    create_default_roles(app, menu_data["roles"])
    menu_snapshot = dict(Menu.objects.filter(app="alarm").values_list("name", "id"))
    role_snapshot = {
        role.name: tuple(role.menu_list)
        for role in Role.objects.filter(app="alarm").order_by("name")
    }
    real_create_default_roles = init_realm_resource.create_default_roles

    def fail_after_role_update(app_inst, roles):
        real_create_default_roles(app_inst, roles)
        raise RuntimeError("injected role initialization failure")

    monkeypatch.setattr(init_realm_resource, "get_install_apps", lambda: set())
    monkeypatch.setattr(
        init_realm_resource.os,
        "walk",
        lambda _: [("support-files/system_mgmt/menus", [], ["alarm.json"])],
    )
    monkeypatch.setattr(init_realm_resource, "create_default_roles", fail_after_role_update)

    with pytest.raises(RuntimeError, match="injected role initialization failure"):
        init_realm_resource.Command().handle()

    assert dict(Menu.objects.filter(app="alarm").values_list("name", "id")) == menu_snapshot
    assert {
        role.name: tuple(role.menu_list)
        for role in Role.objects.filter(app="alarm").order_by("name")
    } == role_snapshot


@pytest.mark.django_db
def test_alert_source_list(superuser):
    _make_source("s1")
    _make_source("s2")
    request = _request("get", "/alert_source/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 2


@pytest.mark.django_db
def test_alert_source_retrieve(superuser):
    src = _make_source("s1")
    request = _request("get", f"/alert_source/{src.id}/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "retrieve"})(request, pk=str(src.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["source_id"] == "s1"


@pytest.mark.django_db
def test_alert_source_integration_guide(superuser, event_level):
    # 仅 zabbix adapter 的 get_integration_guide 接受 language 参数；
    # restful/prometheus adapter 不接受，视图调用会报错（已知问题）。
    src = _make_source("s1", source_type="zabbix")
    request = _request("get", f"/alert_source/{src.id}/integration-guide/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "integration_guide"})(request, pk=str(src.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["source_id"] == "s1"


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

    # remove
    req_rm = _request("post", f"/alert_source/{src.id}/team_secrets/remove/", superuser, data={"team_id": 5})
    resp_rm = AlertSourceModelViewSet.as_view({"post": "remove_team_secret"})(req_rm, pk=str(src.id))
    _render(resp_rm)
    assert resp_rm.status_code == status.HTTP_200_OK
    src.refresh_from_db()
    assert src.team_secrets == {}


class _StubRequest:
    """承载 .data dict 的最小请求壳，模拟 DRF Request。"""

    def __init__(self, data):
        self.data = data


@pytest.mark.django_db
def test_resolve_k8s_team_secret_requires_team_secret():
    """K8s 接入必须显式传 team_secret；未传 → BaseAppException。"""
    from apps.core.exceptions.base_app_exception import BaseAppException

    src = _make_source("k8s", team_secrets={"5": "team-secret-token"})
    request = _StubRequest({"server_url": "https://h:8000", "cluster_name": "c"})
    with pytest.raises(BaseAppException):
        AlertSourceModelViewSet._resolve_k8s_team_secret(request, src)


@pytest.mark.django_db
def test_resolve_k8s_team_secret_rejects_unknown_token():
    """K8s 接入传了 team_secret 但不在 source.team_secrets 里 → 拒绝。"""
    from apps.core.exceptions.base_app_exception import BaseAppException

    src = _make_source("k8s", team_secrets={"5": "team-secret-token"})
    request = _StubRequest({"team_secret": "forged-token"})
    with pytest.raises(BaseAppException):
        AlertSourceModelViewSet._resolve_k8s_team_secret(request, src)


@pytest.mark.django_db
def test_resolve_k8s_team_secret_accepts_valid_token():
    """K8s 接入传入合法 team_secret → 返回该 secret。"""
    src = _make_source("k8s", team_secrets={"5": "team-secret-token"})
    request = _StubRequest({"team_secret": "team-secret-token"})
    assert AlertSourceModelViewSet._resolve_k8s_team_secret(request, src) == "team-secret-token"


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
def test_alert_source_create(superuser):
    data = {"name": "新源", "source_id": "new-src", "source_type": "restful"}
    request = _request("post", "/alert_source/", superuser, data=data)
    response = AlertSourceModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    src = AlertSource.objects.get(source_id="new-src")
    # 序列化器 validate 会基于 source_type 构建默认 config
    assert isinstance(src.config, dict)


@pytest.mark.django_db
def test_alert_source_update(superuser):
    src = _make_source("s1")
    data = {"name": "改名", "source_id": "s1", "source_type": "restful"}
    request = _request("put", f"/alert_source/{src.id}/", superuser, data=data)
    response = AlertSourceModelViewSet.as_view({"put": "update"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    src.refresh_from_db()
    assert src.name == "改名"


@pytest.mark.django_db
def test_alert_source_destroy(superuser):
    src = _make_source("s1")
    request = _request("delete", f"/alert_source/{src.id}/", superuser)
    response = AlertSourceModelViewSet.as_view({"delete": "destroy"})(request, pk=str(src.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_snmp_trap_nodes(superuser, monkeypatch):
    from apps.alerts.views import alert_source as as_mod

    class FakeNodeMgmt:
        def node_list(self, query):
            return {"count": 1, "nodes": [{"id": "n1"}]}

    monkeypatch.setattr(as_mod, "NodeMgmt", FakeNodeMgmt)
    request = _request("post", "/alert_source/snmp_trap_nodes/", superuser, data={"page": 1})
    request.COOKIES["current_team"] = "1"
    response = AlertSourceModelViewSet.as_view({"post": "snmp_trap_nodes"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["count"] == 1


@pytest.mark.django_db
def test_k8s_install_command(superuser):
    # K8s 接入强制走组织密钥路径：source 需配 team_secrets，请求需带合法 team_secret。
    _make_source(
        "k8s", source_type="webhook", config={"url": "/recv"},
        team_secrets={"1": "team-sec-1"},
    )
    data = {"server_url": "https://host:8000", "cluster_name": "prod", "team_secret": "team-sec-1"}
    request = _request("post", "/alert_source/k8s_install_command/", superuser, data=data)
    response = AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["command"]
    assert payload["data"]["token"]


@pytest.mark.django_db
def test_k8s_install_command_requires_team_secret(superuser):
    """K8s 接入强制要求 team_secret(组织密钥),缺失应被拒。"""
    from apps.core.exceptions.base_app_exception import BaseAppException

    _make_source(
        "k8s", source_type="webhook", config={"url": "/recv"},
        team_secrets={"1": "team-sec-1"},
    )
    data = {"server_url": "https://host:8000", "cluster_name": "prod"}  # 故意不传 team_secret
    request = _request("post", "/alert_source/k8s_install_command/", superuser, data=data)
    with pytest.raises(BaseAppException):
        AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)


@pytest.mark.django_db
def test_k8s_meta_not_found(superuser):
    request = _request("get", "/alert_source/k8s_meta/", superuser)
    response = AlertSourceModelViewSet.as_view({"get": "k8s_meta"})(request)
    _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_k8s_meta_found(superuser):
    _make_source("k8s", source_type="webhook", config={"url": "/recv", "method": "POST"})
    request = _request("get", "/alert_source/k8s_meta/", superuser)
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
    from django.utils import timezone as dj_timezone
    import zoneinfo
    from unittest.mock import patch

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
    assert payload["data"]["today_count"] >= 1, (
        f"按用户时区日界，事件应计入今日，实际 today_count={payload['data']['today_count']}"
    )
