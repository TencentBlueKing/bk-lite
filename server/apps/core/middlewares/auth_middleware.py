import logging

from django.conf import settings
from django.contrib import auth
from django.utils.deprecation import MiddlewareMixin

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils

logger = logging.getLogger(__name__)


class AuthMiddleware(MiddlewareMixin):
    # 豁免路径常量
    EXEMPT_PATHS = [
        "/swagger/",
        "/admin/",
        "/accounts/",
    ]

    def _get_loader(self, request=None) -> LanguageLoader:
        """获取基于用户locale的LanguageLoader"""
        locale = "en"
        if request and hasattr(request, "user") and hasattr(request.user, "locale"):
            locale = request.user.locale or "en"
        return LanguageLoader(app="core", default_lang=locale)

    def process_view(self, request, view, args, kwargs):
        """处理视图请求的认证逻辑"""
        try:
            # 检查豁免条件
            if self._is_exempt(request, view):
                return None

            # 执行Token认证
            return self._authenticate_token(request)

        except Exception as e:
            logger.error("Authentication error for %s: %s", request.path, str(e))
            loader = self._get_loader(request)
            return WebUtils.response_401(loader.get("error.auth_failed", "Authentication failed"))

    def _is_exempt(self, request, view):
        """检查请求是否豁免认证"""
        # 检查API和登录豁免标记
        if getattr(view, "api_exempt", False) or getattr(view, "login_exempt", False) or getattr(request, "api_pass", False):
            return True

        # 检查路径豁免
        request_path = request.path
        return any(request_path == path.rstrip("/") or request_path.startswith(path) for path in self.EXEMPT_PATHS)

    def _authenticate_token(self, request):
        """执行Token认证"""
        # 获取并验证Token
        token = self._extract_token(request)
        if not token:
            logger.warning("Missing or invalid token for %s", request.path)
            loader = self._get_loader(request)
            return WebUtils.response_401(loader.get("error.please_provide_token", "Please provide Token"))

        # 认证用户
        try:
            user = auth.authenticate(request=request, token=token)
            if not user:
                logger.warning("Token authentication failed for %s", request.path)
                loader = self._get_loader(request)
                return WebUtils.response_401(loader.get("error.please_provide_token", "Please provide Token"))

            # 登录用户并确保session有效
            auth.login(request, user)
            if not request.session.session_key:
                request.session.cycle_key()

            return None

        except Exception as e:
            logger.error("Token authentication error for %s: %s", request.path, str(e))
            loader = self._get_loader(request)
            return WebUtils.response_401(loader.get("error.please_provide_token", "Please provide Token"))

    @staticmethod
    def _extract_token(request):
        """从请求头中提取Token"""
        token_header = request.META.get(settings.AUTH_TOKEN_HEADER_NAME)
        if not token_header:
            return None

        # 处理Bearer格式或直接返回token
        if token_header.startswith("Bearer "):
            return token_header[7:].strip()

        return token_header.strip()
