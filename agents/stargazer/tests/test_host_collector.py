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
    VALID_MODULES,
    SCRIPTS_DIR,
)


def _load_nats_server_module(monkeypatch):
    import core.nats as core_nats

    class DummyNatsInstance:
        def __init__(self):
            self.handlers = {}

        def register_handler(self, subject, queue=None):
            def decorator(handler):
                self.handlers[subject] = handler
                return handler

            return decorator

    monkeypatch.setattr(core_nats, "_nats_instance", DummyNatsInstance())
    collection_service_module = types.ModuleType("service.collection_service")
    collection_service_module.CollectionService = MagicMock()
    debug_service_module = types.ModuleType("service.debug.protocol_debug_service")
    debug_service_module.ProtocolDebugService = MagicMock()
    monkeypatch.setitem(sys.modules, "service.collection_service", collection_service_module)
    monkeypatch.setitem(sys.modules, "service.debug.protocol_debug_service", debug_service_module)
    monkeypatch.delitem(sys.modules, "service.nats_server", raising=False)
    return importlib.import_module("service.nats_server")


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
class TestHostCollectorCollect:
    """测试完整采集流程（mock Ansible RPC）"""

    @patch("core.ansible_rpc.ansible_adhoc", new_callable=AsyncMock)
    async def test_submit_collection_passes_callback_and_returns_accepted_response(self, mock_adhoc):
        mock_adhoc.return_value = {
            "success": True,
            "result": {
                "accepted": True,
                "status": "queued",
                "task_id": "task-123",
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
        assert result["result"]["task_id"] == "task-123"

        mock_adhoc.assert_called_once()
        call_kwargs = mock_adhoc.call_args[1]
        assert call_kwargs["ansible_node_id"] == "region1"
        assert call_kwargs["module"] == "shell"
        assert call_kwargs["host_credentials"][0]["connection"] == "ssh"
        assert call_kwargs["callback"] == {
            "collect_task_id": "collect-123",
            "instance_id": "region1_host_10.0.0.1",
            "instance_name": "10.0.0.1",
            "model_id": "host",
            "subject": "stargazer.host.callback",
            "timeout": 10,
        }

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


@pytest.mark.asyncio
class TestHostRemoteCallbackHandler:
    def _build_params(self):
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

    async def test_host_remote_callback_handler_publishes_processed_metrics(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        params = self._build_params()
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
        publish_metrics = AsyncMock()
        monkeypatch.setattr(nats_server, "publish_metrics_to_nats", publish_metrics)

        nats_server.register_host_remote_callback_context("task-123", params)

        result = await nats_server.handle_host_remote_callback({"args": [callback_payload], "kwargs": {}})

        assert result["status"] == "success"
        publish_metrics.assert_awaited_once()
        publish_args = publish_metrics.await_args.args
        assert publish_args[2] == params
        assert publish_args[3] == "task-123"
        assert "host_cpu_usage_percent" in publish_args[1]
        assert nats_server.pop_host_remote_callback_context("task-123") is None

    async def test_host_remote_callback_handler_publishes_error_metrics_on_processing_failure(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)
        params = self._build_params()
        callback_payload = {"task_id": "task-456", "success": False, "error": "Connection refused"}
        publish_metrics = AsyncMock()
        error_metrics = "monitor_collection_status{status=\"error\"} 1 1\n"
        generate_error_metrics = MagicMock(return_value=error_metrics)
        monkeypatch.setattr(nats_server, "publish_metrics_to_nats", publish_metrics)
        monkeypatch.setattr(nats_server, "generate_monitor_error_metrics", generate_error_metrics)

        nats_server.register_host_remote_callback_context("task-456", params)

        result = await nats_server.handle_host_remote_callback({"args": [callback_payload], "kwargs": {}})

        assert result["status"] == "failed"
        assert "Host collection failed" in result["error"]
        generate_error_metrics.assert_called_once()
        publish_metrics.assert_awaited_once_with({}, error_metrics, params, "task-456")
        assert nats_server.pop_host_remote_callback_context("task-456") is None

    async def test_host_remote_callback_handler_raises_for_missing_context(self, monkeypatch):
        nats_server = _load_nats_server_module(monkeypatch)

        with pytest.raises(RuntimeError, match="Missing Host Remote callback context for task_id=task-missing"):
            await nats_server.handle_host_remote_callback(
                {"args": [{"task_id": "task-missing", "success": True, "result": []}], "kwargs": {}}
            )
