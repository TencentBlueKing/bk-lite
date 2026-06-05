import uuid

from apps.cmdb.constants.constants import OPERATE, VIEW, PERMISSION_INSTANCES, APP_NAME
from apps.cmdb.utils.base import get_current_team_from_request
from apps.core.utils.permission_utils import get_permission_rules
from apps.system_mgmt.utils.group_utils import GroupUtils


DENY_PERMISSION_PLACEHOLDER = "__cmdb_no_permission__"


class CmdbRulesFormatUtil:

    @staticmethod
    def _normalize_user_group_ids(group_list):
        group_list = group_list or []
        result = []
        for item in group_list:
            group_id = item.get("id") if isinstance(item, dict) else item
            if group_id is None:
                continue
            result.append(int(group_id))
        return result

    @staticmethod
    def _normalize_team_rule_ids(team_rules):
        result = set()
        for item in team_rules or []:
            team_id = item.get("id") if isinstance(item, dict) else item
            if team_id is None:
                continue
            try:
                result.add(int(team_id))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def get_authorized_team_ids(user, current_team, include_children):
        current_team = int(current_team)
        if getattr(user, "is_superuser", False):
            return GroupUtils.get_group_with_descendants(current_team) if include_children else [current_team]

        user_group_ids = CmdbRulesFormatUtil._normalize_user_group_ids(getattr(user, "group_list", []))
        if not user_group_ids:
            return []

        return GroupUtils.get_user_authorized_child_groups(
            user_group_list=user_group_ids,
            target_group_id=current_team,
            include_children=include_children,
        )

    @staticmethod
    def build_deny_permission_data():
        deny_value = f"{DENY_PERMISSION_PLACEHOLDER}:{uuid.uuid4().hex}"
        return {
            "permission_instances_map": {deny_value: []},
            "inst_names": [deny_value],
        }

    @staticmethod
    def build_permission_rule_map(user_teams, permission_rules, fallback_team_id=None):
        teams = CmdbRulesFormatUtil._normalize_team_rule_ids(permission_rules.get("team", []))
        instance = permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil.format_permission_instances_list(instances=instance)
        inst_names = list(permission_instances_map.keys())

        permission_rule_map = {}
        for team in user_teams:
            team = int(team)
            if team in teams:
                permission_rule_map[team] = {
                    "permission_instances_map": {},
                    "inst_names": [],
                }
                continue

            if permission_instances_map:
                permission_rule_map[team] = {
                    "permission_instances_map": permission_instances_map,
                    "inst_names": inst_names,
                }
                continue

            permission_rule_map[team] = CmdbRulesFormatUtil.build_deny_permission_data()

        if not permission_rule_map and fallback_team_id is not None:
            permission_rule_map[int(fallback_team_id)] = CmdbRulesFormatUtil.build_deny_permission_data()

        return permission_rule_map

    @staticmethod
    def has_object_permission(obj_type, operator, model_id, permission_instances_map, instance, team_id=None,
                              default_group_id=None):
        """
        检查用户是否有权限操作对象
        :param model_id: 模型id
        :param obj_type: 对象类型，例如 "model" 或 "instance"
        :param operator: 操作类型
        :param permission_instances_map: 实例权限映射
            # {4: {'inst_names': [], 'permission_instances_map': {}, 'team': []},
            # 6: {'inst_names': [], 'permission_instances_map': {}, 'team': []}}
        :param instance: 实例
            {'organization': [1], 'inst_name': 'VMware vCenter Server222', 'ip_addr': '10.10.41.149',
            'model_id': 'vmware_vc', '_creator': 'admin', '_id': 1132, '_labels': 'instance'}
        :param default_group_id: 默认组织ID
        :return: 是否有权限
        """
        organizations_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(
            permission_instances_map)

        if obj_type == "model":
            groups = instance.get("group", [])
            if default_group_id in groups and operator == VIEW:
                return True

            for group in groups:
                if group in organizations_instances_map and operator in organizations_instances_map[group]["permission"]:
                    return True

            permission_data = organizations_instances_map.get(model_id)
            if permission_data and operator in permission_data["permission"]:
                return bool(set(groups) & permission_data["organization"])

            return False


        elif obj_type == "instances":
            inst_name = instance.get("inst_name")
            organizations = instance.get("organization", [])
            for organization in organizations:
                if organization in organizations_instances_map and operator in organizations_instances_map[organization]["permission"]:
                    return True

            permission_data = organizations_instances_map.get(inst_name)
            if permission_data and operator in permission_data["permission"]:
                return bool(set(organizations) & permission_data["organization"])

        return False

    @staticmethod
    def format_permission_instances_list(instances):
        """
        [{'id': '产研vc', 'name': '产研vc', 'permission': ['View']}]
        """
        result = {}
        for instance in instances:
            inst_name = instance["id"]
            if inst_name == "-1":
                continue
            permission = instance["permission"]
            result[inst_name] = permission
        return result

    @staticmethod
    def format_permission_instances_count_list(rules):
        result = {}
        for model_id, rule in rules.items():
            for instance in rule["instance"]:
                inst_name = instance["id"]
                if inst_name == "-1":
                    continue
                permission = instance["permission"]
                result[inst_name] = permission
        return result

    @staticmethod
    def format_search_query_list(default_group, query_list):
        """
        格式化搜索查询列表，将类型为 "str*" 的查询转换为 "str=" 查询
        :param query_list: 原始查询列表 检查是否带了 [{"field": "organization", "type": "list[]", "value": [1]}]
        :param default_group: 请求对象
        :return: 格式化后的查询列表
        """
        has_organization = any([query for query in query_list if query["field"] == "organization"])
        if not has_organization:
            query_list.append({"field": "organization", "type": "list[]", "value": [int(default_group)]})

        return query_list

    @staticmethod
    def pop_organization_query_list(query_list, permissions_map):
        """
        从查询列表中移除组织查询
        :param query_list: 查询列表
        :param permissions_map: 权限映射
        :return: 移除组织查询后的查询列表
        """
        new_query_list = []
        for query in query_list:
            if query["field"] != "organization":
                new_query_list.append(query)
        return new_query_list

    @staticmethod
    def search_organizations(query_list):
        """
        从查询列表中提取组织ID
        :param query_list: 查询列表
        :return: 组织ID列表
        """
        organization_ids = []
        for query in query_list:
            if query["field"] == "organization":
                organization_ids.extend(query["value"])
        return organization_ids

    @staticmethod
    def format_user_groups_permissions(request, model_id, permission_type=PERMISSION_INSTANCES):
        """
        格式化用户组权限映射
        :param request: 请求对象
        :param model_id: 模型ID
        :param permission_type: 权限类型
        :return: 格式化后的权限映射
        """

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        user_teams = CmdbRulesFormatUtil.get_authorized_team_ids(
            user=request.user,
            current_team=current_team,
            include_children=include_children,
        )
        permission_key = f"{permission_type}.{model_id}" if model_id else permission_type
        permission_rules = get_permission_rules(
            user=request.user,
            current_team=current_team,
            app_name=APP_NAME,
            permission_key=permission_key,
            include_children=include_children,
        )
        if not isinstance(permission_rules, dict):
            permission_rules = {}

        return CmdbRulesFormatUtil.build_permission_rule_map(
            user_teams=user_teams,
            permission_rules=permission_rules,
            fallback_team_id=current_team,
        )

    @staticmethod
    def format_organizations_instances_map(permission_instances_map):
        """
        :param permission_instances_map: 权限数据
        {4: {'inst_names': ['VC-同名'], 'permission_instances_map': {'VC-同名': ['View']}, 'team': []},
        6: {'inst_names': ['VC3'], 'permission_instances_map': {'VC3': ['View', 'Operate']}, 'team': []}}
        """
        organizations_instances_map = {}
        for organizations_id, _permission_data in permission_instances_map.items():
            instances_map = _permission_data.get("permission_instances_map", {})
            if "__default_model" in _permission_data:
                organizations_instances_map[organizations_id] = {"permission": {VIEW},
                                                                 "organization": {organizations_id}}
                continue
            if not instances_map:
                # 说明这个组织没有额外配置条件 则全选都有权限
                organizations_instances_map[organizations_id] = {"permission": {VIEW, OPERATE},
                                                                 "organization": {organizations_id}}
                continue
            for inst_name, permission in instances_map.items():
                if inst_name not in organizations_instances_map:
                    organizations_instances_map[inst_name] = {"permission": set(permission),
                                                              "organization": {organizations_id}}
                else:
                    organizations_instances_map[inst_name]["permission"].update(set(permission))
                    organizations_instances_map[inst_name]["organization"].add(organizations_id)

        return organizations_instances_map
