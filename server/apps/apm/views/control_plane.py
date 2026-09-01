from dataclasses import asdict

from django.db import transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.apm.adapters import SystemMgmtNotificationDispatcher, TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmApplication,
    ApmEventSnapshot,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmService,
    ApmServiceInstance,
    ApmSlo,
)
from apps.apm.pagination import ApmCatalogPagination
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import (
    ApmAlertQuerySerializer,
    ApmApplicationSerializer,
    ApmEventQuerySerializer,
    ApmPolicySerializer,
    ApmServiceInstanceSerializer,
    ApmServiceSerializer,
    ApmSloSerializer,
    ApplicationMutationSerializer,
    CatalogListQuerySerializer,
    IngestSnippetSerializer,
    InstanceCatalogListQuerySerializer,
    NotificationDeliveryQuerySerializer,
    NotificationDeliveryRetrySerializer,
    NotificationRecipientQuerySerializer,
    OrganizationAssignmentSerializer,
    ServiceMetricQuerySerializer,
)
from apps.apm.services import (
    ApmAlertMetricSnapshotStore,
    ApmEventSnapshotStore,
    DeliveryStateConflict,
    DjangoApmAlertService,
    DjangoApmApplicationService,
    DjangoApmEventReader,
    DjangoApmPolicyService,
    DjangoApmReliabilityService,
    DjangoIntegrationConfigurationService,
    DjangoNotificationDeliveryService,
    DjangoTelemetryCatalogService,
    DjangoTelemetryQueryService,
    NotificationChannelDirectory,
)
from apps.apm.services.access import current_organization_id, filter_current_organization, validate_assignable_organizations, visible_organization_ids
from apps.apm.services.contracts import IngestSnippetRequest, MetricDataState, ServiceMetricQuery
from apps.apm.services.integration_configuration import CloudRegionConfigurationError
from apps.apm.services.probe_artifacts import LANGUAGE_PROBE_ARTIFACTS
from apps.apm.services.status import ACTIVE_WINDOW, ARCHIVE_WINDOW
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import apm_logger as logger
from apps.core.utils.user_group import normalize_user_group_ids
from apps.rpc.node_mgmt import NodeMgmt

MAX_CATALOG_KEYWORD_TOKENS = 8


def _catalog_list_params(view) -> dict:
    if view.action != "list":
        return {}
    serializer_class = getattr(view, "list_query_serializer", CatalogListQuerySerializer)
    serializer = serializer_class(data=view.request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _filter_catalog_keyword(queryset, keyword: str, fields: tuple[str, ...]):
    for token in keyword.split()[:MAX_CATALOG_KEYWORD_TOKENS]:
        token_query = Q()
        for field in fields:
            token_query |= Q(**{f"{field}__icontains": token})
        queryset = queryset.filter(token_query)
    return queryset


def _filter_catalog_status(queryset, requested_status: str | None, include_archived: bool):
    now = timezone.now()
    if requested_status == "active":
        return queryset.filter(archived_at__isnull=True, last_seen_at__gte=now - ACTIVE_WINDOW)
    if requested_status == "silent":
        return queryset.filter(
            archived_at__isnull=True,
            last_seen_at__lt=now - ACTIVE_WINDOW,
            last_seen_at__gt=now - ARCHIVE_WINDOW,
        )
    if requested_status == "archived":
        return queryset.filter(archived_at__isnull=False)
    if not include_archived:
        return queryset.filter(archived_at__isnull=True)
    return queryset


def _filter_instance_status(queryset, requested_status: str | None):
    cutoff = timezone.now() - ACTIVE_WINDOW
    if requested_status == "active":
        return queryset.filter(last_seen_at__gte=cutoff)
    if requested_status == "silent":
        return queryset.filter(last_seen_at__lt=cutoff)
    return queryset


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


class ApmApplicationViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmApplicationSerializer
    service = DjangoApmApplicationService()

    def get_queryset(self) -> QuerySet[ApmApplication]:
        queryset = ApmApplication.objects.prefetch_related("organization_links").annotate(service_count=Count("services", distinct=True))
        organization_ids = visible_organization_ids(self.request)
        if not organization_ids:
            return queryset.none()
        return queryset.filter(organization_links__organization__in=organization_ids, is_builtin=False).distinct()

    @HasPermission("applications-View,integration_add-View,services-View,integration_instances-View")
    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @HasPermission("applications-View,integration_add-View")
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)

    @HasPermission("applications-Operate")
    def create(self, request, *args, **kwargs):
        serializer = ApplicationMutationSerializer(data=request.data, context={"creating": True})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            validate_assignable_organizations(request, data["organization_ids"])
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        application = self.service.create(
            application_id=data["application_id"],
            name=data["name"],
            description=data.get("description", ""),
            organization_ids=data["organization_ids"],
            actor=request.user.username,
        )
        return Response(self.get_serializer(application).data, status=status.HTTP_201_CREATED)

    @HasPermission("applications-Operate")
    def update(self, request, *args, **kwargs):
        application = self.get_object()
        payload = {key: value for key, value in request.data.items() if key != "application_id"}
        serializer = ApplicationMutationSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            validate_assignable_organizations(request, data["organization_ids"])
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        updated = self.service.update(
            application.id,
            name=data["name"],
            description=data.get("description", ""),
            organization_ids=data["organization_ids"],
            actor=request.user.username,
        )
        return Response(self.get_serializer(updated).data)

    partial_update = update


class ApmIntegrationConfigurationViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    service = DjangoIntegrationConfigurationService()

    @action(methods=("get",), detail=False)
    @HasPermission("integration_add-View")
    def regions(self, request, *args, **kwargs):
        try:
            return Response(self.service.list_regions(NodeMgmt()))
        except CloudRegionConfigurationError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.warning("APM cloud region listing failed: %s", type(exc).__name__)
            return Response(
                {"code": "cloud_region_unavailable", "detail": "云区域目录暂时不可用，请稍后重试。"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @HasPermission("integration_add-View")
    def create(self, request, *args, **kwargs):
        serializer = IngestSnippetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response({"detail": "当前组织不在用户授权范围内。"}, status=status.HTTP_403_FORBIDDEN)
        applications = filter_current_organization(
            ApmApplication.objects.filter(is_builtin=False),
            request,
            "organization_links",
        )
        application = get_object_or_404(applications, application_id=data["application_id"])
        probe_artifact_name = LANGUAGE_PROBE_ARTIFACTS.get(data["language"], "")
        try:
            endpoints = self.service.resolve_region(
                NodeMgmt(),
                data["cloud_region_id"],
                organization_ids=[organization_id],
                include_probe_download=bool(probe_artifact_name),
                probe_artifact_name=probe_artifact_name,
            )
        except CloudRegionConfigurationError as exc:
            response_status = (
                status.HTTP_404_NOT_FOUND
                if exc.code in {"cloud_region_not_found", "cloud_region_receiver_unavailable", "probe_download_unavailable"}
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"code": exc.code, "detail": exc.detail}, status=response_status)
        except Exception as exc:
            logger.warning("APM cloud region endpoint resolution failed: %s", type(exc).__name__)
            return Response(
                {"code": "cloud_region_unavailable", "detail": "云区域配置暂时不可用，请稍后重试。"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        snippet = self.service.render_snippet(
            IngestSnippetRequest(
                language=data["language"],
                runtime=data["runtime"],
                endpoint=endpoints.http_endpoint,
                service_namespace=application.application_id,
                service_name=data["service_name"],
                service_version=data.get("service_version", ""),
                environment=data["environment"],
                probe_download_url=endpoints.probe_download_url,
            )
        )
        return Response(
            {
                "application_id": application.application_id,
                "application_name": application.name,
                "cloud_region": {"id": endpoints.region_id, "name": endpoints.region_name},
                "http_endpoint": f"{endpoints.http_endpoint}/v1/traces",
                "environment": snippet.environment,
                "code": snippet.code,
            }
        )


class ApmServiceViewSet(viewsets.ReadOnlyModelViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmServiceSerializer
    catalog = DjangoTelemetryCatalogService()
    pagination_class = ApmCatalogPagination

    def get_queryset(self) -> QuerySet[ApmService]:
        params = _catalog_list_params(self)
        queryset = (
            ApmService.objects.filter(application__isnull=False)
            .select_related("application")
            .prefetch_related(
                "organization_links",
                Prefetch("instances", queryset=ApmServiceInstance.objects.order_by("environment", "id")),
            )
        )
        if self.action == "list":
            queryset = _filter_catalog_status(queryset, params.get("status"), params["include_archived"])
            if params.get("application"):
                queryset = queryset.filter(application__application_id=params["application"])
            if params.get("environment"):
                queryset = queryset.filter(instances__environment=params["environment"])
            if params.get("started_at"):
                queryset = queryset.filter(last_seen_at__gte=params["started_at"])
            if params.get("ended_at"):
                queryset = queryset.filter(last_seen_at__lte=params["ended_at"])
            if params.get("keyword"):
                queryset = _filter_catalog_keyword(
                    queryset,
                    params["keyword"],
                    ("namespace", "name", "application__application_id", "application__name"),
                )
        elif self.action != "restore" and self.request.query_params.get("include_archived") != "true":
            queryset = queryset.filter(archived_at__isnull=True)
        return filter_current_organization(queryset, self.request, "organization_links").distinct().order_by("-last_seen_at", "id")

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
            endpoint=data["endpoint"],
        )
        try:
            red = DjangoTelemetryQueryService(VictoriaTracesTelemetryStore()).service_red(query)
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
                "data_state": str(MetricDataState.NO_DATA if red.request_rate is None else MetricDataState.AVAILABLE),
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
    pagination_class = ApmCatalogPagination
    list_query_serializer = InstanceCatalogListQuerySerializer

    def get_queryset(self) -> QuerySet[ApmServiceInstance]:
        params = _catalog_list_params(self)
        queryset = (
            ApmServiceInstance.objects.filter(service__application__isnull=False)
            .select_related("service", "service__application")
            .prefetch_related("organization_links")
        )
        if self.action == "list":
            queryset = _filter_instance_status(queryset, params.get("status"))
            if params.get("application"):
                queryset = queryset.filter(service__application__application_id=params["application"])
            if params.get("environment"):
                queryset = queryset.filter(environment=params["environment"])
            if params.get("started_at"):
                queryset = queryset.filter(last_seen_at__gte=params["started_at"])
            if params.get("ended_at"):
                queryset = queryset.filter(last_seen_at__lte=params["ended_at"])
            if params.get("keyword"):
                queryset = _filter_catalog_keyword(
                    queryset,
                    params["keyword"],
                    (
                        "service__namespace",
                        "service__name",
                        "service__application__application_id",
                        "service__application__name",
                        "instance_id",
                        "environment",
                        "version",
                    ),
                )
        return filter_current_organization(queryset, self.request, "organization_links").order_by("-last_seen_at", "id")

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


class ApmSloViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmSloSerializer

    @staticmethod
    def _service():
        return DjangoApmReliabilityService(VictoriaTracesTelemetryStore())

    def get_queryset(self):
        queryset = ApmSlo.objects.select_related("service").prefetch_related("service__organization_links")
        return filter_current_organization(queryset, self.request, "service__organization_links")

    def _visible_service(self, service_id):
        queryset = filter_current_organization(
            ApmService.objects.all(),
            self.request,
            "organization_links",
        )
        return get_object_or_404(queryset, id=service_id)

    def _serialize(self, slo):
        data = self.get_serializer(slo).data
        try:
            evaluation = self._service().evaluate(slo, evaluated_at=timezone.now())
            data.update(asdict(evaluation))
        except (TelemetryStoreUnavailable, ValueError) as exc:
            data.update(
                {
                    "current_rate": None,
                    "budget_remaining": None,
                    "data_state": "unavailable",
                    "started_at": None,
                    "ended_at": timezone.now(),
                    "reason": str(exc),
                }
            )
        return data

    @HasPermission("services-View")
    def list(self, request, *args, **kwargs):
        return Response([self._serialize(slo) for slo in self.get_queryset()[:200]])

    @HasPermission("services-View")
    def retrieve(self, request, *args, **kwargs):
        return Response(self._serialize(self.get_object()))

    @HasPermission("services-Operate")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        service = self._visible_service(data.pop("service_id"))
        slo = ApmSlo.objects.create(
            service=service,
            created_by=request.user.username,
            updated_by=request.user.username,
            **data,
        )
        return Response(self._serialize(slo), status=status.HTTP_201_CREATED)

    def _update(self, request, *, partial):
        slo = self.get_object()
        serializer = self.get_serializer(slo, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        service_id = data.pop("service_id", None)
        if service_id is not None:
            slo.service = self._visible_service(service_id)
        for field, value in data.items():
            setattr(slo, field, value)
        slo.updated_by = request.user.username
        slo.save()
        return Response(self._serialize(slo))

    @HasPermission("services-Operate")
    def update(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    @HasPermission("services-Operate")
    def partial_update(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    @HasPermission("services-Operate")
    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _set_enabled(self, request, *, enabled):
        slo = self.get_object()
        slo.is_enabled = enabled
        slo.updated_by = request.user.username
        slo.save(update_fields=("is_enabled", "updated_by", "updated_at"))
        return Response(self._serialize(slo))

    @action(methods=("post",), detail=True)
    @HasPermission("services-Operate")
    def enable(self, request, *args, **kwargs):
        return self._set_enabled(request, enabled=True)

    @action(methods=("post",), detail=True)
    @HasPermission("services-Operate")
    def disable(self, request, *args, **kwargs):
        return self._set_enabled(request, enabled=False)


class ApmPolicyViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmPolicySerializer
    notification_directory = NotificationChannelDirectory()

    @staticmethod
    def _service():
        return DjangoApmPolicyService(VictoriaTracesTelemetryStore(), SystemMgmtNotificationDispatcher())

    def get_queryset(self):
        queryset = ApmPolicy.objects.select_related("service").prefetch_related(
            "service__organization_links",
            "notification_targets",
            "target_states",
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
        if "notification_targets" not in data:
            if policy is None:
                return []
            return None
        requested_targets = data.get("notification_targets")
        if not requested_targets:
            return []
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
        serializer.validated_data.pop("notification_targets", None)
        with transaction.atomic():
            policy = serializer.save(
                service=self._visible_service(service_id),
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
        serializer.validated_data.pop("notification_targets", None)
        save_kwargs = {"updated_by": request.user.username}
        if service_id is not None:
            save_kwargs["service"] = self._visible_service(service_id)
        with transaction.atomic():
            policy = serializer.save(**save_kwargs)
            if targets is not None:
                self._replace_notification_targets(policy, targets, actor=request.user.username)
            policy.target_states.all().delete()
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
                "threshold": getattr(result, "threshold", None),
                "series": [
                    {
                        "timestamp": point.timestamp,
                        "request_rate": point.request_rate,
                        "error_rate": point.error_rate,
                        "p95_ms": point.p95_ms,
                        "p99_ms": point.p99_ms,
                    }
                    for point in getattr(result, "series", ())
                ],
            }
        )

    @action(methods=("post",), detail=False)
    @HasPermission("policies-Operate")
    def preview(self, request, *args, **kwargs):
        payload = dict(request.data)
        payload["notification_targets"] = []
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        service_id = values.pop("service_id")
        values.pop("notification_targets", None)
        policy = ApmPolicy(service=self._visible_service(service_id), **values)
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
                "threshold": result.threshold,
                "series": [
                    {
                        "timestamp": point.timestamp,
                        "request_rate": point.request_rate,
                        "error_rate": point.error_rate,
                        "p95_ms": point.p95_ms,
                        "p99_ms": point.p99_ms,
                    }
                    for point in result.series
                ],
            }
        )


class ApmEventViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    reader = DjangoApmEventReader()

    @HasPermission("events-View")
    def list(self, request, *args, **kwargs):
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
            return Response([])
        serializer = ApmEventQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(self.reader.list(organization_ids=organization_ids, **serializer.validated_data))


class ApmAlertViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    alert_service = DjangoApmAlertService()

    def get_queryset(self):
        organization_ids = visible_organization_ids(self.request)
        if not organization_ids:
            return ApmAlert.objects.none()
        return self.alert_service.queryset(organization_ids=organization_ids)

    @HasPermission("events-View")
    def list(self, request, *args, **kwargs):
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
            return Response([])
        serializer = ApmAlertQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(self.alert_service.list(organization_ids=organization_ids, **serializer.validated_data))

    @HasPermission("events-View")
    def retrieve(self, request, *args, **kwargs):
        return Response(self.alert_service.serialize(self.get_object()))

    @action(methods=("get",), detail=False)
    @HasPermission("events-View")
    def distribution(self, request, *args, **kwargs):
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
            return Response([])
        serializer = ApmAlertQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            self.alert_service.distribution(
                organization_ids=organization_ids,
                started_at=data["started_at"],
                ended_at=data["ended_at"],
                status_group=data.get("status_group"),
            )
        )

    @action(methods=("post",), detail=True)
    @HasPermission("policies-Operate")
    def close(self, request, *args, **kwargs):
        alert = self.get_object()
        closed = self.alert_service.close(
            alert,
            actor=request.user.username,
            occurred_at=timezone.now(),
        )
        return Response(self.alert_service.serialize(closed))

    @action(methods=("get",), detail=True)
    @HasPermission("events-View")
    def snapshots(self, request, *args, **kwargs):
        alert = self.get_object()
        snapshot = getattr(alert, "metric_snapshot", None)
        if snapshot is None:
            return Response({"snapshots": []})
        return Response(ApmAlertMetricSnapshotStore.serialize(snapshot))

    @action(methods=("get",), detail=True, url_path="event-evidence")
    @HasPermission("events-View")
    def event_evidence(self, request, *args, **kwargs):
        alert = self.get_object()
        event_id = request.query_params.get("event_id", "").strip()
        queryset = ApmEventSnapshot.objects.filter(alert=alert).select_related("payload", "event")
        if event_id:
            queryset = queryset.filter(source_event_id=event_id)
        return Response([ApmEventSnapshotStore.serialize(snapshot) for snapshot in queryset.order_by("occurred_at", "id")[:100]])


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
        organization_ids = visible_organization_ids(self.request)
        if not organization_ids:
            return ApmAlertOutbox.objects.none()
        return self.delivery_service.queryset(organization_ids=organization_ids)

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
