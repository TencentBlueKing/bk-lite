from unittest.mock import Mock

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded

from apps.mlops.constants import TrainJobStatus
from apps.mlops.models.classification import ClassificationTrainJob
from apps.mlops.tasks.poll_train_job_status import poll_train_job_status
from apps.mlops.utils.webhook_client import WebhookError


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_poll_train_job_status_observation_failure_does_not_force_stop_running_job(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="running-job",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    stop_mock = Mock()

    def raise_mlflow_unavailable(_experiment_name):
        raise RuntimeError("mlflow temporarily unavailable")

    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        raise_mlflow_unavailable,
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "error", "message": "Container not found"}],
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.stop",
        stop_mock,
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=9,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container not running after observation failures"}
    assert train_job.status == TrainJobStatus.FAILED
    stop_mock.assert_not_called()


def test_poll_train_job_status_keeps_running_job_when_container_still_running(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="running-job-container-up",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    def raise_mlflow_unavailable(_experiment_name):
        raise RuntimeError("mlflow temporarily unavailable")

    retry_calls = []

    def fake_retry(*args, **kwargs):
        retry_calls.append({"args": args, "kwargs": kwargs})
        raise Retry()

    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        raise_mlflow_unavailable,
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "running"}],
    )
    monkeypatch.setattr(poll_train_job_status, "retry", fake_retry)

    with pytest.raises(Retry):
        poll_train_job_status.run(
            train_job.id,
            "Classification",
            expected_run_count=0,
            consecutive_errors=9,
        )

    train_job.refresh_from_db()

    assert train_job.status == TrainJobStatus.RUNNING
    assert len(retry_calls) == 1
    assert retry_calls[0]["kwargs"]["countdown"] == 300
    assert retry_calls[0]["kwargs"]["kwargs"]["consecutive_errors"] == 10


def test_poll_train_job_status_marks_failed_when_container_missing_after_observation_failures(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="running-job-container-missing",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    def raise_mlflow_unavailable(_experiment_name):
        raise RuntimeError("mlflow temporarily unavailable")

    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        raise_mlflow_unavailable,
    )
    stop_mock = Mock()
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "error", "message": "Container not found"}],
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.stop",
        stop_mock,
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=9,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container not running after observation failures"}
    assert train_job.status == TrainJobStatus.FAILED
    stop_mock.assert_not_called()


def test_poll_train_job_status_keeps_running_job_when_max_retries_exceeded_but_container_running(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="running-job-max-retries",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    class FakeMaxRetriesExceededError(Exception):
        pass

    apply_async_mock = Mock()

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(poll_train_job_status, "apply_async", apply_async_mock)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(FakeMaxRetriesExceededError()),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "running"}],
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=10,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container still running after max retries; rescheduled polling"}
    assert train_job.status == TrainJobStatus.RUNNING
    apply_async_mock.assert_called_once()
    assert apply_async_mock.call_args.kwargs["countdown"] == 300


def test_poll_train_job_status_marks_failed_when_max_retries_exceeded_and_container_missing(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="failed-job-max-retries",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    stop_mock = Mock()

    class FakeMaxRetriesExceededError(Exception):
        pass

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(FakeMaxRetriesExceededError()),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "error", "message": "Container not found"}],
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.stop",
        stop_mock,
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=10,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container not running after observation failures"}
    assert train_job.status == TrainJobStatus.FAILED
    stop_mock.assert_not_called()


def test_poll_train_job_status_reschedules_when_webhook_status_check_fails_after_max_retries(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="webhook-error-job-max-retries",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    class FakeMaxRetriesExceededError(Exception):
        pass

    apply_async_mock = Mock()

    def unexpected_retry(*args, **kwargs):
        raise AssertionError("retry should not be called after max retries")

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(poll_train_job_status, "apply_async", apply_async_mock)
    monkeypatch.setattr(poll_train_job_status, "retry", unexpected_retry)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(FakeMaxRetriesExceededError()),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: (_ for _ in ()).throw(WebhookError("webhook unavailable")),
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=10,
    )

    train_job.refresh_from_db()

    assert result == {
        "result": False,
        "reason": "container status check failed after max retries; rescheduled polling",
    }
    assert train_job.status == TrainJobStatus.RUNNING
    apply_async_mock.assert_called_once()
    assert apply_async_mock.call_args.kwargs["countdown"] == 300


def test_poll_train_job_status_reschedules_when_container_state_is_unclear_after_max_retries(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="unclear-container-job-max-retries",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    class FakeMaxRetriesExceededError(Exception):
        pass

    apply_async_mock = Mock()

    def unexpected_retry(*args, **kwargs):
        raise AssertionError("retry should not be called after max retries")

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(poll_train_job_status, "apply_async", apply_async_mock)
    monkeypatch.setattr(poll_train_job_status, "retry", unexpected_retry)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(FakeMaxRetriesExceededError()),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "pending", "detail": "waiting"}],
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=10,
    )

    train_job.refresh_from_db()

    assert result == {
        "result": False,
        "reason": "container state unclear after max retries; rescheduled polling",
    }
    assert train_job.status == TrainJobStatus.RUNNING
    apply_async_mock.assert_called_once()
    assert apply_async_mock.call_args.kwargs["countdown"] == 300


def test_poll_train_job_status_reschedules_when_soft_time_limit_hits_on_final_retry(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="soft-time-limit-final-retry",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    class FakeMaxRetriesExceededError(Exception):
        pass

    retry_call_count = {"count": 0}
    apply_async_mock = Mock()

    def fake_retry(*args, **kwargs):
        retry_call_count["count"] += 1
        raise FakeMaxRetriesExceededError()

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(poll_train_job_status, "retry", fake_retry)
    monkeypatch.setattr(poll_train_job_status, "apply_async", apply_async_mock)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(SoftTimeLimitExceeded()),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "running"}],
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=9,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container still running after max retries; rescheduled polling"}
    assert train_job.status == TrainJobStatus.RUNNING
    assert retry_call_count["count"] == 1
    apply_async_mock.assert_called_once()
    assert apply_async_mock.call_args.kwargs["countdown"] == 300


def test_poll_train_job_status_reschedules_when_generic_exception_hits_on_final_retry(monkeypatch):
    train_job = ClassificationTrainJob.objects.create(
        name="generic-error-final-retry",
        description="",
        team=[1],
        status=TrainJobStatus.RUNNING,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )

    class FakeMaxRetriesExceededError(Exception):
        pass

    retry_call_count = {"count": 0}
    apply_async_mock = Mock()

    def fake_retry(*args, **kwargs):
        retry_call_count["count"] += 1
        raise FakeMaxRetriesExceededError()

    monkeypatch.setattr(poll_train_job_status, "MaxRetriesExceededError", FakeMaxRetriesExceededError)
    monkeypatch.setattr(poll_train_job_status, "retry", fake_retry)
    monkeypatch.setattr(poll_train_job_status, "apply_async", apply_async_mock)
    monkeypatch.setattr(
        "apps.mlops.utils.mlflow_service.get_experiment_by_name",
        lambda _experiment_name: (_ for _ in ()).throw(RuntimeError("mlflow unavailable at final retry")),
    )
    monkeypatch.setattr(
        "apps.mlops.utils.webhook_client.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "running"}],
    )

    result = poll_train_job_status.run(
        train_job.id,
        "Classification",
        expected_run_count=0,
        consecutive_errors=9,
    )

    train_job.refresh_from_db()

    assert result == {"result": False, "reason": "container still running after max retries; rescheduled polling"}
    assert train_job.status == TrainJobStatus.RUNNING
    assert retry_call_count["count"] == 1
    apply_async_mock.assert_called_once()
    assert apply_async_mock.call_args.kwargs["countdown"] == 300
