import json
import logging
import traceback

from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils

logger = logging.getLogger("app")


class AppExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        """
        app后台错误统一处理
        """

        self.exception = exception
        self.request = request

        # 用户自我感知的异常抛出
        if isinstance(exception, BaseAppException):
            logger.log(
                exception.LOG_LEVEL,
                """捕获主动抛出异常, 具体异常堆栈->[%s] status_code->[%s] & """
                """client_message->[%s] & args->[%s] """
                % (
                    traceback.format_exc(),
                    exception.ERROR_CODE,
                    exception.message,
                    exception.args,
                ),
            )

            return WebUtils.response_error(error_message=exception.message, status_code=exception.STATUS_CODE)

        # 用户未主动捕获的异常
        logger.error(
            """捕获未处理异常,异常具体堆栈->[%s], 请求URL->[%s], """
            """请求用户->[%s] 请求方法->[%s] 请求参数->[%s]"""
            % (
                traceback.format_exc(),
                request.path,
                request.user.username,
                request.method,
                json.dumps(getattr(request, request.method, None)),
            )
        )

        return WebUtils.response_error(error_message="系统异常,请联系管理员处理", status_code=500)

    def get_check_functions(self):
        """获取需要判断的函数列表"""
        return [getattr(self, func) for func in dir(self) if func.startswith("check") and callable(getattr(self, func))]

    def check_is_debug(self):
        """判断是否是开发模式"""
        return settings.DEBUG

    def check_is_http404(self):
        """判断是否基于Http404异常"""
        return isinstance(self.exception, Http404)
