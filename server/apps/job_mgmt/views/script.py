"""脚本视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.script import ScriptFilter
from apps.job_mgmt.models import Script
from apps.job_mgmt.serializers.script import (
    ScriptBatchDeleteSerializer,
    ScriptCreateSerializer,
    ScriptListSerializer,
    ScriptSerializer,
    ScriptUpdateSerializer,
)
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.views.mixins import BatchDeleteMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ScriptViewSet(BatchDeleteMixin, AuthViewSet):
    """脚本视图集"""

    queryset = Script.objects.all()
    serializer_class = ScriptSerializer
    filterset_class = ScriptFilter
    search_fields = ["name", "description"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    batch_delete_serializer_class = ScriptBatchDeleteSerializer
    batch_delete_log_label = "脚本"

    def get_serializer_class(self):
        if self.action == "list":
            return ScriptListSerializer
        elif self.action == "create":
            return ScriptCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ScriptUpdateSerializer
        elif self.action == "batch_delete":
            return ScriptBatchDeleteSerializer
        return ScriptSerializer

    @HasPermission("script_library-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("script_library-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("script_library-Add")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 校验用户是否有目标组织的权限
        team = data.get("team", [])
        self._validate_org_field_permission(request, team)

        # 高危命令检测
        script_content = data.get("content", "")
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            return Response(
                {"error": f"脚本包含高危命令，禁止创建: {', '.join(forbidden_rules)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self.perform_create(serializer)

        # 返回完整的对象信息
        instance = Script.objects.get(pk=serializer.instance.pk)
        response_serializer = ScriptSerializer(instance)
        response = Response(response_serializer.data, status=status.HTTP_201_CREATED)
        if response.status_code == status.HTTP_201_CREATED:
            log_operation(request, "create", "job", f"新增脚本: {response.data.get('name')}")
        return response

    @HasPermission("script_library-Edit")
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 校验用户是否有目标组织的权限
        team = data.get("team", instance.team)
        self._validate_org_field_permission(request, team)

        # 高危命令检测（仅当修改了脚本内容时）
        script_content = data.get("content", instance.content)
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            return Response(
                {"error": f"脚本包含高危命令，禁止修改: {', '.join(forbidden_rules)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self.perform_update(serializer)
        response = Response(ScriptSerializer(instance).data)
        if response.status_code == status.HTTP_200_OK:
            log_operation(request, "update", "job", f"编辑脚本: {response.data.get('name')}")
        return response

    @action(detail=False, methods=["post"])
    @HasPermission("script_library-Delete")
    def batch_delete(self, request):
        """批量删除脚本"""
        return self.perform_batch_delete(request)
