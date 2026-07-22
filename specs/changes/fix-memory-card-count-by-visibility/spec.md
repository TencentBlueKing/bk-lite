# Fix Memory Card Count By Visibility

Status: ready

## Migration Context

- Legacy source: `openspec/changes/fix-memory-card-count-by-visibility/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot「记忆」模块外层卡片显示的「记忆条数: N」与详情页列表实际能看到的行数不一致:卡片用的是 `MemorySpace.memories.count()`(数据库真实条数),而详情页 `MemoryViewSet.list` 会再叠加「个人记忆仅创建者可见」的过滤。两者口径不同,导致同一张卡片点进去后,数字对不上、用户无法对账。

## What Changes

- 抽出一个共享的可见性过滤函数 `get_visible_memories_qs(memory_space, user)`,作为「当前用户对该空间可见的 Memory queryset」的唯一来源。
- `MemorySpaceSerializer.get_memory_count` 改为对 `get_visible_memories_qs(...).count()` 求值,使卡片数字与详情页列表可见行数口径一致。
- `MemoryViewSet.list` 改为复用同一函数替换原 inline `queryset.exclude(...)`,消除规则双份。
- 新增 `tests/memory/test_visibility.py` 单测,覆盖团队空间/个人空间创建者/个人空间非创建者三个分支。
- 新增/扩展一个集成测试:列表接口 `memory_count` 与详情页接口可见行数完全相等。

## Capabilities

### New Capabilities

- `memory-space-visible-count`: 记忆空间列表返回的记忆条数,必须按当前用户的可见性规则计算,与详情页列表口径一致。

### Modified Capabilities

- `memory-space`: 在该 spec 中**新增**一条 Requirement,要求 `memory_count` 字段值与 `GET /api/opspilot/memory/{memory_space_id}/` 对当前用户返回的可见行数相等(口径一致即可,实现由后端 helper 决定)。

## Impact

- 受影响代码(全部位于 `server/apps/opspilot/`,前端不动):
  - `serializers/memory_serializer.py` —— `MemorySpaceSerializer.get_memory_count` 改造
  - `viewsets/memory_view.py` —— `MemorySpaceViewSet.list` 不动(仍由 `AuthViewSet` 走 `team` 权限);`MemoryViewSet.list` 改用 helper
  - `memory/visibility.py`(新) —— `get_visible_memories_qs` 实现
  - `tests/memory/test_visibility.py`(新) + 既有 memory 集成测试扩展
- API 契约:`memory_count: number` 字段名、类型、URL 全部不变;只是数值口径变正确。
- 不涉及数据库迁移、URL 变更、依赖变更、前端改动。

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-09
```

## Capability Deltas

### memory-space

## ADDED Requirements

### Requirement: 列表返回的记忆条数遵循用户可见性规则
`MemorySpace` 列表 API SHALL 返回的 `memory_count` 字段值,等于当前用户在同一空间下通过 `GET /api/opspilot/memory/?memory_space=<id>` 能看到的 Memory 行数。

#### Scenario: 团队空间全可见
- **WHEN** 调用 `GET /api/opspilot/memory_space/`,空间 `scope=team` 且 `memories.count() = 3`
- **THEN** 返回的 `memory_count = 3`

#### Scenario: 个人空间非创建者不可见
- **WHEN** 调用 `GET /api/opspilot/memory_space/` 的用户不是该 `scope=personal` 空间的创建者
- **THEN** 返回的 `memory_count = 0`

#### Scenario: 个人空间创建者可见
- **WHEN** 调用 `GET /api/opspilot/memory_space/` 的用户是该 `scope=personal` 空间的创建者,且 `memories.count() = 2`
- **THEN** 返回的 `memory_count = 2`

### memory-space-visible-count

## ADDED Requirements

### Requirement: 共享可见性过滤函数
`server/apps/opspilot/memory/visibility.py` MUST 提供 `get_visible_memories_qs(user, *, memory_space_id: int)`,返回「该用户在该 memory_space 下可见的 Memory queryset」,作为整个记忆模块可见性规则的唯一来源。

#### Scenario: 团队空间对任意用户可见
- **WHEN** 传入 `user` 为任意用户,`memory_space_id` 为 `SCOPE_TEAM` 的空间
- **THEN** 返回该空间下全部 Memory 的 queryset

#### Scenario: 个人空间仅创建者可见
- **WHEN** 传入 `user` 为空间创建者,`memory_space_id` 为 `SCOPE_PERSONAL` 的空间
- **THEN** 返回该空间下全部 Memory 的 queryset

#### Scenario: 个人空间非创建者不可见
- **WHEN** 传入 `user` 为非创建者,`memory_space_id` 为 `SCOPE_PERSONAL` 的空间
- **THEN** 返回空 queryset

#### Scenario: 未认证用户
- **WHEN** 传入 `user` 为 `AnonymousUser` 或 `is_authenticated=False`
- **THEN** 返回空 queryset 且不抛异常

### Requirement: 卡片记忆条数字段一致性
`GET /api/opspilot/memory_space/` 列表接口返回的 `memory_count` 字段 MUST 与同一用户对同一空间调用 `GET /api/opspilot/memory/?memory_space=<id>` 时可见行数相等。

#### Scenario: 团队空间条数对齐
- **WHEN** 用户 A 请求一个团队记忆空间列表,该空间有 3 条记忆
- **THEN** 卡片 `memory_count = 3`,且详情列表也返回 3 行

#### Scenario: 个人空间非创建者对齐为零
- **WHEN** 用户 B 请求列表,看到一个用户 A 创建的个人记忆空间
- **THEN** 卡片 `memory_count = 0`,且详情列表返回空

#### Scenario: 个人空间创建者对齐
- **WHEN** 用户 A 请求自己创建的个人记忆空间,该空间有 2 条记忆
- **THEN** 卡片 `memory_count = 2`,且详情列表返回 2 行

## Work Checklist

## 1. 准备测试环境与失败用例(TDD 红)

- [ ] 1.1 在 `server/apps/opspilot/tests/memory/` 下新增 `test_visibility.py`,写入四个 helper 单测场景:团队空间全见、个人空间创建者见、个人空间非创建者不可见、未认证用户空集合
- [ ] 1.2 在 `server/apps/opspilot/tests/memory/` 下新增/扩展集成测试 `test_memory_space_count.py`,断言列表接口 `memory_count` 与详情页接口可见行数相等(团队/个人创建者/个人非创建者三组样本)
- [ ] 1.3 运行 `cd server && make test APP=opspilot TEST=tests/memory/test_visibility.py`,确认新单测**全部 FAIL**(红);确认集成测试 FAIL
- [ ] 1.4 在 worktree 中跑不通单测时,按「worktree vs main repo bash cwd」记忆,在 master 主仓库跑同命令兜底

## 2. 抽 helper 并完成改造(绿)

- [ ] 2.1 在 `server/apps/opspilot/memory/visibility.py`(新文件)实现 `get_visible_memories_qs(user, *, memory_space_id: int) -> QuerySet[Memory]`,逻辑等价于原 `MemoryViewSet.list` 内联过滤
- [ ] 2.2 修改 `server/apps/opspilot/serializers/memory_serializer.py` 的 `MemorySpaceSerializer.get_memory_count`,改为 `get_visible_memories_qs(self.context['request'].user, memory_space_id=instance.id).count()`
- [ ] 2.3 修改 `server/apps/opspilot/viewsets/memory_view.py` 的 `MemoryViewSet.get_queryset`,返回 `get_visible_memories_qs(self.request.user, memory_space_id=<query_params['memory_space']>)`,移除原 list 内联过滤块
- [ ] 2.4 运行 1.3 同命令,确认单测**全部 PASS**(绿);集成测试 PASS

## 3. 质量门禁与回归

- [ ] 3.1 `cd server && make test` 全量回归,确认无新增失败(尤其是 `opspilot` 全部测试)
- [ ] 3.2 `cd server && pre-commit run --all-files`(或等价的 black/isort/flake8)确保格式与导入顺序通过
- [ ] 3.3 在 master 主仓库跑同 pytest 一次(worktree 缺 MINIO env),排除「worktree vs master」因素

## 4. 文档与归档

- [ ] 4.1 跑 `openspec validate fix-memory-card-count-by-visibility --strict`,确认三件套全部通过
- [ ] 4.2 提交变更到 worktree 分支(不推、不 merge master,等用户确认);commit message 中文,前缀遵循「个人 commit 前缀规约」(本次为修复类,用 `fix`)
- [ ] 4.3 用户确认后再同步到 master 并归档:`openspec archive fix-memory-card-count-by-visibility`
