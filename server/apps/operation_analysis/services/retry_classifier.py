from __future__ import annotations

from apps.operation_analysis.services.retry_types import (
    AttemptResult,
    ClassifierDecision,
    ClassifierDecisionKind,
    ResourceState,
    ResumeClass,
)

MAX_ATTEMPTS = 3

_RETRYABLE_RENDER_CODES = frozenset(
    {
        "chromium_launch_failed",
        "page_load_failed",
        "report_ready_timeout",
        "pdf_generate_failed",
        "widget_query_timeout",
        "widget_query_transient",
    }
)

_RETRYABLE_EMAIL_CODES = frozenset(
    {
        "smtp_transient",
        "smtp_connection_failed",
        "smtp_timeout",
    }
)

_TERMINAL_PERMISSION_CODES = frozenset(
    {
        "creator_inactive",
        "dashboard_view_denied",
        "dashboard_missing",
    }
)

_TERMINAL_SNAPSHOT_CODES = frozenset(
    {
        "input_snapshot_absent",
        "input_snapshot_corrupt",
        "filter_invalid",
    }
)

_TERMINAL_RENDER_CODES = frozenset(
    {
        "pdf_too_large",
        "render_contract_business_failed",
        "render_snapshot_create_permanent",
    }
)

_TERMINAL_EMAIL_CODES = frozenset(
    {
        "channel_missing",
        "channel_not_email",
        "smtp_permanent",
    }
)


class RetryClassifier:
    """唯一 retry 策略入口；Step 不得决定 retry。"""

    @classmethod
    def classify(
        cls,
        result: AttemptResult,
        attempt_count: int,
        resource: ResourceState,
    ) -> ClassifierDecision:
        if resource.delivery_outcome == "delivered":
            return ClassifierDecision(kind=ClassifierDecisionKind.SUCCEEDED)

        if result.ok:
            return ClassifierDecision(kind=ClassifierDecisionKind.SUCCEEDED)

        if resource.delivery_outcome == "smtp_unknown":
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_UNKNOWN
            )

        stage = result.failure_stage
        code = result.error_code

        if code == "smtp_result_unknown":
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_UNKNOWN
            )

        if code == "execution_timeout":
            if resource.delivery_outcome == "delivered":
                return ClassifierDecision(
                    kind=ClassifierDecisionKind.SUCCEEDED
                )
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if stage == "permission_check" or code in _TERMINAL_PERMISSION_CODES:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if stage == "snapshot" or code in _TERMINAL_SNAPSHOT_CODES:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if code == "render_snapshot_corrupt" or (
            stage == "render_snapshot"
            and resource.render_snapshot == "corrupt"
        ):
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if code in _TERMINAL_RENDER_CODES:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if code in _TERMINAL_EMAIL_CODES:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if not code:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if attempt_count >= MAX_ATTEMPTS:
            return ClassifierDecision(
                kind=ClassifierDecisionKind.TERMINAL_FAILED
            )

        if (
            code == "render_snapshot_create_transient"
            and resource.input_snapshot == "valid"
            and resource.render_snapshot == "absent"
            and resource.delivery_outcome == "not_delivered"
        ):
            return ClassifierDecision(
                kind=ClassifierDecisionKind.RETRY,
                resume_class=ResumeClass.RENDER_SNAPSHOT_ENSURE,
            )

        if (
            (
                code in _RETRYABLE_RENDER_CODES
                or stage in {"render", "data_load"}
                and code in _RETRYABLE_RENDER_CODES
            )
            and resource.input_snapshot == "valid"
            and resource.render_snapshot == "valid"
            and resource.artifact in {"absent", "unusable"}
            and resource.delivery_outcome == "not_delivered"
        ):
            return ClassifierDecision(
                kind=ClassifierDecisionKind.RETRY,
                resume_class=ResumeClass.RENDER,
            )

        if (
            code in _RETRYABLE_EMAIL_CODES
            and resource.input_snapshot == "valid"
            and resource.render_snapshot == "valid"
            and resource.delivery_outcome == "not_delivered"
        ):
            if resource.artifact == "valid":
                return ClassifierDecision(
                    kind=ClassifierDecisionKind.RETRY,
                    resume_class=ResumeClass.DELIVERY,
                )
            if resource.artifact in {"absent", "unusable"}:
                return ClassifierDecision(
                    kind=ClassifierDecisionKind.RETRY,
                    resume_class=ResumeClass.RENDER,
                )

        return ClassifierDecision(
            kind=ClassifierDecisionKind.TERMINAL_FAILED
        )
