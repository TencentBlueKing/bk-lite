import pytest

from apps.workflow_orchestration.services.job_platform import JobPlatformError, JobPlatformExecutor


class FakeJobClient:
    def __init__(self, detail=None):
        self.submitted = None
        self.detail = detail or {"result": True, "data": {"status": "success", "execution_results": []}}

    def execute_automation_script(self, payload, actor_context):
        self.submitted = payload
        self.actor_context = actor_context
        return {"result": True, "data": {"task_id": 9}}

    def get_automation_execution_statuses(self, data, actor_context):
        return {"result": True, "data": [{"task_id": 9, "status": "success"}]}

    def get_automation_execution_detail(self, data, actor_context):
        return self.detail


def test_submit_uses_node_ids_and_team_boundary():
    client = FakeJobClient()
    executor = JobPlatformExecutor(client=client, sleep=lambda _: None)

    task_id = executor.submit(
        name="巡检",
        nodes=[
            {
                "id": "node:n1",
                "source": "node_mgmt",
                "source_id": "n1",
                "name": "host",
                "ip": "10.0.0.1",
                "operating_system": "linux",
            }
        ],
        team=7,
        target_source="node_mgmt",
        script_type="python",
        script_content="print('ok')",
        timeout=60,
        actor={"username": "operator", "domain": "example.com"},
    )

    assert task_id == 9
    assert client.submitted["team"] == [7]
    assert client.actor_context == {
        "username": "operator",
        "domain": "example.com",
        "authorized_team_ids": [7],
    }
    assert client.submitted["target_list"] == [{"node_id": "n1", "name": "host", "ip": "10.0.0.1", "os": "linux"}]


def test_job_rejection_is_typed_error():
    client = FakeJobClient()
    client.execute_automation_script = lambda payload, actor_context: {"result": False, "message": "危险命令"}

    with pytest.raises(JobPlatformError, match="危险命令"):
        JobPlatformExecutor(client=client).submit(
            name="巡检",
            nodes=[{"id": "node:n1", "source_id": "n1", "operating_system": "linux"}],
            team=7,
            target_source="node_mgmt",
            script_type="shell",
            script_content="bad",
            timeout=60,
            actor={"username": "operator", "domain": "example.com"},
        )


def test_submit_manual_target_uses_controlled_target_id_not_ip_identity():
    client = FakeJobClient()

    JobPlatformExecutor(client=client).submit(
        name="Windows 巡检",
        nodes=[
            {
                "id": "manual:5",
                "source": "manual",
                "source_id": 5,
                "name": "job-web3",
                "ip": "10.10.90.120",
                "operating_system": "windows",
            }
        ],
        team=1,
        target_source="manual",
        script_type="powershell",
        script_content="Write-Output ok",
        timeout=60,
        actor={"username": "operator", "domain": "example.com"},
    )

    assert client.submitted["target_list"] == [
        {
            "target_id": 5,
            "name": "job-web3",
            "ip": "10.10.90.120",
            "os": "windows",
        }
    ]


def test_submit_rejects_unsupported_source_missing_actor_and_missing_source_id():
    client = FakeJobClient()
    executor = JobPlatformExecutor(client=client)

    with pytest.raises(JobPlatformError, match="不支持的作业目标来源"):
        executor.submit(
            name="x",
            nodes=[{"source_id": "n1"}],
            team=7,
            target_source="cmdb",
            script_type="shell",
            script_content="echo",
            timeout=60,
            actor={"username": "operator", "domain": "example.com"},
        )
    with pytest.raises(JobPlatformError, match="缺少可信执行人"):
        executor.submit(
            name="x",
            nodes=[{"source_id": "n1"}],
            team=7,
            target_source="node_mgmt",
            script_type="shell",
            script_content="echo",
            timeout=60,
            actor={"username": "  ", "domain": "example.com"},
        )
    with pytest.raises(JobPlatformError, match="缺少受控引用 ID"):
        executor.submit(
            name="x",
            nodes=[{"name": "host"}],
            team=7,
            target_source="node_mgmt",
            script_type="shell",
            script_content="echo",
            timeout=60,
            actor={"username": "operator", "domain": "example.com"},
        )


def test_wait_returns_terminal_detail_and_times_out(mocker):
    client = FakeJobClient(detail={"result": True, "data": {"status": "success", "execution_results": [{"ok": True}]}})
    sleeps = []
    executor = JobPlatformExecutor(client=client, sleep=sleeps.append)

    # pending then success
    statuses = iter(
        [
            {"result": True, "data": [{"task_id": 9, "status": "running"}]},
            {"result": True, "data": [{"task_id": 9, "status": "success"}]},
        ]
    )
    client.get_automation_execution_statuses = lambda data, actor_context: next(statuses)
    clock = iter([100.0, 100.5, 101.0, 101.5])
    mocker.patch("apps.workflow_orchestration.services.job_platform.time.monotonic", side_effect=lambda: next(clock))

    detail = executor.wait(9, team=7, timeout=10, actor={"username": "operator", "domain": "example.com"})
    assert detail["status"] == "success"
    assert sleeps == [1]

    # detail fetch failure
    client.get_automation_execution_statuses = lambda data, actor_context: {
        "result": True,
        "data": [{"task_id": 9, "status": "failed"}],
    }
    client.detail = {"result": False, "message": "详情不可用"}
    mocker.patch(
        "apps.workflow_orchestration.services.job_platform.time.monotonic",
        side_effect=[200.0, 200.5],
    )
    with pytest.raises(JobPlatformError, match="详情不可用"):
        JobPlatformExecutor(client=client, sleep=lambda _: None).wait(9, team=7, timeout=10, actor={"username": "operator", "domain": "example.com"})

    # timeout while still running
    client.get_automation_execution_statuses = lambda data, actor_context: {
        "result": True,
        "data": [{"task_id": 9, "status": "running"}],
    }
    mocker.patch(
        "apps.workflow_orchestration.services.job_platform.time.monotonic",
        side_effect=[300.0, 311.0],
    )
    with pytest.raises(JobPlatformError, match="等待超时"):
        JobPlatformExecutor(client=client, sleep=lambda _: None).wait(9, team=7, timeout=10, actor={"username": "operator", "domain": "example.com"})
