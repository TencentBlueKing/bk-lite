from typing import Any, Dict

from apps.core.logger import logger
from apps.rpc.system_mgmt import SystemMgmt

USER_LIST_MAX_PAGE_SIZE = 10000


class UserGroup:
    @staticmethod
    def get_system_mgmt_client() -> SystemMgmt:
        """获取系统管理客户端"""
        try:
            return SystemMgmt()
        except Exception as e:
            logger.error("Failed to create SystemMgmt client: %s", e)
            raise

    @classmethod
    def user_list(cls, system_mgmt_client: SystemMgmt, actor_context: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
        """当前组织授权范围内的用户选择器列表。"""
        search = query_params.get("search") or ""
        try:
            page = int(query_params.get("page", 1))
            page_size = int(query_params.get("page_size", 20))
        except (ValueError, TypeError):
            page, page_size = 1, 20
        page = max(page, 1)
        page_size = min(max(page_size, 1), USER_LIST_MAX_PAGE_SIZE)
        include_children = bool((actor_context or {}).get("include_children"))
        result = system_mgmt_client.get_group_users_scoped(
            actor_context,
            include_children=include_children,
            search=search,
        )
        if not isinstance(result, dict) or result.get("result") is False:
            message = result.get("message") if isinstance(result, dict) else "user list query failed"
            raise RuntimeError(message)
        users = list(result.get("data") or [])
        start = (page - 1) * page_size
        return {"count": len(users), "users": users[start : start + page_size]}

    @classmethod
    def get_all_users(cls, system_mgmt_client: SystemMgmt) -> Dict[str, Any]:
        """用户列表"""
        try:
            result = system_mgmt_client.get_all_users()
            data = result["data"]
            return {"count": data.__len__(), "users": data}
        except Exception as e:
            logger.error("Failed to search users: %s", e)
            raise

    @classmethod
    def get_all_groups(cls, system_mgmt_client: SystemMgmt) -> Any:
        """获取所有用户组"""
        try:
            groups = system_mgmt_client.get_all_groups()
            return groups["data"]
        except Exception as e:
            logger.error("Failed to get all groups: %s", e)
            raise
