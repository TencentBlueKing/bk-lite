from core.collection.metrics import CollectionMetrics


def test_collection_metrics_exposes_rolling_stage_percentiles():
    metrics = CollectionMetrics()
    for value in range(1, 101):
        metrics.observe("plugin_duration_seconds", value / 1000)

    snapshot = metrics.snapshot()

    assert snapshot["plugin_duration_seconds_p95"] == 0.095
    assert snapshot["plugin_duration_seconds_p99"] == 0.099


def test_collection_metrics_keeps_only_bounded_recent_samples():
    metrics = CollectionMetrics(sample_capacity=3)
    for value in (1.0, 2.0, 3.0, 4.0):
        metrics.observe("publish_duration_seconds", value)

    snapshot = metrics.snapshot()

    assert snapshot["publish_duration_seconds_p95"] == 3.0
    assert snapshot["publish_duration_seconds_p99"] == 3.0


def test_collection_metrics_tracks_non_negative_in_flight_gauges():
    metrics = CollectionMetrics()

    metrics.add_gauge("sync_calls_in_flight", 2)
    metrics.add_gauge("sync_calls_in_flight", -1)
    assert metrics.snapshot()["sync_calls_in_flight"] == 1

    metrics.add_gauge("sync_calls_in_flight", -10)
    assert metrics.snapshot()["sync_calls_in_flight"] == 0


def test_collection_metrics_expires_percentiles_by_time_window_when_idle():
    now = [100.0]
    metrics = CollectionMetrics(sample_capacity=10, sample_window_seconds=300, monotonic=lambda: now[0])
    metrics.observe("publish_queue_residence_seconds", 40.0)

    assert metrics.snapshot()["publish_queue_residence_seconds_p99"] == 40.0

    now[0] += 301

    assert metrics.snapshot()["publish_queue_residence_seconds_p99"] == 0.0
