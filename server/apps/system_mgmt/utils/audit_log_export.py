"""操作日志与登录日志 Excel 导出的行数上限。

默认 10000。运行时读取 Django settings.AUDIT_LOG_EXPORT_MAX_ROWS
（由环境变量 AUDIT_LOG_EXPORT_MAX_ROWS 注入）。超过上限返回 400，不截断。
"""

from rest_framework.response import Response

from apps.system_mgmt.utils.i18n import system_mgmt_request_message

EXPORT_MAX_ROWS = 10000


def configured_export_max_rows():
    """返回当前生效的导出行数上限。非法或非正数回退 EXPORT_MAX_ROWS。"""
    from django.conf import settings

    raw = getattr(settings, "AUDIT_LOG_EXPORT_MAX_ROWS", EXPORT_MAX_ROWS)
    if raw is None or raw == "":
        return EXPORT_MAX_ROWS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return EXPORT_MAX_ROWS
    if value < 1:
        return EXPORT_MAX_ROWS
    return value


def export_limit_rejection(request, queryset):
    """行数超过上限时返回 400；未超过时返回 None，调用方继续生成工作簿。"""
    limit = configured_export_max_rows()
    count = queryset.count()
    if count <= limit:
        return None
    message = system_mgmt_request_message(
        request,
        "export.too_many_rows",
        limit=limit,
        count=count,
    )
    return Response({"result": False, "message": message}, status=400)
