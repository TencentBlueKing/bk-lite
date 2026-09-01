"""受限 Pod exec 工具单测。不连真实集群。"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.kubernetes import exec_ops as e


@pytest.fixture
def exec_env():
    core = MagicMock()
    with patch.object(e, "prepare_context", return_value=None), patch.object(e.client, "CoreV1Api", return_value=core), patch.object(
        e, "stream", return_value="200 0.012s"
    ) as stream_fn:
        yield core, stream_fn


class TestExecInPod:
    def test_allows_whitelisted_curl(self, exec_env):
        _, stream_fn = exec_env
        out = json.loads(
            e.exec_in_pod.invoke(
                {
                    "namespace": "nacos",
                    "pod_name": "nacos-0",
                    "command": [
                        "curl",
                        "-s",
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code} %{time_total}",
                        "http://127.0.0.1:8848/nacos/v1/console/health/readiness",
                    ],
                    "config": {},
                }
            )
        )
        assert out["success"] is True
        assert "200" in out["stdout"]
        stream_fn.assert_called_once()

    def test_rejects_shell(self, exec_env):
        out = json.loads(e.exec_in_pod.invoke({"namespace": "nacos", "pod_name": "nacos-0", "command": ["sh", "-c", "id"], "config": {}}))
        assert out["success"] is False
        assert "白名单" in out["error"]

    def test_rejects_string_command(self, exec_env):
        out = json.loads(e.exec_in_pod.invoke({"namespace": "nacos", "pod_name": "nacos-0", "command": "curl http://127.0.0.1", "config": {}}))
        assert out["success"] is False
        assert "数组" in out["error"] or "列表" in out["error"]

    def test_rejects_shell_metacharacters(self, exec_env):
        out = json.loads(e.exec_in_pod.invoke({"namespace": "nacos", "pod_name": "nacos-0", "command": ["curl", "http://x; rm -rf /"], "config": {}}))
        assert out["success"] is False

    def test_approval_metadata_required(self):
        meta = e.exec_in_pod.metadata or {}
        assert (meta.get("approval") or {}).get("required") is True
