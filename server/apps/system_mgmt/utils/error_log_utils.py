"""
错误日志记录工具

提供统一的错误日志记录接口
"""
from typing import Optional

from apps.system_mgmt.models import ErrorLog


def log_error(
    username: str,
    app: str,
    module: str,
    error_message: str,
    domain: str = "domain.com",
) -> Optional[ErrorLog]:
    """
    记录错误日志

    Args:
        username: 触发错误的用户名
        app: 应用模块（如 monitor, cmdb, opspilot 等）
        module: 具体功能模块（如 viewset名称或功能路径）
        error_message: 详细的错误描述
        domain: 域名，默认为 domain.com

    Returns:
        创建的错误日志对象，失败返回 None

    Examples:
        >>> log_error(
        ...     username="admin",
        ...     app="monitor",
        ...     module="AlertViewSet.create",
        ...     error_message="创建告警规则失败: 缺少必填字段 'name'"
        ... )

        >>> log_error(
        ...     username="user001",
        ...     app="opspilot",
        ...     module="SkillViewSet.execute",
        ...     error_message="执行技能失败: 模型连接超时"
        ... )
    """
    try:
        error_log = ErrorLog.objects.create(
            username=username,
            app=app,
            module=module,
            error_message=error_message,
            domain=domain,
        )
        return error_log
    except Exception as e:
        # 记录错误日志失败时，不应影响主流程，仅打印日志
        from apps.core.logger import system_mgmt_logger

        system_mgmt_logger.error(f"Failed to create error log: {str(e)}")
        return None


def log_error_from_exception(
    username: str,
    app: str,
    module: str,
    exception: Exception,
    context: Optional[str] = None,
    domain: str = "domain.com",
) -> Optional[ErrorLog]:
    """
    从异常对象记录错误日志

    Args:
        username: 触发错误的用户名
        app: 应用模块
        module: 具体功能模块
        exception: 异常对象
        context: 额外的上下文信息
        domain: 域名

    Returns:
        创建的错误日志对象，失败返回 None

    Examples:
        >>> try:
        ...     # some operation
        ...     raise ValueError("Invalid input")
        ... except Exception as e:
        ...     log_error_from_exception(
        ...         username="admin",
        ...         app="cmdb",
        ...         module="HostViewSet.update",
        ...         exception=e,
        ...         context="host_id=123, field=ip_address"
        ...     )
    """
    error_type = type(exception).__name__
    error_msg = str(exception)

    # 组装完整的错误信息
    full_message = f"{error_type}: {error_msg}"
    if context:
        full_message = f"{full_message} | Context: {context}"

    return log_error(
        username=username,
        app=app,
        module=module,
        error_message=full_message,
        domain=domain,
    )
