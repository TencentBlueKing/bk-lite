from pathlib import Path

import pytest
from core.collection.execution_plan import ExecutionPlanResolver, TimeoutDefaults
from core.collection.runtime import CollectionRequest
from core.plugin.yaml_reader import PluginYamlReader


def _write_plugin(root: Path, body: str) -> None:
    plugin_dir = root / "network"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yml").write_text(body, encoding="utf-8")


def test_execution_plan_uses_yaml_metadata_and_task_collection_budget(tmp_path):
    _write_plugin(
        tmp_path,
        """
metadata:
  type: network
default_executor: protocol
executors:
  protocol:
    type: protocol
    probe_timeout: 14
    execution_mode: async
    capacity_group: snmp
    target_policy:
      mode: snmp
      timeout: 13
""",
    )
    resolver = ExecutionPlanResolver(
        reader=PluginYamlReader(plugins_base_dir=str(tmp_path)),
        defaults=TimeoutDefaults(
            preflight_seconds=15,
            probe_seconds=15,
            collection_seconds=60,
            publish_seconds=30,
        ),
        preflight_enabled=True,
    )

    plan = resolver.resolve(
        CollectionRequest(
            task_id="plan-yaml",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
            params={"executor_type": "protocol", "timeout": "90"},
        )
    )

    assert plan.preflight_timeout_seconds == 13
    assert plan.probe_timeout_seconds == 14
    assert plan.collection_timeout_seconds == 90
    assert plan.publish_timeout_seconds == 30
    assert plan.execution_mode == "async"
    assert plan.capacity_group == "snmp"


def test_execution_plan_missing_task_timeout_defaults_to_collection_timeout(tmp_path):
    _write_plugin(
        tmp_path,
        """
metadata:
  type: network
default_executor: protocol
executors:
  protocol:
    type: protocol
    collector:
      module: plugins.inputs.network.snmp_facts
      class: SnmpFacts
""",
    )
    resolver = ExecutionPlanResolver(
        reader=PluginYamlReader(plugins_base_dir=str(tmp_path)),
        defaults=TimeoutDefaults(),
        preflight_enabled=False,
    )

    plan = resolver.resolve(
        CollectionRequest(
            task_id="plan-default",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
        )
    )

    assert plan.preflight_enabled is False
    assert plan.preflight_timeout_seconds == 15
    assert plan.probe_timeout_seconds == 15
    assert plan.collection_timeout_seconds == 60
    assert plan.publish_timeout_seconds == 30
    assert plan.execution_mode == "sync"
    assert plan.capacity_group == "default"


def test_execution_plan_accepts_network_topology_capacity_group(tmp_path):
    _write_plugin(
        tmp_path,
        """
metadata:
  type: network
default_executor: protocol
executors:
  protocol:
    type: protocol
    capacity_group: network_topology
""",
    )
    resolver = ExecutionPlanResolver(
        reader=PluginYamlReader(plugins_base_dir=str(tmp_path)),
        defaults=TimeoutDefaults(),
        preflight_enabled=True,
    )

    plan = resolver.resolve(
        CollectionRequest(
            task_id="topology-plan",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
        )
    )

    assert plan.capacity_group == "network_topology"


@pytest.mark.parametrize(
    ("raw_timeout", "expected"),
    (
        ("1", 1.0),
        ("86400", 86400.0),
        ("0", 60.0),
        ("", 60.0),
        (None, 60.0),
        ("0.5", 1.0),
        ("90000", 86400.0),
    ),
)
def test_execution_plan_clamps_task_collection_budget(tmp_path, raw_timeout, expected):
    _write_plugin(
        tmp_path,
        """
metadata:
  type: network
executors:
  protocol:
    type: protocol
""",
    )
    resolver = ExecutionPlanResolver(
        reader=PluginYamlReader(plugins_base_dir=str(tmp_path)),
        defaults=TimeoutDefaults(collection_seconds=60),
        preflight_enabled=True,
    )
    params = {"executor_type": "protocol"}
    if raw_timeout is not None:
        params["timeout"] = raw_timeout

    plan = resolver.resolve(
        CollectionRequest(
            task_id="plan-clamp",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
            params=params,
        )
    )

    assert plan.collection_timeout_seconds == expected


def test_execution_plan_ignores_yaml_executor_timeout(tmp_path):
    _write_plugin(
        tmp_path,
        """
metadata:
  type: network
executors:
  protocol:
    type: protocol
    timeout: 300
""",
    )
    resolver = ExecutionPlanResolver(
        reader=PluginYamlReader(plugins_base_dir=str(tmp_path)),
        defaults=TimeoutDefaults(collection_seconds=60),
        preflight_enabled=True,
    )

    plan = resolver.resolve(
        CollectionRequest(
            task_id="plan-ignore-yaml-timeout",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
            params={"timeout": "120"},
        )
    )

    assert plan.collection_timeout_seconds == 120
