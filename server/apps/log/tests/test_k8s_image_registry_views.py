from types import SimpleNamespace
from unittest.mock import Mock

from apps.log.views.k8s_collect import K8sCollectViewSet


def _request(data):
    return SimpleNamespace(data=data, method="POST")


def test_generate_install_command_forwards_image_registry_prefix(monkeypatch):
    instance = SimpleNamespace(id="instance-1")
    authorize = Mock(return_value=([instance], None))
    generate = Mock(return_value="kubectl apply")
    monkeypatch.setattr(
        "apps.log.views.k8s_collect.CollectInstanceViewSet._authorize_instances",
        authorize,
    )
    monkeypatch.setattr(
        "apps.log.views.k8s_collect.K8sLogCollectService.generate_install_command",
        generate,
    )

    response = K8sCollectViewSet().generate_install_command(
        _request(
            {
                "instance_id": instance.id,
                "cloud_region_id": 1,
                "image_registry_prefix": "harbor.internal/bklite",
            }
        )
    )

    assert response.status_code == 200
    authorize.assert_called_once()
    generate.assert_called_once_with(instance.id, 1, "harbor.internal/bklite")


def test_save_setting_command_forwards_image_registry_prefix(monkeypatch):
    instance = SimpleNamespace(id="instance-1")
    monkeypatch.setattr(
        "apps.log.views.k8s_collect.CollectInstanceViewSet._authorize_instances",
        Mock(return_value=([instance], None)),
    )
    monkeypatch.setattr(
        "apps.log.views.k8s_collect.K8sLogCollectService.save_setting",
        Mock(return_value={"instance_id": instance.id}),
    )
    generate = Mock(return_value="kubectl apply")
    monkeypatch.setattr(
        "apps.log.views.k8s_collect.K8sLogCollectService.generate_install_command",
        generate,
    )

    response = K8sCollectViewSet().collect_setting(
        _request(
            {
                "instance_id": instance.id,
                "cloud_region_id": 1,
                "image_registry_prefix": "harbor.internal/bklite",
            }
        )
    )

    assert response.status_code == 200
    generate.assert_called_once_with(instance.id, 1, "harbor.internal/bklite")
