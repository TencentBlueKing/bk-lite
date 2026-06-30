# -- coding: utf-8 --
"""
运营分析 YAML 导入导出 Open API

提供面向外部系统的导入导出接口，支持：
- 导出指定对象为 YAML
- 导入预检（检测冲突、缺失配置）
- 导入提交（执行导入）

认证方式：通过 API Token（由 APISecretMiddleware 验证）
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions.base_app_exception import UnauthorizedException
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.open_base import OpenAPIViewSet
from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.serializers.import_export_serializers import (
    ExportRequestSerializer,
    ImportPrecheckRequestSerializer,
    ImportSubmitRequestSerializer,
)
from apps.operation_analysis.services.import_export.authorization_service import ImportExportAuthorizationService
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService


class OpenImportExportViewSet(OpenAPIViewSet):
    """
    运营分析 YAML 导入导出开放 API 视图集

    提供无需登录的 API 接口，通过 API Token 认证：
    - POST /export - 导出对象为 YAML
    - POST /import/precheck - 导入预检
    - POST /import/submit - 导入提交

    认证方式：
        请求头需包含有效的 API Token（由 APISecretMiddleware 验证）
        Header: Api-Authorization: <api_token>
    """

    def _check_api_auth(self, request):
        if not getattr(request, "api_pass", False):
            logger.warning("Open API request rejected: missing or invalid API token, path=%s", request.path)
            raise UnauthorizedException("缺少有效的 API Token，请在请求头中提供有效的认证信息")

    def _get_groups_from_request(self, request) -> list[int]:
        user = getattr(request, "user", None)
        group_list = getattr(user, "group_list", None)
        if not isinstance(group_list, list):
            return []

        resolved_groups = []
        for item in group_list:
            if isinstance(item, int):
                resolved_groups.append(item)
                continue
            if isinstance(item, str) and item.isdigit():
                resolved_groups.append(int(item))
                continue
            if isinstance(item, dict):
                group_id = item.get("id")
                if isinstance(group_id, int):
                    resolved_groups.append(group_id)
                    continue
                if isinstance(group_id, str) and group_id.isdigit():
                    resolved_groups.append(int(group_id))

        return resolved_groups

    def _require_groups(self, request) -> list[int]:
        groups = self._get_groups_from_request(request)
        if not groups:
            raise ValidationError("无法从API Token上下文解析有效的组织信息")
        return groups

    def _get_username_from_request(self, request) -> str:
        if hasattr(request, "user") and getattr(request.user, "is_authenticated", False) and getattr(request.user, "username", None):
            return request.user.username
        return "api_user"

    def _filter_ids_by_org(self, object_type: str, object_ids: list[int], current_team: int = None) -> list[int]:
        """按组织过滤对象 ID，返回当前组织可见的合法 ID 列表"""
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
        from apps.operation_analysis.models.models import Architecture, Dashboard, Topology

        MODEL_MAP = {
            ObjectType.DASHBOARD.value: Dashboard,
            ObjectType.TOPOLOGY.value: Topology,
            ObjectType.ARCHITECTURE.value: Architecture,
            ObjectType.DATASOURCE.value: DataSourceAPIModel,
        }

        model = MODEL_MAP.get(object_type)
        if model is not None:
            qs = model.objects.filter(id__in=object_ids)
            if current_team is not None:
                qs = qs.filter(groups__contains=current_team)
            return list(qs.values_list("id", flat=True))

        if object_type == ObjectType.NAMESPACE.value:
            return list(NameSpace.objects.filter(id__in=object_ids).values_list("id", flat=True))

        return []

    @action(detail=False, methods=["post"], url_path="export")
    def export_objects(self, request):
        """
        导出对象为 YAML

        API: POST /open_api/import_export/export

        Request Headers:
            Authorization (str, required): API Token 认证

        Request Body:
            {
                "object_type": "dashboard",  # 对象类型: "dashboard" | "topology" | "architecture" | "datasource" | "namespace"
                "object_ids": [1, 2, 3]  # 要导出的对象 ID 列表
            }

        Response (200 OK):
            {
                "yaml_content": "version: '1.0'\\n...",  # 导出的 YAML 内容
                "exported_objects": [  # 已导出的对象列表
                    {
                        "object_type": "dashboard",
                        "object_key": "dashboard::my-dashboard",
                        "name": "my-dashboard"
                    }
                ],
                "warnings": []  # 警告信息
            }

        Response (401 Unauthorized):
            {
                "success": False,
                "code": "UNAUTHORIZED",
                "message": "缺少有效的 API Token"
            }
        """
        self._check_api_auth(request)

        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        scope = data["scope"]
        object_type = data["object_type"]
        object_ids = data["object_ids"]

        groups = self._require_groups(request)
        organization_id = groups[0]

        filtered_ids = ImportExportAuthorizationService.filter_export_object_ids(
            request,
            object_type,
            object_ids,
            current_team=organization_id,
        )

        logger.info(
            "Open API export request: object_type=%s, object_ids=%s, organization_id=%s",
            object_type,
            object_ids,
            organization_id,
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
        """
        导入预检

        API: POST /open_api/import_export/import/precheck

        Request Headers:
            Authorization (str, required): API Token 认证

        Request Body:
            {
                "yaml_content": "version: '1.0'\\n...",  # YAML 内容
                "target_directory_id": 1  # 可选，目标目录 ID（仅对画布类对象有效）
            }

        Response (200 OK):
            {
                "valid": true,  # 预检是否通过
                "errors": [],  # 错误列表
                "warnings": [],  # 警告列表
                "conflicts": [  # 冲突列表
                    {
                        "object_type": "dashboard",
                        "object_key": "dashboard::my-dashboard",
                        "name": "my-dashboard",
                        "reason": "NAME_CONFLICT",  # 冲突原因
                        "existing_id": 123,  # 已存在对象的 ID
                        "available_actions": ["overwrite", "rename", "skip"]  # 可选的冲突处理方式
                    }
                ],
                "objects": [  # 待导入对象列表
                    {
                        "object_type": "dashboard",
                        "object_key": "dashboard::my-dashboard",
                        "name": "my-dashboard",
                        "has_conflict": true,
                        "status": "pending"
                    }
                ],
                "secret_fields": [  # 需要补充的敏感字段
                    {
                        "object_key": "datasource::my-ds::http://api.example.com",
                        "field": "password",
                        "required": true
                    }
                ]
            }

        Response (401 Unauthorized):
            认证失败
        """
        self._check_api_auth(request)

        serializer = ImportPrecheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        yaml_content = data["yaml_content"]
        target_directory_id = data.get("target_directory_id")

        groups = self._require_groups(request)
        current_team = groups[0]

        logger.info(
            "Open API import precheck request: yaml_size=%d, target_directory_id=%s, current_team=%s",
            len(yaml_content),
            target_directory_id,
            current_team,
        )

        result = PrecheckService.precheck(
            yaml_content=yaml_content,
            target_directory_id=target_directory_id,
            current_team=current_team,
        )
        doc = result.pop("_doc")

        if not result["valid"]:
            return Response(result, status=status.HTTP_200_OK)

        result = ImportExportAuthorizationService.apply_precheck_permissions(
            request,
            doc,
            result,
            current_team=current_team,
        )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="import/submit")
    def import_submit(self, request):
        """
        导入提交

        API: POST /open_api/import_export/import/submit

        Request Headers:
            Authorization (str, required): API Token 认证

        Request Body:
            {
                "yaml_content": "version: '1.0'\\n...",  # YAML 内容
                "target_directory_id": 1,  # 可选，目标目录 ID
                "conflict_decisions": [  # 冲突决策列表
                    {
                        "object_key": "dashboard::my-dashboard",
                        "action": "overwrite"  # "overwrite" | "rename" | "skip"
                    }
                ],
                "secret_supplements": [  # 敏感字段补充
                    {
                        "object_key": "datasource::my-ds::http://api.example.com",
                        "field": "password",
                        "value": "secret123"
                    }
                ]
            }

        Response (200 OK):
            {
                "success": true,
                "summary": {  # 导入汇总
                    "total": 5,
                    "created": 3,
                    "overwritten": 1,
                    "renamed": 0,
                    "skipped": 1,
                    "failed": 0
                },
                "results": [  # 各对象导入结果
                    {
                        "object_type": "dashboard",
                        "object_key": "dashboard::my-dashboard",
                        "name": "my-dashboard",
                        "action": "created",  # "created" | "overwritten" | "renamed" | "skipped" | "failed"
                        "new_id": 456,  # 新对象 ID（如果创建/覆盖）
                        "new_name": null,  # 新名称（如果重命名）
                        "error": null  # 错误信息（如果失败）
                    }
                ],
                "errors": []  # 全局错误
            }

        Response (400 Bad Request):
            {
                "success": false,
                "errors": [...],
                "message": "预检失败，无法执行导入"
            }

        Response (401 Unauthorized):
            认证失败
        """
        self._check_api_auth(request)

        serializer = ImportSubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        yaml_content = data["yaml_content"]
        target_directory_id = data.get("target_directory_id")
        conflict_decisions_list = data.get("conflict_decisions", [])
        secret_supplements_list = data.get("secret_supplements", [])

        groups = self._require_groups(request)
        current_team = groups[0]
        username = self._get_username_from_request(request)

        logger.info(
            "Open API import submit request: yaml_size=%d, target_directory_id=%s, groups=%s, operator=%s",
            len(yaml_content),
            target_directory_id,
            groups,
            username,
        )

        precheck_result = PrecheckService.precheck(
            yaml_content=yaml_content,
            target_directory_id=target_directory_id,
            current_team=current_team,
        )
        doc = precheck_result.pop("_doc")

        if not precheck_result["valid"]:
            return Response(
                {
                    "success": False,
                    "errors": precheck_result["errors"],
                    "message": "预检失败，无法执行导入",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        return Response(result, status=status.HTTP_200_OK)
