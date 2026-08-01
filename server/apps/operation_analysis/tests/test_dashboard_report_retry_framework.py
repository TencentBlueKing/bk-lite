import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_orchestrator import (
    _testing_run_classifier_loop_with_results,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.retry_classifier import RetryClassifier
from apps.operation_analysis.services.retry_types import (
    AttemptResult,
    ClassifierDecisionKind,
    ResourceState,
    ResumeClass,
)
from apps.operation_analysis.tasks.tasks import render_dashboard_report_task
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


def _resource(**overrides):
    base = dict(
        input_snapshot="valid",
        render_snapshot="valid",
        artifact="valid",
        delivery_outcome="not_delivered",
    )
    base.update(overrides)
    return ResourceState(**base)


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="Retry 框架通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def running_execution(authenticated_user, email_channel):
    directory = Directory.objects.create(name="Retry 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="Retry 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="Retry 订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={},
    )
    # Classifier 对 smtp_transient 要求 render_snapshot=valid 才可 retry
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        dashboard_name=dashboard.name,
        dashboard_updated_at=dashboard.updated_at,
        view_sets=[],
        filters=[],
        other={},
        widget_manifest=[],
    )
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    return execution


class TestTransitionCas:
    def test_running_to_succeeded_is_conditional(
        self, running_execution
    ):
        other = DashboardReportExecution.objects.get(pk=running_execution.pk)
        DashboardReportExecutionService.transition(
            running_execution,
            DashboardReportExecution.Status.SUCCEEDED,
        )
        DashboardReportExecutionService.transition(
            other,
            DashboardReportExecution.Status.FAILED,
            failure_stage="email",
            error_code="smtp_transient",
            error_message="should not overwrite",
        )
        running_execution.refresh_from_db()
        assert (
            running_execution.status
            == DashboardReportExecution.Status.SUCCEEDED
        )
        assert running_execution.failure_stage == ""
        assert running_execution.error_code == ""

    def test_terminal_rejects_further_transition(
        self, running_execution
    ):
        DashboardReportExecutionService.transition(
            running_execution,
            DashboardReportExecution.Status.FAILED,
            failure_stage="render",
            error_code="pdf_too_large",
            error_message="过大",
        )
        with pytest.raises(Exception):
            DashboardReportExecutionService.transition(
                running_execution,
                DashboardReportExecution.Status.SUCCEEDED,
            )


class TestRetryClassifier:
    def test_delivery_transient_with_valid_artifact_retries_delivery(self):
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="temp",
                side_effect="should_be_ignored",
            ),
            attempt_count=1,
            resource=_resource(artifact="valid"),
        )
        assert decision.kind == ClassifierDecisionKind.RETRY
        assert decision.resume_class == ResumeClass.DELIVERY

    def test_side_effect_does_not_affect_decision(self):
        a = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="x",
                side_effect="delivered",
            ),
            1,
            _resource(artifact="valid"),
        )
        b = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="x",
                side_effect="",
            ),
            1,
            _resource(artifact="valid"),
        )
        assert a == b

    def test_attempt_count_exhausted_is_terminal(self):
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="x",
            ),
            attempt_count=3,
            resource=_resource(artifact="valid"),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED

    def test_delivered_forces_succeeded(self):
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="x",
            ),
            1,
            _resource(delivery_outcome="delivered"),
        )
        assert decision.kind == ClassifierDecisionKind.SUCCEEDED

    def test_permission_is_terminal(self):
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="permission_check",
                error_code="dashboard_view_denied",
                error_message="denied",
            ),
            1,
            _resource(),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED


class TestAttemptLoopFramework:
    def test_loop_retries_then_succeeds_without_writing_mid_failure(
        self, running_execution
    ):
        results = [
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="temp-1",
            ),
            AttemptResult(ok=True),
        ]
        _testing_run_classifier_loop_with_results(
            running_execution, results
        )
        running_execution.refresh_from_db()
        assert (
            running_execution.status
            == DashboardReportExecution.Status.SUCCEEDED
        )
        assert running_execution.attempt_count == 2
        # 中间失败不得覆盖最终错误字段；成功终态保持空
        assert running_execution.failure_stage == ""
        assert running_execution.error_code == ""

    def test_loop_writes_terminal_fields_only_on_final_failure(
        self, running_execution
    ):
        results = [
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="temp-1",
            ),
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="temp-2",
            ),
            AttemptResult(
                ok=False,
                failure_stage="email",
                error_code="smtp_transient",
                error_message="temp-3",
            ),
        ]
        _testing_run_classifier_loop_with_results(
            running_execution, results
        )
        running_execution.refresh_from_db()
        assert (
            running_execution.status
            == DashboardReportExecution.Status.FAILED
        )
        assert running_execution.attempt_count == 3
        assert running_execution.failure_stage == "email"
        assert running_execution.error_code == "smtp_transient"
        assert running_execution.error_message == "temp-3"


class TestNoReclaimAfterRunning:
    def test_claim_fails_when_already_running(self, running_execution):
        assert (
            DashboardReportExecutionService.claim_execution(
                running_execution.id
            )
            is False
        )
        running_execution.refresh_from_db()
        assert (
            running_execution.status
            == DashboardReportExecution.Status.RUNNING
        )

    def test_render_task_does_not_reclaim_running(
        self, running_execution, monkeypatch
    ):
        called = []

        def boom(execution_id):
            called.append(execution_id)
            raise AssertionError("不得再次进入 Orchestrator")

        monkeypatch.setattr(
            "apps.operation_analysis.tasks.tasks.ExecutionOrchestrator.execute",
            boom,
        )
        result = render_dashboard_report_task(running_execution.id)
        assert result == {
            "claimed": False,
            "execution_id": running_execution.id,
        }
        assert called == []


class TestScheduledRetryDoesNotTouchNextRun:
    def test_failed_execution_keeps_advanced_next_run(
        self, authenticated_user, email_channel, monkeypatch
    ):
        from datetime import timedelta

        directory = Directory.objects.create(name="调度 Retry 目录", groups=[1])
        dashboard = Dashboard.objects.create(
            name="调度 Retry 仪表盘",
            directory=directory,
            groups=[1],
        )
        due_at = timezone.now() - timedelta(minutes=1)
        subscription = DashboardReportSubscription.objects.create(
            dashboard=dashboard,
            creator=authenticated_user.username,
            name="调度 Retry",
            recipient_email="ops@example.com",
            email_channel=email_channel,
            schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
            schedule_hour=9,
            schedule_minute=0,
            timezone="Asia/Shanghai",
            next_run_at=due_at,
            version=1,
        )
        monkeypatch.setattr(
            DashboardReportExecutionService,
            "_dispatch_render",
            staticmethod(lambda execution_id: None),
        )
        created = DashboardReportExecutionService.create_scheduled(
            subscription.id,
            now=timezone.now(),
        )
        assert created.created is True
        subscription.refresh_from_db()
        advanced = subscription.next_run_at
        assert advanced > due_at

        execution = created.execution
        assert DashboardReportExecutionService.claim_execution(execution.id)
        execution.refresh_from_db()
        _testing_run_classifier_loop_with_results(
            execution,
            [
                AttemptResult(
                    ok=False,
                    failure_stage="permission_check",
                    error_code="dashboard_view_denied",
                    error_message="denied",
                )
            ],
        )
        subscription.refresh_from_db()
        assert subscription.next_run_at == advanced
