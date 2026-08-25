import subprocess
import sys
from unittest.mock import AsyncMock

import pytest
from core.collection.contracts import AccessProbeStatus
from core.plugin.executor import PluginExecutor
from core.plugin.yaml_reader import ExecutorConfig
from plugins.inputs.qcloud.qcloud_info import TencentCloudManager


def test_qcloud_manager_accepts_boolean_tls_from_plugin_policy():
    manager = TencentCloudManager(
        {
            "secret_id": "test-secret-id",
            "secret_key": "test-secret-key",
            "ssl": True,
        }
    )

    assert manager.protocol == "https"


def test_qcloud_bucket_collection_accepts_empty_bucket_payload():
    class EmptyBucketClient:
        @staticmethod
        def list_buckets():
            return {"Buckets": None}

    manager = TencentCloudManager(
        {
            "secret_id": "test-secret-id",
            "secret_key": "test-secret-key",
            "region_id": "ap-guangzhou",
        }
    )
    manager.available_region_list = ["ap-guangzhou"]
    manager.get_tencent_cos_client = lambda region: EmptyBucketClient()

    assert manager.get_qcloud_bucket() == []


def test_aliyun_collector_imports_on_supported_python_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from plugins.inputs.aliyun.aliyun_info import CwAliyun",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_dynamic_collector_fallback_is_not_treated_as_access_probe(monkeypatch):
    class DynamicFallbackCollector:
        def __getattr__(self, name):
            return lambda: {"result": True, "data": []}

    executor = PluginExecutor(
        "aliyun",
        ExecutorConfig(
            executor_type="protocol",
            config={"collector": {"module": "unused", "class": "Unused"}},
            plugin_config={"metadata": {}},
        ),
        {},
    )
    monkeypatch.setattr(
        executor,
        "_prepare_collector",
        AsyncMock(return_value=DynamicFallbackCollector()),
    )

    result = await executor.probe()

    assert result.status == AccessProbeStatus.NOT_SUPPORTED
