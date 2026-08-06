import pytest

from core.collection_runtime import CollectionRequest
from core.collection_plugins import (
    ConfigurationCollectionPlugin,
    MonitorCollectionPlugin,
    UnifiedPluginFactory,
)
from core.target_collection_executor import (
    CollectOutcomeStatus,
    TargetCollectionContext,
)


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
async def test_configuration_plugin_classifies_auth_failure_for_internal_rotation():
    class Service:
        def __init__(self, params):
            pass

        async def collect(self):
            return (
                'mysql_info{collect_status="failed",'
                'collect_error="authentication failed"} 1'
            )

    outcome = await ConfigurationCollectionPlugin(
        service_factory=Service
    ).collect(
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
            return (
                'network{collect_status="failed",'
                'collect_error="No SNMP response received before timeout"} 1'
            )

    outcome = await ConfigurationCollectionPlugin(
        service_factory=Service
    ).collect(
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
    factory = UnifiedPluginFactory()
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
