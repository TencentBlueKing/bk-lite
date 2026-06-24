# -- coding: utf-8 --
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.operation_analysis.common.audit_log import log_ops_analysis_import_results
from apps.operation_analysis.serializers.import_export_serializers import (
    ExportRequestSerializer,
    ImportPrecheckRequestSerializer,
    ImportSubmitRequestSerializer,
)
from apps.operation_analysis.services.import_export.authorization_service import ImportExportAuthorizationService
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService
from apps.core.utils.team_utils import get_current_team


class ImportExportViewSet(ViewSet):
    @action(detail=False, methods=["post"], url_path="export")
    def export_objects(self, request):
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        scope = data["scope"]
        object_type = data["object_type"]
        object_ids = data["object_ids"]

        organization_id = getattr(request, "organization_id", 0)
        current_team = self._get_current_team(request)

        filtered_ids = ImportExportAuthorizationService.filter_export_object_ids(
            request,
            object_type,
            object_ids,
            current_team=current_team,
        )

        result = ExportService.export_objects(
            scope_type=scope,
            object_type=object_type,
            object_ids=filtered_ids,
            organization_id=organization_id,
        )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="import/precheck")
    def import_precheck(self, request):
        serializer = ImportPrecheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        yaml_content = data["yaml_content"]
        target_directory_id = data.get("target_directory_id")

        current_team = self._get_current_team(request)

        result = PrecheckService.precheck(
            yaml_content=yaml_content,
            target_directory_id=target_directory_id,
            current_team=current_team,
        )

        if not result["valid"]:
            return Response(result, status=status.HTTP_200_OK)

        doc = result["_doc"]
        result = ImportExportAuthorizationService.apply_precheck_permissions(
            request,
            doc,
            result,
            current_team=current_team,
        )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="import/submit")
    def import_submit(self, request):
        serializer = ImportSubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        yaml_content = data["yaml_content"]
        target_directory_id = data.get("target_directory_id")
        conflict_decisions_list = data.get("conflict_decisions", [])
        secret_supplements_list = data.get("secret_supplements", [])

        current_team = self._get_current_team(request)

        precheck_result = PrecheckService.precheck(
            yaml_content=yaml_content,
            target_directory_id=target_directory_id,
            current_team=current_team,
        )

        if not precheck_result["valid"]:
            return Response(
                {
                    "success": False,
                    "errors": precheck_result["errors"],
                    "message": "预检失败，无法执行导入",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc = precheck_result["_doc"]
        precheck_result = ImportExportAuthorizationService.apply_precheck_permissions(
            request,
            doc,
            precheck_result,
            current_team=current_team,
        )

        if not precheck_result["valid"]:
            return Response(
                {
                    "success": False,
                    "errors": precheck_result["errors"],
                    "message": "预检失败，无法执行导入",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        conflict_decisions = {item["object_key"]: item["action"] for item in conflict_decisions_list}

        invalid_decisions = ImportExportAuthorizationService.validate_conflict_decisions(
            precheck_result["conflicts"],
            conflict_decisions,
        )
        if invalid_decisions:
            return Response(
                {
                    "success": False,
                    "errors": invalid_decisions,
                    "message": "冲突决策无效",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        secret_supplements = {}
        for item in secret_supplements_list:
            key = item["object_key"]
            if key not in secret_supplements:
                secret_supplements[key] = {}
            secret_supplements[key][item["field"]] = item["value"]

        ImportExportAuthorizationService.validate_import_submit_permissions(
            request,
            doc,
            precheck_result["conflicts"],
            conflict_decisions,
            current_team=current_team,
        )

        username = getattr(request.user, "username", "system")
        groups = [current_team] if current_team else []

        import_service = ImportService(
            doc=doc,
            target_directory_id=target_directory_id,
            conflict_decisions=conflict_decisions,
            secret_supplements=secret_supplements,
            created_by=username,
            updated_by=username,
            groups=groups,
        )

        result = import_service.execute()

        if isinstance(result, dict):
            log_ops_analysis_import_results(request, result.get("results"))
        return Response(result, status=status.HTTP_200_OK)

    def _get_current_team(self, request) -> int | None:
        current_team = get_current_team(request)
        if current_team:
            try:
                return int(current_team)
            except (ValueError, TypeError):
                pass
        return None


