from django.http import JsonResponse

from apps.core.decorators.api_permission import HasRole
from apps.opspilot.services import usage_statistics_service
from apps.opspilot.utils.bot_utils import set_time_range

_extract_token_usage = usage_statistics_service.extract_token_usage
_user_team_ids = usage_statistics_service.user_team_ids
_annotate_token_fields = usage_statistics_service.annotate_token_fields
set_channel_type_line = usage_statistics_service.format_channel_type_line


def _bot_in_user_team(request, bot_id) -> bool:
    """兼容旧导入/patch 点，团队作用域逻辑由统计 service 承载。"""
    return usage_statistics_service.bot_in_user_team(
        request,
        bot_id,
        team_ids_getter=_user_team_ids,
    )


def _token_consumption_queryset(request):  # pragma: no cover
    """兼容旧 patch 点，查询构造由统计 service 承载。"""
    return usage_statistics_service.token_consumption_queryset(
        request,
        bot_scope_check=_bot_in_user_team,
        time_range_getter=set_time_range,
    )


@HasRole("admin")
def get_total_token_consumption(request):  # pragma: no cover
    queryset, _start_time, _end_time = _token_consumption_queryset(request)
    data = usage_statistics_service.aggregate_token_totals(
        queryset,
        annotate=_annotate_token_fields,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_token_consumption_overview(request):  # pragma: no cover
    queryset, start_time, end_time = _token_consumption_queryset(request)
    data = usage_statistics_service.token_consumption_overview(
        queryset,
        start_time,
        end_time,
        annotate=_annotate_token_fields,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_conversations_line_data(request):  # pragma: no cover
    data = usage_statistics_service.conversation_line_data(
        request,
        role="bot",
        distinct_users=False,
        bot_scope_check=_bot_in_user_team,
        line_formatter=set_channel_type_line,
        time_range_getter=set_time_range,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_active_users_line_data(request):  # pragma: no cover
    data = usage_statistics_service.conversation_line_data(
        request,
        role="user",
        distinct_users=True,
        bot_scope_check=_bot_in_user_team,
        line_formatter=set_channel_type_line,
        time_range_getter=set_time_range,
    )
    return JsonResponse({"result": True, "data": data})
