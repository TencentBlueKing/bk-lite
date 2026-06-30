from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.fixture
def draft_instance(db):
    return IntegrationInstance.objects.create(
        name="总部通讯录",
        provider_key="feishu",
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.READY,
            "im_notification": IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
        },
        capability_enabled={
            "login_auth": True,
            "user_sync": True,
            "im_notification": True,
        },
        enabled=True,
        team=[1],
        description="feishu instance",
    )


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

    def test_available_instances_includes_ready_ad_for_user_sync(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        IntegrationInstance.objects.create(
            name="Corporate AD",
            provider_key="ad",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"user_sync": IntegrationInstanceStatusChoices.READY},
            capability_enabled={"user_sync": True},
            enabled=True,
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=user_sync")

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["provider_key"] == "ad"
        assert response.data[0]["provider_name"] == "Active Directory"


@pytest.mark.django_db
class TestIntegrationInstanceViewSet:
    def test_list_filters_by_accessible_team(self, api_client, authenticated_user, draft_instance):
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
        authenticated_user.save(update_fields=["group_list"])

        hidden = IntegrationInstance.objects.create(
            name="隐藏实例",
            provider_key="feishu",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
            capability_enabled={"login_auth": True},
            enabled=True,
            team=[2],
        )
        IntegrationInstance.objects.create(
            name="内建实例",
            provider_key="bk_lite_builtin",
            config={},
            status=IntegrationInstanceStatusChoices.READY,
            capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
            capability_enabled={"login_auth": True},
            enabled=True,
            team=[1],
        )

        response = api_client.get("/api/v1/system_mgmt/integration_instance/")

        assert response.status_code == 200
        payload = response.data if isinstance(response.data, list) else response.data.get("results", response.data["items"])
        returned_ids = {item["id"] for item in payload}
        assert draft_instance.id in returned_ids
        assert hidden.id not in returned_ids

    @patch("apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri")
    def test_retrieve_returns_instance_for_team_member(
        self,
        mock_get_login_auth_callback_uri,
        api_client,
        authenticated_user,
        draft_instance,
    ):
        mock_get_login_auth_callback_uri.return_value = "http://testserver/api/v1/core/api/login_auth/callback/"
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
        authenticated_user.save(update_fields=["group_list"])

        response = api_client.get(f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/")

        assert response.status_code == 200
        assert response.data["id"] == draft_instance.id
        assert response.data["login_auth_callback_url"] == "http://testserver/api/v1/core/api/login_auth/callback/"

    def test_retrieve_rejects_instance_outside_user_team(self, api_client, authenticated_user, draft_instance):
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.group_list = [{"id": 999, "name": "Other Team"}]
        authenticated_user.save(update_fields=["group_list"])

        response = api_client.get(f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/")

        assert response.status_code == 403
        assert response.json()["result"] is False

    def test_create_draft_logs_operation(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-Add"}}
        authenticated_user.save(update_fields=["is_superuser"])

        with patch("apps.system_mgmt.viewset.integration_instance_viewset.log_operation") as mock_log:
            response = api_client.post(
                "/api/v1/system_mgmt/integration_instance/",
                {
                    "name": "新实例",
                    "provider_key": "feishu",
                    "description": "draft",
                    "config": {},
                    "team": [1],
                    "is_draft": True,
                },
                format="json",
            )

        assert response.status_code == 201
        assert IntegrationInstance.objects.filter(name="新实例").exists() is True
        mock_log.assert_called_once()

    def test_update_rejects_instance_outside_user_team(self, api_client, authenticated_user, draft_instance):
        authenticated_user.permission = {"system-manager": {"integration_center-Edit"}}
        authenticated_user.group_list = [{"id": 2, "name": "Other Team"}]
        authenticated_user.save(update_fields=["group_list"])

        response = api_client.put(
            f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/",
            {
                "name": draft_instance.name,
                "provider_key": draft_instance.provider_key,
                "description": draft_instance.description,
                "config": draft_instance.config,
                "enabled": draft_instance.enabled,
                "team": draft_instance.team,
                "status": draft_instance.status,
                "capability_status": draft_instance.capability_status,
                "capability_enabled": draft_instance.capability_enabled,
            },
            format="json",
        )

        assert response.status_code == 403

    def test_update_logs_operation_for_superuser(self, api_client, authenticated_user, draft_instance):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-Edit"}}
        authenticated_user.save(update_fields=["is_superuser"])

        with patch("apps.system_mgmt.viewset.integration_instance_viewset.log_operation") as mock_log:
            response = api_client.put(
                f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/",
                {
                    "name": "修改后实例",
                    "provider_key": draft_instance.provider_key,
                    "description": draft_instance.description,
                    "config": draft_instance.config,
                    "enabled": draft_instance.enabled,
                    "team": draft_instance.team,
                    "status": draft_instance.status,
                    "capability_status": draft_instance.capability_status,
                    "capability_enabled": draft_instance.capability_enabled,
                },
                format="json",
            )

        assert response.status_code == 200
        draft_instance.refresh_from_db()
        assert draft_instance.name == "修改后实例"
        mock_log.assert_called_once()

    def test_destroy_rejects_instance_outside_user_team(self, api_client, authenticated_user, draft_instance):
        authenticated_user.permission = {"system-manager": {"integration_center-Delete"}}
        authenticated_user.group_list = [{"id": 2, "name": "Other Team"}]
        authenticated_user.save(update_fields=["group_list"])

        response = api_client.delete(f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/")

        assert response.status_code == 403
        assert IntegrationInstance.objects.filter(id=draft_instance.id).exists() is True

    def test_destroy_logs_operation_for_superuser(self, api_client, authenticated_user, draft_instance):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-Delete"}}
        authenticated_user.save(update_fields=["is_superuser"])

        with patch("apps.system_mgmt.viewset.integration_instance_viewset.log_operation") as mock_log:
            response = api_client.delete(f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/")

        assert response.status_code == 200
        assert IntegrationInstance.objects.filter(id=draft_instance.id).exists() is False
        mock_log.assert_called_once()

    def test_providers_returns_public_manifests(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        response = api_client.get("/api/v1/system_mgmt/integration_instance/providers/")

        assert response.status_code == 200
        provider_keys = {item["key"] for item in response.data}
        assert {"feishu", "wechat"}.issubset(provider_keys)

    def test_status_returns_current_instance_status(self, api_client, authenticated_user, draft_instance):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-View"}}
        authenticated_user.save(update_fields=["is_superuser"])

        response = api_client.get(f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/status/")

        assert response.status_code == 200
        assert response.data == {
            "status": draft_instance.status,
            "enabled": draft_instance.enabled,
            "capability_status": draft_instance.capability_status,
        }

    def test_test_connection_updates_single_capability_status(self, api_client, authenticated_user, draft_instance):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-Edit"}}
        authenticated_user.save(update_fields=["is_superuser"])
        draft_instance.capability_status = {
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
        }
        draft_instance.status = IntegrationInstanceStatusChoices.PENDING_VERIFICATION
        draft_instance.save(update_fields=["capability_status", "status"])

        result = CapabilityExecutionResult.success_result(
            "ok",
            payload={"capability_status": {"user_sync": IntegrationInstanceStatusChoices.READY}},
        )

        with patch(
            "apps.system_mgmt.viewset.integration_instance_viewset.RuntimeApplicationService.test_connection",
            return_value=result,
        ), patch("apps.system_mgmt.viewset.integration_instance_viewset.log_operation") as mock_log:
            response = api_client.post(
                f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/test_connection/",
                {"capability_key": "user_sync"},
                format="json",
            )

        assert response.status_code == 200
        draft_instance.refresh_from_db()
        assert draft_instance.capability_status["user_sync"] == IntegrationInstanceStatusChoices.READY
        assert draft_instance.status == IntegrationInstanceStatusChoices.READY
        mock_log.assert_called_once()

    def test_test_connection_updates_instance_status_for_full_check(self, api_client, authenticated_user, draft_instance):
        authenticated_user.is_superuser = True
        authenticated_user.permission = {"system-manager": {"integration_center-Edit"}}
        authenticated_user.save(update_fields=["is_superuser"])

        result = CapabilityExecutionResult(
            success=False,
            summary="failed",
            payload={
                "instance_status": IntegrationInstanceStatusChoices.VERIFICATION_FAILED,
                "capability_status": {"login_auth": IntegrationInstanceStatusChoices.VERIFICATION_FAILED},
            },
        )

        with patch(
            "apps.system_mgmt.viewset.integration_instance_viewset.RuntimeApplicationService.test_connection",
            return_value=result,
        ):
            response = api_client.post(
                f"/api/v1/system_mgmt/integration_instance/{draft_instance.id}/test_connection/",
                {},
                format="json",
            )

        assert response.status_code == 200
        draft_instance.refresh_from_db()
        assert draft_instance.status == IntegrationInstanceStatusChoices.VERIFICATION_FAILED
        assert draft_instance.capability_status == {"login_auth": IntegrationInstanceStatusChoices.VERIFICATION_FAILED}
