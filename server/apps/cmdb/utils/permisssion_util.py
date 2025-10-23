from apps.cmdb.constants import PERMISSION_MODEL, PERMISSION_INSTANCES, OPERATE, VIEW
from apps.cmdb.services.model import ModelManage


class CmdbRulesFormatUtil:

    @staticmethod
    def get_rules_classification_id_list(rules, classification_id=None):
        permission_map = CmdbRulesFormatUtil.format_permission_map(rules, classification_id)
        model_list = []
        classification_id_list = []
        for _classification_id, _permission_map in permission_map.items():
            if _permission_map["select_all"]:
                classification_id_list.append(_classification_id)
            else:
                for model_id, permission in _permission_map["permission_map"].items():
                    if VIEW in permission:
                        model_list.append(model_id)

        return model_list, classification_id_list

    @staticmethod
    def has_object_permission(obj_type, operator, model_id, permission_instances_map, instance={}, team_id=None,
                              default_group_id=None):
        """
        检查用户是否有权限操作对象
        :param model_id: 模型id
        :param obj_type: 对象类型，例如 "model" 或 "instance"
        :param operator: 操作类型
        :param permission_instances_map: 实例权限映射
        :param instance: 实例
            {'organization': [1], 'inst_name': 'VMware vCenter Server222', 'ip_addr': '10.10.41.149',
            'model_id': 'vmware_vc', '_creator': 'admin', '_id': 1132, '_labels': 'instance'}
        :param team_id: 用户组织ID
        :param default_group_id: 默认组织ID
        :return: 是否有权限
        """
        if obj_type == "model":
            if model_id in permission_instances_map:
                permission = permission_instances_map[model_id]
            else:
                group = instance["group"]
                if team_id in group:
                    permission = [VIEW, OPERATE]
                elif default_group_id is not None and default_group_id in group:
                    permission = [VIEW]
                else:
                    permission = []

            return operator in permission


        elif obj_type == "instances":
            inst_name = instance.get("inst_name")
            team_ids = instance.get("organization", [])
            if inst_name:
                operators = permission_instances_map.get(inst_name, [])
                if not operators:
                    if team_id and int(team_id) in team_ids:
                        return True
                else:
                    return operator in operators

        return False

    @staticmethod
    def format_permission_map(rules, _classification_id=None, model_id=None):
        rules = [i for i in rules if i.get("id") != "-1"]
        permission_map = {}
        for classification_id, permission_data in rules.items():
            if _classification_id and classification_id != _classification_id:
                continue
            _map_data = {"select_all": False, "permission_map": {}}
            if not model_id:
                for data in permission_data:
                    if data["id"] in ["0"]:
                        _map_data["select_all"] = True
                        _map_data["permission_map"] = data["permission"]
                        permission_map[classification_id] = _map_data
                        break
                    _map_data["permission_map"][data["id"]] = data["permission"]
                    permission_map[classification_id] = _map_data

            else:
                for _model_id, _permission_data in permission_data.items():
                    if _model_id != model_id:
                        continue
                    _map_data = {"select_all": False, "permission_map": {}}
                    for _model_data in _permission_data:
                        if _model_data["id"] in ["0"]:
                            _map_data["select_all"] = True
                            _map_data["permission_map"] = _model_data["permission"]
                            permission_map[model_id] = _map_data
                            break
                        _map_data["permission_map"][_model_data["id"]] = _model_data["permission"]
                    permission_map[model_id] = _map_data
        return permission_map

    @staticmethod
    def format_permission_instances_list(rules):
        """
        [{'id': '产研vc', 'name': '产研vc', 'permission': ['View']}]
        """
        result = {}
        for rule in rules:
            inst_name = rule["id"]
            if inst_name == "-1":
                continue
            permission = rule["permission"]
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
