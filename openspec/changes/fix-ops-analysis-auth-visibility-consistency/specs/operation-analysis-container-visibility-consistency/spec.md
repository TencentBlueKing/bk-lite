## ADDED Requirements

### Requirement: Canvas target groups MUST be covered by the full directory ancestry

仪表盘、拓扑图、架构图在保存时，其目标 `groups` 必须被所属目录及全部祖先目录的 `groups` 完整覆盖。系统不得接受“对象自身可见但目录链不可见”的配置。

#### Scenario: Reject canvas save when direct parent directory does not cover target groups

- **Given** 某仪表盘目标目录的 `groups = [1]`
- **When** 用户尝试将该仪表盘保存为 `groups = [1, 2]`
- **Then** 系统必须拒绝保存
- **And** 系统必须说明直属目录未覆盖组织 `2`

#### Scenario: Reject canvas save when ancestor directory does not cover target groups

- **Given** 某拓扑图所属子目录 `groups = [1, 2]`
- **And** 该子目录的父目录 `groups = [1]`
- **When** 用户尝试将该拓扑图保存为 `groups = [1, 2]`
- **Then** 系统必须拒绝保存
- **And** 系统必须说明祖先目录链未覆盖组织 `2`

#### Scenario: Allow canvas save when the entire directory chain covers target groups

- **Given** 某架构图所属目录及全部祖先目录的 `groups` 均包含 `1` 和 `2`
- **When** 用户将该架构图保存为 `groups = [1, 2]`
- **Then** 系统必须允许保存

### Requirement: Directory-chain validation errors SHOULD identify the conflicting containers

当对象保存因目录链可见性不一致而失败时，系统应返回足够的冲突信息，便于调用方明确是哪个目录阻止了对象在目标组织中被发现。

#### Scenario: Return structured conflict details for directory-chain mismatch

- **Given** 用户保存某仪表盘时，其目标组织超出了祖先目录的可见范围
- **When** 系统拒绝该保存请求
- **Then** 响应中应包含至少一个冲突目录的标识信息
- **And** 响应中应包含该目录缺失覆盖的组织 ID 信息
