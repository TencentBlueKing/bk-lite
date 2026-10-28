"""操作日志与登录日志 Excel 导出的行数上限。

上限写死为 EXPORT_MAX_ROWS。超过上限返回 400，不截断。
"""

from rest_framework.response import Response

from apps.system_mgmt.utils.i18n import system_mgmt_request_message

EXPORT_MAX_ROWS = 10000


def export_limit_rejection(request, queryset):
    """行数超过 EXPORT_MAX_ROWS 时返回 400；未超过时返回 None，调用方继续生成工作簿。"""
    limit = EXPORT_MAX_ROWS
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
