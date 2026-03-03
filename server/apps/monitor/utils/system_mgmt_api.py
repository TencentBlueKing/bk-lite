from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtUtils:
    @staticmethod
    def get_user_all(group=None, include_children=False):
        result = SystemMgmt().get_group_users(
            group=group, include_children=include_children
        )
        return result["data"]

    @staticmethod
    def search_channel_list(channel_type="", teams=None, include_children=False):
        """email、enterprise_wechat"""
        result = SystemMgmt().search_channel_list(
            channel_type, teams=teams, include_children=include_children
        )
        return result["data"]

    @staticmethod
    def send_msg_with_channel(channel_id, title, content, receivers):
        result = SystemMgmt().send_msg_with_channel(
            channel_id, title, content, receivers
        )
        return result

    @staticmethod
    def format_rules(module, child_module, rules):
        rule = rules.get("monitor", {})
        combined_map = {}

        # 合并 normal 和 guest 下的规则
        for rule_type in ["normal", "guest"]:
            for j in [i for i in rule.get(rule_type, {}).get(module, {}).values()]:
                combined_map.update(**j)

        rule_items = combined_map.get(child_module, [])

        instance_permission_map = {}
        # 相同实例权限列表合并去重
        for item in rule_items:
            if item["id"] not in instance_permission_map:
                instance_permission_map[item["id"]] = item["permission"]
            instance_permission_map[item["id"]].extend(item["permission"])

        for instance_id, permissions in instance_permission_map.items():
            # 去重权限
            instance_permission_map[instance_id] = list(set(permissions))

        if (
            "0" in instance_permission_map
            or "-1" in instance_permission_map
            or not instance_permission_map
        ):
            return None
        return instance_permission_map

    @staticmethod
    def format_rules_v2(module, rules):
        all_permission_objs = set()
        instance_map = {}

        combined_map = {}
        # Merge rules from both "normal" and "guest"
        for rule_type in ["normal", "guest"]:
            rule = rules.get("monitor", {}).get(rule_type, {})
            for j in [i for i in rule.get(module, {}).values()]:
                combined_map.update(**j)

        for obj, instance_rules in combined_map.items():
            for instance_rule in instance_rules:
                if instance_rule["id"] in {"0", "-1"}:
                    all_permission_objs.add(obj)
                    continue
                if instance_rule["id"] not in instance_map:
                    instance_map[instance_rule["id"]] = []
                instance_map[instance_rule["id"]].extend(instance_rule["permission"])

        # Remove duplicate permissions for each instance
        for instance_id, permissions in instance_map.items():
            instance_map[instance_id] = list(set(permissions))

        return all_permission_objs, instance_map
