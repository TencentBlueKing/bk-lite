import pytest

from apps.workflow_orchestration.atom_packages.bklite_job_execute.runtime.handler import execute as execute_job_atom
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


class FakeTargetGateway:
    def __init__(self):
        self.calls = []

    def resolve(self, source, source_ids):
        self.calls.append((source, source_ids))
        if source != "job_mgmt":
            return []
        return [
            {
                "id": f"manual:{source_id}",
                "source": "job_mgmt",
                "source_id": source_id,
                "name": f"job-host-{source_id}",
                "ip": "10.0.0.5",
                "operating_system": "linux",
                "cloud_region_id": 1,
                "connected": None,
            }
            for source_id in source_ids
        ]


def _inputs(*targets, script_type="shell", script_content="echo ok"):
    return {
        "targets": list(targets),
        "script_type": script_type,
        "script_content": script_content,
        "execution_params": "--check",
        "timeout_seconds": 60,
        "team": 7,
        "actor": {"username": "operator", "domain": "example.com"},
    }


def _target(source_id, operating_system="linux", source="node_mgmt"):
    return {
        "id": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "name": f"host-{source_id}",
        "ip": "10.0.0.1",
        "operating_system": operating_system,
    }


def test_job_output_uses_unified_envelope_and_optional_json_marker():
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {
                        "target_key": "n1",
                        "status": "success",
                        "exit_code": 0,
                        "stdout": 'log\nBK_LITE_RESULT={"cpu":{"usage_percent":42}}',
                    }
                ]
            }
        ]
    )

    output = execute_custom_script(_inputs(_target("n1")), executor=runner)

    assert output["summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert output["results"][0]["status"] == "SUCCESS"
    assert output["results"][0]["data"] == {"cpu": {"usage_percent": 42}}
    assert output["results"][0]["error"] is None


def test_job_output_extracts_json_marker_from_ansible_wrapped_stdout():
    wrapped_stdout = "\n\n".join(
        [
            '{"changed": true, "path": "C:\\\\Temp\\\\inspection.ps1"}',
            (
                '{"changed": true, "stdout": "BK_LITE_RESULT={\\"metric_count\\":1,'
                '\\"metrics\\":[{\\"category\\":\\"CPU\\",\\"value\\":12.5}]}\\r\\n", "rc": 0}'
            ),
            '{"changed": true}',
        ]
    )
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {
                        "target_key": "n1",
                        "status": "success",
                        "exit_code": 0,
                        "stdout": wrapped_stdout,
                    }
                ]
            }
        ]
    )

    output = execute_custom_script(_inputs(_target("n1")), executor=runner)

    assert output["summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert output["results"][0]["data"] == {
        "metric_count": 1,
        "metrics": [{"category": "CPU", "value": 12.5}],
    }


def test_parse_optional_data_only_reads_bounded_stdout_prefix():
    from apps.workflow_orchestration.services.job_operations import MAX_CAPTURED_OUTPUT, _parse_optional_data

    marker = 'BK_LITE_RESULT={"ok":true}'
    # Marker sits beyond the capture window so unbounded parsing would find it.
    stdout = ("x" * (MAX_CAPTURED_OUTPUT + 1)) + "\n" + marker

    assert _parse_optional_data(stdout) is None
    assert _parse_optional_data(marker + "\n" + ("y" * MAX_CAPTURED_OUTPUT)) == {"ok": True}


def test_invalid_result_marker_fails_the_node():
    runner = FakeExecutor([{"execution_results": [{"target_key": "n1", "status": "success", "exit_code": 0, "stdout": "BK_LITE_RESULT={bad"}]}])

    with pytest.raises(ValueError, match="有效 JSON"):
        execute_custom_script(_inputs(_target("n1")), executor=runner)


def test_script_failures_stay_in_results_and_do_not_stop_the_report():
    runner = FakeExecutor([{"execution_results": [{"target_key": "n1", "status": "failed", "stderr": "boom"}]}])

    output = execute_custom_script(_inputs(_target("n1")), executor=runner)

    assert output["summary"] == {"total": 1, "succeeded": 0, "failed": 1}
    assert output["results"][0]["status"] == "FAILED"
    assert output["results"][0]["error"] == "boom"


def test_targets_are_grouped_by_source_for_one_script_type():
    runner = FakeExecutor(
        [
            {"execution_results": [{"target_key": "n1", "status": "success", "stdout": "ok"}]},
            {"execution_results": [{"target_key": "5", "status": "success", "stdout": "ok"}]},
        ]
    )

    output = execute_custom_script(
        _inputs(
            _target("n1", "linux", "node_mgmt"),
            _target(5, "linux", "job_mgmt"),
        ),
        executor=runner,
    )

    assert [(item["target_source"], item["script_type"], item["params"]) for item in runner.submissions] == [
        ("node_mgmt", "shell", [{"value": "--check"}]),
        ("manual", "shell", [{"value": "--check"}]),
    ]
    assert output["summary"] == {"total": 2, "succeeded": 2, "failed": 0}


def test_mixed_os_targets_are_submitted_like_job_platform_without_prefilter():
    """与作业平台对齐：同一种脚本可混选 Linux/Windows，整批下发，不在编排侧预拒。"""
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {"target_key": "win-1", "status": "success", "exit_code": 0, "stdout": "ok"},
                    {
                        "target_key": "linux-1",
                        "status": "failed",
                        "exit_code": 1,
                        "stderr": "win_shell incompatible",
                    },
                ]
            }
        ]
    )

    output = execute_custom_script(
        _inputs(
            _target("win-1", "windows", "node_mgmt"),
            _target("linux-1", "linux", "node_mgmt"),
            script_type="powershell",
            script_content="Write-Output ok",
        ),
        executor=runner,
    )

    assert len(runner.submissions) == 1
    assert runner.submissions[0]["script_type"] == "powershell"
    assert [node["source_id"] for node in runner.submissions[0]["nodes"]] == ["win-1", "linux-1"]
    assert output["summary"] == {"total": 2, "succeeded": 1, "failed": 1}
    by_ip_os = {(item["target"]["operating_system"], item["status"]): item for item in output["results"]}
    assert by_ip_os[("windows", "SUCCESS")]["exit_code"] == 0
    assert by_ip_os[("linux", "FAILED")]["error"] == "win_shell incompatible"


def test_job_atom_accepts_mixed_os_targets_for_single_script_type():
    class MixedOsGateway:
        def __init__(self):
            self.calls = []

        def resolve(self, source, source_ids):
            self.calls.append((source, list(source_ids)))
            catalog = {
                "5": {
                    "id": "manual:5",
                    "source": "job_mgmt",
                    "source_id": "5",
                    "name": "win-host",
                    "ip": "10.10.90.120",
                    "operating_system": "windows",
                    "cloud_region_id": 5,
                    "connected": True,
                },
                "3": {
                    "id": "manual:3",
                    "source": "job_mgmt",
                    "source_id": "3",
                    "name": "linux-host",
                    "ip": "192.168.64.5",
                    "operating_system": "linux",
                    "cloud_region_id": 5,
                    "connected": True,
                },
            }
            return [catalog[source_id] for source_id in source_ids if source_id in catalog]

    gateway = MixedOsGateway()
    runner = FakeExecutor(
        [
            {
                "execution_results": [
                    {"target_key": "5", "status": "success", "exit_code": 0, "stdout": "ok"},
                    {"target_key": "3", "status": "failed", "exit_code": 1, "stderr": "module mismatch"},
                ]
            }
        ]
    )

    output = execute_job_atom(
        {
            "targets": ["manual:5", "manual:3"],
            "script_type": "powershell",
            "script_content": "Write-Output ok",
            "execution_params": "",
            "timeout_seconds": 60,
            "team": 1,
            "actor": {"username": "admin", "domain": "domain.com"},
            "__bklite_context": {
                "organization_id": 1,
                "actor": {"username": "admin", "domain": "domain.com"},
            },
        },
        gateway=gateway,
        executor=runner,
    )

    assert gateway.calls == [("job_mgmt", ["5", "3"])]
    assert runner.submissions[0]["script_type"] == "powershell"
    assert output["summary"] == {"total": 2, "succeeded": 1, "failed": 1}


def test_job_atom_revalidates_selected_references_with_trusted_execution_identity():
    gateway = FakeTargetGateway()
    runner = FakeExecutor([{"execution_results": [{"target_key": "5", "status": "success", "stdout": "ok"}]}])

    output = execute_job_atom(
        {
            **_inputs("manual:5"),
            "team": 999,
            "actor": {"username": "spoofed", "domain": "attacker.example"},
            "__bklite_context": {
                "organization_id": 7,
                "actor": {"username": "operator", "domain": "example.com"},
            },
        },
        gateway=gateway,
        executor=runner,
    )

    assert gateway.calls == [("job_mgmt", ["5"])]
    assert runner.submissions[0]["team"] == 7
    assert runner.submissions[0]["actor"] == {"username": "operator", "domain": "example.com"}
    assert runner.submissions[0]["nodes"][0]["id"] == "manual:5"
    assert output["summary"] == {"total": 1, "succeeded": 1, "failed": 0}


def test_job_atom_rejects_fixed_targets_without_trusted_execution_context():
    with pytest.raises(ValueError, match="缺少可信流程上下文"):
        execute_job_atom(_inputs("manual:5"), gateway=FakeTargetGateway(), executor=FakeExecutor([]))
