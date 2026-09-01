"""指标标签基数契约测试。"""

from tasks.utils.metrics_helper import generate_host_remote_state_metric


def test_host_remote_state_uses_only_bounded_labels():
    metric = generate_host_remote_state_metric(
        event="processing_failed",
        task_id="remote-result-attempt-a",
        status="delivery_failed",
        monitor_type="host",
        extra_labels={
            "reason": "processing_error",
            "task_id": "remote-result-attempt-a",
            "collection_result_id": "result-attempt-a",
        },
    )

    assert 'monitor_type="host"' in metric
    assert 'event="processing_failed"' in metric
    assert 'status="delivery_failed"' in metric
    assert 'reason="processing_error"' in metric
    assert "task_id=" not in metric
    assert "collection_result_id=" not in metric
