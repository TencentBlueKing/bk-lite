from copy import deepcopy
from django.db import DatabaseError, OperationalError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
import logging

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.filter_snapshot import (
    normalize_applied_filter_values,
)
from apps.operation_analysis.services.schedule_calculator import (
    ScheduleSpec,
    next_run,
    validate_iana_timezone,
)
from apps.system_mgmt.models import Channel

logger = logging.getLogger(__name__)

SCHEDULE_FIELDS = frozenset(
    {
        "schedule_type",
        "schedule_hour",
        "schedule_minute",
        "schedule_weekday",
        "schedule_day_of_month",
        "timezone",
    }
)

TERMINATION_REASON_DASHBOARD_DELETED = "dashboard_deleted"


class DashboardSubscriptionService:
    @staticmethod
    def can_view_dashboard(request, dashboard: Dashboard) -> bool:
        user = request.user
        if getattr(user, "is_superuser", False):
            return True

        current_team = get_current_team(request)
        try:
            current_team_id = int(current_team)
        except (TypeError, ValueError):
            return False

        from apps.operation_analysis.views.view import DashboardModelViewSet

        viewset = DashboardModelViewSet()
        return viewset.get_has_permission(
            user,
            dashboard,
            current_team_id,
            is_check=True,
            include_children=request.COOKIES.get("include_children", "0") == "1",
        )

    @classmethod
    def require_dashboard_view(cls, request, dashboard: Dashboard) -> None:
        if not cls.can_view_dashboard(request, dashboard):
            raise PermissionDenied("无权查看该仪表盘")

    @classmethod
    def can_view_datasource(cls, request, datasource) -> bool:
        """实例级 DataSource View 判断（布尔）；瞬时依赖失败视为 False。

        创建期扫描请用 evaluate_datasource_for_create_scan，以区分
        明确拒绝与依赖瞬时不可用（D3）。
        """
        outcome = cls.evaluate_datasource_for_create_scan(request, datasource)
        return outcome == "allowed"

    @classmethod
    def _load_datasource_rules_for_create_scan(
        cls,
        user,
        current_team_id: int,
        *,
        include_children: bool,
    ) -> tuple[dict | None, bool]:
        """返回 (rules, transient)。

        不修改全局 get_permission_rules：在创建期边界自行处理 RPC 失败。
        成功规则形如 {"team": [...], "instance": [...]}；
        get_permission_rules 在 RPC 失败时返回 {}，亦视为瞬时。
        """
        from apps.core.utils.permission_cache import (
            get_cached_permission_rules,
            set_cached_permission_rules,
        )
        from apps.core.utils.permission_utils import set_rules_module_params

        cached = get_cached_permission_rules(
            username=user.username,
            domain=getattr(user, "domain", None),
            current_team=current_team_id,
            app_name="operation_analysis",
            permission_key="datasource",
            include_children=include_children,
        )
        if cached is not None:
            return cached, False

        try:
            app, child_module, client, module = set_rules_module_params(
                "operation_analysis",
                "datasource",
            )
            permission_data = client.get_user_rules_by_app(
                current_team_id,
                user.username,
                app,
                module,
                child_module,
                getattr(user, "domain", None),
                include_children,
            )
        except Exception as exc:
            logger.warning(
                "创建期 DataSource 权限规则 RPC 瞬时失败: err=%s",
                type(exc).__name__,
            )
            return None, True

        if not isinstance(permission_data, dict) or (
            "team" not in permission_data and "instance" not in permission_data
        ):
            # 与 get_permission_rules 失败回落 {} 对齐：无结构视为依赖不可用
            logger.warning(
                "创建期 DataSource 权限规则不可用（空/无结构），允许保存"
            )
            return None, True

        set_cached_permission_rules(
            username=user.username,
            domain=getattr(user, "domain", None),
            current_team=current_team_id,
            app_name="operation_analysis",
            permission_key="datasource",
            permission_data=permission_data,
            include_children=include_children,
        )
        return permission_data, False

    @classmethod
    def evaluate_datasource_for_create_scan(
        cls,
        request,
        datasource,
    ) -> str:
        """创建期 DS 扫描专用：'allowed' | 'denied' | 'transient'。"""
        user = request.user
        if getattr(user, "is_superuser", False):
            return "allowed"

        from apps.core.utils.user_group import normalize_user_group_ids
        from apps.operation_analysis.services.import_export.authorization_service import (
            ImportExportAuthorizationService,
        )

        # 功能权限为本地判定，缺失即明确拒绝
        if not ImportExportAuthorizationService.has_permission(
            request, "data_source-View"
        ):
            return "denied"

        current_team = get_current_team(request)
        try:
            current_team_id = int(current_team)
        except (TypeError, ValueError):
            return "denied"

        user_groups = normalize_user_group_ids(getattr(user, "group_list", []))
        include_children = (
            request.COOKIES.get("include_children", "0") == "1"
        )
        org_value = getattr(datasource, "groups", None) or []
        if not set(org_value).intersection(set(user_groups)):
            return "denied"

        rules, transient = cls._load_datasource_rules_for_create_scan(
            user,
            current_team_id,
            include_children=include_children,
        )
        if transient:
            return "transient"

        team_rules = rules.get("team") or []
        try:
            if current_team_id in {int(t) for t in team_rules}:
                return "allowed"
        except (TypeError, ValueError):
            pass

        if include_children:
            allowed_teams = set()
            for item in team_rules:
                try:
                    allowed_teams.add(int(item))
                except (TypeError, ValueError):
                    continue
            if allowed_teams & set(user_groups):
                return "allowed"

        instance_list = []
        for item in rules.get("instance") or []:
            if not isinstance(item, dict):
                continue
            perms = item.get("permission") or []
            if "View" not in perms:
                continue
            try:
                instance_list.append(int(item["id"]))
            except (TypeError, ValueError, KeyError):
                continue

        if datasource.id in instance_list:
            return "allowed"
        return "denied"

    @classmethod
    def scan_dashboard_datasources(cls, request, dashboard: Dashboard) -> None:
        """创建期 DS 权限扫描（D3 / A5）。

        明确无权限/不存在 → 拒绝；瞬时网络/DB/权限规则 RPC 错误 → 允许保存并记 warning。
        不发起真实业务查询。复用 Render Snapshot 的 widget→datasource 解析。
        """
        from apps.operation_analysis.models.datasource_models import (
            DataSourceAPIModel,
        )
        from apps.operation_analysis.services.render_snapshot_service import (
            _widget_manifest,
        )

        try:
            manifest = _widget_manifest(dashboard.view_sets or [])
            ds_ids = {
                entry["datasource_id"]
                for entry in manifest
                if entry.get("datasource_id") is not None
            }
            if not ds_ids:
                return

            found = {
                ds.id: ds
                for ds in DataSourceAPIModel.objects.filter(id__in=ds_ids)
            }
        except (OperationalError, DatabaseError, ConnectionError, TimeoutError) as exc:
            logger.warning(
                "创建期 DataSource 扫描瞬时失败，允许保存: dashboard_id=%s err=%s",
                dashboard.id,
                type(exc).__name__,
            )
            return

        missing = sorted(ds_ids - set(found))
        if missing:
            raise ValidationError(
                {
                    "dashboard": (
                        f"仪表盘引用的数据源不存在: {', '.join(map(str, missing))}"
                    )
                }
            )

        for ds_id in sorted(found):
            try:
                outcome = cls.evaluate_datasource_for_create_scan(
                    request, found[ds_id]
                )
            except (
                OperationalError,
                DatabaseError,
                ConnectionError,
                TimeoutError,
            ) as exc:
                logger.warning(
                    "创建期 DataSource 权限检查瞬时失败，允许保存: "
                    "dashboard_id=%s err=%s",
                    dashboard.id,
                    type(exc).__name__,
                )
                return

            if outcome == "transient":
                logger.warning(
                    "创建期 DataSource 权限依赖不可用，允许保存: "
                    "dashboard_id=%s datasource_id=%s",
                    dashboard.id,
                    ds_id,
                )
                return
            if outcome == "denied":
                raise PermissionDenied(
                    f"无权查看仪表盘引用的数据源: {ds_id}"
                )

    @classmethod
    def build_filter_config(
        cls,
        *,
        dashboard: Dashboard,
        applied_filter_values,
        existing_config: dict | None = None,
    ) -> dict:
        config = deepcopy(existing_config or {})
        snapshot = normalize_applied_filter_values(
            applied_filter_values if applied_filter_values is not None else {},
            dashboard.filters,
        )
        config["filter_snapshot"] = snapshot
        return config

    @classmethod
    def validate_email_channel(cls, request, channel: Channel | None) -> None:
        if channel is None:
            raise ValidationError(
                {"email_channel": "报告订阅必须指定邮件通道"}
            )
        if channel.channel_type != "email":
            raise ValidationError(
                {"email_channel": "所选通道不是邮件类型"}
            )
        if not getattr(request.user, "is_superuser", False):
            current_team = get_current_team(request)
            try:
                current_team_id = int(current_team)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"email_channel": "无权使用该邮件通道"}
                )
            channel_teams = channel.team or []
            if current_team_id not in channel_teams:
                raise ValidationError(
                    {"email_channel": "无权使用该邮件通道"}
                )

    @classmethod
    def build_schedule_spec(
        cls,
        *,
        schedule_type: str | None,
        schedule_hour: int | None,
        schedule_minute: int | None,
        schedule_weekday: int | None,
        schedule_day_of_month: int | None,
    ) -> ScheduleSpec | None:
        if schedule_type is None:
            return None
        if schedule_hour is None or schedule_minute is None:
            raise ValidationError(
                {"schedule_hour": "已配置调度时必须指定时分"}
            )
        return ScheduleSpec(
            schedule_type=schedule_type,
            hour=schedule_hour,
            minute=schedule_minute,
            weekday=schedule_weekday,
            day_of_month=schedule_day_of_month,
        )

    @classmethod
    def compute_next_run_at(
        cls,
        *,
        schedule_type: str | None,
        schedule_hour: int | None,
        schedule_minute: int | None,
        schedule_weekday: int | None,
        schedule_day_of_month: int | None,
        timezone_name: str | None,
        after=None,
    ):
        spec = cls.build_schedule_spec(
            schedule_type=schedule_type,
            schedule_hour=schedule_hour,
            schedule_minute=schedule_minute,
            schedule_weekday=schedule_weekday,
            schedule_day_of_month=schedule_day_of_month,
        )
        if spec is None:
            return None
        if not timezone_name:
            raise ValidationError(
                {"timezone": "已配置调度时必须指定 IANA 时区"}
            )
        try:
            tz = validate_iana_timezone(timezone_name)
            spec.validate()
        except ValueError as exc:
            raise ValidationError({"schedule_type": str(exc)}) from exc
        result = next_run(spec, tz, after=after or timezone.now())
        return result.utc

    @classmethod
    def _schedule_values_from_instance(
        cls, subscription: DashboardReportSubscription
    ) -> dict:
        return {
            "schedule_type": subscription.schedule_type,
            "schedule_hour": subscription.schedule_hour,
            "schedule_minute": subscription.schedule_minute,
            "schedule_weekday": subscription.schedule_weekday,
            "schedule_day_of_month": subscription.schedule_day_of_month,
            "timezone": subscription.timezone,
        }

    @classmethod
    def _merge_schedule_values(
        cls,
        subscription: DashboardReportSubscription | None,
        validated_data: dict,
    ) -> dict:
        base = (
            cls._schedule_values_from_instance(subscription)
            if subscription is not None
            else {
                "schedule_type": None,
                "schedule_hour": None,
                "schedule_minute": None,
                "schedule_weekday": None,
                "schedule_day_of_month": None,
                "timezone": None,
            }
        )
        for field in SCHEDULE_FIELDS:
            if field in validated_data:
                base[field] = validated_data[field]
        return base

    @classmethod
    def _schedule_changed(
        cls,
        subscription: DashboardReportSubscription,
        validated_data: dict,
    ) -> bool:
        current = cls._schedule_values_from_instance(subscription)
        for field in SCHEDULE_FIELDS:
            if field in validated_data and validated_data[field] != current[field]:
                return True
        return False

    @classmethod
    def create(cls, request, serializer) -> DashboardReportSubscription:
        dashboard = serializer.validated_data["dashboard"]
        cls.require_dashboard_view(request, dashboard)
        cls.validate_email_channel(
            request,
            serializer.validated_data.get("email_channel"),
        )
        applied = serializer.validated_data.pop("applied_filter_values", {})
        cls.scan_dashboard_datasources(request, dashboard)
        schedule = cls._merge_schedule_values(None, serializer.validated_data)
        next_run_at = cls.compute_next_run_at(
            schedule_type=schedule["schedule_type"],
            schedule_hour=schedule["schedule_hour"],
            schedule_minute=schedule["schedule_minute"],
            schedule_weekday=schedule["schedule_weekday"],
            schedule_day_of_month=schedule["schedule_day_of_month"],
            timezone_name=schedule["timezone"],
        )
        config = cls.build_filter_config(
            dashboard=dashboard,
            applied_filter_values=applied,
        )
        return serializer.save(
            creator=request.user.username,
            next_run_at=next_run_at,
            version=1,
            config=config,
        )

    @classmethod
    def update(
        cls,
        request,
        subscription: DashboardReportSubscription,
        serializer,
    ) -> DashboardReportSubscription:
        if (
            subscription.creator != request.user.username
            and not getattr(request.user, "is_superuser", False)
        ):
            raise PermissionDenied("只能修改自己的报告订阅")
        if subscription.deleted_at is not None:
            raise PermissionDenied("已删除的报告订阅不可修改")
        if subscription.status == DashboardReportSubscription.Status.TERMINATED:
            raise ValidationError(
                {"status": "已终止的报告订阅不可修改或恢复"}
            )
        if subscription.dashboard is None:
            raise PermissionDenied("源仪表盘已不存在，不能修改该订阅")
        cls.require_dashboard_view(request, subscription.dashboard)
        cls.validate_email_channel(
            request,
            serializer.validated_data.get(
                "email_channel",
                subscription.email_channel,
            ),
        )

        expected_version = serializer.validated_data.pop("version", None)
        applied_provided = "applied_filter_values" in serializer.validated_data
        applied = serializer.validated_data.pop("applied_filter_values", None)
        schedule_changed = cls._schedule_changed(
            subscription, serializer.validated_data
        )
        if schedule_changed:
            if (
                expected_version is not None
                and expected_version != subscription.version
            ):
                raise ValidationError(
                    {"version": "调度配置版本冲突，请刷新后重试"}
                )

        new_status = serializer.validated_data.get(
            "status", subscription.status
        )
        pausing = (
            subscription.status == DashboardReportSubscription.Status.ACTIVE
            and new_status == DashboardReportSubscription.Status.PAUSED
        )
        resuming = (
            subscription.status == DashboardReportSubscription.Status.PAUSED
            and new_status == DashboardReportSubscription.Status.ACTIVE
        )

        # 重新启用 active 时重跑 DS 扫描；改名/筛选等不强制扫描
        if resuming:
            cls.scan_dashboard_datasources(request, subscription.dashboard)

        schedule = cls._merge_schedule_values(
            subscription, serializer.validated_data
        )
        extra = {}
        if schedule_changed:
            extra["next_run_at"] = cls.compute_next_run_at(
                schedule_type=schedule["schedule_type"],
                schedule_hour=schedule["schedule_hour"],
                schedule_minute=schedule["schedule_minute"],
                schedule_weekday=schedule["schedule_weekday"],
                schedule_day_of_month=schedule["schedule_day_of_month"],
                timezone_name=schedule["timezone"],
            )
            extra["version"] = subscription.version + 1
        elif resuming and schedule["schedule_type"] is not None:
            # 恢复：从恢复时刻重算未来计划，不递增 schedule version，不立即发送
            extra["next_run_at"] = cls.compute_next_run_at(
                schedule_type=schedule["schedule_type"],
                schedule_hour=schedule["schedule_hour"],
                schedule_minute=schedule["schedule_minute"],
                schedule_weekday=schedule["schedule_weekday"],
                schedule_day_of_month=schedule["schedule_day_of_month"],
                timezone_name=schedule["timezone"],
            )

        if pausing or resuming:
            extra["last_lifecycle_action"] = (
                DashboardReportSubscription.LifecycleAction.PAUSE
                if pausing
                else DashboardReportSubscription.LifecycleAction.RESUME
            )
            extra["last_lifecycle_actor"] = request.user.username
            extra["last_lifecycle_at"] = timezone.now()

        if applied_provided:
            extra["config"] = cls.build_filter_config(
                dashboard=subscription.dashboard,
                applied_filter_values=applied,
                existing_config=subscription.config,
            )

        return serializer.save(**extra)

    @classmethod
    @transaction.atomic
    def soft_delete(
        cls,
        request,
        subscription: DashboardReportSubscription,
    ) -> DashboardReportSubscription:
        """逻辑删除 Subscription；不取消已有 pending/running Execution。"""
        locked = (
            DashboardReportSubscription.all_objects.select_for_update().get(
                pk=subscription.pk
            )
        )
        if (
            locked.creator != request.user.username
            and not getattr(request.user, "is_superuser", False)
        ):
            raise PermissionDenied("只能删除自己的报告订阅")
        if locked.deleted_at is not None:
            return locked

        now = timezone.now()
        locked.deleted_at = now
        locked.deleted_by = request.user.username
        locked.save(
            update_fields=["deleted_at", "deleted_by", "updated_at"]
        )
        return locked

    @classmethod
    @transaction.atomic
    def terminate_for_dashboard_deletion(
        cls,
        dashboard: Dashboard,
        *,
        actor: str,
        reason: str = TERMINATION_REASON_DASHBOARD_DELETED,
    ) -> int:
        """Dashboard 删除前终止关联未删除订阅，并标记在途 Execution。

        必须在同一事务内于 Dashboard.delete() 之前调用，避免出现
        active + dashboard=null 的悬空状态。
        """
        now = timezone.now()
        subscriptions = list(
            DashboardReportSubscription.all_objects.select_for_update()
            .filter(dashboard_id=dashboard.pk, deleted_at__isnull=True)
            .exclude(status=DashboardReportSubscription.Status.TERMINATED)
        )
        if not subscriptions:
            return 0

        subscription_ids = [item.pk for item in subscriptions]
        in_flight = (
            DashboardReportExecution.Status.PENDING,
            DashboardReportExecution.Status.RUNNING,
        )
        DashboardReportExecution.objects.filter(
            subscription_id__in=subscription_ids,
            status__in=in_flight,
        ).update(source_canvas_deleted_during_execution=True)

        DashboardReportSubscription.all_objects.filter(
            pk__in=subscription_ids
        ).update(
            status=DashboardReportSubscription.Status.TERMINATED,
            terminated_at=now,
            terminated_by=actor or "",
            termination_reason=reason,
            next_run_at=None,
            updated_at=now,
        )
        return len(subscription_ids)
