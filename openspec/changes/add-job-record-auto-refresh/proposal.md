## Why

作业详情页面 (`/job/execution/job-record?id=xxx`) 当前只在初始加载时获取一次数据，当任务处于 `pending` 或 `running` 状态时，用户必须手动刷新浏览器才能看到最新状态。这导致用户体验差，无法实时跟踪任务执行进度。

代码库中已有成熟的轮询模式（如 `mlops/TrainTaskDetail` 和 `opspilot/task-progress`），应复用这些模式为作业详情页添加自动刷新功能。

## What Changes

- 当作业状态为 `pending` 或 `running` 时，自动每 5-10 秒轮询一次 `getJobRecordDetail` API
- 当状态变为终态（`success`、`failed`、`canceled`）时自动停止轮询
- 页面卸载或切换到列表视图时清理定时器，避免内存泄漏
- 可选：在详情页头部显示"自动刷新中"状态指示器

## Capabilities

### New Capabilities

- `job-record-auto-refresh`: 作业详情页在任务进行中时自动轮询刷新状态

### Modified Capabilities

<!-- 无需修改现有 spec，这是纯前端增强 -->

## Impact

- **前端代码**: `web/src/app/job/(pages)/execution/job-record/page.tsx`
- **API**: 无变更，复用现有 `getJobRecordDetail` 接口
- **依赖**: 无新增依赖，使用原生 `setInterval` + React hooks
- **性能**: 每 5-10 秒一次 API 调用（仅在任务进行中），对后端影响可忽略
