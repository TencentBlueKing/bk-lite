from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import NetworkWhiteList
from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer
from apps.system_mgmt.utils.network_whitelist_cache import invalidate_network_whitelist_cache
from apps.system_mgmt.utils.operation_log_utils import log_operation


class NetworkWhiteListViewSet(viewsets.ModelViewSet):
    queryset = NetworkWhiteList.objects.all().order_by("-id")
    serializer_class = NetworkWhiteListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(is_build_in=False) if self.action == "list" else queryset

    def _user_domain(self):
        return getattr(self.request.user, "domain", "domain.com")

    def _label(self, instance: NetworkWhiteList) -> str:
        """用于日志和错误提示的标识"""
        return instance.domain_name or instance.network or f"id={instance.pk}"

    def _refuse_builtin(self, instance: NetworkWhiteList):
        """内置条目不可修改/删除"""
        return Response(
            {
                "result": False,
                "message": f"内置条目不可修改或删除: {self._label(instance)}",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

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
        if response.status_code == 201:
            invalidate_network_whitelist_cache()
            log_operation(request, "create", "system-manager", f"新增内网白名单: {self._label_from_response(response)}")
        return response

    @HasPermission("network_white_list-Edit", "system-manager")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            return self._refuse_builtin(instance)
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            invalidate_network_whitelist_cache()
            log_operation(request, "update", "system-manager", f"编辑内网白名单: {self._label(instance)}")
        return response

    @HasPermission("network_white_list-Delete", "system-manager")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            return self._refuse_builtin(instance)
        label = self._label(instance)
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 204:
            invalidate_network_whitelist_cache()
            log_operation(request, "delete", "system-manager", f"删除内网白名单: {label}")
        return response

    def _label_from_response(self, response):
        data = response.data if isinstance(response.data, dict) else {}
        return data.get("domain_name") or data.get("network") or ""
