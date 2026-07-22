# 2026 05 07 External App Role Access

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-07-external-app-role-access/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

外部应用（External App）添加后，所有普通用户在 ops-console 和应用切换列表中均看不到该应用——因为当前系统仅为内置应用自动创建角色，且角色分配 UI 硬过滤了非内置应用。管理员无法为组织或用户授予外部应用的访问权限，导致外部应用无法投入实际使用。

## What Changes

- **新增**：创建外部应用时，自动同步创建对应的 `user` 角色（`Role(name='user', app=<app_name>)`），并与应用创建操作保持事务一致性
- **新增**：删除外部应用时，自动级联删除对应的 `user` 角色
- **修改**：`get_role_tree` API 去除 `is_build_in` 硬过滤，返回所有应用（内置 + 外部）的角色供分配 UI 使用
- 授权后，普通用户可在 ops-console 首页卡片和顶部应用切换器中看到该外部应用

## Capabilities

### New Capabilities

- `external-app-role`: 外部应用的角色生命周期管理——创建时自动建立 user 角色，删除时级联清理，角色分配 UI 可见外部应用角色

### Modified Capabilities

<!-- 无现有 spec 需要变更 -->

## Impact

- **后端**：
  - `server/apps/system_mgmt/serializers/app_serializer.py` — `create()` 方法新增 Role 创建逻辑
  - `server/apps/system_mgmt/viewset/app_viewset.py` — `destroy()` 方法新增级联删除 Role 逻辑
  - `server/apps/system_mgmt/viewset/role_viewset.py` — `get_role_tree()` 去除 `is_build_in` 过滤
- **前端**：无需改动（`clientData` 权限过滤和角色树展示逻辑已具备，后端修复后自动生效）
- **数据库**：无 migration（Role 表结构不变，仅数据层面新增记录）
- **已有数据**：历史外部应用不受影响（无 Role 记录），管理员可手动补充授权或通过管理命令修复

## Implementation Decisions

## Context

系统通过 `App` 表管理所有应用（内置 + 外部），通过 `Role` 表管理各应用的角色（`Role.app` 字段关联应用名）。`get_client(username)` 通过"用户拥有哪些 Role.app → 过滤 App 列表"来决定用户可见哪些应用。

当前存在两个断点：
1. 外部应用创建时只写 `App` 表，不创建对应 `Role`，用户永远无法被授权
2. `get_role_tree` API 硬过滤 `is_build_in=True`，即使手动创建了 Role，管理 UI 中也不可见

## Goals / Non-Goals

**Goals:**
- 外部应用创建时自动创建 `user` 角色，保证可授权
- 外部应用删除时级联删除对应角色，避免孤立数据
- 角色分配 UI（编辑组织/用户）中能看到外部应用的 `user` 角色
- 授权后，普通用户在 ops-console 和应用切换列表中可见外部应用

**Non-Goals:**
- 不为外部应用创建 `admin`/`normal` 等多个角色（外部应用语义简单，仅需"有无访问权"）
- 不处理历史已存在的外部应用数据修复（留给管理员手动或运维脚本处理）
- 不改动前端代码（现有权限过滤和角色树展示逻辑已具备）

## Decisions

### D1: 在 Serializer 层而非 ViewSet 层创建角色

**选择**：在 `AppSerializer.create()` 中创建 Role，并用 `transaction.atomic` 包裹。

**理由**：Serializer 的 `create()` 是数据写入的天然收口，Django REST Framework 在这里已有事务语义保障。若放在 ViewSet，需要覆盖更多方法（list/create/update），侵入面更大。

**替代方案**：Django `post_save` signal → 拒绝，signal 难以追踪、不易测试，且无法保证与主事务同步。

### D2: 去除 `get_role_tree` 的 `is_build_in` 过滤而非新增参数

**选择**：直接移除过滤条件，让所有有 Role 记录的应用都出现在角色树中。

**理由**：外部应用只要有 Role 就应该可被授权，`is_build_in` 在这个查询中没有业务价值。新增参数会增加接口复杂度，而现有调用方（前端 `getRoleList`）已经传入完整 `client_list`，不需要区分。

**替代方案**：新增 `include_external` 参数 → 不必要的复杂性。

### D3: 角色名固定为 `user`

**选择**：外部应用只创建一个名为 `user` 的角色。

**理由**：`get_client` 通过 `Role.app` 判断可见性，只要存在任意角色即可。外部应用是第三方系统，bk-lite 无法管理其内部权限分级，`user` 表示"有权访问"语义清晰。

## Risks / Trade-offs

- **[风险] 历史外部应用无 Role 记录** → 现有数据不受影响，普通用户依然不可见；管理员可通过 django shell 或 management command 补录，不影响本次功能交付
- **[风险] `get_role_tree` 去除过滤后，外部应用 Role 显示在分配 UI 中，但内置应用的 admin/normal 等多角色已有成熟处理** → 外部应用只有一个 `user` 角色，树形结构简洁，不影响现有 UI 渲染逻辑
- **[风险] 删除外部应用时，已分配给用户/组的 Role ID 成为悬空引用** → 级联删除 Role 后，`user.role_list` / `group.roles` 中的 ID 会变为无效；这与内置应用的删除行为一致（内置应用不允许删除），属于可接受的边界情况，后续可通过 clean job 处理

## Migration Plan

1. 部署新代码即生效，无 migration 文件
2. 回滚：回退代码即可；历史数据无破坏性变更
3. 历史外部应用修复（可选，非强制）：
   ```python
   from apps.system_mgmt.models import App, Role
   for app in App.objects.filter(is_build_in=False):
       Role.objects.get_or_create(name='user', app=app.name)
   ```

## Open Questions

- 无

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-07
```

## Capability Deltas

### external-app-role

## ADDED Requirements

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

## Work Checklist

## 1. 后端 — AppSerializer 创建角色

- [x] 1.1 在 `AppSerializer.create()` 中引入 `transaction.atomic`，保证 App 和 Role 同事务写入
- [x] 1.2 在 `AppSerializer.create()` 中调用 `Role.objects.get_or_create(name='user', app=validated_data['name'])` 创建外部应用的 user 角色

## 2. 后端 — AppViewSet 级联删除角色

- [x] 2.1 在 `AppViewSet.destroy()` 中，于父类 `destroy()` 调用前执行 `Role.objects.filter(app=obj.name).delete()`，级联清理角色数据

## 3. 后端 — get_role_tree 去除 is_build_in 过滤

- [x] 3.1 在 `RoleViewSet.get_role_tree()` 中，将 `client_list = [i for i in ... if i.get("is_build_in")]` 改为接受所有应用（移除 `is_build_in` 过滤条件）

## 4. 验证

- [x] 4.1 创建外部应用后，确认 Role 表中存在对应 `user` 角色记录
- [x] 4.2 调用 `get_role_tree` API，确认响应中包含外部应用的角色节点
- [x] 4.3 为组织分配外部应用 `user` 角色后，组织内用户登录可在 ops-console 和应用切换列表看到该应用
- [x] 4.4 删除外部应用后，确认对应 Role 记录被清除
