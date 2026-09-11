import json

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
from apps.alerts.notification_templates.binding import build_runtime_alert_context
from apps.alerts.notification_templates.operation import ensure_alert_operation_template
from apps.alerts.notification_templates.renderer import TemplateValidationError, render_source
from apps.alerts.serializers.notification_template import NotificationTemplateSerializer
from apps.alerts.utils.permission_scope import (
    apply_team_scope_for_request,
    apply_team_scope_with_group_ids,
    get_current_team_from_request,
    get_query_group_ids,
)
from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models.channel import Channel
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


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
            raise serializers.ValidationError("示例数据不能超过 64KB")
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
                raise ValidationError({"team": "缺少当前团队"})
            payload["team"] = [current_team]
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"name": "当前团队已存在同名模板"}) from exc
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _locked_queryset(self):
        visible_ids = self.get_queryset().filter(pk=self.kwargs["pk"]).values("pk")
        return NotificationTemplate.objects.prefetch_related("contents", "references").filter(pk__in=visible_ids).select_for_update()

    def _locked_object(self):
        return get_object_or_404(self._locked_queryset())

    @staticmethod
    def _get_test_channel(request, channel_id):
        channel = apply_team_scope_with_group_ids(Channel.objects.all(), get_query_group_ids(request)).filter(pk=channel_id).first()
        if not channel:
            raise ValidationError({"channel_id": "通知渠道不存在或无权使用"})
        if channel.channel_type == "nats" and (channel.config or {}).get("source") != "opspilot":
            raise ValidationError({"channel_id": "仅 OpsPilot 托管的 NATS 渠道支持模板试发"})
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
            raise ValidationError({"alert_id": "告警不存在或无权用于当前团队的测试发送"})
        return alert

    @staticmethod
    def _build_test_context(request, alert, scope, receivers):
        notification_context = None
        if scope == NotificationTemplate.SCOPE_ALERT_OPERATION:
            action_time = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
            notification_context = {
                "action_summary": (f"这是由 {request.user.username} 使用告警 {alert.alert_id} 发起的测试发送，" "请勿作为真实分派处理。"),
                "actor_name": request.user.username,
                "previous_receiver_names": "",
                "action_time": action_time,
            }
        return build_runtime_alert_context(
            alert,
            receivers,
            "test",
            notification_context,
        )

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
        notifier = Notify(receivers, channel.id, subject, send_content, append_receivers=False)
        resolved_usernames = {item.get("username") for item in notifier.user_list}
        missing_receivers = [username for username in receivers if username not in resolved_usernames]
        if missing_receivers:
            raise ValidationError({"receivers": f"接收人不存在：{'、'.join(missing_receivers)}"})
        result = notifier.notify()
        if isinstance(result, dict) and result.get("result") is False:
            return Response(
                {"detail": result.get("message") or "测试发送失败"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"result": result, "subject": subject, "body": body})

    @HasPermission("notification_templates-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self._locked_object()
        if (instance.is_builtin and not instance.is_alert_operation) or instance.is_global:
            raise ValidationError({"detail": "全局模板不可修改，请复制后编辑"})
        expected_revision = request.data.get("revision")
        try:
            revision_matches = expected_revision is not None and int(expected_revision) == instance.revision
        except (TypeError, ValueError):
            revision_matches = False
        if not revision_matches:
            return Response(
                {"revision": "模板已被其他用户修改，请刷新后重试", "current_revision": instance.revision},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError as exc:
            raise ValidationError({"name": "当前团队已存在同名模板"}) from exc
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
            raise ValidationError({"detail": "内置或全局模板不可删除"})
        references = list(instance.references.values("source_type", "source_id", "scene", "channel_id", "locator", "is_snapshot")[:100])
        if references:
            return Response({"detail": "模板正在使用，不能删除", "references": references}, status=status.HTTP_409_CONFLICT)
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
                    {"path": "alert.title", "label": "告警标题"},
                    {"path": "alert.content", "label": "告警内容"},
                    {"path": "alert.level", "label": "告警级别"},
                    {"path": "alert.level_id", "label": "原始级别 ID"},
                    {"path": "alert.alert_id", "label": "告警 ID"},
                    {"path": "alert.created_at", "label": "告警时间"},
                    {"path": "alert.resource_name", "label": "资源名称"},
                    {"path": "alert.resource_type", "label": "资源类型"},
                    {"path": "alert.source_name", "label": "告警来源"},
                    {"path": "alert.item", "label": "监控指标"},
                    {"path": "notification.scene_name", "label": "通知场景"},
                    {"path": "notification.receiver_names", "label": "本次接收人"},
                    {"path": "notification.receivers", "label": "接收人列表（JSON）"},
                    {
                        "path": "notification.action_summary",
                        "label": "操作说明",
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.actor_name",
                        "label": "操作人",
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.previous_receiver_names",
                        "label": "原处理人",
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {
                        "path": "notification.action_time",
                        "label": "操作时间",
                        "scopes": [NotificationTemplate.SCOPE_ALERT_OPERATION],
                    },
                    {"path": "labels.env", "label": "标签（示例）"},
                    {"path": "dimensions.instance", "label": "维度（示例）"},
                    {"path": "enrichment.cmdb.owner", "label": "丰富字段（示例）"},
                ]
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
            raise ValidationError({"detail": "分页参数必须是正整数"})
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
            raise ValidationError({"detail": "内置告警操作模板不可复制"})
        current_team = get_current_team_from_request(request, required=True)
        if not current_team:
            raise ValidationError({"team": "缺少当前团队"})
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
            raise ValidationError({"name": "当前团队已存在同名模板"}) from exc
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
            raise ValidationError({"channel_id": "告警操作通知只能使用已选择的唯一渠道"})
        channel = self._get_test_channel(request, channel_id)
        content = template.contents.filter(channel_type=channel.channel_type).first()
        if not content:
            raise ValidationError({"channel_id": "模板未配置该渠道类型"})
        alert_id = request_serializer.validated_data.get("alert_id")
        receivers = request_serializer.validated_data.get("receivers") or [request.user.username]
        if alert_id:
            alert = self._get_test_alert(request, alert_id)
            context = self._build_test_context(request, alert, template.scope, receivers)
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
        channel = self._get_test_channel(request, data["channel_id"])
        if data["channel_type"] != channel.channel_type:
            raise ValidationError({"channel_type": "模板格式与所选通知渠道不一致"})
        scope = data["scope"]
        if scope not in {
            NotificationTemplate.SCOPE_SINGLE_ALERT,
            NotificationTemplate.SCOPE_ALERT_OPERATION,
        }:
            raise ValidationError({"scope": "测试发送仅支持单条告警和告警操作模板"})
        if scope == NotificationTemplate.SCOPE_ALERT_OPERATION:
            template_id = data.get("template_id")
            template = self.get_queryset().filter(pk=template_id).first() if template_id else None
            if not template or not template.is_alert_operation:
                raise ValidationError({"template_id": "告警操作通知必须使用当前团队的内置模板"})
        alert = self._get_test_alert(request, data["alert_id"])
        receivers = list(dict.fromkeys(data["receivers"]))
        context = self._build_test_context(request, alert, scope, receivers)
        subject, body = self._render_test_content(
            channel,
            scope,
            data["subject_template"],
            data["body_template"],
            context,
        )
        return self._send_test_content(request, channel, receivers, subject, body)
