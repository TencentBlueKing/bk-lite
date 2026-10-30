from unittest.mock import patch

import pytest

from apps.alerts.tests.test_itsm_client import create_calls, response, workflow_body
from apps.alerts.tests.test_itsm_views import configured_api_client, superuser_client  # noqa: F401

BASE = "/api/v1/alerts/api/itsm_integration/"


@pytest.fixture(autouse=True)
def verified_test_contract(monkeypatch):
    # 模拟后端完成协议适配后的行为；这是测试协议，不代表真实 ITSM 已验收。
    monkeypatch.setattr(
        "apps.alerts.itsm.config.BKLITE_RESPONSE_CONTRACT",
        {
            "create_id_path": "ticket.id",
            "detail_fields": {"id": "ticket.id", "status": "ticket.status"},
            "states": {"running": {"label": "处理中", "closed": False}, "finished": {"label": "已关闭", "closed": True}},
        },
    )


def payload():
    return {
        "name": "开发 ITSM",
        "url": "https://itsm.example/openapi/v1/itsm/openapi/v1",
        "token": "SENSITIVE-TEST-TOKEN",
        "enabled": True,
        "failure_notification": {"usernames": [], "channel_ids": []},
    }


def save_tested(client, values):
    # 配置用例的外部 HTTP 边界返回成功；保存仍经过真实校验和复测路径。
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})
    ):
        return client.put(BASE + "configure/", values, format="json")


@pytest.mark.django_db
def test_saved_configuration_is_private_and_used_for_authentication(itsm_api_client):
    assert itsm_api_client.get(BASE).json()["data"] is None
    saved = save_tested(itsm_api_client, payload())
    assert saved.status_code == 200
    assert "SENSITIVE-TEST-TOKEN" not in str(saved.data)
    assert saved.data["token_configured"] is True
    reference = saved.data["reference"]
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})
    ) as http:
        result = itsm_api_client.post(BASE + "test_connection/", {}, format="json")
        assert result.status_code == 200
        assert http.call_args.args[0] == "GET"
        assert "ticket/list/" in http.call_args.args[1]
        assert http.call_args.kwargs["headers"]["Authorization"] == "Bearer SENSITIVE-TEST-TOKEN"
    update = payload()
    update["token"] = ""
    update["name"] = "重命名"
    assert save_tested(itsm_api_client, update).status_code == 200
    assert itsm_api_client.get(BASE).json()["data"]["reference"] == reference
    from apps.alerts.models.itsm import AlertItsmIntegration

    stored = AlertItsmIntegration.objects.get(team_id=1)
    assert "SENSITIVE-TEST-TOKEN" not in stored.encrypted_token
    choices = itsm_api_client.get("/api/v1/alerts/api/action_rule/itsm_connections/").json()["data"]
    assert choices == [{"value": reference, "label": "重命名"}]


@pytest.mark.django_db
def test_team_isolation_rotation_and_disabled_runtime(itsm_api_client):
    from apps.alerts.itsm.config import ItsmError, get_connection
    from apps.alerts.itsm.integration import resolve_token
    from apps.alerts.models.itsm import AlertItsmIntegration

    save_tested(itsm_api_client, payload())
    record = AlertItsmIntegration.objects.get(team_id=1)
    itsm_api_client.cookies["current_team"] = "2"
    assert itsm_api_client.get(BASE).json()["data"] is None
    assert itsm_api_client.post(BASE + "test_connection/", {}, format="json").status_code == 400
    with pytest.raises(ItsmError):
        get_connection(record.reference, [2])
    itsm_api_client.cookies["current_team"] = "1"
    changed = payload()
    changed["token"] = "ROTATED-SENTINEL"
    assert save_tested(itsm_api_client, changed).status_code == 200
    assert resolve_token(record.pk) == "ROTATED-SENTINEL"
    changed["enabled"] = False
    assert save_tested(itsm_api_client, changed).status_code == 200
    with pytest.raises(ItsmError):
        get_connection(record.reference, [1])
    assert itsm_api_client.get("/api/v1/alerts/api/action_rule/itsm_connections/").json()["data"] == []
    record.encrypted_token = "invalid-ciphertext"
    record.enabled = True
    record.save()
    with pytest.raises(ItsmError, match="凭据不可用"):
        resolve_token(record.pk)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("url", "http://insecure.example"),
        ("url", "https://user:secret@itsm.example"),
        ("url", "https://itsm.example/?token=secret"),
        ("ca_pem", "not-a-certificate"),
        ("states", {"finished": {"closed": "false", "label": "end"}}),
    ],
)
def test_invalid_configuration_cannot_be_saved(itsm_api_client, field, value):
    values = payload()
    values[field] = value
    assert save_tested(itsm_api_client, values).status_code == 400
    assert itsm_api_client.get(BASE).json()["data"] is None


@pytest.mark.django_db
def test_view_permission_does_not_allow_edit_or_test(authenticated_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    client.cookies["current_team"] = "1"
    with patch("apps.core.decorators.api_permission.HasPermission._get_user_permissions", return_value={"global_config-View"}):
        assert client.get(BASE).status_code == 200
        assert client.put(BASE + "configure/", payload(), format="json").status_code == 403
        assert client.post(BASE + "test_connection/", {}, format="json").status_code == 403


@pytest.mark.django_db
def test_connection_test_blocks_metadata_and_hides_remote_errors(itsm_api_client):
    values = payload()
    values["url"] = "https://169.254.169.254/openapi"
    values["enabled"] = False
    assert save_tested(itsm_api_client, values).status_code == 200
    with patch("requests.Session.request") as http:
        denied = itsm_api_client.post(BASE + "test_connection/", {}, format="json")
        assert denied.status_code == 400
        assert "网络访问策略" in denied.data["detail"]
        http.assert_not_called()
    save_tested(itsm_api_client, payload())
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": False, "code": "40100", "message": "SENSITIVE-TEST-TOKEN"}, 401)
    ):
        result = itsm_api_client.post(BASE + "test_connection/", {}, format="json")
        assert result.status_code == 400
        assert "SENSITIVE-TEST-TOKEN" not in str(result.data)


@pytest.mark.django_db
def test_connection_can_be_enabled_before_ticket_contract_is_available(itsm_api_client, monkeypatch):
    monkeypatch.setattr("apps.alerts.itsm.config.BKLITE_RESPONSE_CONTRACT", {"detail_fields": {"id": "ticket.id"}})
    values = {"name": "待联调", "url": payload()["url"], "token": "DRAFT-TOKEN", "enabled": False}
    assert save_tested(itsm_api_client, values).status_code == 200
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"count": 0, "results": []}})
    ):
        assert itsm_api_client.post(BASE + "test_connection/", {}, format="json").status_code == 200
    assert itsm_api_client.get(BASE).json()["data"]["contract_ready"] is False
    values["enabled"] = True
    result = save_tested(itsm_api_client, values)
    assert result.status_code == 200
    assert result.data["enabled"] is True
    assert result.data["contract_ready"] is False
    assert itsm_api_client.get("/api/v1/alerts/api/action_rule/itsm_connections/").json()["data"] == [
        {"value": result.data["reference"], "label": "待联调"}
    ]
    # 允许启用连接不等于绕过建单校验；规则仍须验证真实响应契约。
    from apps.alerts.itsm.config import ItsmError, validate_config

    with patch("requests.Session.request") as http, pytest.raises(ItsmError, match="接口联调"):
        validate_config(
            {
                "connection": result.data["reference"],
                "workflow_key": "workflow",
                "form_bindings": [{"name": "ticket__title", "from": "field", "value": "title"}],
            },
            [1],
        )
    http.assert_not_called()
    values["enabled"] = False
    assert save_tested(itsm_api_client, values).data["enabled"] is False


@pytest.mark.django_db
def test_dns_change_at_actual_connection_is_blocked(itsm_api_client):
    save_tested(itsm_api_client, payload())
    with patch("socket.getaddrinfo", side_effect=[[(2, 1, 6, "", ("93.184.216.34", 443))], [(2, 1, 6, "", ("169.254.169.254", 443))]]), patch(
        "socket.socket"
    ) as sock:
        result = itsm_api_client.post(BASE + "test_connection/", {}, format="json")
        assert result.status_code == 400
        sock.assert_not_called()


@pytest.mark.django_db
def test_new_target_never_receives_old_token_and_existing_tickets_keep_target(itsm_api_client):
    from apps.alerts.itsm.client import ItsmClient, ItsmError
    from apps.alerts.itsm.config import get_connection
    from apps.alerts.models.itsm import AlertItsmIntegration, AlertItsmTicket
    from apps.alerts.tests.test_itsm_service import alert

    save_tested(itsm_api_client, payload())
    instance = AlertItsmIntegration.objects.get(team_id=1)
    old = get_connection(instance.reference, [1])
    values = payload()
    values["url"] = "https://another.example/api"
    values["token"] = ""
    assert save_tested(itsm_api_client, values).status_code == 400
    values["token"] = "NEW-DESTINATION-TOKEN"
    assert save_tested(itsm_api_client, values).status_code == 200
    with patch("requests.Session.request") as http, pytest.raises(ItsmError, match="已变更"):
        ItsmClient(old).test_connection()
    http.assert_not_called()
    AlertItsmTicket.objects.create(alert=alert(), connection=instance.reference, ticket_id="123", instance_id=instance.reference, team=[1])
    assert save_tested(itsm_api_client, payload()).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("suffix", ["v1", "v1/"])
def test_same_target_across_teams_has_one_ticket_namespace(itsm_api_client, suffix):
    from django.db import IntegrityError, transaction

    from apps.alerts.models.itsm import AlertItsmIntegration, AlertItsmTicket
    from apps.alerts.tests.test_itsm_service import alert

    save_tested(itsm_api_client, payload())
    itsm_api_client.cookies["current_team"] = "2"
    same = payload()
    same["url"] = "https://ITSM.EXAMPLE:443/openapi/v1/itsm/openapi/" + suffix
    same["token"] = "DIFFERENT-ACCOUNT"
    assert save_tested(itsm_api_client, same).status_code == 200
    first, second = list(AlertItsmIntegration.objects.order_by("team_id"))
    assert first.reference != second.reference
    assert first.connection_config()["instance_id"] == second.connection_config()["instance_id"]
    AlertItsmTicket.objects.create(alert=alert(), connection=first.reference, instance_id=first.connection_config()["instance_id"], ticket_id="123")
    with pytest.raises(IntegrityError), transaction.atomic():
        AlertItsmTicket.objects.create(
            alert=alert(), connection=second.reference, instance_id=second.connection_config()["instance_id"], ticket_id="123"
        )


@pytest.mark.django_db
def test_db_config_drives_creation_and_target_cannot_change_while_sending(itsm_api_client):
    from apps.alerts.itsm.service import execute_creation
    from apps.alerts.tests.test_itsm_service import alert, prepare, rule

    saved = save_tested(itsm_api_client, payload()).data
    r = rule()
    r.action_config["connection"] = saved["reference"]
    r.save()
    a = alert()
    link = prepare(a)

    def remote(*args, **kwargs):
        if args[0] == "GET":
            return response(workflow_body([]))
        changed = payload()
        changed["url"] = "https://changed.example/api"
        changed["token"] = "REPLACEMENT-TOKEN"
        assert itsm_api_client.put(BASE + "configure/", changed, format="json").status_code == 400
        assert kwargs["headers"]["Authorization"] == "Bearer SENSITIVE-TEST-TOKEN"
        return response({"result": True, "code": "20000", "data": {"id": "actual-123"}})

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", side_effect=remote
    ) as http:
        execute_creation(link.current_execution_id)
        execute_creation(link.current_execution_id)
        assert len(create_calls(http)) == 1
    link.refresh_from_db()
    assert link.ticket_id == "actual-123"


@pytest.mark.django_db
def test_configuration_encrypt_failure_rolls_back_without_secret_in_error(itsm_api_client):
    with patch("apps.core.mixinx.EncryptMixin.get_cipher_suite", side_effect=ValueError("SENSITIVE-TEST-TOKEN")):
        result = save_tested(itsm_api_client, payload())
        assert result.status_code == 400
        assert "SENSITIVE-TEST-TOKEN" not in str(result.data)
    assert itsm_api_client.get(BASE).json()["data"] is None


@pytest.mark.django_db
def test_empty_or_unowned_team_cannot_manage_integration(authenticated_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    with patch("apps.core.decorators.api_permission.HasPermission._get_user_permissions", return_value={"global_config-View", "global_config-Edit"}):
        assert client.get(BASE).status_code == 403
        client.cookies["current_team"] = "999"
        assert client.get(BASE).status_code == 403
        assert client.put(BASE + "configure/", payload(), format="json").status_code == 403


@pytest.mark.django_db
def test_ca_bundle_used_only_during_request_and_removed(itsm_api_client):
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ITSM Test CA")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    values = payload()
    values["ca_pem"] = certificate.public_bytes(serialization.Encoding.PEM).decode()
    assert save_tested(itsm_api_client, values).status_code == 200
    paths = []

    def remote(*args, **kwargs):
        paths.append(Path(kwargs["verify"]))
        assert paths[-1].read_text() == values["ca_pem"].strip()
        return response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch("requests.Session.request", side_effect=remote):
        assert itsm_api_client.post(BASE + "test_connection/", {}, format="json").status_code == 200
    assert len(paths) == 1 and not paths[0].exists()


@pytest.mark.django_db
def test_response_contract_is_not_user_configuration(itsm_api_client):
    values = {"name": "ITSM", "url": payload()["url"], "token": "TEST-TOKEN", "enabled": False}
    saved = save_tested(itsm_api_client, values)
    assert saved.status_code == 200
    assert isinstance(saved.data["contract_ready"], bool)
    assert not {"create_id_path", "detail_fields", "states"}.intersection(saved.data)
    for field, value in [("create_id_path", "id"), ("detail_fields", {"id": "id"}), ("states", {"running": {"label": "closed", "closed": True}})]:
        result = itsm_api_client.put(BASE + "configure/", {**values, field: value}, format="json")
        assert result.status_code == 400


@pytest.mark.django_db
def test_legacy_saved_response_fields_cannot_override_backend_contract(itsm_api_client):
    from apps.alerts.itsm.client import ItsmClient
    from apps.alerts.models.itsm import AlertItsmIntegration

    assert save_tested(itsm_api_client, payload()).status_code == 200
    record = AlertItsmIntegration.objects.get(team_id=1)
    record.config.update({"create_id_path": "fake", "detail_fields": {"id": "fake"}, "states": {"running": {"closed": True}}})
    record.save()
    public = itsm_api_client.get(BASE).json()["data"]
    assert public["contract_ready"] is True
    assert not {"create_id_path", "detail_fields", "states"}.intersection(public)
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"ticket": {"id": "123", "status": "running"}}})
    ):
        result = ItsmClient(record.connection_config()).detail("123")
    assert result["is_closed"] is False
    assert result["status_label"] == "running"


@pytest.mark.django_db
def test_service_catalog_is_exposed_as_ticket_options(itsm_api_client):
    save_tested(itsm_api_client, payload())
    catalog = {
        "code": "20000",
        "data": {
            "results": [
                {"name": "终端服务 / 个人电脑或外设申请与更换", "workflow_id": "20261008185800000809", "enabled": True},
                {"name": "停用服务", "workflow_id": "disabled", "enabled": False},
            ]
        },
    }
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response(catalog)
    ) as http:
        result = itsm_api_client.get(BASE + "services/")
    assert result.status_code == 200
    assert result.json()["data"] == [{"value": "20261008185800000809", "label": "终端服务 / 个人电脑或外设申请与更换"}]
    assert http.call_args.args[1].endswith("/service_catalog/service_list/")
    assert "SENSITIVE-TEST-TOKEN" not in str(result.data)
