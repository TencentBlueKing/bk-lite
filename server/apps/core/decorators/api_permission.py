import logging
import os
from functools import wraps
from typing import Any, Callable, List, Set, Union

from django.utils.translation import gettext as _
from django.views.generic.base import View

from apps.core.utils.web_utils import WebUtils

logger = logging.getLogger("app")


def _extract_request(args: tuple) -> Any:
    """从参数中提取请求对象"""
    request = args[0]
    if isinstance(request, View):
        return args[1] if len(args) > 1 else None
    return request


def _get_app_name(task_definition: Callable) -> str:
    """获取装饰器所在文件的app名称"""
    module = task_definition.__module__
    if module and "." in module:
        parts = module.split(".")
        # 查找apps后面的部分作为app名称
        try:
            apps_index = parts.index("apps")
            if apps_index + 1 < len(parts):
                return parts[apps_index + 1]
        except ValueError:
            pass
    return ""


class HasRole(object):
    def __init__(self, roles: Union[str, List[str], None] = None):
        self.roles = self._normalize_roles(roles)

    def _normalize_roles(self, roles: Union[str, List[str], None]) -> List[str]:
        """标准化角色列表"""
        if roles is None:
            return []

        if isinstance(roles, str):
            if roles == "admin":
                client_id = os.getenv("CLIENT_ID", "")
                return ["admin", f"{client_id}_admin"] if client_id else ["admin"]
            return [roles]

        if isinstance(roles, list):
            return roles

        return []

    def __call__(self, task_definition: Callable) -> Callable:
        @wraps(task_definition)
        def wrapper(*args, **kwargs):
            request = _extract_request(args)
            if request is None:
                return WebUtils.response_403(_("insufficient permissions"))

            # 检查API通行证
            if getattr(request, "api_pass", False):
                return task_definition(*args, **kwargs)

            # 如果没有指定角色要求，直接通过
            if not self.roles:
                return task_definition(*args, **kwargs)

            # 获取用户角色并检查权限
            user_roles = getattr(request.user, "roles", [])
            for role in user_roles:
                if role in self.roles:
                    return task_definition(*args, **kwargs)

            logger.warning(f"Access denied. Required roles: {self.roles}, user roles: {user_roles}")
            return WebUtils.response_403(_("insufficient permissions"))

        return wrapper


class HasPermission(object):
    def __init__(self, permission: str = "", app_name=""):
        self.permission = self._parse_permissions(permission)
        self.app_name = app_name

    def _parse_permissions(self, permission: str) -> Set[str]:
        """解析权限字符串为集合"""
        if not permission:
            return set()
        return {p.strip() for p in permission.split(",") if p.strip()}

    def _get_user_permissions(self, request, app_name: str) -> Set[str]:
        """获取用户在指定app下的权限集合"""
        app_name_map = {"system_mgmt": "system-manager", "node_mgmt": "node", "console_mgmt": "ops-console", "alerts": "alarm","operation_analysis":"ops-analysis"}
        if not self.app_name:
            app_name = app_name_map.get(app_name, app_name)
        else:
            app_name = self.app_name

        user_permissions = getattr(request.user, "permission", set())

        # 处理新格式: {"app": set()}
        if isinstance(user_permissions, dict):
            return user_permissions.get(app_name, set())

        # 兼容旧格式: set()
        if isinstance(user_permissions, set):
            return user_permissions

        return set()

    def __call__(self, task_definition: Callable) -> Callable:
        @wraps(task_definition)
        def wrapper(*args, **kwargs):
            request = _extract_request(args)
            if request is None:
                return WebUtils.response_403(_("insufficient permissions"))

            # 检查API通行证
            if getattr(request, "api_pass", False):
                return task_definition(*args, **kwargs)

            # 检查超级用户
            if getattr(request.user, "is_superuser", False):
                return task_definition(*args, **kwargs)

            # 获取app名称和用户权限
            app_name = _get_app_name(task_definition)
            user_permissions = self._get_user_permissions(request, app_name)

            # 检查权限交集
            if self.permission & user_permissions:
                return task_definition(*args, **kwargs)

            logger.warning(f"Access denied. App: {app_name}," f" Required permissions: {self.permission}," f"user permissions: {user_permissions}")
            return WebUtils.response_403(_("insufficient permissions"))

        return wrapper
