"""
操作日志工具函数
"""
from apps.system_mgmt.models.operation_log import OperationLog
from apps.system_mgmt.utils.login_log_utils import get_client_ip


def log_operation(request, action_type, app, summary):
    """
    记录操作日志

    Args:
        request: Django request 对象
        action_type: 操作类型 (create/update/delete/execute)
        app: 应用模块名称
        summary: 操作概要描述

    Returns:
        OperationLog 实例
    """
    try:
        operation_log = OperationLog.objects.create(
            username=request.user.username,
            source_ip=get_client_ip(request),
            app=app,
            action_type=action_type,
            summary=summary,
            domain=getattr(request.user, "domain", "domain.com"),
        )
        return operation_log
    except Exception as e:
        # 记录日志失败不应影响主业务流程
        from apps.core.logger import system_mgmt_logger as logger

        logger.error(f"记录操作日志失败: {str(e)}")
        return None
