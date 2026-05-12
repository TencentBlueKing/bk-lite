from rest_framework import status
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.node_mgmt.filters.child_config import ChildConfigFilter
from apps.node_mgmt.models import ChildConfig
from apps.node_mgmt.serializers.child_config import ChildConfigSerializer
from apps.node_mgmt.utils.permission import (
    authorize_mutable_child_config_ids,
    authorize_mutable_collector_configuration_ids,
    get_authorized_child_config_queryset,
    get_mutable_child_config_queryset,
)


class ChildConfigViewSet(MaintainerViewSet):
    queryset = ChildConfig.objects.all()
    serializer_class = ChildConfigSerializer
    filterset_class = ChildConfigFilter

    def get_queryset(self):
        if self.action in {"update", "partial_update", "destroy"}:
            return get_mutable_child_config_queryset(self.request)
        return get_authorized_child_config_queryset(self.request)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collector_config = serializer.validated_data["collector_config"]
        _, error_response = authorize_mutable_collector_configuration_ids(request, [collector_config.id])
        if error_response:
            return error_response
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def update(self, request, *args, **kwargs):
        return self._update(request, partial=False, *args, **kwargs)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def partial_update(self, request, *args, **kwargs):
        return self._update(request, partial=True, *args, **kwargs)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def destroy(self, request, *args, **kwargs):
        _, error_response = authorize_mutable_child_config_ids(request, [kwargs["pk"]])
        if error_response:
            return error_response
        return super().destroy(request, *args, **kwargs)

    def _update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        collector_config = serializer.validated_data.get("collector_config")
        if collector_config and collector_config.id != instance.collector_config_id:
            return Response({"result": False, "message": "collector_config cannot be modified"}, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)
