# -- coding: utf-8 --
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.operation_analysis.constants.import_export import ConflictAction, ConflictReason, ImportExportErrorCode, ObjectType
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.serializers.import_export_serializers import (
    ExportRequestSerializer,
    ImportPrecheckRequestSerializer,
    ImportSubmitRequestSerializer,
)
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService


class ImportExportViewSet(ViewSet):
    IMPORT_ACTION_PERMISSION_MAP = {
        ObjectType.DASHBOARD: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.TOPOLOGY: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.ARCHITECTURE: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.DATASOURCE: {"create": "data_source-Add", "overwrite": "data_source-Edit"},
        ObjectType.NAMESPACE: {"create": "namespace-Add", "overwrite": "namespace-Edit"},
    }

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

        object_keys = self._convert_ids_to_keys(object_type, object_ids, current_team=current_team)

        result = ExportService.export_objects(
            scope_type=scope,
            object_types=[object_type],
            object_keys=object_keys,
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

        if result["valid"]:
            doc = self._parse_yaml_to_document(yaml_content)
            permission_errors = self._collect_precheck_permission_errors(request, doc)
            if permission_errors:
                result["valid"] = False
                result["errors"].extend(permission_errors)

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

        precheck_result = PrecheckService.precheck(
            yaml_content=yaml_content,
            target_directory_id=target_directory_id,
            current_team=self._get_current_team(request),
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

        invalid_decisions = self._validate_conflict_decisions(precheck_result["conflicts"], conflict_decisions)
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

        doc = self._parse_yaml_to_document(yaml_content)
        self._validate_import_permissions(request, doc, conflict_decisions)

        username = getattr(request.user, "username", "system")
        current_team = request.COOKIES.get("current_team")
        groups = [int(current_team)] if current_team else []

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

    def _convert_ids_to_keys(self, object_type: str, object_ids: list[int], current_team: int = None) -> list[str]:
        from apps.operation_analysis.constants.import_export import BUSINESS_KEY_SEPARATOR
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
        from apps.operation_analysis.models.models import Architecture, Dashboard, Topology

        keys = []
        if object_type == ObjectType.DASHBOARD.value:
            qs = Dashboard.objects.filter(id__in=object_ids)
            if current_team is not None:
                qs = qs.filter(groups__contains=current_team)
            for obj in qs:
                keys.append(f"{object_type}{BUSINESS_KEY_SEPARATOR}{obj.name}")
        elif object_type == ObjectType.TOPOLOGY.value:
            qs = Topology.objects.filter(id__in=object_ids)
            if current_team is not None:
                qs = qs.filter(groups__contains=current_team)
            for obj in qs:
                keys.append(f"{object_type}{BUSINESS_KEY_SEPARATOR}{obj.name}")
        elif object_type == ObjectType.ARCHITECTURE.value:
            qs = Architecture.objects.filter(id__in=object_ids)
            if current_team is not None:
                qs = qs.filter(groups__contains=current_team)
            for obj in qs:
                keys.append(f"{object_type}{BUSINESS_KEY_SEPARATOR}{obj.name}")
        elif object_type == ObjectType.DATASOURCE.value:
            qs = DataSourceAPIModel.objects.filter(id__in=object_ids)
            if current_team is not None:
                qs = qs.filter(groups__contains=current_team)
            for obj in qs:
                keys.append(f"{obj.name}{BUSINESS_KEY_SEPARATOR}{obj.rest_api}")
        elif object_type == ObjectType.NAMESPACE.value:
            for obj in NameSpace.objects.filter(id__in=object_ids):
                keys.append(obj.name)
        return keys

    def _get_current_team(self, request) -> int | None:
        current_team = request.COOKIES.get("current_team")
        if current_team:
            try:
                return int(current_team)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_yaml_to_document(self, yaml_content: str) -> YAMLDocument:
        import yaml as pyyaml

        data = pyyaml.safe_load(yaml_content)
        return YAMLDocument(**data)

    def _get_request_permissions(self, request) -> set[str]:
        user_permissions = getattr(request.user, "permission", set())
        if isinstance(user_permissions, dict):
            permissions = user_permissions.get("ops-analysis", set())
        elif isinstance(user_permissions, set):
            permissions = user_permissions
        else:
            permissions = set()

        return set(permissions)

    def _get_existing_object(self, object_type: ObjectType, item):
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
        from apps.operation_analysis.models.models import Architecture, Dashboard, Topology

        if object_type == ObjectType.DASHBOARD:
            return Dashboard.objects.filter(name=item.name).first()
        if object_type == ObjectType.TOPOLOGY:
            return Topology.objects.filter(name=item.name).first()
        if object_type == ObjectType.ARCHITECTURE:
            return Architecture.objects.filter(name=item.name).first()
        if object_type == ObjectType.DATASOURCE:
            return DataSourceAPIModel.objects.filter(name=item.name, rest_api=item.rest_api).first()
        if object_type == ObjectType.NAMESPACE:
            return NameSpace.objects.filter(name=item.name).first()
        return None

    def _iter_import_items(self, doc: YAMLDocument):
        yield ObjectType.NAMESPACE, doc.namespaces
        yield ObjectType.DATASOURCE, doc.datasources
        yield ObjectType.DASHBOARD, doc.dashboards
        yield ObjectType.TOPOLOGY, doc.topologies
        yield ObjectType.ARCHITECTURE, doc.architectures

    def _build_permission_error(self, object_type: ObjectType, item, required_permissions: list[str], message: str) -> dict:
        return {
            "code": ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
            "message": message,
            "object_key": item.key,
            "object_type": object_type.value,
            "required_permission": ", ".join(required_permissions),
            "details": {
                "required_permissions": required_permissions,
            },
        }

    def _collect_precheck_permission_errors(self, request, doc: YAMLDocument) -> list[dict]:
        if getattr(request, "api_pass", False) or getattr(request.user, "is_superuser", False):
            return []

        user_permissions = self._get_request_permissions(request)
        permission_errors = []

        for object_type, items in self._iter_import_items(doc):
            permission_config = self.IMPORT_ACTION_PERMISSION_MAP.get(object_type)
            if not permission_config:
                continue

            create_permission = permission_config["create"]
            overwrite_permission = permission_config["overwrite"]

            for item in items:
                existing = self._get_existing_object(object_type, item)
                if existing:
                    if create_permission not in user_permissions and overwrite_permission not in user_permissions:
                        permission_errors.append(
                            self._build_permission_error(
                                object_type,
                                item,
                                [create_permission, overwrite_permission],
                                f"{object_type.value} '{item.name}' 缺少可导入权限，需要 {create_permission} 或 {overwrite_permission}",
                            )
                        )
                elif create_permission not in user_permissions:
                    permission_errors.append(
                        self._build_permission_error(
                            object_type,
                            item,
                            [create_permission],
                            f"{object_type.value} '{item.name}' 缺少权限 {create_permission}",
                        )
                    )

        return permission_errors

    def _validate_import_permissions(self, request, doc: YAMLDocument, conflict_decisions: dict[str, str]):
        if getattr(request, "api_pass", False) or getattr(request.user, "is_superuser", False):
            return

        user_permissions = self._get_request_permissions(request)
        denied_permissions = []

        for object_type, items in self._iter_import_items(doc):
            permission_config = self.IMPORT_ACTION_PERMISSION_MAP.get(object_type)
            if not permission_config:
                continue

            for item in items:
                existing = self._get_existing_object(object_type, item)
                action = conflict_decisions.get(item.key, ConflictAction.RENAME.value)
                required_permission = None

                if existing and action == ConflictAction.SKIP.value:
                    continue

                if existing and action == ConflictAction.OVERWRITE.value:
                    required_permission = permission_config["overwrite"]
                else:
                    required_permission = permission_config["create"]

                if required_permission not in user_permissions:
                    denied_permissions.append(
                        self._build_permission_error(
                            object_type,
                            item,
                            [required_permission],
                            f"{object_type.value} '{item.name}' 缺少权限 {required_permission}",
                        )
                    )

        if denied_permissions:
            raise PermissionDenied(
                {
                    "success": False,
                    "message": "当前用户没有本次 YAML 导入所需的对象权限",
                    "errors": denied_permissions,
                }
            )

    def _validate_conflict_decisions(self, conflicts: list[dict], conflict_decisions: dict[str, str]) -> list[dict]:
        errors = []
        for conflict in conflicts:
            if conflict["reason"] != ConflictReason.NO_PERMISSION_CONFLICT:
                continue
            object_key = conflict["object_key"]
            action = conflict_decisions.get(object_key, ConflictAction.RENAME.value)
            if action != ConflictAction.RENAME.value:
                errors.append(
                    {
                        "code": ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
                        "message": f"对象 '{object_key}' 在其他组织中已存在，只能选择重命名",
                        "object_key": object_key,
                        "object_type": conflict["object_type"],
                    }
                )
        return errors
