from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Lock

import pydantic.root_model  # noqa

import pytest

from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.services.k8s_collect import K8sLogCollectService as K8s


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


# ----------------------- _build_cache_key -----------------------


def test_build_cache_key():
    assert K8s._build_cache_key("tok") == "log_k8s_install_token:tok"


# ----------------------- generate_install_token / validate_and_get_token_data -----------------------


def test_token_lifecycle_increments_usage():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    cache_key = K8s._build_cache_key(token)
    assert cache.get(cache_key)["cluster_name"] == "cluster-a"

    data = K8s.validate_and_get_token_data(token)
    assert data["cluster_name"] == "cluster-a"
    assert data["cloud_region_id"] == "cr-1"
    assert data["remaining_usage"] == K8s.TOKEN_MAX_USAGE - 1


class BarrierCache:
    def __init__(self, readers):
        self._barrier = Barrier(readers)
        self._lock = Lock()
        self._store = {}
        self.synchronized_key = None

    def get(self, key):
        with self._lock:
            value = deepcopy(self._store.get(key))
        if key == self.synchronized_key:
            self._barrier.wait(timeout=5)
        return value

    def set(self, key, value, timeout=None):
        with self._lock:
            self._store[key] = deepcopy(value)

    def add(self, key, value, timeout=None):
        with self._lock:
            if key in self._store:
                return False
            self._store[key] = deepcopy(value)
            return True

    def incr(self, key):
        with self._lock:
            if key not in self._store:
                raise ValueError
            self._store[key] += 1
            return self._store[key]

    def delete(self, key):
        with self._lock:
            self._store.pop(key, None)


def test_concurrent_validation_never_exceeds_max_usage(mocker):
    attempts = K8s.TOKEN_MAX_USAGE * 2
    fake_cache = BarrierCache(attempts)
    mocker.patch("apps.log.services.k8s_collect.cache", fake_cache)

    token = K8s.generate_install_token("cluster-a", "cr-1")
    cache_key = K8s._build_cache_key(token)
    fake_cache.synchronized_key = cache_key

    def consume():
        try:
            return K8s.validate_and_get_token_data(token)["remaining_usage"]
        except BaseAppException:
            return None

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        remaining_usage = list(executor.map(lambda _: consume(), range(attempts)))

    assert sorted(value for value in remaining_usage if value is not None) == list(range(K8s.TOKEN_MAX_USAGE))
    assert fake_cache.get(f"{cache_key}:usage_count") == attempts


def test_validation_does_not_extend_token_ttl(mocker):
    token = K8s.generate_install_token("cluster-a", "cr-1")

    cache_set = mocker.patch.object(cache, "set", wraps=cache.set)
    K8s.validate_and_get_token_data(token)

    cache_set.assert_not_called()


def test_legacy_payload_usage_count_seeds_atomic_counter():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    cache_key = K8s._build_cache_key(token)
    payload = cache.get(cache_key)
    payload["usage_count"] = 2
    cache.set(cache_key, payload, timeout=K8s.TOKEN_EXPIRE_TIME)

    data = K8s.validate_and_get_token_data(token)

    assert cache.get(f"{cache_key}:usage_count") == 3
    assert data["remaining_usage"] == K8s.TOKEN_MAX_USAGE - 3


def test_validation_fails_closed_when_atomic_counter_is_missing(mocker):
    token = K8s.generate_install_token("cluster-a", "cr-1")
    mocker.patch.object(cache, "incr", side_effect=ValueError)

    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data(token)


def test_validate_token_missing_raises():
    with pytest.raises(BaseAppException, match="Token is required"):
        K8s.validate_and_get_token_data("")


def test_validate_token_not_found_raises(mocker):
    mocker.patch("apps.log.services.k8s_collect.cache.get", return_value=None)
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data("nope")


def test_validate_token_exceeds_max_usage_deletes_and_raises():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    for _ in range(K8s.TOKEN_MAX_USAGE):
        K8s.validate_and_get_token_data(token)

    with pytest.raises(BaseAppException, match="maximum usage limit"):
        K8s.validate_and_get_token_data(token)
    assert cache.get(K8s._build_cache_key(token)) is None


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
    mocker.patch(
        "apps.log.services.k8s_collect.CollectInstance.objects.filter"
    ).return_value.first.return_value = inst
    mocker.patch.object(K8s, "get_cloud_region_envconfig", return_value=dict(_FULL_ENV))
    mocker.patch.object(K8s, "generate_install_token", return_value="tok-123")
    cmd = K8s.generate_install_command("inst-1", "cr1")
    assert "curl -sSLk -X POST" in cmd
    assert "http://node/api/v1/log/open_api/k8s/render/" in cmd
    assert "tok-123" in cmd
    assert "kubectl apply -f -" in cmd


def test_generate_install_command_missing_instance(mocker):
    mocker.patch(
        "apps.log.services.k8s_collect.CollectInstance.objects.filter"
    ).return_value.first.return_value = None
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
