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
    reporter = CapacityUsageReporter(snapshot=dict, emit=lambda _snapshot: None, interval_seconds=30)
    await reporter.stop()


def test_application_capacity_snapshot_exposes_derived_values_for_health_metrics():
    application = SimpleNamespace(
        active_runs=3,
        runtime=SimpleNamespace(active_runs=3),
        _scheduler=SimpleNamespace(
            active=120,
            topology_active=45,
            capacity=150,
            peak=145,
            pending=80,
            pending_runs=4,
            completed=600,
            completed_total=1800,
        ),
        settings=SimpleNamespace(
            max_active_targets=150,
            network_topology_max_active_targets=50,
            target_task_window=150,
        ),
        _target_activity=SimpleNamespace(active=110),
        _publisher=SimpleNamespace(queue_depth=45, capacity=150, current_batch_age_seconds=1.25),
        _metrics=SimpleNamespace(snapshot=lambda: {"publish_queue_residence_seconds_p99": 2.5}),
        _loop_lag=SimpleNamespace(latest_seconds=0.008, p99_seconds=0.035),
        _resource_sampler=SimpleNamespace(
            sample=lambda: {
                "process_cpu_percent": 62.5,
                "process_rss_mb": 384.0,
                "cgroup_memory_utilization_percent": 37.5,
            }
        ),
    )

    snapshot = CollectionApplication.capacity_snapshot(application)

    assert snapshot["target_slots_available"] == 30
    assert snapshot["target_slots_utilization_percent"] == 80.0
    assert snapshot["publish_queue_utilization_percent"] == 30.0
    assert snapshot["publish_batch_age_ms"] == 1250.0
    assert snapshot["publish_queue_residence_p99_ms"] == 2500.0
    assert snapshot["completed_targets"] == 600
    assert snapshot["completed_targets_total"] == 1800
    assert snapshot["configured_network_topology_max_active_targets"] == 50
    assert snapshot["network_topology_active_targets"] == 45
    assert snapshot["process_cpu_percent"] == 62.5
    assert snapshot["process_rss_mb"] == 384.0
    assert snapshot["cgroup_memory_utilization_percent"] == 37.5


def test_capacity_log_includes_process_and_cgroup_resources(monkeypatch):
    messages = []
    fake_logger = SimpleNamespace(info=lambda message, *args: messages.append(message % args))
    monkeypatch.setattr("core.collection.application.logger", fake_logger)

    CollectionApplication._emit_capacity_log(
        {
            "active_runs": 3,
            "pending_runs": 2,
            "target_slots_used": 120,
            "target_slots_capacity": 150,
            "target_slots_available": 30,
            "target_slots_utilization_percent": 80.0,
            "target_slots_peak": 145,
            "active_targets": 110,
            "pending_targets": 80,
            "completed_targets": 600,
            "completed_targets_total": 1800,
            "configured_max_active_targets": 150,
            "configured_target_task_window": 150,
            "publish_queue_depth": 45,
            "publish_queue_capacity": 150,
            "publish_queue_utilization_percent": 30.0,
            "publish_batch_age_ms": 1250.0,
            "publish_queue_residence_p99_ms": 2500.0,
            "event_loop_lag_ms": 8.0,
            "event_loop_lag_p99_ms": 35.0,
            "process_cpu_percent": 62.5,
            "process_cpu_quota_utilization_percent": 31.25,
            "process_rss_mb": 384.0,
            "process_threads": 9,
            "process_open_fds": 128,
            "cgroup_memory_current_mb": 512.0,
            "cgroup_memory_limit_mb": 1024.0,
            "cgroup_memory_utilization_percent": 50.0,
            "cgroup_cpu_limit_cores": 2.0,
            "cgroup_cpu_throttled_seconds_total": 8.5,
            "cgroup_cpu_throttled_seconds_delta": 1.25,
            "cgroup_cpu_throttled_periods_total": 40,
            "cgroup_cpu_throttled_periods_delta": 5,
        }
    )

    assert "event=collection_capacity" in messages[0]
    assert "状态=需关注" in messages[0]
    assert "提示=CPU发生限流" in messages[0]
    assert "采集任务[正在执行=3 调度中=2]" in messages[0]
    assert "目标任务[等待执行=80 正在执行=120 本轮已完成=600 累计已完成=1800]" in messages[0]
    assert "目标并发槽位[已用=120/150 可用=30 使用率=80.0% 峰值=145]" in messages[0]
    assert "发布队列[深度=45/150 使用率=30.0%" in messages[0]
    assert "事件循环[当前延迟=8.0ms P99延迟=35.0ms]" in messages[0]
    assert "进程[CPU=62.5% CPU配额使用率=31.25% RSS内存=384.0MiB 线程=9 FD=128]" in messages[0]
    assert "容器[内存=512.0MiB/1024.0MiB 使用率=50.0% CPU限额=2.0核" in messages[0]
    assert "CPU限流增量=1.25秒/5次" in messages[0]


def test_capacity_log_displays_unavailable_values_in_chinese(monkeypatch):
    messages = []
    fake_logger = SimpleNamespace(info=lambda message, *args: messages.append(message % args))
    monkeypatch.setattr("core.collection.application.logger", fake_logger)

    CollectionApplication._emit_capacity_log({})

    assert "状态=空闲" in messages[0]
    assert "进程[CPU=不可用" in messages[0]
    assert "容器[内存=不可用/不可用" in messages[0]
