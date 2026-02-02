import logging
from typing import Dict, Any, Optional, List, Union

from apps.core.utils.user_group import Group
from apps.rpc.system_mgmt import SystemMgmt

logger = logging.getLogger(__name__)


class UserGroup:
    @staticmethod
    def get_system_mgmt_client() -> SystemMgmt:
        """获取系统管理客户端"""
        try:
            return SystemMgmt()
        except Exception as e:
            logger.error(f"Failed to create SystemMgmt client: {e}")
            raise

    @classmethod
    def user_list(cls, system_mgmt_client: SystemMgmt, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """用户列表"""
        try:
            result = system_mgmt_client.search_users(query_params)
            data = result["data"]
            return {"count": data.get("count", 0), "users": data.get("users", [])}
        except Exception as e:
            logger.error(f"Failed to search users: {e}")
            raise

    @classmethod
    def get_all_users(cls, system_mgmt_client: SystemMgmt) -> Dict[str, Any]:
        """用户列表"""
        try:
            result = system_mgmt_client.get_all_users()
            data = result["data"]
            return {"count": data.__len__(), "users": data}
        except Exception as e:
            logger.error(f"Failed to search users: {e}")
            raise

    @classmethod
    def groups_list(cls, system_mgmt_client: SystemMgmt, query_params: Union[Optional[Dict[str, Any]], str]) -> Any:
        """用户组列表"""
        if not query_params:
            query_params = {"search": ""}
        
        try:
            groups = system_mgmt_client.search_groups(query_params)
            return groups["data"]
        except Exception as e:
            logger.error(f"Failed to search groups: {e}")
            raise

    @classmethod
    def user_groups_list(cls, request) -> Dict[str, Any]:
        """用户组列表"""
        try:
            user = request.user
            
            if getattr(user, 'is_superuser', False):
                return {"is_all": True, "group_ids": []}

            user_groups = getattr(user, 'group_list', [])
            group_instance = Group()
            group_ids = group_instance.get_user_group_and_subgroup_ids(user_group_list=user_groups)
            
            return {"is_all": False, "group_ids": group_ids if isinstance(group_ids, list) else []}
            
        except Exception as e:
            logger.error(f"Failed to process user groups list: {e}")
            return {"is_all": False, "group_ids": []}

    @classmethod
    def get_all_groups(cls, system_mgmt_client: SystemMgmt) -> Any:
        """获取所有用户组"""
        try:
            groups = system_mgmt_client.get_all_groups()
            return groups["data"]
        except Exception as e:
            logger.error(f"Failed to get all groups: {e}")
            raise
