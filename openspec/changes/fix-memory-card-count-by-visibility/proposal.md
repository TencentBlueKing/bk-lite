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