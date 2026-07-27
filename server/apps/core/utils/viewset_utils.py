from django.db import connection
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.logger import logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_utils import delete_instance_rules, get_permission_rules
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.system_mgmt.models import Group


def build_json_membership_query(queryset, field_name, expected_values):
    """构造跨数据库 JSON 数组成员查询。

    支持 JSON contains 的数据库走原生查询；SQLite 等不支持 contains 的
    后端只物化主键和目标字段，再返回等价的主键条件。
    """
    normalized_values = []
    for value in expected_values or []:
        if value in (None, ""):
            continue
        normalized_values.append(value)
        try:
            normalized_values.append(int(value))
        except (TypeError, ValueError):
            pass
        normalized_values.append(str(value))
    normalized_values = list(dict.fromkeys(normalized_values))
    if not normalized_values:
        return Q(pk__in=[])

    if connection.features.supports_json_field_contains:
        query = Q()
        for value in normalized_values:
            query |= Q(**{f"{field_name}__contains": [value]})
        return query

    expected_set = set(normalized_values)
    matched_ids = []
    # values_list 会清除 select_related 的字段装载要求，避免 only() 将关联
    # 外键延迟后与调用方已有的 select_related 冲突。
    for item_id, field_value in queryset.order_by().values_list("pk", field_name):
        current_values = field_value or []
        if not isinstance(current_values, (list, tuple, set)):
            current_values = [current_values]
        comparable_values = set()
        for value in current_values:
            comparable_values.add(value)
            comparable_values.add(str(value))
            try:
                comparable_values.add(int(value))
            except (TypeError, ValueError):
                pass
        if expected_set.intersection(comparable_values):
            matched_ids.append(item_id)
    return Q(pk__in=matched_ids)


class GenericViewSetFun(object):
    @staticmethod
    def _parse_current_team_cookie(request, default=0):
        current_team = get_current_team(request, str(default))
        try:
            return int(current_team)
        except (TypeError, ValueError):
            return default

    def _get_app_name(self):
        """获取当前序列化器所属的应用名称"""
        module_path = self.__class__.__module__
        if "apps." in module_path:
            parts = module_path.split(".")
            if len(parts) >= 2 and parts[0] == "apps":
                return parts[1]
        return None

    def get_has_permission(self, user, instance, current_team, is_list=False, is_check=False, include_children=False):
        """获取规则实例ID"""
        user_groups = normalize_user_group_ids(getattr(user, "group_list", []))
        if include_children:
            group_tree = getattr(user, "group_tree", [])
            child_groups = self.extract_child_group_ids(group_tree, current_team)
            if child_groups:
                user_groups = child_groups
        org_field = getattr(self, "ORGANIZATION_FIELD", "team")
        if is_list:
            instance_id = list(instance.values_list("id", flat=True))
            for i in instance:
                if hasattr(i, org_field):
                    # 判断两个集合是否有交集
                    org_value = getattr(i, org_field)
                    if not set(org_value).intersection(set(user_groups)):
                        return False
        else:
            if hasattr(instance, org_field):
                org_value = getattr(instance, org_field)
                if not set(org_value).intersection(set(user_groups)):
                    return False
            instance_id = [instance.id]
        try:
            app_name = self._get_app_name()
            permission_rules = get_permission_rules(user, current_team, app_name, self.permission_key, include_children)
            if int(current_team) in permission_rules["team"]:
                return True
            if include_children:
                # 仅当用户在子树范围内确有 team 级授权才放行；不得无条件把 current_team
                # 加入 allowed_teams——否则与子树 user_groups 必然相交，对象级校验退化成
                # "对象属于当前组织树即放行"，造成子组织任务越权（issue #3037）。
                # current_team 自身已授权的情况已由上方 current_team in permission_rules["team"] 覆盖。
                allowed_teams = {i for i in permission_rules.get("team", [])}
                if allowed_teams & set(user_groups):
                    return True

            operate = "View" if is_check else "Operate"
            instance_list = [int(i["id"]) for i in permission_rules["instance"] if operate in i["permission"]]
            return set(instance_id).issubset(set(instance_list))
        except Exception as e:
            logger.error(f"Error getting rule instances: {e}")
            return False

    @staticmethod
    def extract_child_group_ids(group_tree, current_team_id):
        """
        从 group_tree 中递归提取指定组及其所有子组的 ID

        Args:
            group_tree: 组树结构列表
            current_team_id: 当前团队 ID

        Returns:
            包含当前组及其所有子组 ID 的列表
        """
        group_ids = []

        def extract_ids(groups, target_id, found=False):
            for group in groups:
                if group.get("id") == target_id:
                    group_ids.append(target_id)
                    # 递归提取所有子组
                    if group.get("subGroups"):
                        extract_subgroups(group["subGroups"])
                    return True
                elif group.get("subGroups"):
                    if extract_ids(group["subGroups"], target_id, found):
                        return True
            return False

        def extract_subgroups(subgroups):
            for subgroup in subgroups:
                group_ids.append(subgroup.get("id"))
                if subgroup.get("subGroups"):
                    extract_subgroups(subgroup["subGroups"])

        extract_ids(group_tree, current_team_id)
        return group_ids

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        user = getattr(request, "user", None)
        if not user:
            message = self.loader.get("error.user_not_found") if self.loader else "User not found in request"
            return self.value_error(message)

        current_team, include_children, org_field, query = self.filter_by_group(queryset, request, user)

        permission_key = permission_key or getattr(self, "permission_key", None)
        if permission_key:
            app_name = self._get_app_name()
            permission_data = get_permission_rules(user, current_team, app_name, permission_key, include_children)
            instance_ids = [i["id"] for i in permission_data.get("instance", [])]
            team = permission_data.get("team", [])
            if instance_ids:
                query |= Q(id__in=instance_ids)
            query |= build_json_membership_query(queryset, org_field, team)
            if not instance_ids and not team:
                return queryset.filter(id=0)
        return queryset.filter(query)

    @classmethod
    def filter_by_group(cls, queryset, request, user):
        current_team = cls._parse_current_team_cookie(request)
        # 验证 current_team 权限（超管豁免）
        if not getattr(user, "is_superuser", False):
            user_group_ids = {g["id"] for g in getattr(user, "group_list", [])}

            if current_team not in user_group_ids:
                raise PermissionDenied("无权访问该团队数据")

        include_children = request.COOKIES.get("include_children", "0") == "1"
        fields = [i.name for i in queryset.model._meta.fields]
        org_field = getattr(cls, "ORGANIZATION_FIELD", "team")
        if org_field in fields:
            if include_children:
                # 提取当前组及其所有子组的 ID
                group_tree = getattr(user, "group_tree", [])
                team_ids = cls.extract_child_group_ids(group_tree, current_team)

                if team_ids:
                    # 查询组织 ID 在子组列表中
                    query = build_json_membership_query(queryset, org_field, team_ids)
                else:
                    # 没有找到子组，使用当前组
                    query = build_json_membership_query(queryset, org_field, [current_team])
            else:
                # 不包含子组，team包含当前组
                query = build_json_membership_query(queryset, org_field, [current_team])
        else:
            query = Q()
        return current_team, include_children, org_field, query

    @staticmethod
    def value_error(msg):
        return JsonResponse({"result": False, "message": msg})


class LanguageViewSet(viewsets.ModelViewSet, GenericViewSetFun):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loader = None

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        app_name = self._get_app_name()
        if hasattr(request, "user") and request.user:
            locale = getattr(request.user, "locale", "en") or "en"
        else:
            locale = "en"
        self.loader = LanguageLoader(app=app_name, default_lang=locale)
        return request


class MaintainerViewSet(LanguageViewSet):
    DEFAULT_USERNAME = "guest"

    def perform_create(self, serializer):
        """创建时补充基础Model中的字段"""
        try:
            request = serializer.context.get("request")
            if not request:
                return super().perform_create(serializer)

            user = getattr(request, "user", None)
            username = getattr(user, "username", self.DEFAULT_USERNAME)
            domain = getattr(user, "domain", "domain.com")
            model = serializer.Meta.model
            if hasattr(model, "created_by"):
                serializer.save(created_by=username, updated_by=username, domain=domain, updated_by_domain=domain)
                return

        except Exception as e:
            logger.error(f"Error in perform_create: {e}")
            raise

        return super().perform_create(serializer)

    def perform_update(self, serializer):
        """更新时补充基础Model中的字段"""
        try:
            request = serializer.context.get("request")
            if not request:
                return super().perform_update(serializer)

            user = getattr(request, "user", None)
            username = getattr(user, "username", self.DEFAULT_USERNAME)
            domain = getattr(user, "domain", "domain.com")

            model = serializer.Meta.model
            if hasattr(model, "updated_by"):
                serializer.save(updated_by=username, updated_by_domain=domain)
                return

        except Exception as e:
            logger.error(f"Error in perform_update: {e}")
            raise

        return super().perform_update(serializer)


class AuthViewSet(MaintainerViewSet):
    SUPERUSER_RULE_ID = ["0"]
    ORDERING_FIELD = "-id"
    ORGANIZATION_FIELD = "team"  # 默认使用 team 字段,子类可覆盖为 groups 或其他字段名

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.core_loader = None

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        # 初始化 core 模块的 loader，用于通用错误消息
        if hasattr(request, "user") and request.user:
            locale = getattr(request.user, "locale", "en") or "en"
        else:
            locale = "en"
        self.core_loader = LanguageLoader(app="core", default_lang=locale)
        return request

    def _validate_current_team_permission(self, request):
        """验证用户有权限访问 current_team，返回 current_team 值

        - 如果 current_team 无效或用户无权访问，抛出 PermissionDenied
        - superuser 跳过 group_list 验证，但仍需要有效的 current_team
        """
        current_team = self._parse_current_team_cookie(request)
        if not current_team:
            raise PermissionDenied(self.loader.get("error.no_permission_access_team") if self.loader else "无权访问该团队数据")
        if not getattr(request.user, "is_superuser", False):
            user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
            if current_team not in user_group_ids:
                raise PermissionDenied(self.loader.get("error.no_permission_access_team") if self.loader else "无权访问该团队数据")
        return current_team

    def _validate_org_field_permission(self, request, org_values):
        """校验目标组织是否在当前用户可管理范围内

        Args:
            request: HTTP 请求对象
            org_values: 需要校验的组织 ID（可以是单个整数、字符串或列表）

        Raises:
            PermissionDenied: 当存在无权管理的组织时
        """
        if not org_values:
            return

        # 规范化输入：支持单个整数、字符串或列表
        if isinstance(org_values, (int, str)):
            org_values = [org_values]

        # 转换为整数列表
        normalized_values = []
        for v in org_values:
            if v is None:
                continue
            if isinstance(v, int):
                normalized_values.append(v)
            elif isinstance(v, str) and v.strip().isdigit():
                normalized_values.append(int(v.strip()))

        if not normalized_values:
            return

        user = getattr(request, "user", None)
        if not user:
            message = self.core_loader.get("error.user_not_logged_in", "用户未登录") if self.core_loader else "用户未登录"
            raise PermissionDenied(message)

        # 超级管理员跳过校验
        if getattr(user, "is_superuser", False):
            return

        # 获取用户可管理的组织 ID 集合
        user_group_ids = {g["id"] for g in getattr(user, "group_list", [])}

        # 检查是否有无权管理的组织
        invalid_group_ids = set(normalized_values) - user_group_ids
        if invalid_group_ids:
            # 查询数据库获取组名，用于友好的错误提示

            group_names = []
            groups = Group.objects.filter(id__in=invalid_group_ids).values("id", "name")
            group_name_map = {g["id"]: g["name"] for g in groups}
            for gid in invalid_group_ids:
                name = group_name_map.get(gid)
                if name:
                    group_names.append(f"{name}(ID:{gid})")
                else:
                    group_names.append(f"ID:{gid}")

            default_message = "您没有以下组织的权限，无法创建或修改: {invalid_groups}"
            message = self.core_loader.get("error.no_permission_for_groups", default_message) if self.core_loader else default_message
            message = message.format(invalid_groups=", ".join(group_names))
            raise PermissionDenied(message)

    def filter_rules(self, rules):
        """根据规则过滤查询集"""
        if not rules:
            return []

        if len(rules) == 1 and isinstance(rules[0], dict) and str(rules[0].get("id")) in self.SUPERUSER_RULE_ID:
            return []

        rule_ids = []
        for rule in rules:
            if isinstance(rule, dict) and "id" in rule:
                rule_ids.append(int(rule["id"]))
        if 0 in rule_ids:
            return []
        return rule_ids

    def create(self, request, *args, **kwargs):
        """重写创建方法以支持组织权限校验"""
        org_field = self.ORGANIZATION_FIELD
        data = request.data

        # 校验提交的组织字段是否在用户可管理范围内
        if org_field in data:
            org_values = self._normalize_org_values(data, org_field)
            self._validate_org_field_permission(request, org_values)

        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """重写列表方法以支持权限过滤"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            return self.query_by_groups(request, queryset)
        except Exception as e:
            logger.error(f"Error in list method: {e}")
            raise

    def query_by_groups(self, request, queryset):
        """根据用户组权限过滤查询结果"""
        try:
            new_queryset = self.get_queryset_by_permission(request, queryset)
            return self._list(new_queryset.order_by(self.ORDERING_FIELD))

        except Exception as e:
            logger.error(f"Error in query_by_groups: {e}")
            raise

    def _filter_by_user_groups(self, queryset, current_team):
        """根据用户组过滤查询集"""
        query = Q()

        try:
            if not current_team:
                return query
            teams = [i.strip() for i in current_team.split(",") if i.strip()]
            org_field = self.ORGANIZATION_FIELD
            for i in teams:
                query |= Q(**{f"{org_field}__contains": int(i)})
            return query

        except Exception as e:
            logger.error(f"Error filtering by user groups: {e}")
            return query

    def _list(self, queryset):
        """统一的列表响应处理"""
        try:
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error in _list method: {e}")
            raise

    @staticmethod
    def _normalize_org_values(data, org_field):
        """规范化组织字段为 int 列表，兼容 QueryDict / str / list / int"""
        values = []

        if hasattr(data, "getlist"):
            raw_list = data.getlist(org_field)
            if raw_list:
                values = raw_list
            elif org_field in data:
                values = [data.get(org_field)]
        elif isinstance(data, dict) and org_field in data:
            raw_value = data.get(org_field)
            values = raw_value if isinstance(raw_value, list) else [raw_value]

        normalized = []
        for value in values:
            if value is None:
                continue

            if isinstance(value, int):
                normalized.append(value)
                continue

            if isinstance(value, str):
                v = value.strip()
                if not v:
                    continue

                # 支持 "1,2" / "1" / "[1,2]"
                if v.startswith("[") and v.endswith("]"):
                    try:
                        import json

                        parsed = json.loads(v)
                        if isinstance(parsed, list):
                            for item in parsed:
                                try:
                                    normalized.append(int(item))
                                except Exception:
                                    continue
                            continue
                    except Exception:
                        pass

                if "," in v:
                    for item in v.split(","):
                        item = item.strip()
                        if not item:
                            continue
                        try:
                            normalized.append(int(item))
                        except Exception:
                            continue
                    continue

                try:
                    normalized.append(int(v))
                except Exception:
                    continue

        return normalized

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_detail(request, *args, **kwargs)
        return Response(serializer.data)

    def get_detail(self, request, *args, **kwargs):
        """获取详情"""
        user = getattr(request, "user", None)
        instance = self.get_object()
        if getattr(user, "is_superuser", False):
            return super().retrieve(request, *args, **kwargs)
        # 验证 current_team 权限
        current_team = self._parse_current_team_cookie(request)
        user_group_ids = {g["id"] for g in getattr(user, "group_list", [])}
        if current_team not in user_group_ids:
            raise PermissionDenied("无权访问该团队数据")
        if hasattr(self, "permission_key"):
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(user, instance, current_team, is_check=True, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_permission_view") if self.loader else "User does not have permission to view this instance"
                return self.value_error(message)
        serializer = self.get_serializer(instance)
        return serializer

    def destroy(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        instance = self.get_object()
        if getattr(user, "is_superuser", False):
            return super().destroy(request, *args, **kwargs)
        # 验证 current_team 权限
        current_team = self._parse_current_team_cookie(request)
        user_group_ids = {g["id"] for g in getattr(user, "group_list", [])}
        if current_team not in user_group_ids:
            raise PermissionDenied("无权访问该团队数据")
        if hasattr(self, "permission_key"):
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(user, instance, current_team, include_children=include_children)
            if not has_permission:
                message = self.loader.get("error.no_permission_delete") if self.loader else "User does not have permission to delete this instance"
                return self.value_error(message)
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """重写更新方法以支持权限控制"""
        try:
            user = getattr(request, "user", None)
            partial = kwargs.pop("partial", False)
            data = request.data
            instance = self.get_object()
            org_field = self.ORGANIZATION_FIELD
            instance_org_value = getattr(instance, org_field, [])
            if not isinstance(instance_org_value, list):
                instance_org_value = []

            if getattr(user, "is_superuser", False):
                if org_field in data:
                    org_values = self._normalize_org_values(data, org_field)
                    delete_team = [i for i in instance_org_value if i not in org_values]
                    self.delete_rules(instance.id, delete_team)
                return super().update(request, *args, **kwargs)

            current_team = self._parse_current_team_cookie(request, default=None)
            if current_team is None:
                message = self.loader.get("error.invalid_current_team") if self.loader else "Invalid current_team cookie"
                return self.value_error(message)
            if current_team not in instance_org_value:
                message = self.loader.get("error.no_permission_update") if self.loader else "User does not have permission to update this instance"
                return self.value_error(message)
            if hasattr(self, "permission_key"):
                include_children = request.COOKIES.get("include_children", "0") == "1"
                has_permission = self.get_has_permission(user, instance, current_team, include_children=include_children)
                if not has_permission:
                    message = (
                        self.loader.get("error.no_permission_update") if self.loader else "User does not have permission to update this instance"
                    )
                    return self.value_error(message)
            if org_field in data:
                org_values = self._normalize_org_values(data, org_field)
                # 校验新增的组织是否在用户可管理范围内
                new_groups = set(org_values) - set(instance_org_value)
                if new_groups:
                    self._validate_org_field_permission(request, list(new_groups))
                delete_team = [i for i in instance_org_value if i not in org_values]
                self.delete_rules(instance.id, delete_team)
            serializer = self.get_serializer(instance, data=data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            if getattr(instance, "_prefetched_objects_cache", None):
                instance._prefetched_objects_cache = {}

            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error in update method: {e}")
            raise

    def delete_rules(self, instance_id, delete_team):
        if not hasattr(self, "permission_key"):
            return
        if not delete_team:
            return
        app_name = self._get_app_name()
        try:
            delete_instance_rules(app_name, self.permission_key, instance_id, delete_team)
        except Exception as e:
            logger.error(e)

    def _validate_name(self, name, group_list, org_value, exclude_id=None):
        """验证名称在团队中的唯一性"""
        try:
            if not name or not isinstance(name, str):
                return ""

            if not isinstance(group_list, list) or not isinstance(org_value, list):
                return ""

            org_field = self.ORGANIZATION_FIELD
            queryset = self.queryset.filter(name=name)
            if exclude_id:
                queryset = queryset.exclude(id=exclude_id)

            team_list = list(queryset.values_list(org_field, flat=True))
            existing_teams = []

            for team_data in team_list:
                if isinstance(team_data, list):
                    existing_teams.extend(team_data)

            team_name_map = {}
            for group in group_list:
                if isinstance(group, dict) and "id" in group and "name" in group:
                    team_name_map[group["id"]] = group["name"]

            for team_id in org_value:
                if team_id in existing_teams:
                    conflict_team_name = team_name_map.get(team_id, f"Team-{team_id}")
                    return conflict_team_name

            return ""

        except Exception as e:
            logger.error(f"Error in _validate_name: {e}")
            return ""
