## ADDED Requirements

### Requirement: Directory write requests MUST use the unified AuthViewSet authorization chain

`operation_analysis` 的目录创建、更新、部分更新请求必须执行与其他 `AuthViewSet` 子类一致的写时授权校验，不得仅凭模块级菜单权限直接写库。

#### Scenario: Reject directory create with unauthorized target groups

- **Given** 用户具备目录模块新增菜单权限
- **And** 用户可管理组织仅包含 `1`
- **When** 用户提交目录创建请求，目标 `groups = [1, 2]`
- **Then** 系统必须拒绝创建请求并返回 403
- **And** 系统必须指出目标组织超出当前用户可管理范围

#### Scenario: Reject directory update without current-team ownership or instance operate permission

- **Given** 某目录对象存在且其 `groups` 不包含当前请求的 `current_team`
- **When** 用户提交目录更新请求
- **Then** 系统必须拒绝更新请求并返回 403

#### Scenario: Allow authorized directory write through shared viewset flow

- **Given** 用户具备目录模块写权限
- **And** 目标目录写入组织均在用户可管理范围内
- **And** 对于更新请求，用户对该目录实例具备操作权限
- **When** 用户提交目录创建或更新请求
- **Then** 系统必须允许请求通过统一写时授权链完成保存

### Requirement: Directory-specific business rules MUST NOT bypass authorization

目录特有业务规则（如内置目录只读）可以额外约束目录写操作，但不得替代组织范围校验或实例级授权校验。

#### Scenario: Built-in directory remains read-only after auth refactor

- **Given** 某目录对象为内置目录
- **And** 当前用户对其组织和实例权限均合法
- **When** 用户尝试更新该目录
- **Then** 系统必须拒绝该请求
- **And** 拒绝原因必须是内置目录只读，而非授权链被绕过
