import pytest

from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices


@pytest.mark.django_db
class TestIntegrationInstanceAvailableInstances:
    def test_filters_by_capability(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        IntegrationInstance.objects.create(
            name="总部通讯录",
            provider_key="feishu",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={
                "login_auth": IntegrationInstanceStatusChoices.READY,
                "user_sync": IntegrationInstanceStatusChoices.READY,
            },
            capability_enabled={"login_auth": True, "user_sync": True},
            enabled=True,
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["provider_name"] == "Feishu"

    def test_excludes_disabled_capability(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        IntegrationInstance.objects.create(
            name="总部通讯录",
            provider_key="feishu",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
            capability_enabled={"login_auth": False},
            enabled=True,
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")

        assert response.status_code == 200
        assert len(response.data) == 0

    def test_excludes_not_ready_capability(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        IntegrationInstance.objects.create(
            name="总部通讯录",
            provider_key="feishu",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"login_auth": IntegrationInstanceStatusChoices.PENDING_VERIFICATION},
            capability_enabled={"login_auth": True},
            enabled=True,
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")

        assert response.status_code == 200
        assert len(response.data) == 0

    def test_excludes_builtin_provider(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        IntegrationInstance.objects.create(
            name="平台内建",
            provider_key="bk_lite_builtin",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
            capability_enabled={"login_auth": True},
            enabled=True,
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")

        assert response.status_code == 200
        assert not any(item["provider_key"] == "bk_lite_builtin" for item in response.data)

    def test_requires_capability_parameter(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/")

        assert response.status_code == 400
