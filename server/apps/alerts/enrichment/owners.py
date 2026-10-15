"""把 CMDB 用户字段转换成事件责任人。丰富到才替换上报值。"""

MAX_OWNER_FIELDS = 5
MAX_OWNER_USERNAMES = 20
MAX_OWNER_RULE_IDS = 20

_FAILURE_STATUSES = {
    "provider_failed",
    "circuit_open",
    "budget_exhausted",
    "provider_saturated",
}


def owner_fields_of(rule) -> list[str]:
    config = getattr(rule, "provider_config", None) or {}
    raw = config.get("owner_fields") if isinstance(config, dict) else None
    if not isinstance(raw, list):
        return []
    fields = []
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in fields:
            continue
        fields.append(name)
        if len(fields) >= MAX_OWNER_FIELDS:
            break
    return fields


def user_ids_from_records(records, owner_fields, on_multiple) -> list[int]:
    if not records or not owner_fields:
        return []
    selected = records[:1] if on_multiple == "first" else list(records)
    found = []
    seen = set()
    for record in selected:
        if not isinstance(record, dict):
            continue
        for field in owner_fields:
            raw = record.get(field)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                if isinstance(value, bool) or not isinstance(value, int):
                    continue
                if value in seen:
                    continue
                seen.add(value)
                found.append(value)
    return found


def remember_owner_ids(sink, rule, records, status, events) -> None:
    fields = owner_fields_of(rule)
    if not fields or status in _FAILURE_STATUSES:
        return
    user_ids = user_ids_from_records(records, fields, getattr(rule, "on_multiple", "first"))
    if not user_ids:
        return
    rule_id = getattr(rule, "id", None)
    for event in events:
        sink.setdefault(id(event), []).append((rule_id, user_ids))


def resolve_active_usernames(user_ids) -> dict[int, str]:
    if not user_ids:
        return {}
    from apps.system_mgmt.models import User

    rows = User.objects.filter(id__in=list(user_ids), disabled=False).values_list("id", "username")
    return {user_id: username for user_id, username in rows if isinstance(username, str) and username.strip()}


def apply_enriched_owners(events, sink) -> None:
    """非空丰富结果替换 assignee；否则保留上报值。"""
    wanted = []
    seen = set()
    for contributions in sink.values():
        for _rule_id, user_ids in contributions:
            for user_id in user_ids:
                if user_id not in seen:
                    seen.add(user_id)
                    wanted.append(user_id)
    names_by_id = resolve_active_usernames(wanted)

    for event in events:
        contributions = sink.get(id(event), [])
        usernames = []
        rule_ids = []
        for rule_id, user_ids in contributions:
            resolved = [names_by_id[user_id] for user_id in user_ids if user_id in names_by_id]
            if not resolved:
                continue
            if rule_id is not None and rule_id not in rule_ids and len(rule_ids) < MAX_OWNER_RULE_IDS:
                rule_ids.append(rule_id)
            for username in resolved:
                if username not in usernames and len(usernames) < MAX_OWNER_USERNAMES:
                    usernames.append(username)

        meta = event.setdefault("enrichment_meta", {"schema_version": 1, "status": "skipped", "reasons": []})
        if usernames:
            event["assignee"] = usernames
            meta["owner_source"] = {"kind": "enrichment", "rule_ids": rule_ids}
            continue
        reported = event.get("assignee") or []
        has_reported = any(isinstance(item, str) and item.strip() for item in reported)
        meta["owner_source"] = {"kind": "reported" if has_reported else "none"}
