## ADDED Requirements

### Requirement: 进行中任务自动刷新

当用户查看作业详情页且任务状态为 `pending` 或 `running` 时，系统 SHALL 每 5 秒自动刷新任务详情。

#### Scenario: 任务执行中自动刷新
- **WHEN** 用户打开状态为 `running` 的作业详情页
- **THEN** 系统每 5 秒自动调用 `getJobRecordDetail` API 刷新页面数据

#### Scenario: 任务等待中自动刷新
- **WHEN** 用户打开状态为 `pending` 的作业详情页
- **THEN** 系统每 5 秒自动调用 `getJobRecordDetail` API 刷新页面数据

### Requirement: 任务完成后停止刷新

当任务状态变为终态（`success`、`failed`、`canceled`）时，系统 SHALL 自动停止轮询。

#### Scenario: 任务成功后停止刷新
- **WHEN** 轮询返回的任务状态为 `success`
- **THEN** 系统停止自动刷新，不再发起新的 API 请求

#### Scenario: 任务失败后停止刷新
- **WHEN** 轮询返回的任务状态为 `failed`
- **THEN** 系统停止自动刷新，不再发起新的 API 请求

#### Scenario: 任务取消后停止刷新
- **WHEN** 轮询返回的任务状态为 `canceled`
- **THEN** 系统停止自动刷新，不再发起新的 API 请求

### Requirement: 页面离开时清理定时器

当用户离开作业详情页时，系统 SHALL 清理轮询定时器，避免内存泄漏。

#### Scenario: 返回列表页时清理
- **WHEN** 用户点击返回按钮回到作业记录列表
- **THEN** 系统清理轮询定时器，停止所有后台 API 请求

#### Scenario: 切换到其他页面时清理
- **WHEN** 用户通过导航切换到其他页面
- **THEN** 系统清理轮询定时器，停止所有后台 API 请求

#### Scenario: 关闭浏览器标签时清理
- **WHEN** 用户关闭浏览器标签页
- **THEN** 系统清理轮询定时器（通过 React useEffect cleanup）
