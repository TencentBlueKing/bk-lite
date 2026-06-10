from typing import Any, Dict, List, Optional, Set

import pytz
from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import IntegrityError
from django.utils import timezone as django_timezone
from django.utils import translation

from apps.base.models import User, UserAPISecret
from apps.core.constants import VERIFY_TOKEN_USER_NOT_FOUND_CODE, VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE
from apps.core.logger import logger
from apps.core.utils.custom_error import DoesNotExist
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

# 常量定义
DEFAULT_LOCALE = "en"
CHINESE_LOCALE_MAPPING = {"zh-CN": "zh-Hans"}
COOKIE_CURRENT_TEAM = "current_team"
CLIENT_ID_ENV_KEY = "CLIENT_ID"


class APISecretAuthBackend(ModelBackend):
    """API密钥认证后端"""

    # 缓存配置
    PERMISSION_CACHE_TTL = 60  # 权限缓存 TTL（秒）
    PERMISSION_CACHE_KEY_PREFIX = "api_token_permissions"

    def authenticate(self, request=None, username=None, password=None, api_token=None, **kwargs) -> Optional[User]:
        """使用API token进行用户认证"""
        if not api_token:
            return None

        user_secret = None
        try:
            user_secret = UserAPISecret._default_manager.get(api_secret=api_token)
            user = User._default_manager.get(username=user_secret.username, domain=user_secret.domain)
            user.group_list = [user_secret.team]

            # 填充用户权限信息
            self._populate_user_permissions(user, user_secret.team)

            return user

        except ObjectDoesNotExist:
            return None
        except MultipleObjectsReturned:
            logger.error("Duplicate API token records detected")
            return None
        except Exception as e:
            if user_secret is not None:
                logger.error("API token authentication failed for %s@%s: %s", user_secret.username, user_secret.domain, str(e))
            else:
                logger.error(f"API token authentication failed: {e}")
            return None

    def _get_permission_cache_key(self, username: str, domain: str, team: int) -> str:
        """生成权限缓存 key"""
        return f"{self.PERMISSION_CACHE_KEY_PREFIX}:{username}:{domain}:{team}"

    def _populate_user_permissions(self, user: User, team: int) -> None:
        """
        为 API Token 用户填充权限信息

        复用 system_mgmt/nats_api.py 中的权限计算逻辑，
        确保 API Token 用户与 Web Token 用户的权限模型一致。
        """
        try:
            # 尝试从缓存获取
            cache_key = self._get_permission_cache_key(user.username, user.domain, team)
            cached = cache.get(cache_key)
            if cached:
                user.roles = cached.get("roles", [])
                user.permission = {k: set(v) for k, v in cached.get("permission", {}).items()}
                user.is_superuser = cached.get("is_superuser", False)
                user.role_ids = cached.get("role_ids", [])
                return

            # 获取用户所有角色
            all_role_ids = self._get_user_all_roles(user)

            # 获取角色名称
            role_list = Role.objects.filter(id__in=all_role_ids)
            role_names = [f"{role.app}--{role.name}" if role.app else role.name for role in role_list]

            # 判断是否超级用户
            is_superuser = "admin" in role_names or "system-manager--admin" in role_names

            # 获取权限（菜单）
            permission: Dict[str, Set[str]] = {}
            if not is_superuser:
                menu_list = role_list.values_list("menu_list", flat=True)
                menu_ids: List[int] = []
                for i in menu_list:
                    if i:
                        menu_ids.extend(i)
                menu_data = Menu.objects.filter(id__in=list(set(menu_ids))).values_list("app", "name")
                for app, name in menu_data:
                    permission.setdefault(app, set()).add(name)

            # 设置到用户对象
            user.roles = role_names
            user.permission = permission
            user.is_superuser = is_superuser
            user.role_ids = list(all_role_ids)

            # 缓存结果
            cache.set(
                cache_key,
                {
                    "roles": role_names,
                    "permission": {k: list(v) for k, v in permission.items()},
                    "is_superuser": is_superuser,
                    "role_ids": list(all_role_ids),
                },
                self.PERMISSION_CACHE_TTL,
            )

        except Exception as e:
            logger.error(f"Failed to populate user permissions for {user.username}@{user.domain}: {e}")
            # 设置空权限，让权限检查正常拒绝
            user.roles = []
            user.permission = {}
            user.is_superuser = False
            user.role_ids = []

    def _get_user_all_roles(self, user: User) -> Set[int]:
        """
        获取用户的所有角色（个人角色 + 组角色，含完整继承链）

        继承规则：沿 parent_id 链向上追溯，只要父级 allow_inherit_roles=True，
        就收集该父级的角色并继续向上，直到某层 allow_inherit_roles=False 或到达根节点为止。

        复用 system_mgmt/nats_api.py 中 get_user_all_roles 的逻辑。
        """
        # 用户直接授权的角色：base.User 存储的是 role_names，需从 system_mgmt.User 获取 role_list（ID 列表）
        try:
            sys_user = SystemUser.objects.filter(username=user.username, domain=user.domain).first()
            personal_role_ids = set(sys_user.role_list if sys_user and sys_user.role_list else [])
        except Exception:
            personal_role_ids = set()

        group_role_ids: Set[int] = set()
        user_groups = user.group_list or []

        if user_groups:
            # 单次查询所有组织，内存中完成递归，避免 N+1
            all_groups = {g.id: g for g in Group.objects.prefetch_related("roles").all()}
            visited: Set[int] = set()

            def collect_roles(group_id: int) -> None:
                if group_id in visited:
                    return
                visited.add(group_id)

                group = all_groups.get(group_id)
                if not group:
                    return

                # 收集自身角色
                for role in group.roles.all():
                    group_role_ids.add(role.id)

                # 向上追溯：父级 allow_inherit_roles=True 才继续继承
                parent_id = group.parent_id
                if parent_id:
                    parent = all_groups.get(parent_id)
                    if parent and parent.allow_inherit_roles:
                        collect_roles(parent_id)

            for gid in user_groups:
                # 处理 group_list 可能是 [{"id": 1}] 或 [1] 的情况
                if isinstance(gid, dict):
                    gid = gid.get("id")
                if gid:
                    collect_roles(gid)

        return personal_role_ids | group_role_ids


class AuthBackend(ModelBackend):
    """标准认证后端"""

    def authenticate(self, request=None, username=None, password=None, token=None, **kwargs) -> Optional[User]:
        """使用token进行用户认证"""
        if not token:
            return None

        try:
            result = self._verify_token_with_system_mgmt(token)
            if not result:
                return None

            user_info = result.get("data")
            if not user_info:
                logger.error("Token verification returned empty user info")
                return None

            self._handle_user_locale(user_info)
            rules = self._get_user_rules(request, user_info)

            return self.set_user_info(request, user_info, rules)

        except DoesNotExist:
            raise
        except Exception as e:
            logger.error(f"Token authentication failed: {e}")
            return None

    def _verify_token_with_system_mgmt(self, token: str) -> Optional[Dict[str, Any]]:
        """使用SystemMgmt验证token"""
        try:
            client = SystemMgmt()
            result = client.verify_token(token)
            if not isinstance(result, dict):
                logger.error("Token verification returned invalid result type: %s", type(result).__name__)
                return None
            if not result.get("result"):
                error_code = result.get("error_code", "")
                error_message = result.get("message", "")
                if error_code == VERIFY_TOKEN_USER_NOT_FOUND_CODE or error_message == VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE:
                    raise DoesNotExist(error_message)
            if not result.get("result"):
                return None

            return result

        except DoesNotExist:
            raise
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            raise

    def _handle_user_locale(self, user_info: Dict[str, Any]) -> None:
        """处理用户locale设置"""
        locale = user_info.get("locale")
        if not locale:
            return

        if locale in CHINESE_LOCALE_MAPPING:
            user_info["locale"] = CHINESE_LOCALE_MAPPING[locale]
            locale = user_info["locale"]

        try:
            translation.activate(locale)
        except Exception:
            pass  # 忽略locale设置失败

        # 处理用户时区设置
        timezone = user_info.get("timezone")
        if not timezone:
            return

        try:
            tz = pytz.timezone(timezone)
            django_timezone.activate(tz)
        except Exception as e:
            logger.warning(f"Failed to activate timezone {timezone}: {e}")

    def _get_user_rules(self, request, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户规则权限"""
        if not request or not hasattr(request, "COOKIES"):
            return {}

        current_group = request.COOKIES.get(COOKIE_CURRENT_TEAM)
        username = user_info.get("username")

        if not current_group or not username:
            return {}

        try:
            client = SystemMgmt()
            rules = client.get_user_rules(current_group, username)
            if not isinstance(rules, dict):
                return {}
            return rules or {}
        except Exception as e:
            logger.error(f"Failed to get user rules for {username}: {e}")
            return {}

    @staticmethod
    def get_is_superuser(request, user_info) -> bool:
        """检查用户是否为超级用户"""
        is_superuser = bool(user_info.get("is_superuser", False))
        if is_superuser:
            return True
        app_name = request.path.split("api/v1/")[-1].split("/", 1)[0]
        app_name_map = {
            "system_mgmt": "system-manager",
            "node_mgmt": "node",
            "console_mgmt": "ops-console",
            "operation_analysis": "ops-analysis",
            "job_mgmt": "job",
        }
        app_name = app_name_map.get(app_name, app_name)
        app_admin = f"{app_name}--admin"
        return app_admin in user_info.get("roles", [])

    def set_user_info(self, request, user_info: Dict[str, Any], rules: Dict[str, Any]) -> Optional[User]:
        """设置用户信息"""
        username = user_info.get("username")
        if not username:
            logger.error("Username not provided in user_info")
            return None

        try:
            domain = user_info.get("domain", "domain.com")
            user, created = User._default_manager.get_or_create(username=username, domain=domain)
            is_superuser = self.get_is_superuser(request, user_info)
            # 更新用户基本信息
            user.email = user_info.get("email", "")
            user.is_superuser = is_superuser
            user.is_staff = user.is_superuser
            user.is_active = True
            user.group_list = user_info.get("group_list", [])
            user.roles = user_info.get("roles", [])
            user.locale = user_info.get("locale", DEFAULT_LOCALE)
            user.save()
            # 设置运行时属性
            user.timezone = user_info.get("timezone", "Asia/Shanghai")
            user.rules = rules
            user.permission = {key: set(value) for key, value in user_info.get("permission", {}).items()}
            user.role_ids = user_info.get("role_ids", [])
            user.display_name = user_info.get("display_name", "")
            user.group_tree = user_info.get("group_tree", [])
            return user

        except MultipleObjectsReturned:
            domain = user_info.get("domain", "domain.com")
            logger.error("Duplicate users detected for token owner: %s@%s", username, domain)
            return None
        except IntegrityError as e:
            logger.error(f"Database integrity error for user {username}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create/update user {username}: {e}")
            return None
