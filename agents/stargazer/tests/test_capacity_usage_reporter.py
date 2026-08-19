import asyncio
from types import SimpleNamespace

import pytest
from core.collection.application import CollectionApplication
from core.collection.capacity_observer import CapacityUsageReporter


@pytest.mark.asyncio
async def test_capacity_reporter_periodically_emits_150_target_slot_usage():
    emitted = []
    snapshot = {
        "active_runs": 12,
        "target_slots_used": 120,
        "target_slots_capacity": 150,
        "target_slots_peak": 145,
        "pending_targets": 380,
        "pending_runs": 8,
        "publish_queue_depth": 40,
        "publish_queue_capacity": 150,
    }
    reporter = CapacityUsageReporter(
        snapshot=lambda: dict(snapshot),
        emit=emitted.append,
        interval_seconds=0.01,
    )

    reporter.start()
    await asyncio.sleep(0.025)
    await reporter.stop()

    assert len(emitted) >= 2
    assert emitted[0] == {
        **snapshot,
        "target_slots_available": 30,
        "target_slots_utilization_percent": 80.0,
        "publish_queue_utilization_percent": 26.67,
    }


@pytest.mark.asyncio
async def test_capacity_reporter_stop_is_idempotent_before_start():
    reporter = CapacityUsageReporter(
        snapshot=dict, emit=lambda _snapshot: None, interval_seconds=30
    )
    await reporter.stop()


def test_application_capacity_snapshot_exposes_derived_values_for_health_metrics():
    application = SimpleNamespace(
        active_runs=3,
        runtime=SimpleNamespace(active_runs=3),
        _scheduler=SimpleNamespace(
            active=120, capacity=150, peak=145, pending=80, pending_runs=4
        ),
        settings=SimpleNamespace(max_active_targets=150, target_task_window=150),
        _target_activity=SimpleNamespace(active=110),
        _publisher=SimpleNamespace(queue_depth=45, capacity=150),
        _loop_lag=SimpleNamespace(latest_seconds=0.008, p99_seconds=0.035),
    )

    snapshot = CollectionApplication.capacity_snapshot(application)

    assert snapshot["target_slots_available"] == 30
    assert snapshot["target_slots_utilization_percent"] == 80.0
    assert snapshot["publish_queue_utilization_percent"] == 30.0
