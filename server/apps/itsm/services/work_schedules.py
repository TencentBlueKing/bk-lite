from datetime import date, datetime

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from apps.itsm.models import ItsmSetting
from apps.itsm.models.extend import ChangeWindow, DutyShift
from apps.system_mgmt.models import User


class WorkScheduleError(ValueError):
    pass


def _validated_name(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 128:
        raise WorkScheduleError("名称须为 1 至 128 个字符")
    return name.strip()


def _window_time(value):
    try:
        parsed = parse_datetime(value) if isinstance(value, str) else value
    except ValueError:
        parsed = None
    if not isinstance(parsed, datetime) or not is_aware(parsed):
        raise WorkScheduleError("请选择开始和结束时间，时间须包含时区")
    return parsed


@transaction.atomic
def mutate_change_window(domain, username, values, *, item_id=None, delete=False):
    ItsmSetting.objects.select_for_update().get_or_create(domain=domain, key="change_window_write_lock")
    windows = ChangeWindow.objects.filter(domain=domain)
    item = windows.get(id=item_id) if item_id is not None else ChangeWindow(domain=domain, created_by=username)
    if delete:
        item.delete()
        return None
    name = _validated_name(values.get("name", item.name))
    start_at = _window_time(values.get("start_at", item.start_at))
    end_at = _window_time(values.get("end_at", item.end_at))
    if end_at <= start_at:
        raise WorkScheduleError("结束时间须晚于开始时间")
    if windows.exclude(pk=item.pk).filter(start_at__lt=end_at, end_at__gt=start_at).exists():
        raise WorkScheduleError("变更窗口冲突")
    item.name, item.start_at, item.end_at = name, start_at, end_at
    item.updated_by = username
    item.save()
    return item


@transaction.atomic
def save_duty_shift(domain, username, values, *, item_id=None):
    shifts = DutyShift.objects.filter(domain=domain)
    item = shifts.select_for_update().get(id=item_id) if item_id is not None else DutyShift(domain=domain, created_by=username)
    name = _validated_name(values.get("name", item.name))
    day = values.get("day", item.day)
    try:
        day = date.fromisoformat(day) if isinstance(day, str) else day
    except ValueError:
        day = None
    if not isinstance(day, date):
        raise WorkScheduleError("请选择有效的值班日期")
    members = values.get("members", item.members)
    if not isinstance(members, list) or not members or any(not isinstance(member, str) or not member.strip() for member in members):
        raise WorkScheduleError("请至少选择一名值班人员")
    members = list(dict.fromkeys(member.strip() for member in members))
    users = User.objects.filter(domain=domain, username__in=members, disabled=False).values_list("username", flat=True)
    if set(members) != set(users):
        raise WorkScheduleError("请选择本组织内启用的值班人员")
    item.name, item.day, item.members = name, day, members
    item.updated_by = username
    item.save()
    return item
