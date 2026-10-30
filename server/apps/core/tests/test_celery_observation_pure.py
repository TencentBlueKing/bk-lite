"""公共观测不改变业务签名，不把正常 ETA 等待当排队积压。"""

from types import SimpleNamespace

import pytest

from apps.core.celery_runtime.observation import Observer, queue_wait

pytestmark = pytest.mark.unit


def test_eta_and_clock_skew_are_distinguished_from_old_messages():
    assert queue_wait({"bklite_published_at": 10, "eta": "1970-01-01T00:01:40+00:00"}, 103) == (3, "known")
    assert queue_wait({}, 103) == (None, "unknown")
    assert queue_wait({"bklite_published_at": 200}, 100) == (None, "clock_skew")
    assert queue_wait({"bklite_published_at": "not-a-time"}, 100) == (None, "unknown")
    assert queue_wait({"bklite_published_at": 10, "eta": "1970-01-01T00:01:40"}, 103) == (None, "unknown")


def test_retry_publish_overwrites_timestamp_without_touching_body(monkeypatch):
    observer = Observer(emit=lambda event: None)
    headers = {"bklite_published_at": 1, "retries": 2}
    monkeypatch.setattr("apps.core.celery_runtime.observation.time", lambda: 100)
    observer.published(sender="apps.future.task", headers=headers, body={"secret": "hidden"})
    assert headers == {"bklite_published_at": 100, "retries": 2}


def test_completion_aggregates_all_counts_with_bounded_labels_and_no_payload():
    events = []
    observer = Observer(emit=events.append)
    for index in range(3):
        task = SimpleNamespace(name=f"unknown.{index}", request=SimpleNamespace(headers={}, eta=None, delivery_info={}, retries=0))
        observer.started(task=task, args=["secret"])
        observer.finished(task=task, state="SUCCESS", retval="secret")
    observer.flush()
    assert sum(row["count"] for row in events[-1]["rows"] if row["phase"] == "finished") == 3
    assert all(row["task"] == "unknown" for row in events[-1]["rows"])
    assert "secret" not in str(events)


def test_observation_failure_does_not_escape_into_task_execution():
    def broken_emit(event):
        raise RuntimeError("logging unavailable")

    observer = Observer(emit=broken_emit)
    observer.published(sender="unknown", headers={})
    observer.flush()
    observer.started(task=SimpleNamespace())
    observer.finished(task=SimpleNamespace(), state="FAILURE")
