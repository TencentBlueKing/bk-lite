from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.models import SensitiveInfoAuthorization
from apps.system_mgmt.models.sensitive_info_authorization import get_authorized_types_text, normalize_sensitive_types
from apps.system_mgmt.serializers.sensitive_info_authorization_serializer import SensitiveInfoAuthorizationSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class SensitiveInfoAuthorizationViewSet(MaintainerViewSet):
    queryset = SensitiveInfoAuthorization.objects.all().order_by("-created_at", "-id")
    serializer_class = SensitiveInfoAuthorizationSerializer

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        if response.status_code == 201:
            response_data = response.data or {}
            username = response_data.get("username", "")
            domain = response_data.get("domain", "domain.com")
            authorized_types_text = get_authorized_types_text(response_data.get("sensitive_types", []))
            log_operation(request, "create", "sensitive_info", f"新增敏感信息授权: {username}@{domain} ({authorized_types_text})")

        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        username = instance.username
        domain = instance.domain
        authorized_types_text = get_authorized_types_text(instance.sensitive_types)

        response = super().destroy(request, *args, **kwargs)

        if response.status_code == 204:
            log_operation(request, "delete", "sensitive_info", f"删除敏感信息授权: {username}@{domain} ({authorized_types_text})")

        return response

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def current_user(self, request):
        username = getattr(request.user, "username", "")
        domain = getattr(request.user, "domain", "domain.com")
        authorization = SensitiveInfoAuthorization.objects.filter(username=username, domain=domain).first()
        authorized_types = normalize_sensitive_types(getattr(authorization, "sensitive_types", []))
        return Response({"result": True, "data": {"authorized_types": authorized_types}})

    def retrieve(self, request, *args, **kwargs):
        return Response({"result": False, "message": "不支持详情查询"}, status=405)

    def update(self, request, *args, **kwargs):
        return Response({"result": False, "message": "不支持修改"}, status=405)

    def partial_update(self, request, *args, **kwargs):
        return Response({"result": False, "message": "不支持修改"}, status=405)
