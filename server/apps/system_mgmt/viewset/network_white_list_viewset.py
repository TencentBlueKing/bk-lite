from rest_framework import viewsets

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import NetworkWhiteList
from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer
from apps.system_mgmt.utils.network_whitelist_cache import invalidate_network_whitelist_cache
from apps.system_mgmt.utils.operation_log_utils import log_operation


class NetworkWhiteListViewSet(viewsets.ModelViewSet):
    queryset = NetworkWhiteList.objects.all().order_by("-id")
    serializer_class = NetworkWhiteListSerializer

    def _user_domain(self):
        return getattr(self.request.user, "domain", "domain.com")

    def perform_create(self, serializer):
        username = self.request.user.username
        serializer.save(created_by=username, updated_by=username, domain=self._user_domain())

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.username)

    @HasPermission("network_white_list-View", "system-manager")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("network_white_list-View", "system-manager")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("network_white_list-Add", "system-manager")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "create", "system-manager", f"新增内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Edit", "system-manager")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "update", "system-manager", f"编辑内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Edit", "system-manager")
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "update", "system-manager", f"编辑内网白名单: {request.data.get('network', '')}")
        return response

    @HasPermission("network_white_list-Delete", "system-manager")
    def destroy(self, request, *args, **kwargs):
        instance_network = self.get_object().network
        response = super().destroy(request, *args, **kwargs)
        if 200 <= response.status_code < 300:
            invalidate_network_whitelist_cache()
            log_operation(request, "delete", "system-manager", f"删除内网白名单: {instance_network}")
        return response
