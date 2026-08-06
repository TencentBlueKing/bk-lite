import pytest

from core.collection_plugins import MonitorCollectionPlugin
from core.target_collection_executor import (
    CollectOutcomeStatus,
    TargetCollectionContext,
)


@pytest.mark.asyncio
async def test_windows_wmi_runs_through_unified_monitor_plugin():
    captured = {}

    class Collector:
        def __init__(self, params):
            captured.update(params)

        async def collect(self):
            return "windows_wmi_collection_up 1\n"

    context = TargetCollectionContext(
        task_id="task-wmi-1",
        plugin_ref="windows_wmi.monitor",
        fence=2,
        params={
            "monitor_type": "windows_wmi",
            "plugin_family": "monitor",
            "namespace": "root\\cimv2",
        },
    )

    outcome = await MonitorCollectionPlugin(
        {"windows_wmi": Collector}
    ).collect(
        "10.10.24.8",
        {
            "credential_id": "credential-1",
            "username": "administrator",
            "password": "secret",
        },
        context,
    )

    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert outcome.value == "windows_wmi_collection_up 1\n"
    assert captured["host"] == "10.10.24.8"
    assert captured["collection_task_id"] == "task-wmi-1"
    assert captured["collection_fence"] == 2
