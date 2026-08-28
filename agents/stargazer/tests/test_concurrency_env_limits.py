from pathlib import Path

import pytest
from core.collection.application import CollectionApplicationSettings, concurrency_limit_from_env
from core.collection.constants import DEFAULT_MAX_ACTIVE_TARGETS, DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS, DEFAULT_TARGET_TASK_WINDOW
from core.collection.contracts import TargetExecutorSettings
from core.collection.executor import TargetWorkerBudget


def test_default_concurrency_matches_production_baseline():
    assert DEFAULT_MAX_ACTIVE_TARGETS == 250
    assert DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS == 50
    assert DEFAULT_TARGET_TASK_WINDOW == 250
    assert TargetExecutorSettings().max_active_targets == 250
    assert TargetExecutorSettings().target_task_window == 250


def test_concurrency_limit_from_env_uses_default_and_zero_unlimited(monkeypatch):
    monkeypatch.delenv("MAX_ACTIVE_TARGETS", raising=False)
    assert concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS) == DEFAULT_MAX_ACTIVE_TARGETS

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "3500")
    assert concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS) == 3500

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "0")
    assert concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS) == 0

    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "-1")
    with pytest.raises(ValueError, match="MAX_ACTIVE_TARGETS"):
        concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS)


def test_application_settings_from_env_reads_concurrency(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "250")
    monkeypatch.setenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS", "30")
    monkeypatch.setenv("TARGET_TASK_WINDOW", "0")
    settings = CollectionApplicationSettings.from_env()
    assert settings.max_active_targets == 250
    assert settings.network_topology_max_active_targets == 30
    assert settings.target_task_window == 0

    monkeypatch.delenv("MAX_ACTIVE_TARGETS", raising=False)
    monkeypatch.delenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS", raising=False)
    monkeypatch.delenv("TARGET_TASK_WINDOW", raising=False)
    settings = CollectionApplicationSettings.from_env()
    assert settings.max_active_targets == DEFAULT_MAX_ACTIVE_TARGETS
    assert settings.network_topology_max_active_targets == DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS
    assert settings.target_task_window == DEFAULT_TARGET_TASK_WINDOW
    monkeypatch.delenv("CAPACITY_LOG_INTERVAL", raising=False)
    assert CollectionApplicationSettings.from_env().capacity_log_interval_seconds == 180

    monkeypatch.setenv("CAPACITY_LOG_INTERVAL", "45")
    assert CollectionApplicationSettings.from_env().capacity_log_interval_seconds == 45


@pytest.mark.parametrize("raw_value", ("0", "101", "-1", "not-an-int"))
def test_network_topology_limit_rejects_invalid_values(monkeypatch, raw_value):
    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "250")
    monkeypatch.setenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS", raw_value)

    with pytest.raises(ValueError, match="NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS"):
        CollectionApplicationSettings.from_env()


def test_network_topology_limit_must_be_less_than_bounded_total(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "50")
    monkeypatch.setenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS", "50")

    with pytest.raises(ValueError, match="less than MAX_ACTIVE_TARGETS"):
        CollectionApplicationSettings.from_env()


def test_network_topology_limit_allows_unbounded_total(monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_TARGETS", "0")
    monkeypatch.setenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS", "100")

    settings = CollectionApplicationSettings.from_env()

    assert settings.max_active_targets == 0
    assert settings.network_topology_max_active_targets == 100


def test_application_settings_split_timeouts_and_keep_legacy_fallback(monkeypatch):
    monkeypatch.setenv("CONNECT_TIMEOUT", "9")
    monkeypatch.setenv("PLUGIN_TIMEOUT", "70")
    monkeypatch.delenv("PREFLIGHT_TIMEOUT", raising=False)
    monkeypatch.delenv("PROBE_TIMEOUT", raising=False)
    monkeypatch.delenv("COLLECTION_TIMEOUT", raising=False)
    monkeypatch.setenv("PUBLISH_TIMEOUT", "31")
    monkeypatch.delenv("PUBLISH_DELIVERY_TIMEOUT", raising=False)
    monkeypatch.setenv("PUBLISH_QUEUE_TIMEOUT", "61")
    monkeypatch.setenv("PUBLISH_TOTAL_TIMEOUT", "121")

    legacy = CollectionApplicationSettings.from_env()

    assert legacy.connect_timeout_seconds == 9
    assert legacy.probe_timeout_seconds == 9
    assert legacy.plugin_timeout_seconds == 70
    assert legacy.publish_timeout_seconds == 31
    assert legacy.publish_queue_timeout_seconds == 61
    assert legacy.publish_total_timeout_seconds == 121

    monkeypatch.setenv("PREFLIGHT_TIMEOUT", "15")
    monkeypatch.setenv("PROBE_TIMEOUT", "16")
    monkeypatch.setenv("COLLECTION_TIMEOUT", "80")

    current = CollectionApplicationSettings.from_env()

    assert current.connect_timeout_seconds == 15
    assert current.probe_timeout_seconds == 16
    assert current.plugin_timeout_seconds == 80


def test_jetstream_publish_mode_defaults_to_four_publish_workers(monkeypatch):
    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.delenv("PUBLISH_WORKERS", raising=False)

    assert CollectionApplicationSettings.from_env().publish_worker_count == 4

    monkeypatch.setenv("PUBLISH_WORKERS", "8")
    assert CollectionApplicationSettings.from_env().publish_worker_count == 8

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    assert CollectionApplicationSettings.from_env().publish_worker_count == 1


def test_env_example_uses_split_timeout_contract():
    example = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    keys = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.lstrip().startswith("#")}

    assert "PREFLIGHT_TIMEOUT=15" in example
    assert "PROBE_TIMEOUT=15" in example
    assert "COLLECTION_TIMEOUT=60" in example
    assert "PUBLISH_QUEUE_TIMEOUT=60" in example
    assert "PUBLISH_DELIVERY_TIMEOUT=30" in example
    assert "PUBLISH_TOTAL_TIMEOUT=120" in example
    assert "NATS_METRICS_JETSTREAM_ENABLED=false" in example
    assert "PUBLISH_WORKERS=4" in example
    assert "NATS_JS_PUBLISH_MAX_PENDING=1024" in example
    assert "NATS_JS_PUBLISH_MAX_PENDING_BYTES=134217728" in example
    assert "NATS_JS_STREAM_NAME=CMDB_METRICS" in example
    assert "CAPACITY_LOG_INTERVAL=180" in example
    assert "MAX_ACTIVE_TARGETS=250" in example
    assert "NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS=50" in example
    assert "TARGET_TASK_WINDOW=250" in example
    assert "CONNECT_TIMEOUT" not in keys
    assert "PLUGIN_TIMEOUT" not in keys
    assert "PUBLISH_TIMEOUT" not in keys
    assert "PREFLIGHT_REACHABILITY" not in keys


def test_target_executor_settings_allow_zero_unlimited():
    settings = TargetExecutorSettings(max_active_targets=0, target_task_window=0)
    assert settings.max_active_targets == 0
    assert settings.target_task_window == 0


@pytest.mark.asyncio
async def test_worker_budget_zero_means_unlimited():
    budget = TargetWorkerBudget(0)
    reserved = await budget.reserve(12)
    assert reserved == 12
    assert budget.active == 12
    await budget.release(12)
    assert budget.active == 0
