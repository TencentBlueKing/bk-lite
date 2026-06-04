# -*- coding: utf-8 -*-
"""
Host Collector 单元测试

测试内容：
1. build_script - 脚本拼接逻辑
2. parse_metrics_to_prometheus - JSON→Prometheus 转换
3. HostCollector._extract_stdout - 结果解析
4. HostCollector.collect - 完整采集流程（mock Ansible RPC）
"""

import importlib
import json
import sys
import os
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# 让 import 能找到 stargazer 根目录模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.collectors.host_collector import (
    build_script,
    parse_metrics_to_prometheus,
    HostCollector,
    HOST_REMOTE_CALLBACK_REQUEST_TIMEOUT,
    VALID_MODULES,
    SCRIPTS_DIR,
)


def _load_nats_server_module(monkeypatch):
    import core.nats as core_nats
    import core.host_remote_callback as host_remote_callback_module

    class DummyNatsInstance:
        def __init__(self):
            self.handlers = {}
            self.handler_queues = {}
            self.service_name = host_remote_callback_module.get_stargazer_service_name()

        def register_handler(self, subject, queue=None):
            def decorator(handler):
                self.handlers[subject] = handler
                self.handler_queues[subject] = queue
                return handler

            return decorator

    monkeypatch.setattr(core_nats, "_nats_instance", DummyNatsInstance())
    collection_service_module = types.ModuleType("service.collection_service")
    collection_service_module.CollectionService = MagicMock()
    debug_service_module = types.ModuleType("service.debug.protocol_debug_service")
    debug_service_module.ProtocolDebugService = MagicMock()
    monkeypatch.setitem(sys.modules, "service.collection_service", collection_service_module)
    monkeypatch.setitem(sys.modules, "service.debug.protocol_debug_service", debug_service_module)
    influxdb_client_module = types.ModuleType("influxdb_client")
    influxdb_client_module.Point = MagicMock()
    influxdb_client_module.WritePrecision = MagicMock()
    monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
    monkeypatch.delitem(sys.modules, "service.nats_server", raising=False)
    return importlib.import_module("service.nats_server")


def _load_host_remote_runtime_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "core.host_remote_runtime", raising=False)
    return importlib.import_module("core.host_remote_runtime")


def _load_monitor_handler_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "tasks.handlers.monitor_handler", raising=False)
    return importlib.import_module("tasks.handlers.monitor_handler")


def _load_worker_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "core.worker", raising=False)
    return importlib.import_module("core.worker")


def _load_host_remote_handler_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "tasks.handlers.host_remote_handler", raising=False)
    return importlib.import_module("tasks.handlers.host_remote_handler")


def _install_fake_host_remote_callback_store(monkeypatch):
    import core.host_remote_callback as host_remote_callback_module

    callback_contexts = {}

    async def store_context(task_id, params, ctx=None):
        callback_contexts[str(task_id)] = {
            "task_id": str(task_id),
            "ctx": dict(ctx or {}),
            "params": dict(params or {}),
        }

    async def load_context(task_id):
        return callback_contexts.get(str(task_id))

    async def clear_context(task_id):
        return callback_contexts.pop(str(task_id), None)

    async def update_context(task_id, **updates):
        current = callback_contexts.get(str(task_id))
        if current is None:
            return None
        current = dict(current)
        status_updates = updates.pop("status", None)
        if isinstance(status_updates, dict):
            status = dict(current.get("status") or {})
            status.update(status_updates)
            current["status"] = status
        current.update(updates)
        callback_contexts[str(task_id)] = current
        return current

    async def record_callback_payload(task_id, payload):
        current = callback_contexts.get(str(task_id))
        if current is None:
            return None
        if current.get("raw_callback") is not None:
            return current
        current = dict(current)
        current["raw_callback"] = payload
        status = dict(current.get("status") or {})
        status.update({"execution": "execution_finished"})
        current["status"] = status
        callback_contexts[str(task_id)] = current
        return current

    async def mark_processing_enqueued(task_id, processing_job_id=None):
        current = callback_contexts.get(str(task_id))
        if current is None:
            return None
        current = dict(current)
        status = dict(current.get("status") or {})
        status.update({"delivery": "processing"})
        current["status"] = status
        current["processing_job_id"] = processing_job_id
        callback_contexts[str(task_id)] = current
        return current

    async def mark_processing_started(task_id):
        return await update_context(task_id, status={"delivery": "processing"})

    async def mark_processing_published(task_id):
        return await update_context(task_id, status={"delivery": "published"}, published_at=1)

    async def mark_processing_failed(task_id, error):
        return await update_context(task_id, status={"delivery": "delivery_failed"}, last_error=str(error))

    async def schedule_publish_retry(task_id, error):
        current = callback_contexts.get(str(task_id))
        if current is None:
            return {"retry_scheduled": False, "attempt": 0, "max_attempts": 0}
        attempts = int(current.get("publish_attempts") or 0) + 1
        current = dict(current)
        current["publish_attempts"] = attempts
        status = dict(current.get("status") or {})
        status.update({"delivery": "publish_pending"})
        current["status"] = status
        current["last_error"] = str(error)
        current["next_retry_at"] = attempts
        callback_contexts[str(task_id)] = current
        return {
            "retry_scheduled": True,
            "attempt": attempts,
            "max_attempts": 4,
            "delay_seconds": 15,
            "next_retry_at": attempts,
        }

    monkeypatch.setattr(
        host_remote_callback_module,
        "store_host_remote_callback_context",
        store_context,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "load_host_remote_callback_context",
        load_context,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "clear_host_remote_callback_context",
        clear_context,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "update_host_remote_callback_context",
        update_context,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "record_host_remote_callback_payload",
        record_callback_payload,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "mark_host_remote_processing_enqueued",
        mark_processing_enqueued,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "mark_host_remote_processing_started",
        mark_processing_started,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "mark_host_remote_processing_published",
        mark_processing_published,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "mark_host_remote_processing_failed",
        mark_processing_failed,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "schedule_host_remote_publish_retry",
        schedule_publish_retry,
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "is_retryable_host_remote_publish_error",
        lambda error: "publish failed" in str(error).lower() or "timeout" in str(error).lower(),
    )
    monkeypatch.setattr(
        host_remote_callback_module,
        "log_host_remote_event",
        lambda *args, **kwargs: None,
    )
    return host_remote_callback_module, callback_contexts


def _install_fake_host_remote_callback_pool(monkeypatch):
    import core.host_remote_callback as host_remote_callback_module

    class FakeRedisPool:
        def __init__(self):
            self.values = {}
            self.last_set = None
            self.deleted_keys = []

        async def set(self, key, value, ex=None):
            self.last_set = (key, value, ex)
            self.values[key] = value

        async def get(self, key):
            return self.values.get(key)

        async def delete(self, key):
            self.deleted_keys.append(key)
            self.values.pop(key, None)

    fake_pool = FakeRedisPool()
    monkeypatch.setattr(host_remote_callback_module, "_host_remote_callback_pool", fake_pool)
    return fake_pool


def _build_host_params():
    return {
        "host": "10.0.0.9",
        "os_type": "linux",
        "username": "root",
        "password": "secret",
        "ansible_node_id": "region1",
        "metrics_modules": "cpu",
        "monitor_type": "host",
        "tags": {"instance_id": "region1_host_10.0.0.9"},
    }


class TestBuildScript:
    """测试脚本拼接逻辑"""

    def test_linux_all_modules(self):
        script = build_script("linux", ["cpu", "mem", "disk", "net"])
        assert "#!/bin/bash" in script or "echo" in script
        # 应包含 header + 4 modules + footer
        assert script.count("\n") > 10

    def test_windows_all_modules(self):
        script = build_script("windows", ["cpu", "mem", "disk", "net"])
        # Windows 脚本应包含 PowerShell 相关内容
        assert "$" in script  # PowerShell 变量

    def test_single_module(self):
        script = build_script("linux", ["cpu"])
        # 应该只有 header + cpu + footer, 不含 mem/disk/net 内容
        assert script  # 非空即可

    def test_linux_cpu_script_uses_delta_sampling(self):
        script = build_script("linux", ["cpu"])

        assert "sleep 1" in script
        assert "cpu_user_1" in script
        assert "cpu_user_2" in script
        assert "used_delta" in script

    def test_linux_disk_script_filters_container_overlay_mounts(self):
        script = build_script("linux", ["disk"])

        assert "overlay:*" in script
        assert "/var/lib/docker/overlay2/*/merged" in script
        assert "/data/lib/docker/overlay2/*/merged" in script

    def test_linux_header_script_provides_json_escape_helper(self):
        script = build_script("linux", ["disk"])

        assert "json_escape()" in script
        assert "python3 -c" in script

    def test_linux_disk_and_net_scripts_escape_string_fields(self):
        disk_script = build_script("linux", ["disk"])
        net_script = build_script("linux", ["net"])

        assert 'mount_json=$(json_escape "$mount")' in disk_script
        assert '\\"mount\\":\\"$mount_json\\"' in disk_script
        assert 'iface_json=$(json_escape "$iface")' in net_script
        assert '\\"interface\\":\\"$iface_json\\"' in net_script

    def test_linux_net_script_filters_virtual_interfaces(self):
        script = build_script("linux", ["net"])

        assert "docker0" in script
        assert "br-*" in script
        assert "veth*" in script
        assert "cni*" in script

    def test_empty_modules_still_has_header_footer(self):
        script = build_script("linux", [])
        # 即使无模块，也应有 header + footer
        assert script

    def test_invalid_module_ignored(self):
        """无效模块名的脚本文件不存在，应被跳过"""
        script = build_script("linux", ["cpu", "nonexistent"])
        # 不应报错，nonexistent 被跳过
        assert script

    def test_scripts_dir_exists(self):
        assert (SCRIPTS_DIR / "linux").is_dir()
        assert (SCRIPTS_DIR / "windows").is_dir()

    def test_all_expected_scripts_exist(self):
        for mod in VALID_MODULES:
            assert (SCRIPTS_DIR / "linux" / f"{mod}.sh").exists(), f"Missing linux/{mod}.sh"
            assert (SCRIPTS_DIR / "windows" / f"{mod}.ps1").exists(), f"Missing windows/{mod}.ps1"
        assert (SCRIPTS_DIR / "linux" / "header.sh").exists()
        assert (SCRIPTS_DIR / "linux" / "footer.sh").exists()
        assert (SCRIPTS_DIR / "windows" / "header.ps1").exists()
        assert (SCRIPTS_DIR / "windows" / "footer.ps1").exists()


class TestParseMetricsToPrometheus:
    """测试 JSON 指标数据到 Prometheus 格式转换"""

    def test_explicit_timestamp_is_used_when_provided(self):
        data = {
            "cpu": {
                "usage_percent": 45.2,
                "core_count": 4,
                "load_1m": 1.5,
                "load_5m": 1.2,
                "load_15m": 0.9,
            }
        }

        result = parse_metrics_to_prometheus(data, "test_instance", "linux", timestamp=1234567890000)

        assert "1234567890000" in result

    @patch("tasks.collectors.host_collector.time.time", return_value=1234.567)
    def test_timestamp_defaults_to_current_time_when_not_provided(self, _mock_time):
        data = {
            "cpu": {
                "usage_percent": 45.2,
                "core_count": 4,
                "load_1m": 1.5,
                "load_5m": 1.2,
                "load_15m": 0.9,
            }
        }

        result = parse_metrics_to_prometheus(data, "test_instance", "linux")

        assert "1234567" in result

    def test_cpu_metrics(self):
        data = {
            "cpu": {
                "usage_percent": 45.2,
                "core_count": 4,
                "load_1m": 1.5,
                "load_5m": 1.2,
                "load_15m": 0.9,
            }
        }
        result = parse_metrics_to_prometheus(data, "test_instance", "linux")
        assert "host_cpu_usage_percent" in result
        assert "45.2" in result
        assert 'instance_id="test_instance"' in result
        assert 'os_type="linux"' in result
        assert "host_cpu_core_count" in result
        assert "host_cpu_load_1m" in result

    def test_memory_metrics(self):
        data = {
            "mem": {
                "total_bytes": 8589934592,
                "used_bytes": 4294967296,
                "available_bytes": 4294967296,
                "swap_total_bytes": 2147483648,
                "swap_used_bytes": 0,
            }
        }
        result = parse_metrics_to_prometheus(data, "inst1", "linux")
        assert "host_mem_total_bytes" in result
        assert "8589934592" in result
        assert "host_mem_swap_total_bytes" in result
        assert "host_mem_used_percent" in result

    def test_disk_metrics_with_dimensions(self):
        data = {
            "disk": [
                {"mount": "/", "total_bytes": 100000, "used_bytes": 50000, "used_percent": 50.0},
                {"mount": "/data", "total_bytes": 200000, "used_bytes": 100000, "used_percent": 50.0},
            ]
        }
        result = parse_metrics_to_prometheus(data, "inst1", "linux")
        assert 'mount="/"' in result
        assert 'mount="/data"' in result
        assert "host_disk_used_percent" in result

    def test_network_metrics_with_interface(self):
        data = {
            "net": [
                {"interface": "eth0", "rx_bytes": 1000, "tx_bytes": 2000, "rx_errors": 0, "tx_errors": 0},
            ]
        }
        result = parse_metrics_to_prometheus(data, "inst1", "windows")
        assert 'interface="eth0"' in result
        assert 'os_type="windows"' in result
        assert "host_net_rx_bytes" in result
        assert "host_net_tx_bytes" in result

    def test_empty_data(self):
        result = parse_metrics_to_prometheus({}, "inst1", "linux")
        # 空数据应只返回换行
        assert result == "\n"

    def test_all_modules_combined(self):
        data = {
            "cpu": {"usage_percent": 10, "core_count": 2, "load_1m": 0.5, "load_5m": 0.3, "load_15m": 0.1},
            "mem": {"total_bytes": 1000, "used_bytes": 500, "available_bytes": 500, "swap_total_bytes": 0, "swap_used_bytes": 0},
            "disk": [{"mount": "/", "total_bytes": 100, "used_bytes": 50, "used_percent": 50}],
            "net": [{"interface": "lo", "rx_bytes": 0, "tx_bytes": 0, "rx_errors": 0, "tx_errors": 0}],
        }
        result = parse_metrics_to_prometheus(data, "full_test", "linux")
        assert "host_cpu" in result
        assert "host_mem" in result
        assert "host_disk" in result
        assert "host_net" in result


class TestHostCollectorExtractStdout:
    """测试 Ansible 结果解析"""

    def setup_method(self):
        self.collector = HostCollector({
            "host": "10.0.0.1",
            "username": "root",
            "password": "test",
            "ansible_node_id": "node1",
        })

    def test_string_result(self):
        result = {"result": '{"cpu": {"usage_percent": 50}}'}
        assert self.collector._extract_stdout(result) == '{"cpu": {"usage_percent": 50}}'

    def test_dict_with_contacted(self):
        result = {
            "result": {
                "contacted": {
                    "10.0.0.1": {"stdout": '{"cpu": {}}', "rc": 0}
                }
            }
        }
        assert self.collector._extract_stdout(result) == '{"cpu": {}}'

    def test_dict_without_contacted(self):
        result = {
            "result": {
                "10.0.0.1": {"stdout": '{"mem": {}}', "rc": 0}
            }
        }
        assert self.collector._extract_stdout(result) == '{"mem": {}}'

    def test_empty_result(self):
        result = {"result": {}}
        # 空 dict 应返回 JSON 序列化
        stdout = self.collector._extract_stdout(result)
        assert stdout == "{}"


@pytest.mark.asyncio
class TestHostRemoteMonitorTask:
    async def test_collect_host_metrics_task_submits_callback_flow_and_returns_queued_status(
        self, monkeypatch
    ):
        import tasks.collectors.host_collector as host_collector_module
        import core.host_remote_callback as host_remote_callback_module

        class UnexpectedNatsServerModule(types.ModuleType):
            def __getattr__(self, name):
                raise AssertionError("collect_host_metrics_task must not depend on service.nats_server")

        monkeypatch.setitem(
            sys.modules,
            "service.nats_server",
            UnexpectedNatsServerModule("service.nats_server"),
        )
        monitor_handler = _load_monitor_handler_module(monkeypatch)
        monkeypatch.setattr(monitor_handler.time, "time", lambda: 1234.567)
        accepted_response = {
            "success": True,
            "result": {
                "accepted": True,
                "status": "queued",
                "task_id": "collect-task-1",
            },
        }
        call_order = []

        async def submit_collection(task_id, callback_subject, callback_payload):
            call_order.append(("submit", task_id, callback_subject, callback_payload))
            return accepted_response

        submit_collection = AsyncMock(side_effect=submit_collection)
        collect = AsyncMock(side_effect=AssertionError("collect should not be called"))

        class FakeCollector:
            def __init__(self, params):
                self.params = params
                self.collect = collect
                self.submit_collection = submit_collection

        monkeypatch.setattr(host_collector_module, "HostCollector", FakeCollector)
        async def store_callback_context(task_id, callback_params, ctx):
            call_order.append(("store", task_id, callback_params, ctx))

        store_callback_context = AsyncMock(side_effect=store_callback_context)
        monkeypatch.setattr(
            host_remote_callback_module,
            "store_host_remote_callback_context",
            store_callback_context,
        )

        nats_server = _load_nats_server_module(monkeypatch)
        params = _build_host_params()
        result = await monitor_handler.collect_host_metrics_task({}, params, "collect-task-1")
        callback_subject = host_remote_callback_module.get_host_remote_callback_subject()
        registered_service_name = nats_server.get_nats().service_name
        registered_subject = host_remote_callback_module.get_host_remote_callback_subject(
            registered_service_name
        )

        assert result["task_id"] == "collect-task-1"
        assert result["status"] == "queued"
        assert result["monitor_type"] == "host"
        assert result["accepted_task_id"] == "collect-task-1"
        assert result["defer_running_clear"] is True
        assert result["submitted_at"] == 1234567
        collect.assert_not_awaited()
        assert host_remote_callback_module.HOST_REMOTE_CALLBACK_HANDLER == "host_remote.callback"
        assert registered_service_name == host_remote_callback_module.get_stargazer_service_name()
        assert callback_subject == registered_subject
        assert (
            nats_server.get_nats().handlers[host_remote_callback_module.HOST_REMOTE_CALLBACK_HANDLER]
            is nats_server.handle_host_remote_callback
        )
        assert (
            nats_server.get_nats().handler_queues[host_remote_callback_module.HOST_REMOTE_CALLBACK_HANDLER]
            == host_remote_callback_module.get_host_remote_callback_queue(registered_service_name)
        )
        submit_collection.assert_awaited_once_with(
            "collect-task-1",
            callback_subject,
            {
                "collect_task_id": "collect-task-1",
                "instance_id": "region1_host_10.0.0.9",
                "instance_name": "10.0.0.9",
                "model_id": "host",
            },
        )
        store_callback_context.assert_awaited_once_with(
            "collect-task-1",
            {
                "callback_timestamp": 1234567,
                "host": "10.0.0.9",
                "os_type": "linux",
                "monitor_type": "host",
                "tags": {"instance_id": "region1_host_10.0.0.9"},
            },
            {},
        )
        assert [entry[0] for entry in call_order] == ["store", "submit"]

    async def test_collect_host_metrics_task_publishes_error_metrics_on_submission_failure(
        self, monkeypatch
    ):
        from tasks.handlers import monitor_handler
        import core.nats as core_nats
        import core.host_remote_callback as host_remote_callback_module
        import tasks.collectors.host_collector as host_collector_module
        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module
        import tasks.utils.metrics_helper as metrics_helper_module

        submit_collection = AsyncMock(side_effect=RuntimeError("submission failed"))
        publish_metrics = AsyncMock()
        error_metrics = "monitor_collection_status{status=\"error\"} 1 1\n"

        class FakeCollector:
            def __init__(self, params):
                self.submit_collection = submit_collection

        monkeypatch.setattr(host_collector_module, "HostCollector", FakeCollector)
        monkeypatch.setattr(
            core_nats,
            "get_nats",
            lambda: types.SimpleNamespace(service_name="stargazer-service"),
        )
        monkeypatch.setattr(
            host_remote_callback_module,
            "store_host_remote_callback_context",
            AsyncMock(),
        )
        monkeypatch.setattr(
            host_remote_callback_module,
            "clear_host_remote_callback_context",
            AsyncMock(),
        )
        monkeypatch.setattr(nats_helper_module, "publish_metrics_to_nats", publish_metrics)
        monkeypatch.setattr(
            metrics_helper_module,
            "generate_monitor_error_metrics",
            MagicMock(return_value=error_metrics),
        )

        params = _build_host_params()
        result = await monitor_handler.collect_host_metrics_task({"job": "ctx"}, params, "collect-task-2")

        assert result["status"] == "failed"
        assert result["error"] == "submission failed"
        publish_metrics.assert_awaited_once_with({"job": "ctx"}, error_metrics, params, "collect-task-2")

    async def test_collect_host_metrics_task_clears_pre_stored_context_when_submission_fails(
        self, monkeypatch
    ):
        import core.host_remote_callback as host_remote_callback_module
        import tasks.collectors.host_collector as host_collector_module
        from tasks.handlers import monitor_handler
        import core.nats as core_nats

        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module
        import tasks.utils.metrics_helper as metrics_helper_module

        call_order = []

        async def submit_collection(task_id, callback_subject, callback_payload):
            call_order.append(("submit", task_id, callback_subject, callback_payload))
            raise RuntimeError("submission failed")

        submit_collection = AsyncMock(side_effect=submit_collection)
        publish_metrics = AsyncMock()
        error_metrics = "monitor_collection_status{status=\"error\"} 1 1\n"

        class FakeCollector:
            def __init__(self, params):
                self.submit_collection = submit_collection

        async def store_callback_context(task_id, callback_params, ctx):
            call_order.append(("store", task_id, callback_params, ctx))

        store_callback_context = AsyncMock(side_effect=store_callback_context)

        async def clear_callback_context(task_id):
            call_order.append(("clear", task_id))

        clear_callback_context = AsyncMock(side_effect=clear_callback_context)

        monkeypatch.setattr(host_collector_module, "HostCollector", FakeCollector)
        monkeypatch.setattr(monitor_handler.time, "time", lambda: 1234.567)
        monkeypatch.setattr(
            core_nats,
            "get_nats",
            lambda: types.SimpleNamespace(service_name="stargazer-service"),
        )
        monkeypatch.setattr(
            host_remote_callback_module,
            "store_host_remote_callback_context",
            store_callback_context,
        )
        monkeypatch.setattr(
            host_remote_callback_module,
            "clear_host_remote_callback_context",
            clear_callback_context,
        )
        monkeypatch.setattr(nats_helper_module, "publish_metrics_to_nats", publish_metrics)
        monkeypatch.setattr(
            metrics_helper_module,
            "generate_monitor_error_metrics",
            MagicMock(return_value=error_metrics),
        )

        params = _build_host_params()
        result = await monitor_handler.collect_host_metrics_task({"job": "ctx"}, params, "collect-task-3")

        assert result["status"] == "failed"
        store_callback_context.assert_awaited_once_with(
            "collect-task-3",
            {
                "callback_timestamp": 1234567,
                "host": "10.0.0.9",
                "os_type": "linux",
                "monitor_type": "host",
                "tags": {"instance_id": "region1_host_10.0.0.9"},
            },
            {"job": "ctx"},
        )
        submit_collection.assert_awaited_once()
        clear_callback_context.assert_awaited_once_with("collect-task-3")
        assert [entry[0] for entry in call_order] == ["store", "submit", "clear"]


@pytest.mark.asyncio
class TestHostCollectorCollect:
    """测试完整采集流程（mock Ansible RPC）"""

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_submit_collection_passes_callback_and_returns_accepted_response(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": True,
            "result": {
                "accepted": True,
                "status": "queued",
                "task_id": "collect-123",
            },
        }

        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "port": "22",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "region1_host_10.0.0.1"},
        })

        result = await collector.submit_collection(
            "collect-123",
            "stargazer.host.callback",
            {
                "collect_task_id": "collect-123",
                "instance_id": "region1_host_10.0.0.1",
                "instance_name": "10.0.0.1",
                "model_id": "host",
            },
        )

        assert result["result"]["accepted"] is True
        assert result["result"]["status"] == "queued"
        assert result["result"]["task_id"] == "collect-123"

        mock_adhoc.assert_called_once()
        call_kwargs = mock_adhoc.call_args[1]
        assert call_kwargs["ansible_node_id"] == "region1"
        assert call_kwargs["module"] == "shell"
        assert call_kwargs["host_credentials"][0]["connection"] == "ssh"
        assert call_kwargs["task_id"] == "collect-123"
        assert call_kwargs["callback"] == {
            "collect_task_id": "collect-123",
            "instance_id": "region1_host_10.0.0.1",
            "instance_name": "10.0.0.1",
            "model_id": "host",
            "subject": "stargazer.host.callback",
            "timeout": HOST_REMOTE_CALLBACK_REQUEST_TIMEOUT,
        }

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_submit_collection_uses_configured_callback_timeout(self, mock_adhoc):
        mock_adhoc.return_value = {"success": True, "result": {"accepted": True, "status": "queued"}}

        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "port": "22",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "host_remote_callback_timeout": 90,
            "tags": {"instance_id": "region1_host_10.0.0.1"},
        })

        await collector.submit_collection(
            "collect-123",
            "stargazer.host.callback",
            {"collect_task_id": "collect-123"},
        )

        assert mock_adhoc.call_args[1]["callback"]["timeout"] == 90

    async def test_process_adhoc_result_returns_prometheus_metrics(self):
        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "region1_host_10.0.0.1"},
        })

        result = {
            "success": True,
            "result": {
                "contacted": {
                    "10.0.0.1": {
                        "stdout": json.dumps({
                            "cpu": {
                                "usage_percent": 25.0,
                                "core_count": 4,
                                "load_1m": 0.5,
                                "load_5m": 0.3,
                                "load_15m": 0.1,
                            }
                        }),
                        "rc": 0,
                    }
                }
            },
        }

        metrics = collector.process_adhoc_result(result)

        assert "host_cpu_usage_percent" in metrics
        assert 'instance_id="region1_host_10.0.0.1"' in metrics

    async def test_process_adhoc_result_supports_callback_result_list(self):
        collector = HostCollector({
            "host": "10.0.0.8",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "region1_host_10.0.0.8"},
        })

        result = {
            "task_id": "task-123",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.8",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 25.0,
                            "core_count": 4,
                            "load_1m": 0.5,
                            "load_5m": 0.3,
                            "load_15m": 0.1,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }

        metrics = collector.process_adhoc_result(result)

        assert "host_cpu_usage_percent" in metrics
        assert 'instance_id="region1_host_10.0.0.8"' in metrics

    async def test_process_adhoc_result_uses_stored_callback_timestamp(self):
        collector = HostCollector({
            "host": "10.0.0.8",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "callback_timestamp": 1234567890000,
            "tags": {"instance_id": "region1_host_10.0.0.8"},
        })

        result = {
            "task_id": "task-123",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.8",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 25.0,
                            "core_count": 4,
                            "load_1m": 0.5,
                            "load_5m": 0.3,
                            "load_15m": 0.1,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }

        metrics = collector.process_adhoc_result(result)

        assert "1234567890000" in metrics

    async def test_process_adhoc_result_reuses_stored_callback_timestamp_on_retry(self):
        collector = HostCollector({
            "host": "10.0.0.8",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "callback_timestamp": 1234567890000,
            "tags": {"instance_id": "region1_host_10.0.0.8"},
        })

        result = {
            "task_id": "task-123",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.8",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 25.0,
                            "core_count": 4,
                            "load_1m": 0.5,
                            "load_5m": 0.3,
                            "load_15m": 0.1,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }

        first_metrics = collector.process_adhoc_result(result)
        second_metrics = collector.process_adhoc_result(result)

        assert first_metrics == second_metrics

    @patch("tasks.collectors.host_collector.time.time", return_value=1234.567)
    async def test_process_adhoc_result_without_callback_timestamp_uses_current_time(
        self, _mock_time
    ):
        collector = HostCollector({
            "host": "10.0.0.8",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "region1_host_10.0.0.8"},
        })

        result = {
            "task_id": "task-123",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.8",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 25.0,
                            "core_count": 4,
                            "load_1m": 0.5,
                            "load_5m": 0.3,
                            "load_15m": 0.1,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }

        metrics = collector.process_adhoc_result(result)

        assert "1234567" in metrics

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_successful_collect_linux(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": True,
            "result": {
                "contacted": {
                    "10.0.0.1": {
                        "stdout": json.dumps({
                            "cpu": {"usage_percent": 25.0, "core_count": 4, "load_1m": 0.5, "load_5m": 0.3, "load_15m": 0.1},
                            "mem": {"total_bytes": 8000000000, "used_bytes": 4000000000, "available_bytes": 4000000000, "swap_total_bytes": 0, "swap_used_bytes": 0},
                        }),
                        "rc": 0,
                    }
                }
            },
        }

        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "port": "22",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu,mem",
            "tags": {"instance_id": "region1_host_10.0.0.1"},
        })

        result = await collector.collect()
        assert "host_cpu_usage_percent" in result
        assert "host_mem_total_bytes" in result
        assert 'instance_id="region1_host_10.0.0.1"' in result

        # 验证 adhoc 调用参数
        mock_adhoc.assert_called_once()
        call_kwargs = mock_adhoc.call_args[1]
        assert call_kwargs["ansible_node_id"] == "region1"
        assert call_kwargs["module"] == "shell"
        assert call_kwargs["host_credentials"][0]["connection"] == "ssh"

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_successful_collect_windows(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": True,
            "result": {
                "contacted": {
                    "10.0.0.2": {
                        "stdout": json.dumps({
                            "cpu": {"usage_percent": 60.0, "core_count": 8, "load_1m": 0, "load_5m": 0, "load_15m": 0},
                        }),
                        "rc": 0,
                    }
                }
            },
        }

        collector = HostCollector({
            "host": "10.0.0.2",
            "os_type": "windows",
            "username": "Administrator",
            "password": "secret",
            "port": "5986",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "region1_host_10.0.0.2"},
        })

        result = await collector.collect()
        assert "host_cpu_usage_percent" in result

        call_kwargs = mock_adhoc.call_args[1]
        assert call_kwargs["module"] == "win_shell"
        assert call_kwargs["host_credentials"][0]["connection"] == "winrm"
        assert call_kwargs["host_credentials"][0]["port"] == 5986

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_adhoc_failure_raises(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": False,
            "error": "Connection refused",
        }

        collector = HostCollector({
            "host": "10.0.0.3",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "x"},
        })

        with pytest.raises(RuntimeError, match="Host collection failed"):
            await collector.collect()

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_invalid_json_raises(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": True,
            "result": {"contacted": {"10.0.0.1": {"stdout": "not json at all", "rc": 0}}},
        }

        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "cpu",
            "tags": {"instance_id": "x"},
        })

        with pytest.raises(RuntimeError, match="Failed to parse metrics JSON"):
            await collector.collect()

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_default_modules_when_invalid(self, mock_adhoc):
        """当 metrics_modules 全部无效时，应使用所有默认模块"""
        mock_adhoc.return_value = {
            "success": True,
            "result": {"contacted": {"10.0.0.1": {"stdout": '{"cpu": {"usage_percent": 1, "core_count": 1, "load_1m": 0, "load_5m": 0, "load_15m": 0}}', "rc": 0}}},
        }

        collector = HostCollector({
            "host": "10.0.0.1",
            "os_type": "linux",
            "username": "root",
            "password": "secret",
            "ansible_node_id": "region1",
            "metrics_modules": "invalid1,invalid2",
            "tags": {"instance_id": "x"},
        })

        result = await collector.collect()
        # 应该正常完成（使用全部模块的脚本）
        assert "host_cpu" in result


class TestHostRemoteCallbackHelper:
    def test_get_host_remote_callback_subject_uses_service_name(self):
        import core.host_remote_callback as host_remote_callback_module

        assert host_remote_callback_module.get_host_remote_callback_subject("stargazer-service") == (
            "stargazer-service.host_remote.callback"
        )

    def test_get_host_remote_callback_queue_uses_service_name(self):
        import core.host_remote_callback as host_remote_callback_module

        assert host_remote_callback_module.get_host_remote_callback_queue("stargazer-service") == (
            "stargazer-service.host_remote.callback"
        )

    @pytest.mark.asyncio
    async def test_store_load_and_clear_host_remote_callback_context_with_fake_redis_pool(
        self, monkeypatch
    ):
        import core.host_remote_callback as host_remote_callback_module

        fake_pool = _install_fake_host_remote_callback_pool(monkeypatch)
        params = {"host": "10.0.0.9"}
        ctx = {"trace_id": "abc"}

        await host_remote_callback_module.store_host_remote_callback_context(
            "task-redis",
            params,
            ctx,
            ttl_seconds=123,
        )

        loaded = await host_remote_callback_module.load_host_remote_callback_context("task-redis")
        cleared = await host_remote_callback_module.clear_host_remote_callback_context("task-redis")

        assert fake_pool.last_set[0] == "host_remote:callback_context:task-redis"
        assert fake_pool.last_set[2] == 123
        assert json.loads(fake_pool.last_set[1]) == {"ctx": ctx, "params": params}
        assert loaded == {"ctx": ctx, "params": params}
        assert cleared == {"ctx": ctx, "params": params}
        assert fake_pool.deleted_keys == ["host_remote:callback_context:task-redis"]


@pytest.mark.asyncio
class TestHostRemoteCallbackHandler:
    async def test_host_remote_callback_handler_registration_uses_queue_group(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        service_name = nats_server.get_nats().service_name

        assert (
            nats_server.get_nats().handler_queues[nats_server.host_remote_callback.HOST_REMOTE_CALLBACK_HANDLER]
            == nats_server.host_remote_callback.get_host_remote_callback_queue(service_name)
        )

    async def test_host_remote_callback_handler_reads_context_via_shared_helper(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        params = _build_host_params()
        callback_payload = {
            "task_id": "task-122",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.9",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 42.0,
                            "core_count": 4,
                            "load_1m": 0.2,
                            "load_5m": 0.1,
                            "load_15m": 0.05,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }
        load_context = AsyncMock(return_value={"ctx": {}, "params": params})
        clear_context = AsyncMock(return_value={"ctx": {}, "params": params})
        record_callback_payload = AsyncMock(return_value={"ctx": {}, "params": params, "raw_callback": callback_payload})
        mark_processing_enqueued = AsyncMock()
        enqueue_processing = AsyncMock(return_value={"task_id": "task-122", "job_id": "process_host_remote_callback:task-122", "status": "queued"})
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "load_host_remote_callback_context",
            load_context,
        )
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "record_host_remote_callback_payload",
            record_callback_payload,
        )
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "mark_host_remote_processing_enqueued",
            mark_processing_enqueued,
        )
        clear_running_flag = AsyncMock()
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "clear_host_remote_running_flag",
            clear_running_flag,
        )
        monkeypatch.setattr(nats_server, "get_task_queue", lambda: types.SimpleNamespace(enqueue_host_remote_processing_task=enqueue_processing))

        result = await nats_server.handle_host_remote_callback({"args": [callback_payload], "kwargs": {}})

        assert result["status"] == "accepted"
        load_context.assert_awaited_once_with("task-122")
        record_callback_payload.assert_awaited_once_with("task-122", callback_payload)
        clear_running_flag.assert_awaited_once_with("task-122")
        enqueue_processing.assert_awaited_once_with("task-122")
        mark_processing_enqueued.assert_awaited_once_with(
            "task-122", processing_job_id="process_host_remote_callback:task-122"
        )

    async def test_host_remote_callback_handler_stores_payload_and_enqueues_processing(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        params = _build_host_params()
        callback_payload = {
            "task_id": "task-123",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.9",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 42.0,
                            "core_count": 4,
                            "load_1m": 0.2,
                            "load_5m": 0.1,
                            "load_15m": 0.05,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }
        clear_running_flag = AsyncMock()
        enqueue_processing = AsyncMock(return_value={"task_id": "task-123", "job_id": "process_host_remote_callback:task-123", "status": "queued"})
        monkeypatch.setattr(nats_server, "get_task_queue", lambda: types.SimpleNamespace(enqueue_host_remote_processing_task=enqueue_processing))
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "clear_host_remote_running_flag",
            clear_running_flag,
        )

        await nats_server.host_remote_callback.store_host_remote_callback_context("task-123", params)

        result = await nats_server.handle_host_remote_callback({"args": [callback_payload], "kwargs": {}})

        assert result["status"] == "accepted"
        enqueue_processing.assert_awaited_once_with("task-123")
        clear_running_flag.assert_awaited_once_with("task-123")
        assert callback_contexts["task-123"]["raw_callback"] == callback_payload
        assert callback_contexts["task-123"]["processing_job_id"] == "process_host_remote_callback:task-123"
        assert callback_contexts["task-123"]["status"]["delivery"] == "processing"

    async def test_host_remote_callback_handler_keeps_context_when_enqueue_processing_fails(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        params = _build_host_params()
        callback_payload = {"task_id": "task-456", "success": False, "error": "Connection refused"}
        clear_running_flag = AsyncMock()
        enqueue_processing = AsyncMock(side_effect=RuntimeError("enqueue failed"))
        monkeypatch.setattr(nats_server, "get_task_queue", lambda: types.SimpleNamespace(enqueue_host_remote_processing_task=enqueue_processing))
        monkeypatch.setattr(
            nats_server.host_remote_callback,
            "clear_host_remote_running_flag",
            clear_running_flag,
        )
        
        await nats_server.host_remote_callback.store_host_remote_callback_context("task-456", params)

        with pytest.raises(RuntimeError, match="enqueue failed"):
            await nats_server.handle_host_remote_callback({"args": [callback_payload], "kwargs": {}})

        clear_running_flag.assert_awaited_once_with("task-456")
        assert callback_contexts["task-456"]["raw_callback"] == callback_payload
        assert callback_contexts["task-456"]["status"]["delivery"] == "not_ready"

    async def test_host_remote_callback_handler_raises_for_missing_context(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        _install_fake_host_remote_callback_store(monkeypatch)

        with pytest.raises(RuntimeError, match="Missing Host Remote callback context for task_id=task-missing"):
            await nats_server.handle_host_remote_callback(
                {"args": [{"task_id": "task-missing", "success": True, "result": []}], "kwargs": {}}
            )


@pytest.mark.asyncio
class TestHostRemoteProcessWorker:
    async def test_process_host_remote_callback_task_publishes_metrics_and_clears_context(self, monkeypatch):
        handler = _load_host_remote_handler_module(monkeypatch)
        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module

        params = _build_host_params()
        callback_payload = {
            "task_id": "task-process-1",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.9",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 42.0,
                            "core_count": 4,
                            "load_1m": 0.2,
                            "load_5m": 0.1,
                            "load_15m": 0.05,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }
        callback_contexts["task-process-1"] = {
            "ctx": {},
            "params": params,
            "raw_callback": callback_payload,
            "status": {"execution": "execution_finished", "delivery": "processing"},
        }
        publish_metrics = AsyncMock()
        monkeypatch.setattr(nats_helper_module, "publish_metrics_to_nats", publish_metrics)

        result = await handler.process_host_remote_callback_task({}, {}, "task-process-1")

        assert result["status"] == "success"
        publish_metrics.assert_awaited_once()
        publish_args = publish_metrics.await_args.args
        assert publish_args[2] == params
        assert publish_args[3] == "task-process-1"
        assert "host_cpu_usage_percent" in publish_args[1]
        assert callback_contexts.get("task-process-1") is None

    async def test_process_host_remote_callback_task_publishes_error_metrics_on_processing_failure(self, monkeypatch):
        handler = _load_host_remote_handler_module(monkeypatch)
        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module
        import tasks.utils.metrics_helper as metrics_helper_module

        params = _build_host_params()
        callback_contexts["task-process-2"] = {
            "ctx": {},
            "params": params,
            "raw_callback": {"task_id": "task-process-2", "success": False, "error": "Connection refused"},
            "status": {"execution": "execution_finished", "delivery": "processing"},
        }
        publish_metrics = AsyncMock()
        error_metrics = "monitor_collection_status{status=\"error\"} 1 1\n"
        monkeypatch.setattr(nats_helper_module, "publish_metrics_to_nats", publish_metrics)
        monkeypatch.setattr(
            metrics_helper_module,
            "generate_monitor_error_metrics",
            MagicMock(return_value=error_metrics),
        )

        result = await handler.process_host_remote_callback_task({}, {}, "task-process-2")

        assert result["status"] == "failed"
        assert "Host collection failed" in result["error"]
        publish_metrics.assert_awaited_once_with({}, error_metrics, params, "task-process-2")
        assert callback_contexts["task-process-2"]["status"]["delivery"] == "delivery_failed"

    async def test_process_host_remote_callback_task_marks_failure_when_publish_fails(self, monkeypatch):
        handler = _load_host_remote_handler_module(monkeypatch)
        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module

        params = _build_host_params()
        callback_payload = {
            "task_id": "task-process-3",
            "success": True,
            "result": [
                {
                    "host": "10.0.0.9",
                    "status": "success",
                    "stdout": json.dumps({
                        "cpu": {
                            "usage_percent": 42.0,
                            "core_count": 4,
                            "load_1m": 0.2,
                            "load_5m": 0.1,
                            "load_15m": 0.05,
                        }
                    }),
                    "stderr": "",
                    "exit_code": 0,
                }
            ],
        }
        callback_contexts["task-process-3"] = {
            "ctx": {},
            "params": params,
            "raw_callback": callback_payload,
            "status": {"execution": "execution_finished", "delivery": "processing"},
        }
        monkeypatch.setattr(nats_helper_module, "publish_metrics_to_nats", AsyncMock(side_effect=RuntimeError("publish failed")))

        result = await handler.process_host_remote_callback_task({}, {}, "task-process-3")

        assert result["status"] == "retry_scheduled"
        assert callback_contexts["task-process-3"]["status"]["delivery"] == "publish_pending"
        assert callback_contexts["task-process-3"]["publish_attempts"] == 1


@pytest.mark.asyncio
class TestHostRemoteRuntime:
    async def test_sweeper_marks_waiting_callback_timeout(self, monkeypatch):
        runtime_module = _load_host_remote_runtime_module(monkeypatch)

        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        callback_contexts["task-timeout"] = {
            "task_id": "task-timeout",
            "ctx": {},
            "params": _build_host_params(),
            "status": {"execution": "waiting_callback", "delivery": "not_ready"},
            "callback_deadline_at": 1,
        }
        monkeypatch.setattr(
            runtime_module.host_remote_callback,
            "list_host_remote_callback_contexts",
            AsyncMock(return_value=[callback_contexts["task-timeout"]]),
        )
        monkeypatch.setattr(
            runtime_module.host_remote_callback,
            "_now_ms",
            lambda: 100,
        )
        clear_running_flag = AsyncMock()
        monkeypatch.setattr(
            runtime_module.host_remote_callback,
            "clear_host_remote_running_flag",
            clear_running_flag,
        )

        await runtime_module.sweep_host_remote_callback_contexts()

        assert callback_contexts["task-timeout"]["status"]["execution"] == "callback_timeout"
        clear_running_flag.assert_awaited_once_with("task-timeout")

    async def test_sweeper_reenqueues_publish_pending_retry(self, monkeypatch):
        runtime_module = _load_host_remote_runtime_module(monkeypatch)

        _, callback_contexts = _install_fake_host_remote_callback_store(monkeypatch)
        callback_contexts["task-retry"] = {
            "task_id": "task-retry",
            "ctx": {},
            "params": _build_host_params(),
            "status": {"execution": "execution_finished", "delivery": "publish_pending"},
            "next_retry_at": 1,
        }
        monkeypatch.setattr(
            runtime_module.host_remote_callback,
            "list_host_remote_callback_contexts",
            AsyncMock(return_value=[callback_contexts["task-retry"]]),
        )
        monkeypatch.setattr(runtime_module.host_remote_callback, "_now_ms", lambda: 100)
        enqueue_processing = AsyncMock(return_value={"task_id": "task-retry", "job_id": "process_host_remote_callback:task-retry"})
        monkeypatch.setattr(runtime_module, "get_task_queue", lambda: types.SimpleNamespace(enqueue_host_remote_processing_task=enqueue_processing))

        await runtime_module.sweep_host_remote_callback_contexts()

        enqueue_processing.assert_awaited_once_with("task-retry")
        assert callback_contexts["task-retry"]["status"]["delivery"] == "processing"

    def test_validate_host_remote_runtime_config_warns_on_nats_mismatch(self, monkeypatch):
        runtime_module = _load_host_remote_runtime_module(monkeypatch)

        warnings = []
        monkeypatch.setenv("NATS_URLS", "tls://nats-a:4222")
        monkeypatch.setenv("NATS_SERVERS", "tls://nats-b:4222")
        monkeypatch.setenv("TASK_JOB_TIMEOUT", "300")
        monkeypatch.setattr(runtime_module.logger, "warning", lambda message: warnings.append(message))

        runtime_module.validate_host_remote_runtime_config()

        assert any("NATS_URLS and NATS_SERVERS differ" in message for message in warnings)


@pytest.mark.asyncio
class TestPublishMetricsToNats:
    async def test_publish_metrics_to_nats_raises_when_any_line_publish_fails(self, monkeypatch):
        influxdb_client_module = types.ModuleType("influxdb_client")
        influxdb_client_module.Point = MagicMock()
        influxdb_client_module.WritePrecision = MagicMock()
        monkeypatch.setitem(sys.modules, "influxdb_client", influxdb_client_module)
        import tasks.utils.nats_helper as nats_helper_module

        published = []

        class FakeNatsConnection:
            is_closed = False

            async def publish(self, subject, payload):
                published.append((subject, payload))
                if len(published) == 2:
                    raise RuntimeError("line publish failed")

        class FakeNatsClient:
            def __init__(self, config):
                self.nc = FakeNatsConnection()
                self.is_connected = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(
            nats_helper_module,
            "convert_prometheus_to_influx",
            MagicMock(return_value=["metric value=1 1", "metric value=2 2"]),
        )
        monkeypatch.setattr(
            nats_helper_module.NATSConfig,
            "from_env",
            MagicMock(return_value=types.SimpleNamespace(servers=["nats://example"], tls_enabled=False, user="demo")),
        )
        monkeypatch.setattr(nats_helper_module, "NATSClient", FakeNatsClient)

        with pytest.raises(RuntimeError, match="line publish failed"):
            await nats_helper_module.publish_metrics_to_nats({}, "ignored", {"monitor_type": "host"}, "task-900")

        assert len(published) == 2


@pytest.mark.asyncio
class TestWorkerRunningFlag:
    async def test_collect_task_does_not_clear_running_flag_when_handler_defers_cleanup(
        self, monkeypatch
    ):
        worker = _load_worker_module(monkeypatch)
        clear_running_flag = AsyncMock()
        handler = AsyncMock(
            return_value={
                "task_id": "collect-task-worker",
                "status": "queued",
                "defer_running_clear": True,
            }
        )

        monitor_handler_module = types.ModuleType("tasks.handlers.monitor_handler")
        monitor_handler_module.collect_host_metrics_task = handler
        monkeypatch.setitem(sys.modules, "tasks.handlers.monitor_handler", monitor_handler_module)
        monkeypatch.setattr(worker, "_clear_running_flag", clear_running_flag)

        result = await worker.collect_task({}, {"monitor_type": "host"}, "collect-task-worker")

        assert result["defer_running_clear"] is True
        clear_running_flag.assert_not_awaited()

    async def test_process_host_remote_callback_worker_routes_to_handler(self, monkeypatch):
        worker = _load_worker_module(monkeypatch)
        handler = AsyncMock(return_value={"task_id": "task-worker-2", "status": "success"})
        host_remote_handler_module = types.ModuleType("tasks.handlers.host_remote_handler")
        host_remote_handler_module.process_host_remote_callback_task = handler
        monkeypatch.setitem(sys.modules, "tasks.handlers.host_remote_handler", host_remote_handler_module)

        result = await worker.process_host_remote_callback_task({}, {}, "task-worker-2")

        assert result["status"] == "success"
        handler.assert_awaited_once_with({}, {}, "task-worker-2")
