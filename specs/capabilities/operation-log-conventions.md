## ADDED Requirements

### Requirement: 操作日志工具函数
所有用户操作日志 SHALL 使用统一的 `log_operation` 工具函数记录。

#### Scenario: 导入方式
- **WHEN** 需要记录操作日志
- **THEN** SHALL 从 `apps.system_mgmt.utils.operation_log_utils` 导入 `log_operation`

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation
```

### Requirement: 函数签名
`log_operation` 函数 SHALL 接受以下参数。

#### Scenario: 参数定义
- **GIVEN** `log_operation(request, action_type, app, summary)`
- **THEN** `request` SHALL 为 Django request 对象
- **AND** `action_type` SHALL 为操作类型字符串
- **AND** `app` SHALL 为应用模块标识字符串
- **AND** `summary` SHALL 为中文操作概要描述

### Requirement: app 参数值规范
每个 app 模块 SHALL 使用固定的 `app` 参数值。

#### Scenario: system_mgmt 模块
- **WHEN** 在 `apps/system_mgmt/` 下记录操作日志
- **THEN** `app` 参数 SHALL 为 `"system-manager"`

#### Scenario: job_mgmt 模块
- **WHEN** 在 `apps/job_mgmt/` 下记录操作日志
- **THEN** `app` 参数 SHALL 为 `"job"`

#### Scenario: opspilot 模块
- **WHEN** 在 `apps/opspilot/` 下记录操作日志
- **THEN** `app` 参数 SHALL 为 `"opspilot"`

### Requirement: action_type 取值规范
`action_type` 参数 SHALL 使用以下标准值。

#### Scenario: 创建操作
- **WHEN** 新增资源（用户、角色、作业、机器人等）
- **THEN** `action_type` SHALL 为 `"create"`

#### Scenario: 更新操作
- **WHEN** 编辑/修改资源
- **THEN** `action_type` SHALL 为 `"update"`

#### Scenario: 删除操作
- **WHEN** 删除资源
- **THEN** `action_type` SHALL 为 `"delete"`

#### Scenario: 执行操作
- **WHEN** 执行动作（启用、同步、运行、发布等）
- **THEN** `action_type` SHALL 为 `"execute"`

### Requirement: summary 格式规范
`summary` 参数 SHALL 使用中文描述，格式为 `"动作 + 资源类型: 资源名称"`。

#### Scenario: 单个资源操作
- **WHEN** 操作单个资源
- **THEN** summary SHALL 格式为 `"新增用户: {username}"` 或 `"删除作业: {job_name}"`

#### Scenario: 批量操作
- **WHEN** 批量操作多个资源
- **THEN** summary SHALL 包含数量信息，如 `"批量删除用户: user1, user2 (共2个)"`

### Requirement: 日志记录时机
操作日志 SHALL 在操作成功后记录。

#### Scenario: ViewSet 中的记录时机
- **WHEN** 在 ViewSet 的 create/update/destroy 方法中
- **THEN** SHALL 在 `super()` 调用成功后、返回响应前记录日志

```python
def create(self, request, *args, **kwargs):
    response = super().create(request, *args, **kwargs)
    if response.status_code == 201:
        log_operation(request, "create", "job", f"新增作业: {job_name}")
    return response
```

#### Scenario: 自定义 action 中的记录时机
- **WHEN** 在自定义 action 方法中
- **THEN** SHALL 在业务逻辑执行成功后、返回响应前记录日志

### Requirement: 异常处理
日志记录失败 SHALL NOT 影响主业务流程。

#### Scenario: 日志记录异常
- **WHEN** `log_operation` 内部发生异常
- **THEN** SHALL 捕获异常并记录错误日志，但不抛出异常
- **AND** 主业务流程 SHALL 继续正常执行

## 使用示例

### system_mgmt 示例

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 创建
log_operation(request, "create", "system-manager", f"新增用户: {username}")

# 更新
log_operation(request, "update", "system-manager", f"编辑角色: {role_name}")

# 删除
log_operation(request, "delete", "system-manager", f"删除组织: {group_name}")

# 执行
log_operation(request, "execute", "system-manager", f"开启认证源: {module_name}")
```

### job_mgmt 示例

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 创建
log_operation(request, "create", "job", f"新增作业: {job_name}")

# 更新
log_operation(request, "update", "job", f"编辑作业: {job_name}")

# 删除
log_operation(request, "delete", "job", f"删除作业: {job_name}")

# 执行
log_operation(request, "execute", "job", f"执行作业: {job_name}")
```

### opspilot 示例

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 创建
log_operation(request, "create", "opspilot", f"新增机器人: {bot_name}")

# 更新
log_operation(request, "update", "opspilot", f"编辑知识库: {kb_name}")

# 删除
log_operation(request, "delete", "opspilot", f"删除技能: {skill_name}")

# 执行
log_operation(request, "execute", "opspilot", f"发布机器人: {bot_name}")
```
