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