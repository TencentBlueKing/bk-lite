import jwt
from django.conf import settings
from django.contrib import auth
from django.db import InterfaceError, OperationalError
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import LazyObject, empty

from apps.core.logger import logger, safe_exception_info, safe_log_value
from apps.core.utils.custom_error import DoesNotExist
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils


class AuthMiddleware(MiddlewareMixin):
    # 豁免路径常量
    EXEMPT_PATHS = [
        "/swagger/",
        "/admin/",
        "/accounts/",
    ]
    USER_NOT_FOUND_STATUS_CODE = 460

    def _get_loader(self, request=None) -> LanguageLoader:
        """获取基于用户locale的LanguageLoader"""
        # 错误文案只读取已加载的用户字段，不能触发 Session / 惰性用户查库。
        user = vars(request).get("user") if request is not None else None
        if isinstance(user, LazyObject):
            user = user._wrapped
        locale = vars(user).get("locale", "en") if user is not None and user is not empty else "en"
        return LanguageLoader(app="core", default_lang=locale)

    @staticmethod
    def _get_loader_message(loader: LanguageLoader, key: str, default: str) -> str:
        """获取国际化消息并确保返回字符串"""
        message = loader.get(key, default)
        return message if isinstance(message, str) else default

    def process_view(self, request, view, args, kwargs):
        """处理视图请求的认证逻辑"""
        try:
            # 检查豁免条件
            if self._is_exempt(request, view):
                return None

            # 执行Token认证
            return self._authenticate_token(request)
        except DoesNotExist:
            logger.warning("event=auth_user_missing path=%s", safe_log_value(request.path))
            loader = self._get_loader(request)
            return WebUtils.response_error(
                error_message=self._get_loader_message(loader, "error.user_does_not_exist", "User Does Not Exist"),
                status_code=self.USER_NOT_FOUND_STATUS_CODE,
            )
        except (OperationalError, InterfaceError) as e:
            return self._service_error(request, e, 503)
        except Exception as e:
            return self._service_error(request, e, 500)

    @staticmethod
    def _service_error(request, error, status_code):
        # 此边界独占 traceback；异常正文可能包含连接串，不直接返回或记录。
        logger.error(
            "event=auth_service_failed path=%s request_id=%s failed_stage=authentication error_type=%s",
            safe_log_value(request.path),
            safe_log_value(vars(request).get("request_id", "")),
            type(error).__name__,
            exc_info=safe_exception_info(error),
        )
        return WebUtils.response_error(error_message="Authentication service unavailable", status_code=status_code)

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

        # Render JWT：scope 白名单 + 实时创建者身份；不得走普通 verify_token / Session。
        if self._is_render_token_candidate(token):
            from apps.operation_analysis.services.render_scope_service import DashboardReportRenderScopeError, DashboardReportRenderScopeService

            try:
                render_claims = DashboardReportRenderScopeService.authorize_request(request, token)
                user = DashboardReportRenderScopeService.resolve_request_user(request, render_claims)
            except DashboardReportRenderScopeError:
                loader = self._get_loader(request)
                return WebUtils.response_401(loader.get("error.auth_failed", "Authentication failed"))
            if not user:
                loader = self._get_loader(request)
                return WebUtils.response_401(loader.get("error.please_provide_token", "Please provide Token"))
            request.user = user
            request.dashboard_report_render_scope = render_claims
            return None

        # 认证用户
        user = auth.authenticate(request=request, token=token)
        if not user:
            logger.warning("Token authentication failed for %s", safe_log_value(request.path))
            loader = self._get_loader(request)
            return WebUtils.response_401(loader.get("error.please_provide_token", "Please provide Token"))

        auth.login(request, user)
        if not request.session.session_key:
            request.session.cycle_key()
        return None

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

    @staticmethod
    def _is_render_token_candidate(token: str) -> bool:
        """只用于选择认证器；真实性仍由 Render Scope Service 完整校验。"""
        try:
            claims = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
        except Exception:
            return False
        return claims.get("token_type") == "dashboard_report_render" or "render_execution_id" in claims
