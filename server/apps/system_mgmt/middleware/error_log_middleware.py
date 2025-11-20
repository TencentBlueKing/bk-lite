"""
错误日志中间件

全局捕获 API 异常并自动记录到错误日志
"""
import re
import traceback

from django.utils.deprecation import MiddlewareMixin

from apps.core.logger import system_mgmt_logger
from apps.system_mgmt.models import ErrorLog


class ErrorLogMiddleware(MiddlewareMixin):
    """
    错误日志中间件

    功能：
    1. 捕获 API 请求过程中的异常
    2. 解析请求路径，识别应用和模块
    3. 自动记录到错误日志表
    4. 不影响原有异常处理流程
    """

    # API 路径模式: /api/v1/{app}/{module}/...
    API_PATH_PATTERN = re.compile(r"^/api/v\d+/([^/]+)/([^/]+)")

    # 需要记录错误日志的应用白名单（为空表示记录所有）
    ALLOWED_APPS = [
        "monitor",
        "cmdb",
        "opspilot",
        "node",
        "system_mgmt",
        "mlops",
        "alarm",
        "log",
        "playground",
        "ops_analysis",
    ]

    def process_exception(self, request, exception):
        """
        处理异常

        Args:
            request: Django request 对象
            exception: 异常对象

        Returns:
            None - 不干预原有异常处理流程
        """
        try:
            # 只处理 API 请求
            if not request.path.startswith("/api/"):
                return None

            # 解析请求路径
            app, module = self._parse_path(request.path)
            if not app:
                return None

            # 检查是否在白名单中（为空则记录所有）
            if self.ALLOWED_APPS and app not in self.ALLOWED_APPS:
                return None

            # 获取用户信息
            username = self._get_username(request)

            # 获取域名
            domain = request.get_host()

            # 构建错误信息
            error_message = self._build_error_message(request, exception)

            # 记录错误日志
            ErrorLog.objects.create(
                username=username,
                app=app,
                module=module,
                error_message=error_message,
                domain=domain,
            )

        except Exception as e:
            # 记录错误日志失败不应影响原有流程
            system_mgmt_logger.error(f"Failed to log error via middleware: {str(e)}")

        # 返回 None，让 Django 继续原有的异常处理流程
        return None

    def _parse_path(self, path):
        """
        解析 API 路径，提取应用和模块

        Args:
            path: 请求路径，如 /api/v1/monitor/alert_rule/

        Returns:
            tuple: (app, module) 或 (None, None)

        Examples:
            /api/v1/monitor/alert_rule/ -> ('monitor', 'alert_rule')
            /api/v1/opspilot/skill/123/ -> ('opspilot', 'skill')
            /api/v1/system_mgmt/user/ -> ('system_mgmt', 'user')
        """
        match = self.API_PATH_PATTERN.match(path)
        if match:
            app = match.group(1)
            module = match.group(2)
            return app, module
        return None, None

    def _get_username(self, request):
        """
        获取用户名

        Args:
            request: Django request 对象

        Returns:
            str: 用户名，未认证返回 'anonymous'
        """
        if hasattr(request, "user") and request.user.is_authenticated:
            return request.user.username
        return "anonymous"

    def _build_error_message(self, request, exception):
        """
        构建错误信息

        Args:
            request: Django request 对象
            exception: 异常对象

        Returns:
            str: 格式化的错误信息
        """
        error_type = type(exception).__name__
        error_msg = str(exception)

        # 获取请求方法和完整路径
        method = request.method
        full_path = request.get_full_path()

        # 获取堆栈跟踪（只保留最后5层）
        tb_lines = traceback.format_tb(exception.__traceback__)
        stack_trace = "".join(tb_lines[-5:]) if tb_lines else ""

        # 组装错误信息
        message_parts = [
            f"[{method}] {full_path}",
            f"错误类型: {error_type}",
            f"错误信息: {error_msg}",
        ]

        # 添加堆栈跟踪（如果有）
        if stack_trace:
            message_parts.append(f"堆栈跟踪:\n{stack_trace}")

        return "\n".join(message_parts)
