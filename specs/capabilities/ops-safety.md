# ops-safety Specification

## Purpose
TBD - created by archiving change react-loop-enhancements. Update Purpose after archive.
## Requirements
### Requirement: 人工审批机制
系统 SHALL 支持 LLM 自主判断高风险操作并请求人工审批。

#### Scenario: LLM 调用 request_human_approval 工具
- **WHEN** LLM 判断当前操作需要人工确认
- **THEN** LLM SHALL 调用 request_human_approval 工具，传入操作描述和风险说明

#### Scenario: 审批请求 SSE 事件
- **WHEN** request_human_approval 工具被调用
- **THEN** 系统 SHALL 发送 approval_request SSE 事件到前端

#### Scenario: Redis 轮询等待审批
- **WHEN** 审批请求发出后
- **THEN** 系统 SHALL 通过 Redis 轮询等待用户审批结果

#### Scenario: 审批通过继续执行
- **WHEN** 用户批准操作
- **THEN** 系统 SHALL 继续执行原计划的操作

#### Scenario: 审批拒绝终止操作
- **WHEN** 用户拒绝操作
- **THEN** 系统 SHALL 终止当前操作并通知 LLM 寻找替代方案

#### Scenario: 审批超时处理
- **WHEN** 审批请求超过配置的超时时间（默认 5 分钟）
- **THEN** 系统 SHALL 自动拒绝并记录日志

#### Scenario: 前端 ApprovalCard 展示
- **WHEN** 前端收到 approval_request 事件
- **THEN** ApprovalCard 组件 SHALL 内联展示审批卡片，包含倒计时

### Requirement: 执行后验证
系统 SHALL 支持变更类操作执行后自动触发验证。

#### Scenario: verification_started 事件
- **WHEN** 变更操作执行完成，开始验证
- **THEN** 系统 SHALL 发送 verification_started SSE 事件

#### Scenario: verification_completed 事件
- **WHEN** 验证完成
- **THEN** 系统 SHALL 发送 verification_completed SSE 事件，包含验证结果

#### Scenario: 验证失败触发回滚
- **WHEN** 验证结果显示操作未生效
- **THEN** 系统 SHALL 提示 LLM 考虑回滚或重试

### Requirement: 回滚能力
系统 SHALL 支持变更类操作的回滚。

#### Scenario: rollback_started 事件
- **WHEN** 开始执行回滚操作
- **THEN** 系统 SHALL 发送 rollback_started SSE 事件

#### Scenario: rollback_completed 事件
- **WHEN** 回滚完成
- **THEN** 系统 SHALL 发送 rollback_completed SSE 事件，包含回滚结果

### Requirement: 取消与优雅终止
系统 SHALL 支持用户中途取消正在执行的 Agent 任务。

#### Scenario: 用户发起取消
- **WHEN** 用户点击取消按钮
- **THEN** 系统 SHALL 设置 abort signal，Agent 在下一个检查点优雅退出

#### Scenario: 取消后返回中间结果
- **WHEN** Agent 收到取消信号
- **THEN** 系统 SHALL 返回当前已完成的中间结果，而非空结果

### Requirement: 超时熔断
系统 SHALL 支持单步超时和总时间限制。

#### Scenario: 单步超时
- **WHEN** 单个工具执行时间超过 TimeoutConfig.step_timeout
- **THEN** 系统 SHALL 终止该工具执行并返回超时错误

#### Scenario: 总时间限制
- **WHEN** Agent 总执行时间超过 TimeoutConfig.total_timeout
- **THEN** 系统 SHALL 优雅终止 Agent 并返回当前结果

### Requirement: 步骤级进度汇报
系统 SHALL 支持结构化的步骤级进度汇报。

#### Scenario: agent_step_progress 事件格式
- **WHEN** Agent 完成一个步骤
- **THEN** 系统 SHALL 发送 agent_step_progress 事件，包含 step_number、total_steps（如已知）、description

#### Scenario: 前端进度展示
- **WHEN** 前端收到 agent_step_progress 事件
- **THEN** 前端 SHALL 展示 "第 N 步：正在执行 XXX" 格式的进度信息
