# Fix Authviewset Current Team Validation

Status: done

## Migration Context

- Legacy source: `openspec/changes/fix-authviewset-current-team-validation/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`AuthViewSet.filter_by_group()` 从 cookie 获取 `current_team` 后直接用于数据筛选，没有验证当前用户是否有权限访问该 team。攻击者可以伪造 cookie 中的 `current_team` 值，越权访问其他团队的数据。这是一个权限提升漏洞，需要立即修复。

## What Changes

- 在 `filter_by_group()` 方法中添加 `current_team` 权限验证
- 验证逻辑：`current_team` 必须存在于 `user.group_list` 的 id 列表中
- 超管用户（`is_superuser=True`）豁免此验证
- 验证失败时抛出 `PermissionDenied` 异常，返回 403

## Capabilities

### New Capabilities

- `current-team-validation`: 验证 cookie 中的 current_team 是否在用户有权限的团队列表中

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **代码**: `server/apps/core/utils/viewset_utils.py` - `GenericViewSetFun.filter_by_group()` 方法
- **API**: 所有继承 `AuthViewSet` 的 ViewSet 的 list 接口
- **行为变更**: 如果 `current_team` cookie 值不在用户的 `group_list` 中，将返回 403 而非之前的（可能越权的）数据
- **依赖**: 需要导入 `rest_framework.exceptions.PermissionDenied`

## Implementation Decisions

## Context

`AuthViewSet` 是 BK-Lite 后端的核心 ViewSet 基类，所有需要权限控制的 API 都继承自它。当前 `filter_by_group()` 方法从 cookie 读取 `current_team` 后直接用于数据筛选，没有验证用户是否有权访问该团队。

**当前数据流**:
```
Cookie(current_team=X) → filter_by_group() → Q(team__contains=X) → 返回数据
                         ↑
                         没有验证 X 是否在 user.group_list 中
```

**用户权限数据来源**:
- `user.group_list`: 从 token 验证获取，格式为 `[{"id": 1, "name": "default", "parent_id": 0}, ...]`
- `user.is_superuser`: 超管标识，超管拥有所有团队的访问权限

## Goals / Non-Goals

**Goals:**
- 在 `filter_by_group()` 中验证 `current_team` 是否在用户有权限的团队列表中
- 超管用户豁免此验证
- 验证失败返回 403 Forbidden
- 为 opspilot 模块创建 `TeamPermissionMixin`，统一 current_team 验证逻辑
- 为 system_mgmt 模块创建 `GroupPermissionMixin`，验证用户对特定组的访问权限
- 为缺少 `@HasPermission` 装饰器的 ViewSet 添加功能权限控制

**Non-Goals:**
- 不修改 node_mgmt 模块（Issue #2877 单独处理）
- 不修改 `current_team` 的解析逻辑（`_parse_current_team_cookie`）
- 不修改前端行为

## Decisions

### 1. 验证位置：`filter_by_group()` 方法开头

**选择**: 在 `current_team = cls._parse_current_team_cookie(request)` 之后立即验证

**理由**:
- 这是 `current_team` 被使用的最早位置
- 所有通过 `AuthViewSet.list()` 的请求都会经过这里
- 验证失败可以立即抛出异常，避免后续无意义的计算

**备选方案**:
- 在 `_parse_current_team_cookie()` 中验证：需要修改方法签名传入 user，影响范围更大
- 在 middleware 中验证：全局影响，可能影响不需要此验证的接口

### 2. 验证失败处理：抛出 `PermissionDenied` 异常

**选择**: 使用 `rest_framework.exceptions.PermissionDenied`

**理由**:
- DRF 标准异常，自动返回 403 状态码
- 与现有权限检查模式一致
- 不需要修改返回值类型

### 3. 超管豁免逻辑

**选择**: 检查 `user.is_superuser` 属性

**理由**:
- 超管拥有所有团队的访问权限，这是系统设计
- `is_superuser` 在认证时从 token 中获取，是可信数据

### 4. opspilot 模块：TeamPermissionMixin

**选择**: 创建独立的 `TeamPermissionMixin` 类

**理由**:
- opspilot 的 ViewSet 有些不继承 `AuthViewSet`（如 `LanguageViewSet`）
- Mixin 模式允许灵活组合，不强制继承关系
- 提供 `_validate_current_team_permission()` 和 `_validate_knowledge_base_permission()` 等方法

### 5. system_mgmt 模块：GroupPermissionMixin

**选择**: 创建独立的 `GroupPermissionMixin` 类

**理由**:
- system_mgmt 不使用 current_team 验证，而是验证用户对特定 group 的访问权限
- 通过 `user.group_list` 检查用户是否有权访问目标组
- 提供 `_get_user_group_ids()` 和 `_validate_group_permission()` 等方法

### 6. @HasPermission 装饰器

**选择**: 基于 `opspilot.json` 中的权限 key 添加装饰器

**权限映射**:
- WorkFlowTaskResultViewSet → `bot_conversation_log-View`
- ChatApplicationViewSet → `bot_list-View`
- BotViewSet (list/retrieve) → `bot_list-View`
- ModelVendorViewSet → `provide_list-View/Add/Setting/Delete`

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 前端可能依赖当前（不安全）行为 | 前端应该只设置用户有权限的 team，此修复不影响正常使用 |
| `group_list` 为空时所有请求都会 403 | 这是正确行为，没有团队权限的用户不应访问任何数据 |
| 性能影响 | 验证逻辑是 O(n) 的集合查找，n 为用户所属团队数，通常很小，可忽略 |
| node_mgmt 模块未修复 | Issue #2877 单独跟踪，需要修改 `get_node_permission()` 函数 |

## 修改的文件清单

### 核心
- `server/apps/core/utils/viewset_utils.py` - AuthViewSet 添加 `_validate_current_team_permission()`

### opspilot 模块
- `server/apps/opspilot/utils/team_permission_mixin.py` - 新建 TeamPermissionMixin
- `server/apps/opspilot/utils/vendor_model_mixin.py` - 新建 VendorModelMixin
- `server/apps/opspilot/viewsets/bot_view.py`
- `server/apps/opspilot/viewsets/chat_application_view.py`
- `server/apps/opspilot/viewsets/workflow_task_result_view.py`
- `server/apps/opspilot/viewsets/model_vendor_view.py`
- `server/apps/opspilot/viewsets/knowledge_base_view.py`
- `server/apps/opspilot/viewsets/knowledge_document_view.py`
- `server/apps/opspilot/viewsets/file_knowledge_view.py`
- `server/apps/opspilot/viewsets/manual_knowledge_view.py`
- `server/apps/opspilot/viewsets/web_page_knowledge_view.py`
- `server/apps/opspilot/viewsets/qa_pairs_view.py`
- `server/apps/opspilot/viewsets/knowledge_graph_view.py`
- `server/apps/opspilot/viewsets/history_view.py`
- `server/apps/opspilot/viewsets/llm_view.py`
- `server/apps/opspilot/viewsets/embed_view.py`
- `server/apps/opspilot/viewsets/rerank_view.py`
- `server/apps/opspilot/viewsets/ocr_view.py`

### system_mgmt 模块
- `server/apps/system_mgmt/utils/group_filter_mixin.py` - 添加 GroupPermissionMixin
- `server/apps/system_mgmt/viewset/channel_viewset.py`
- `server/apps/system_mgmt/viewset/user_viewset.py`
- `server/apps/system_mgmt/viewset/group_viewset.py`
- `server/apps/system_mgmt/viewset/group_data_rule_viewset.py`

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-11
```

## Capability Deltas

### current-team-validation

## ADDED Requirements

### Requirement: Validate current_team against user permissions

The system SHALL validate that the `current_team` cookie value is within the user's authorized team list (`user.group_list`) before using it for data filtering in `AuthViewSet`.

#### Scenario: User accesses data with valid current_team
- **WHEN** user has `group_list = [{"id": 1}, {"id": 2}]` and `current_team` cookie is `1`
- **THEN** system SHALL proceed with data filtering using `current_team=1`

#### Scenario: User accesses data with invalid current_team
- **WHEN** user has `group_list = [{"id": 1}]` and `current_team` cookie is `999`
- **THEN** system SHALL raise `PermissionDenied` exception and return HTTP 403

#### Scenario: User accesses data with non-numeric current_team
- **WHEN** `current_team` cookie is `"abc"` (non-numeric)
- **THEN** system SHALL use default value `0` (existing behavior from `_parse_current_team_cookie`)
- **AND** validation SHALL check if `0` is in user's `group_list`

### Requirement: Superuser bypass validation

The system SHALL allow superusers to access any team's data without validation.

#### Scenario: Superuser accesses data with any current_team
- **WHEN** user has `is_superuser=True` and `current_team` cookie is `999`
- **THEN** system SHALL proceed with data filtering using `current_team=999` without checking `group_list`

#### Scenario: Non-superuser must pass validation
- **WHEN** user has `is_superuser=False` and `current_team` cookie is not in their `group_list`
- **THEN** system SHALL raise `PermissionDenied` exception and return HTTP 403

### Requirement: Extract team IDs from group_list format

The system SHALL correctly extract team IDs from `user.group_list` which has format `[{"id": 1, "name": "...", "parent_id": 0}, ...]`.

#### Scenario: Parse group_list with multiple teams
- **WHEN** user has `group_list = [{"id": 1, "name": "A"}, {"id": 3, "name": "B"}]`
- **THEN** system SHALL recognize `1` and `3` as valid `current_team` values

#### Scenario: Handle empty group_list
- **WHEN** user has `group_list = []` and is not superuser
- **THEN** system SHALL raise `PermissionDenied` for any `current_team` value

## Work Checklist

## 1. 添加依赖导入

- [x] 1.1 在 `server/apps/core/utils/viewset_utils.py` 中添加 `from rest_framework.exceptions import PermissionDenied` 导入

## 2. 实现 AuthViewSet 验证逻辑

- [x] 2.1 在 `GenericViewSetFun.filter_by_group()` 方法中，`current_team = cls._parse_current_team_cookie(request)` 之后添加验证逻辑
- [x] 2.2 验证逻辑：如果 `user.is_superuser` 为 False，则检查 `current_team` 是否在 `user.group_list` 的 id 集合中
- [x] 2.3 验证失败时抛出 `PermissionDenied("无权访问该团队")`
- [x] 2.4 在 `AuthViewSet` 中添加 `_validate_current_team_permission()` 方法，供子类调用

## 3. opspilot 模块权限修复

- [x] 3.1 创建 `server/apps/opspilot/utils/team_permission_mixin.py` - TeamPermissionMixin
- [x] 3.2 创建 `server/apps/opspilot/utils/vendor_model_mixin.py` - VendorModelMixin
- [x] 3.3 修改 KnowledgeBaseViewSet, KnowledgeDocumentViewSet 添加 current_team 验证
- [x] 3.4 修改 FileKnowledgeViewSet, ManualKnowledgeViewSet, WebPageKnowledgeViewSet 添加 current_team 验证
- [x] 3.5 修改 QAPairsViewSet, KnowledgeGraphViewSet, HistoryViewSet 添加 current_team 验证
- [x] 3.6 修改 BotViewSet, LLMViewSet 添加 current_team 验证
- [x] 3.7 修改 ChatApplicationViewSet, WorkFlowTaskResultViewSet 添加 current_team 验证
- [x] 3.8 修改 EmbedProviderViewSet, RerankProviderViewSet, OCRProviderViewSet, ModelVendorViewSet 添加 current_team 验证

## 4. opspilot 模块添加 @HasPermission 装饰器

- [x] 4.1 WorkFlowTaskResultViewSet 添加 `@HasPermission("bot_conversation_log-View")`
- [x] 4.2 ChatApplicationViewSet 添加 `@HasPermission("bot_list-View")`
- [x] 4.3 BotViewSet list/retrieve 添加 `@HasPermission("bot_list-View")`
- [x] 4.4 ModelVendorViewSet 添加 `@HasPermission("provide_list-View/Add/Setting/Delete")`

## 5. system_mgmt 模块权限修复

- [x] 5.1 在 `server/apps/system_mgmt/utils/group_filter_mixin.py` 添加 GroupPermissionMixin
- [x] 5.2 修改 ChannelViewSet 添加 @HasPermission + 组权限验证
- [x] 5.3 修改 UserViewSet 添加用户过滤和目标用户权限验证
- [x] 5.4 修改 GroupViewSet 添加组权限验证 (get_detail, get_group_detail_with_roles)
- [x] 5.5 修改 GroupDataRuleViewSet 添加组权限验证

## 6. 验证

- [x] 6.1 运行 flake8 检查所有修改文件语法正确
- [x] 6.2 手动验证：opspilot API - 未授权团队返回 403，已授权团队返回 200
- [x] 6.3 手动验证：system_mgmt API - 未授权组返回 403，已授权组返回 200
