import pytest
import sys
import types

from core.collection.plugins import MonitorCollectionPlugin, UnifiedPluginFactory
from core.collection.runtime import CollectionRequest
from core.collection.contracts import (
    CollectOutcomeStatus,
    TargetCollectionContext,
)


@pytest.mark.asyncio
async def test_optional_enterprise_monitor_runs_inside_unified_runtime(
    monkeypatch,
):
    captured = {}

    class Collector:
        def __init__(self, params):
            captured["params"] = params

        async def collect(self):
            return "metric 1"
    context = TargetCollectionContext(
        task_id="monitor-enterprise-1",
        plugin_ref="pure.monitor",
        fence=3,
        params={"monitor_type": "pure", "plugin_family": "monitor"},
    )

    outcome = await MonitorCollectionPlugin(
        {"pure": Collector}
    ).collect(
        "10.10.24.9", {"credential_id": "credential-1"}, context
    )

    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert captured["params"]["host"] == "10.10.24.9"


@pytest.mark.asyncio
async def test_unknown_monitor_stays_failed_when_no_extension_exists():
    context = TargetCollectionContext(
        task_id="monitor-unknown-1",
        plugin_ref="not_existing.monitor",
        fence=1,
        params={"monitor_type": "not_existing", "plugin_family": "monitor"},
    )

    with pytest.raises(ValueError, match="unsupported monitor_type"):
        await MonitorCollectionPlugin().collect("logical", {}, context)


def test_unified_factory_loads_optional_enterprise_collector_registry(monkeypatch):
    class Collector:
        pass

    module = types.ModuleType("enterprise.stargazer_collectors")
    module.get_monitor_collector_factories = lambda: {"pure": Collector}
    monkeypatch.setitem(sys.modules, "enterprise.stargazer_collectors", module)
    plugin = UnifiedPluginFactory().resolve(CollectionRequest(
        task_id="enterprise", plugin_ref="pure.monitor", targets=("10.0.0.1",),
        params={"plugin_family": "monitor", "monitor_type": "pure"},
    ))
    assert plugin._collector_factories["pure"] is Collector
