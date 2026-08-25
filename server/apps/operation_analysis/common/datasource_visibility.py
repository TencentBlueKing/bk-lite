from django.db.models import Q


def is_empty_groups(groups) -> bool:
    return not bool(groups)


def is_builtin_globally_visible(instance) -> bool:
    return bool(getattr(instance, "is_build_in", False)) and is_empty_groups(getattr(instance, "groups", None))


def can_access_datasource_in_org(instance, current_team) -> bool:
    if is_builtin_globally_visible(instance):
        return True
    groups = getattr(instance, "groups", None) or []
    return current_team in groups


def builtin_global_visibility_q() -> Q:
    return Q(is_build_in=True) & (Q(groups=[]) | Q(groups__isnull=True))


def expand_datasource_org_query(membership_query: Q, *, include_all_builtins: bool) -> Q:
    if include_all_builtins:
        return membership_query | Q(is_build_in=True)
    return membership_query | builtin_global_visibility_q()
