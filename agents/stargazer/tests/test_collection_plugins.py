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
