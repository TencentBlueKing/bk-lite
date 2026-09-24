"""脚本视图"""

from django.http import FileResponse
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
    ScriptExportSerializer,
    ScriptImportSerializer,
    ScriptListSerializer,
    ScriptSerializer,
    ScriptUpdateSerializer,
    validate_script_name_unique_in_organizations,
)
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_pack_service import ScriptPackService
from apps.job_mgmt.utils.i18n import job_message
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
        elif self.action == "export":
            return ScriptExportSerializer
        elif self.action == "import_scripts":
            return ScriptImportSerializer
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
        validate_script_name_unique_in_organizations(data["name"], team)

        # 高危命令检测
        script_content = data.get("content", "")
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            return Response(
                {
                    "error": job_message(
                        request,
                        "error.dangerous_command_create_forbidden",
                        "Script contains high-risk commands and cannot be created: {rules}",
                        rules=", ".join(forbidden_rules),
                    )
                },
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
        validate_script_name_unique_in_organizations(
            data.get("name", instance.name),
            team,
            exclude_script_id=instance.pk,
        )

        # 高危命令检测（仅当修改了脚本内容时）
        script_content = data.get("content", instance.content)
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            return Response(
                {
                    "error": job_message(
                        request,
                        "error.dangerous_command_update_forbidden",
                        "Script contains high-risk commands and cannot be updated: {rules}",
                        rules=", ".join(forbidden_rules),
                    )
                },
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

    @action(detail=False, methods=["post"])
    @HasPermission("script_library-View")
    def export(self, request):
        """批量导出脚本为 ZIP。"""
        serializer = ScriptExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        queryset = self.filter_queryset(self.get_queryset()).filter(id__in=ids)
        found_ids = set(queryset.values_list("id", flat=True))
        missing = sorted(set(ids) - found_ids)
        if missing:
            return Response(
                {
                    "error": job_message(
                        request,
                        "error.scripts_export_missing",
                        "Some scripts do not exist or cannot be exported: {ids}",
                        ids=", ".join(str(i) for i in missing),
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 保持请求 ids 顺序，避免 zip 内目录顺序抖动
        scripts_by_id = {script.id: script for script in queryset}
        scripts = [scripts_by_id[script_id] for script_id in ids if script_id in scripts_by_id]
        buffer = ScriptPackService.build_export_zip(scripts)
        log_operation(request, "export", "job", f"批量导出脚本: {len(scripts)} 条")
        return FileResponse(
            buffer,
            as_attachment=True,
            filename="script-pack.zip",
            content_type="application/zip",
        )

    @action(detail=False, methods=["post"], url_path="import")
    @HasPermission("script_library-Add")
    def import_scripts(self, request):
        """批量导入脚本 ZIP。"""
        serializer = ScriptImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = serializer.validated_data["team"]
        upload = serializer.validated_data["file"]

        self._validate_org_field_permission(request, team)

        try:
            drafts = ScriptPackService.parse_import_zip(upload)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        username = getattr(request.user, "username", "") or ""
        result = ScriptPackService.import_scripts(drafts, team, username=username)
        payload = result.to_dict()
        log_operation(
            request,
            "import",
            "job",
            f"批量导入脚本: 成功 {len(result.created)} 跳过 {len(result.skipped)} 失败 {len(result.failed)}",
        )
        return Response(payload, status=status.HTTP_200_OK)
