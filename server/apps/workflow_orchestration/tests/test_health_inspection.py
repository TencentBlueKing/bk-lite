import json

import pytest

from apps.workflow_orchestration.services.job_operations import execute_custom_script


class FakeExecutor:
    def __init__(self, details):
        self.details = details
        self.submissions = []

    def submit(self, **kwargs):
        task_id = len(self.submissions) + 1
        self.submissions.append(kwargs)
        return task_id

    def wait(self, task_id, **kwargs):
        return self.details[task_id - 1]


def _windows_target():
    return {
        "id": "manual:1",
        "source": "job_mgmt",
        "source_id": "1",
        "name": "Windows 巡检主机",
        "ip": "10.10.90.120",
        "operating_system": "windows",
    }


def _inputs():
    return {
        "targets": [_windows_target()],
        "script_type": "powershell",
        "script_content": "Write-Output ok",
        "execution_params": "",
        "timeout_seconds": 60,
        "team": 1,
        "actor": {"username": "admin", "domain": "domain.com"},
    }


def test_health_job_envelope_keeps_multidimensional_disk_warning_evidence():
    payload = {
        "collected_at": "2026-09-23T00:00:00Z",
        "metrics": [
            {
                "category": "CPU",
                "object_type": "processor",
                "object_name": "CPU Total",
                "dimensions": "core=all",
                "metric_name": "usage_percent",
                "value": 42,
                "unit": "%",
                "warning_threshold": 80,
                "critical_threshold": 90,
                "health_status": "NORMAL",
                "collected_at": "2026-09-23T00:00:00Z",
                "detail": "CPU 总使用率",
            },
            {
                "category": "磁盘",
                "object_type": "logical_disk",
                "object_name": "D:",
                "dimensions": "mount=D:",
                "metric_name": "usage_percent",
                "value": 87.6,
                "unit": "%",
                "warning_threshold": 80,
                "critical_threshold": 90,
                "health_status": "WARNING",
                "collected_at": "2026-09-23T00:00:00Z",
                "detail": "total_gb=500,used_gb=438",
            },
            {
                "category": "网络",
                "object_type": "network_adapter",
                "object_name": "Ethernet0",
                "dimensions": "adapter=Ethernet0",
                "metric_name": "throughput_mbps",
                "value": 18.6,
                "unit": "Mbps",
                "warning_threshold": 800,
                "critical_threshold": 950,
                "health_status": "NORMAL",
                "collected_at": "2026-09-23T00:00:00Z",
                "detail": "网卡总吞吐率",
            },
        ],
        "metric_count": 3,
        "critical": [],
        "warning": [],
        "normal": [],
        "critical_count": 0,
        "warning_count": 1,
        "normal_count": 2,
        "conclusion": "需关注",
    }
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {
                        "target_key": "1",
                        "status": "success",
                        "exit_code": 0,
                        "stdout": f"BK_LITE_RESULT={json.dumps(payload, ensure_ascii=False)}",
                    }
                ]
            }
        ]
    )

    output = execute_custom_script(_inputs(), executor=runner)

    assert output["summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert output["results"][0]["target"]["ip"] == "10.10.90.120"
    data = output["results"][0]["data"]
    assert {metric["category"] for metric in data["metrics"]} >= {"CPU", "磁盘", "网络"}
    disk = next(metric for metric in data["metrics"] if metric["object_name"] == "D:")
    assert disk["dimensions"] == "mount=D:"
    assert disk["health_status"] == "WARNING"


def test_script_failure_stays_in_results_and_keeps_node_success_summary():
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {
                        "target_key": "1",
                        "status": "failed",
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": "host offline",
                    }
                ]
            }
        ]
    )

    output = execute_custom_script(_inputs(), executor=runner)

    assert output["summary"] == {"total": 1, "succeeded": 0, "failed": 1}
    assert output["results"][0]["status"] == "FAILED"
    assert output["results"][0]["data"] is None
    assert "offline" in output["results"][0]["error"]


def test_invalid_bk_lite_result_json_fails_the_job_node():
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {
                        "target_key": "1",
                        "status": "success",
                        "exit_code": 0,
                        "stdout": "BK_LITE_RESULT={not-json",
                    }
                ]
            }
        ]
    )

    with pytest.raises(ValueError, match="BK_LITE_RESULT"):
        execute_custom_script(_inputs(), executor=runner)
