"""字段级数据调和的纯判断。落库和配置服务都调用这里，不读图、不读库。"""

import json
from datetime import datetime, timedelta, timezone

COLLECT_SOURCES_ATTR = "_collect_sources"
MANUAL_SOURCE = "manual"
MEMBER_SCOPE = "member"
STALE_DAYS_SETTING = "cmdb_collect_source_stale_days"
DEFAULT_STALE_DAYS = 7

EXCLUDED_FIELDS = {
    "assos",
    "model_id",
    "organization",
    "collect_task",
    "auto_collect",
    "collect_time",
    "inst_name",
    "_id",
    "_labels",
    COLLECT_SOURCES_ATTR,
    "manual_fields",
    "_expected_collect_sources",
    "suppress_change_record",
}

OUTSIDE_CONFLICT = "已有资产属于其他采集任务，无法自动接管"
ORG_CONFLICT = "已有资产不在当前采集组织范围内，无法自动接管"


def is_empty_value(value) -> bool:
    return value is None or value == "" or value == []


def _as_task_id(value):
    if value in (None, ""):
        return ""
    return str(value)


def parse_sources(raw) -> dict:
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
    return {"fields": dict(fields), "seen": {str(key): value for key, value in seen.items()}}


def dump_sources(sources: dict) -> str:
    return json.dumps(sources, ensure_ascii=False, separators=(",", ":"))


def _parse_time(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _ensure_now(now):
    parsed = _parse_time(now) if not isinstance(now, datetime) else now
    if parsed is None:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _stale_days(stale_days) -> int:
    try:
        return int(stale_days)
    except (TypeError, ValueError):
        return DEFAULT_STALE_DAYS


def is_expired(timestamp, now, stale_days) -> bool:
    """超过 N 天才过期。N≤0 永不过期。没有时间戳且 N>0 视为已经过期。"""
    if _stale_days(stale_days) <= 0:
        return False
    parsed = _parse_time(timestamp)
    if parsed is None:
        return True
    return _ensure_now(now) - parsed > timedelta(days=_stale_days(stale_days))


def still_seen(timestamp, now, stale_days) -> bool:
    """有过记录且未过期。没记录不算看到。N≤0 时只要有记录就一直算看到。"""
    if _parse_time(timestamp) is None:
        return False
    return not is_expired(timestamp, now, stale_days)


def _rank(task_id, order) -> int | None:
    key = _as_task_id(task_id)
    normalized = [_as_task_id(item) for item in order or []]
    if key not in normalized:
        return None
    return normalized.index(key)


def decide_field_write(*, current, proposed, source, source_updated_at, task_id, order, now, stale_days) -> str:
    """返回 write 或 skip。调用方保证本轮结果里有这个字段。按规格表第一条成立的规则。"""
    if source not in (None, "", MANUAL_SOURCE) and _rank(source, order) is None:
        source = None
    else:
        source = _as_task_id(source) if source not in (None, "", MANUAL_SOURCE) else source or None
    task = _as_task_id(task_id)
    if source == MANUAL_SOURCE:
        return "skip"
    if source is None:
        return "write"
    if source == task:
        return "write"
    if is_empty_value(proposed) and not is_empty_value(current):
        return "skip"
    task_rank = _rank(task, order)
    source_rank = _rank(source, order)
    if task_rank is not None and source_rank is not None and task_rank < source_rank:
        return "write"
    if is_empty_value(current):
        return "write"
    if task_rank is not None and source_rank is not None and task_rank > source_rank and is_expired(source_updated_at, now, stale_days):
        return "write"
    return "skip"


def field_order_for(attr_id, field_orders, member_order):
    order = (field_orders or {}).get(attr_id)
    if order:
        return [_as_task_id(item) for item in order]
    return [_as_task_id(item) for item in member_order or []]


def _source_entry(sources, attr_id):
    entry = sources["fields"].get(attr_id)
    if not isinstance(entry, dict):
        return None, None
    return entry.get("source"), entry.get("updated_at")


def plan_create(incoming: dict, task_id: str, now) -> dict:
    task = _as_task_id(task_id)
    stamp = _ensure_now(now).isoformat()
    fields = {}
    for key, value in incoming.items():
        if key in EXCLUDED_FIELDS or str(key).startswith("_"):
            continue
        fields[key] = {"source": task, "updated_at": stamp}
    sources = {"fields": fields, "seen": {task: stamp}}
    return {"sources_json": dump_sources(sources), "collect_task": task}


def plan_collected_instance(
    *,
    old: dict,
    incoming: dict,
    task_id,
    member_order,
    field_orders,
    now,
    stale_days,
) -> dict:
    """主实例更新计划。conflict 为文案时不写。"""
    task = _as_task_id(task_id)
    members = [_as_task_id(item) for item in member_order or []]
    stamp = _ensure_now(now).isoformat()
    moment = _ensure_now(now)
    sources = parse_sources(old.get(COLLECT_SOURCES_ATTR))
    owner = _as_task_id(old.get("collect_task"))
    skipped = 0

    if owner and owner not in members:
        return {"conflict": OUTSIDE_CONFLICT, "skipped_fields": 0}
    if not _same_org(old.get("organization"), incoming.get("_task_organizations")):
        return {"conflict": ORG_CONFLICT, "skipped_fields": 0}

    properties = {}
    for key, proposed in incoming.items():
        if key in EXCLUDED_FIELDS or str(key).startswith("_"):
            continue
        order = field_order_for(key, field_orders, members)
        source, updated_at = _source_entry(sources, key)
        if source not in (None, "", MANUAL_SOURCE) and _rank(source, members) is None:
            source = None
        if source not in (None, "", MANUAL_SOURCE) and _rank(source, order) is None:
            source = None
        decision = decide_field_write(
            current=old.get(key),
            proposed=proposed,
            source=source,
            source_updated_at=updated_at,
            task_id=task,
            order=order,
            now=moment,
            stale_days=stale_days,
        )
        if decision == "skip":
            skipped += 1
            continue
        sources["fields"][key] = {"source": task, "updated_at": stamp}
        if old.get(key) != proposed:
            properties[key] = proposed

    ownership = _plan_ownership(
        owner=owner,
        task=task,
        members=members,
        seen=sources["seen"],
        owner_collect_time=old.get("collect_time"),
        now=moment,
        stale_days=stale_days,
    )
    sources["seen"][task] = stamp
    _prune_sources(sources, members, moment, stale_days)
    # 本轮看到的任务刚写入，剪枝不能把它清掉。
    sources["seen"][task] = stamp
    refresh_time = ownership in {"refresh", "transfer", "adopt"}
    return {
        "conflict": None,
        "properties": properties,
        "sources_json": dump_sources(sources),
        "collect_task": task if ownership in {"transfer", "adopt", "refresh"} else owner or task,
        "refresh_collect_time": refresh_time,
        "skipped_fields": skipped,
        "ownership": ownership,
        "suppress_change_record": not properties,
    }


def _same_org(organization, task_organizations) -> bool:
    if task_organizations is None:
        return True
    current = {str(value) for value in (organization or [])}
    allowed = {str(value) for value in task_organizations}
    if not current or not allowed:
        return False
    return bool(current & allowed)


def _plan_ownership(*, owner, task, members, seen, owner_collect_time, now, stale_days):
    if not owner:
        return "adopt"
    if owner == task:
        return "refresh"
    owner_rank = _rank(owner, members)
    task_rank = _rank(task, members)
    if owner_rank is None or task_rank is None:
        return "keep"
    if owner_rank > task_rank:
        return "transfer"
    owner_seen = seen.get(owner) or owner_collect_time
    if not is_expired(owner_seen, now, stale_days):
        return "keep"
    seers = [member for member in members if member == task or still_seen(seen.get(member), now, stale_days)]
    if seers and seers[0] == task:
        return "transfer"
    return "keep"


def _prune_sources(sources, members, now, stale_days):
    live = set(members)
    sources["fields"] = {
        key: value
        for key, value in sources["fields"].items()
        if not isinstance(value, dict) or value.get("source") in (None, "", MANUAL_SOURCE) or _as_task_id(value.get("source")) in live
    }
    sources["seen"] = {key: value for key, value in sources["seen"].items() if key in live and not is_expired(value, now, stale_days)}


def other_member_still_sees(owner, sources_raw, member_order, now, stale_days) -> bool:
    sources = parse_sources(sources_raw)
    owner_id = _as_task_id(owner)
    for member in [_as_task_id(item) for item in member_order or []]:
        if member == owner_id:
            continue
        if still_seen(sources["seen"].get(member), now, stale_days):
            return True
    return False


def stamp_manual_sources(existing: dict, updates: dict, now=None) -> str | None:
    """值确实变化的字段记为 manual。没有变化时返回 None。"""
    stamp = _ensure_now(now).isoformat()
    sources = parse_sources((existing or {}).get(COLLECT_SOURCES_ATTR))
    changed = False
    for key, value in (updates or {}).items():
        if key in EXCLUDED_FIELDS or str(key).startswith("_"):
            continue
        if (existing or {}).get(key) != value:
            sources["fields"][key] = {"source": MANUAL_SOURCE, "updated_at": stamp}
            changed = True
    if not changed:
        return None
    return dump_sources(sources)


def clear_manual_fields(existing: dict, fields) -> str:
    sources = parse_sources((existing or {}).get(COLLECT_SOURCES_ATTR))
    targets = (
        list(fields)
        if fields
        else [key for key, entry in sources["fields"].items() if isinstance(entry, dict) and entry.get("source") == MANUAL_SOURCE]
    )
    for key in targets:
        entry = sources["fields"].get(key)
        if isinstance(entry, dict) and entry.get("source") == MANUAL_SOURCE:
            sources["fields"].pop(key, None)
    return dump_sources(sources)


def manual_field_ids(instance: dict) -> list[str]:
    sources = parse_sources((instance or {}).get(COLLECT_SOURCES_ATTR))
    return sorted(key for key, entry in sources["fields"].items() if isinstance(entry, dict) and entry.get("source") == MANUAL_SOURCE)


def hide_collect_sources(data):
    if not isinstance(data, dict) or COLLECT_SOURCES_ATTR not in data:
        return data
    copied = dict(data)
    copied.pop(COLLECT_SOURCES_ATTR, None)
    return copied
