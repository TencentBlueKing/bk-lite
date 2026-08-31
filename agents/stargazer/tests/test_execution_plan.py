from pathlib import Path

import pytest
from core.collection.execution_plan import ExecutionPlanResolver, TimeoutDefaults
from core.collection.metrics import CollectionMetrics
from core.collection.runtime import CollectionRequest
from core.plugin.yaml_reader import ExecutorConfig, PluginYamlReader


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


def test_snmp_execution_plan_preserves_internal_retry_budget(monkeypatch):
    metrics = CollectionMetrics()
    warning_logs = []
    monkeypatch.setattr(
        "core.collection.execution_plan.logger.warning",
        lambda message, *args: warning_logs.append(message % args if args else message),
    )
    plan = ExecutionPlanResolver(defaults=TimeoutDefaults(), metrics=metrics).resolve(
        CollectionRequest(
            task_id="snmp-timeout-profile",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
            params={
                "executor_type": "protocol",
                "timeout": "10",
                "community": "must-not-be-logged",
            },
        )
    )

    assert plan.probe_timeout_seconds == 25
    assert plan.collection_timeout_seconds == 30
    assert metrics.snapshot()["snmp_timeout_clamped_total"] == 1
    assert len(warning_logs) == 1
    assert "event=snmp_collection_timeout_clamped" in warning_logs[0]
    assert "configured_seconds=10" in warning_logs[0]
    assert "effective_seconds=30" in warning_logs[0]
    assert "must-not-be-logged" not in warning_logs[0]


def test_snmp_execution_plan_clamps_low_environment_default_without_form_value():
    plan = ExecutionPlanResolver(
        defaults=TimeoutDefaults(collection_seconds=10),
    ).resolve(
        CollectionRequest(
            task_id="snmp-low-environment-default",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
            params={"executor_type": "protocol"},
        )
    )

    assert plan.collection_timeout_seconds == 30


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
    )

    plan = resolver.resolve(
        CollectionRequest(
            task_id="plan-default",
            plugin_ref="network.config",
            targets=("10.10.24.1",),
        )
    )

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


def test_execution_plan_uses_final_fallback_executor_config_without_rereading_yaml():
    class ReaderMustNotBeUsed:
        def __getattr__(self, name):
            raise AssertionError(f"unexpected YAML read: {name}")

    fallback = ExecutorConfig(
        executor_type="protocol",
        config={
            "execution_mode": "async",
            "capacity_group": "snmp",
            "probe_timeout": 25,
            "target_policy": {"mode": "snmp", "timeout": 15},
        },
        plugin_config={"metadata": {"type": "network"}},
    )
    request = CollectionRequest(
        task_id="fallback-plan",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"timeout": 45},
    )

    plan = ExecutionPlanResolver(reader=ReaderMustNotBeUsed()).resolve(
        request,
        executor_config=fallback,
    )

    assert plan.preflight_timeout_seconds == 15
    assert plan.probe_timeout_seconds == 25
    assert plan.collection_timeout_seconds == 45
    assert plan.execution_mode == "async"
    assert plan.capacity_group == "snmp"
