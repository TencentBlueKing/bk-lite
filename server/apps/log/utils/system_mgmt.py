from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtUtils:
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
