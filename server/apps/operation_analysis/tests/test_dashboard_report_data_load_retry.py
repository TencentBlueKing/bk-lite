import pytest

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderContractError,
    resolve_report_failed_semantics,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
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
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


def _resource(**overrides):
    base = dict(
        input_snapshot="valid",
        render_snapshot="valid",
        artifact="absent",
        delivery_outcome="not_delivered",
    )
    base.update(overrides)
    return ResourceState(**base)


@pytest.fixture
def running_execution(authenticated_user):
    directory = Directory.objects.create(name="data_load 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="data_load 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    channel = Channel.objects.create(
        name="data_load 通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="data_load 订阅",
        recipient_email="ops@example.com",
        email_channel=channel,
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
        email_channel_id=channel.id,
        filter_values={},
    )
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


class TestReportFailedSemantics:
    def test_maps_widget_query_timeout_to_data_load(self):
        assert resolve_report_failed_semantics(
            {"errorCode": "widget_query_timeout", "widgetId": "w1"}
        ) == ("data_load", "widget_query_timeout")

    def test_unknown_error_code_stays_render_contract(self):
        assert resolve_report_failed_semantics(
            {"errorCode": "something_else"}
        ) == ("render", "render_contract_business_failed")

    def test_missing_error_code_stays_render_contract(self):
        assert resolve_report_failed_semantics(
            {"type": "report-failed", "widgetId": "w1"}
        ) == ("render", "render_contract_business_failed")

    def test_frontend_timeout_signal_to_classifier_retry(self):
        """A1 生产链：前端 classify → report-failed.errorCode → resolve → retry。

        信号形状对齐 web buildDashboardRenderSignal + classifyWidgetQueryError
        (ECONNABORTED → widget_query_timeout)。
        """
        signal = {
            "type": "report-failed",
            "dashboardId": "8",
            "widgets": [
                {
                    "widgetId": "chart-1",
                    "status": "failed",
                    "error": "timeout of 30000ms exceeded",
                    "errorCode": "widget_query_timeout",
                }
            ],
            "widgetId": "chart-1",
            "error": "timeout of 30000ms exceeded",
            "errorCode": "widget_query_timeout",
        }
        stage, code = resolve_report_failed_semantics(signal)
        assert (stage, code) == ("data_load", "widget_query_timeout")

        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage=stage,
                error_code=code,
                error_message=signal["error"],
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.RETRY
        assert decision.resume_class == ResumeClass.RENDER

    def test_frontend_forbidden_signal_stays_terminal(self):
        stage, code = resolve_report_failed_semantics(
            {
                "type": "report-failed",
                "errorCode": "widget_data_forbidden",
                "widgetId": "chart-1",
            }
        )
        assert (stage, code) == ("data_load", "widget_data_forbidden")
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage=stage,
                error_code=code,
                error_message="noAuth",
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED

    def test_plain_render_contract_signal_stays_terminal(self):
        stage, code = resolve_report_failed_semantics(
            {
                "type": "report-failed",
                "widgetId": "chart-1",
                "error": "dataCannotRenderAsChart",
            }
        )
        assert (stage, code) == ("render", "render_contract_business_failed")
        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage=stage,
                error_code=code,
                error_message="dataCannotRenderAsChart",
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED


class TestDataLoadRetryPath:
    def test_widget_query_timeout_retries_then_render_succeeds(
        self, running_execution, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )
        render_calls = []

        def flaky_render(cls, execution, snapshot, render_snapshot):
            render_calls.append(execution.attempt_count)
            if len(render_calls) == 1:
                raise DashboardRenderContractError(
                    widget_id="chart-1",
                    error_code="widget_query_timeout",
                    failure_stage="data_load",
                )
            return object()

        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DashboardReportRenderService.render",
            classmethod(flaky_render),
        )
        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DeliveryStep.execute",
            lambda *args, **kwargs: AttemptResult(
                ok=True, side_effect="delivered"
            ),
        )

        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="data_load",
                error_code="widget_query_timeout",
                error_message="timeout",
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.RETRY
        assert decision.resume_class == ResumeClass.RENDER

        result = ExecutionOrchestrator.execute(running_execution.id)
        running_execution.refresh_from_db()
        assert result.status == DashboardReportExecution.Status.SUCCEEDED
        assert running_execution.attempt_count == 2
        assert render_calls == [1, 2]
        assert running_execution.failure_stage == ""
        assert running_execution.error_code == ""

    def test_widget_data_forbidden_is_terminal(
        self, running_execution, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )
        render_calls = []

        def forbid_render(cls, execution, snapshot, render_snapshot):
            render_calls.append("render")
            raise DashboardRenderContractError(
                widget_id="chart-1",
                error_code="widget_data_forbidden",
                failure_stage="data_load",
            )

        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DashboardReportRenderService.render",
            classmethod(forbid_render),
        )
        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DeliveryStep.execute",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("不得 Delivery")
            ),
        )

        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="data_load",
                error_code="widget_data_forbidden",
                error_message="forbidden",
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED

        result = ExecutionOrchestrator.execute(running_execution.id)
        running_execution.refresh_from_db()
        assert result.status == DashboardReportExecution.Status.FAILED
        assert running_execution.attempt_count == 1
        assert running_execution.failure_stage == "data_load"
        assert running_execution.error_code == "widget_data_forbidden"
        assert render_calls == ["render"]

    def test_render_contract_business_failed_remains_terminal(
        self, running_execution, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )

        def contract_fail(cls, execution, snapshot, render_snapshot):
            raise DashboardRenderContractError(widget_id="chart-1")

        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DashboardReportRenderService.render",
            classmethod(contract_fail),
        )

        decision = RetryClassifier.classify(
            AttemptResult(
                ok=False,
                failure_stage="render",
                error_code="render_contract_business_failed",
                error_message="contract",
            ),
            attempt_count=1,
            resource=_resource(),
        )
        assert decision.kind == ClassifierDecisionKind.TERMINAL_FAILED

        result = ExecutionOrchestrator.execute(running_execution.id)
        running_execution.refresh_from_db()
        assert result.status == DashboardReportExecution.Status.FAILED
        assert running_execution.attempt_count == 1
        assert running_execution.failure_stage == "render"
        assert (
            running_execution.error_code
            == "render_contract_business_failed"
        )
