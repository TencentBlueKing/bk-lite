import copy
import json
from datetime import datetime, timezone

from django.db import transaction
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_policy import MonitorPolicyFilter
from apps.monitor.models import PolicyOrganization, MonitorAlert
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.alert_lifecycle_notify import (
    AlertLifecycleNotifier,
    NOTIFY_SCOPE_ALERT_CENTER_ONLY,
    NOTIFY_SCOPE_ALL_CONFIGURED,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.policy_bulk import build_bulk_policy_payloads
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.services.policy_preview import PolicyPreviewService
from apps.monitor.utils.pagination import parse_page_params
from config.drf.pagination import CustomPageNumberPagination
from apps.core.utils.team_utils import get_current_team


class MonitorPolicyViewSet(viewsets.ModelViewSet):
    queryset = MonitorPolicy.objects.all()
    serializer_class = MonitorPolicySerializer
    filterset_class = MonitorPolicyFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get("monitor_object_id", None)

        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            get_current_team(request),
            "monitor",
            f"{PermissionConstants.POLICY_MODULE}.{monitor_object_id}",
            include_children=include_children,
        )
        qs = permission_filter(
            MonitorPolicy,
            permission,
            team_key="policyorganization__organization__in",
            id_key="id__in",
        )

        queryset = self.filter_queryset(qs)

        queryset = queryset.distinct()

        # 获取分页参数
        page, page_size = parse_page_params(request.GET, default_page=1, default_page_size=10)

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        for instance_info in results:
            if instance_info["id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

    def create(self, request, *args, **kwargs):
        request.data["created_by"] = request.user.username
        response = super().create(request, *args, **kwargs)
        policy_id = response.data["id"]
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        schedule = request.data.get("schedule")
        organizations = request.data.get("organizations", [])
        self.update_or_create_task(policy_id, schedule)
        self.update_policy_organizations(policy_id, organizations)
        if self.is_no_data_alert_enabled(policy):
            self.update_policy_baselines(policy_id, policy.enable_alerts)
        return response

    def update(self, request, *args, **kwargs):
        request.data["updated_by"] = request.user.username
        policy_id = kwargs["pk"]

        # 获取策略变更前的 enable 状态和无数据基准语义
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        old_enable = policy.enable if policy else None
        old_baseline_state = self.get_baseline_state(policy)

        with transaction.atomic():
            response = super().update(request, *args, **kwargs)
            updated_policy = MonitorPolicy.objects.filter(id=policy_id).first()

            schedule = request.data.get("schedule")
            if schedule:
                self.update_or_create_task(policy_id, schedule)
            organizations = request.data.get("organizations", [])
            if organizations:
                self.update_policy_organizations(policy_id, organizations)
            if self.should_update_policy_baselines(policy, old_baseline_state, updated_policy):
                self.update_policy_baselines(
                    policy_id,
                    updated_policy.enable_alerts,
                    operator=request.user.username,
                    reset_active_no_data_alerts=self.baseline_state_changed(old_baseline_state, updated_policy),
                )

            self.close_active_threshold_alerts_for_policy_config_change(
                policy,
                old_baseline_state,
                updated_policy,
                request.user.username,
            )

            # 处理 enable 字段变更
            if "enable" in request.data and policy and updated_policy:
                new_enable = updated_policy.enable
                self.handle_policy_enable_change(policy_id, old_enable, new_enable)

        return response

    def partial_update(self, request, *args, **kwargs):
        request.data["updated_by"] = request.user.username
        policy_id = kwargs["pk"]

        # 获取策略变更前的 enable 状态和无数据基准语义
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        old_enable = policy.enable if policy else None
        old_baseline_state = self.get_baseline_state(policy)

        with transaction.atomic():
            response = super().partial_update(request, *args, **kwargs)
            updated_policy = MonitorPolicy.objects.filter(id=policy_id).first()

            schedule = request.data.get("schedule")
            if schedule:
                self.update_or_create_task(policy_id, schedule)
            organizations = request.data.get("organizations", [])
            if organizations:
                self.update_policy_organizations(policy_id, organizations)
            if self.should_update_policy_baselines(policy, old_baseline_state, updated_policy):
                self.update_policy_baselines(
                    policy_id,
                    updated_policy.enable_alerts,
                    operator=request.user.username,
                    reset_active_no_data_alerts=self.baseline_state_changed(old_baseline_state, updated_policy),
                )

            self.close_active_threshold_alerts_for_policy_config_change(
                policy,
                old_baseline_state,
                updated_policy,
                request.user.username,
            )

            # 处理 enable 字段变更
            if "enable" in request.data and policy and updated_policy:
                new_enable = updated_policy.enable
                self.handle_policy_enable_change(policy_id, old_enable, new_enable)

        return response

    def destroy(self, request, *args, **kwargs):
        policy_id = kwargs["pk"]
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        if policy:
            PolicyBaselineService(policy).clear()
            alerts_to_close = list(MonitorAlert.objects.filter(policy_id=policy_id, status="new"))
            self.close_alerts(policy, alerts_to_close, request.user.username, "policy_deleted")
        PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").delete()
        PolicyOrganization.objects.filter(policy_id=policy_id).delete()
        return super().destroy(request, *args, **kwargs)

    def is_no_data_alert_enabled(self, policy):
        return bool(policy and AlertConstants.NO_DATA in (policy.enable_alerts or []))

    def _normalize_baseline_source(self, source):
        normalized_source = copy.deepcopy(source) if source else {}
        if not isinstance(normalized_source, dict):
            return normalized_source

        source_values = normalized_source.get("values")
        if isinstance(source_values, list):
            normalized_source["values"] = sorted(
                source_values,
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
            )

        return normalized_source

    def get_baseline_state(self, policy):
        if not policy:
            return {}
        return {
            "source": self._normalize_baseline_source(policy.source),
            "group_by": copy.deepcopy(policy.group_by),
            "query_condition": copy.deepcopy(policy.query_condition),
            "monitor_object": policy.monitor_object_id,
            "collect_type": policy.collect_type,
        }

    def baseline_state_changed(self, old_state, policy):
        if not old_state or not policy:
            return False
        return old_state != self.get_baseline_state(policy)

    def should_update_policy_baselines(self, old_policy, old_state, policy):
        if not policy:
            return False

        old_no_data_enabled = self.is_no_data_alert_enabled(old_policy)
        new_no_data_enabled = self.is_no_data_alert_enabled(policy)
        if not old_no_data_enabled and not new_no_data_enabled:
            return False
        if old_no_data_enabled != new_no_data_enabled:
            return True
        return self.baseline_state_changed(old_state, policy)

    def get_policy_config_change_reason(self, old_state, policy):
        if not old_state or not policy:
            return ""

        new_state = self.get_baseline_state(policy)
        if old_state.get("source") != new_state.get("source"):
            return "policy_scope_changed"
        if old_state.get("group_by") != new_state.get("group_by"):
            return "policy_group_by_changed"
        if old_state.get("query_condition") != new_state.get("query_condition"):
            return "policy_query_condition_changed"
        if old_state.get("monitor_object") != new_state.get("monitor_object") or old_state.get("collect_type") != new_state.get("collect_type"):
            return "policy_monitor_target_changed"
        return ""

    def close_active_threshold_alerts_for_policy_config_change(self, old_policy, old_state, policy, operator):
        reason = self.get_policy_config_change_reason(old_state, policy)
        if not reason or not old_policy or not policy:
            return

        alerts_to_close = list(
            MonitorAlert.objects.filter(
                policy_id=old_policy.id,
                alert_type="alert",
                status="new",
            )
        )
        self.close_alerts(
            policy,
            alerts_to_close,
            operator,
            reason,
            notify_scope=NOTIFY_SCOPE_ALERT_CENTER_ONLY,
        )

    def update_policy_baselines(
        self,
        policy_id,
        enable_alerts,
        operator="system",
        reset_active_no_data_alerts=False,
    ):
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        if not policy:
            return

        baseline_service = PolicyBaselineService(policy)
        if AlertConstants.NO_DATA in enable_alerts:
            if reset_active_no_data_alerts:
                self.close_active_no_data_alerts(policy, operator, "policy_baseline_changed")
            baseline_service.refresh()
        else:
            self.close_active_no_data_alerts(policy, operator, "no_data_disabled")
            baseline_service.clear()

    def close_alerts(self, policy, alerts_to_close, operator, reason, notify_scope=NOTIFY_SCOPE_ALL_CONFIGURED):
        if not alerts_to_close:
            return

        now = datetime.now(timezone.utc)
        operation_log = {
            "action": "closed",
            "reason": reason,
            "operator": operator,
            "time": now.isoformat(),
        }
        for alert in alerts_to_close:
            alert.status = "closed"
            alert.end_event_time = now
            alert.operator = operator
            alert.operation_logs = (alert.operation_logs or []) + [operation_log]
            alert.alert_center_notified = False
        MonitorAlert.objects.bulk_update(
            alerts_to_close,
            fields=["status", "end_event_time", "operator", "operation_logs", "alert_center_notified"],
        )
        if policy and notify_scope:
            AlertLifecycleNotifier(policy).notify_alerts(
                alerts_to_close,
                action="closed",
                operator=operator,
                reason=reason,
                notify_scope=notify_scope,
            )

    def close_active_no_data_alerts(self, policy, operator, reason):
        alerts_to_close = list(
            MonitorAlert.objects.filter(
                policy_id=policy.id,
                alert_type="no_data",
                status="new",
            )
        )
        self.close_alerts(policy, alerts_to_close, operator, reason)

    def handle_policy_enable_change(self, policy_id, old_enable, new_enable):
        if old_enable == new_enable:
            return

        if old_enable and not new_enable:
            policy = MonitorPolicy.objects.filter(id=policy_id).first()
            alerts_to_close = list(MonitorAlert.objects.filter(policy_id=policy_id, status="new"))
            self.close_alerts(policy, alerts_to_close, "system", "policy_disabled")
        elif not old_enable and new_enable:
            MonitorPolicy.objects.filter(id=policy_id).update(last_run_time=datetime.now(timezone.utc))

    def format_crontab(self, schedule):
        """
        将 schedule 格式化为 CrontabSchedule 实例
        """
        from django.utils import timezone

        schedule_type = schedule.get("type")
        value = schedule.get("value")
        current_tz = timezone.get_current_timezone()

        if schedule_type == "min":
            return CrontabSchedule.objects.get_or_create(
                minute=f"*/{value}",
                hour="*",
                day_of_month="*",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        elif schedule_type == "hour":
            return CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=f"*/{value}",
                day_of_month="*",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        elif schedule_type == "day":
            return CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=0,
                day_of_month=f"*/{value}",
                month_of_year="*",
                day_of_week="*",
                timezone=current_tz,
            )[0]
        else:
            raise BaseAppException("Invalid schedule type")

    def update_or_create_task(self, policy_id, schedule):
        task_name = f"scan_policy_task_{policy_id}"

        # 删除旧的定时任务
        PeriodicTask.objects.filter(name=task_name).delete()

        # 解析 schedule，并创建相应的调度
        format_crontab = self.format_crontab(schedule)
        # 创建新的 PeriodicTask
        PeriodicTask.objects.create(
            name=task_name,
            task="apps.monitor.tasks.monitor_policy.scan_policy_task",
            args=json.dumps([policy_id]),  # 任务参数，使用 JSON 格式存储
            crontab=format_crontab,
            enabled=True,
        )

    def update_policy_organizations(self, policy_id, organizations):
        """更新策略的组织"""
        old_organizations = PolicyOrganization.objects.filter(policy_id=policy_id)
        old_set = set([org.organization for org in old_organizations])
        new_set = set(organizations)
        # 删除不存在的组织
        delete_set = old_set - new_set
        PolicyOrganization.objects.filter(policy_id=policy_id, organization__in=delete_set).delete()
        # 添加新的组织
        create_set = new_set - old_set
        create_objs = [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in create_set]
        PolicyOrganization.objects.bulk_create(create_objs, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

    @action(methods=["post"], detail=False, url_path="template")
    def template(self, request):
        data = PolicyService.get_policy_templates(request.data["monitor_object_name"])
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="template/monitor_object")
    def template_monitor_object(self, request):
        data = PolicyService.get_policy_templates_monitor_object()
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="bulk_create_from_templates")
    def bulk_create_from_templates(self, request):
        monitor_object_id = request.data.get("monitor_object")
        templates = request.data.get("templates") or []
        asset_ids = request.data.get("asset_ids") or []
        config = request.data.get("config") or {}
        if not monitor_object_id:
            raise BaseAppException("monitor_object 不能为空")
        if not templates:
            raise BaseAppException("templates 不能为空")
        if not asset_ids:
            raise BaseAppException("asset_ids 不能为空")

        assets = self.get_bulk_policy_assets(monitor_object_id, asset_ids)
        enriched_templates = self.enrich_bulk_policy_templates(monitor_object_id, templates)
        payloads = build_bulk_policy_payloads(
            monitor_object_id=int(monitor_object_id),
            templates=enriched_templates,
            assets=assets,
            config=config,
        )
        created = []
        with transaction.atomic():
            for payload in payloads:
                payload["created_by"] = request.user.username
                payload["updated_by"] = request.user.username
                payload["domain"] = getattr(request.user, "domain", "domain.com")
                payload["updated_by_domain"] = getattr(request.user, "domain", "domain.com")
                serializer = self.get_serializer(data=payload)
                serializer.is_valid(raise_exception=True)
                policy = serializer.save()
                created.append(policy)
                self.update_or_create_task(policy.id, payload["schedule"])
                self.update_policy_organizations(policy.id, payload.get("organizations", []))
                if self.is_no_data_alert_enabled(policy):
                    self.update_policy_baselines(policy.id, policy.enable_alerts)

        return WebUtils.response_success(
            {
                "created_count": len(created),
                "policy_ids": [policy.id for policy in created],
            }
        )

    @action(methods=["post"], detail=False, url_path="preview")
    def preview(self, request):
        data = PolicyPreviewService(request.data).preview()
        return WebUtils.response_success(data)

    def get_bulk_policy_assets(self, monitor_object_id, asset_ids):
        from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization

        normalized_ids = [str(asset_id) for asset_id in asset_ids if asset_id not in (None, "")]
        if not normalized_ids:
            return []
        instances = list(
            MonitorInstance.objects.filter(
                id__in=normalized_ids,
                monitor_object_id=monitor_object_id,
                is_deleted=False,
            ).values("id")
        )
        found_ids = {item["id"] for item in instances}
        missing_ids = sorted(set(normalized_ids) - found_ids)
        if missing_ids:
            raise BaseAppException(f"监控资产不存在: {', '.join(missing_ids)}")

        org_map = {}
        for instance_id, organization in MonitorInstanceOrganization.objects.filter(
            monitor_instance_id__in=normalized_ids
        ).values_list("monitor_instance_id", "organization"):
            org_map.setdefault(instance_id, []).append(organization)

        return [
            {
                "instance_id": item["id"],
                "organizations": org_map.get(item["id"], []),
            }
            for item in instances
        ]

    def enrich_bulk_policy_templates(self, monitor_object_id, templates):
        from apps.monitor.models.monitor_metrics import Metric

        enriched = []
        for template in templates:
            metric_name = template.get("metric_name")
            if not metric_name:
                raise BaseAppException("模板 metric_name 不能为空")
            metric_qs = Metric.objects.filter(
                monitor_object_id=monitor_object_id,
                name=metric_name,
            )
            collect_type = template.get("collect_type") or template.get("plugin_id")
            if collect_type:
                metric_qs = metric_qs.filter(monitor_plugin_id=collect_type)
            metric = metric_qs.first()
            if not metric:
                raise BaseAppException(f"指标不存在: {metric_name}")
            enriched.append(
                {
                    **template,
                    "metric_id": metric.id,
                    "metric_unit": "" if metric.unit in ("none", "short") else metric.unit,
                    "collect_type": collect_type or metric.monitor_plugin_id,
                }
            )
        return enriched
