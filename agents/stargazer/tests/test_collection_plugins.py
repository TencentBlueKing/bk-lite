import asyncio

import pytest
from core.collection.contracts import AccessProbeResult, AccessProbeStatus, CollectOutcomeStatus, StructuredMetricsPayload, TargetCollectionContext
from core.collection.plugins import ConfigurationCollectionPlugin, MonitorCollectionPlugin, UnifiedPluginFactory
from core.collection.runtime import CollectionRequest


@pytest.mark.asyncio
async def test_configuration_plugin_exposes_credential_protocol_probe():
    captured = {}

    class Service:
        def __init__(self, params):
            captured.update(params)

        async def probe(self):
            return AccessProbeResult(status=AccessProbeStatus.READY)

    result = await ConfigurationCollectionPlugin(service_factory=Service).probe(
        "10.10.24.1",
        {
            "credential_id": "credential-1",
            "username": "collector",
            "password": "secret",
        },
        TargetCollectionContext(
            task_id="config-probe",
            plugin_ref="mysql.config",
            fence=1,
            params={
                "model_id": "mysql",
                "executor_type": "protocol",
                "timeout": 20,
            },
        ),
        timeout_seconds=5,
    )

    assert result.status == AccessProbeStatus.READY
    assert captured["host"] == "10.10.24.1"
    assert captured["credential_id"] == "credential-1"
    assert captured["timeout"] == 5


@pytest.mark.asyncio
async def test_job_plugin_injects_run_node_info_before_service_probe_and_collect():
    captured = []

    class Lookup:
        async def get(self, target, *, connect_host=""):
            assert target == "10.10.24.9"
            assert connect_host == "10.10.24.9"
            return {
                "id": "node-9",
                "ip": "10.10.24.9",
                "operating_system": "linux",
            }

    class Service:
        def __init__(self, params):
            captured.append(dict(params))

        async def probe(self):
            return AccessProbeResult(status=AccessProbeStatus.READY)

        async def collect(self):
            return 'host{collect_status="success"} 1'

    plugin = ConfigurationCollectionPlugin(
        service_factory=Service,
        node_info_lookup=Lookup(),
    )
    context = TargetCollectionContext(
        task_id="job-node-info",
        plugin_ref="host.config",
        fence=1,
        params={
            "model_id": "host",
            "executor_type": "job",
            "_validated_connect_host": "10.10.24.9",
        },
    )

    await plugin.probe(
        "10.10.24.9",
        {"credential_id": "credential-1"},
        context,
        timeout_seconds=5,
    )
    await plugin.collect(
        "10.10.24.9",
        {"credential_id": "credential-1"},
        context,
    )

    assert len(captured) == 2
    assert all(params["node_info"]["id"] == "node-9" for params in captured)


@pytest.mark.asyncio
async def test_monitor_plugin_exposes_same_credential_protocol_probe():
    class MonitorCollector:
        def __init__(self, params):
            self.params = params

        async def probe(self):
            assert self.params["host"] == "10.10.24.2"
            assert self.params["timeout"] == 5
            return AccessProbeResult(status=AccessProbeStatus.READY)

    result = await MonitorCollectionPlugin({"database": MonitorCollector}).probe(
        "10.10.24.2",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="monitor-probe",
            plugin_ref="database.monitor",
            fence=1,
            params={"monitor_type": "database", "timeout": 20},
        ),
        timeout_seconds=5,
    )

    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_monitor_host_probe_is_not_supported_without_fake_unknown():
    result = await MonitorCollectionPlugin().probe(
        "10.10.24.3",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="host-probe",
            plugin_ref="host.monitor",
            fence=1,
            params={"monitor_type": "host"},
        ),
        timeout_seconds=5,
    )
    assert result.status == AccessProbeStatus.NOT_SUPPORTED


@pytest.mark.asyncio
async def test_monitor_plugin_without_collector_probe_returns_not_supported():
    class MonitorCollector:
        def __init__(self, params):
            self.params = params

    result = await MonitorCollectionPlugin({"database": MonitorCollector}).probe(
        "10.10.24.2",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="monitor-no-probe",
            plugin_ref="database.monitor",
            fence=1,
            params={"monitor_type": "database"},
        ),
        timeout_seconds=5,
    )
    assert result.status == AccessProbeStatus.NOT_SUPPORTED


@pytest.mark.asyncio
async def test_configuration_plugin_merges_one_target_and_one_credential():
    captured = {}

    class Service:
        def __init__(self, params):
            captured.update(params)

        async def collect(self):
            return 'mysql_info{collect_status="success"} 1'

    plugin = ConfigurationCollectionPlugin(service_factory=Service)
    context = TargetCollectionContext(
        task_id="config-1",
        plugin_ref="mysql.config",
        fence=3,
        params={
            "model_id": "mysql",
            "plugin_name": "mysql_info",
            "executor_type": "protocol",
        },
    )

    outcome = await plugin.collect(
        "10.10.24.1",
        {
            "credential_id": "credential-1",
            "username": "root",
            "password": "secret",
        },
        context,
    )

    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert captured["host"] == "10.10.24.1"
    assert captured["credential_id"] == "credential-1"
    assert captured["password"] == "secret"
    assert "credentials_pool" not in captured


@pytest.mark.asyncio
async def test_configuration_plugin_uses_preflight_pinned_connect_host():
    captured = {}

    class Service:
        def __init__(self, params):
            captured.update(params)

        async def collect(self):
            return 'mysql_info{collect_status="success"} 1'

    context = TargetCollectionContext(
        task_id="config-pinned-host",
        plugin_ref="mysql.config",
        fence=1,
        params={"model_id": "mysql", "_validated_connect_host": "10.0.0.8"},
    )

    await ConfigurationCollectionPlugin(service_factory=Service).collect(
        "db.trusted.example",
        {"credential_id": "credential-1"},
        context,
    )

    assert captured["host"] == "10.0.0.8"
    assert captured["target_hostname"] == "db.trusted.example"
    assert "_validated_connect_host" not in captured


@pytest.mark.asyncio
async def test_configuration_runtime_requests_structured_metrics_output():
    captured = {}
    payload = StructuredMetricsPayload(data={"network": ({"host": "10.10.24.1", "port": 161},)})

    class Service:
        def __init__(self, params):
            captured.update(params)

        async def collect(self):
            return payload

    outcome = await ConfigurationCollectionPlugin(service_factory=Service).collect(
        "10.10.24.1",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="structured-config",
            plugin_ref="network.config",
            fence=1,
            params={"model_id": "network", "executor_type": "protocol"},
        ),
    )

    assert captured["_runtime_structured_metrics"] is True
    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert outcome.value is payload


@pytest.mark.asyncio
async def test_configuration_plugin_classifies_auth_failure_for_internal_rotation():
    class Service:
        def __init__(self, params):
            pass

        async def collect(self):
            return 'mysql_info{collect_status="failed",' 'collect_error="authentication failed"} 1'

    outcome = await ConfigurationCollectionPlugin(service_factory=Service).collect(
        "10.10.24.1",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="config-auth",
            plugin_ref="mysql.config",
            fence=1,
            params={"model_id": "mysql", "executor_type": "protocol"},
        ),
    )

    assert outcome.status == CollectOutcomeStatus.AUTH_FAILED
    assert outcome.error_code == "authentication_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected_status,expected_code",
    [
        ("HCI TLS validation failed", CollectOutcomeStatus.UNREACHABLE, "tls_validation_failed"),
        ("HCI product/API mismatch at public-key endpoint", CollectOutcomeStatus.FAILED, "product_api_mismatch"),
    ],
)
async def test_configuration_plugin_preserves_hci_failure_classification(error, expected_status, expected_code):
    class Service:
        def __init__(self, params):
            pass

        async def collect(self):
            return StructuredMetricsPayload(data={}, error=error)

    outcome = await ConfigurationCollectionPlugin(service_factory=Service).collect(
        "192.0.2.17",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="config-hci-error",
            plugin_ref="sangforhci.config",
            fence=1,
            params={"model_id": "sangforhci", "executor_type": "protocol"},
        ),
    )

    assert outcome.status == expected_status
    assert outcome.error_code == expected_code


@pytest.mark.asyncio
async def test_snmp_no_response_rotates_without_auth_cooldown():
    class Service:
        def __init__(self, params):
            pass

        async def collect(self):
            return 'network{collect_status="failed",' 'collect_error="No SNMP response received before timeout"} 1'

    outcome = await ConfigurationCollectionPlugin(service_factory=Service).collect(
        "10.10.24.1",
        {"credential_id": "credential-1"},
        TargetCollectionContext(
            task_id="config-snmp",
            plugin_ref="network.config",
            fence=1,
            params={"model_id": "network", "executor_type": "protocol"},
        ),
    )

    assert outcome.status == CollectOutcomeStatus.RETRY_CREDENTIAL


def test_factory_routes_configuration_and_monitor_to_one_contract():
    factory = UnifiedPluginFactory(configuration_service_factory=lambda params: params)
    configuration = CollectionRequest(
        task_id="config",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        params={"plugin_family": "configuration"},
    )
    monitor = CollectionRequest(
        task_id="monitor",
        plugin_ref="windows_wmi.monitor",
        targets=("10.10.24.2",),
        params={"plugin_family": "monitor", "monitor_type": "windows_wmi"},
    )

    assert isinstance(factory.resolve(configuration), ConfigurationCollectionPlugin)
    assert isinstance(factory.resolve(monitor), MonitorCollectionPlugin)


@pytest.mark.asyncio
async def test_run_preparation_failure_preserves_target_level_service_contract(monkeypatch):
    warning_logs = []
    monkeypatch.setattr(
        "core.collection.plugins.logger.warning",
        lambda message, *args: warning_logs.append(message % args if args else message),
    )

    class Service:
        @classmethod
        async def prepare(cls, _params):
            raise RuntimeError("token=must-not-be-logged")

        def __init__(self, _params):
            pass

        async def collect(self):
            return 'network{collect_status="success"} 1'

    request = CollectionRequest(
        task_id="prepare-fallback",
        plugin_ref="network.config",
        targets=("10.0.0.1",),
        params={"model_id": "network", "executor_type": "protocol"},
    )
    plugin = ConfigurationCollectionPlugin(service_factory=Service)

    await plugin.prepare(request)
    outcome = await plugin.collect(
        "10.0.0.1",
        {"credential_id": "one"},
        TargetCollectionContext(
            task_id=request.task_id,
            plugin_ref=request.plugin_ref,
            fence=1,
            params=request.params,
        ),
    )

    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert len(warning_logs) == 1
    assert "event=collection_run_preparation_fallback" in warning_logs[0]
    assert "error_type=RuntimeError" in warning_logs[0]
    assert "must-not-be-logged" not in warning_logs[0]


@pytest.mark.asyncio
async def test_factory_scopes_one_node_info_batch_to_one_job_run():
    targets = tuple(f"10.20.0.{index}" for index in range(1, 101))
    load_calls = []

    async def load(ips, **_context):
        load_calls.append(tuple(ips))
        return [{"id": f"node-{ip}", "ip": ip, "operating_system": "linux"} for ip in ips]

    class Service:
        def __init__(self, params):
            self.params = params

        async def collect(self):
            assert self.params["node_info"]["ip"] == self.params["host"]
            return 'host{collect_status="success"} 1'

    request = CollectionRequest(
        task_id="job-run-100",
        plugin_ref="host.config",
        targets=targets,
        params={
            "plugin_family": "configuration",
            "model_id": "host",
            "executor_type": "job",
            "collect_task_id": 91,
        },
    )
    plugin = UnifiedPluginFactory(
        configuration_service_factory=Service,
        configuration_node_info_loader=load,
    ).resolve(request)
    context = TargetCollectionContext(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        fence=1,
        params=request.params,
    )

    await asyncio.gather(*(plugin.collect(target, {"credential_id": "credential-1"}, context) for target in targets))
    close = getattr(plugin, "close", None)
    if close is not None:
        await close()

    assert load_calls == [targets]


@pytest.mark.asyncio
async def test_job_probe_and_collect_credentials_reuse_one_run_lookup():
    calls = 0

    async def load(ips, **_context):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [{"id": "node-1", "ip": ips[0], "operating_system": "linux"}]

    class Service:
        def __init__(self, params):
            assert params["node_info"]["id"] == "node-1"

        async def probe(self):
            return AccessProbeResult(status=AccessProbeStatus.READY)

        async def collect(self):
            return 'host{collect_status="success"} 1'

    request = CollectionRequest(
        task_id="job-credentials",
        plugin_ref="host.config",
        targets=("10.0.0.1",),
        params={
            "plugin_family": "configuration",
            "model_id": "host",
            "executor_type": "job",
            "collect_task_id": 91,
        },
    )
    plugin = UnifiedPluginFactory(
        configuration_service_factory=Service,
        configuration_node_info_loader=load,
    ).resolve(request)
    context = TargetCollectionContext(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        fence=1,
        params=request.params,
    )

    await asyncio.gather(
        plugin.probe("10.0.0.1", {"credential_id": "one"}, context, timeout_seconds=5),
        plugin.probe("10.0.0.1", {"credential_id": "two"}, context, timeout_seconds=5),
    )
    await plugin.collect("10.0.0.1", {"credential_id": "two"}, context)
    close = getattr(plugin, "close", None)
    if close is not None:
        await close()

    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"plugin_family": "configuration", "executor_type": "protocol"},
        {"plugin_family": "configuration", "executor_type": "job"},
        {"plugin_family": "monitor", "monitor_type": "host"},
    ],
)
async def test_non_job_or_unscoped_request_does_not_load_job_node_info(params):
    async def unexpected_load(*_args, **_kwargs):
        raise AssertionError("node info loader must not be called")

    class Service:
        def __init__(self, _params):
            pass

        async def collect(self):
            return 'host{collect_status="success"} 1'

    request = CollectionRequest(
        task_id="not-scoped-job",
        plugin_ref="host.config",
        targets=("10.0.0.1",),
        params=params,
    )
    plugin = UnifiedPluginFactory(
        configuration_service_factory=Service,
        configuration_node_info_loader=unexpected_load,
    ).resolve(request)
    if params["plugin_family"] == "configuration":
        await plugin.collect(
            "10.0.0.1",
            {"credential_id": "one"},
            TargetCollectionContext(
                task_id=request.task_id,
                plugin_ref=request.plugin_ref,
                fence=1,
                params=request.params,
            ),
        )
    close = getattr(plugin, "close", None)
    if close is not None:
        await close()
