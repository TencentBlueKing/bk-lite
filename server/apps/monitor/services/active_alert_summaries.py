# -*- coding: utf-8 -*-
"""Per-monitor active alert summaries for room3D and similar callers.

Counts only status=new MonitorAlert under actor-accessible policies.
Levels are restricted to critical|error|warning (info excluded).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db.models import Count

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorAlert

ACTIVE_ALERT_SUMMARY_BATCH_SIZE = 100
ACTIVE_ALERT_SEVERITY_LEVELS = frozenset({"critical", "error", "warning"})
_SEVERITY_RANK = {"critical": 3, "error": 2, "warning": 1}


class ActiveAlertSummaryError(ValueError):
    """Caller-facing validation / permission context error."""


def normalize_monitor_ids(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise ActiveAlertSummaryError("monitor_ids 必须是列表")
    unique: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item).strip() if item not in (None, "") else ""
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _max_severity(levels: set[str]) -> str | None:
    best = None
    best_rank = 0
    for level in levels:
        rank = _SEVERITY_RANK.get(level, 0)
        if rank > best_rank:
            best_rank = rank
            best = level
    return best


def summarize_active_alerts_by_monitor_ids(
    monitor_ids: list[str] | None,
    *,
    user_info: dict | None,
    accessible_policy_queryset_loader=None,
    accessible_instance_queryset_loader=None,
) -> dict[str, Any]:
    """Return per-monitor active alarm summaries for the given actor.

    Response shape::

        {
          "result": True,
          "data": {
            "items": [
              {
                "monitor_id": "...",
                "active_alarm_count": 0,
                "highest_severity": None,
              },
            ]
          },
          "message": "",
        }

    Only authorized monitor instances appear in ``items``. Callers should treat
    missing requested ids as alarm-unavailable for bound devices.
    """
    try:
        ordered_ids = normalize_monitor_ids(monitor_ids)
    except ActiveAlertSummaryError as exc:
        return {"result": False, "data": {"items": []}, "message": str(exc)}

    if not ordered_ids:
        return {"result": True, "data": {"items": []}, "message": ""}

    user_info = user_info or {}
    policy_loader = accessible_policy_queryset_loader
    instance_loader = accessible_instance_queryset_loader
    if policy_loader is None or instance_loader is None:
        from apps.monitor.nats import monitor as monitor_nats

        policy_loader = policy_loader or monitor_nats._get_nats_accessible_policy_queryset
        instance_loader = instance_loader or monitor_nats._get_nats_accessible_instance_queryset

    try:
        policy_qs, policy_error = policy_loader(user_info)
        if policy_error:
            return policy_error
        instance_qs, instance_error = instance_loader(user_info)
        if instance_error:
            return instance_error
    except Exception as exc:
        logger.exception(
            "active alert summary permission context failed monitor_id_count=%s " "failed_stage=permission_context error_type=%s",
            len(ordered_ids),
            type(exc).__name__,
        )
        return {
            "result": False,
            "data": {"items": []},
            "message": "告警权限上下文加载失败",
        }

    try:
        policy_ids = list(policy_qs.values_list("id", flat=True))
        authorized_ids = set(instance_qs.filter(id__in=ordered_ids).values_list("id", flat=True))
    except Exception as exc:
        logger.exception(
            "active alert summary authorization query failed monitor_id_count=%s " "failed_stage=authorize error_type=%s",
            len(ordered_ids),
            type(exc).__name__,
        )
        return {
            "result": False,
            "data": {"items": []},
            "message": "告警授权查询失败",
        }

    authorized_ordered = [monitor_id for monitor_id in ordered_ids if monitor_id in authorized_ids]
    counts: dict[str, int] = defaultdict(int)
    levels: dict[str, set[str]] = defaultdict(set)

    if authorized_ordered and policy_ids:
        try:
            for offset in range(0, len(authorized_ordered), ACTIVE_ALERT_SUMMARY_BATCH_SIZE):
                batch = authorized_ordered[offset : offset + ACTIVE_ALERT_SUMMARY_BATCH_SIZE]
                rows = (
                    MonitorAlert.objects.filter(
                        status="new",
                        monitor_instance_id__in=batch,
                        policy_id__in=policy_ids,
                        level__in=ACTIVE_ALERT_SEVERITY_LEVELS,
                    )
                    .values("monitor_instance_id", "level")
                    .annotate(count=Count("id"))
                )
                for row in rows:
                    monitor_id = str(row["monitor_instance_id"])
                    level = str(row["level"]).strip().lower()
                    if level not in ACTIVE_ALERT_SEVERITY_LEVELS:
                        continue
                    counts[monitor_id] += int(row["count"] or 0)
                    levels[monitor_id].add(level)
        except Exception as exc:
            logger.exception(
                "active alert summary query failed monitor_id_count=%s " "failed_stage=aggregate error_type=%s",
                len(authorized_ordered),
                type(exc).__name__,
            )
            return {
                "result": False,
                "data": {"items": []},
                "message": "告警聚合查询失败",
            }

    items = [
        {
            "monitor_id": monitor_id,
            "active_alarm_count": int(counts.get(monitor_id, 0)),
            "highest_severity": _max_severity(levels.get(monitor_id, set())),
        }
        for monitor_id in authorized_ordered
    ]
    return {"result": True, "data": {"items": items}, "message": ""}
