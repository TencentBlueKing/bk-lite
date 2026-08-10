import pydantic.root_model  # noqa
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.services.k8s_collect import K8sLogCollectService as K8s

pytestmark = pytest.mark.django_db

RENDER_URL = "/api/v1/log/open_api/k8s/render/"


def test_render_route_keeps_request_and_remaining_usage_header(api_client, mocker):
    mocker.patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async.delay")
    token = K8s.generate_install_token("cluster-a", "cr-1")
    render = mocker.patch.object(
        K8s,
        "render_config_from_cloud_region",
        return_value="apiVersion: v1",
    )

    responses = [api_client.post(RENDER_URL, {"token": token}, format="json") for _ in range(K8s.TOKEN_MAX_USAGE)]

    assert [response.status_code for response in responses] == [200] * K8s.TOKEN_MAX_USAGE
    assert [response["X-Token-Remaining-Usage"] for response in responses] == ["4", "3", "2", "1", "0"]
    assert all(response.content == b"apiVersion: v1" for response in responses)
    assert all(response["Content-Type"] == "text/yaml; charset=utf-8" for response in responses)

    rejected = api_client.post(RENDER_URL, {"token": token}, format="json")

    assert rejected.status_code == 500
    assert rejected.json()["message"] == "Token has exceeded maximum usage limit (5 times)"
    assert render.call_count == K8s.TOKEN_MAX_USAGE


def test_render_failure_still_consumes_attempt(api_client, mocker):
    mocker.patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async.delay")
    token = K8s.generate_install_token("cluster-a", "cr-1")
    mocker.patch.object(
        K8s,
        "render_config_from_cloud_region",
        side_effect=[BaseAppException("remote failure"), "apiVersion: v1"],
    )

    failed = api_client.post(RENDER_URL, {"token": token}, format="json")
    response = api_client.post(RENDER_URL, {"token": token}, format="json")

    assert failed.status_code == 500
    assert failed.json()["message"] == "remote failure"
    assert response.status_code == 200
    assert response["X-Token-Remaining-Usage"] == "3"
