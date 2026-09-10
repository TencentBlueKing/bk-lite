def collect_prefetched_group_role_ids(groups):
    """从已 prefetch roles 的组迭代器收集去重后的角色 ID。

    调用方须先 prefetch_related("roles")。本函数只消费预取缓存，不自行查询。
    """
    role_ids = set()
    for group in groups:
        role_ids.update(role.id for role in group.roles.all())
    return role_ids
