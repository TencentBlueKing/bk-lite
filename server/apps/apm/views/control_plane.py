from dataclasses import asdict

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.apm.models import (
    ApmAlertOutbox,
    ApmIngestSource,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmPolicyState,
    ApmService,
    ApmServiceInstance,
)
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import (
    ApmEventQuerySerializer,
    ApmIngestSourceSerializer,
    ApmPolicySerializer,
    ApmServiceInstanceSerializer,
    ApmServiceSerializer,
    CreateIngestSourceSerializer,
    IngestSnippetSerializer,
    NotificationDeliveryQuerySerializer,
    NotificationDeliveryRetrySerializer,
    NotificationRecipientQuerySerializer,
    OrganizationAssignmentSerializer,
    ServiceMetricQuerySerializer,
)
from apps.apm.adapters import (
    SystemMgmtNotificationDispatcher,
    TelemetryStoreUnavailable,
    VictoriaMetricsMetricStore,
)
from apps.apm.services import (
    DjangoApmEventReader,
    DjangoApmPolicyService,
    DjangoIngestSourceService,
    DeliveryStateConflict,
    DjangoNotificationDeliveryService,
    DjangoTelemetryCatalogService,
    DjangoTelemetryQueryService,
    NotificationChannelDirectory,
)
from apps.apm.services.access import (
    current_organization_id,
    filter_current_organization,
    validate_assignable_organizations,
)
from apps.apm.services.contracts import IngestSnippetRequest, MetricDataState, ServiceMetricQuery
from apps.apm.services.status import ACTIVE_WINDOW, ARCHIVE_WINDOW
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.user_group import normalize_user_group_ids


def _notification_actor_context(request, organization_id: int) -> dict:
    include_children = request.COOKIES.get("include_children", "0") == "1"
    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": organization_id,
        "include_children": include_children,
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


class ApmIngestSourceViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmIngestSourceSerializer
    service = DjangoIngestSourceService()

    def get_queryset(self) -> QuerySet[ApmIngestSource]:
        queryset = ApmIngestSource.objects.prefetch_related("organization_links")
        return filter_current_organization(queryset, self.request, "organization_links")

    @HasPermission("integration_add-View,integration_instances-View")
    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @HasPermission("integration_add-View,integration_instances-View")
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)

    @HasPermission("integration_add-Operate")
    def create(self, request, *args, **kwargs):
        serializer = CreateIngestSourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            validate_assignable_organizations(request, data["organization_ids"])
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        created = self.service.create(
            name=data["name"],
            ingest_type=data["ingest_type"],
            organization_ids=data["organization_ids"],
            actor=request.user.username,
            cloud_region_id=data.get("cloud_region_id"),
            environment_hint=data.get("environment_hint", ""),
        )
        response_data = ApmIngestSourceSerializer(created.source).data
        response_data["credential"] = created.credential
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(methods=("post",), detail=True)
    @HasPermission("integration_add-Operate")
    def rotate(self, request, *args, **kwargs):
        source = self.get_object()
        created = self.service.rotate(source.id, actor=request.user.username)
        response_data = self.get_serializer(created.source).data
        response_data["credential"] = created.credential
        return Response(response_data)

    @action(methods=("post",), detail=True)
    @HasPermission("integration_add-Operate")
    def disable(self, request, *args, **kwargs):
        source = self.get_object()
        disabled = self.service.disable(source.id, actor=request.user.username)
        return Response(self.get_serializer(disabled).data)

    @action(methods=("post",), detail=True)
    @HasPermission("integration_add-Operate")
    def snippet(self, request, *args, **kwargs):
        # 创建向导允许把接入源直接分配给用户可管理、但并非当前选中的组织。
        # 这里不能复用按 current_team 过滤的 get_object()，否则刚返回的一次性
        # 凭证会在同一个向导中立即变成不可验证。凭证本身仍需匹配目标 source，
        # 同时用公开的可分配组织校验约束控制面访问范围。
        source = get_object_or_404(
            ApmIngestSource.objects.prefetch_related("organization_links"),
            pk=kwargs["pk"],
        )
        organization_ids = list(source.organization_links.values_list("organization", flat=True))
        try:
            validate_assignable_organizations(request, organization_ids)
        except PermissionError:
            # 与常规 detail 路由保持一致，不向越权调用方泄漏资源是否存在。
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = IngestSnippetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credential_source = self.service.validate_credential(data["credential"])
        if credential_source is None or credential_source.id != source.id:
            raise ValidationError({"credential": ["接入凭证无效或已失效。"]})
        snippet = self.service.render_snippet(
            IngestSnippetRequest(
                language=data["language"],
                runtime=data["runtime"],
                endpoint=data["endpoint"],
                service_namespace=data["service_namespace"],
                service_name=data["service_name"],
                environment=data["environment"],
                credential=data["credential"],
                ingest_type=source.ingest_type,
            )
        )
        return Response({"environment": snippet.environment, "code": snippet.code})

    @action(methods=("put",), detail=True, url_path="organizations")
    @HasPermission("integration_add-Operate")
    def organizations(self, request, *args, **kwargs):
        source = self.get_object()
        serializer = OrganizationAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_ids = serializer.validated_data["organization_ids"]
        try:
            validate_assignable_organizations(request, organization_ids)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated = self.service.set_organizations(
            source.id,
            organization_ids,
            actor=request.user.username,
        )
        return Response(self.get_serializer(updated).data)


class ApmServiceViewSet(viewsets.ReadOnlyModelViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmServiceSerializer
    catalog = DjangoTelemetryCatalogService()

    def get_queryset(self) -> QuerySet[ApmService]:
        queryset = ApmService.objects.prefetch_related(
            "organization_links",
            Prefetch("instances", queryset=ApmServiceInstance.objects.order_by("environment", "id")),
        )
        if self.action != "restore" and self.request.query_params.get("include_archived") != "true":
            queryset = queryset.filter(archived_at__isnull=True)
        environment = self.request.query_params.get("environment")
        if self.action == "list" and environment is not None:
            queryset = queryset.filter(instances__environment=environment)
        return filter_current_organization(queryset, self.request, "organization_links")

    @HasPermission("services-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("services-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(methods=("put",), detail=True, url_path="organizations")
    @HasPermission("services-Operate")
    def organizations(self, request, *args, **kwargs):
        service = self.get_object()
        serializer = OrganizationAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_ids = serializer.validated_data["organization_ids"]
        try:
            validate_assignable_organizations(request, organization_ids)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated = self.catalog.set_service_organizations(
            service.id,
            organization_ids,
            actor=request.user.username,
        )
        return Response(self.get_serializer(updated).data)

    @action(methods=("post",), detail=True)
    @HasPermission("services-Operate")
    def archive(self, request, *args, **kwargs):
        service = self.get_object()
        archived = self.catalog.archive_service(
            service.id,
            reason=str(request.data.get("reason", "manual")),
            actor=request.user.username,
        )
        return Response(self.get_serializer(archived).data)

    @action(methods=("post",), detail=True)
    @HasPermission("services-Operate")
    def restore(self, request, *args, **kwargs):
        service = self.get_object()
        restored = self.catalog.restore_service(service.id, actor=request.user.username)
        return Response(self.get_serializer(restored).data)

    @action(methods=("get",), detail=True)
    @HasPermission("services-View")
    def metrics(self, request, *args, **kwargs):
        service = self.get_object()
        serializer = ServiceMetricQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        query = ServiceMetricQuery(
            service_namespace=service.namespace,
            service_name=service.name,
            environment=data["environment"],
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            include_breakdown=True,
        )
        try:
            red = DjangoTelemetryQueryService(VictoriaMetricsMetricStore()).service_red(query)
        except ValueError as exc:
            return Response(
                {"code": "invalid_query", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"detail": str(exc), "code": "telemetry_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "service_id": str(service.id),
                "environment": data["environment"],
                "started_at": data["started_at"],
                "ended_at": data["ended_at"],
                "data_state": str(
                    MetricDataState.NO_DATA if red.request_rate is None else MetricDataState.AVAILABLE
                ),
                "request_rate": red.request_rate,
                "error_rate": red.error_rate,
                "p95_ms": red.p95_ms,
                "p99_ms": red.p99_ms,
                "timeseries": [
                    {
                        "timestamp": point.timestamp,
                        "request_rate": point.request_rate,
                        "error_rate": point.error_rate,
                        "p95_ms": point.p95_ms,
                        "p99_ms": point.p99_ms,
                    }
                    for point in red.timeseries
                ],
                "top_endpoints": [
                    {
                        "endpoint": endpoint.endpoint,
                        "request_rate": endpoint.request_rate,
                        "error_rate": endpoint.error_rate,
                        "p95_ms": endpoint.p95_ms,
                        "p99_ms": endpoint.p99_ms,
                    }
                    for endpoint in red.top_endpoints
                ],
            }
        )


class ApmServiceInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmServiceInstanceSerializer
    catalog = DjangoTelemetryCatalogService()

    def get_queryset(self) -> QuerySet[ApmServiceInstance]:
        queryset = ApmServiceInstance.objects.select_related("service", "ingest_source").prefetch_related(
            "organization_links"
        )
        requested_status = self.request.query_params.get("status")
        if (
            self.action != "restore"
            and requested_status != "archived"
            and self.request.query_params.get("include_archived") != "true"
        ):
            queryset = queryset.filter(archived_at__isnull=True)
        environment = self.request.query_params.get("environment")
        if environment is not None:
            queryset = queryset.filter(environment=environment)
        now = timezone.now()
        if requested_status == "active":
            queryset = queryset.filter(archived_at__isnull=True, last_seen_at__gte=now - ACTIVE_WINDOW)
        elif requested_status == "silent":
            queryset = queryset.filter(
                archived_at__isnull=True,
                last_seen_at__lt=now - ACTIVE_WINDOW,
                last_seen_at__gt=now - ARCHIVE_WINDOW,
            )
        elif requested_status == "archived":
            queryset = queryset.filter(archived_at__isnull=False)
        return filter_current_organization(queryset, self.request, "organization_links")

    @HasPermission("integration_instances-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("integration_instances-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(methods=("put",), detail=True, url_path="organizations")
    @HasPermission("integration_instances-Operate")
    def organizations(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = OrganizationAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_ids = serializer.validated_data["organization_ids"]
        try:
            validate_assignable_organizations(request, organization_ids)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated = self.catalog.set_instance_organizations(
            instance.id,
            organization_ids,
            actor=request.user.username,
        )
        return Response(self.get_serializer(updated).data)

    @action(methods=("post",), detail=True)
    @HasPermission("integration_instances-Operate")
    def archive(self, request, *args, **kwargs):
        instance = self.get_object()
        archived = self.catalog.archive_instance(
            instance.id,
            reason=str(request.data.get("reason", "manual")),
            actor=request.user.username,
        )
        return Response(self.get_serializer(archived).data)

    @action(methods=("post",), detail=True)
    @HasPermission("integration_instances-Operate")
    def restore(self, request, *args, **kwargs):
        instance = self.get_object()
        restored = self.catalog.restore_instance(instance.id, actor=request.user.username)
        return Response(self.get_serializer(restored).data)


class ApmPolicyViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmPolicySerializer
    notification_directory = NotificationChannelDirectory()

    @staticmethod
    def _service():
        return DjangoApmPolicyService(VictoriaMetricsMetricStore(), SystemMgmtNotificationDispatcher())

    def get_queryset(self):
        queryset = ApmPolicy.objects.select_related("service", "state").prefetch_related(
            "service__organization_links",
            "notification_targets",
        )
        return filter_current_organization(queryset, self.request, "service__organization_links")

    def _visible_service(self, service_id):
        queryset = filter_current_organization(
            ApmService.objects.all(),
            self.request,
            "organization_links",
        )
        return get_object_or_404(queryset, id=service_id)

    @staticmethod
    def _pop_notification_fields(data):
        notification_targets = data.pop("notification_targets", None)
        notice = data.pop("notice", None)
        if notification_targets is not None:
            notice = bool(notification_targets)
        return {
            "notice": notice,
            "notification_targets": notification_targets,
            "notice_type_ids": data.pop("notice_type_ids", None),
            "notice_users": data.pop("notice_users", None),
        }

    def _validate_notification_channels(self, serializer, policy=None):
        data = serializer.validated_data
        notification_fields = {"notice", "notification_targets", "notice_type_ids", "notice_users"}
        if policy is not None and not notification_fields.intersection(data):
            return None
        requested_targets = data.get("notification_targets")
        notice = (
            bool(requested_targets)
            if requested_targets is not None
            else data.get("notice", getattr(policy, "notice", False))
        )
        if not notice:
            return []
        if requested_targets is None:
            legacy_channel_ids = data.get("notice_type_ids")
            if legacy_channel_ids is None and policy is not None:
                requested_targets = [
                    {"channel_id": target.channel_id, "recipients": list(target.recipients)}
                    for target in policy.notification_targets.all()
                ]
            else:
                legacy_recipients = data.get("notice_users", getattr(policy, "notice_users", []))
                requested_targets = [
                    {"channel_id": channel_id, "recipients": list(legacy_recipients or [])}
                    for channel_id in legacy_channel_ids or []
                ]
        if not requested_targets:
            raise ValidationError({"notification_targets": "启用通知时至少选择一个渠道。"})
        organization_id = current_organization_id(self.request)
        if organization_id is None:
            raise ValidationError({"notification_targets": "缺少当前组织。"})
        actor_context = _notification_actor_context(self.request, organization_id)
        try:
            channels = self.notification_directory.list_available(
                actor_context=actor_context,
                organization_id=organization_id,
                include_children=actor_context["include_children"],
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), "code": "notification_channels_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        allowed = {channel.id: channel for channel in channels if channel.availability == "available"}
        normalized_targets = []
        for target in requested_targets:
            channel = allowed.get(int(target["channel_id"]))
            if channel is None:
                raise ValidationError({"notification_targets": "包含当前组织不可用的通知渠道。"})
            recipients = [str(value).strip() for value in target.get("recipients", [])]
            if channel.recipient_mode == "none" and recipients:
                raise ValidationError({"notification_targets": f"渠道 {channel.name} 不接受接收人。"})
            if channel.recipient_mode != "none" and not recipients:
                raise ValidationError({"notification_targets": f"渠道 {channel.name} 必须配置接收人。"})
            if channel.recipient_mode == "system_user" and not all(value.isdigit() for value in recipients):
                raise ValidationError({"notification_targets": f"渠道 {channel.name} 只接受系统用户 ID。"})
            normalized_targets.append(
                {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "channel_type": channel.channel_type,
                    "delivery_mode": channel.delivery_mode,
                    "recipient_mode": channel.recipient_mode,
                    "recipients": recipients,
                }
            )
        return normalized_targets

    @staticmethod
    def _replace_notification_targets(policy, targets, *, actor):
        policy.notification_targets.all().delete()
        ApmPolicyNotificationTarget.objects.bulk_create(
            [
                ApmPolicyNotificationTarget(
                    policy=policy,
                    created_by=actor,
                    updated_by=actor,
                    **target,
                )
                for target in targets
            ]
        )

    @HasPermission("policies-View")
    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @HasPermission("policies-View")
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)

    @HasPermission("policies-Operate")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        targets = self._validate_notification_channels(serializer)
        if isinstance(targets, Response):
            return targets
        service_id = serializer.validated_data.pop("service_id")
        notification_data = self._pop_notification_fields(serializer.validated_data)
        with transaction.atomic():
            policy = serializer.save(
                service=self._visible_service(service_id),
                notice=bool(notification_data["notice"]),
                created_by=request.user.username,
                updated_by=request.user.username,
            )
            self._replace_notification_targets(policy, targets or [], actor=request.user.username)
            self._service().save_policy(policy)
        return Response(self.get_serializer(policy).data, status=status.HTTP_201_CREATED)

    @HasPermission("policies-Operate")
    def update(self, request, *args, **kwargs):
        policy = self.get_object()
        serializer = self.get_serializer(policy, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        targets = self._validate_notification_channels(serializer, policy)
        if isinstance(targets, Response):
            return targets
        service_id = serializer.validated_data.pop("service_id", None)
        notification_data = self._pop_notification_fields(serializer.validated_data)
        save_kwargs = {"updated_by": request.user.username}
        if service_id is not None:
            save_kwargs["service"] = self._visible_service(service_id)
        if notification_data["notice"] is not None:
            save_kwargs["notice"] = bool(notification_data["notice"])
        with transaction.atomic():
            policy = serializer.save(**save_kwargs)
            if targets is not None:
                self._replace_notification_targets(policy, targets, actor=request.user.username)
            state, _ = ApmPolicyState.objects.get_or_create(policy=policy)
            state.evaluation_cursor = ""
            state.consecutive_hits = 0
            state.consecutive_recoveries = 0
            state.save()
        return Response(self.get_serializer(policy).data)

    @HasPermission("policies-Operate")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("policies-Operate")
    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=("post",), detail=True)
    @HasPermission("policies-Operate")
    def enable(self, request, *args, **kwargs):
        policy = self.get_object()
        policy.is_enabled = True
        policy.updated_by = request.user.username
        policy.save(update_fields=("is_enabled", "updated_by", "updated_at"))
        return Response(self.get_serializer(policy).data)

    @action(methods=("post",), detail=True)
    @HasPermission("policies-Operate")
    def disable(self, request, *args, **kwargs):
        policy = self.get_object()
        policy.is_enabled = False
        policy.updated_by = request.user.username
        policy.save(update_fields=("is_enabled", "updated_by", "updated_at"))
        return Response(self.get_serializer(policy).data)

    @action(methods=("post",), detail=True, url_path="test-query")
    @HasPermission("policies-Operate")
    def test_query(self, request, *args, **kwargs):
        policy = self.get_object()
        try:
            result = self._service().test_query(policy, evaluated_at=timezone.now())
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"detail": str(exc), "code": "telemetry_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "value": str(result.value) if result.value is not None else None,
                "breached": result.breached,
                "evaluated_at": result.evaluated_at,
                "data_state": str(result.data_state),
            }
        )


class ApmEventViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    reader = DjangoApmEventReader()

    @HasPermission("events-View")
    def list(self, request, *args, **kwargs):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response([])
        serializer = ApmEventQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(self.reader.list(organization_id=organization_id, **serializer.validated_data))


class ApmNotificationChannelViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    directory = NotificationChannelDirectory()

    @HasPermission("policies-View")
    def list(self, request, *args, **kwargs):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response([])
        actor_context = _notification_actor_context(request, organization_id)
        try:
            channels = self.directory.list_available(
                actor_context=actor_context,
                organization_id=organization_id,
                include_children=actor_context["include_children"],
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), "code": "notification_channels_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response([asdict(channel) for channel in channels])


class ApmNotificationDeliveryViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    delivery_service = DjangoNotificationDeliveryService()

    def get_queryset(self):
        organization_id = current_organization_id(self.request)
        if organization_id is None:
            return ApmAlertOutbox.objects.none()
        return self.delivery_service.queryset(organization_id=organization_id)

    @HasPermission("events-View")
    def list(self, request, *args, **kwargs):
        serializer = NotificationDeliveryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = self.get_queryset()
        if data.get("event_id"):
            queryset = queryset.filter(event__event_id=data["event_id"])
        if data.get("status"):
            queryset = queryset.filter(delivery_status=data["status"])
        deliveries = queryset.order_by("-created_at", "-id")[: data["limit"]]
        return Response([self.delivery_service.serialize(delivery) for delivery in deliveries])

    @action(methods=("post",), detail=True)
    @HasPermission("policies-Operate")
    def retry(self, request, *args, **kwargs):
        delivery = self.get_object()
        serializer = NotificationDeliveryRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            retried = self.delivery_service.retry(
                delivery,
                actor=request.user.username,
                recipients=serializer.validated_data.get("recipients"),
            )
        except DeliveryStateConflict as exc:
            return Response(
                {"code": "state_conflict", "detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.delivery_service.serialize(retried))


class ApmNotificationRecipientViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    directory = NotificationChannelDirectory()

    @HasPermission("policies-View")
    def list(self, request, *args, **kwargs):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response([])
        serializer = NotificationRecipientQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        actor_context = _notification_actor_context(request, organization_id)
        try:
            recipients = self.directory.search_recipients(
                actor_context=actor_context,
                organization_id=organization_id,
                include_children=actor_context["include_children"],
                **serializer.validated_data,
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), "code": "notification_recipients_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response([asdict(recipient) for recipient in recipients])
