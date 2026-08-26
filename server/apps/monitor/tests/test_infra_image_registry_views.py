from types import SimpleNamespace
from unittest.mock import Mock

from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.views.infra import InfraViewSet


def test_monitor_render_uses_token_bound_registry_and_ignores_request_override(monkeypatch):
    captured = {}

    class Service:
        @staticmethod
        def validate_and_get_token_data(token):
            assert token == "signed-token"
            return {
                "cluster_name": "prod",
                "cloud_region_id": "7",
                "image_registry_prefix": "harbor.internal/bklite",
                "remaining_usage": 2,
            }

        @staticmethod
        def render_config_from_cloud_region(**kwargs):
            captured.update(kwargs)
            return "kind: DaemonSet\n"

    monkeypatch.setattr("apps.monitor.views.infra.InfraService", Service)
    request = SimpleNamespace(
        data={
            "token": "signed-token",
            "image_registry_prefix": "attacker.example/override",
        }
    )

    response = InfraViewSet().render(request)

    assert response.content == b"kind: DaemonSet\n"
    assert response["X-Token-Remaining-Usage"] == "2"
    assert captured == {
        "cluster_name": "prod",
        "cloud_region_id": "7",
        "config_type": "metric",
        "image_registry_prefix": "harbor.internal/bklite",
    }


def test_monitor_install_command_binds_registry_to_generated_token(monkeypatch):
    generate_token = Mock(return_value="signed-token")
    monkeypatch.setattr(
        "apps.monitor.services.manual_collect.parse_instance_id",
        Mock(return_value=("prod-k8s", "ignored")),
    )
    monkeypatch.setattr(
        "apps.monitor.services.manual_collect.InfraService.generate_install_token",
        generate_token,
    )
    node_mgmt = Mock()
    node_mgmt.return_value.get_cloud_region_public_config.return_value = {
        "NODE_SERVER_URL": "https://node.internal/base",
    }
    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", node_mgmt)

    command = ManualCollectService.generate_install_command(
        "prod-k8s-instance",
        "7",
        "harbor.internal/bklite",
    )

    generate_token.assert_called_once_with(
        "prod-k8s",
        "7",
        "harbor.internal/bklite",
    )
    assert "https://node.internal/base/api/v1/monitor/open_api/infra/render/" in command
    assert "signed-token" in command
