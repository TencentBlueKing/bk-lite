from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.response import Response

from apps.apm.models import ApmDeploymentEvent
from apps.apm.pagination import ApmDeploymentPagination
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import ApmDeploymentEventSerializer, ApmDeploymentQuerySerializer
from apps.apm.services.access import filter_current_organization
from apps.core.decorators.api_permission import HasPermission


class ApmDeploymentEventViewSet(viewsets.GenericViewSet):
    renderer_classes = (ApmRenderer,)
    serializer_class = ApmDeploymentEventSerializer
    pagination_class = ApmDeploymentPagination
    queryset = ApmDeploymentEvent.objects.none()

    def get_queryset(self) -> QuerySet[ApmDeploymentEvent]:
        queryset = (
            ApmDeploymentEvent.objects.filter(service__archived_at__isnull=True)
            .select_related("service")
            .order_by("-deployed_at", "-id")
        )
        return filter_current_organization(queryset, self.request, "service__organization_links")

    @HasPermission("services-View")
    def list(self, request, *args, **kwargs):
        serializer = ApmDeploymentQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = self.get_queryset().filter(
            deployed_at__gte=data["started_at"],
            deployed_at__lte=data["ended_at"],
        )
        if data.get("service_id"):
            queryset = queryset.filter(service_id=data["service_id"])
        if data.get("environment"):
            queryset = queryset.filter(environment=data["environment"])
        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)
