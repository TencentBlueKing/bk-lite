from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtUtils:
    @staticmethod
    def get_user_all(actor_context=None, group=None, include_children=False):
        # 带 actor_context（用户面调用）走授权范围收口的 scoped 查询，避免返回全平台用户（#3140）；
        # 无 actor_context 仅供系统内部调用方使用。
        if actor_context is not None:
            result = SystemMgmt().get_group_users_scoped(actor_context, group=group, include_children=include_children)
        else:
            result = SystemMgmt().get_group_users(group=group, include_children=include_children)
        return result["data"]

    @staticmethod
    def get_users_by_organizations(actor_context, organization_ids):
        """按策略所属组织拉取通知人候选，且限制在调用方可分配组织内。

        与 current_team 投影不同：跨组织策略（A+B）在 B 下编辑时，仍需能选到 A 组织用户。
        """
        from django.db.models import Q

        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.core.utils.current_team_scope import _normalize_organization_ids
        from apps.system_mgmt.models import User

        if isinstance(organization_ids, str):
            raw_ids = [part.strip() for part in organization_ids.split(",") if part.strip()]
        elif isinstance(organization_ids, (list, tuple, set)):
            raw_ids = list(organization_ids)
        else:
            return []

        if not raw_ids:
            return []

        try:
            requested = _normalize_organization_ids(raw_ids)
        except BaseAppException:
            return []

        assignable_result = SystemMgmt().get_assignable_groups(actor_context)
        if not isinstance(assignable_result, dict) or not assignable_result.get("result"):
            return []
        try:
            assignable = _normalize_organization_ids(assignable_result.get("data") or [])
        except BaseAppException:
            return []

        allowed = requested & assignable
        if not allowed:
            return []

        user_filter = Q()
        for group_id in allowed:
            user_filter |= Q(group_list__contains=int(group_id))

        return list(
            User.objects.filter(user_filter, disabled=False).values(
                "id", "user_id", "username", "display_name"
            )
        )

    @staticmethod
    def search_channel_list(actor_context, channel_type="", teams=None, include_children=False):
        """email、enterprise_wechat"""
        result = SystemMgmt().search_channel_list_scoped(
            actor_context,
            channel_type=channel_type,
            teams=teams,
            include_children=include_children,
        )
        return result["data"]

    @staticmethod
    def send_msg_with_channel(channel_id, title, content, receivers):
        result = SystemMgmt().send_msg_with_channel(channel_id, title, content, receivers)
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

        if "0" in instance_permission_map or "-1" in instance_permission_map or not instance_permission_map:
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
