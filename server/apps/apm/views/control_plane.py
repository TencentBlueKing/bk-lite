from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.apm.models import ApmIngestSource, ApmPolicy, ApmPolicyState, ApmService, ApmServiceInstance
from apps.apm.serializers import (
    ApmEventQuerySerializer,
    ApmIngestSourceSerializer,
    ApmPolicySerializer,
    ApmServiceInstanceSerializer,
    ApmServiceSerializer,
    CreateIngestSourceSerializer,
    OrganizationAssignmentSerializer,
    ServiceMetricQuerySerializer,
)
from apps.apm.adapters import AlertsNatsPublisher, TelemetryStoreUnavailable, VictoriaMetricsMetricStore
from apps.apm.services import (
    AlertsUnavailable,
    DjangoApmEventReader,
    DjangoApmPolicyService,
    DjangoIngestSourceService,
    DjangoTelemetryCatalogService,
    DjangoTelemetryQueryService,
)
from apps.apm.services.access import current_organization_id, filter_current_organization, validate_assignable_organizations
from apps.apm.services.contracts import ServiceMetricQuery
from apps.apm.services.status import ACTIVE_WINDOW, ARCHIVE_WINDOW
from apps.core.decorators.api_permission import HasPermission


class ApmIngestSourceViewSet(viewsets.GenericViewSet):
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
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        query = ServiceMetricQuery(
            service_namespace=service.namespace,
            service_name=service.name,
            environment=data["environment"],
            started_at=data["started_at"],
            ended_at=data["ended_at"],
        )
        try:
            red = DjangoTelemetryQueryService(VictoriaMetricsMetricStore()).service_red(query)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
            }
        )


class ApmServiceInstanceViewSet(viewsets.ReadOnlyModelViewSet):
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
    serializer_class = ApmPolicySerializer

    @staticmethod
    def _service():
        return DjangoApmPolicyService(VictoriaMetricsMetricStore(), AlertsNatsPublisher())

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
    reader = DjangoApmEventReader()

    @HasPermission("events-View")
    def list(self, request, *args, **kwargs):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response([])
        serializer = ApmEventQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            events = self.reader.list(organization_id=organization_id, **serializer.validated_data)
        except AlertsUnavailable as exc:
            return Response(
                {"detail": str(exc), "code": "alerts_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(events)
