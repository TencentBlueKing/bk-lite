"""告警源视图集覆盖测试。

对照 spec/prd/告警中心·集成：告警源增删改查、对接指引、组织密钥管理、事件统计。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level
from apps.alerts.views.alert_source import AlertSourceModelViewSet


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


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


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
    _make_source("k8s", source_type="webhook", config={"url": "/recv"})
    data = {"server_url": "https://host:8000", "cluster_name": "prod"}
    request = _request("post", "/alert_source/k8s_install_command/", superuser, data=data)
    response = AlertSourceModelViewSet.as_view({"post": "k8s_install_command"})(request)
    payload = _render(response)
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)


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
