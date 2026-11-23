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
- **GIVEN** `log_operation(request, action_type, app, summary, *, target_type="", target_id="", target_name="", detail=None, outcome="", failure_reason="")`
- **THEN** `request` SHALL 为 Django request 对象
- **AND** `action_type` SHALL 为操作类型字符串
- **AND** `app` SHALL 为应用模块标识字符串
- **AND** `summary` SHALL 为中文操作概要描述
- **AND** `target_type` / `target_id` / `target_name` / `detail` / `outcome` / `failure_reason` SHALL 均为可选
- **AND** 现有调用方不传新参数时 SHALL 仍能写入，且 `outcome` 存空字符串（未记录）

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

### Requirement: outcome 取值规范
操作日志 SHALL 可以记录成功、失败和提交成功。未传 `outcome` 表示未记录。

#### Scenario: 成功
- **WHEN** 操作已生效
- **THEN** `outcome` SHALL 为 `"success"`

#### Scenario: 失败
- **WHEN** 操作未生效并需要留下失败记录
- **THEN** `outcome` SHALL 为 `"failure"`
- **AND** `failure_reason` SHALL 为返回给用户的失败原因
- **AND** 成功与提交成功时 `failure_reason` SHALL 为空字符串

#### Scenario: 提交成功
- **WHEN** 请求已受理但任务尚未执行完毕
- **THEN** `outcome` SHALL 为 `"accepted"`
- **AND** 这只表示已提交，不表示任务执行成功

#### Scenario: 未记录
- **WHEN** 调用方未传 `outcome`，或传入值不是 `success` / `failure` / `accepted`
- **THEN** `outcome` SHALL 存空字符串
- **AND** MUST NOT 把默认值写成成功
- **AND** 读取侧 MUST NOT 把空结果展示成成功

#### Scenario: 失败与成功分两行
- **WHEN** 一次失败之后再次成功
- **THEN** SHALL 写成两行
- **AND** MUST NOT 用幂等键把失败改写成成功

### Requirement: target_name
`target_name` SHALL 记录操作发生时的对象名称，不事后回查。

#### Scenario: 写入时快照
- **WHEN** 写入操作日志
- **THEN** `target_name` SHALL 使用调用方传入的当时名称
- **AND** 空字符串表示未记录

### Requirement: 变更内容
变更 SHALL 放在 `detail.before_data` 和 `detail.after_data`。没有这两份已生效数据，就不算有变更。

#### Scenario: 不推断变更
- **WHEN** 写入或展示变更
- **THEN** MUST NOT 从 `summary` 或请求体推断变更
- **AND** MUST NOT 把 `action_type=execute` 自动标成提交成功
- **AND** MUST NOT 采集任务最终结果或关联错误日志

### Requirement: summary 格式规范
`summary` 参数 SHALL 使用中文描述，格式为 `"动作 + 资源类型: 资源名称"`。

#### Scenario: 单个资源操作
- **WHEN** 操作单个资源
- **THEN** summary SHALL 格式为 `"新增用户: {username}"` 或 `"删除作业: {job_name}"`

#### Scenario: 批量操作
- **WHEN** 批量操作多个资源
- **THEN** summary SHALL 包含数量信息，如 `"批量删除用户: user1, user2 (共2个)"`

### Requirement: 脱敏
写入前 SHALL 递归处理 `detail`。读取、列表和导出 SHALL 使用同一函数脱敏，避免旧数据明文流出。

#### Scenario: 敏感字段
- **WHEN** 字段名不区分大小写，命中 `password`、`token`、`secret`、`otp`、`access_key`、`private_key`
- **THEN** 值 SHALL 改为「已修改」
- **AND** 原值 MUST NOT 入库

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
