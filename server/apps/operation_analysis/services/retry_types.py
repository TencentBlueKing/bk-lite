from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResumeClass(StrEnum):
    RENDER_SNAPSHOT_ENSURE = "render_snapshot_ensure"
    RENDER = "render"
    DELIVERY = "delivery"


class ClassifierDecisionKind(StrEnum):
    RETRY = "retry"
    TERMINAL_FAILED = "terminal_failed"
    TERMINAL_UNKNOWN = "terminal_unknown"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True)
class AttemptResult:
    ok: bool
    failure_stage: str = ""
    error_code: str = ""
    error_message: str = ""
    side_effect: str = ""  # 仅日志/调试；不参与 Classifier


@dataclass(frozen=True)
class ResourceState:
    input_snapshot: str  # absent | valid | corrupt
    render_snapshot: str  # absent | valid | corrupt
    artifact: str  # absent | valid | unusable
    delivery_outcome: str  # not_delivered | delivered | smtp_unknown


@dataclass(frozen=True)
class ClassifierDecision:
    kind: ClassifierDecisionKind
    resume_class: ResumeClass | None = None
