"""Memory 可见性规则。

整个记忆模块「当前用户能看到哪些 Memory」的单一来源。
MemorySpaceViewSet 序列化 memory_count、MemoryViewSet 列表过滤,
都应通过本模块计算,避免规则双份造成卡片数字与详情列表对不上。

helper 设计:
- ``get_visible_memories_qs(user)``:返回当前用户可见的所有 Memory。
  团队空间对任意用户全见;个人空间仅 owner_username+owner_domain 匹配当前用户。
- 配合外部 ``memory_space_id`` 过滤(DRF filterset_fields)使用,
  先 filter memory_space_id 再 ``&`` 上 helper 结果,保证个人记忆跨空间隔离。

为什么不直接 ``get_visible_memories_qs(user, *, memory_space_id)``:
- ViewSet 列表接口支持无 memory_space 查询,返回当前用户可见的所有 Memory;
  MemorySpaceSerializer.get_memory_count 是单空间 count。
- helper 必须支持两种语义:per-user 全量、per-user-per-space 限定。
- 选择 helper 始终返回 user 可见全集,与外部 queryset 自由组合,
  调用方按需决定是否先 filter memory_space_id。
"""

from django.db.models import Q, QuerySet

from apps.opspilot.models.memory_mgmt import Memory, MemorySpace


def _user_identity(user) -> tuple[str, str] | None:
    """返回 (username, domain);user 为 None 或缺 username 时返回 None。

    注:helper 不校验 ``is_authenticated`` —— 由调用方(view/serializer)负责;
    这样测试用 SimpleNamespace 模拟 user 时也能直接生效,避免过严校验
    把「视图中确实存在的 user」错当成未认证。
    """
    if user is None:
        return None
    username = getattr(user, "username", None)
    if not username:
        return None
    domain = getattr(user, "domain", "") or ""
    return username, domain


def get_visible_memories_qs(user) -> QuerySet[Memory]:
    """返回 user 可见的所有 Memory queryset。

    规则:
    - 团队空间(scope=team):返回全部 Memory。
    - 个人空间(scope=personal):仅 owner_username + owner_domain 与当前用户匹配的 Memory。
    - 未认证用户:返回空 queryset。

    实现:用单个 Q 对象表达「团队 OR (个人 且 owner 匹配)」,
    避免 Django QuerySet ``|`` 在某些场景触发 EmptyResultSet 优化。
    """
    identity = _user_identity(user)
    if identity is None:
        return Memory.objects.none()
    username, domain = identity

    visibility_q = Q(memory_space__scope=MemorySpace.SCOPE_TEAM) | Q(
        memory_space__scope=MemorySpace.SCOPE_PERSONAL,
        owner_username=username,
        owner_domain=domain,
    )
    return Memory.objects.filter(visibility_q)
