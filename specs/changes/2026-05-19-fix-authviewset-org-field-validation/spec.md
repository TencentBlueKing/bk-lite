# 2026 05 19 Fix Authviewset Org Field Validation

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-19-fix-authviewset-org-field-validation/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`operation_analysis` 模块的写接口（创建/更新）直接信任客户端提交的 `groups`/`team` 组织字段，没有校验目标组织是否在当前用户的可管理范围内。这导致用户可以将对象发布到自己无权管理的组织，造成跨组织数据泄露和配置漂移。

关联 Issue: https://github.com/TencentBlueKing/bk-lite/issues/3028

## What Changes

- 在 `AuthViewSet` 中添加 `_validate_org_field_permission` 方法，校验组织字段是否在用户可管理范围内
- 在 `AuthViewSet` 中新增 `create` 方法，创建时校验提交的组织字段
- 修改 `AuthViewSet.update` 方法，更新时校验新增的组织字段
- 超级管理员跳过校验

## Capabilities

### New Capabilities

- `org-field-validation`: AuthViewSet 组织字段写入权限校验能力

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **代码**: `server/apps/core/utils/viewset_utils.py` 的 `AuthViewSet` 类
- **API**: 所有继承 `AuthViewSet` 的 ViewSet 的 create/update 接口将增加组织字段校验
- **行为变更**: 用户尝试写入无权管理的组织时，将收到 403 PermissionDenied 错误

## Implementation Decisions

## Context

`AuthViewSet` 是 bk-lite 后端的核心权限控制基类，位于 `server/apps/core/utils/viewset_utils.py`。它通过 `ORGANIZATION_FIELD`（默认 `team`，可覆盖为 `groups`）字段实现组织级数据隔离。

当前问题：
- `AuthViewSet` 没有覆写 `create` 方法，创建时直接信任客户端提交的组织字段
- `AuthViewSet.update` 方法只校验 `current_team` 是否在旧对象的组织字段中，不校验新提交的组织是否在用户可管理范围内
- 读取时用组织字段做边界过滤，但写入时不校验，导致权限边界失效

## Goals / Non-Goals

**Goals:**
- 在 `AuthViewSet.create` 中校验提交的组织字段是否在用户可管理范围内
- 在 `AuthViewSet.update` 中校验新增的组织是否在用户可管理范围内
- 超级管理员跳过校验
- 复用现有的 `_normalize_org_values` 方法解析组织字段

**Non-Goals:**
- 不修改 `DirectoryModelViewSet` 等直接使用 ORM 的特殊实现
- 不修改读取逻辑
- 不修改删除逻辑

## Decisions

### 1. 校验方法设计

新增 `_validate_org_field_permission(request, org_values)` 方法：
- 获取 `user.group_list` 作为用户可管理的组织集合
- 检查 `org_values` 是否为该集合的子集
- 超级管理员跳过校验
- 校验失败抛出 `PermissionDenied`

**理由**: 与现有的 `_validate_current_team_permission` 方法风格一致，职责单一。

### 2. create 方法实现

新增 `create` 方法：
1. 从 `request.data` 中提取组织字段
2. 调用 `_normalize_org_values` 解析为 int 列表
3. 调用 `_validate_org_field_permission` 校验
4. 调用 `super().create()` 继续原有流程

**理由**: 最小侵入，复用现有方法。

### 3. update 方法修改

在现有 `update` 方法的组织字段处理逻辑中（约 line 460-463），添加对新增组织的校验：
1. 计算 `new_groups = set(org_values) - set(instance_org_value)`
2. 如果有新增组织，调用 `_validate_org_field_permission` 校验

**理由**: 只校验新增的组织，允许用户移除自己有权的组织（现有逻辑已处理）。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 现有 API 调用方可能依赖无校验行为 | 这是安全修复，应当强制执行。返回 403 错误信息明确 |
| 性能影响（每次写入多一次校验） | `user.group_list` 已在请求上下文中，无额外查询 |
| 子类覆写 create/update 可能绕过校验 | 文档说明，子类应调用 `super()` 或自行校验 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-19
```

## Capability Deltas

### org-field-validation

## ADDED Requirements

### Requirement: 创建时校验组织字段权限

当用户通过继承 `AuthViewSet` 的接口创建对象时，系统 SHALL 校验提交的组织字段（`team` 或 `groups`）是否在用户可管理的组织范围内。

#### Scenario: 用户创建对象时提交合法组织

- **WHEN** 用户属于组织 [1, 2]，创建对象时提交 `groups: [1, 2]`
- **THEN** 系统允许创建，对象的 `groups` 字段为 `[1, 2]`

#### Scenario: 用户创建对象时提交非法组织

- **WHEN** 用户属于组织 [1, 2]，创建对象时提交 `groups: [1, 999]`
- **THEN** 系统拒绝创建，返回 403 PermissionDenied 错误，错误信息包含无权操作的组织 ID

#### Scenario: 超级管理员创建对象时提交任意组织

- **WHEN** 超级管理员创建对象时提交 `groups: [1, 999]`
- **THEN** 系统允许创建，不校验组织权限

### Requirement: 更新时校验新增组织字段权限

当用户通过继承 `AuthViewSet` 的接口更新对象时，系统 SHALL 校验新增的组织是否在用户可管理的组织范围内。

#### Scenario: 用户更新对象时添加合法组织

- **WHEN** 用户属于组织 [1, 2, 3]，对象原 `groups` 为 `[1, 2]`，更新时提交 `groups: [1, 2, 3]`
- **THEN** 系统允许更新，对象的 `groups` 字段更新为 `[1, 2, 3]`

#### Scenario: 用户更新对象时添加非法组织

- **WHEN** 用户属于组织 [1, 2]，对象原 `groups` 为 `[1, 2]`，更新时提交 `groups: [1, 2, 999]`
- **THEN** 系统拒绝更新，返回 403 PermissionDenied 错误

#### Scenario: 用户更新对象时移除组织

- **WHEN** 用户属于组织 [1, 2]，对象原 `groups` 为 `[1, 2]`，更新时提交 `groups: [1]`
- **THEN** 系统允许更新（移除组织不需要额外校验）

#### Scenario: 超级管理员更新对象时添加任意组织

- **WHEN** 超级管理员更新对象，原 `groups` 为 `[1]`，提交 `groups: [1, 999]`
- **THEN** 系统允许更新，不校验组织权限

### Requirement: 组织字段为空时跳过校验

当提交的数据中不包含组织字段时，系统 SHALL 跳过组织权限校验。

#### Scenario: 创建时不提交组织字段

- **WHEN** 用户创建对象时不提交 `groups` 字段
- **THEN** 系统不进行组织权限校验，按原有逻辑处理

#### Scenario: 更新时不提交组织字段

- **WHEN** 用户更新对象时不提交 `groups` 字段
- **THEN** 系统不进行组织权限校验，按原有逻辑处理

## Work Checklist

## 1. 添加校验方法

- [x] 1.1 在 `AuthViewSet` 类中添加 `_validate_org_field_permission(self, request, org_values)` 方法，校验组织字段是否在用户可管理范围内

## 2. 实现 create 方法

- [x] 2.1 在 `AuthViewSet` 类中添加 `create(self, request, *args, **kwargs)` 方法
- [x] 2.2 在 create 方法中提取并校验组织字段，然后调用 `super().create()`

## 3. 修改 update 方法

- [x] 3.1 在 `AuthViewSet.update` 方法中，计算新增的组织（`new_groups = set(org_values) - set(instance_org_value)`）
- [x] 3.2 对新增的组织调用 `_validate_org_field_permission` 进行校验

## 4. 验证

- [x] 4.1 运行 `server/` 目录下的相关测试，确保现有功能不受影响
- [x] 4.2 检查 LSP 诊断，确保无类型错误
