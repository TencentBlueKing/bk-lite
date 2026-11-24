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

### Requirement: 读出与导出
列表、详情和导出 SHALL 使用写入时保存的结果、对象名称和变更，不把空结果展示成成功。

#### Scenario: 列表
- **WHEN** 展示操作日志列表
- **THEN** 列 SHALL 为操作时间、操作者、来源 IP、应用名称、操作类型、操作对象、执行结果、操作详情
- **AND** 应用名称 SHALL 使用控制台显示名，对不上时回退应用 ID
- **AND** 操作对象 SHALL 展示写入时的 `target_name`
- **AND** 空的对象类型、对象名称、对象 ID 和执行结果 SHALL 显示「未记录」

#### Scenario: 筛选
- **WHEN** 查询操作日志
- **THEN** SHALL 支持操作者、对象名称或对象 ID、应用、操作类型、执行结果、时间，并可组合
- **AND** 对象条件 SHALL 对 `target_name` 或 `target_id` 做包含匹配
- **AND** 执行结果 SHALL 取 `success`、`failure`、`accepted` 或未记录（空字符串）

#### Scenario: 详情
- **WHEN** 打开一条操作日志的详情
- **THEN** SHALL 展示基本信息（操作者、时间、应用名称、来源 IP）、操作对象（类型、名称、ID）、执行结果（结果、失败原因）、变更内容
- **AND** 变更内容 SHALL 只使用 `detail.before_data` 与 `detail.after_data` 中已生效的数据
- **AND** 修改 SHALL 只突出变化字段。创建展示创建后的数据，删除展示删除前的数据
- **AND** 没有这两份已生效数据时 MUST NOT 把提交值展示为修改后
- **AND** `outcome` 为 `accepted` 时 SHALL 提示这只表示已提交，不表示任务执行成功

#### Scenario: 失败原因为空
- **WHEN** `outcome` 为 `failure` 且 `failure_reason` 为空
- **THEN** 详情和导出的失败原因 SHALL 写「未记录」
- **WHEN** `outcome` 为 `success`、`accepted` 或未记录，且 `failure_reason` 为空
- **THEN** 详情和导出的失败原因 SHALL 写 `-`
- **AND** MUST NOT 写成「未记录」

#### Scenario: 导出列
- **WHEN** 导出操作日志
- **THEN** 列 SHALL 为用户名、域名、操作时间、源 IP 地址、应用、操作类型、概要描述、对象类型、对象名称、对象 ID、执行结果、失败原因
- **AND** 敏感字段 SHALL 使用与列表相同的脱敏结果

#### Scenario: 其他模块尚未补结果
- **WHEN** 调用方未传 `outcome`
- **THEN** 列表执行结果 SHALL 显示「未记录」
- **AND** 系统管理中已生效、已提交或需要留下失败记录的调用 SHALL 传入 `outcome`
- **AND** 其他模块的调用点以后再补，不在同一次改动里铺开

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

系统管理里已经生效、已经提交或需要留下失败记录的调用，带上对象快照和 `outcome`。成功和提交成功不传 `failure_reason`。

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 已生效
log_operation(
    request,
    "create",
    "system-manager",
    f"新增用户: {username} ({display_name})",
    target_type="user",
    target_id=user_id,
    target_name=username,
    outcome="success",
)

log_operation(
    request,
    "update",
    "system-manager",
    f"更新角色名称: {role_name}",
    target_type="role",
    target_id=role_id,
    target_name=role_name,
    outcome="success",
)

log_operation(
    request,
    "delete",
    "system-manager",
    f"删除角色: {role_name}",
    target_type="role",
    target_id=role_id,
    target_name=role_name,
    outcome="success",
)

# 请求已受理，任务尚未执行完
log_operation(
    request,
    "execute",
    "system-manager",
    f"开启认证源: {module_name}",
    target_type="login_module",
    target_id=module_id,
    target_name=module_name,
    outcome="accepted",
)

# 未生效，且需要留下失败记录。failure_reason 用返回给用户的原因
log_operation(
    request,
    "execute",
    "system-manager",
    f"测试集成实例连接: {instance_name}",
    target_type="integration_instance",
    target_id=instance_id,
    target_name=instance_name,
    outcome="failure",
    failure_reason=reason,
)
```

### job_mgmt 示例

作业模块的调用点尚未补 `outcome` 和对象快照。不传 `outcome` 仍会写入，结果为空，表示未记录。

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

log_operation(request, "create", "job", f"新增作业: {job_name}")

log_operation(request, "update", "job", f"编辑作业: {job_name}")

log_operation(request, "delete", "job", f"删除作业: {job_name}")

log_operation(request, "execute", "job", f"执行作业: {job_name}")
```

### opspilot 示例

运维助手的调用点同样尚未补 `outcome` 和对象快照。不传 `outcome` 仍会写入，结果为空，表示未记录。

```python
from apps.system_mgmt.utils.operation_log_utils import log_operation

log_operation(request, "create", "opspilot", f"新增机器人: {bot_name}")

log_operation(request, "update", "opspilot", f"编辑知识库: {kb_name}")

log_operation(request, "delete", "opspilot", f"删除技能: {skill_name}")

log_operation(request, "execute", "opspilot", f"发布机器人: {bot_name}")
```
