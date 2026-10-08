import json
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.alerts.constants.constants import SessionStatus
from apps.alerts.filters.notification_template import NotificationTemplateFilter
from apps.alerts.models.models import Alert
from apps.alerts.models.notification_template import NotificationTemplate
from apps.alerts.notification_templates.binding import build_runtime_alert_context, load_event_context
from apps.alerts.notification_templates.events import (
    DEFAULT_LIMIT,
    DEFAULT_ORDER,
    EVENT_SCALAR_FIELDS,
    MAX_EVENT_COLUMNS,
    MAX_EVENT_ROWS,
    inspect_event_usage,
)
from apps.alerts.notification_templates.operation import ensure_alert_operation_template
from apps.alerts.notification_templates.renderer import TemplateValidationError, render_source
from apps.alerts.serializers.notification_template import NotificationTemplateSerializer
from apps.alerts.utils.i18n import alerts_message, serializer_message
from apps.alerts.utils.permission_scope import (
    apply_team_scope_for_request,
    apply_team_scope_with_group_ids,
    get_current_team_from_request,
    get_query_group_ids,
)
from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


def _preview_events():
    latest = {
        "event_id": "EVENT-PREVIEW-2",
        "title": "CPU 使用率过高",
        "level": "严重",
        "status": "received",
        "item": "cpu_usage",
        "value": 95,
        "resource_name": "生产主机 01",
        "resource_type": "host",
        "source_name": "Prometheus",
        "start_time": "2026-09-08 10:05:00+08:00",
        "received_at": "2026-09-08 10:05:12+08:00",
        "tags": {"alert": "CpuHigh"},
        "labels": {"env": "prod"},
        "enrichment": {"cmdb": {"owner": "张三"}},
    }
    first = {
        "event_id": "EVENT-PREVIEW-1",
        "title": "CPU 使用率过高",
        "level": "警告",
        "status": "received",
        "item": "cpu_usage",
        "value": 81,
        "resource_name": "生产主机 01",
        "resource_type": "host",
        "source_name": "Prometheus",
        "start_time": "2026-09-08 10:00:00+08:00",
        "received_at": "2026-09-08 10:00:08+08:00",
        "tags": {"alert": "CpuHigh"},
        "labels": {"env": "prod"},
        "enrichment": {"cmdb": {"owner": "张三"}},
    }
    return {"count": 2, "latest": latest, "first": first, "rows": [latest, first]}


def _preview_context(sample):
    sample = sample if isinstance(sample, dict) else {}
    receivers = sample.get("receivers", ["zhangsan"])
    receiver_names = "、".join(str(receiver) for receiver in receivers) if isinstance(receivers, list) else str(receivers or "")
    alert = {
        "alert_id": "ALERT-PREVIEW",
        "title": "CPU 使用率过高",
        "content": "CPU 使用率已达到 95%",
        "level": "警告",
        "level_id": "2",
        "status": "unassigned",
        "source_name": "Prometheus",
        "resource_id": "host-01",
        "resource_name": "生产主机 01",
        "resource_type": "host",
        "item": "cpu_usage",
        "created_at": "2026-09-08 10:00:00+08:00",
        "first_event_time": "2026-09-08 10:00:00+08:00",
        "last_event_time": "2026-09-08 10:05:00+08:00",
        "operators": ["zhangsan"],
        "team": [1],
        **(sample.get("alert") if isinstance(sample.get("alert"), dict) else {}),
    }
    return {
        "alert": alert,
        "labels": {"env": "prod", **(sample.get("labels") if isinstance(sample.get("labels"), dict) else {})},
        "dimensions": {"instance": "10.0.0.8", **(sample.get("dimensions") if isinstance(sample.get("dimensions"), dict) else {})},
        "enrichment": {"cmdb": {"owner": "张三"}, **(sample.get("enrichment") if isinstance(sample.get("enrichment"), dict) else {})},
        "notification": {
            "scene": "test",
            "scene_name": "测试发送",
            "receivers": receivers,
            "receiver_names": receiver_names,
            "generated_at": "2026-09-08 10:06:00+08:00",
            "action_summary": "该告警已由 admin 分派给 zhangsan，请及时认领并处理。",
            "actor_name": "admin",
            "previous_receiver_names": "lisi",
            "action_time": "2026-09-08 10:06:00+08:00",
        },
        "summary": sample.get("summary", {"total": 2, "displayed": 2, "omitted": 0, "alerts": []}),
        "events": sample.get("events") if isinstance(sample.get("events"), dict) else _preview_events(),
    }


class NotificationTemplateTestSendSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    alert_id = serializers.IntegerField(min_value=1, required=False)
    receivers = serializers.ListField(
        child=serializers.CharField(max_length=150),
        min_length=1,
        max_length=50,
        required=False,
    )
    sample = serializers.JSONField(required=False)

    def validate_sample(self, value):
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
            raise serializers.ValidationError(serializer_message(self, "error.sample_payload_too_large"))
        return value


class NotificationTemplateDraftTestSendSerializer(serializers.Serializer):
    template_id = serializers.IntegerField(min_value=1, required=False)
    channel_id = serializers.IntegerField(min_value=1)
    alert_id = serializers.IntegerField(min_value=1)
    receivers = serializers.ListField(
        child=serializers.CharField(max_length=150),
        min_length=1,
        max_length=50,
    )
    scope = serializers.ChoiceField(choices=NotificationTemplate.SCOPE_CHOICES)
    channel_type = serializers.CharField(max_length=30)
    subject_template = serializers.CharField(allow_blank=True, required=False, default="")
    body_template = serializers.CharField()


class NotificationTemplateViewSet(ModelViewSet):
    queryset = NotificationTemplate.objects.prefetch_related("contents", "references").all()
    serializer_class = NotificationTemplateSerializer
    filterset_class = NotificationTemplateFilter
    pagination_class = CustomPageNumberPagination
    ordering_fields = ["created_at", "updated_at", "name"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        base = super().get_queryset()
        scoped = apply_team_scope_for_request(base, self.request)
        current_team = get_current_team_from_request(self.request, required=False)
        if current_team:
            return base.filter(
                ((Q(pk__in=scoped.values("pk")) | Q(is_global=True)) & ~Q(scope=NotificationTemplate.SCOPE_ALERT_OPERATION))
                | Q(builtin_key=f"alert_operation:{current_team}")
            ).distinct()
        return base.filter(Q(pk__in=scoped.values("pk")) | Q(is_global=True)).exclude(scope=NotificationTemplate.SCOPE_ALERT_OPERATION).distinct()

    @HasPermission("notification_templates-View")
    def list(self, request, *args, **kwargs):
        # 内置模板初始化会写库，必须在任何写入前校验当前团队归属。
        get_query_group_ids(request)
        current_team = get_current_team_from_request(request, required=True)
        if current_team:
            ensure_alert_operation_template(current_team, request.user)
        return super().list(request, *args, **kwargs)

    @HasPermission("notification_templates-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("notification_templates-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        if "team" not in payload:
            current_team = get_current_team_from_request(request, required=True)
            if not current_team:
                raise ValidationError({"team": alerts_message(request, "error.team_missing")})
            payload["team"] = [current_team]
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"name": alerts_message(request, "error.template_name_exists")}) from exc
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _locked_queryset(self):
        visible_ids = self.get_queryset().filter(pk=self.kwargs["pk"]).values("pk")
        return NotificationTemplate.objects.prefetch_related("contents", "references").filter(pk__in=visible_ids).select_for_update()

    def _locked_object(self):
        return get_object_or_404(self._locked_queryset())

    @staticmethod
    def _get_test_channel(request, channel_id, channel_type=None):
        if channel_type == IMNotificationChannel.CHANNEL_TYPE:
            channel = (
                apply_team_scope_with_group_ids(
                    IMNotificationChannel.objects.filter(enabled=True),
                    get_query_group_ids(request),
                )
                .filter(pk=channel_id)
                .first()
            )
            if not channel:
                raise ValidationError({"channel_id": alerts_message(request, "error.channel_unusable")})
            return SimpleNamespace(id=channel.id, channel_type=IMNotificationChannel.CHANNEL_TYPE, team=channel.team, name=channel.name)
        channel = apply_team_scope_with_group_ids(Channel.objects.all(), get_query_group_ids(request)).filter(pk=channel_id).first()
        if not channel:
            raise ValidationError({"channel_id": alerts_message(request, "error.channel_unusable")})
        if channel_type and channel.channel_type != channel_type:
            raise ValidationError({"channel_id": alerts_message(request, "error.channel_unusable")})
        if channel.channel_type == "nats" and (channel.config or {}).get("source") != "opspilot":
            raise ValidationError({"channel_id": alerts_message(request, "error.template_test_nats_only")})
        return channel

    @staticmethod
    def _get_test_alert(request, alert_id):
        alert = (
            apply_team_scope_with_group_ids(
                Alert.objects.exclude(session_status__in=SessionStatus.NO_CONFIRMED),
                get_query_group_ids(request),
            )
            .filter(pk=alert_id)
            .first()
        )
        if not alert:
            raise ValidationError({"alert_id": alerts_message(request, "error.alert_unusable_for_test")})
        return alert

    @staticmethod
    def _build_test_context(request, alert, scope, receivers, sources=()):
        notification_context = None
        if scope == NotificationTemplate.SCOPE_ALERT_OPERATION:
            action_time = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
            notification_context = {
                "action_summary": (f"这是由 {request.user.username} 使用告警 {alert.alert_id} 发起的测试发送，" "请勿作为真实分派处理。"),
                "actor_name": request.user.username,
                "previous_receiver_names": "",
                "action_time": action_time,
            }
        context = build_runtime_alert_context(
            alert,
            receivers,
            "test",
            notification_context,
        )
        if inspect_event_usage(sources).used:
            context["events"] = load_event_context(alert, sources)
        return context

    @staticmethod
    def _render_test_content(channel, scope, subject_template, body_template, context):
        try:
            subject = render_source(
                subject_template,
                context,
                channel_type=channel.channel_type,
                is_subject=True,
                scope=scope,
            ).value
            body = render_source(
                body_template,
                context,
                channel_type=channel.channel_type,
                scope=scope,
            ).value
        except TemplateValidationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return subject, body

    @staticmethod
    def _send_test_content(request, channel, receivers, subject, body):
        from apps.alerts.common.notify.notify import Notify

        send_content = body
        if channel.channel_type == "nats":
            send_content = {
                "message": body,
                "team": get_current_team_from_request(request, required=True),
                "user_ids": receivers,
            }
            subject = ""
        notifier = Notify(receivers, channel.id, subject, send_content, append_receivers=False, channel_type=channel.channel_type)
        resolved_usernames = {item.get("username") for item in notifier.user_list}
        missing_receivers = [username for username in receivers if username not in resolved_usernames]
        if missing_receivers:
            raise ValidationError({"receivers": alerts_message(request, "error.receivers_missing", receivers="、".join(missing_receivers))})
        result = notifier.notify()
        if isinstance(result, dict) and result.get("result") is False:
            return Response(
                {"detail": result.get("message") or alerts_message(request, "error.test_send_failed")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"result": result, "subject": subject, "body": body})

    @HasPermission("notification_templates-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self._locked_object()
        if (instance.is_builtin and not instance.is_alert_operation) or instance.is_global:
            raise ValidationError({"detail": alerts_message(request, "error.global_template_readonly")})
        expected_revision = request.data.get("revision")
        try:
            revision_matches = expected_revision is not None and int(expected_revision) == instance.revision
        except (TypeError, ValueError):
            revision_matches = False
        if not revision_matches:
            return Response(
                {"revision": alerts_message(request, "error.template_revision_conflict"), "current_revision": instance.revision},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"name": alerts_message(request, "error.template_name_exists")}) from exc
        return Response(serializer.data)

    @HasPermission("notification_templates-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("notification_templates-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self._locked_object()
        if instance.is_builtin or instance.is_global:
            raise ValidationError({"detail": alerts_message(request, "error.builtin_or_global_template_undeletable")})
        references = list(instance.references.values("source_type", "source_id", "scene", "channel_id", "locator", "is_snapshot")[:100])
        if references:
            return Response(
                {"detail": alerts_message(request, "error.template_in_use"), "references": references},
                status=status.HTTP_409_CONFLICT,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    @HasPermission("notification_templates-View")
    def preview(self, request):
        channel_type = request.data.get("channel_type", "")
        scope = request.data.get("scope", NotificationTemplate.SCOPE_SINGLE_ALERT)
        context = _preview_context(request.data.get("sample"))
        try:
            subject_result = render_source(request.data.get("subject_template", ""), context, channel_type=channel_type, is_subject=True, scope=scope)
            body_result = render_source(request.data.get("body_template", ""), context, channel_type=channel_type, scope=scope)
        except TemplateValidationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            {
                "subject": subject_result.value,
                "body": body_result.value,
                "missing_fields": list(dict.fromkeys(subject_result.missing_fields + body_result.missing_fields)),
            }
        )

    @action(detail=False, methods=["get"])
    @HasPermission("notification_templates-View,alert_assign-View")
    def options(self, request):
        channel_type = request.query_params.get("channel_type")
        queryset = self.get_queryset().filter(scope=NotificationTemplate.SCOPE_SINGLE_ALERT)
        if channel_type:
            queryset = queryset.filter(contents__channel_type=channel_type)
        return Response(list(queryset.values("id", "name", "scope", "is_global", "revision").distinct().order_by("name")[:200]))

    @action(detail=False, methods=["get"])
    @HasPermission("notification_templates-View")
    def catalog(self, request):
        return Response(
            {
                "variables": [
                    {"path": "alert.title", "label": alerts_message(request, "catalog.alert_title")},
                    {"path": "alert.content", "label": alerts_message(request, "catalog.alert_content")},
                    {"path": "alert.level", "label": alerts_message(request, "catalog.alert_level")},
                    {"path": "alert.level_id", "label": alerts_message(request, "catalog.alert_level_id")},
                    {"path": "alert.alert_id", "label": alerts_message(request, "catalog.alert_id")},
                    {"path": "alert.created_at", "label": alerts_message(request, "catalog.alert_created_at")},
                    {"path": "alert.resource_name", "label": alerts_message(request, "catalog.alert_resource_name")},
                    {"path": "alert.resource_type", "label": alerts_message(request, "catalog.alert_resource_type")},
                    {"path": "alert.source_name", "label": alerts_message(request, "catalog.alert_source_name")},
                    {"path": "alert.item", "label": alerts_message(request, "catalog.alert_item")},
                    {"path": "notification.scene_name", "label": alerts_message(request, "catalog.scene_name")},
                    {"path": "notification.receiver_names", "label": alerts_message(request, "catalog.receiver_names")},
                    {"path": "notification.receivers", "label": alerts_message(request, "catalog.receivers")},
                    {
                        "path": "notification.action_summary",
                        "label": alerts_message(request, "catalog.action_summary"),
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.actor_name",
                        "label": alerts_message(request, "catalog.actor_name"),
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.previous_receiver_names",
                        "label": alerts_message(request, "catalog.previous_receiver_names"),
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.action_time",
                        "label": alerts_message(request, "catalog.action_time"),
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {"path": "labels.env", "label": alerts_message(request, "catalog.label_example")},
                    {"path": "dimensions.instance", "label": alerts_message(request, "catalog.dimension_example")},
                    {"path": "enrichment.cmdb.owner", "label": alerts_message(request, "catalog.enrichment_example")},
                    {"path": "events.count", "label": alerts_message(request, "catalog.event_count")},
                    {"path": "events.latest.title", "label": alerts_message(request, "catalog.latest_event_title")},
                    {"path": "events.latest.value", "label": alerts_message(request, "catalog.latest_event_value")},
                    {"path": "events.latest.tags.alert", "label": alerts_message(request, "catalog.latest_event_tag_example")},
                ],
                "event_block": {
                    "max_rows": MAX_EVENT_ROWS,
                    "max_columns": MAX_EVENT_COLUMNS,
                    "default_limit": DEFAULT_LIMIT,
                    "default_order": DEFAULT_ORDER,
                    "orders": [
                        {"value": "-start_time", "label": alerts_message(request, "catalog.order_start_time_desc")},
                        {"value": "start_time", "label": alerts_message(request, "catalog.order_start_time_asc")},
                        {"value": "-received_at", "label": alerts_message(request, "catalog.order_received_at_desc")},
                        {"value": "received_at", "label": alerts_message(request, "catalog.order_received_at_asc")},
                    ],
                    "limits": [5, 10, 20, 50, "all"],
                    "fields": [
                        {"path": path, "label": alerts_message(request, f"catalog.event_field.{path}")} for path in EVENT_SCALAR_FIELDS
                    ],
                    "json_roots": [
                        {"root": "tags", "label": alerts_message(request, "catalog.root_tags")},
                        {"root": "labels", "label": alerts_message(request, "catalog.root_labels")},
                        {"root": "enrichment", "label": alerts_message(request, "catalog.root_enrichment")},
                    ],
                },
            }
        )

    @action(detail=True, methods=["get"])
    @HasPermission("notification_templates-View")
    def references(self, request, pk=None):
        template = self.get_object()
        queryset = template.references.order_by("id")
        if template.is_global and not request.user.is_superuser:
            return Response({"count": queryset.count(), "items": [], "restricted": True})
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        except (TypeError, ValueError):
            raise ValidationError({"detail": alerts_message(request, "error.page_params_positive")})
        start = (page - 1) * page_size
        return Response(
            {
                "count": queryset.count(),
                "items": list(
                    queryset.values("source_type", "source_id", "scene", "channel_id", "locator", "is_snapshot")[start : start + page_size]
                ),
            }
        )

    @action(detail=True, methods=["post"])
    @HasPermission("notification_templates-Add")
    @transaction.atomic
    def copy(self, request, pk=None):
        source = self.get_object()
        if source.is_alert_operation:
            raise ValidationError({"detail": alerts_message(request, "error.builtin_operation_template_uncopyable")})
        current_team = get_current_team_from_request(request, required=True)
        if not current_team:
            raise ValidationError({"team": alerts_message(request, "error.team_missing")})
        payload = {
            "name": request.data.get("name") or f"{source.name} - 副本",
            "description": source.description,
            "team": [current_team],
            "scope": source.scope,
            "contents": list(source.contents.values("channel_type", "subject_template", "body_template")),
        }
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"name": alerts_message(request, "error.template_name_exists")}) from exc
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="test_send")
    @HasPermission("notification_templates-Test")
    @HasPermission("notification_templates-View")
    @HasPermission("Alarms-View")
    def test_send(self, request, pk=None):
        template = self.get_object()
        request_serializer = NotificationTemplateTestSendSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        channel_id = request_serializer.validated_data["channel_id"]
        if template.is_alert_operation and template.channel_id != channel_id:
            raise ValidationError({"channel_id": alerts_message(request, "error.operation_template_selected_channel_only")})
        channel = self._get_test_channel(request, channel_id)
        content = template.contents.filter(channel_type=channel.channel_type).first()
        if not content:
            raise ValidationError({"channel_id": alerts_message(request, "error.template_channel_type_missing")})
        alert_id = request_serializer.validated_data.get("alert_id")
        receivers = request_serializer.validated_data.get("receivers") or [request.user.username]
        if alert_id:
            alert = self._get_test_alert(request, alert_id)
            context = self._build_test_context(
                request,
                alert,
                template.scope,
                receivers,
                (content.subject_template, content.body_template),
            )
        else:
            # 兼容第一版 API 调用；新版页面始终要求选择一条真实告警。
            context = _preview_context(request_serializer.validated_data.get("sample"))
        subject, body = self._render_test_content(
            channel,
            template.scope,
            content.subject_template,
            content.body_template,
            context,
        )
        return self._send_test_content(request, channel, receivers, subject, body)

    @action(detail=False, methods=["post"], url_path="test_send")
    @HasPermission("notification_templates-Test")
    @HasPermission("notification_templates-View")
    @HasPermission("Alarms-View")
    def test_send_draft(self, request):
        request_serializer = NotificationTemplateDraftTestSendSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data
        channel = self._get_test_channel(request, data["channel_id"], data.get("channel_type"))
        if data["channel_type"] != channel.channel_type:
            raise ValidationError({"channel_type": alerts_message(request, "error.template_channel_mismatch")})
        scope = data["scope"]
        if scope not in {
            NotificationTemplate.SCOPE_SINGLE_ALERT,
            NotificationTemplate.SCOPE_ALERT_OPERATION,
        }:
            raise ValidationError({"scope": alerts_message(request, "error.test_send_scope_limited")})
        if scope == NotificationTemplate.SCOPE_ALERT_OPERATION:
            template_id = data.get("template_id")
            template = self.get_queryset().filter(pk=template_id).first() if template_id else None
            if not template or not template.is_alert_operation:
                raise ValidationError({"template_id": alerts_message(request, "error.operation_template_must_be_builtin")})
        alert = self._get_test_alert(request, data["alert_id"])
        receivers = list(dict.fromkeys(data["receivers"]))
        context = self._build_test_context(
            request,
            alert,
            scope,
            receivers,
            (data["subject_template"], data["body_template"]),
        )
        subject, body = self._render_test_content(
            channel,
            scope,
            data["subject_template"],
            data["body_template"],
            context,
        )
        return self._send_test_content(request, channel, receivers, subject, body)
