"""
用户登录日志工具函数

提供登录日志记录功能
"""
import logging

from apps.system_mgmt.models import UserLoginLog

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    从请求中获取客户端IP地址

    优先从 X-Forwarded-For 或 X-Real-IP 头获取，如果没有则从 REMOTE_ADDR 获取
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "0.0.0.0")
    return ip


def get_user_agent(request):
    """从请求中获取 User-Agent"""
    return request.META.get("HTTP_USER_AGENT", "")[:500]


def log_user_login(
    username,
    source_ip,
    status,
    domain="domain.com",
    failure_reason="",
    user_agent="",
):
    """
    记录用户登录日志

    参数:
        username: 用户名
        source_ip: 源IP地址
        status: 登录状态 ('success' 或 'failed')
        domain: 域名，默认 'domain.com'
        failure_reason: 失败原因，仅在 status='failed' 时有意义
        user_agent: 用户代理字符串

    返回:
        UserLoginLog 实例，如果记录失败则返回 None
    """
    try:
        log_entry = UserLoginLog.objects.create(
            username=username,
            source_ip=source_ip,
            status=status,
            domain=domain,
            failure_reason=failure_reason if status == UserLoginLog.STATUS_FAILED else "",
            user_agent=user_agent,
        )
        logger.info(f"Login log recorded: username={username}, status={status}, " f"ip={source_ip}, domain={domain}")
        return log_entry
    except Exception as e:
        logger.error(f"Failed to record login log: {e}", exc_info=True)
        return None


def log_user_login_from_request(request, username, status, domain="domain.com", failure_reason=""):
    """
    从请求对象记录用户登录日志

    自动从请求中提取 IP 和 User-Agent

    参数:
        request: Django 请求对象
        username: 用户名
        status: 登录状态 ('success' 或 'failed')
        domain: 域名，默认 'domain.com'
        failure_reason: 失败原因

    返回:
        UserLoginLog 实例，如果记录失败则返回 None
    """
    source_ip = get_client_ip(request)
    user_agent = get_user_agent(request)

    return log_user_login(
        username=username,
        source_ip=source_ip,
        status=status,
        domain=domain,
        failure_reason=failure_reason,
        user_agent=user_agent,
    )
