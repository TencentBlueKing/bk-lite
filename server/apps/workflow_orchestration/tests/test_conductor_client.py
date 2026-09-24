import json

import httpx
import pytest

from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorConfigurationError


def test_rejects_unsafe_conductor_base_url():
    with pytest.raises(ConductorConfigurationError):
        ConductorClient("http://user:secret@conductor:8080/api")


def test_register_and_start_use_conductor_oss_api():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/workflow/demo":
            return httpx.Response(200, text="workflow-123")
        return httpx.Response(204)

    client = ConductorClient(
        "http://conductor:8080/api",
        transport=httpx.MockTransport(handler),
    )
    client.register_task_definitions([{"name": "demo", "timeoutSeconds": 30}])
    client.register_workflow({"name": "demo", "version": 1, "tasks": []})
    workflow_id = client.start_workflow("demo", version=1, inputs={"message": "hello"})

    assert workflow_id == "workflow-123"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/metadata/taskdefs"),
        ("POST", "/api/metadata/workflow"),
        ("POST", "/api/workflow/demo"),
    ]
    assert requests[2].url.params["version"] == "1"


def test_execution_controls_use_conductor_oss_api():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/workflow/workflow-123/rerun":
            return httpx.Response(200, text="workflow-456")
        return httpx.Response(204)

    client = ConductorClient("http://conductor:8080/api", transport=httpx.MockTransport(handler))

    client.retry_workflow("workflow-123")
    client.restart_workflow("workflow-123")
    client.terminate_workflow("workflow-123", reason="manual")
    rerun_id = client.rerun_workflow("workflow-123", task_id="task-9", correlation_id="local-2")

    assert rerun_id == "workflow-456"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/workflow/workflow-123/retry"),
        ("POST", "/api/workflow/workflow-123/restart"),
        ("DELETE", "/api/workflow/workflow-123"),
        ("POST", "/api/workflow/workflow-123/rerun"),
    ]
    assert not requests[0].url.params
    assert requests[2].url.params["reason"] == "manual"
    assert json.loads(requests[3].read()) == {
        "reRunFromWorkflowId": "workflow-123",
        "reRunFromTaskId": "task-9",
        "correlationId": "local-2",
    }


def test_conductor_client_ignores_ambient_http_proxy(mocker):
    client_factory = mocker.patch("apps.workflow_orchestration.services.conductor.httpx.Client")

    ConductorClient(base_url="http://conductor.internal:8080/api")

    assert client_factory.call_args.kwargs["trust_env"] is False


def test_register_workflow_compensates_orphaned_conductor_version():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(409, json={"message": "already exists"})
        return httpx.Response(204)

    client = ConductorClient(
        "http://conductor:8080/api",
        transport=httpx.MockTransport(handler),
    )
    definition = {"name": "demo", "version": 1, "tasks": []}

    client.register_workflow(definition)

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/metadata/workflow"),
        ("PUT", "/api/metadata/workflow"),
    ]
    assert json.loads(requests[1].read()) == [definition]
