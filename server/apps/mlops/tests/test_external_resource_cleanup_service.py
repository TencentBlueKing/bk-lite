import importlib
import importlib.util
from datetime import timedelta
from unittest.mock import Mock, call

import pydantic.root_model  # noqa
import pytest
from django.apps import apps
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _intent_model():
    model = next(
        (candidate for candidate in apps.get_app_config("mlops").get_models() if candidate.__name__ == "ExternalResourceCleanupIntent"),
        None,
    )
    assert model is not None, "缺少持久外部资源清理意图模型"
    return model


def _cleanup_service():
    module_name = "apps.mlops.services.external_resource_cleanup"
    assert importlib.util.find_spec(module_name) is not None, "缺少持久清理服务"
    return importlib.import_module(module_name)


def _cleanup_tasks():
    module_name = "apps.mlops.tasks.external_resource_cleanup"
    assert importlib.util.find_spec(module_name) is not None, "缺少持久清理任务"
    return importlib.import_module(module_name)


def test_cleanup_intent_has_durable_retry_contract():
    intent_model = _intent_model()

    intent = intent_model.objects.create(
        idempotency_key="mlflow:AnomalyDetection_algo_4249",
        resource_type="mlflow_experiment_model",
        payload={"experiment_name": "exp", "model_name": "model"},
    )

    assert intent.status == "pending"
    assert intent.attempts == 0
    assert intent.next_retry_at is None
    assert intent.claim_token == ""
    assert intent.last_error == ""


def test_create_mlflow_cleanup_intent_is_idempotent():
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()

    first = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    second = cleanup_service.create_mlflow_cleanup_intent("exp", "model")

    assert first.pk == second.pk
    assert intent_model.objects.count() == 1
    assert first.payload == {"experiment_name": "exp", "model_name": "model"}


def test_process_cleanup_failure_records_backoff_and_releases_claim(monkeypatch):
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    claim = cleanup_service.claim_cleanup_intent(intent.pk)
    assert claim is not None
    monkeypatch.setattr(
        cleanup_service.mlflow_service,
        "delete_experiment_and_model",
        Mock(side_effect=RuntimeError("temporary outage")),
    )

    with pytest.raises(RuntimeError, match="temporary outage"):
        cleanup_service.process_cleanup_intent(intent.pk, claim)

    intent.refresh_from_db()
    assert intent.status == intent_model.Status.PENDING
    assert intent.attempts == 1
    assert intent.next_retry_at > timezone.now()
    assert intent.claim_token == ""
    assert intent.claim_expires_at is None
    assert intent.last_error == "RuntimeError"


def test_tenth_cleanup_failure_stays_durable_and_stops_automatic_retries(monkeypatch):
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    intent_model.objects.filter(pk=intent.pk).update(attempts=9)
    claim = cleanup_service.claim_cleanup_intent(intent.pk)
    monkeypatch.setattr(
        cleanup_service.mlflow_service,
        "delete_experiment_and_model",
        Mock(side_effect=RuntimeError("persistent outage")),
    )

    with pytest.raises(RuntimeError, match="persistent outage"):
        cleanup_service.process_cleanup_intent(intent.pk, claim)

    intent.refresh_from_db()
    assert intent.status == intent_model.Status.FAILED
    assert intent.attempts == 10
    assert intent.next_retry_at is None
    assert cleanup_service.claim_due_cleanup_intents() == []


def test_process_cleanup_is_fenced_and_idempotent(monkeypatch):
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    claim = cleanup_service.claim_cleanup_intent(intent.pk)
    delete = Mock()
    monkeypatch.setattr(cleanup_service.mlflow_service, "delete_experiment_and_model", delete)

    result = cleanup_service.process_cleanup_intent(intent.pk, claim)
    stale_result = cleanup_service.process_cleanup_intent(intent.pk, claim)

    assert result == {"result": True, "state": "completed"}
    assert stale_result == {"result": False, "reason": "stale cleanup claim"}
    delete.assert_called_once_with(experiment_name="exp", model_name="model")
    intent.refresh_from_db()
    assert intent.status == intent_model.Status.COMPLETED
    assert intent.completed_at is not None


def test_claim_due_cleanup_intents_recovers_expired_worker_claim():
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    intent_model.objects.filter(pk=intent.pk).update(
        status=intent_model.Status.PROCESSING,
        claim_token="lost-worker",
        claim_expires_at=timezone.now() - timedelta(seconds=1),
    )

    claims = cleanup_service.claim_due_cleanup_intents(limit=1)

    assert len(claims) == 1
    assert claims[0][0] == intent.pk
    assert claims[0][1] != "lost-worker"


def test_expired_claim_cannot_execute_before_reclaim(monkeypatch):
    cleanup_service = _cleanup_service()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    claim = cleanup_service.claim_cleanup_intent(intent.pk)
    intent_model.objects.filter(pk=intent.pk).update(
        claim_expires_at=timezone.now() - timedelta(seconds=1),
    )
    delete = Mock()
    monkeypatch.setattr(cleanup_service.mlflow_service, "delete_experiment_and_model", delete)

    result = cleanup_service.process_cleanup_intent(intent.pk, claim)

    assert result == {"result": False, "reason": "stale cleanup claim"}
    delete.assert_not_called()
    intent.refresh_from_db()
    assert intent.status == intent_model.Status.PROCESSING


def test_initial_broker_failure_releases_claim_for_periodic_recovery(monkeypatch):
    cleanup_service = _cleanup_service()
    cleanup_tasks = _cleanup_tasks()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    monkeypatch.setattr(
        cleanup_tasks.cleanup_external_resource,
        "apply_async",
        Mock(side_effect=ConnectionError("broker down")),
    )

    scheduled = cleanup_tasks.enqueue_external_resource_cleanup_intent(intent.pk)

    assert scheduled is False
    intent.refresh_from_db()
    assert intent.status == intent_model.Status.PENDING
    assert intent.claim_token == ""
    assert intent.claim_expires_at is None
    assert intent.next_retry_at <= timezone.now()


def test_celery_disabled_processes_cleanup_synchronously(settings, monkeypatch):
    cleanup_service = _cleanup_service()
    cleanup_tasks = _cleanup_tasks()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    settings.IS_USE_CELERY = False
    delete = Mock()
    apply_async = Mock()
    monkeypatch.setattr(cleanup_service.mlflow_service, "delete_experiment_and_model", delete)
    monkeypatch.setattr(cleanup_tasks.cleanup_external_resource, "apply_async", apply_async)

    scheduled = cleanup_tasks.enqueue_external_resource_cleanup_intent(intent.pk)

    assert scheduled is True
    apply_async.assert_not_called()
    delete.assert_called_once_with(experiment_name="exp", model_name="model")
    intent.refresh_from_db()
    assert intent.status == intent_model.Status.COMPLETED


def test_celery_disabled_failure_is_swallowed_with_pending_intent(settings, monkeypatch):
    cleanup_service = _cleanup_service()
    cleanup_tasks = _cleanup_tasks()
    intent_model = _intent_model()
    intent = cleanup_service.create_mlflow_cleanup_intent("exp", "model")
    settings.IS_USE_CELERY = False
    monkeypatch.setattr(
        cleanup_service.mlflow_service,
        "delete_experiment_and_model",
        Mock(side_effect=RuntimeError("mlflow down")),
    )

    scheduled = cleanup_tasks.enqueue_external_resource_cleanup_intent(intent.pk)

    assert scheduled is False
    intent.refresh_from_db()
    assert intent.status == intent_model.Status.PENDING
    assert intent.attempts == 1
    assert intent.next_retry_at > timezone.now()


def test_periodic_dispatch_is_bounded_and_publishes_claim_tokens(monkeypatch):
    cleanup_service = _cleanup_service()
    cleanup_tasks = _cleanup_tasks()
    intent_model = _intent_model()
    for index in range(101):
        cleanup_service.create_mlflow_cleanup_intent(f"exp-{index}", f"model-{index}")
    apply_async = Mock()
    monkeypatch.setattr(cleanup_tasks.cleanup_external_resource, "apply_async", apply_async)

    result = cleanup_tasks.dispatch_pending_external_resource_cleanup()

    assert result == {"claimed": 100, "scheduled": 100}
    assert apply_async.call_count == 100
    assert all(call.kwargs["delivery_mode"] == 2 for call in apply_async.call_args_list)
    assert all(call.kwargs["retry"] is False for call in apply_async.call_args_list)
    assert intent_model.objects.filter(status=intent_model.Status.PENDING).count() == 1


def test_periodic_dispatch_scans_each_configured_database_alias(monkeypatch):
    cleanup_tasks = _cleanup_tasks()
    claim_due = Mock(side_effect=lambda limit, using="default": [(1, f"{using}-token")])
    publish = Mock(return_value=True)
    monkeypatch.setattr(
        cleanup_tasks,
        "connections",
        ["default", "archive"],
        raising=False,
    )
    monkeypatch.setattr(cleanup_tasks, "claim_due_cleanup_intents", claim_due)
    monkeypatch.setattr(cleanup_tasks, "_publish_cleanup_claim", publish)

    result = cleanup_tasks.dispatch_pending_external_resource_cleanup()

    assert result == {"claimed": 2, "scheduled": 2}
    assert claim_due.call_args_list == [
        call(limit=50, using="default"),
        call(limit=99, using="archive"),
    ]
    assert publish.call_args_list == [
        call(1, "default-token", using="default"),
        call(1, "archive-token", using="archive"),
    ]


def test_periodic_dispatch_shares_global_budget_fairly_between_aliases(monkeypatch):
    cleanup_tasks = _cleanup_tasks()
    claim_due = Mock(side_effect=lambda limit, using="default": [(index, f"{using}-{index}") for index in range(limit)])
    monkeypatch.setattr(cleanup_tasks, "connections", ["default", "archive"])
    monkeypatch.setattr(cleanup_tasks, "claim_due_cleanup_intents", claim_due)
    monkeypatch.setattr(cleanup_tasks, "_publish_cleanup_claim", Mock(return_value=True))

    result = cleanup_tasks.dispatch_pending_external_resource_cleanup()

    assert result == {"claimed": 100, "scheduled": 100}
    assert claim_due.call_args_list == [
        call(limit=50, using="default"),
        call(limit=50, using="archive"),
    ]
