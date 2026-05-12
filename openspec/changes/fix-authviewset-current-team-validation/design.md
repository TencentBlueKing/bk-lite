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

**Non-Goals:**
- 不修改其他使用 `current_team` 的地方（如 `GroupFilterMixin`、`monitor/views` 等），这些将在后续阶段处理
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

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 前端可能依赖当前（不安全）行为 | 前端应该只设置用户有权限的 team，此修复不影响正常使用 |
| `group_list` 为空时所有请求都会 403 | 这是正确行为，没有团队权限的用户不应访问任何数据 |
| 性能影响 | 验证逻辑是 O(n) 的集合查找，n 为用户所属团队数，通常很小，可忽略 |
