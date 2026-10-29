"""策略条件列表：镜像、旧单条件判定，以及多条件级别合成。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmPolicy
from apps.apm.services.contracts import MetricDataState
from apps.core.logger import apm_logger as logger

REQUEST_COUNT_METRIC = "request_count"
MIRROR_FIELDS = (
    "metric_type",
    "compare_mode",
    "compare_offset_amount",
    "compare_value_kind",
    "min_request_count",
    "slow_threshold_ms",
    "apdex_threshold_ms",
    "thresholds",
)
_MIRROR = frozenset(MIRROR_FIELDS)
_UNDECIDED = {
    MetricDataState.NO_DATA,
    MetricDataState.MISSING_BASELINE,
    MetricDataState.INSUFFICIENT_SAMPLES,
}


def anchor_from_policy(policy) -> dict:
    return {
        "ref": "a",
        "role": "regular",
        "metric_type": policy.metric_type,
        "compare_mode": policy.compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
        "compare_offset_amount": policy.compare_offset_amount,
        "compare_value_kind": policy.compare_value_kind or "",
        "min_request_count": policy.min_request_count,
        "slow_threshold_ms": policy.slow_threshold_ms,
        "apdex_threshold_ms": policy.apdex_threshold_ms,
        "thresholds": list(policy.thresholds or []),
    }


def effective_conditions(policy) -> list[dict]:
    stored = list(getattr(policy, "conditions", None) or [])
    if stored:
        return stored
    return [anchor_from_policy(policy)]


def regular_conditions(conditions) -> list[dict]:
    return [item for item in conditions if item.get("role") != "guard"]


def guard_conditions(conditions) -> list[dict]:
    return [item for item in conditions if item.get("role") == "guard"]


def condition_value_map(result) -> dict:
    if getattr(result, "condition_rows", None):
        values = {}
        for row in result.condition_rows:
            raw = row.get("compared_value")
            values[str(row.get("ref"))] = str(raw) if raw is not None else None
        return values
    return {"a": str(result.value) if result.value is not None else None}


def compare_window_key(condition: dict):
    mode = condition.get("compare_mode") or ApmPolicy.CompareMode.ABSOLUTE
    if mode == ApmPolicy.CompareMode.ABSOLUTE:
        return None
    return (mode, condition.get("compare_offset_amount"))


def _same_mirror(policy, anchor: dict) -> bool:
    for field in MIRROR_FIELDS:
        left = anchor.get(field)
        right = getattr(policy, field)
        if field == "thresholds":
            if list(left or []) != list(right or []):
                return False
            continue
        if field == "compare_mode":
            left = left or ApmPolicy.CompareMode.ABSOLUTE
            right = right or ApmPolicy.CompareMode.ABSOLUTE
        elif field == "compare_value_kind":
            left = left or ""
            right = right or ""
        if left != right:
            return False
    return True


def uses_legacy_evaluation(policy) -> bool:
    """空条件或一条常规条件且镜像列一致时，沿用升级前的单条件判定。"""
    stored = list(getattr(policy, "conditions", None) or [])
    if not stored:
        return True
    regulars = regular_conditions(stored)
    if len(regulars) != 1 or guard_conditions(stored):
        return False
    return _same_mirror(policy, regulars[0])


class ConditionView:
    """把一条条件伪装成策略，复用单条件取值。恢复线只对锚点生效。"""

    def __init__(self, policy, condition: dict, *, anchor: bool):
        self._policy = policy
        self._condition = condition
        self._anchor = anchor

    def __getattr__(self, name):
        if name == "recovery_threshold":
            if self._anchor:
                return getattr(self._policy, "recovery_threshold", None) or {}
            return {}
        if name in _MIRROR and name in self._condition:
            return self._condition[name]
        return getattr(self._policy, name)


def log_condition_failure(policy, exc: Exception) -> None:
    proxy = RuntimeError(type(exc).__name__)
    logger.warning(
        "event=apm_policy_condition_failed policy_id=%s failed_stage=%s error_type=%s",
        "" if getattr(policy, "pk", None) is None else str(policy.pk),
        "conditions",
        type(exc).__name__,
        exc_info=(type(proxy), proxy, exc.__traceback__),
    )


def _query_one(service, policy, condition, *, anchor, evaluated_at, endpoint, version, cache, instance_id="", target_service=None, dependency=None):
    view = ConditionView(policy, condition, anchor=anchor)
    try:
        return service.test_query(
            view,
            evaluated_at=evaluated_at,
            endpoint=endpoint,
            version=version,
            cache=cache,
            instance_id=instance_id,
            target_service=target_service,
            dependency=dependency,
        )
    except TelemetryStoreUnavailable:
        raise
    except Exception as exc:
        log_condition_failure(policy, exc)
        raise TelemetryStoreUnavailable("conditions") from None


def _condition_row(ref: str, result) -> dict:
    matched = None
    threshold_value = None
    if result.breached and result.threshold:
        matched = str(result.threshold.get("severity") or "") or None
        threshold_value = "" if result.threshold.get("value") is None else str(result.threshold.get("value"))
    return {
        "ref": ref,
        "current_value": result.current_value,
        "baseline_value": result.baseline_value,
        "compared_value": result.value,
        "matched_severity": matched,
        "threshold_value": threshold_value,
    }


def _project(service, policy, anchor_result, rows, guards, **overrides):
    value = overrides["value"] if "value" in overrides else anchor_result.value
    breached = overrides["breached"] if "breached" in overrides else anchor_result.breached
    threshold = overrides["threshold"] if "threshold" in overrides else anchor_result.threshold
    return service._query_result(
        policy,
        value=value,
        breached=breached,
        evaluated_at=anchor_result.evaluated_at,
        data_state=overrides.get("data_state", anchor_result.data_state),
        series=anchor_result.series,
        threshold=threshold,
        current_value=anchor_result.current_value,
        baseline_value=anchor_result.baseline_value,
        baseline_series=anchor_result.baseline_series,
        request_count=anchor_result.request_count,
        reason=overrides.get("reason", anchor_result.reason),
        window_ended_at=anchor_result.window_ended_at,
        baseline_days_used=anchor_result.baseline_days_used,
        condition_rows=tuple(rows),
        guard_rows=tuple(guards),
        guard_blocked=overrides.get("guard_blocked", False),
    )


def _missing(service, policy, anchor_result, rows, guards):
    return _project(
        service,
        policy,
        anchor_result,
        rows,
        guards,
        value=None,
        breached=None,
        data_state=MetricDataState.MISSING_CONDITION_DATA,
        threshold=None,
        reason="missing_condition_data",
    )


def _guard_metric(guard: dict) -> dict:
    return {
        "role": "regular",
        "metric_type": guard["metric_type"],
        "compare_mode": ApmPolicy.CompareMode.ABSOLUTE,
        "compare_offset_amount": None,
        "compare_value_kind": "",
        "min_request_count": None,
        "slow_threshold_ms": None,
        "apdex_threshold_ms": None,
        "thresholds": [],
    }


def _guard_value(
    service, policy, guard, anchor_result, *, evaluated_at, endpoint, version, cache, instance_id="", target_service=None, dependency=None
):
    if guard["metric_type"] == REQUEST_COUNT_METRIC:
        if anchor_result.request_count is None:
            return None
        return Decimal(int(anchor_result.request_count))
    from apps.apm.services.policies import evaluation_delay

    window = max(int(policy.metric_window or 1), 1)
    window_end = evaluated_at - evaluation_delay()
    current_start = window_end - timedelta(minutes=window)
    view = ConditionView(policy, _guard_metric(guard), anchor=False)
    try:
        red = service._read_window(
            view,
            started_at=current_start,
            ended_at=window_end,
            endpoint=endpoint or "",
            version=version or "",
            include_endpoints=True,
            cache=cache,
            instance_id=instance_id,
            service=target_service,
            dependency=dependency,
        )
    except TelemetryStoreUnavailable:
        raise
    except Exception as exc:
        log_condition_failure(policy, exc)
        raise TelemetryStoreUnavailable("conditions") from None
    return service._raw_value(view, red)


def evaluate_policy_conditions(service, policy, *, evaluated_at, endpoint, version, instance_id="", target_service=None, dependency=None):
    if endpoint is None:
        endpoint, version = service._targets(policy)[0]
    conditions = effective_conditions(policy)
    regulars = regular_conditions(conditions)
    guards = guard_conditions(conditions)
    cache: dict = {}
    anchor = regulars[0]
    anchor_result = _query_one(
        service,
        policy,
        anchor,
        anchor=True,
        evaluated_at=evaluated_at,
        endpoint=endpoint,
        version=version,
        cache=cache,
        instance_id=instance_id,
        target_service=target_service,
        dependency=dependency,
    )
    rows = [_condition_row(str(anchor.get("ref") or "a"), anchor_result)]
    if anchor_result.data_state in _UNDECIDED:
        return _project(service, policy, anchor_result, rows, ())

    others = []
    for condition in regulars[1:]:
        result = _query_one(
            service,
            policy,
            condition,
            anchor=False,
            evaluated_at=evaluated_at,
            endpoint=endpoint,
            version=version,
            cache=cache,
            instance_id=instance_id,
            target_service=target_service,
            dependency=dependency,
        )
        rows.append(_condition_row(str(condition.get("ref") or ""), result))
        if result.data_state in _UNDECIDED or result.value is None:
            return _missing(service, policy, anchor_result, rows, ())
        others.append(result)

    guard_rows = []
    blocked = False
    for guard in guards:
        observed = _guard_value(
            service,
            policy,
            guard,
            anchor_result,
            evaluated_at=evaluated_at,
            endpoint=endpoint,
            version=version,
            cache=cache,
            instance_id=instance_id,
            target_service=target_service,
            dependency=dependency,
        )
        if observed is None:
            guard_rows.append({"ref": guard["ref"], "value": None, "matched": False})
            return _missing(service, policy, anchor_result, rows, guard_rows)
        matched = service._breached(str(guard["comparator"]), Decimal(str(guard["value"])), observed)
        guard_rows.append({"ref": guard["ref"], "value": observed, "matched": matched})
        if not matched:
            blocked = True
    if blocked:
        return _project(
            service,
            policy,
            anchor_result,
            rows,
            guard_rows,
            breached=False,
            data_state=MetricDataState.AVAILABLE,
            threshold=None,
            guard_blocked=True,
            reason="guard_not_met",
        )

    if any(not result.breached for result in others):
        return _project(
            service,
            policy,
            anchor_result,
            rows,
            guard_rows,
            breached=False,
            data_state=MetricDataState.AVAILABLE,
            threshold=None,
        )
    if anchor_result.data_state == MetricDataState.HOLD or not anchor_result.breached:
        return _project(service, policy, anchor_result, rows, guard_rows, threshold=None if not anchor_result.breached else anchor_result.threshold)

    matched = [anchor_result, *others]
    lowest = max(matched, key=lambda item: service._severity_rank(str(item.threshold["severity"])))
    return _project(
        service,
        policy,
        anchor_result,
        rows,
        guard_rows,
        value=anchor_result.value,
        breached=True,
        data_state=MetricDataState.AVAILABLE,
        threshold=dict(lowest.threshold),
    )
