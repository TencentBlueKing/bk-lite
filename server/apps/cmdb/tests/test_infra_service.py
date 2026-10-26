"""cmdb.services.infra.InfraService 测试（token 生命周期 + 渲染分支）。

规格：
- generate_install_token：写入缓存且 usage_count=0，返回 uuid token；
- validate_and_get_token_data：空 token / 无缓存 / 超额 -> BaseAppException；
  正常扣减后 remaining_usage 按次数减少，且不重写令牌键；
  usage_count 距上限还剩 1 次时，并发只能成功一次；
- render_config_from_cloud_region：缺失环境变量 -> 异常；齐全则透传调用 API；
- render_config_from_api：缺 url / 非 200 / 缺 yaml / Timeout / RequestException
  / json 解析失败 各自映射到 BaseAppException。
仅 mock 真实边界：cache、NodeMgmt RPC、requests.post。
"""
import pydantic.root_model  # noqa

import pytest

from apps.cmdb.constants.infra import InfraConstants
from apps.cmdb.services.infra import CACHE_KEY_PREFIX, InfraService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


class TestGenerateToken:
    def test_生成并写缓存(self, mocker):
        cache_set = mocker.patch("apps.cmdb.services.infra.cache.set")
        token = InfraService.generate_install_token("cluster-a", "1")
        assert isinstance(token, str) and len(token) > 0
        cache_set.assert_called_once()
        key, value = cache_set.call_args.args
        assert key == f"{CACHE_KEY_PREFIX}{token}"
        assert value["cluster_name"] == "cluster-a"
        assert value["cloud_region_id"] == "1"
        assert value["usage_count"] == 0
        assert value["max_usage"] == InfraConstants.TOKEN_MAX_USAGE
        assert cache_set.call_args.kwargs["timeout"] == InfraConstants.TOKEN_EXPIRE_TIME


class _MutexTokenCache:
    """假缓存：get 返回副本，add 与 incr 在同一把锁里互斥。"""

    def __init__(self, initial, timeouts, rendezvous_keys=()):
        import copy
        import threading

        self._copy = copy.deepcopy
        self.data = copy.deepcopy(initial)
        self.timeouts = dict(timeouts)
        self._lock = threading.Lock()
        self._rendezvous_keys = set(rendezvous_keys)
        self._barrier = threading.Barrier(2) if rendezvous_keys else None
        self.token_writes = []

    def get(self, key, default=None):
        with self._lock:
            value = self._copy(self.data.get(key, default))
        if self._barrier is not None and key in self._rendezvous_keys:
            self._barrier.wait(timeout=5)
        return value

    def set(self, key, value, timeout=None):
        stored = self._copy(value)
        with self._lock:
            self.data[key] = stored
            self.timeouts[key] = timeout
            self.token_writes.append((key, stored, timeout))

    def add(self, key, value, timeout=None):
        with self._lock:
            if key in self.data:
                return False
            self.data[key] = self._copy(value)
            self.timeouts[key] = timeout
            return True

    def incr(self, key, delta=1):
        with self._lock:
            if key not in self.data or isinstance(self.data[key], bool):
                raise ValueError(f"Key '{key}' not found")
            if not isinstance(self.data[key], int):
                raise ValueError(f"Key '{key}' is not an integer")
            self.data[key] += delta
            return self.data[key]

    def delete(self, key):
        with self._lock:
            self.data.pop(key, None)
            self.timeouts.pop(key, None)


class TestValidateToken:
    def test_空token_报错(self):
        with pytest.raises(BaseAppException, match="Token is required"):
            InfraService.validate_and_get_token_data("")

    def test_缓存不存在_报错(self, mocker, caplog):
        import logging

        sentinel = "SENTINEL_CMDB_5952_ZzQ9mK2p"
        mocker.patch("apps.cmdb.services.infra.cache.get", return_value=None)
        with caplog.at_level(logging.WARNING, logger="cmdb"):
            with pytest.raises(BaseAppException, match="Invalid or expired token"):
                InfraService.validate_and_get_token_data(sentinel)
        assert sentinel not in caplog.text
        assert sentinel[:8] not in caplog.text

    def test_超过最大使用_删除并报错(self, mocker):
        mocker.patch(
            "apps.cmdb.services.infra.cache.get",
            return_value={
                "cluster_name": "c",
                "cloud_region_id": "1",
                "usage_count": 5,
                "max_usage": 5,
            },
        )
        delete = mocker.patch("apps.cmdb.services.infra.cache.delete")
        with pytest.raises(BaseAppException, match="exceeded maximum usage"):
            InfraService.validate_and_get_token_data("abcdef1234")
        delete.assert_called_once()

    def test_最后一次额度不能被两个请求一起用掉(self, mocker):
        from concurrent.futures import ThreadPoolExecutor

        token = "abcdef1234"
        token_key = f"{CACHE_KEY_PREFIX}{token}"
        original_timeout = 100
        fake = _MutexTokenCache(
            {
                token_key: {
                    "cluster_name": "cluster-x",
                    "cloud_region_id": "9",
                    "usage_count": 4,
                    "max_usage": 5,
                }
            },
            {token_key: original_timeout},
            rendezvous_keys=(token_key,),
        )
        mocker.patch("apps.cmdb.services.infra.cache", fake)

        def consume():
            try:
                return ("ok", InfraService.validate_and_get_token_data(token))
            except BaseAppException as exc:
                return ("err", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))

        successes = [item for kind, item in results if kind == "ok"]
        failures = [item for kind, item in results if kind == "err"]
        assert len(successes) == 1, {"results": results, "token_writes": fake.token_writes}
        assert successes == [
            {
                "cluster_name": "cluster-x",
                "cloud_region_id": "9",
                "remaining_usage": 0,
            }
        ]
        assert len(failures) == 1
        assert "exceeded maximum usage" in failures[0]
        assert fake.token_writes == []
        assert fake.timeouts.get(token_key, original_timeout) == original_timeout

    def test_正常使用_计数加一并返回剩余(self, mocker):
        token = "abcdef1234"
        token_key = f"{CACHE_KEY_PREFIX}{token}"
        original_timeout = 100
        fake = _MutexTokenCache(
            {
                token_key: {
                    "cluster_name": "cluster-x",
                    "cloud_region_id": "9",
                    "usage_count": 1,
                    "max_usage": 5,
                }
            },
            {token_key: original_timeout},
        )
        mocker.patch("apps.cmdb.services.infra.cache", fake)

        out = InfraService.validate_and_get_token_data(token)

        assert out == {
            "cluster_name": "cluster-x",
            "cloud_region_id": "9",
            "remaining_usage": 3,
        }
        assert fake.data[token_key]["usage_count"] == 1
        assert fake.timeouts[token_key] == original_timeout
        assert fake.token_writes == []
        assert fake.data[f"{token_key}:usage_count"] == 2


class TestRenderFromCloudRegion:
    def _patch_nodemgmt(self, mocker, env):
        rpc = mocker.MagicMock()
        rpc.get_cloud_region_envconfig.return_value = env
        mocker.patch("apps.cmdb.services.infra.NodeMgmt", return_value=rpc)
        return rpc

    def test_缺失环境变量_报错(self, mocker):
        self._patch_nodemgmt(mocker, {"NATS_USERNAME": "u"})
        with pytest.raises(BaseAppException, match="Missing required environment"):
            InfraService.render_config_from_cloud_region("c", "1")

    def test_齐全_透传参数调用api(self, mocker):
        self._patch_nodemgmt(
            mocker,
            {
                "NATS_USERNAME": "u",
                "NATS_PASSWORD": "p",
                "NATS_SERVERS": "nats://x:4222",
                "NATS_TLS_CA": "ca-content",
                "WEBHOOK_SERVER_URL": "https://hook",
            },
        )
        render = mocker.patch.object(
            InfraService, "render_config_from_api", return_value="yaml-out"
        )
        out = InfraService.render_config_from_cloud_region("c1", "1", config_type="node")
        assert out == "yaml-out"
        params, base_url = render.call_args.args
        assert base_url == "https://hook"
        assert params["nats_username"] == "u"
        assert params["nats_url"] == "nats://x:4222"
        assert params["nats_ca"] == "ca-content"
        assert params["type"] == "node"
        assert params["cluster_name"] == "c1"


class TestRenderFromApi:
    def _resp(self, mocker, status=200, json_data=None, json_exc=None):
        resp = mocker.MagicMock()
        resp.status_code = status
        resp.text = "err-body"
        if json_exc:
            resp.json.side_effect = json_exc
        else:
            resp.json.return_value = json_data or {}
        return resp

    def test_缺url_报错(self):
        with pytest.raises(BaseAppException, match="URL is required"):
            InfraService.render_config_from_api({}, None)

    def test_非200_报错带状态(self, mocker):
        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            return_value=self._resp(mocker, status=500),
        )
        with pytest.raises(BaseAppException, match="returned status 500"):
            InfraService.render_config_from_api({}, "https://hook")

    def test_缺yaml字段_报错(self, mocker):
        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            return_value=self._resp(mocker, json_data={"other": 1}),
        )
        with pytest.raises(BaseAppException, match="missing 'yaml'"):
            InfraService.render_config_from_api({}, "https://hook")

    def test_正常返回yaml(self, mocker):
        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            return_value=self._resp(mocker, json_data={"yaml": "kind: DaemonSet"}),
        )
        out = InfraService.render_config_from_api({"cluster_name": "c"}, "https://hook/")
        assert out == "kind: DaemonSet"

    def test_超时映射异常(self, mocker):
        import requests

        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            side_effect=requests.Timeout("slow"),
        )
        with pytest.raises(BaseAppException, match="timeout"):
            InfraService.render_config_from_api({}, "https://hook")

    def test_请求异常映射(self, mocker):
        import requests

        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            side_effect=requests.ConnectionError("refused"),
        )
        with pytest.raises(BaseAppException, match="request failed"):
            InfraService.render_config_from_api({}, "https://hook")

    def test_json解析失败映射(self, mocker):
        mocker.patch(
            "apps.cmdb.services.infra.requests.post",
            return_value=self._resp(mocker, json_exc=ValueError("bad json")),
        )
        with pytest.raises(BaseAppException, match="Failed to parse response"):
            InfraService.render_config_from_api({}, "https://hook")
