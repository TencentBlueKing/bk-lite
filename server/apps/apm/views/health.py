from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.response import Response

from apps.apm.renderers import ApmRenderer
from apps.apm.services.health import CATALOG_RECONCILE_HEALTH_KEY, pending_catalog_health
from apps.core.decorators.api_permission import HasPermission


class ApmHealthViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)
    @HasPermission("services-View,integration_instances-View")
    def list(self, request):
        return Response({"catalog_reconcile": cache.get(CATALOG_RECONCILE_HEALTH_KEY) or pending_catalog_health()})
