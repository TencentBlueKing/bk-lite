from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.response import Response

from apps.apm.renderers import ApmRenderer
from apps.apm.services.health import (
    HEALTH_COMPONENT_KEYS,
    RUNTIME_DEPENDENCIES_HEALTH_KEY,
    pending_catalog_health,
    pending_runtime_dependencies_health,
)
from apps.core.decorators.api_permission import HasPermission


class ApmHealthViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)

    @HasPermission("services-View,integration_instances-View")
    def list(self, request):
        dependencies = cache.get(RUNTIME_DEPENDENCIES_HEALTH_KEY) or pending_runtime_dependencies_health()
        health = dict(dependencies)
        for component, cache_key in HEALTH_COMPONENT_KEYS.items():
            health[component] = cache.get(cache_key) or pending_catalog_health()
        return Response(health)
