"""CollectionRun 的流式结果生命周期与有界终态汇总。"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, replace

from core.collection.contracts import RunSummary, TargetCollectionResult
from core.collection.enums import FailureStage
from core.collection.result_delivery import BoundedResultDeliveryObserver
from core.logger import safe_log_value

_FAILURE_SAMPLE_LIMIT = 3
_FAILURE_CODE_LIMIT = 8


@dataclass(frozen=True)
class RunResultReport:
    """不含采集 payload 的 Run 终态报告。"""

    summary: RunSummary
    failure_codes: str = "-"
    failure_samples: str = "-"
    failure_sample_count: int = 0
    total_failures: int = 0
    publish_failure_codes: str = "-"
    publish_failure_samples: str = "-"
    ip_precheck_failure_count: int = 0
    ip_precheck_failure_sample_count: int = 0
    ip_precheck_failure_samples: str = "-"


class RunResultSink:
    """逐目标接管结果；以固定 worker 数等待发布终态。"""

    def __init__(
        self,
        *,
        delivery,
        metrics,
        total_targets: int,
        delivery_worker_count: int = 4,
        delivery_queue_capacity: int = 160,
    ) -> None:
        if total_targets < 0:
            raise ValueError("total_targets must be >= 0")
        if delivery_worker_count <= 0:
            raise ValueError("delivery_worker_count must be greater than zero")
        if delivery_queue_capacity <= 0:
            raise ValueError("delivery_queue_capacity must be greater than zero")
        self._delivery_observer = BoundedResultDeliveryObserver(
            delivery,
            worker_count=min(int(delivery_worker_count), max(1, int(total_targets))),
            queue_capacity=delivery_queue_capacity,
        )
        self._metrics = metrics
        self._total_targets = int(total_targets)
        self._accepted = 0
        self._collection_counts: Counter[str] = Counter()
        self._publish_counts: Counter[str] = Counter()
        self._failure_counts: Counter[str] = Counter()
        self._failure_samples: list[str] = []
        self._publish_failure_counts: Counter[str] = Counter()
        self._publish_failure_samples: list[tuple[int, str]] = []
        self._ip_precheck_failure_count = 0
        self._ip_precheck_failure_samples: list[str] = []
        self._pending_deliveries = 0
        self._delivery_terminal = asyncio.Event()
        self._delivery_terminal.set()
        self._delivery_error: BaseException | None = None

    @property
    def targets_terminal(self) -> int:
        return self._accepted

    @property
    def pending_deliveries(self) -> int:
        return self._pending_deliveries

    async def accept(self, pending) -> None:
        """接收一个目标终态；失败立即汇总，成功进入有界发布终态队列。"""

        if self._accepted >= self._total_targets:
            raise RuntimeError("run result sink received more targets than declared")
        self._accepted += 1
        result = pending.result
        self._record_collection(result)
        if not pending.delivery_required:
            self._record_publish(pending.index, result.target, "not_applicable", "")
            return

        self._pending_deliveries += 1
        self._metrics.add_gauge("result_deliveries_pending", 1)
        self._delivery_terminal.clear()
        await self._delivery_observer.observe(
            (replace(pending, result=None, target=result.target) if bool(getattr(pending.receipt, "retries_managed", False)) else pending),
            target=safe_log_value(result.target, max_length=255),
            on_terminal=self._delivery_finished,
        )

    async def finish(self) -> RunResultReport:
        """等待全部目标与发布进入终态，返回不持有 payload 的有界报告。"""

        if self._accepted != self._total_targets:
            raise RuntimeError(f"run result sink incomplete: accepted={self._accepted} total={self._total_targets}")
        await self._delivery_terminal.wait()
        await self._delivery_observer.drain()
        if self._delivery_error is not None:
            raise self._delivery_error

        summary = RunSummary(
            total=self._total_targets,
            collection_succeeded=self._collection_counts["success"],
            collection_failed=self._collection_counts["failed"],
            unreachable=self._collection_counts["unreachable"],
            deferred=self._collection_counts["deferred"],
            skipped=self._collection_counts["skipped"],
            publish_succeeded=self._publish_counts["succeeded"],
            publish_not_applicable=self._publish_counts["not_applicable"],
            publish_failed=self._publish_counts["failed"],
            publish_unknown=self._publish_counts["unknown"],
            publish_event_failed=self._publish_counts["event_failed"],
            publish_permanent_failed=self._publish_counts["permanent_failed"],
        )
        ordered_publish_samples = sorted(self._publish_failure_samples)
        return RunResultReport(
            summary=summary,
            failure_codes=_bounded_failure_counts(self._failure_counts),
            failure_samples=",".join(self._failure_samples) or "-",
            failure_sample_count=len(self._failure_samples),
            total_failures=sum(self._failure_counts.values()),
            publish_failure_codes=_render_counts(self._publish_failure_counts),
            publish_failure_samples=",".join(sample for _index, sample in ordered_publish_samples) or "-",
            ip_precheck_failure_count=self._ip_precheck_failure_count,
            ip_precheck_failure_sample_count=len(self._ip_precheck_failure_samples),
            ip_precheck_failure_samples=",".join(self._ip_precheck_failure_samples) or "-",
        )

    async def abort(self) -> None:
        """Run 被取消或框架失败时停止回执观察，不遗留持有 payload 的 Task。"""

        await self._delivery_observer.abort()
        if self._pending_deliveries:
            self._metrics.add_gauge("result_deliveries_pending", -self._pending_deliveries)
            self._pending_deliveries = 0
            self._delivery_terminal.set()

    def _record_collection(self, result: TargetCollectionResult) -> None:
        self._collection_counts[result.status] += 1
        if result.status not in {"failed", "unreachable"}:
            return
        error_code = result.error_code or result.status
        _increment_bounded(self._failure_counts, error_code)
        if result.failed_stage == FailureStage.IP_PRECHECK:
            self._ip_precheck_failure_count += 1
            if len(self._ip_precheck_failure_samples) < _FAILURE_SAMPLE_LIMIT:
                self._ip_precheck_failure_samples.append(
                    "%s|%s"
                    % (
                        safe_log_value(result.target, max_length=255),
                        safe_log_value(error_code),
                    )
                )
        if len(self._failure_samples) < _FAILURE_SAMPLE_LIMIT:
            self._failure_samples.append(
                "%s|%s|%s"
                % (
                    safe_log_value(result.target, max_length=255),
                    safe_log_value(_failure_stage_name(result)),
                    safe_log_value(error_code),
                )
            )

    def _delivery_finished(
        self,
        index: int,
        target: str,
        publish_status: str,
        error_code: str,
        error: Exception | None,
    ) -> None:
        try:
            if error is not None:
                if self._delivery_error is None:
                    self._delivery_error = error
                return
            self._record_publish(index, target, publish_status, error_code)
        finally:
            self._pending_deliveries = max(0, self._pending_deliveries - 1)
            self._metrics.add_gauge("result_deliveries_pending", -1)
            if self._pending_deliveries == 0:
                self._delivery_terminal.set()

    def _record_publish(self, index: int, target: str, status: str, error_code: str) -> None:
        self._publish_counts[status] += 1
        self._metrics.increment(f"publish_{status}_total")
        if status == "succeeded":
            self._metrics.increment("publish_confirmed_total")
            return
        if status == "unknown":
            self._metrics.increment("publish_delivery_unknown_total")
        elif status == "failed":
            self._metrics.increment("publish_retryable_failed_total")
        if status == "not_applicable":
            return

        reason = error_code or status
        _increment_bounded(self._publish_failure_counts, reason)
        self._publish_failure_samples.append((index, f"{safe_log_value(target, max_length=255)}|{safe_log_value(reason)}"))
        self._publish_failure_samples.sort(key=lambda item: item[0])
        del self._publish_failure_samples[_FAILURE_SAMPLE_LIMIT:]


def _bounded_failure_counts(failure_counts: Counter[str]) -> str:
    other_count = failure_counts.get("other", 0)
    ordered = sorted(
        ((code, count) for code, count in failure_counts.items() if code != "other"),
        key=lambda item: (-item[1], str(item[0])),
    )
    visible = ordered[:_FAILURE_CODE_LIMIT]
    rendered = [f"{safe_log_value(code)}:{count}" for code, count in visible]
    other_count += sum(count for _code, count in ordered[_FAILURE_CODE_LIMIT:])
    if other_count:
        rendered.append(f"other:{other_count}")
    return ",".join(rendered) or "-"


def _increment_bounded(counts: Counter[str], code: str) -> None:
    if code in counts or len(counts) < _FAILURE_CODE_LIMIT:
        counts[code] += 1
    else:
        counts["other"] += 1


def _render_counts(counts: Counter[str]) -> str:
    return ",".join(f"{safe_log_value(code)}:{count}" for code, count in sorted(counts.items())) or "-"


def _failure_stage_name(result: TargetCollectionResult) -> str:
    if result.failed_stage is not None:
        return result.failed_stage.value
    error_code = result.error_code or result.status
    if result.status == "unreachable" and result.attempts == 0:
        return "preflight"
    if error_code.startswith("access_probe_") or error_code in {
        "protocol_no_response",
        "snmp_no_response",
        "no_response_attempt_limit",
        "target_unreachable",
    }:
        return "access_probe"
    if error_code in {
        "authentication_failed",
        "credential_state_unavailable",
        "credentials_exhausted",
        "no_matching_credential",
        "no_valid_credential",
    }:
        return "credential"
    return "collection"


__all__ = ["RunResultReport", "RunResultSink"]
