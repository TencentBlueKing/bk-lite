"""OpsPilot usage statistics query and aggregation logic.

The HTTP views keep authentication decorators and response conversion. This
module owns the ORM queries and data shaping so statistics changes do not
share a file with chat execution and channel callbacks.
"""

import datetime
from collections.abc import Callable
from typing import Any

from django.db.models import Count, IntegerField, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, NullIf, TruncDate

from apps.opspilot.models import Bot, BotConversationHistory, LLMSkill, SkillRequestLog
from apps.opspilot.utils.bot_utils import set_time_range


def extract_token_usage(response_detail: Any) -> tuple[int, int, int]:  # pragma: no cover
    """Return OpenAI-style input, output and total token counts."""
    if not isinstance(response_detail, dict):
        return 0, 0, 0
    usage = response_detail.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, 0

    def _to_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _to_int(usage.get("prompt_tokens"))
    completion = _to_int(usage.get("completion_tokens"))
    total = _to_int(usage.get("total_tokens")) or (prompt + completion)
    return prompt, completion, total  # pragma: no cover


def user_team_ids(request) -> set[int]:
    """Return accessible team IDs; an empty set means unrestricted superuser."""
    if getattr(request.user, "is_superuser", False):
        return set()  # pragma: no cover
    return {group["id"] for group in getattr(request.user, "group_list", []) if isinstance(group, dict) and "id" in group}  # pragma: no cover


def bot_in_user_team(request, bot_id, *, team_ids_getter: Callable = user_team_ids) -> bool:
    """Return whether the requested bot is visible to the caller."""
    bot = Bot.objects.filter(id=bot_id).first()
    if not bot:
        return False
    if getattr(request.user, "is_superuser", False):  # pragma: no cover
        return True
    return bool(set(bot.team or []) & team_ids_getter(request))  # pragma: no cover


def token_consumption_queryset(
    request,
    *,
    bot_scope_check: Callable = bot_in_user_team,
    time_range_getter: Callable = set_time_range,
):  # pragma: no cover
    """Build the scoped token-consumption queryset and requested time range."""
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = time_range_getter(end_time_str, start_time_str)
    queryset = SkillRequestLog.objects.filter(created_at__range=[start_time, end_time], state=True)
    bot_id = request.GET.get("bot_id")
    if bot_id:
        if not bot_scope_check(request, bot_id):
            return queryset.none(), start_time, end_time
        skill_ids = LLMSkill.objects.filter(bot__id=bot_id).values_list("id", flat=True)
        queryset = queryset.filter(skill_id__in=skill_ids)
    return queryset, start_time, end_time


def annotate_token_fields(queryset):
    """Annotate token values from ``response_detail`` for DB aggregation."""

    def _int_field(path):
        return Coalesce(
            Cast(
                KeyTextTransform(path[1], KeyTextTransform(path[0], "response_detail")),
                IntegerField(),
            ),
            0,
        )

    prompt_expr = _int_field(("usage", "prompt_tokens"))
    completion_expr = _int_field(("usage", "completion_tokens"))
    total_expr = _int_field(("usage", "total_tokens"))
    return queryset.annotate(
        _prompt=prompt_expr,
        _completion=completion_expr,
        _total=Coalesce(
            NullIf(total_expr, Value(0)),
            prompt_expr + completion_expr,
            Value(0),
            output_field=IntegerField(),
        ),
    )


def aggregate_token_totals(queryset, *, annotate: Callable = annotate_token_fields) -> dict[str, int]:
    """Aggregate total, input and output token counts in the database."""
    result = annotate(queryset).aggregate(
        input_tokens=Sum("_prompt"),
        output_tokens=Sum("_completion"),
        total_tokens=Sum("_total"),
    )
    return {
        "total_tokens": result["total_tokens"] or 0,
        "input_tokens": result["input_tokens"] or 0,
        "output_tokens": result["output_tokens"] or 0,
    }


def token_consumption_overview(
    queryset,
    start_time,
    end_time,
    *,
    annotate: Callable = annotate_token_fields,
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate daily token totals while retaining zero-value date buckets."""
    num_days = (end_time - start_time).days + 1
    daily_totals = {(start_time + datetime.timedelta(days=index)).strftime("%Y-%m-%d"): 0 for index in range(num_days)}
    rows = annotate(queryset).annotate(date=TruncDate("created_at")).values("date").annotate(tokens=Sum("_total")).order_by("date")
    for row in rows:
        date_key = row["date"].strftime("%Y-%m-%d")
        daily_totals[date_key] = (daily_totals.get(date_key) or 0) + (row["tokens"] or 0)
    return {"items": [{"date": date, "tokens": tokens} for date, tokens in sorted(daily_totals.items())]}


def conversation_line_data(
    request,
    *,
    role: str,
    distinct_users: bool,
    bot_scope_check: Callable = bot_in_user_team,
    line_formatter: Callable,
    time_range_getter: Callable = set_time_range,
):
    """Build the per-channel conversation or active-user time series."""
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = time_range_getter(end_time_str, start_time_str)
    bot_id = request.GET.get("bot_id")
    if bot_id and not bot_scope_check(request, bot_id):
        return line_formatter(end_time, [], start_time)

    count = Count("channel_user", distinct=True) if distinct_users else Count("id")
    queryset = (
        BotConversationHistory.objects.filter(
            created_at__range=[start_time, end_time],
            bot_id=bot_id,
            conversation_role=role,
        )
        .annotate(date=TruncDate("created_at"))
        .values("channel_user__channel_type", "date")
        .annotate(count=count)
    )
    return line_formatter(end_time, queryset, start_time)


def format_channel_type_line(end_time, queryset, start_time):  # pragma: no cover
    """Format per-channel rows into the existing chart response structure."""
    num_days = (end_time - start_time).days + 1
    all_dates = [start_time + datetime.timedelta(days=index) for index in range(num_days)]
    formatted_dates = {date.strftime("%Y-%m-%d"): 0 for date in all_dates}
    known_channel_types = [
        "web",
        "ding_talk",
        "enterprise_wechat",
        "wechat_official_account",
    ]
    result_dict = {channel_type: formatted_dates.copy() for channel_type in known_channel_types}
    total_user_count = formatted_dates.copy()
    for entry in queryset:
        channel_type = entry["channel_user__channel_type"]
        date = entry["date"].strftime("%Y-%m-%d")
        user_count = entry["count"]
        if channel_type not in result_dict:
            result_dict[channel_type] = formatted_dates.copy()
        result_dict[channel_type][date] = user_count
        total_user_count[date] += user_count
    result = {
        channel_type: [{"time": date, "count": user_count} for date, user_count in sorted(date_dict.items())]
        for channel_type, date_dict in result_dict.items()
    }
    result["total"] = [{"time": date, "count": user_count} for date, user_count in sorted(total_user_count.items())]
    return result
