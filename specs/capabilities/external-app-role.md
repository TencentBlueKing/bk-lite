# external-app-role

## Purpose

定义外部应用（`is_build_in=False`）与角色系统的集成行为：包括外部应用创建/删除时的角色生命周期管理、角色分配 UI 的展示逻辑，以及用户授权后对外部应用的可见性。

## Requirements

### Requirement: 创建外部应用时自动创建 user 角色
创建外部应用（`is_build_in=False`）时，系统 SHALL 在同一事务中自动创建一个名为 `user` 的角色（`Role(name='user', app=<app_name>)`）。若角色已存在则幂等跳过（get_or_create 语义）。

#### Scenario: 创建外部应用成功，角色同步创建
- **WHEN** 管理员通过 API 创建一个新的外部应用（`is_build_in=False`）
- **THEN** 系统同时在 Role 表中创建 `{name: 'user', app: <新应用名>}` 记录

#### Scenario: 角色创建失败时回滚应用创建
- **WHEN** 创建外部应用时 Role 写入失败（数据库异常）
- **THEN** 应用创建操作一并回滚，App 表中无新记录

### Requirement: 删除外部应用时级联删除对应角色
删除外部应用时，系统 SHALL 自动删除对应的所有 `Role` 记录（`Role.objects.filter(app=app_name).delete()`）。

#### Scenario: 删除外部应用，角色同步清除
- **WHEN** 管理员删除一个外部应用
- **THEN** 该应用对应的所有 Role 记录被一并删除

#### Scenario: 删除内置应用不受影响（内置应用不可删）
- **WHEN** 管理员尝试删除内置应用
- **THEN** 系统返回错误，内置应用和其 Role 均不变

### Requirement: 角色分配 UI 展示外部应用角色
`get_role_tree` API SHALL 返回所有有 Role 记录的应用（包括 `is_build_in=False` 的外部应用）的角色树，不再按 `is_build_in` 过滤。

#### Scenario: 角色树包含外部应用
- **WHEN** 管理员打开编辑组织或编辑用户弹窗，加载角色树
- **THEN** 角色树中包含已创建外部应用的 `user` 角色节点

#### Scenario: 未创建外部应用时角色树不受影响
- **WHEN** 系统中没有外部应用
- **THEN** 角色树仅展示内置应用的角色，与修改前行为一致

### Requirement: 授权后用户可见外部应用
当组织或用户被授予外部应用的 `user` 角色后，系统 SHALL 在 `get_client(username)` 中返回该外部应用，使其出现在 ops-console 首页和应用切换列表中。

#### Scenario: 授权用户可见外部应用
- **WHEN** 用户所在组织或用户本人被分配了外部应用的 `user` 角色
- **THEN** 用户登录后，ops-console 首页和顶部应用切换列表中可看到该外部应用卡片

#### Scenario: 未授权用户不可见外部应用
- **WHEN** 用户未被分配任何外部应用角色
- **THEN** ops-console 首页和应用切换列表中不显示该外部应用
