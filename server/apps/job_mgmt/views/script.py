"""脚本视图"""

from django.http import FileResponse
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.script import ScriptFilter
from apps.job_mgmt.models import Script, ScriptRevision
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
from apps.job_mgmt.services.template_revision import (
    DEFAULT_PAGE_SIZE,
    RevisionAlreadyCurrent,
    RevisionNotFound,
    TemplateRevisionService,
    annotate_current_revision_label,
    parse_page,
)
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

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            queryset = annotate_current_revision_label(queryset, ScriptRevision, "script")
        return queryset

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

    @HasPermission("script_library-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

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

    @action(detail=True, methods=["get"], url_path="revisions")
    @HasPermission("script_library-View")
    def revisions(self, request, pk=None):
        """版本列表。没有历史时用当前内容补一条。"""
        instance, denied = authorize_job_template(self, request, view_only=True)
        if denied is not None:
            return denied
        parsed = _revision_page(request)
        if parsed is None:
            return _invalid_revision_page(request)
        page, page_size = parsed
        return Response(TemplateRevisionService.list_script_revisions(instance, page, page_size))

    @action(detail=True, methods=["get"], url_path=r"revisions/(?P<revision_id>[0-9]+)/compare")
    @HasPermission("script_library-View")
    def compare_revision(self, request, pk=None, revision_id=None):
        """所选版本与当前版本对比。加密参数默认值只返回是否变化。"""
        instance, denied = authorize_job_template(self, request, view_only=True)
        if denied is not None:
            return denied
        try:
            payload = TemplateRevisionService.compare_script(instance, int(revision_id))
        except RevisionNotFound:
            return _revision_not_found(request)
        return Response(payload)

    @action(detail=True, methods=["post"], url_path=r"revisions/(?P<revision_id>[0-9]+)/restore")
    @HasPermission("script_library-Edit")
    def restore_revision(self, request, pk=None, revision_id=None):
        """恢复到所选版本，并追加一条新的日期版本。"""
        instance, denied = authorize_job_template(self, request, view_only=False)
        if denied is not None:
            return denied
        revision = ScriptRevision.objects.filter(script=instance, pk=revision_id).first()
        if revision is None:
            return _revision_not_found(request)

        check_result = DangerousChecker.check_command(revision.content, instance.team)
        if not check_result.can_execute:
            forbidden_rules = [item["rule_name"] for item in check_result.forbidden]
            return Response(
                {
                    "error": job_message(
                        request,
                        "error.revision_restore_forbidden",
                        "Script contains high-risk commands and cannot be restored: {rules}",
                        rules=", ".join(forbidden_rules),
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_script_name_unique_in_organizations(revision.name, instance.team, exclude_script_id=instance.pk)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        operator = getattr(request.user, "username", "") or ""
        try:
            instance = TemplateRevisionService.restore_script(instance, revision, operator)
        except RevisionAlreadyCurrent:
            return Response(
                {"error": job_message(request, "error.revision_already_current", "This revision is already current")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_operation(request, "update", "job", f"恢复脚本版本: {instance.name} -> {revision.label}")
        return Response(ScriptSerializer(instance).data)


def authorize_job_template(view, request, *, view_only):
    """与详情/更新相同的组织边界。实例规则不能越过当前团队。"""
    from django.core.exceptions import PermissionDenied

    from apps.core.utils.viewset_utils import team_access_denied_message

    user = getattr(request, "user", None)
    instance = view.get_object()
    if getattr(user, "is_superuser", False):
        return instance, None
    current_team = view._parse_current_team_cookie(request)
    user_group_ids = {group["id"] for group in getattr(user, "group_list", [])}
    if current_team not in user_group_ids:
        raise PermissionDenied(team_access_denied_message(request, getattr(view, "loader", None)))
    include_children = request.COOKIES.get("include_children", "0") == "1"
    if not view.get_has_permission(user, instance, current_team, is_check=view_only, include_children=include_children):
        message_key = "error.no_permission_view" if view_only else "error.no_permission_update"
        message = view.loader.get(message_key) if getattr(view, "loader", None) else "permission denied"
        return None, view.value_error(message)
    return instance, None


def _revision_page(request):
    try:
        return parse_page(request.query_params.get("page", 1), request.query_params.get("page_size", DEFAULT_PAGE_SIZE))
    except ValueError:
        return None


def _invalid_revision_page(request):
    return Response(
        {"detail": job_message(request, "error.revision_page_invalid", "Invalid pagination parameters")},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _revision_not_found(request):
    return Response(
        {"detail": job_message(request, "error.revision_not_found", "Revision not found")},
        status=status.HTTP_404_NOT_FOUND,
    )
