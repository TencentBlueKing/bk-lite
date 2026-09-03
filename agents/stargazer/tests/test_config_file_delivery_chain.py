import base64
import json
from types import SimpleNamespace

import api.collect as collect_api
import pytest
from core.collection.contracts import TargetCollectionContext, TargetCollectionResult
from core.collection.enums import CollectOutcomeStatus
from core.collection.plugins import ConfigurationCollectionPlugin
from core.collection.result_publisher import NatsResultPublisher
from core.collection.runtime import RunLease, Submission, SubmissionStatus
from plugins.inputs.config_file.config_file_info import ConfigFileInfo
from plugins.inputs.network_config_file.network_config_file_info import NetworkConfigFileInfo
from service.collection_service import CollectionService

INSTANCE_UUID = "123e4567-e89b-42d3-a456-426614174000"


class AdmissionApplication:
    def __init__(self):
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return Submission(task_id=request.task_id, status=SubmissionStatus.ACCEPTED, fence=7)


class FakeResponse:
    def __init__(self, result):
        self.result = result
        self.failed = False


class FakeNetworkConnection:
    def __init__(self):
        self.commands = []
        self.closed = False

    async def open(self):
        return None

    async def close(self):
        self.closed = True

    async def send_command(self, command):
        self.commands.append(command)
        return FakeResponse(f"output for {command}")


def _telegraf_request(headers):
    async def receive_body():
        return None

    return SimpleNamespace(
        method="GET",
        path="/api/collect/collect_info",
        query_string="",
        query_args=[],
        headers=headers,
        receive_body=receive_body,
    )


@pytest.mark.asyncio
async def test_telegraf_http_to_network_plugin_to_nats_callback_chain(monkeypatch):
    admission = AdmissionApplication()
    connection = FakeNetworkConnection()
    callbacks = []
    metrics_called = False
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: admission)
    monkeypatch.setattr(
        "plugins.inputs.network_config_file.network_config_file_info.AsyncScrapli",
        lambda **_kwargs: connection,
    )

    response = await collect_api.collect(
        _telegraf_request(
            {
                "cmdbplugin_name": "network_config_file_info",
                "cmdbmodel_id": "network_config_file",
                "cmdbexecutor_type": "protocol",
                "cmdbhosts": "10.0.0.8",
                "cmdbusername": "readonly",
                "cmdbpassword": "test-secret",
                "cmdbdevice_type": "cisco_ios",
                "cmdbcommands": "show running-config",
                "cmdbconfig_name": "running-config",
                "cmdbcollect_task_id": "42",
                "cmdbtarget_model_id": "switch",
                "cmdbtarget_instance_uuid": INSTANCE_UUID,
                "cmdbprotocol_version": "2",
                "cmdbcallback_subject": "receive_config_file_result",
                "instance_id": "cmdb_42_123e4567e89b42d3a456426614174000",
                "instance_type": "cmdb_network_config_file",
                "collect_type": "http",
                "config_type": "network_config_file",
            }
        )
    )

    assert response.status == 202
    request = admission.requests[0]

    class NetworkExecutor:
        def __init__(self, params):
            self.params = params

        async def execute(self):
            return await NetworkConfigFileInfo(self.params).list_all_resources()

    def service_factory(params):
        return CollectionService(
            params,
            prepared_executor_factory=lambda runtime_params: NetworkExecutor(runtime_params),
        )

    plugin = ConfigurationCollectionPlugin(service_factory=service_factory)
    context = TargetCollectionContext(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        fence=7,
        params=request.params,
        owner_id="pod-a",
        attempt_id="attempt-1",
    )
    outcome = await plugin.collect(request.targets[0], request.credentials[0], context)

    assert outcome.status is CollectOutcomeStatus.SUCCESS

    async def publish_callback(payload, params, task_id):
        callbacks.append((payload, params, task_id))

    async def publish_metrics(*_args):
        nonlocal metrics_called
        metrics_called = True

    publisher = NatsResultPublisher(
        metrics_publish=publish_metrics,
        callback_publish=publish_callback,
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="attempt-1",
    )
    await publisher.publish(
        request,
        TargetCollectionResult(
            target=request.targets[0],
            status="success",
            attempts=1,
            value=outcome.value,
        ),
        lease,
    )

    assert metrics_called is False
    assert connection.closed is True
    assert "show running-config" in connection.commands
    assert len(callbacks) == 1
    payload, callback_params, _task_id = callbacks[0]
    assert callback_params["callback_subject"] == "receive_config_file_result"
    assert payload["collect_task_id"] == "42"
    assert payload["protocol_version"] == "2"
    assert payload["instance_uuid"] == INSTANCE_UUID
    assert payload["model_id"] == "switch"
    assert payload["file_path"] == "network://running-config"
    assert payload["status"] == "success"
    assert payload["content_base64"]
    assert "execution_id" not in payload


@pytest.mark.asyncio
async def test_telegraf_http_to_host_plugin_to_nats_callback_chain(monkeypatch):
    admission = AdmissionApplication()
    callbacks = []
    metrics_called = False
    collected_content = "server { listen 80; }"
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: admission)

    response = await collect_api.collect(
        _telegraf_request(
            {
                "cmdbplugin_name": "config_file_info",
                "cmdbmodel_id": "config_file",
                "cmdbexecutor_type": "job",
                "cmdbhosts": "10.0.0.10",
                "cmdbnode_id": "node-9",
                "cmdbusername": "readonly",
                "cmdbpassword": "test-secret",
                "cmdbconfig_file_path": "/etc/nginx/nginx.conf",
                "cmdbcollect_task_id": "43",
                "cmdbtarget_model_id": "host",
                "cmdbtarget_instance_uuid": INSTANCE_UUID,
                "cmdbprotocol_version": "2",
                "cmdbcallback_subject": "receive_config_file_result",
                "instance_id": "cmdb_43_123e4567e89b42d3a456426614174000",
                "instance_type": "cmdb_config_file",
                "collect_type": "http",
                "config_type": "config_file",
            }
        )
    )

    assert response.status == 202
    request = admission.requests[0]

    class HostPlugin(ConfigFileInfo):
        async def _execute_script(self, script_content):
            assert "FILE_PATH='/etc/nginx/nginx.conf'" in script_content
            return {
                "success": True,
                "result": json.dumps(
                    {
                        "status": "success",
                        "content_base64": base64.b64encode(collected_content.encode()).decode(),
                        "size": len(collected_content.encode()),
                    }
                ),
            }

    class HostExecutor:
        def __init__(self, params):
            self.params = {**params, "script_path": "plugins/inputs/config_file/config_file_discover.sh"}

        async def execute(self):
            return await HostPlugin(self.params).list_all_resources()

    def service_factory(params):
        return CollectionService(
            params,
            prepared_executor_factory=lambda runtime_params: HostExecutor(runtime_params),
        )

    plugin = ConfigurationCollectionPlugin(service_factory=service_factory)
    context = TargetCollectionContext(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        fence=8,
        params=request.params,
        owner_id="pod-a",
        attempt_id="attempt-2",
    )
    outcome = await plugin.collect(request.targets[0], request.credentials[0], context)

    assert outcome.status is CollectOutcomeStatus.SUCCESS

    async def publish_callback(payload, params, task_id):
        callbacks.append((payload, params, task_id))

    async def publish_metrics(*_args):
        nonlocal metrics_called
        metrics_called = True

    publisher = NatsResultPublisher(
        metrics_publish=publish_metrics,
        callback_publish=publish_callback,
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=8,
        expires_at=999999,
        attempt_id="attempt-2",
    )
    await publisher.publish(
        request,
        TargetCollectionResult(
            target=request.targets[0],
            status="success",
            attempts=1,
            value=outcome.value,
        ),
        lease,
    )

    assert metrics_called is False
    assert len(callbacks) == 1
    payload, callback_params, _task_id = callbacks[0]
    assert callback_params["callback_subject"] == "receive_config_file_result"
    assert payload["collect_task_id"] == "43"
    assert payload["protocol_version"] == "2"
    assert payload["instance_uuid"] == INSTANCE_UUID
    assert payload["model_id"] == "host"
    assert payload["file_path"] == "/etc/nginx/nginx.conf"
    assert payload["status"] == "success"
    assert base64.b64decode(payload["content_base64"]).decode() == collected_content
    assert "execution_id" not in payload
