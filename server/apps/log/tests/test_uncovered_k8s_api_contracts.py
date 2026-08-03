"""补齐 Kubernetes 日志配置开放接口的输入与响应契约。"""

from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.views.open_api_k8s import K8sOpenAPIViewSet


pytestmark = pytest.mark.unit


def test_k8s_render_requires_token():
    with pytest.raises(BaseAppException, match="token"):
        K8sOpenAPIViewSet().render(SimpleNamespace(data={}))


def test_k8s_render_forwards_profile_and_reports_remaining_usage(monkeypatch):
    calls = []

    class Service:
        @staticmethod
        def validate_and_get_token_data(token):
            assert token == "signed-token"
            return {
                "cluster_name": "prod",
                "cloud_region_id": 7,
                "remaining_usage": 2,
            }

        @staticmethod
        def render_config_from_cloud_region(*args):
            calls.append(args)
            return "kind: ConfigMap\n"

    monkeypatch.setattr(
        "apps.log.views.open_api_k8s.K8sLogCollectService",
        Service,
    )
    request = SimpleNamespace(
        data={
            "token": "signed-token",
            "runtime_profile": "containerd",
            "host_log_path": "/var/log",
            "docker_container_log_path": "/docker",
        }
    )

    response = K8sOpenAPIViewSet().render(request)

    assert response.content == b"kind: ConfigMap\n"
    assert response["X-Token-Remaining-Usage"] == "2"
    assert calls == [("prod", 7, "containerd", "/var/log", "/docker")]
