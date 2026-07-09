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