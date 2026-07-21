# -- coding: utf-8 --
from __future__ import annotations

from typing import Any

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.core.utils.permission_utils import get_permission_rules
from apps.operation_analysis.constants.import_export import ConflictAction, ConflictReason, ImportExportErrorCode, ObjectType
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument


class ImportExportAuthorizationService:
    APP_NAME = "operation_analysis"
    APP_PERMISSION_NAME = "ops-analysis"
    ORG_SCOPED_OBJECT_TYPES = {
        ObjectType.DASHBOARD,
        ObjectType.TOPOLOGY,
        ObjectType.ARCHITECTURE,
        ObjectType.SCREEN,
        ObjectType.REPORT,
        ObjectType.NETWORK_TOPOLOGY,
        ObjectType.DATASOURCE,
    }

    EXPORT_PERMISSION_MAP = {
        ObjectType.DASHBOARD: {"permission": "view-View", "permission_key": "directory.dashboard"},
        ObjectType.TOPOLOGY: {"permission": "view-View", "permission_key": "directory.topology"},
        ObjectType.ARCHITECTURE: {"permission": "view-View", "permission_key": "directory.architecture"},
        ObjectType.SCREEN: {"permission": "view-View", "permission_key": "directory.screen"},
        ObjectType.REPORT: {"permission": "view-View", "permission_key": "directory.report"},
        ObjectType.NETWORK_TOPOLOGY: {"permission": "view-View", "permission_key": "directory.networkTopology"},
        ObjectType.DATASOURCE: {"permission": "data_source-View", "permission_key": "datasource"},
        ObjectType.NAMESPACE: {"permission": "namespace-View", "permission_key": None},
    }

    IMPORT_ACTION_PERMISSION_MAP = {
        ObjectType.DASHBOARD: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.TOPOLOGY: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.ARCHITECTURE: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.SCREEN: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.REPORT: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.NETWORK_TOPOLOGY: {"create": "view-AddChart", "overwrite": "view-EditChart"},
        ObjectType.DATASOURCE: {"create": "data_source-Add", "overwrite": "data_source-Edit"},
        ObjectType.NAMESPACE: {"create": "namespace-Add", "overwrite": "namespace-Edit"},
    }

    @classmethod
    def get_request_permissions(cls, request) -> set[str]:
        user_permissions = getattr(request.user, "permission", set())
        if isinstance(user_permissions, dict):
            permissions = user_permissions.get(cls.APP_PERMISSION_NAME, set())
        elif isinstance(user_permissions, set):
            permissions = user_permissions
        else:
            permissions = set()
        return set(permissions)

    @classmethod
    def has_permission(cls, request, permission: str) -> bool:
        if getattr(request.user, "is_superuser", False):
            return True
        return permission in cls.get_request_permissions(request)

    @classmethod
    def validate_current_team(cls, request, current_team: int | None) -> int | None:
        if getattr(request.user, "is_superuser", False):
            return current_team

        if not current_team:
            raise PermissionDenied("无权访问该团队数据")

        user_group_ids = cls._normalize_ids(getattr(request.user, "group_list", []))
        if current_team not in user_group_ids:
            raise PermissionDenied("无权访问该团队数据")
        return current_team

    @classmethod
    def filter_export_object_ids(cls, request, object_type: str, object_ids: list[int], current_team: int | None) -> list[int]:
        object_enum = ObjectType(object_type)
        cls.validate_current_team(request, current_team)

        export_config = cls.EXPORT_PERMISSION_MAP[object_enum]
        if not cls.has_permission(request, export_config["permission"]):
            raise PermissionDenied(f"缺少导出 {object_enum.value} 所需权限 {export_config['permission']}")

        group_ids = cls._get_export_group_ids(request, current_team)
        filtered_ids = cls._filter_ids_by_org(object_enum, object_ids, current_team, group_ids)
        filtered_ids = cls._filter_ids_by_scope(request, object_enum, filtered_ids, current_team)
        if not filtered_ids:
            raise PermissionDenied("无权导出所选对象或对象不存在")
        return filtered_ids

    @classmethod
    def apply_precheck_permissions(
        cls,
        request,
        doc: YAMLDocument,
        result: dict[str, Any],
        current_team: int | None,
    ) -> dict[str, Any]:
        cls.validate_current_team(request, current_team)
        if getattr(request.user, "is_superuser", False):
            return result

        permission_errors = []
        conflict_map = {conflict["object_key"]: conflict for conflict in result.get("conflicts", [])}

        for object_type, items in cls.iter_import_items(doc):
            permission_config = cls.IMPORT_ACTION_PERMISSION_MAP[object_type]
            create_allowed = cls.has_permission(request, permission_config["create"])
            overwrite_allowed = cls.has_permission(request, permission_config["overwrite"])
            view_allowed = cls.has_permission(request, cls.EXPORT_PERMISSION_MAP[object_type]["permission"])

            existing_map = cls.get_existing_objects_batch(object_type, items)

            for item in items:
                existing = existing_map.get(cls._item_lookup_key(object_type, item))
                if not existing:
                    if not create_allowed:
                        permission_errors.append(
                            cls.build_permission_error(
                                object_type,
                                item,
                                [permission_config["create"]],
                                f"{object_type.value} '{item.name}' 缺少权限 {permission_config['create']}",
                            )
                        )
                    continue

                conflict = conflict_map.get(item.key)
                if not conflict:
                    continue

                if not view_allowed or not cls.can_access_existing_object(request, object_type, existing, current_team):
                    suggested_actions = [ConflictAction.RENAME.value] if create_allowed else []
                    conflict["reason"] = ConflictReason.NO_PERMISSION_CONFLICT
                    conflict["suggested_actions"] = suggested_actions
                    if not suggested_actions:
                        permission_errors.append(
                            cls.build_permission_error(
                                object_type,
                                item,
                                [cls.EXPORT_PERMISSION_MAP[object_type]["permission"], permission_config["create"]],
                                f"{object_type.value} '{item.name}' 无权访问现有对象且缺少重命名所需权限",
                            )
                        )
                    continue

                suggested_actions = []
                if overwrite_allowed:
                    suggested_actions.append(ConflictAction.OVERWRITE.value)
                suggested_actions.append(ConflictAction.SKIP.value)
                if create_allowed:
                    suggested_actions.append(ConflictAction.RENAME.value)

                conflict["reason"] = ConflictReason.NAME_CONFLICT
                conflict["suggested_actions"] = suggested_actions

        if permission_errors:
            result["valid"] = False
            result.setdefault("errors", []).extend(permission_errors)

        return result

    @classmethod
    def validate_conflict_decisions(cls, conflicts: list[dict], conflict_decisions: dict[str, str]) -> list[dict]:
        errors = []
        for conflict in conflicts:
            allowed_actions = conflict.get("suggested_actions", [])
            if not allowed_actions:
                continue

            action = conflict_decisions.get(conflict["object_key"], ConflictAction.RENAME.value)
            if action not in allowed_actions:
                errors.append(
                    {
                        "code": ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
                        "message": f"对象 '{conflict['object_key']}' 不允许执行冲突动作 {action}",
                        "object_key": conflict["object_key"],
                        "object_type": conflict["object_type"],
                        "allowed_actions": allowed_actions,
                    }
                )
        return errors

    @classmethod
    def validate_import_submit_permissions(
        cls,
        request,
        doc: YAMLDocument,
        conflicts: list[dict],
        conflict_decisions: dict[str, str],
        current_team: int | None,
    ):
        cls.validate_current_team(request, current_team)
        if getattr(request.user, "is_superuser", False):
            return

        denied_permissions = []
        conflict_map = {conflict["object_key"]: conflict for conflict in conflicts}

        for object_type, items in cls.iter_import_items(doc):
            permission_config = cls.IMPORT_ACTION_PERMISSION_MAP[object_type]

            existing_map = cls.get_existing_objects_batch(object_type, items)

            for item in items:
                existing = existing_map.get(cls._item_lookup_key(object_type, item))
                conflict = conflict_map.get(item.key)
                action = conflict_decisions.get(item.key, ConflictAction.RENAME.value)

                if conflict and action not in conflict.get("suggested_actions", []):
                    denied_permissions.append(
                        {
                            "code": ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
                            "message": f"对象 '{item.key}' 不允许执行冲突动作 {action}",
                            "object_key": item.key,
                            "object_type": object_type.value,
                            "allowed_actions": conflict.get("suggested_actions", []),
                        }
                    )
                    continue

                if existing and action == ConflictAction.SKIP.value:
                    continue

                required_permission = (
                    permission_config["overwrite"] if existing and action == ConflictAction.OVERWRITE.value else permission_config["create"]
                )

                if not cls.has_permission(request, required_permission):
                    denied_permissions.append(
                        cls.build_permission_error(
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

    @classmethod
    def iter_import_items(cls, doc: YAMLDocument):
        yield ObjectType.NAMESPACE, getattr(doc, "namespaces", [])
        yield ObjectType.DATASOURCE, getattr(doc, "datasources", [])
        yield ObjectType.DASHBOARD, getattr(doc, "dashboards", [])
        yield ObjectType.TOPOLOGY, getattr(doc, "topologies", [])
        yield ObjectType.ARCHITECTURE, getattr(doc, "architectures", [])
        yield ObjectType.SCREEN, getattr(doc, "screens", [])
        yield ObjectType.REPORT, getattr(doc, "reports", [])
        yield ObjectType.NETWORK_TOPOLOGY, getattr(doc, "network_topologies", [])

    @classmethod
    def build_permission_error(cls, object_type: ObjectType, item, required_permissions: list[str], message: str) -> dict:
        return {
            "code": ImportExportErrorCode.IMPORT_PERMISSION_DENIED,
            "message": message,
            "object_key": item.key,
            "object_type": object_type.value,
            "required_permission": ", ".join(required_permissions),
            "details": {"required_permissions": required_permissions},
        }

    @classmethod
    def get_existing_object(cls, object_type: ObjectType, item):
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
        from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology

        if object_type == ObjectType.DASHBOARD:
            return Dashboard.objects.filter(name=item.name).first()
        if object_type == ObjectType.TOPOLOGY:
            return Topology.objects.filter(name=item.name).first()
        if object_type == ObjectType.ARCHITECTURE:
            return Architecture.objects.filter(name=item.name).first()
        if object_type == ObjectType.SCREEN:
            return Screen.objects.filter(name=item.name).first()
        if object_type == ObjectType.REPORT:
            return Report.objects.filter(name=item.name).first()
        if object_type == ObjectType.NETWORK_TOPOLOGY:
            return NetworkTopology.objects.filter(name=item.name).first()
        if object_type == ObjectType.DATASOURCE:
            return DataSourceAPIModel.objects.filter(name=item.name, rest_api=item.rest_api).first()
        if object_type == ObjectType.NAMESPACE:
            return NameSpace.objects.filter(name=item.name).first()
        return None

    @classmethod
    def get_existing_objects_batch(cls, object_type: ObjectType, items) -> dict:
        """批量查询一组 items 对应的已存在对象，返回 {lookup_key: object} 字典，消除 N+1 查询。"""
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
        from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology

        if not items:
            return {}

        if object_type == ObjectType.DATASOURCE:
            # DataSourceAPIModel 以 (name, rest_api) 为唯一键
            lookup_pairs = [(item.name, item.rest_api) for item in items]
            names = [p[0] for p in lookup_pairs]
            qs = DataSourceAPIModel.objects.filter(name__in=names)
            return {(obj.name, obj.rest_api): obj for obj in qs if (obj.name, obj.rest_api) in set(lookup_pairs)}

        name_set = [item.name for item in items]
        model_map = {
            ObjectType.DASHBOARD: Dashboard,
            ObjectType.TOPOLOGY: Topology,
            ObjectType.ARCHITECTURE: Architecture,
            ObjectType.SCREEN: Screen,
            ObjectType.REPORT: Report,
            ObjectType.NETWORK_TOPOLOGY: NetworkTopology,
            ObjectType.NAMESPACE: NameSpace,
        }
        model = model_map.get(object_type)
        if model is None:
            return {}
        return {obj.name: obj for obj in model.objects.filter(name__in=name_set)}

    @staticmethod
    def _item_lookup_key(object_type: ObjectType, item):
        """返回用于 get_existing_objects_batch 结果字典的查找键。"""
        if object_type == ObjectType.DATASOURCE:
            return (item.name, item.rest_api)
        return item.name

    @classmethod
    def can_access_existing_object(cls, request, object_type: ObjectType, existing, current_team: int | None) -> bool:
        if getattr(request.user, "is_superuser", False):
            return True

        if (
            object_type in cls.ORG_SCOPED_OBJECT_TYPES
            and current_team
            and hasattr(existing, "groups")
            and current_team not in (getattr(existing, "groups", None) or [])
        ):
            return False

        export_config = cls.EXPORT_PERMISSION_MAP[object_type]
        permission_key = export_config.get("permission_key")
        if not permission_key:
            return True

        permission_data = cls._get_permission_data(request, permission_key, current_team)
        allowed_team_ids = cls._normalize_ids(permission_data.get("team", []))
        if current_team in allowed_team_ids:
            return True

        allowed_instance_ids = cls._normalize_ids(permission_data.get("instance", []))
        return existing.id in allowed_instance_ids

    @classmethod
    def _filter_ids_by_scope(
        cls,
        request,
        object_type: ObjectType,
        object_ids: list[int],
        current_team: int | None,
    ) -> list[int]:
        if getattr(request.user, "is_superuser", False) or not object_ids:
            return object_ids

        permission_key = cls.EXPORT_PERMISSION_MAP[object_type].get("permission_key")
        if not permission_key:
            return object_ids

        permission_data = cls._get_permission_data(request, permission_key, current_team)
        allowed_team_ids = cls._normalize_ids(permission_data.get("team", []))
        if current_team in allowed_team_ids:
            return object_ids

        allowed_instance_ids = cls._normalize_ids(permission_data.get("instance", []))
        allowed_ids = set(allowed_instance_ids)
        model = cls._get_org_scoped_model(object_type)
        if model is not None:
            builtin_ids = model.objects.filter(id__in=object_ids, is_build_in=True).values_list("id", flat=True)
            allowed_ids.update(builtin_ids)

        created_by = getattr(request.user, "username", None)
        if created_by and model is not None:
            creator_ids = model.objects.filter(id__in=object_ids, created_by=created_by).values_list("id", flat=True)
            allowed_ids.update(creator_ids)

        return [object_id for object_id in object_ids if object_id in allowed_ids]

    @classmethod
    def _get_permission_data(cls, request, permission_key: str, current_team: int | None) -> dict[str, Any]:
        if not current_team:
            return {}
        return get_permission_rules(request.user, current_team, cls.APP_NAME, permission_key, False) or {}

    @classmethod
    def _filter_ids_by_org(
        cls,
        object_type: ObjectType,
        object_ids: list[int],
        current_team: int | None,
        group_ids: list[int] | None = None,
    ) -> list[int]:
        from apps.operation_analysis.models.datasource_models import NameSpace

        model = cls._get_org_scoped_model(object_type)
        if model is not None:
            queryset = model.objects.filter(id__in=object_ids)
            if current_team is not None:
                org_query = Q()
                for group_id in group_ids or [current_team]:
                    org_query |= Q(groups__contains=int(group_id))
                queryset = queryset.filter(org_query)
            return list(queryset.values_list("id", flat=True))

        if object_type == ObjectType.NAMESPACE:
            return list(NameSpace.objects.filter(id__in=object_ids).values_list("id", flat=True))

        return []

    @staticmethod
    def _get_export_group_ids(request, current_team: int | None) -> list[int]:
        if current_team is None:
            return []
        if request.COOKIES.get("include_children", "0") != "1":
            return [current_team]

        from apps.core.utils.viewset_utils import GenericViewSetFun

        child_ids = GenericViewSetFun.extract_child_group_ids(getattr(request.user, "group_tree", []), current_team)
        return child_ids or [current_team]

    @staticmethod
    def _get_org_scoped_model(object_type: ObjectType):
        from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
        from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology

        return {
            ObjectType.DASHBOARD: Dashboard,
            ObjectType.TOPOLOGY: Topology,
            ObjectType.ARCHITECTURE: Architecture,
            ObjectType.SCREEN: Screen,
            ObjectType.REPORT: Report,
            ObjectType.NETWORK_TOPOLOGY: NetworkTopology,
            ObjectType.DATASOURCE: DataSourceAPIModel,
        }.get(object_type)

    @staticmethod
    def _normalize_ids(values: list[Any]) -> set[int]:
        normalized = set()
        if not isinstance(values, list):
            return normalized

        for value in values:
            if isinstance(value, dict):
                value = value.get("id")
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if isinstance(value, int):
                normalized.add(value)
        return normalized
