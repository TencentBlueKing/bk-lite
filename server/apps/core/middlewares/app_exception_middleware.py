import logging
from typing import Optional

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from ipware import get_client_ip

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils

logger = logging.getLogger("app")


class AppExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """
        app后台错误统一处理

        Args:
            request: Django请求对象
            exception: 捕获的异常对象

        Returns:
            HttpResponse: 错误响应或None
        """
        try:
            # 处理用户主动抛出的异常
            if isinstance(exception, BaseAppException):
                return self._handle_app_exception(request, exception)

            # 处理未捕获的系统异常
            return self._handle_system_exception(request, exception)

        except Exception as middleware_error:
            # 中间件自身异常处理，防止异常处理逻辑出错
            logger.critical("异常处理中间件自身发生错误: %s, 原始异常: %s, 请求路径: %s", str(middleware_error), str(exception), getattr(request, "path", "unknown"))
            return WebUtils.response_error(error_message="系统异常,请联系管理员处理", status_code=500)

    def _handle_app_exception(self, request: HttpRequest, exception: BaseAppException) -> HttpResponse:
        """
        处理业务异常

        Args:
            request: Django请求对象
            exception: 业务异常对象

        Returns:
            HttpResponse: 错误响应
        """
        client_ip, _ = get_client_ip(request)

        logger.log(
            exception.LOG_LEVEL,
            "业务异常 - %s [%s] %s %s - %s",
            exception.ERROR_CODE,
            client_ip or "unknown",
            getattr(request, "method", "unknown"),
            getattr(request, "path", "unknown"),
            exception.message,
        )

        return WebUtils.response_error(error_message=exception.message, status_code=exception.STATUS_CODE)

    def _handle_system_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """
        处理系统异常

        Args:
            request: Django请求对象
            exception: 系统异常对象

        Returns:
            HttpResponse: 错误响应
        """
        client_ip, _ = get_client_ip(request)
        username = self._get_username(request)

        logger.error(
            "系统异常 - %s [%s] %s %s - 用户: %s - %s",
            type(exception).__name__,
            client_ip or "unknown",
            getattr(request, "method", "unknown"),
            getattr(request, "path", "unknown"),
            username,
            str(exception),
            exc_info=True,
        )

        return WebUtils.response_error(error_message="系统异常,请联系管理员处理", status_code=500)

    def _get_username(self, request: HttpRequest) -> str:
        """
        安全获取用户名

        Args:
            request: Django请求对象

        Returns:
            str: 用户名或匿名标识
        """
        try:
            if hasattr(request, "user") and hasattr(request.user, "username"):
                return request.user.username
        except Exception:
            # 防止用户对象访问异常
            pass
        return "anonymous"
