"""Organization scope rules for credential ownership."""

from __future__ import annotations

from collections.abc import Iterable

from apps.system_mgmt.utils.group_utils import GroupUtils


def _coerce_group_id(value) -> int | None:
    if isinstance(value, (bool, float)):
        return None
    try:
        group_id = int(value)
    except (TypeError, ValueError):
        return None
    return group_id if group_id > 0 else None


def _normalize_group_ids(group_list: Iterable | None) -> frozenset[int]:
    if group_list is None or isinstance(group_list, (str, bytes, dict)):
        group_list = (group_list,)
    group_ids: set[int] = set()
    for group in group_list or ():
        value = group.get("id") if isinstance(group, dict) else group
        group_id = _coerce_group_id(value)
        if group_id is not None:
            group_ids.add(group_id)
    return frozenset(group_ids)


def is_current_team_authorized(current_team, group_list, is_superuser) -> bool:
    """Return whether an active current organization is authorized for the actor."""
    current_id = _coerce_group_id(current_team)
    if current_id is None:
        return False
    if not GroupUtils.active_queryset(id=current_id).exists():
        return False
    if is_superuser:
        return True
    return current_id in _normalize_group_ids(group_list)


def usable_owner_group_ids(current_team: int) -> frozenset[int]:
    """Return current and active ancestors visible to a credential reader."""
    current_id = _coerce_group_id(current_team)
    if current_id is None:
        return frozenset()

    parent_by_id = dict(GroupUtils.active_queryset().values_list("id", "parent_id"))
    if current_id not in parent_by_id:
        return frozenset()

    result: set[int] = set()
    group_id = current_id
    while group_id in parent_by_id and group_id not in result:
        result.add(group_id)
        parent_id = parent_by_id[group_id]
        if not parent_id or parent_id not in parent_by_id:
            break
        group_id = parent_id
    return frozenset(result)


def manageable_owner_group_ids(current_team, group_list, is_superuser) -> frozenset[int]:
    """Return active organizations the actor may assign and manage in the vault."""
    if not is_current_team_authorized(current_team, group_list, is_superuser):
        return frozenset()
    if is_superuser:
        return frozenset(GroupUtils.active_queryset().values_list("id", flat=True))
    authorized_ids = _normalize_group_ids(group_list)
    if not authorized_ids:
        return frozenset()
    return frozenset(GroupUtils.active_queryset(id__in=authorized_ids).values_list("id", flat=True))
