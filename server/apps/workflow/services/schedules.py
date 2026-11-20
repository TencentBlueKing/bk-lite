from __future__ import annotations

import copy
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.core.utils.viewset_utils import user_group_id_set
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.workflow.services.definitions import DefinitionValidationError

FREQUENCIES = {"daily", "weekly", "monthly", "crontab"}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def resolve_user_timezone(user) -> str:
    """Return the authenticated user's active IANA timezone, with platform fallback."""
    candidates = (getattr(user, "timezone", None), timezone.get_current_timezone_name())
    for candidate in candidates:
        name = str(candidate or "").strip()
        if not name:
            continue
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, KeyError, ValueError):
            continue
        return name
    return "Asia/Shanghai"


def _time_values(config: dict) -> list[str]:
    values = config.get("time")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise DefinitionValidationError("time 必须包含 1 到 10 个执行时间")
    normalized = []
    for value in values:
        text = str(value or "").strip()
        if not TIME_PATTERN.fullmatch(text):
            raise DefinitionValidationError("time 必须使用 HH:MM 的 24 小时格式")
        if text not in normalized:
            normalized.append(text)
    return normalized


def _integer_values(config: dict, key: str, *, minimum: int, maximum: int) -> list[int]:
    values = config.get(key)
    if not isinstance(values, list) or not values:
        raise DefinitionValidationError(f"{key} 必须至少选择一项")
    if len(values) > maximum - minimum + 1:
        raise DefinitionValidationError(f"{key} 选择项过多")
    normalized = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise DefinitionValidationError(f"{key} 必须是 {minimum} 到 {maximum} 的整数")
        if value not in normalized:
            normalized.append(value)
    return sorted(normalized)


def compile_schedule_config(config: dict, *, timezone_name: str | None = None) -> dict:
    """Validate a user-facing schedule and compile it into runtime cron expressions."""
    if not isinstance(config, dict):
        raise DefinitionValidationError("定时触发 config 必须是 JSON 对象")
    frequency = str(config.get("frequency") or "").strip().lower()
    if not frequency and (config.get("crontab_expression") or config.get("expression")):
        frequency = "crontab"
    if frequency not in FREQUENCIES:
        raise DefinitionValidationError("frequency 必须是 daily、weekly、monthly 或 crontab")

    normalized: dict = {"frequency": frequency}
    if "execution_team_id" in config:
        team_id = config["execution_team_id"]
        if type(team_id) is not int or not 0 < team_id <= 2**63 - 1:
            raise DefinitionValidationError("定时执行组织必须是单个有效组织")
        normalized["execution_team_id"] = team_id
    expressions: list[str]
    if frequency == "crontab":
        expression = str(config.get("crontab_expression") or config.get("expression") or "").strip()
        if not croniter.is_valid(expression) or len(expression.split()) != 5:
            raise DefinitionValidationError("Cron 表达式非法，必须包含 5 个字段")
        normalized["crontab_expression"] = expression
        expressions = [expression]
    else:
        times = _time_values(config)
        normalized["time"] = times
        day_of_week = "*"
        day_of_month = "*"
        if frequency == "weekly":
            weekdays = _integer_values(config, "weekdays", minimum=0, maximum=6)
            normalized["weekdays"] = weekdays
            day_of_week = ",".join(str(value) for value in weekdays)
        elif frequency == "monthly":
            days = _integer_values(config, "days", minimum=1, maximum=31)
            normalized["days"] = days
            day_of_month = ",".join(str(value) for value in days)
        expressions = []
        for value in times:
            hour, minute = value.split(":")
            expressions.append(f"{int(minute)} {int(hour)} {day_of_month} * {day_of_week}")

    normalized["expressions"] = expressions
    normalized["expression"] = expressions[0]
    if timezone_name is not None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, KeyError, ValueError) as error:
            raise DefinitionValidationError("Cron 时区非法") from error
        normalized["timezone"] = timezone_name
    return normalized


def next_schedule_runs(config: dict, *, count: int = 6, after: datetime | None = None) -> list[datetime]:
    compiled = compile_schedule_config(
        config,
        timezone_name=str(config.get("timezone") or timezone.get_current_timezone_name()),
    )
    zone = ZoneInfo(compiled["timezone"])
    base = (after or timezone.now()).astimezone(zone)
    candidates = []
    for expression in compiled["expressions"]:
        iterator = croniter(expression, base)
        candidates.extend(iterator.get_next(datetime) for _ in range(count))
    return sorted(set(candidates))[:count]


def build_schedule_preview(config: dict, *, timezone_name: str, count: int = 6) -> dict:
    compiled = compile_schedule_config(config, timezone_name=timezone_name)
    now = timezone.now().astimezone(ZoneInfo(timezone_name))
    next_runs = next_schedule_runs(compiled, count=count, after=now)
    serialized_runs = [item.isoformat() for item in next_runs]
    return {
        "config": compiled,
        "expressions": compiled["expressions"],
        "timezone": timezone_name,
        "next_runs": serialized_runs,
        "test_output": build_schedule_event(
            compiled,
            scheduled_at=next_runs[0],
            triggered_at=now,
            test=True,
        ),
    }


def build_schedule_event(
    config: dict,
    *,
    scheduled_at: datetime,
    triggered_at: datetime | None = None,
    test: bool = False,
) -> dict:
    compiled = compile_schedule_config(
        config,
        timezone_name=str(config.get("timezone") or timezone.get_current_timezone_name()),
    )
    zone = ZoneInfo(compiled["timezone"])
    return {
        "triggered_at": (triggered_at or timezone.now()).astimezone(zone).isoformat(),
        "scheduled_at": scheduled_at.astimezone(zone).isoformat(),
        "timezone": compiled["timezone"],
        "schedule": compiled["expressions"],
        "test": test,
    }


def schedule_execution_identity(config: dict, *, user, current_team: int) -> dict:
    """Bind a validated schedule selection to the user operating the designer."""
    team_id = config.get("execution_team_id", current_team)
    bound_team = getattr(user, "_api_secret_team", None)
    if (
        (bound_team is not None and team_id != bound_team)
        or (not user.is_superuser and team_id not in user_group_id_set(user))
        or not GroupUtils.active_queryset(id=team_id).exists()
    ):
        raise PermissionDenied("定时执行组织不在当前用户的可用组织内")
    if not user.username or len(user.username) > 32 or not user.domain:
        raise DefinitionValidationError("流程执行身份非法")
    return {"username": user.username, "domain": user.domain, "team_id": team_id, "include_children": False}


def bind_published_schedules(canvas_metadata: dict, *, user, current_team: int) -> dict:
    """Freeze the selected active team and display the authenticated publisher on each schedule."""
    metadata = copy.deepcopy(canvas_metadata)
    for node in metadata.get("trigger_nodes") or []:
        if node.get("trigger_type") != "SCHEDULE":
            continue
        config = compile_schedule_config(node.get("config") or {}, timezone_name=resolve_user_timezone(user))
        identity = schedule_execution_identity(config, user=user, current_team=current_team)
        node["config"] = {**config, "execution_team_id": identity["team_id"], "execution_username": identity["username"]}
    return metadata
