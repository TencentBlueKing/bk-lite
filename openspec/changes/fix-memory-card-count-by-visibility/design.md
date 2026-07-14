## Context

OpsPilot「记忆」外层页面(`web/src/app/opspilot/(pages)/memory/page.tsx`)展示 `MemorySpace` 卡片,卡片底部显示「记忆条数: N」。该数值取自后端字段 `memory_count`,由 `MemorySpaceSerializer.get_memory_count`(`server/apps/opspilot/serializers/memory_serializer.py:40-41`)派生,实现为 `instance.memories.count()`。

点击卡片进入详情页(`web/src/app/opspilot/(pages)/memory/detail/memories/page.tsx`)后,前端请求 `GET /opspilot/memory_mgmt/memory/?memory_space=<id>`,由 `MemoryViewSet.list`(`server/apps/opspilot/viewsets/memory_view.py:138-155`)处理。`MemoryViewSet.list` 在标准 DRF 过滤之外,再叠加一段 inline 过滤:

```python
queryset = queryset.exclude(
    memory_space__scope=SCOPE_PERSONAL,
).exclude(
    ~Q(memory_space__owner_username=self.request.user.username)
    | ~Q(memory_space__owner_domain=self.request.user.domain),
)
```

即:个人记忆空间中,只有创建者本人可见,他人 `count = 0`。

问题就出在这里:卡片 `memory_count` 走 `count()`(统计数据库全部行),详情页 `list` 走上述过滤,两个口径不一致。截图 2 中第二张卡显示「记忆条数: 2」,但点开是个人记忆空间,详情表却「暂无数据」,即卡片数字 2 是真值,详情表 0 行是过滤后的值,两侧对不上。

## Goals / Non-Goals

**Goals:**

- 让 `MemorySpaceSerializer.memory_count` 与 `MemoryViewSet.list` 走同一份可见性过滤,数字永远对得上。
- 把可见性规则收敛到单一函数,后续任何个人/团队规则改动只改一处。
- 不改变 API 契约(URL、字段名、字段类型、HTTP 方法不变)。
- 不改变前端展示逻辑,前端 `space.memory_count || 0` 维持不变。

**Non-Goals:**

- 不修改 `MemorySpaceViewSet.list` 的 `team`/`query_by_groups` 权限过滤(由 `AuthViewSet` 统一处理)。
- 不修改 `MemoryViewSet.list` 的现有 `filterset_fields = ("memory_space",)` DRF 过滤。
- 不引入新依赖、不改 schema、不动前端。
- 不扩展为「按组/按 scope 显式过滤」——本次只修一致性问题。

## Decisions

### D1. 抽 helper 函数 `get_visible_memories_qs(memory_space, user)`

**选项**:

- (A) 抽 helper,serializer 与 ViewSet 共用 ✅(采用)
- (B) `MemorySpaceViewSet.get_queryset` 用 `annotate(memory_count=Count(...))` —— 可见性规则双份;ORM 注解难单测。
- (C) 内联复制过滤到 serializer —— 改动最小但规则双份。

**理由**:把「可见性」这一不变量收敛到一个函数。`MemoryViewSet.list` 当前依赖 `request`,helper 函数签名显式传 `user`,避免对请求对象的隐式依赖,易单测,易复用。

### D2. helper 放在 `server/apps/opspilot/memory/visibility.py`

新建模块而非塞进 `viewsets/memory_view.py`:

- 视图层只负责请求/响应,领域规则放到 `memory/` 子包,与既有 engines 子包并列,结构一致。
- 单测可直接 `from apps.opspilot.memory.visibility import get_visible_memories_qs`,不依赖 DRF `Request` 对象。

### D3. serializer 通过 `self.context['request'].user` 取 user,不引入新参数

DRF 视图层在调用 serializer 时已注入 `request` 到 context,直接复用,无需改 ViewSet 调用方式。

### D4. `MemoryViewSet.list` 内联过滤块替换为 helper 调用,不修改行为

- 替换前:`queryset = queryset.exclude(memory_space__scope=SCOPE_PERSONAL,).exclude(...)`
- 替换后:`queryset = get_visible_memories_qs(queryset.first().memory_space, self.request.user) if queryset.exists() else queryset`

不对,这一替换不优雅。helper 签名是 `get_visible_memories_qs(memory_space, user)`,但 `MemoryViewSet.list` 拿到的是已按 `memory_space=<id>` 过滤后的 queryset,内存空间已经确定。更合适的复用方式:

- `MemoryViewSet.list` 改成:`queryset = get_visible_memories_qs_for_list(self.request, memory_space_id)` —— 内部 `Memory.objects.filter(memory_space=memory_space_id)` + 可见性过滤,返回一个最终 queryset。

为避免 helper 双签名(per-space vs per-list),统一签名为:

```python
def get_visible_memories_qs(user, *, memory_space: MemorySpace) -> QuerySet[Memory]: ...
```

- `MemorySpaceSerializer.get_memory_count`:从 `instance`(已经是 `MemorySpace`)直接调用 `get_visible_memories_qs(self.context['request'].user, memory_space=instance).count()`。
- `MemoryViewSet.list`:在 `super().list()` 之前,把 `queryset` 重置为 `Memory.objects.none()` 或继续按 `memory_space=<id>` 过滤后,再调用 `get_visible_memories_qs(user, memory_space=<由 URL kwarg 得到>)` 得到最终 queryset。

更精简:在 `MemoryViewSet.get_queryset()`(而非 list 方法)返回最终 queryset:

```python
def get_queryset(self):
    qs = Memory.objects.filter(memory_space_id=self.kwargs.get("memory_space") or self.request.query_params.get("memory_space"))
    return get_visible_memories_qs(self.request.user, memory_space_id=...)
```

helper 最终签名定为:

```python
def get_visible_memories_qs(user, *, memory_space_id: int) -> QuerySet[Memory]:
    """返回该用户在指定 memory_space 下可见的 Memory queryset。"""
    base = Memory.objects.filter(memory_space_id=memory_space_id)
    return base.exclude(
        memory_space__scope=SCOPE_PERSONAL,
    ).exclude(
        ~Q(memory_space__owner_username=user.username)
        | ~Q(memory_space__owner_domain=user.domain),
    )
```

- `MemorySpaceSerializer.get_memory_count`:`get_visible_memories_qs(self.context['request'].user, memory_space_id=instance.id).count()`
- `MemoryViewSet.get_queryset`:`return get_visible_memories_qs(self.request.user, memory_space_id=<query_params['memory_space']>)`

这样两处**唯一可见性来源**,helper 签名简洁(只需 `user` + `memory_space_id`),`MemorySpaceSerializer` 不再需要访问 `instance.memories` 关系。

### D5. 集成测试用 APIClient + 创建 3 类样本数据

- 一个团队空间 + 1 条记忆 —— 任意用户可见,N=1。
- 一个个人空间(用户 A 创建)+ 1 条记忆 —— 用户 A 看到 N=1,用户 B 看到 N=0。
- 直接断言 `GET /memory_mgmt/memory_space/ {memory_count}` 与 `GET /memory_mgmt/memory/?memory_space=<id>` 返回行数相等。

## Risks / Trade-offs

- [helper 改了可见性规则,ViewSet 与 serializer 同步生效 — 已对齐,且由单测守门] → 用例覆盖团队/个人创建者/个人非创建者三个分支
- [把 inline 过滤从 `list` 移到 `get_queryset`,行为变化需回归测试覆盖] → 集成测试保留原有「个人记忆仅创建者可见」断言
- [helper 未处理 `AnonymousUser`] → 若 user 是 `AnonymousUser`,`user.username` 抛 AttributeError;在 helper 顶部加 `if not user or not user.is_authenticated: return Memory.objects.none()` 兜底
- [前端未做兼容改动] → API 契约完全不变,前端 0 改动

## Migration Plan

无需迁移。直接部署即可,无 schema 变更。

回滚策略:直接 `git revert` 即可,无副作用。

## Open Questions

无。本次变更范围明确、依赖关系简单、用户已确认范围/口径/实现方式三个关键决策。