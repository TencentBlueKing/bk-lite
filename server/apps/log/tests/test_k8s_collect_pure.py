import pydantic.root_model  # noqa
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.services.k8s_collect import K8sLogCollectService as K8s


@pytest.fixture(autouse=True)
def saved_render_options(mocker):
    mocker.patch.object(
        K8s,
        "load_setting_render_options",
        return_value={
            "runtime_profile": "standard",
            "host_log_path": None,
            "docker_container_log_path": None,
            "namespace_patterns": [],
            "pod_patterns": [],
        },
    )


# ----------------------- validate_cluster_name -----------------------


def test_validate_cluster_name_empty_raises():
    with pytest.raises(BaseAppException, match="集群名称不能为空"):
        K8s.validate_cluster_name("")


def test_validate_cluster_name_ok():
    assert K8s.validate_cluster_name("c1") is None


# ----------------------- validate_host_path -----------------------


def test_validate_host_path_empty_raises():
    with pytest.raises(BaseAppException, match="不能为空"):
        K8s.validate_host_path("", "节点路径")


def test_validate_host_path_relative_raises():
    with pytest.raises(BaseAppException, match="必须为绝对路径"):
        K8s.validate_host_path("var/log", "节点路径")


def test_validate_host_path_unsafe_chars_raises():
    with pytest.raises(BaseAppException, match="包含非法字符"):
        K8s.validate_host_path("/var/log\n'; rm", "节点路径")


def test_validate_host_path_strips_and_returns():
    assert K8s.validate_host_path("  /var/log  ", "节点路径") == "/var/log"


# ----------------------- normalize_render_options -----------------------


def test_normalize_render_options_default_standard():
    out = K8s.normalize_render_options()
    assert out == {
        "runtime_profile": "standard",
        "host_log_path": None,
        "docker_container_log_path": None,
    }


def test_normalize_render_options_invalid_profile():
    with pytest.raises(BaseAppException, match="日志运行环境配置不正确"):
        K8s.normalize_render_options(runtime_profile="weird")


def test_normalize_render_options_docker_profile_no_paths():
    out = K8s.normalize_render_options(runtime_profile="DOCKER")
    assert out["runtime_profile"] == "docker"
    assert out["host_log_path"] is None


def test_normalize_render_options_custom_requires_host_path():
    with pytest.raises(BaseAppException, match="不能为空"):
        K8s.normalize_render_options(runtime_profile="custom", host_log_path="")


def test_normalize_render_options_custom_with_paths():
    out = K8s.normalize_render_options(
        runtime_profile="custom",
        host_log_path="/var/log/pods",
        docker_container_log_path="/var/lib/docker/containers",
    )
    assert out["runtime_profile"] == "custom"
    assert out["host_log_path"] == "/var/log/pods"
    assert out["docker_container_log_path"] == "/var/lib/docker/containers"


def test_normalize_render_options_custom_optional_docker_path_none():
    out = K8s.normalize_render_options(runtime_profile="custom", host_log_path="/var/log/pods")
    assert out["docker_container_log_path"] is None


# ----------------------- get_cloud_region_envconfig -----------------------


_FULL_ENV = {
    "NODE_SERVER_URL": "http://node",
    "WEBHOOK_SERVER_URL": "http://hook",
    "NATS_USERNAME": "u",
    "NATS_PASSWORD": "p",
    "NATS_SERVERS": "nats://s",
}


def test_get_cloud_region_envconfig_ok(mocker):
    node = mocker.patch("apps.log.services.k8s_collect.NodeMgmt").return_value
    node.get_cloud_region_envconfig.return_value = dict(_FULL_ENV)
    out = K8s.get_cloud_region_envconfig("cr1")
    assert out == _FULL_ENV


def test_get_cloud_region_envconfig_missing_vars(mocker):
    node = mocker.patch("apps.log.services.k8s_collect.NodeMgmt").return_value
    partial = dict(_FULL_ENV)
    del partial["NATS_PASSWORD"]
    node.get_cloud_region_envconfig.return_value = partial
    with pytest.raises(BaseAppException, match="NATS_PASSWORD"):
        K8s.get_cloud_region_envconfig("cr1")


# ----------------------- generate_install_command -----------------------


def test_generate_install_command_builds_curl(mocker):
    inst = mocker.MagicMock(id="inst-1")
    mocker.patch("apps.log.services.k8s_collect.CollectInstance.objects.filter").return_value.first.return_value = inst
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch.object(K8s, "generate_install_token", return_value="tok-123")
    cmd = K8s.generate_install_command("inst-1", "cr1", "harbor.internal/bklite")
    assert "curl -sSLk -X POST" in cmd
    assert "http://node/api/v1/log/open_api/k8s/render/" in cmd
    assert "tok-123" in cmd
    assert "kubectl apply -f -" in cmd
    K8s.generate_install_token.assert_called_once_with("inst-1", "cr1", "harbor.internal/bklite")


def test_generate_install_command_missing_instance(mocker):
    mocker.patch("apps.log.services.k8s_collect.CollectInstance.objects.filter").return_value.first.return_value = None
    K8s.load_setting_render_options.side_effect = None
    with pytest.raises(BaseAppException, match="实例不存在"):
        K8s.generate_install_command("missing", "cr1")


# ----------------------- render_config_from_cloud_region (mock requests) -----------------------


def test_render_config_from_cloud_region_success(mocker):
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    resp = mocker.MagicMock(status_code=200)
    resp.json.return_value = {"yaml": "apiVersion: v1"}
    post = mocker.patch("apps.log.services.k8s_collect.requests.post", return_value=resp)
    out = K8s.render_config_from_cloud_region("clusterA", "cr1")
    assert out == "apiVersion: v1"
    assert post.call_args.args[0] == "http://hook/infra/kubernetes"
    assert post.call_args.kwargs["json"]["image_registry_prefix"] == "bk-lite.tencentcloudcr.com/bklite"


def test_render_config_forwards_custom_image_registry(mocker):
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    response = mocker.MagicMock(status_code=200)
    response.json.return_value = {"yaml": "apiVersion: v1"}
    post = mocker.patch("apps.log.services.k8s_collect.requests.post", return_value=response)

    K8s.render_config_from_cloud_region("clusterA", "cr1", "harbor.internal/bklite")

    assert post.call_args.kwargs["json"]["image_registry_prefix"] == "harbor.internal/bklite"


def test_render_config_non_200_raises(mocker):
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    resp = mocker.MagicMock(status_code=500, text="err")
    mocker.patch("apps.log.services.k8s_collect.requests.post", return_value=resp)
    with pytest.raises(BaseAppException, match="status 500"):
        K8s.render_config_from_cloud_region("c", "cr1")


def test_render_config_missing_yaml_field(mocker):
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    resp = mocker.MagicMock(status_code=200)
    resp.json.return_value = {}
    mocker.patch("apps.log.services.k8s_collect.requests.post", return_value=resp)
    with pytest.raises(BaseAppException, match="missing 'yaml' field"):
        K8s.render_config_from_cloud_region("c", "cr1")


def test_render_config_timeout(mocker):
    import requests as real_requests

    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    mocker.patch(
        "apps.log.services.k8s_collect.requests.post",
        side_effect=real_requests.Timeout("slow"),
    )
    with pytest.raises(BaseAppException, match="timeout"):
        K8s.render_config_from_cloud_region("c", "cr1")


def test_render_config_request_exception(mocker):
    import requests as real_requests

    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch("apps.log.services.k8s_collect.get_webhook_tls_verify", return_value=True)
    mocker.patch(
        "apps.log.services.k8s_collect.requests.post",
        side_effect=real_requests.RequestException("boom"),
    )
    with pytest.raises(BaseAppException, match="request failed"):
        K8s.render_config_from_cloud_region("c", "cr1")
