# -- coding: utf-8 --
# @File: test_api_http_layer.py
# @Issue: #3526 - HTTP-layer contract tests for agents/stargazer/api/
#
# 测试范围：
#   - agents/stargazer/api/collect.py  : collect_info, credential_results
#   - agents/stargazer/api/monitor.py  : vmware/metrics, qcloud/metrics
#   - agents/stargazer/api/health.py   : /, /ready, /stats, /metrics
#
# 测试策略：
#   通过 importlib.util.spec_from_file_location 直接加载目标文件，
#   跳过 api/__init__.py 的 Blueprint.group 调用，与现有 tests/ 风格一致。
#   用最小化 sanic stub + sys.modules 注入隔离所有外部依赖。
#
# revert 准则：
#   若把 api/collect.py / api/monitor.py / api/health.py 中的实现逻辑 revert，
#   对应测试应 FAIL——每个测试都直接调用 handler 并断言返回值契约。

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

# stargazer 源目录
_STARGAZER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_STARGAZER_ROOT))

_API_DIR = _STARGAZER_ROOT / "api"
FULL_HOST_MODULES = "cpu,mem,disk,diskio,net,processes,system"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _make_sanic_stub():
    """返回 (sanic_module, sanic_log_module) stub，满足 collect/monitor/health 的模块级 import。"""
    sanic_mod = types.ModuleType("sanic")
    sanic_mod.__path__ = []

    class _Blueprint:
        def __init__(self, name, url_prefix=""):
            self.name = name
            self.url_prefix = url_prefix
            self._routes = []

        def get(self, uri, **kw):
            def decorator(fn):
                self._routes.append(("GET", uri, fn))
                return fn
            return decorator

        def route(self, uri, methods=None, **kw):
            def decorator(fn):
                for m in (methods or ["GET"]):
                    self._routes.append((m.upper(), uri, fn))
                return fn
            return decorator

        @classmethod
        def group(cls, *bps, url_prefix=""):
            """api/__init__.py 调用的 group 方法，返回 None 即可（测试不需要）。"""
            return None

    class _Response:
        @staticmethod
        def json(data, status=200, **kw):
            import json as _j
            return {"body": _j.dumps(data), "status": status, "content_type": "application/json"}

        @staticmethod
        def raw(data, content_type="text/plain", status=200, headers=None, **kw):
            body = data.decode() if isinstance(data, bytes) else data
            return {"body": body, "status": status, "content_type": content_type, "headers": headers or {}}

        @staticmethod
        def text(data, content_type="text/plain", status=200, **kw):
            return {"body": data, "status": status, "content_type": content_type}

    resp_obj = _Response()
    sanic_mod.Blueprint = _Blueprint
    sanic_mod.response = resp_obj

    sanic_log_mod = types.ModuleType("sanic.log")
    sanic_log_mod.logger = types.SimpleNamespace(
        debug=lambda *a, **kw: None,
        info=lambda *a, **kw: None,
        warning=lambda *a, **kw: None,
        error=lambda *a, **kw: None,
        exception=lambda *a, **kw: None,
    )
    sanic_mod.log = sanic_log_mod

    return sanic_mod, sanic_log_mod


def _load_api_module(filename: str, module_name: str):
    """直接从文件加载 api/ 模块，绕过 api/__init__.py。"""
    path = _API_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _install_core_stubs(task_queue_mock=None, csc_mock=None):
    """注入 core.* stub。"""
    core_mod = types.ModuleType("core")
    core_mod.__path__ = []
    sys.modules["core"] = core_mod

    csc_mod = types.ModuleType("core.credential_state_cache")
    if csc_mock is None:
        csc_mock = MagicMock()
        csc_mock.list_result_events = AsyncMock(return_value=[])
    csc_mod.CredentialStateCache = csc_mock
    sys.modules["core.credential_state_cache"] = csc_mod

    if task_queue_mock is None:
        task_queue_mock = MagicMock()
        task_queue_mock._is_healthy = True
        task_queue_mock.enqueue_collect_task = AsyncMock(return_value={
            "task_id": "test-task-123",
            "job_id": "job-456",
            "status": "queued",
        })
        task_queue_mock.get_queue_stats = AsyncMock(return_value={
            "healthy": True,
            "queued_jobs": 3,
            "metrics": {
                "tasks_enqueued": 100,
                "tasks_skipped": 5,
                "tasks_failed": 2,
                "redis_connection_errors": 0,
            },
        })

    tq_mod = types.ModuleType("core.task_queue")
    tq_mod.get_task_queue = MagicMock(return_value=task_queue_mock)
    sys.modules["core.task_queue"] = tq_mod

    return task_queue_mock, csc_mock


def _install_plugins_stubs():
    plugins_mod = types.ModuleType("plugins")
    plugins_mod.__path__ = []
    sys.modules["plugins"] = plugins_mod
    bu_mod = types.ModuleType("plugins.base_utils")
    bu_mod.expand_ip_range = lambda s: [s]
    sys.modules["plugins.base_utils"] = bu_mod


def _cleanup_modules(*names):
    for n in names:
        sys.modules.pop(n, None)


class _HeaderDict:
    """支持 dict() 转换和 .get()、.items() 的 header 容器（模拟 Sanic request.headers）。"""
    def __init__(self, raw: dict):
        self._data = {k.lower(): v for k, v in raw.items()}

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, item):
        return item.lower() in self._data

    def __getitem__(self, key):
        return self._data[key.lower()]

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key.lower(), default)

    def startswith(self, prefix):
        # 供 dict(...) 迭代时使用
        return False


def _make_request(headers=None, query_args=None, args=None):
    req = MagicMock()
    req.headers = _HeaderDict(headers or {})
    req.query_args = list((query_args or {}).items())
    req.args = args or {}
    req.receive_body = AsyncMock(return_value=None)
    return req


# ---------------------------------------------------------------------------
# collect.py — 纯函数测试
# ---------------------------------------------------------------------------

class TestCollectPureFunctions:
    """测试 collect.py 的纯函数（不触碰 HTTP 运行时 / Redis）。"""

    _STUBS = ("sanic", "sanic.log", "core", "core.credential_state_cache",
              "core.task_queue", "plugins", "plugins.base_utils", "_collect_mod")

    def setup_method(self):
        sanic_mod, sanic_log_mod = _make_sanic_stub()
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod
        _install_core_stubs()
        _install_plugins_stubs()
        _cleanup_modules("_collect_mod")
        self.mod = _load_api_module("collect.py", "_collect_mod")

    def teardown_method(self):
        _cleanup_modules("_collect_mod", "sanic", "sanic.log", "core",
                         "core.credential_state_cache", "core.task_queue",
                         "plugins", "plugins.base_utils")

    def test_parse_hosts_single_ip(self):
        assert self.mod._parse_hosts("192.168.1.1") == ["192.168.1.1"]

    def test_parse_hosts_comma_separated(self):
        result = self.mod._parse_hosts("192.168.1.1,192.168.1.2")
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_parse_hosts_empty_string_returns_empty(self):
        assert self.mod._parse_hosts("") == []
        assert self.mod._parse_hosts("   ") == []

    def test_parse_hosts_domain(self):
        assert self.mod._parse_hosts("db.example.com") == ["db.example.com"]

    def test_get_connect_ip_plain(self):
        assert self.mod._get_connect_ip("10.0.0.1") == "10.0.0.1"

    def test_get_connect_ip_with_bracket_stripped(self):
        # 格式 "ip[extra]" → "ip"
        assert self.mod._get_connect_ip("10.0.0.1[zone-a]") == "10.0.0.1"

    def test_get_connect_ip_empty_returns_empty(self):
        assert self.mod._get_connect_ip("") == ""
        assert self.mod._get_connect_ip(None) == ""

    def test_is_config_file_collect_by_callback_subject(self):
        assert self.mod._is_config_file_collect(
            {"callback_subject": "receive_config_file_result"}
        )

    def test_is_config_file_collect_by_plugin_name(self):
        assert self.mod._is_config_file_collect({"plugin_name": "config_file_info"})

    def test_is_config_file_collect_false_for_normal_plugin(self):
        assert not self.mod._is_config_file_collect({"plugin_name": "mysql_info"})

    async def test_host_split_preserves_execution_id(self):
        candidates = self.mod._build_collect_task_candidates(
            {
                "collect_task_id": "10",
                "execution_id": "execution-current",
                "model_id": "config_file",
            },
            ["10.0.0.1", "10.0.0.2"],
            [],
        )

        assert candidates["10.0.0.1"][0]["execution_id"] == "execution-current"
        assert candidates["10.0.0.2"][0]["execution_id"] == "execution-current"

    def test_parse_credentials_pool_none_returns_empty(self):
        assert self.mod._parse_credentials_pool(None, params=None) == []

    def test_parse_credentials_pool_json_list(self):
        import json
        pool = [{"username": "root", "password": "s3cr3t"}]
        result = self.mod._parse_credentials_pool(json.dumps(pool))
        assert result == pool

    def test_build_credential_results_payload_empty_returns_dict(self):
        result = self.mod._build_credential_results_payload([])
        assert isinstance(result, dict), "Payload must be a dict"


# ---------------------------------------------------------------------------
# collect.py — HTTP handler 逻辑测试
# ---------------------------------------------------------------------------

class TestCollectEndpointLogic:
    """调用 collect handler 函数，验证 HTTP 契约（状态码 + Prometheus 响应格式）。"""

    def setup_method(self):
        sanic_mod, sanic_log_mod = _make_sanic_stub()
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod
        self.task_queue, self.csc = _install_core_stubs()
        _install_plugins_stubs()
        _cleanup_modules("_collect_mod")
        self.mod = _load_api_module("collect.py", "_collect_mod")

    def teardown_method(self):
        _cleanup_modules("_collect_mod", "sanic", "sanic.log", "core",
                         "core.credential_state_cache", "core.task_queue",
                         "plugins", "plugins.base_utils")

    async def test_collect_info_missing_model_id_returns_500_prometheus(self):
        """缺少 model_id → 500 + Prometheus error 格式。

        若 revert collect.py 中"model_id 为空返回 500"的错误分支，此测试 FAIL。
        """
        req = _make_request()  # 无任何参数

        result = await self.mod.collect(req)

        assert result["status"] == 500, f"Expected 500, got {result['status']}"
        body = result["body"]
        assert "collection_request_error" in body, (
            "Error metric name 'collection_request_error' must appear in body"
        )
        assert "model_id is Null" in body, "Error label must state 'model_id is Null'"
        assert "text/plain" in result["content_type"]
        assert "0.0.4" in result["content_type"]

    async def test_collect_info_single_task_mode_returns_200_prometheus_accepted(self):
        """有 model_id 无 hosts → 单任务模式 → 200 + Prometheus accepted 格式。

        若 revert collect.py 中"单任务返回 collection_request_accepted"逻辑，此测试 FAIL。
        """
        req = _make_request(headers={"cmdbmodel_id": "mysql"})

        result = await self.mod.collect(req)

        assert result["status"] == 200, f"Expected 200, got {result['status']}"
        body = result["body"]
        assert "collection_request_accepted" in body, (
            "Prometheus metric 'collection_request_accepted' must be in response"
        )
        assert "mysql" in body, "model_id label value must appear in body"
        assert "test-task-123" in body, "task_id from enqueue result must appear in body"
        assert "text/plain" in result["content_type"]
        assert "0.0.4" in result["content_type"]
        # X-Task-ID header 必须被设置
        assert result["headers"].get("X-Task-ID") == "test-task-123"

    async def test_collect_info_query_args_fallback_when_no_cmdb_headers(self):
        """无 cmdb* header 时，从 query_args 读取参数（向后兼容路径）。"""
        req = _make_request(
            headers={},
            query_args={"model_id": "redis", "host": "10.0.0.1"},
        )

        result = await self.mod.collect(req)

        # model_id 来自 query_args → 不应走 500 错误分支
        assert result["status"] != 500, (
            "With model_id in query_args, should not return 500"
        )

    async def test_credential_results_calls_cache_and_returns_json(self):
        """GET /credential_results 应调用 CredentialStateCache 并返回 JSON dict。"""
        req = MagicMock()
        req.args = MagicMock()
        req.args.get = MagicMock(return_value=None)

        result = await self.mod.get_credential_results(req)

        assert self.csc.list_result_events.called, (
            "CredentialStateCache.list_result_events must be called"
        )
        assert result["status"] == 200
        assert "application/json" in result["content_type"]


# ---------------------------------------------------------------------------
# monitor.py — HTTP handler 逻辑测试
# ---------------------------------------------------------------------------

class TestMonitorEndpointLogic:
    """验证 monitor 端点的错误路径返回合法 Prometheus 格式 + 正确状态码。"""

    def setup_method(self):
        sanic_mod, sanic_log_mod = _make_sanic_stub()
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod
        self.task_queue, _ = _install_core_stubs()
        _cleanup_modules("_monitor_mod")
        self.mod = _load_api_module("monitor.py", "_monitor_mod")

    def teardown_method(self):
        _cleanup_modules("_monitor_mod", "sanic", "sanic.log", "core", "core.task_queue")

    def _req(self, headers=None):
        req = MagicMock()
        req.headers = _HeaderDict(headers or {})
        # args.get must return a string so int() conversions don't fail
        req.args = MagicMock()
        req.args.get = MagicMock(side_effect=lambda k, default=None: default)
        return req

    def test_monitor_error_response_prometheus_format(self):
        """_monitor_error_response 生成符合 Prometheus text-format 的三行结构。

        若 revert _monitor_error_response 中"# HELP / # TYPE / metric 行"，此测试 FAIL。
        """
        result = self.mod._monitor_error_response("vmware", "missing host", status=400)

        assert result["status"] == 400
        body = result["body"]
        lines = [l for l in body.strip().split("\n") if l]

        help_lines = [l for l in lines if l.startswith("# HELP")]
        type_lines = [l for l in lines if l.startswith("# TYPE")]
        metric_lines = [l for l in lines if not l.startswith("#")]

        assert len(help_lines) >= 1, "Must have at least one # HELP line"
        assert len(type_lines) >= 1, "Must have at least one # TYPE line"
        assert len(metric_lines) >= 1, "Must have at least one metric value line"
        assert "{" in metric_lines[0], "Metric must include label set {}"
        assert "vmware" in body, "monitor_type label must appear in body"
        assert "missing host" in body, "error message must appear in label"
        assert "text/plain" in result["content_type"]

    async def test_vmware_metrics_accepted_returns_prometheus_accepted_format(self):
        """vmware_metrics 成功入队时 → 200 + Prometheus 'monitor_request_accepted' 格式。

        若 revert vmware_metrics 中构建 Prometheus 响应的逻辑，此测试 FAIL。
        """
        result = await self.mod.vmware_metrics(self._req(
            headers={"username": "admin", "password": "pass", "host": "vcenter.example.com"}
        ))

        assert result["status"] == 200, f"Expected 200, got {result['status']}"
        body = result["body"]
        assert "# HELP" in body, "Response must contain Prometheus # HELP comment"
        assert "monitor_request_accepted" in body, (
            "Success metric must be 'monitor_request_accepted'"
        )
        assert "vmware" in body, "monitor_type=vmware must appear in metric labels"
        assert "text/plain" in result["content_type"]
        assert "0.0.4" in result["content_type"]
        assert "X-Task-ID" in result["headers"], "X-Task-ID header must be set"

    async def test_qcloud_metrics_accepted_returns_prometheus_accepted_format(self):
        """qcloud_metrics 成功入队时 → 200 + Prometheus 'monitor_request_accepted' 格式。

        若 revert qcloud_metrics 中构建 Prometheus 响应的逻辑，此测试 FAIL。
        """
        result = await self.mod.qcloud_metrics(self._req(
            headers={"username": "AKIDxxxxxx", "password": "secret"}
        ))

        assert result["status"] == 200, f"Expected 200, got {result['status']}"
        body = result["body"]
        assert "# HELP" in body
        assert "monitor_request_accepted" in body, (
            "Success metric must be 'monitor_request_accepted'"
        )
        assert "qcloud" in body, "monitor_type=qcloud must appear in metric labels"
        assert "text/plain" in result["content_type"]
        assert "0.0.4" in result["content_type"]
        assert "X-Task-ID" in result["headers"]

    async def test_host_metrics_defaults_missing_modules_to_full_collection(self):
        """Host Remote 未传 metrics_modules 时，应默认采集全部主机模块。"""
        result = await self.mod.host_metrics(self._req(
            headers={
                "host": "10.0.0.10",
                "username": "root",
                "password": "pass",
                "ansible_node_id": "node-1",
            }
        ))

        assert result["status"] == 200
        task_params = self.task_queue.enqueue_collect_task.call_args.args[0]
        assert task_params["monitor_type"] == "host"
        assert task_params["metrics_modules"] == FULL_HOST_MODULES

    async def test_windows_wmi_metrics_defaults_missing_modules_to_full_collection(self):
        """Windows WMI 未传 metrics_modules 时，应默认采集全部主机模块。"""
        result = await self.mod.windows_wmi_metrics(self._req(
            headers={
                "host": "10.0.0.20",
                "username": "DOMAIN\\monitor",
                "password": "pass",
            }
        ))

        assert result["status"] == 200
        task_params = self.task_queue.enqueue_collect_task.call_args.args[0]
        assert task_params["monitor_type"] == "windows_wmi"
        assert task_params["metrics_modules"] == FULL_HOST_MODULES

    async def test_host_metrics_passes_disk_fstype_filters_to_collector(self):
        await self.mod.host_metrics(self._req(
            headers={
                "host": "10.0.0.10",
                "username": "root",
                "password": "pass",
                "ansible_node_id": "node-1",
                "disk_include_fstypes": "ext4,xfs",
                "disk_exclude_fstypes": "vfat,exfat",
            }
        ))

        task_params = self.task_queue.enqueue_collect_task.call_args.args[0]
        assert task_params["disk_include_fstypes"] == "ext4,xfs"
        assert task_params["disk_exclude_fstypes"] == "vfat,exfat"

    async def test_windows_wmi_metrics_passes_disk_fstype_filters_to_collector(self):
        await self.mod.windows_wmi_metrics(self._req(
            headers={
                "host": "10.0.0.20",
                "username": "DOMAIN\\monitor",
                "password": "pass",
                "disk_include_fstypes": "NTFS,ReFS",
                "disk_exclude_fstypes": "FAT32,exFAT",
            }
        ))

        task_params = self.task_queue.enqueue_collect_task.call_args.args[0]
        assert task_params["disk_include_fstypes"] == "NTFS,ReFS"
        assert task_params["disk_exclude_fstypes"] == "FAT32,exFAT"


# ---------------------------------------------------------------------------
# health.py — HTTP handler 逻辑测试
# ---------------------------------------------------------------------------

class TestHealthEndpointLogic:
    """验证 health 端点的响应格式和状态码契约。"""

    def setup_method(self):
        sanic_mod, sanic_log_mod = _make_sanic_stub()
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod
        self.task_queue, _ = _install_core_stubs()
        _cleanup_modules("_health_mod")
        self.mod = _load_api_module("health.py", "_health_mod")

    def teardown_method(self):
        _cleanup_modules("_health_mod", "sanic", "sanic.log", "core", "core.task_queue")

    async def test_health_check_returns_200_with_status_ok(self):
        """GET /health/ → 200 + {"status": "ok", "timestamp": ...}。

        若 revert health_check 中返回 status='ok' 的逻辑，此测试 FAIL。
        """
        import json as _j
        result = await self.mod.health_check(MagicMock())

        assert result["status"] == 200
        body = _j.loads(result["body"])
        assert body.get("status") == "ok", f"Expected status='ok', got: {body}"
        assert "timestamp" in body, "Response must include 'timestamp' field"

    async def test_readiness_check_returns_200_when_task_queue_healthy(self):
        """task_queue 健康时 → /health/ready 返回 200 + ready=true。

        若 revert readiness_check 中 200 路径，此测试 FAIL。
        """
        import json as _j
        result = await self.mod.readiness_check(MagicMock())

        assert result["status"] == 200, f"Expected 200 when healthy, got {result['status']}"
        body = _j.loads(result["body"])
        assert body.get("ready") is True

    async def test_readiness_check_returns_503_when_task_queue_unhealthy(self):
        """task_queue 不健康时 → /health/ready 返回 503 + ready=false。

        若 revert readiness_check 中 503 路径，此测试 FAIL。
        """
        import json as _j
        self.task_queue._is_healthy = False

        result = await self.mod.readiness_check(MagicMock())

        assert result["status"] == 503, f"Expected 503 when unhealthy, got {result['status']}"
        body = _j.loads(result["body"])
        assert body.get("ready") is False

    async def test_prometheus_metrics_returns_prometheus_text_format(self):
        """GET /health/metrics → Prometheus text-format（含 HELP/TYPE/指标行 + Content-Type 0.0.4）。

        若 revert prometheus_metrics 中生成 Prometheus 格式的逻辑，此测试 FAIL。
        """
        result = await self.mod.prometheus_metrics(MagicMock())

        assert result["status"] == 200
        body = result["body"]
        assert "text/plain" in result["content_type"]
        assert "0.0.4" in result["content_type"], (
            "Content-Type must include 'version=0.0.4' for Prometheus text format"
        )
        assert "# HELP" in body
        assert "# TYPE" in body
        assert "stargazer_task_queue_healthy" in body, (
            "Must include 'stargazer_task_queue_healthy' metric"
        )
        assert "stargazer_task_queue_length" in body
        assert "stargazer_tasks_enqueued_total" in body

    async def test_queue_stats_returns_json_with_healthy_field(self):
        """GET /health/stats → JSON dict with 'healthy' field。"""
        import json as _j
        result = await self.mod.queue_stats(MagicMock())

        assert result["status"] == 200
        body = _j.loads(result["body"])
        assert "healthy" in body, "Stats response must include 'healthy' field"


# ---------------------------------------------------------------------------
# 路由注册契约测试（验证 Blueprint url_prefix 和路由 path）
# ---------------------------------------------------------------------------

class TestRouteRegistration:
    """验证各 Blueprint 的 url_prefix 和路由路径注册契约。"""

    def setup_method(self):
        sanic_mod, sanic_log_mod = _make_sanic_stub()
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod
        _install_core_stubs()
        _install_plugins_stubs()
        _cleanup_modules("_collect_r", "_monitor_r", "_health_r")

    def teardown_method(self):
        _cleanup_modules(
            "_collect_r", "_monitor_r", "_health_r",
            "sanic", "sanic.log", "core", "core.credential_state_cache",
            "core.task_queue", "plugins", "plugins.base_utils",
        )

    def test_collect_blueprint_url_prefix_is_slash_collect(self):
        mod = _load_api_module("collect.py", "_collect_r")
        assert mod.collect_router.url_prefix == "/collect", (
            f"collect_router.url_prefix must be '/collect', got '{mod.collect_router.url_prefix}'"
        )

    def test_collect_blueprint_registers_collect_info_route(self):
        """collect_router 必须注册 /collect_info。

        若从 collect.py 移除 @collect_router.get('/collect_info') 装饰器，此测试 FAIL。
        """
        mod = _load_api_module("collect.py", "_collect_r")
        paths = [p for _, p, _ in mod.collect_router._routes]
        assert "/collect_info" in paths, (
            f"collect_router must register '/collect_info'. Found: {paths}"
        )

    def test_collect_blueprint_registers_credential_results_route(self):
        """collect_router 必须注册 /credential_results。"""
        mod = _load_api_module("collect.py", "_collect_r")
        paths = [p for _, p, _ in mod.collect_router._routes]
        assert "/credential_results" in paths, (
            f"collect_router must register '/credential_results'. Found: {paths}"
        )

    def test_monitor_blueprint_url_prefix_is_slash_monitor(self):
        mod = _load_api_module("monitor.py", "_monitor_r")
        assert mod.monitor_router.url_prefix == "/monitor", (
            f"monitor_router.url_prefix must be '/monitor', got '{mod.monitor_router.url_prefix}'"
        )

    def test_monitor_blueprint_registers_vmware_metrics_route(self):
        """monitor_router 必须注册 /vmware/metrics。

        若移除 @monitor_router.get('/vmware/metrics')，此测试 FAIL。
        """
        mod = _load_api_module("monitor.py", "_monitor_r")
        paths = [p for _, p, _ in mod.monitor_router._routes]
        assert "/vmware/metrics" in paths, (
            f"monitor_router must register '/vmware/metrics'. Found: {paths}"
        )

    def test_monitor_blueprint_registers_qcloud_metrics_route(self):
        mod = _load_api_module("monitor.py", "_monitor_r")
        paths = [p for _, p, _ in mod.monitor_router._routes]
        assert "/qcloud/metrics" in paths, (
            f"monitor_router must register '/qcloud/metrics'. Found: {paths}"
        )

    def test_monitor_blueprint_registers_host_metrics_route(self):
        mod = _load_api_module("monitor.py", "_monitor_r")
        paths = [p for _, p, _ in mod.monitor_router._routes]
        assert "/host/metrics" in paths, (
            f"monitor_router must register '/host/metrics'. Found: {paths}"
        )

    def test_health_blueprint_url_prefix_is_slash_health(self):
        mod = _load_api_module("health.py", "_health_r")
        assert mod.health_router.url_prefix == "/health", (
            f"health_router.url_prefix must be '/health', got '{mod.health_router.url_prefix}'"
        )

    def test_health_blueprint_registers_readiness_route(self):
        """health_router 必须注册 /ready。"""
        mod = _load_api_module("health.py", "_health_r")
        paths = [p for _, p, _ in mod.health_router._routes]
        assert "/ready" in paths, (
            f"health_router must register '/ready'. Found: {paths}"
        )

    def test_health_blueprint_registers_prometheus_metrics_route(self):
        mod = _load_api_module("health.py", "_health_r")
        paths = [p for _, p, _ in mod.health_router._routes]
        assert "/metrics" in paths, (
            f"health_router must register '/metrics'. Found: {paths}"
        )

    def test_health_blueprint_registers_stats_route(self):
        mod = _load_api_module("health.py", "_health_r")
        paths = [p for _, p, _ in mod.health_router._routes]
        assert "/stats" in paths, (
            f"health_router must register '/stats'. Found: {paths}"
        )
