import logging

from django.conf import settings
from django.contrib import auth
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _
from ipware import get_client_ip
from rest_framework import status

from apps.core.utils.web_utils import WebUtils

logger = logging.getLogger(__name__)


class APISecretMiddleware(MiddlewareMixin):
    """API令牌认证中间件"""

    API_PASS_ATTR = "api_pass"
    TOKEN_MISSING_MSG = "token validation failed"

    def process_request(self, request):
        """处理请求的API令牌验证"""
        # 获取API令牌
        token = self._get_api_token(request)
        if token is None:
            setattr(request, self.API_PASS_ATTR, False)
            return None

        # 验证令牌并进行用户认证
        try:
            user = auth.authenticate(request=request, api_token=token)
            if user is not None:
                return self._handle_successful_auth(request, user)
            else:
                return self._handle_failed_auth(request)

        except Exception as e:
            logger.error("API令牌验证异常: %s", str(e))
            return WebUtils.response_error(error_message=_(self.TOKEN_MISSING_MSG), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_api_token(self, request):
        """从请求头中获取API令牌"""
        header_name = getattr(settings, "API_TOKEN_HEADER_NAME", None)
        if not header_name:
            logger.error("API_TOKEN_HEADER_NAME配置缺失")
            return None

        return request.META.get(header_name)

    def _handle_successful_auth(self, request, user):
        """处理认证成功的情况"""
        setattr(request, self.API_PASS_ATTR, True)
        auth.login(request, user)

        # 确保会话密钥存在
        if not request.session.session_key:
            request.session.cycle_key()

        return None

    def _handle_failed_auth(self, request):
        """处理认证失败的情况"""
        client_ip, _ = get_client_ip(request)
        logger.warning("API令牌验证失败 - IP: %s, 路径: %s", client_ip or "unknown", request.path)

        return WebUtils.response_error(error_message=_(self.TOKEN_MISSING_MSG), status_code=status.HTTP_403_FORBIDDEN)
