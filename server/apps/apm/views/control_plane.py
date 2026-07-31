from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.apm.models import ApmIngestSource, ApmPolicy, ApmPolicyState, ApmService, ApmServiceInstance
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import (
    ApmEventQuerySerializer,
    ApmIngestSourceSerializer,
    ApmPolicySerializer,
    ApmServiceInstanceSerializer,
    ApmServiceSerializer,
    CreateIngestSourceSerializer,
    IngestSnippetSerializer,
    OrganizationAssignmentSerializer,
    ServiceMetricQuerySerializer,
)
from apps.apm.adapters import SystemMgmtNatsAlertPublisher, TelemetryStoreUnavailable, VictoriaMetricsMetricStore
from apps.apm.services import (
    DjangoApmEventReader,
    DjangoApmPolicyService,
    DjangoIngestSourceService,
    DjangoTelemetryCatalogService,
    DjangoTelemetryQueryService,
    NotificationChannelDirectory,
)
from apps.apm.services.access import (
    current_organization_id,
    filter_current_organization,
    validate_assignable_organizations,
)
from apps.apm.services.contracts import IngestSnippetRequest, ServiceMetricQuery
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
        source = self.get_object()
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
        return DjangoApmPolicyService(VictoriaMetricsMetricStore(), SystemMgmtNatsAlertPublisher())

    def get_queryset(self):
        queryset = ApmPolicy.objects.select_related("service", "state").prefetch_related(
            "service__organization_links"
        )
        return filter_current_organization(queryset, self.request, "service__organization_links")

    def _visible_service(self, service_id):
        queryset = filter_current_organization(
            ApmService.objects.all(),
            self.request,
            "organization_links",
        )
        return get_object_or_404(queryset, id=service_id)

    def _validate_notification_channels(self, serializer, policy=None):
        data = serializer.validated_data
        if policy is not None and not {"notice", "notice_type_ids", "service_id"}.intersection(data):
            return None
        notice = data.get("notice", getattr(policy, "notice", False))
        channel_ids = data.get("notice_type_ids", getattr(policy, "notice_type_ids", []))
        if not notice:
            return None
        organization_id = current_organization_id(self.request)
        if organization_id is None:
            raise ValidationError({"notice_type_ids": "缺少当前组织。"})
        actor_context = _notification_actor_context(self.request, organization_id)
        try:
            channels = self.notification_directory.list_alert_event_channels(
                actor_context=actor_context,
                organization_id=organization_id,
                include_children=actor_context["include_children"],
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), "code": "notification_channels_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        allowed_ids = {int(channel["id"]) for channel in channels}
        if not set(channel_ids).issubset(allowed_ids):
            raise ValidationError({"notice_type_ids": "包含当前组织不可用的告警中心渠道。"})
        return None

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
        notification_error = self._validate_notification_channels(serializer)
        if notification_error is not None:
            return notification_error
        service_id = serializer.validated_data.pop("service_id")
        policy = serializer.save(
            service=self._visible_service(service_id),
            created_by=request.user.username,
            updated_by=request.user.username,
        )
        self._service().save_policy(policy)
        return Response(self.get_serializer(policy).data, status=status.HTTP_201_CREATED)

    @HasPermission("policies-Operate")
    def update(self, request, *args, **kwargs):
        policy = self.get_object()
        serializer = self.get_serializer(policy, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        notification_error = self._validate_notification_channels(serializer, policy)
        if notification_error is not None:
            return notification_error
        service_id = serializer.validated_data.pop("service_id", None)
        save_kwargs = {"updated_by": request.user.username}
        if service_id is not None:
            save_kwargs["service"] = self._visible_service(service_id)
        policy = serializer.save(**save_kwargs)
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
                "value": str(result.value),
                "breached": result.breached,
                "evaluated_at": result.evaluated_at,
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
            channels = self.directory.list_alert_event_channels(
                actor_context=actor_context,
                organization_id=organization_id,
                include_children=actor_context["include_children"],
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), "code": "notification_channels_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(channels)
