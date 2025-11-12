import logging
from typing import Any, Dict, Optional

from django.contrib.auth.backends import ModelBackend
from django.core.cache import caches
from django.db import IntegrityError
from django.utils import translation

from apps.base.models import User, UserAPISecret
from apps.rpc.system_mgmt import SystemMgmt

logger = logging.getLogger("app")
cache = caches["db"]

# 常量定义
DEFAULT_LOCALE = "en"
CHINESE_LOCALE_MAPPING = {"zh-CN": "zh-Hans"}
COOKIE_CURRENT_TEAM = "current_team"
CLIENT_ID_ENV_KEY = "CLIENT_ID"


class APISecretAuthBackend(ModelBackend):
    """API密钥认证后端"""

    def authenticate(self, request=None, username=None, password=None, api_token=None) -> Optional[User]:
        """使用API token进行用户认证"""
        if not api_token:
            return None

        try:
            user_secret = UserAPISecret.objects.filter(api_secret=api_token).first()
            if not user_secret:
                return None

            user = User.objects.get(username=user_secret.username)
            user.group_list = [user_secret.team]
            return user

        except User.DoesNotExist:
            logger.error(f"API token user not found: {user_secret.username}")
            return None
        except Exception as e:
            logger.error(f"API token authentication failed: {e}")
            return None


class AuthBackend(ModelBackend):
    """标准认证后端"""

    def authenticate(self, request=None, username=None, password=None, token=None) -> Optional[User]:
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

        except Exception as e:
            logger.error(f"Token authentication failed: {e}")
            return None

    def _verify_token_with_system_mgmt(self, token: str) -> Optional[Dict[str, Any]]:
        """使用SystemMgmt验证token"""
        try:
            client = SystemMgmt()
            result = client.verify_token(token)
            if not result.get("result"):
                return None

            return result

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
        app_name_map = {"system_mgmt": "system-manager", "node_mgmt": "node", "console_mgmt": "ops-console","operation_analysis":"ops-analysis"}
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
            user, created = User.objects.get_or_create(username=username, domain=domain)
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
            user.rules = rules
            user.permission = {key: set(value) for key, value in user_info.get("permission", {}).items()}
            user.role_ids = user_info.get("role_ids", [])
            user.display_name = user_info.get("display_name", "")
            user.group_tree = user_info.get("group_tree", [])
            return user

        except IntegrityError as e:
            logger.error(f"Database integrity error for user {username}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create/update user {username}: {e}")
            return None
