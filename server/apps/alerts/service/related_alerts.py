from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Prefetch
from django.utils import timezone

from apps.alerts.constants import AlertStatus
from apps.alerts.models.models import Alert, Event
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids


DIMENSION_PRIORITY = {
    "service": 4,
    "location": 3,
    "resource_name": 2,
    "item": 1,
}

MATCH_REASON_MAP = {
    "service": "相同服务",
    "location": "相同位置",
    "resource_name": "相同资源",
    "item": "相关指标",
}


class RelatedAlertsService:
    DEFAULT_TIME_WINDOW_MINUTES = 60
    MAX_CANDIDATES = 100

    @classmethod
    def find_related_alerts(
        cls,
        alert: Alert,
        *,
        time_window_minutes: int = DEFAULT_TIME_WINDOW_MINUTES,
        limit: int = 10,
        group_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        time_window_minutes = cls.DEFAULT_TIME_WINDOW_MINUTES
        normalized_limit = min(max(limit, 1), 50)
        current_dimensions = cls._get_alert_dimensions(alert)
        if not current_dimensions:
            return {
                "related_count": 0,
                "maybe_related_count": 0,
                "current_incidents": cls._get_incidents_summary(alert),
                "items": [],
            }

        candidates = cls._fetch_candidates(
            alert,
            time_window_minutes=time_window_minutes,
            group_ids=group_ids,
        )
        items = cls._rank_candidates(alert, current_dimensions, candidates)[:normalized_limit]
        related_count = len([item for item in items if item["similarity_score"] >= 50])

        return {
            "related_count": related_count,
            "maybe_related_count": len(items) - related_count,
            "current_incidents": cls._get_incidents_summary(alert),
            "items": items,
        }

    @classmethod
    def _fetch_candidates(
        cls,
        alert: Alert,
        *,
        time_window_minutes: int,
        group_ids: Optional[List[int]],
    ) -> List[Alert]:
        cutoff_time = timezone.now() - timedelta(minutes=time_window_minutes)
        queryset = Alert.objects.filter(
            created_at__gte=cutoff_time,
            status__in=AlertStatus.ACTIVATE_STATUS,
        ).exclude(pk=alert.pk)
        queryset = queryset.prefetch_related(
            "incident_set",
            Prefetch("events", queryset=Event.objects.only(
                "id",
                "event_id",
                "service",
                "location",
                "resource_name",
                "item",
            )),
        ).order_by("-last_event_time")

        queryset = apply_team_scope_with_group_ids(queryset, group_ids, field_name="team")

        return list(queryset[: cls.MAX_CANDIDATES])

    @classmethod
    def _rank_candidates(
        cls,
        current_alert: Alert,
        current_dimensions: Dict[str, str],
        candidates: List[Alert],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for candidate in candidates:
            candidate_dimensions = cls._get_alert_dimensions(candidate)
            score, matched_dimensions = cls._calculate_similarity(current_dimensions, candidate_dimensions)
            if score <= 0:
                continue

            result.append(
                {
                    "id": candidate.id,
                    "alert_id": candidate.alert_id,
                    "title": candidate.title,
                    "content": candidate.content,
                    "level": candidate.level,
                    "status": candidate.status,
                    "first_event_time": candidate.first_event_time,
                    "last_event_time": candidate.last_event_time,
                    "incidents": cls._get_incidents_summary(candidate),
                    "similarity_score": score,
                    "match_reason": cls._get_match_reason(matched_dimensions, score),
                    "matched_dimensions": matched_dimensions,
                    "time_proximity": cls._format_time_proximity(
                        current_alert.last_event_time,
                        candidate.last_event_time,
                    ),
                }
            )

        result.sort(
            key=lambda item: (
                item["similarity_score"],
                item["last_event_time"] or timezone.now(),
            ),
            reverse=True,
        )
        return result

    @classmethod
    def _get_alert_dimensions(cls, alert: Alert) -> Dict[str, str]:
        dimensions = alert.dimensions or {}
        if dimensions:
            return {str(key): str(value) for key, value in dimensions.items() if value not in (None, "")}

        return cls._extract_dimensions_from_events(alert)

    @staticmethod
    def _extract_dimensions_from_events(alert: Alert) -> Dict[str, str]:
        group_by_field = alert.group_by_field or ""
        dimension_names = [item.strip() for item in group_by_field.split(",") if item.strip()]
        if not dimension_names:
            return {}

        dimensions: Dict[str, str] = {}
        events = list(alert.events.all())
        for dimension_name in dimension_names:
            values = {
                str(getattr(event, dimension_name)).strip()
                for event in events
                if getattr(event, dimension_name, None) not in (None, "")
            }
            if len(values) == 1:
                dimensions[dimension_name] = values.pop()
        return dimensions

    @staticmethod
    def _calculate_similarity(
        current_dimensions: Dict[str, str],
        candidate_dimensions: Dict[str, str],
    ) -> Tuple[int, Dict[str, str]]:
        if not current_dimensions or not candidate_dimensions:
            return 0, {}

        matched_dimensions = {
            key: value
            for key, value in current_dimensions.items()
            if candidate_dimensions.get(key) == value
        }
        if not matched_dimensions:
            return 0, {}

        current_total = sum(DIMENSION_PRIORITY.get(key, 1) for key in current_dimensions.keys())
        matched_total = sum(DIMENSION_PRIORITY.get(key, 1) for key in matched_dimensions.keys())
        if current_total <= 0:
            return 0, {}
        return int(matched_total / current_total * 100), matched_dimensions

    @staticmethod
    def _get_match_reason(matched_dimensions: Dict[str, str], score: int) -> str:
        if score >= 90:
            return "关键事件"

        for key in ("service", "location", "resource_name", "item"):
            if key in matched_dimensions:
                return MATCH_REASON_MAP.get(key, "相关告警")
        return "相关告警"

    @staticmethod
    def _get_incidents_summary(alert: Alert) -> List[Dict[str, Any]]:
        return list(
            alert.incident_set.order_by("-updated_at", "-id").values(
                "id",
                "incident_id",
                "title",
            )
        )

    @staticmethod
    def _format_time_proximity(current_time, candidate_time) -> str:
        if not current_time or not candidate_time:
            return "--"

        total_seconds = abs(int((current_time - candidate_time).total_seconds()))
        if total_seconds < 60:
            return f"{total_seconds}秒内"
        if total_seconds < 3600:
            return f"{total_seconds // 60}分钟前"
        if total_seconds < 86400:
            return f"{total_seconds // 3600}小时前"
        return f"{total_seconds // 86400}天前"
