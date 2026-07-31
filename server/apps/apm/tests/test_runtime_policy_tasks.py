import pytest
from django.utils import timezone

from apps.apm.config import CELERY_BEAT_SCHEDULE
from apps.apm.models import ApmPolicy, ApmService
from apps.apm.services.contracts import PublishResult
from apps.apm.tasks import (
    deliver_apm_alert_outbox,
    dispatch_apm_policy_evaluations,
    evaluate_apm_policy,
)


pytestmark = pytest.mark.django_db


def _policy(enabled=True):
    now = timezone.now()
    sequence = ApmService.objects.count()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=f"checkout-{sequence}",
        normalized_name=f"checkout-{sequence}",
        first_seen_at=now,
        last_seen_at=now,
    )
    return ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="prod",
        metric_type="error_rate",
        comparator="gt",
        threshold="0.1",
        duration_window=1,
        recovery_window=1,
        severity="error",
        is_enabled=enabled,
    )


def test_policy_runtime_tasks_are_beat_driven_and_not_in_batch_init():
    assert CELERY_BEAT_SCHEDULE["apm_dispatch_policy_evaluations"]["task"] == (
        "apps.apm.tasks.dispatch_apm_policy_evaluations"
    )
    assert CELERY_BEAT_SCHEDULE["apm_deliver_alert_outbox"]["task"] == (
        "apps.apm.tasks.deliver_apm_alert_outbox"
    )
    assert evaluate_apm_policy.retry_kwargs["max_retries"] == 5
    with open("apps/core/management/commands/batch_init.py", encoding="utf-8") as file:
        batch_init = file.read()
    assert "dispatch_apm_policy_evaluations" not in batch_init
    assert "apps.alerts" not in batch_init


def test_dispatch_only_schedules_enabled_policies(mocker):
    enabled = _policy(enabled=True)
    _policy(enabled=False)
    delay = mocker.patch("apps.apm.tasks.evaluate_apm_policy.delay")

    result = dispatch_apm_policy_evaluations.run()

    assert result["dispatched"] == 1
    delay.assert_called_once_with(str(enabled.id), result["evaluated_at"])


def test_outbox_task_reports_deferred_failures_without_unbounded_task_retry(mocker):
    retry = mocker.patch(
        "apps.apm.tasks.DjangoApmPolicyService.retry_pending_events",
        return_value=PublishResult(accepted=0, failed=1),
    )

    result = deliver_apm_alert_outbox.run()

    assert result == {"accepted": 0, "duplicates": 0, "failed": 1}
    retry.assert_called_once_with(limit=100)
