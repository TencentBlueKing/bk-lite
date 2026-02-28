from apps.cmdb.constants.constants import OPERATE, VIEW, PERMISSION_INSTANCES, APP_NAME
from apps.cmdb.utils.base import format_groups_params, get_organization_and_children_ids, get_current_team_from_request
from apps.core.utils.permission_utils import get_permission_rules


class CmdbRulesFormatUtil:

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
            if default_group_id in instance["group"] and operator == VIEW:
                return True
            for group in instance["group"]:
                if group in organizations_instances_map:
                    # 全选
                    return True
                # 具体实例权限判断
                if model_id in organizations_instances_map:
                    permission = organizations_instances_map[model_id]["permission"]
                    if operator in permission:
                        return True
                    else:
                        return group == default_group_id

            return False


        elif obj_type == "instances":
            inst_name = instance.get("inst_name")
            organizations = instance.get("organization", [])
            for organization in organizations:
                if organization in organizations_instances_map:
                    return True
            if inst_name in organizations_instances_map:
                permission = organizations_instances_map[inst_name]["permission"]
                return operator in permission

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
        user_teams = get_organization_and_children_ids(
            tree_data=request.user.group_tree, target_id=current_team
        )
        if not user_teams:
            user_teams = [current_team]
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

        teams = permission_rules.get("team", [])
        instance = permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(instances=instance)
        inst_names = list(permission_instances_map.keys())
        permission_rule_map = {}
        if include_children:
            print(
                "CMDB_DEBUG include_children rules",
                {
                    "current_team": current_team,
                    "user_teams": user_teams,
                    "teams_rule": teams,
                    "inst_rule_count": len(instance),
                    "permission_key": permission_key,
                },
            )

        for team in user_teams:
            if not include_children and team not in teams:
                # 不包含子组织的情况下跳过非当前的组织
                continue
            if team in teams:
                # 全部权限
                permission_rule_map[team] = {
                    "permission_instances_map": {},
                    "inst_names": []
                }
            else:
                permission_rule_map[team] = {
                    "permission_instances_map": permission_instances_map,
                    "inst_names": inst_names
                }

        return permission_rule_map

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
