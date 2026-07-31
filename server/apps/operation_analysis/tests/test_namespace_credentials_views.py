import pytest
from rest_framework import status

from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.models import datasource_models
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
# 真实 URL 图会经 operation_analysis.services.network_status_topology 间接加载 apps.alerts / apps.cmdb。
URL_RUNTIME_APP_DEPENDENCIES = ("apps.alerts", "apps.cmdb")


def test_get_source_data_returns_actionable_redacted_credential_error(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "current-key")

    namespace = NameSpace.objects.create(
        name="legacy",
        account="nats-user",
        password="initial-password",
        domain="nats.example.com",
    )
    stored_value = PasswordCrypto("old-key").encrypt("plain-secret")
    NameSpace.objects.filter(pk=namespace.pk).update(password=stored_value)
    data_source = DataSourceAPIModel.objects.create(
        name="test-datasource",
        groups=[1],
        rest_api="monitor/query",
        params=[],
    )
    data_source.namespaces.add(namespace)
    nats_calls = []

    class FakeClient:
        DEFAULT_NATS = True

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_customization_nast_data(self, **kwargs):
            nats_calls.append(kwargs)

    monkeypatch.setattr(GetNatsData, "default_nats_client", property(lambda self: FakeClient))
    response = api_client.post(
        f"/api/v1/operation_analysis/api/data_source/get_source_data/{data_source.pk}/",
        {},
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert payload["result"] is False
    assert payload["message"] == "命名空间密码解密失败，请重新录入密码"
    assert stored_value not in response.content.decode()
    assert "plain-secret" not in response.content.decode()
    assert nats_calls == []
