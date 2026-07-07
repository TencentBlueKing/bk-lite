from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import LoginAuthBinding
from apps.system_mgmt.serializers import LoginAuthBindingSerializer
from apps.system_mgmt.services.login_auth_binding_service import build_login_auth_redirect
from apps.system_mgmt.utils.operation_log_utils import log_operation
from config.drf.pagination import CustomPageNumberPagination


class LoginAuthBindingViewSet(MaintainerViewSet):
    queryset = LoginAuthBinding.objects.select_related("integration_instance").all().order_by("order", "id")
    serializer_class = LoginAuthBindingSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ("order", "id")
    builtin_provider_key = "bk_lite_builtin"

    def _is_builtin_binding(self, binding):
        return binding.integration_instance.provider_key == self.builtin_provider_key

    @HasPermission("login_auth-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("login_auth-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "system-manager", f"新增登录认证源: {response.data.get('name', '')}")
        return response

    @HasPermission("login_auth-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "system-manager", f"编辑登录认证源: {response.data.get('name', '')}")
        return response

    @HasPermission("login_auth-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if self._is_builtin_binding(obj):
            return JsonResponse({"result": False, "message": "Built-in login auth binding cannot be deleted"}, status=403)
        binding_name = obj.name
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 204:
            log_operation(request, "delete", "system-manager", f"删除登录认证源: {binding_name}")
        return response

    @action(methods=["POST"], detail=True)
    @HasPermission("login_auth-View")
    def login_url(self, request, *args, **kwargs):
        binding = self.get_object()
        redirect_uri = request.data.get("redirect_uri", "")
        state = request.data.get("state", "")
        if not redirect_uri:
            return JsonResponse({"result": False, "message": "redirect_uri is required"}, status=400)
        result = build_login_auth_redirect(binding, redirect_uri=redirect_uri, state=state)
        return Response({"result": result.success, "data": result.to_dict(), "message": result.summary}, status=200 if result.success else 400)
