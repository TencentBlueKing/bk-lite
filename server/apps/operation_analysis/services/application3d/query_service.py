from __future__ import annotations

import base64
import binascii
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as datetime_timezone
from typing import Any

from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone

from apps.cmdb.services.application_resource_overview import ApplicationResourceOverviewService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.permission_utils import check_instance_permission, get_permissions_rules
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot, MonitorInstance
from apps.monitor.services.chart_unit import convert_snapshots_copy, resolve_chart_unit
from apps.monitor.views.monitor_alert import AlertPermissionMixin
from apps.operation_analysis.services.application3d.constants import (
    APPLICATION3D_ALARM_PAGE_SIZE,
    APPLICATION3D_ENTITY_BATCH_SIZE,
    APPLICATION3D_SAFETY_MAX_APPLICATIONS,
    FILTER_SYSTEM_STATUS,
)
from apps.operation_analysis.services.application3d.detail_fields import present_alert_dimensions, present_policy_thresholds
from apps.operation_analysis.services.application3d.errors import (
    Application3DCapacityExceeded,
    Application3DInvalidRequest,
    Application3DNotFound,
    Application3DSourceFailure,
)
from apps.operation_analysis.services.application3d.health import aggregate_application_health, unavailable_health
from apps.operation_analysis.services.application3d.metric_fields import (
    collect_policy_metric_ids,
    load_metrics_by_ids,
    present_alarm_metric_fields,
    resolve_policy_metric_display_name,
)
from apps.operation_analysis.services.application3d.notifications import summarize_notification
from apps.operation_analysis.services.application3d.presenters import (
    alert_duration_seconds,
    iso_datetime,
    present_alarm_list_item,
    present_application_properties,
)
from apps.operation_analysis.services.application3d.relations import project_application_hosts, project_application_systems
from apps.operation_analysis.services.application3d.severity import severity_from_monitor_level


class _AlertPolicyScope(AlertPermissionMixin):
    pass


@dataclass
class _ApplicationScope:
    """Shared Application→Host→Monitor mapping + accessible policies.

    Does not hold materialized MonitorAlert rows. Wall aggregates via DB
    values/Count; Detail pages via scoped cursor queries.
    """

    applications: list[dict[str, Any]]
    hosts_by_app: dict[str, list[dict[str, Any]]]
    policies: dict[int, Any]
    complete_apps: set[str]


class Application3DQueryService:
    """Permission-aware CMDB Application → Monitor query seam."""

    @classmethod
    def wall(cls, request, applied_filters: dict | None = None) -> dict[str, Any]:
        filters, allowed_values = cls._filter_definition()
        normalized_filters = cls._validate_applied_filters(applied_filters, allowed_values)
        applications = cls._visible_applications(request)

        selected_statuses = normalized_filters[FILTER_SYSTEM_STATUS]
        if selected_statuses:
            applications = cls._filter_applications_by_system_status(request, applications, set(selected_statuses))

        scope = cls._build_scope(request, applications)
        health_by_app = cls._wall_health_by_application(scope)
        items = [
            {
                "id": cls._instance_uuid(application),
                "name": cls._instance_name(application),
                "health": health_by_app[cls._instance_uuid(application)],
            }
            for application in applications
        ]
        return {
            "items": items,
            "filters": filters,
            "appliedFilters": normalized_filters,
            "refreshedAt": timezone.now().isoformat(),
            "capacity": {"actualCount": len(items), "supportedCount": None},
        }

    @classmethod
    def application_detail(cls, request, application_id: str) -> dict[str, Any]:
        application = cls._visible_application(request, application_id)
        scope = cls._build_scope(request, [application])
        app_id = cls._instance_uuid(application)
        health = cls._health_for_application(scope, app_id)

        if app_id not in scope.complete_apps:
            alarms: dict[str, Any] = {"state": "unavailable"}
        else:
            page_items, has_more = cls._paged_scoped_alerts(
                scope,
                app_id,
                cursor=(getattr(request, "data", None) or {}).get("cursor"),
            )
            page_policies = [scope.policies.get(alert.policy_id) for alert in page_items]
            metrics_by_id = load_metrics_by_ids(collect_policy_metric_ids(page_policies))
            alarms = {
                "state": "available",
                "activeAlarmCount": health["activeAlarmCount"],
                "severityCounts": health["severityCounts"],
                "noDataAlarmCount": health["noDataAlarmCount"],
                "highestSeverity": health["highestSeverity"],
                "items": [
                    present_alarm_list_item(
                        alert,
                        host=cls._host_for_alert(scope, app_id, alert),
                        policy=scope.policies.get(alert.policy_id),
                        metrics_by_id=metrics_by_id,
                    )
                    for alert in page_items
                ],
                "page": {
                    "nextCursor": cls._encode_cursor(page_items[-1]) if has_more and page_items else None,
                    "hasMore": has_more,
                },
            }

        attrs = ModelManage.search_model_attr("application") or []
        visible_fields = ApplicationResourceOverviewService._get_show_fields("application", request.user)
        return {
            "application": {
                "id": app_id,
                "name": cls._instance_name(application),
                "health": health,
                "properties": present_application_properties(
                    application,
                    attrs,
                    visible_fields=set(visible_fields) if visible_fields is not None else None,
                ),
            },
            "alarms": alarms,
            "refreshedAt": timezone.now().isoformat(),
        }

    @classmethod
    def alarm_detail(cls, request, application_id: str, alarm_id: str) -> dict[str, Any]:
        application = cls._visible_application(request, application_id)
        scope = cls._build_scope(request, [application])
        app_id = cls._instance_uuid(application)
        if app_id not in scope.complete_apps:
            raise Application3DNotFound("告警不存在")

        alert = cls._scoped_alert_or_404(scope, app_id, alarm_id)
        previous_id, next_id = cls._adjacent_scoped_alert_ids(scope, app_id, alert)
        policy = scope.policies.get(alert.policy_id)
        host = cls._host_for_alert(scope, app_id, alert)
        is_no_data = str(alert.alert_type).lower() == "no_data"
        alert_type = "no_data" if is_no_data else "alert"
        monitor_object = getattr(policy, "monitor_object", None)
        return {
            "applicationId": app_id,
            "alarm": {
                "id": str(alert.id),
                "content": alert.content or "",
                "severity": severity_from_monitor_level(alert.level),
                "alertType": alert_type,
                "isNoData": is_no_data,
                "occurredAt": iso_datetime(alert.start_event_time),
                "status": "new",
                "durationSeconds": alert_duration_seconds(alert),
                "resource": {
                    "id": str(host.get("inst_uuid") or ""),
                    "name": str(host.get("inst_name") or host.get("inst_uuid") or ""),
                },
                "dimensions": present_alert_dimensions(getattr(alert, "dimensions", None)),
                "metric": present_alarm_metric_fields(
                    alert,
                    policy,
                    unit=cls._policy_chart_unit(policy) or None,
                ),
                "monitorContext": {
                    "objectName": str(getattr(monitor_object, "name", "") or ""),
                    "instanceName": alert.monitor_instance_name or "",
                },
                "policy": {
                    "id": str(alert.policy_id),
                    "name": str(getattr(policy, "name", "") or ""),
                },
                "notification": summarize_notification(
                    policy_notice_configured=bool(getattr(policy, "notice", False)),
                    notice_logs=alert.notice_logs,
                ),
            },
            "navigation": {
                "previousAlarmId": previous_id,
                "nextAlarmId": next_id,
                "order": "start_event_time_desc_id_desc",
            },
        }

    @classmethod
    def metric_series(cls, request, application_id: str, alarm_id: str) -> dict[str, Any]:
        try:
            detail_scope = cls._scope_and_alert(request, application_id, alarm_id)
        except Application3DNotFound:
            return cls._metric_result(application_id, alarm_id, "permission_denied")
        alert, policy = detail_scope

        snapshot = MonitorAlertMetricSnapshot.objects.filter(
            alert_id=alert.id,
            policy_id=alert.policy_id,
        ).first()
        if snapshot is None:
            return cls._metric_result(application_id, alarm_id, "no_snapshot")
        try:
            raw_snapshots = snapshot.snapshots
            if raw_snapshots is None:
                return cls._metric_result(application_id, alarm_id, "failure", error_code="metric_source_failure")
            chart_unit = cls._policy_chart_unit(policy)
            source_unit = getattr(policy, "calculation_unit", "") or getattr(policy, "metric_unit", "")
            converted = convert_snapshots_copy(raw_snapshots, source_unit or chart_unit, chart_unit)
            points = cls._snapshot_points(converted)
        except Exception:
            logger.exception("application3D metric snapshot conversion failed for alert %s", alarm_id)
            return cls._metric_result(application_id, alarm_id, "failure", error_code="metric_source_failure")

        return {
            "applicationId": str(application_id),
            "alarmId": str(alarm_id),
            "state": "available",
            "series": [
                {
                    "name": resolve_policy_metric_display_name(policy),
                    "unit": chart_unit or None,
                    "points": points,
                }
            ],
            "thresholds": present_policy_thresholds(policy),
            "alarmMarker": (
                {
                    "timestamp": alert.start_event_time.isoformat(),
                    "label": alert.content or "",
                }
                if alert.start_event_time
                else None
            ),
        }

    @classmethod
    def _visible_applications(cls, request) -> list[dict[str, Any]]:
        permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="application")
        applications, count = InstanceManage.instance_list(
            model_id="application",
            params=[],
            page=1,
            page_size=APPLICATION3D_SAFETY_MAX_APPLICATIONS + 1,
            order="inst_name",
            permission_map=permission_map,
            creator=request.user.username,
        )
        actual_count = int(count)
        if actual_count > APPLICATION3D_SAFETY_MAX_APPLICATIONS:
            raise Application3DCapacityExceeded(
                actual_count=actual_count,
                supported_count=APPLICATION3D_SAFETY_MAX_APPLICATIONS,
            )
        return list(applications or [])

    @classmethod
    def _visible_application(cls, request, application_id: str) -> dict[str, Any]:
        if not application_id:
            raise Application3DInvalidRequest("application_id 不能为空")
        permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="application")
        applications, _ = InstanceManage.instance_list(
            model_id="application",
            params=[{"field": "inst_uuid", "type": "str=", "value": str(application_id)}],
            page=1,
            page_size=2,
            order="",
            permission_map=permission_map,
            creator=request.user.username,
        )
        application = next((item for item in applications or [] if cls._instance_uuid(item) == str(application_id)), None)
        if application is None:
            raise Application3DNotFound("应用不存在")
        return application

    @classmethod
    def _filter_definition(cls) -> tuple[list[dict[str, Any]], set[str]]:
        attrs = ModelManage.search_model_attr("system") or []
        status_attr = next((attr for attr in attrs if attr.get("attr_id") == "status"), {})
        options = cls._enum_options(status_attr.get("option"))
        definition = {
            "id": FILTER_SYSTEM_STATUS,
            "label": str(status_attr.get("attr_name") or "应用系统运行状态"),
            "type": "multiple",
            "options": options,
        }
        return [definition], {item["value"] for item in options}

    @staticmethod
    def _enum_options(raw_option: Any) -> list[dict[str, str]]:
        if isinstance(raw_option, dict):
            raw_option = raw_option.get("option") or raw_option.get("options") or []
        if not isinstance(raw_option, list):
            return []
        result = []
        for item in raw_option:
            if not isinstance(item, dict):
                continue
            value = item.get("id", item.get("value"))
            if value in (None, ""):
                continue
            result.append({"value": str(value), "label": str(item.get("name") or item.get("label") or value)})
        return result

    @classmethod
    def _validate_applied_filters(cls, applied_filters: dict | None, allowed_values: set[str]) -> dict[str, list[str]]:
        if applied_filters is None:
            return {FILTER_SYSTEM_STATUS: []}
        if not isinstance(applied_filters, dict) or set(applied_filters) - {FILTER_SYSTEM_STATUS}:
            raise Application3DInvalidRequest("存在不支持的筛选条件")
        values = applied_filters.get(FILTER_SYSTEM_STATUS, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise Application3DInvalidRequest("system_status 必须为字符串数组")
        normalized = list(dict.fromkeys(values))
        if set(normalized) - allowed_values:
            raise Application3DInvalidRequest("system_status 包含非法值")
        return {FILTER_SYSTEM_STATUS: normalized}

    @classmethod
    def _filter_applications_by_system_status(
        cls,
        request,
        applications: list[dict[str, Any]],
        selected: set[str],
    ) -> list[dict[str, Any]]:
        app_ids = [cls._instance_uuid(item) for item in applications]
        systems_by_app = project_application_systems(app_ids)
        system_ids = sorted({system_id for values in systems_by_app.values() for system_id in values})
        if not system_ids:
            return []
        permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="system")
        systems = []
        for offset in range(0, len(system_ids), APPLICATION3D_ENTITY_BATCH_SIZE):
            batch = system_ids[offset : offset + APPLICATION3D_ENTITY_BATCH_SIZE]
            batch_systems, _ = InstanceManage.instance_list(
                model_id="system",
                params=[{"field": "inst_uuid", "type": "str[]", "value": batch}],
                page=1,
                page_size=APPLICATION3D_ENTITY_BATCH_SIZE,
                order="",
                permission_map=permission_map,
                creator=request.user.username,
            )
            systems.extend(batch_systems or [])
        status_by_system = {cls._instance_uuid(system): cls._status_values(system.get("status")) for system in systems or []}
        return [
            application
            for application in applications
            if any(status_by_system.get(system_id, set()) & selected for system_id in systems_by_app.get(cls._instance_uuid(application), []))
        ]

    @staticmethod
    def _status_values(raw: Any) -> set[str]:
        """
        CMDB enum fields are stored as lists even for single-select
        (e.g. status=['1']). Also accept plain strings for older rows/tests.
        """
        if raw in (None, ""):
            return set()
        if isinstance(raw, (list, tuple, set)):
            return {str(item) for item in raw if item not in (None, "")}
        return {str(raw)}

    @classmethod
    def _build_scope(cls, request, applications: list[dict[str, Any]]) -> _ApplicationScope:
        app_ids = [cls._instance_uuid(item) for item in applications]
        if not app_ids:
            return _ApplicationScope([], {}, {}, set())
        try:
            host_ids_by_app, integrity_failures = project_application_hosts(app_ids)
            all_host_ids = sorted({host_id for host_ids in host_ids_by_app.values() for host_id in host_ids})
            visible_hosts = cls._visible_hosts(request, all_host_ids)
            visible_host_map = {cls._instance_uuid(item): item for item in visible_hosts}
            hosts_by_app = {
                app_id: [visible_host_map[host_id] for host_id in host_ids if host_id in visible_host_map]
                for app_id, host_ids in host_ids_by_app.items()
            }
            complete_apps = {
                app_id
                for app_id, expected_ids in host_ids_by_app.items()
                if app_id not in integrity_failures
                and len(hosts_by_app.get(app_id, [])) == len(expected_ids)
                and all(host.get("monitor_id") not in (None, "") for host in hosts_by_app.get(app_id, []))
            }

            monitor_ids = {str(host["monitor_id"]) for app_id in complete_apps for host in hosts_by_app.get(app_id, [])}
            authorized_monitor_ids = cls._authorized_monitor_ids(request, monitor_ids)
            for app_id in list(complete_apps):
                expected_monitor_ids = {str(host["monitor_id"]) for host in hosts_by_app.get(app_id, [])}
                if not expected_monitor_ids.issubset(authorized_monitor_ids):
                    complete_apps.remove(app_id)

            scoped_monitor_ids = {str(host["monitor_id"]) for app_id in complete_apps for host in hosts_by_app.get(app_id, [])}
            # Discover referenced policies without materializing alert rows.
            referenced_policy_ids = set(
                MonitorAlert.objects.filter(
                    status="new",
                    monitor_instance_id__in=scoped_monitor_ids,
                )
                .values_list("policy_id", flat=True)
                .distinct()
            )
            policies = cls._accessible_policies(request, referenced_policy_ids)
            policy_ids = set(policies.keys())
            # Policy-incomplete monitors must not produce forged normal/partial counts.
            monitors_with_hidden_policy = set(
                MonitorAlert.objects.filter(
                    status="new",
                    monitor_instance_id__in=scoped_monitor_ids,
                )
                .exclude(policy_id__in=policy_ids)
                .values_list("monitor_instance_id", flat=True)
                .distinct()
            )
            if monitors_with_hidden_policy:
                for app_id in list(complete_apps):
                    app_monitors = {str(host["monitor_id"]) for host in hosts_by_app.get(app_id, [])}
                    if app_monitors & {str(item) for item in monitors_with_hidden_policy}:
                        complete_apps.remove(app_id)

            return _ApplicationScope(applications, hosts_by_app, policies, complete_apps)
        except Exception as exc:
            logger.exception("application3D scope query failed")
            raise Application3DSourceFailure("应用监控数据查询失败") from exc

    @classmethod
    def _visible_hosts(cls, request, host_ids: list[str]) -> list[dict[str, Any]]:
        if not host_ids:
            return []
        permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="host")
        result = []
        for index in range(0, len(host_ids), APPLICATION3D_ENTITY_BATCH_SIZE):
            batch = host_ids[index : index + APPLICATION3D_ENTITY_BATCH_SIZE]
            hosts, _ = InstanceManage.instance_list(
                model_id="host",
                params=[{"field": "inst_uuid", "type": "str[]", "value": batch}],
                page=1,
                page_size=APPLICATION3D_ENTITY_BATCH_SIZE,
                order="",
                permission_map=permission_map,
                creator=request.user.username,
            )
            result.extend(hosts or [])
        return result

    @classmethod
    def _authorized_monitor_ids(cls, request, candidate_ids: set[str]) -> set[str]:
        if not candidate_ids:
            return set()
        scope = resolve_current_team_data_scope(request)
        permissions_result = get_permissions_rules(
            request.user,
            scope.current_team,
            "monitor",
            PermissionConstants.INSTANCE_MODULE,
            include_children=scope.include_children,
        )
        if not request.user.is_superuser and not isinstance(permissions_result, dict):
            return set()
        permission_data = (permissions_result or {}).get("data", {})
        if not isinstance(permission_data, dict):
            permission_data = {}
        result = set()
        ordered_ids = sorted(candidate_ids)
        for offset in range(0, len(ordered_ids), APPLICATION3D_ENTITY_BATCH_SIZE):
            instances = (
                MonitorInstance.objects.filter(
                    id__in=ordered_ids[offset : offset + APPLICATION3D_ENTITY_BATCH_SIZE],
                    is_deleted=False,
                    is_active=True,
                    monitorinstanceorganization__organization__in=list(scope.data_team_ids),
                )
                .select_related("monitor_object")
                .prefetch_related("monitorinstanceorganization_set")
                .distinct()
            )
            for instance in instances:
                teams = {item.organization for item in instance.monitorinstanceorganization_set.all()}
                if request.user.is_superuser or check_instance_permission(
                    str(instance.monitor_object_id),
                    instance.id,
                    teams,
                    permission_data,
                    list(scope.data_team_ids),
                ):
                    result.add(str(instance.id))
        return result

    @staticmethod
    def _accessible_policies(request, policy_ids: set[int]) -> dict[int, Any]:
        if not policy_ids:
            return {}
        helper = _AlertPolicyScope()
        queryset = helper.get_accessible_policy_queryset(request).filter(id__in=policy_ids).select_related("monitor_object")
        return {policy.id: policy for policy in queryset}

    @classmethod
    def _monitor_ids_for_app(cls, scope: _ApplicationScope, app_id: str) -> set[str]:
        return {str(host.get("monitor_id")) for host in scope.hosts_by_app.get(app_id, []) if host.get("monitor_id")}

    @classmethod
    def _scoped_active_alerts_qs(cls, scope: _ApplicationScope, monitor_ids: set[str]) -> QuerySet:
        if not monitor_ids or not scope.policies:
            return MonitorAlert.objects.none()
        return MonitorAlert.objects.filter(
            status="new",
            monitor_instance_id__in=monitor_ids,
            policy_id__in=scope.policies.keys(),
        )

    @classmethod
    def _ordered_scoped_alerts_qs(cls, scope: _ApplicationScope, app_id: str) -> QuerySet:
        # Match prior Python key=(start_event_time or datetime.min, id) reverse=True:
        # null start times sort last in descending order.
        return cls._scoped_active_alerts_qs(scope, cls._monitor_ids_for_app(scope, app_id)).order_by(
            F("start_event_time").desc(nulls_last=True),
            "-id",
        )

    @classmethod
    def _grouped_alert_counts_by_monitor(
        cls,
        scope: _ApplicationScope,
        monitor_ids: set[str],
    ) -> list[dict[str, Any]]:
        """One/few bounded GROUP BY queries — never fan out per Application."""
        if not monitor_ids or not scope.policies:
            return []
        rows: list[dict[str, Any]] = []
        ordered_ids = sorted(monitor_ids)
        for offset in range(0, len(ordered_ids), APPLICATION3D_ENTITY_BATCH_SIZE):
            batch = set(ordered_ids[offset : offset + APPLICATION3D_ENTITY_BATCH_SIZE])
            rows.extend(cls._scoped_active_alerts_qs(scope, batch).values("monitor_instance_id", "alert_type", "level").annotate(count=Count("id")))
        return rows

    @classmethod
    def _wall_health_by_application(cls, scope: _ApplicationScope) -> dict[str, dict[str, Any]]:
        """
        Wall health for all Applications in scope.

        Complete apps share one/few MonitorAlert aggregation queries keyed by
        monitor_instance_id; grouped rows are distributed in memory. Shared Hosts
        contribute to every linked Application, but each Application counts each
        monitor at most once. Incomplete apps stay unknown/unavailable.
        """
        health_by_app: dict[str, dict[str, Any]] = {}
        monitors_by_complete_app: dict[str, set[str]] = {}
        for application in scope.applications:
            app_id = cls._instance_uuid(application)
            if app_id not in scope.complete_apps:
                health_by_app[app_id] = unavailable_health()
                continue
            monitors_by_complete_app[app_id] = cls._monitor_ids_for_app(scope, app_id)

        union_monitor_ids = {monitor_id for monitor_ids in monitors_by_complete_app.values() for monitor_id in monitor_ids}
        grouped_rows = cls._grouped_alert_counts_by_monitor(scope, union_monitor_ids)
        rows_by_monitor: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in grouped_rows:
            rows_by_monitor[str(row["monitor_instance_id"])].append(row)

        for app_id, monitor_ids in monitors_by_complete_app.items():
            app_rows: list[dict[str, Any]] = []
            for monitor_id in monitor_ids:
                app_rows.extend(rows_by_monitor.get(monitor_id, []))
            health_by_app[app_id] = aggregate_application_health(app_rows)
        return health_by_app

    @classmethod
    def _health_for_application(cls, scope: _ApplicationScope, app_id: str) -> dict[str, Any]:
        """Detail/single-app health; same filter + aggregate semantics as Wall distribution."""
        if app_id not in scope.complete_apps:
            return unavailable_health()
        monitor_ids = cls._monitor_ids_for_app(scope, app_id)
        rows = cls._grouped_alert_counts_by_monitor(scope, monitor_ids)
        # Collapse monitor-keyed groups to the same (alert_type, level, count) shape Wall uses.
        collapsed: dict[tuple[str, str], int] = defaultdict(int)
        for row in rows:
            key = (str(row.get("alert_type") or ""), str(row.get("level") or ""))
            collapsed[key] += int(row.get("count") or 0)
        return aggregate_application_health(
            [{"alert_type": alert_type, "level": level, "count": count} for (alert_type, level), count in collapsed.items()]
        )

    @classmethod
    def _paged_scoped_alerts(
        cls,
        scope: _ApplicationScope,
        app_id: str,
        *,
        cursor: str | None,
    ) -> tuple[list[MonitorAlert], bool]:
        queryset = cls._apply_alert_cursor(cls._ordered_scoped_alerts_qs(scope, app_id), cursor)
        page_items = list(queryset[: APPLICATION3D_ALARM_PAGE_SIZE + 1])
        has_more = len(page_items) > APPLICATION3D_ALARM_PAGE_SIZE
        return page_items[:APPLICATION3D_ALARM_PAGE_SIZE], has_more

    @classmethod
    def _scoped_alert_or_404(cls, scope: _ApplicationScope, app_id: str, alarm_id: str) -> MonitorAlert:
        alert = cls._ordered_scoped_alerts_qs(scope, app_id).filter(id=alarm_id).first()
        if alert is None:
            raise Application3DNotFound("告警不存在")
        return alert

    @classmethod
    def _adjacent_scoped_alert_ids(
        cls,
        scope: _ApplicationScope,
        app_id: str,
        alert: MonitorAlert,
    ) -> tuple[str | None, str | None]:
        base = cls._scoped_active_alerts_qs(scope, cls._monitor_ids_for_app(scope, app_id))
        started = alert.start_event_time
        # previous = immediate more-recent neighbor in desc(nulls_last), -id order;
        # next = immediate older neighbor. Among "before" set, take first in the reverse
        # order asc(nulls_first), id — not .last(), which would jump to the newest alert.
        if started is None:
            more_recent = base.filter(Q(start_event_time__isnull=False) | Q(start_event_time__isnull=True, id__gt=alert.id))
            previous = more_recent.order_by(F("start_event_time").asc(nulls_first=True), "id").first()
            next_alert = base.filter(start_event_time__isnull=True, id__lt=alert.id).order_by("-id").first()
        else:
            more_recent = base.filter(Q(start_event_time__gt=started) | Q(start_event_time=started, id__gt=alert.id))
            previous = more_recent.order_by(F("start_event_time").asc(nulls_first=True), "id").first()
            older = base.filter(Q(start_event_time__lt=started) | Q(start_event_time=started, id__lt=alert.id) | Q(start_event_time__isnull=True))
            next_alert = older.order_by(F("start_event_time").desc(nulls_last=True), "-id").first()
        return (
            str(previous.id) if previous is not None else None,
            str(next_alert.id) if next_alert is not None else None,
        )

    @staticmethod
    def _encode_cursor(alert: MonitorAlert) -> str:
        payload = [iso_datetime(alert.start_event_time), str(alert.id)]
        return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")

    @classmethod
    def _apply_alert_cursor(cls, queryset: QuerySet, cursor: str | None) -> QuerySet:
        if not cursor:
            return queryset
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode((cursor + padding).encode()).decode())
            if not isinstance(payload, list) or len(payload) != 2:
                raise ValueError
            cursor_time_raw, cursor_id = payload[0], str(payload[1])
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise Application3DInvalidRequest("cursor 无效") from exc

        if not queryset.filter(id=cursor_id).exists():
            raise Application3DInvalidRequest("cursor 已失效")

        if cursor_time_raw in (None, ""):
            return queryset.filter(start_event_time__isnull=True, id__lt=cursor_id)

        try:
            cursor_time = datetime.fromisoformat(str(cursor_time_raw))
        except ValueError as exc:
            raise Application3DInvalidRequest("cursor 无效") from exc

        return queryset.filter(
            Q(start_event_time__lt=cursor_time) | Q(start_event_time=cursor_time, id__lt=cursor_id) | Q(start_event_time__isnull=True)
        )

    @classmethod
    def _host_for_alert(cls, scope: _ApplicationScope, app_id: str, alert: MonitorAlert) -> dict[str, Any]:
        return next(
            (host for host in scope.hosts_by_app.get(app_id, []) if str(host.get("monitor_id")) == str(alert.monitor_instance_id)),
            {},
        )

    @classmethod
    def _scope_and_alert(cls, request, application_id: str, alarm_id: str) -> tuple[MonitorAlert, Any]:
        application = cls._visible_application(request, application_id)
        scope = cls._build_scope(request, [application])
        app_id = cls._instance_uuid(application)
        if app_id not in scope.complete_apps:
            raise Application3DNotFound("告警不存在")
        alert = cls._scoped_alert_or_404(scope, app_id, alarm_id)
        return alert, scope.policies.get(alert.policy_id)

    @staticmethod
    def _policy_chart_unit(policy: Any) -> str:
        if policy is None:
            return ""
        return resolve_chart_unit(policy.metric_unit, policy.calculation_unit, policy.threshold_unit)

    @staticmethod
    def _snapshot_points(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: dict[str, float | None] = {}
        for snapshot in snapshots:
            raw_data = snapshot.get("raw_data")
            if not isinstance(raw_data, dict):
                continue
            for point in raw_data.get("values") or []:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                timestamp = point[0]
                if isinstance(timestamp, (int, float)):
                    value = float(timestamp)
                    if value > 10**12:
                        value /= 1000
                    timestamp = datetime.fromtimestamp(value, tz=datetime_timezone.utc).isoformat()
                else:
                    timestamp = str(timestamp)
                try:
                    numeric_value = None if point[1] is None else float(point[1])
                except (TypeError, ValueError):
                    numeric_value = None
                points[timestamp] = numeric_value
        return [{"timestamp": timestamp, "value": value} for timestamp, value in sorted(points.items())]

    @staticmethod
    def _metric_result(
        application_id: str,
        alarm_id: str,
        state: str,
        *,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "applicationId": str(application_id),
            "alarmId": str(alarm_id),
            "state": state,
            "series": None,
            "thresholds": [],
            "alarmMarker": None,
        }
        if error_code:
            result["errorCode"] = error_code
        return result

    @staticmethod
    def _instance_uuid(instance: dict[str, Any]) -> str:
        return str(instance.get("inst_uuid") or "")

    @classmethod
    def _instance_name(cls, instance: dict[str, Any]) -> str:
        return str(instance.get("inst_name") or cls._instance_uuid(instance))
