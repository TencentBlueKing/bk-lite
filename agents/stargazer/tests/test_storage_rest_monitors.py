import importlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path


STARGAZER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARGAZER_ROOT))


def _install_monitor_base_stub():
    core_mod = types.ModuleType("core")
    core_mod.__path__ = []
    monitor_pkg = types.ModuleType("core.monitor")
    monitor_pkg.__path__ = []
    base_mod = types.ModuleType("core.monitor.base")

    class ApiMonitor:
        def __init__(self, input_data):
            self.input = input_data
            self.config = input_data.get("config", {})
            self.resource = input_data.get("resource", {})
            self.resource_id = self.resource.get("bk_inst_id", "")
            self.data = {}

    base_mod.ApiMonitor = ApiMonitor
    sys.modules["core"] = core_mod
    sys.modules["core.monitor"] = monitor_pkg
    sys.modules["core.monitor.base"] = base_mod


def _load_file_module(rel_path, module_name):
    path = STARGAZER_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _install_nats_helper_stubs():
    sanic_mod = types.ModuleType("sanic")
    sanic_log_mod = types.ModuleType("sanic.log")
    sanic_log_mod.logger = types.SimpleNamespace(
        debug=lambda *a, **kw: None,
        info=lambda *a, **kw: None,
        warning=lambda *a, **kw: None,
        error=lambda *a, **kw: None,
    )
    sys.modules["sanic"] = sanic_mod
    sys.modules["sanic.log"] = sanic_log_mod

    core_mod = types.ModuleType("core")
    core_mod.__path__ = []
    nats_utils_mod = types.ModuleType("core.nats_utils")

    class NatsLinesPublishError(Exception):
        attempted_count_before_failure = 0
        delivery_detected = False

    async def nats_publish(*args, **kwargs):
        return None

    async def nats_publish_lines(*args, **kwargs):
        return 0

    nats_utils_mod.NatsLinesPublishError = NatsLinesPublishError
    nats_utils_mod.nats_publish = nats_publish
    nats_utils_mod.nats_publish_lines = nats_publish_lines
    sys.modules["core"] = core_mod
    sys.modules["core.nats_utils"] = nats_utils_mod

    influx_mod = types.ModuleType("influxdb_client")

    class Point:
        def __init__(self, metric_name):
            self.metric_name = metric_name
            self.tags = []
            self.fields = []

        def tag(self, key, value):
            self.tags.append((key, str(value)))
            return self

        def field(self, key, value):
            self.fields.append((key, value))
            return self

        def time(self, *_args):
            return self

        def to_line_protocol(self):
            tags = "".join(f",{key}={value}" for key, value in self.tags)
            fields = ",".join(f"{key}={value}" for key, value in self.fields)
            return f"{self.metric_name}{tags} {fields}"

    class WritePrecision:
        NS = "ns"

    influx_mod.Point = Point
    influx_mod.WritePrecision = WritePrecision
    sys.modules["influxdb_client"] = influx_mod


class StorageRestMonitorTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("common.monitor_plugins.infinibox.api", None)
        sys.modules.pop("common.monitor_plugins.storage_utils", None)
        _install_monitor_base_stub()

    def test_infinibox_counter_totals_are_converted_to_rates(self):
        module = importlib.import_module("common.monitor_plugins.infinibox.api")

        rates = module.calculate_counter_rates(
            previous={
                "read_ops": 100,
                "write_ops": 200,
                "read_bytes": 4096,
                "write_bytes": 8192,
                "read_latency": 1_000_000,
                "write_latency": 2_000_000,
            },
            current={
                "read_ops": 340,
                "write_ops": 500,
                "read_bytes": 28_672,
                "write_bytes": 69_632,
                "read_latency": 3_400_000,
                "write_latency": 8_000_000,
            },
            elapsed_seconds=60,
        )

        self.assertEqual(rates["infinibox_volume_read_iops"], 4)
        self.assertEqual(rates["infinibox_volume_write_iops"], 5)
        self.assertEqual(rates["infinibox_volume_read_bandwidth"], 409.6)
        self.assertEqual(rates["infinibox_volume_write_bandwidth"], 1024)
        self.assertEqual(rates["infinibox_volume_read_latency"], 10)
        self.assertEqual(rates["infinibox_volume_write_latency"], 20)

    def test_no_storage_metrics_is_an_error(self):
        module = importlib.import_module("common.monitor_plugins.storage_utils")

        with self.assertRaises(module.NoStorageMetricsError):
            module.ensure_storage_metrics({"inst-1": {}})

    def test_storage_prometheus_labels_escape_special_characters(self):
        convert_module = importlib.import_module("utils.convert")
        resource_id = 'array"\\\n1'
        volume = 'vol"\\\n1'

        metrics = convert_module.convert_to_prometheus(
            {
                (resource_id, "pure"): {
                    "pure_volume_read_iops": {
                        (("volume", volume),): [(None, 7)],
                    }
                }
            }
        )

        metric_line = next(
            line for line in metrics if line.startswith("pure_volume_read_iops{")
        )
        expected_resource_id = (
            resource_id.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        )
        expected_volume = (
            volume.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        )
        self.assertIn(f'resource_id="{expected_resource_id}"', metric_line)
        self.assertIn(f'volume="{expected_volume}"', metric_line)
        self.assertNotIn("\n", metric_line)


class StorageApiShapeTests(unittest.TestCase):
    def setUp(self):
        _install_monitor_base_stub()
        for module_name in (
            "common.monitor_plugins.pure.api",
            "common.monitor_plugins.infinibox.api",
        ):
            sys.modules.pop(module_name, None)

    def test_pure_api_monitor_parses_array_and_volume_responses(self):
        module = importlib.import_module("common.monitor_plugins.pure.api")

        class FakePureClient:
            def __init__(self):
                self.requests = []
                self.logged_out = False

            def request(self, method, endpoint, params=None, json=None, verify=None):
                self.requests.append((method, endpoint, params, json))
                if endpoint == "/api/api_version":
                    return {"version": ["1.19"]}
                if endpoint == "/api/1.19/auth/apitoken":
                    return {"api_token": "token-1"}
                if endpoint == "/api/1.19/auth/session":
                    return {}
                if endpoint == "/api/1.19/array" and params == {"action": "monitor"}:
                    return [
                        {
                            "reads_per_sec": 11,
                            "writes_per_sec": 12,
                            "output_per_sec": 1024,
                            "input_per_sec": 2048,
                            "queue_depth": 3,
                            "usec_per_read_op": 4000,
                            "usec_per_write_op": 5000,
                        }
                    ]
                if endpoint == "/api/1.19/array" and params == {"space": "true"}:
                    return [{"capacity": 1000, "total": 800, "data_reduction": 2.5}]
                if endpoint == "/api/1.19/volume" and params == {"action": "monitor"}:
                    return [
                        {
                            "name": "vol-1",
                            "reads_per_sec": 21,
                            "writes_per_sec": 22,
                            "output_per_sec": 4096,
                            "input_per_sec": 8192,
                            "usec_per_read_op": 6000,
                            "usec_per_write_op": 7000,
                        }
                    ]
                if endpoint == "/api/1.19/volume" and params == {"space": "true"}:
                    return [{"name": "vol-1", "size": 2000, "volumes": 1200}]
                if endpoint == "/api/1.19/auth/session":
                    return {}
                return {}

            def logout(self):
                self.logged_out = True

        monitor = module.PureApiMonitor(
            {
                "config": {
                    "base_url": "https://pure.example",
                    "username": "admin",
                    "password": "secret",
                },
                "resource": {"bk_inst_id": "pure-1", "metrics": []},
            }
        )
        fake_client = FakePureClient()
        monitor.api = fake_client

        monitor.run()

        data = monitor.data["pure-1"]
        self.assertEqual(data["pure_array_read_iops"][()][0][1], 11)
        self.assertEqual(data["pure_array_read_latency"][()][0][1], 4)
        self.assertEqual(data["pure_volume_read_iops"][(("volume", "vol-1"),)][0][1], 21)
        self.assertEqual(data["pure_volume_read_latency"][(("volume", "vol-1"),)][0][1], 6)
        self.assertEqual(data["pure_volume_count"][()][0][1], 1)
        self.assertTrue(fake_client.logged_out)

    def test_infinibox_api_monitor_parses_pools_volumes_and_counter_rates(self):
        module = importlib.import_module("common.monitor_plugins.infinibox.api")
        original_sleep = module.time.sleep
        module.time.sleep = lambda _: None

        class FakeInfiniBoxClient:
            def __init__(self):
                self.counter_calls = 0
                self.logged_out = False

            def request(self, method, endpoint, params=None, json=None, verify=None):
                if endpoint == "/api/rest/users/login":
                    return {"result": {}}
                if endpoint == "/api/rest/users/logout":
                    return {"result": {}}
                if endpoint == "/api/rest/pools":
                    return {
                        "result": [
                            {
                                "name": "pool-1",
                                "physical_capacity": 1000,
                                "allocated_physical_space": 600,
                                "free_physical_space": 400,
                                "virtual_capacity": 2000,
                                "allocated_virtual_space": 1200,
                            }
                        ]
                    }
                if endpoint == "/api/rest/volumes":
                    return {
                        "result": [
                            {
                                "id": 101,
                                "name": "vol-1",
                                "size": 500,
                                "allocated": 300,
                            }
                        ]
                    }
                if endpoint == "/api/rest/counters/volumes/101/total":
                    self.counter_calls += 1
                    if self.counter_calls == 1:
                        return {
                            "result": {
                                "read_ops": 100,
                                "write_ops": 50,
                                "read_bytes": 1000,
                                "write_bytes": 2000,
                                "read_latency": 100000,
                                "write_latency": 100000,
                                "latency": 200000,
                                "ops": 150,
                            }
                        }
                    return {
                        "result": {
                            "read_ops": 160,
                            "write_ops": 80,
                            "read_bytes": 7000,
                            "write_bytes": 5000,
                            "read_latency": 700000,
                            "write_latency": 400000,
                            "latency": 1000000,
                            "ops": 240,
                        }
                    }
                return {"result": []}

            def logout(self):
                self.logged_out = True

        try:
            monitor = module.InfiniBoxApiMonitor(
                {
                    "config": {
                        "base_url": "https://ibox.example",
                        "username": "admin",
                        "password": "secret",
                        "sample_seconds": 10,
                    },
                    "resource": {"bk_inst_id": "ibox-1", "metrics": []},
                }
            )
            fake_client = FakeInfiniBoxClient()
            monitor.api = fake_client

            monitor.run()

            data = monitor.data["ibox-1"]
            self.assertEqual(data["infinibox_pool_count"][()][0][1], 1)
            self.assertEqual(
                data["infinibox_pool_physical_capacity_bytes"][(("pool", "pool-1"),)][0][1],
                1000,
            )
            self.assertEqual(data["infinibox_volume_count"][()][0][1], 1)
            self.assertEqual(
                data["infinibox_volume_size_bytes"][(("volume", "vol-1"),)][0][1],
                500,
            )
            self.assertEqual(
                data["infinibox_volume_read_iops"][(("volume", "vol-1"),)][0][1],
                6,
            )
            self.assertEqual(
                data["infinibox_volume_read_latency"][(("volume", "vol-1"),)][0][1],
                10,
            )
            self.assertTrue(fake_client.logged_out)
        finally:
            module.time.sleep = original_sleep


class StorageCollectorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _install_monitor_base_stub()
        for module_name in (
            "tasks",
            "tasks.collectors",
            "tasks.collectors.pure_collector",
            "tasks.collectors.infinibox_collector",
        ):
            sys.modules.pop(module_name, None)

        tasks_mod = types.ModuleType("tasks")
        tasks_mod.__path__ = [str(STARGAZER_ROOT / "tasks")]
        collectors_mod = types.ModuleType("tasks.collectors")
        collectors_mod.__path__ = [str(STARGAZER_ROOT / "tasks" / "collectors")]
        sys.modules["tasks"] = tasks_mod
        sys.modules["tasks.collectors"] = collectors_mod

        sanic_mod = types.ModuleType("sanic")
        sanic_log_mod = types.ModuleType("sanic.log")
        sanic_log_mod.logger = types.SimpleNamespace(
            info=lambda *a, **kw: None,
            warning=lambda *a, **kw: None,
            error=lambda *a, **kw: None,
        )
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod

    async def test_pure_collector_rejects_empty_monitor_data(self):
        storage_utils = importlib.import_module("common.monitor_plugins.storage_utils")

        pure_api_mod = types.ModuleType("common.monitor_plugins.pure.api")

        class PureApiMonitor:
            data = {}

            def __init__(self, input_data):
                self.input_data = input_data

            def execute(self):
                self.data = {}

        pure_api_mod.PureApiMonitor = PureApiMonitor
        sys.modules["common.monitor_plugins.pure.api"] = pure_api_mod

        collector_mod = importlib.import_module("tasks.collectors.pure_collector")
        collector = collector_mod.PureCollector(
            {
                "username": "u",
                "password": "p",
                "base_url": "https://pure.example",
                "instance_id": "storage-1",
            }
        )

        with self.assertRaises(storage_utils.NoStorageMetricsError):
            await collector.collect()

    async def test_infinibox_collector_emits_prometheus_resource_type(self):
        infinibox_api_mod = types.ModuleType("common.monitor_plugins.infinibox.api")

        class InfiniBoxApiMonitor:
            def __init__(self, input_data):
                self.input_data = input_data
                self.data = {}

            def execute(self):
                self.data = {
                    "storage-2": {
                        "infinibox_pool_count": {
                            (): [(None, 2)],
                        }
                    }
                }

        infinibox_api_mod.InfiniBoxApiMonitor = InfiniBoxApiMonitor
        sys.modules["common.monitor_plugins.infinibox.api"] = infinibox_api_mod

        collector_mod = importlib.import_module("tasks.collectors.infinibox_collector")
        collector = collector_mod.InfiniBoxCollector(
            {
                "username": "u",
                "password": "p",
                "base_url": "https://ibox.example",
                "instance_id": "storage-2",
            }
        )

        metrics = await collector.collect()

        self.assertIn("infinibox_pool_count", metrics)
        self.assertIn('resource_type="infinibox"', metrics)
        self.assertIn('resource_id="storage-2"', metrics)


class StoragePrometheusToInfluxTests(unittest.TestCase):
    def setUp(self):
        for module_name in (
            "_storage_nats_helper",
            "sanic",
            "sanic.log",
            "core",
            "core.nats_utils",
            "influxdb_client",
        ):
            sys.modules.pop(module_name, None)
        _install_nats_helper_stubs()

    def test_common_tags_do_not_emit_raw_control_characters(self):
        nats_helper = _load_file_module(
            "tasks/utils/nats_helper.py", "_storage_nats_helper"
        )
        prometheus_data = "\n".join(
            [
                "# HELP pure_volume_read_iops pure_volume_read_iops metric",
                "# TYPE pure_volume_read_iops gauge",
                'pure_volume_read_iops{resource_id="array-1", resource_type="pure", volume="vol-1"} 7',
            ]
        )

        lines = nats_helper.convert_prometheus_to_influx(
            prometheus_data,
            {
                "monitor_type": "pure",
                "host": "pure.example",
                "tags": {
                    "instance_id": "array\n1",
                    "instance_type": "storage",
                    "collect_type": "pure",
                    "config_type": "pure",
                },
            },
        )

        self.assertEqual(len(lines), 1)
        self.assertNotIn("\n", lines[0])
        self.assertIn("instance_id=array 1", lines[0])


class StorageMonitorApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for module_name in ("_storage_monitor_api", "core.task_queue", "sanic", "sanic.log"):
            sys.modules.pop(module_name, None)

        sanic_mod = types.ModuleType("sanic")

        class Blueprint:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

        class Response:
            @staticmethod
            def raw(data, content_type="text/plain", status=200, headers=None):
                return {
                    "body": data,
                    "content_type": content_type,
                    "status": status,
                    "headers": headers or {},
                }

        sanic_mod.Blueprint = Blueprint
        sanic_mod.response = Response
        sanic_log_mod = types.ModuleType("sanic.log")
        sanic_log_mod.logger = types.SimpleNamespace(
            info=lambda *a, **kw: None,
            warning=lambda *a, **kw: None,
            error=lambda *a, **kw: None,
        )
        sys.modules["sanic"] = sanic_mod
        sys.modules["sanic.log"] = sanic_log_mod

        core_mod = types.ModuleType("core")
        core_mod.__path__ = []
        task_queue_mod = types.ModuleType("core.task_queue")
        sys.modules["core"] = core_mod
        sys.modules["core.task_queue"] = task_queue_mod
        self.queued_params = None

        class TaskQueue:
            async def enqueue_collect_task(inner_self, params):
                self.queued_params = params
                return {"task_id": "task-1", "job_id": "job-1"}

        task_queue_mod.get_task_queue = lambda: TaskQueue()

    async def test_pure_metrics_queues_base_url_and_tags(self):
        monitor = _load_file_module("api/monitor.py", "_storage_monitor_api")
        request = types.SimpleNamespace(
            headers={
                "username": "admin",
                "password": "secret",
                "base_url": "https://pure.example",
                "instance_id": "region_storage_pure_https://pure.example",
                "instance_type": "storage",
            }
        )

        response = await monitor.pure_metrics(request)

        self.assertEqual(response["status"], 200)
        self.assertIn('monitor_type="pure"', response["body"])
        self.assertEqual(self.queued_params["monitor_type"], "pure")
        self.assertEqual(self.queued_params["host"], "https://pure.example")
        self.assertEqual(self.queued_params["tags"]["collect_type"], "pure")
        self.assertEqual(
            self.queued_params["tags"]["instance_id"],
            "region_storage_pure_https://pure.example",
        )

    async def test_infinibox_metrics_queues_base_url_and_tags(self):
        monitor = _load_file_module("api/monitor.py", "_storage_monitor_api")
        request = types.SimpleNamespace(
            headers={
                "username": "admin",
                "password": "secret",
                "base_url": "https://ibox.example",
                "instance_id": "region_storage_infinibox_https://ibox.example",
                "instance_type": "storage",
            }
        )

        response = await monitor.infinibox_metrics(request)

        self.assertEqual(response["status"], 200)
        self.assertIn('monitor_type="infinibox"', response["body"])
        self.assertEqual(self.queued_params["monitor_type"], "infinibox")
        self.assertEqual(self.queued_params["host"], "https://ibox.example")
        self.assertEqual(self.queued_params["tags"]["collect_type"], "infinibox")
        self.assertEqual(
            self.queued_params["tags"]["instance_id"],
            "region_storage_infinibox_https://ibox.example",
        )

    async def test_infinibox_metrics_queues_sample_seconds_header(self):
        monitor = _load_file_module("api/monitor.py", "_storage_monitor_api")
        request = types.SimpleNamespace(
            headers={
                "username": "admin",
                "password": "secret",
                "base_url": "https://ibox.example",
                "instance_id": "region_storage_infinibox_https://ibox.example",
                "instance_type": "storage",
                "sample_seconds": "17",
            }
        )

        response = await monitor.infinibox_metrics(request)

        self.assertEqual(response["status"], 200)
        self.assertEqual(self.queued_params["sample_seconds"], "17")

    async def test_storage_metrics_response_escapes_prometheus_labels(self):
        monitor = _load_file_module("api/monitor.py", "_storage_monitor_api")
        request = types.SimpleNamespace(
            headers={
                "username": "admin",
                "password": "secret",
                "base_url": 'https://ibox.example/"bad\\\n',
                "instance_id": "storage-1",
                "instance_type": "storage",
            }
        )

        response = await monitor.infinibox_metrics(request)

        self.assertEqual(response["status"], 200)
        self.assertIn('host="https://ibox.example/\\"bad\\\\\\n"', response["body"])
        self.assertNotIn('host="https://ibox.example/"bad\\\n"', response["body"])


class StoragePluginMetadataTests(unittest.TestCase):
    def _plugin_dir(self, vendor):
        return (
            STARGAZER_ROOT.parents[1]
            / "server"
            / "apps"
            / "monitor"
            / "support-files"
            / "plugins"
            / "Telegraf"
            / vendor
            / "storage"
        )

    def test_pure_plugin_metadata_matches_stargazer_endpoint(self):
        plugin_dir = self._plugin_dir("pure")
        ui = json.loads((plugin_dir / "UI.json").read_text())
        metrics = json.loads((plugin_dir / "metrics.json").read_text())
        template = (plugin_dir / "pure.child.toml.j2").read_text()

        self.assertEqual(ui["collect_type"], "pure")
        self.assertEqual(
            metrics["default_metric"], "any({instance_type='storage'}) by (instance_id)"
        )
        self.assertIn("/api/monitor/pure/metrics", template)
        self.assertIn('collect_type = "pure"', template)
        metric_names = {metric["name"] for metric in metrics["metrics"]}
        self.assertIn("pure_volume_count_gauge", metric_names)
        self.assertIn("pure_array_read_iops_gauge", metric_names)
        self.assertTrue(
            any('resource_type="pure"' in metric["query"] for metric in metrics["metrics"])
        )

    def test_infinibox_plugin_metadata_matches_stargazer_endpoint(self):
        plugin_dir = self._plugin_dir("infinibox")
        ui = json.loads((plugin_dir / "UI.json").read_text())
        metrics = json.loads((plugin_dir / "metrics.json").read_text())
        template = (plugin_dir / "infinibox.child.toml.j2").read_text()

        self.assertEqual(ui["collect_type"], "infinibox")
        self.assertEqual(
            metrics["default_metric"], "any({instance_type='storage'}) by (instance_id)"
        )
        self.assertIn("/api/monitor/infinibox/metrics", template)
        self.assertIn('collect_type = "infinibox"', template)
        metric_names = {metric["name"] for metric in metrics["metrics"]}
        self.assertIn("infinibox_pool_count_gauge", metric_names)
        self.assertIn("infinibox_volume_read_iops_gauge", metric_names)
        self.assertTrue(
            any('resource_type="infinibox"' in metric["query"] for metric in metrics["metrics"])
        )


if __name__ == "__main__":
    unittest.main()
