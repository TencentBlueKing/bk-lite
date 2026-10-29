"""日志策略试算：只读复用扫描判定，不写告警、事件、快照或游标，不发通知。"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.http import JsonResponse

from apps.core.logger import log_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.web_utils import WebUtils
from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Policy
from apps.log.serializers.policy import PolicySerializer
from apps.log.tasks.services.policy_scan import LogPolicyScan
from apps.log.tasks.utils.policy import period_to_seconds

DRY_RUN_FAIL_TEMPLATE = "event=log_policy_dry_run_failed policy_id=%s failed_stage=%s error_type=%s"
_SKIP_POLICY_FIELDS = frozenset({"id", "last_run_time"})


def _safe_now():
    return datetime.now(dt_timezone.utc) - timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)


def _flatten_validation(detail):
    if isinstance(detail, dict):
        return "; ".join(f"{key}: {_flatten_validation(value)}" for key, value in detail.items())
    if isinstance(detail, (list, tuple)):
        return "; ".join(_flatten_validation(item) for item in detail)
    return str(detail)


class LogPolicyDryRunService:
    def __init__(self, payload, request, view):
        self.payload = payload if payload is not None else {}
        self.request = request
        self.view = view

    def run(self):
        failed_stage = "authorize"
        policy_id = ""
        try:
            payload = self._payload_dict()
            raw_id = payload.pop("id", None)
            if raw_id not in (None, ""):
                policy_id = str(raw_id)
            organizations, instance, denied = self._authorize(payload, raw_id)
            if denied is not None:
                return denied
            if instance is not None:
                policy_id = str(instance.pk)
            failed_stage = "serialize"
            policy, invalid = self._serialize(payload, instance, organizations)
            if invalid is not None:
                return invalid
            failed_stage = "build_policy"
            policy = self._build_policy(policy, instance)
            failed_stage = "evaluate"
            evaluated = self._evaluate(policy)
            failed_stage = "sample"
            rows = evaluated.pop("_rows")
            scan = evaluated.pop("_scan")
            window = evaluated.pop("_window")
            evaluated["sample_preview"] = self._sample_preview(policy, scan, rows, window)
            return evaluated
        except Exception as exc:
            logger.error(
                DRY_RUN_FAIL_TEMPLATE,
                policy_id,
                failed_stage,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return WebUtils.response_error("试算失败")

    def _payload_dict(self):
        source = self.payload
        if hasattr(source, "copy"):
            copied = source.copy()
            if isinstance(copied, dict):
                return dict(copied)
        if isinstance(source, dict):
            return dict(source)
        return {}

    def _authorize(self, payload, raw_id):
        organizations, error_response = self.view._validate_organizations_payload(
            payload.pop("organizations", None),
            required=True,
        )
        if error_response is not None:
            return None, None, error_response
        denied = self.view._authorize_target_organizations(self.request, organizations, payload.get("collect_type"))
        if denied is not None:
            return None, None, denied
        if raw_id in (None, ""):
            return organizations, None, None
        try:
            instance = Policy.objects.prefetch_related("policyorganization_set").get(pk=raw_id)
        except (Policy.DoesNotExist, ValueError, TypeError):
            return None, None, WebUtils.response_error("策略不存在")
        denied = self.view._authorize_policy(self.request, instance)
        if denied is not None:
            return None, None, denied
        return organizations, instance, None

    def _serialize(self, payload, instance, organizations):
        self.view._pending_policy_organizations = organizations
        context = self.view.get_serializer_context()
        context["dry_run"] = True
        context["policy_organizations"] = organizations
        serializer = PolicySerializer(data=payload, instance=instance, context=context)
        if not serializer.is_valid():
            return None, WebUtils.response_error(_flatten_validation(serializer.errors))
        return serializer.validated_data, None

    def _build_policy(self, validated_data, instance):
        policy = Policy()
        for field in Policy._meta.concrete_fields:
            name = field.name
            if name in _SKIP_POLICY_FIELDS or name not in validated_data:
                continue
            setattr(policy, name, validated_data[name])
        if instance is not None:
            policy.pk = instance.pk
        return policy

    def _evaluate(self, policy):
        safe_now = _safe_now()
        period_seconds = period_to_seconds(policy.period)
        window_end = int(safe_now.timestamp())
        window_start = window_end - period_seconds
        scan = LogPolicyScan(policy, scan_time=safe_now, window_start=window_start, window_end=window_end)
        rows = scan._detection_rows(window_start, window_end)
        if policy.alert_type == AlertConstants.TYPE_KEYWORD:
            items = [self._keyword_item(row) for row in rows]
            baseline_status = "not_required"
        else:
            items = [self._aggregate_item(row) for row in rows]
            baseline_status = getattr(scan, "baseline_status", "not_required")
        duration = window_end - window_start
        return {
            "alert_type": policy.alert_type,
            "window": {"start": window_start, "end": window_end},
            "previous_window": {"start": window_start - duration, "end": window_start},
            "baseline_status": baseline_status,
            "baselines": self._baseline_summary(scan),
            "items": items[: AlertConstants.DRY_RUN_ITEM_LIMIT],
            "truncated": len(items) > AlertConstants.DRY_RUN_ITEM_LIMIT,
            "_rows": rows,
            "_scan": scan,
            "_window": (window_start, window_end),
        }

    @staticmethod
    def _with_streak(item, row):
        if isinstance(row, dict) and "streak" in row:
            item["streak"] = row.get("streak")
        return item

    @staticmethod
    def _keyword_item(row):
        count = row.get("total_count") or 0
        reason = row.get("reason") or ""
        streak_blocks = "streak" in row and not row.get("triggered")
        if reason == "window_failed" or streak_blocks:
            verdict = "no_trigger"
        elif count > 0:
            verdict = "would_trigger"
        elif count == 0:
            verdict = "no_trigger"
        else:
            verdict = "no_data"
        return LogPolicyDryRunService._with_streak(
            {
                "group": row.get("group_values") or {},
                "count": count,
                "previous_count": None,
                "count_rate": None,
                "count_delta": None,
                "conditions": [],
                "no_data": False,
                "verdict": verdict,
                "reason": reason,
            },
            row,
        )

    @staticmethod
    def _aggregate_item(row):
        aggregate_data = row.get("aggregate_data") or {}
        if row.get("triggered"):
            verdict = "would_trigger"
        elif row.get("reason") == "missing_baseline":
            verdict = "missing_baseline"
        elif aggregate_data.get("count") is None:
            verdict = "no_data"
        else:
            verdict = "no_trigger"
        return LogPolicyDryRunService._with_streak(
            {
                "group": row.get("group_values") or {},
                "count": aggregate_data.get("count"),
                "previous_count": aggregate_data.get("previous_count"),
                "count_rate": aggregate_data.get("count_rate"),
                "count_delta": aggregate_data.get("count_delta"),
                "conditions": list(aggregate_data.get("conditions") or []),
                "level": aggregate_data.get("level"),
                "no_data": False,
                "verdict": verdict,
                "reason": row.get("reason") or "",
            },
            row,
        )

    @staticmethod
    def _baseline_summary(scan):
        source = getattr(scan, "baselines", None) or {}
        summary = {}
        for key, info in source.items():
            if not isinstance(info, dict):
                continue
            summary[key] = {
                "window": info.get("window") or {},
                "status": info.get("status") or "unavailable",
            }
        return summary

    def _sample_preview(self, policy, scan, rows, window):
        if not rows:
            return []
        try:
            chosen = next((row for row in rows if row.get("triggered")), rows[0])
            limit = scan._get_keyword_sample_limit(getattr(policy, "alert_condition", None) or {})
            start, end = window
            group_values = chosen.get("group_values") or {}
            final_query = chosen.get("final_query")
            if not final_query:
                base_query = (getattr(policy, "alert_condition", None) or {}).get("query") or "*"
                final_query = scan._build_query_with_log_groups(base_query)
            sample_query = scan._build_group_sample_query(final_query, group_values)
            logs = scan.vlogs_api.query(query=sample_query, start=start, end=end, limit=limit)
        except Exception as exc:
            logger.warning(
                "event=log_policy_dry_run_sample_failed policy_id=%s failed_stage=%s error_type=%s",
                getattr(policy, "id", "") or "",
                "sample",
                type(exc).__name__,
            )
            return []
        if not isinstance(logs, list):
            return []
        return logs[:limit]


def is_dry_run_response(result):
    return isinstance(result, JsonResponse)
