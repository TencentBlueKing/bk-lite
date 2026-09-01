from django.db.models import Q

from apps.core.utils.user_group import normalize_user_group_ids

SPECIAL_VIRTUAL_GROUP_NAMES = frozenset({"OpsPilotGuest", "虚拟团队", "虚拟组织"})


def authorized_virtual_organization_ids(user) -> set[int]:
    """用户有权限的虚拟组织 ID。

    虚拟团队 / OpsPilotGuest 的资产在任意 current_team 下都应可见，对齐监控、
    节点、日志通过 guest 组并入查询范围的行为。
    """
    from apps.system_mgmt.utils.group_utils import GroupUtils

    named_ids = _named_virtual_organization_ids(getattr(user, "group_list", []))
    query = Q(is_virtual=True) | Q(name__in=SPECIAL_VIRTUAL_GROUP_NAMES, parent_id=0)
    if getattr(user, "is_superuser", False):
        return named_ids | set(GroupUtils.active_queryset().filter(query).values_list("id", flat=True))

    authorized_ids = set(normalize_user_group_ids(getattr(user, "group_list", [])))
    if not authorized_ids:
        return named_ids
    return named_ids | set(
        GroupUtils.active_queryset(id__in=authorized_ids).filter(query).values_list("id", flat=True)
    )


def _named_virtual_organization_ids(group_list) -> set[int]:
    organization_ids = set()
    for group in group_list or []:
        if not isinstance(group, dict):
            continue
        if group.get("name") not in SPECIAL_VIRTUAL_GROUP_NAMES:
            continue
        try:
            organization_ids.add(int(group["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return organization_ids
