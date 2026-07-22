# 2026 06 05 Add Job Record Auto Refresh

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-job-record-auto-refresh/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

作业详情页 (`web/src/app/job/(pages)/execution/job-record/page.tsx`) 当前只在初始加载时调用 `fetchDetail()`，没有轮询机制。代码库中已有成熟的轮询模式：

- `mlops/TrainTaskDetail.tsx`: 使用 `pollingTimerRef` + `setInterval`，仅在 `status === 'RUNNING'` 时轮询
- `opspilot/task-progress/index.tsx`: 使用 `setInterval(fetchTasks, 10000)` 无条件轮询

作业状态类型定义在 `web/src/app/job/types/index.ts`:
```typescript
export type JobRecordStatus = 'pending' | 'running' | 'success' | 'failed' | 'canceled';
```

## Goals / Non-Goals

**Goals:**
- 当作业状态为 `pending` 或 `running` 时，自动轮询刷新详情
- 状态变为终态时自动停止轮询
- 页面卸载时正确清理定时器
- 复用代码库已有的轮询模式

**Non-Goals:**
- 不实现 WebSocket/SSE 实时推送（当前架构不支持）
- 不修改后端 API
- 不添加用户可配置的刷新间隔（保持简单）

## Decisions

### Decision 1: 轮询间隔选择 5 秒

**选择**: 5 秒固定间隔

**备选方案**:
- 10 秒间隔：响应太慢，用户体验差
- 3 秒间隔：API 调用过于频繁
- 指数退避：增加复杂度，收益不明显

**理由**: 5 秒是响应速度和服务器负载的平衡点，与 `mlops` 模块的 10 秒相比更适合作业执行这种用户关注度高的场景。

### Decision 2: 使用 useRef + setInterval 模式

**选择**: 复用 `mlops/TrainTaskDetail.tsx` 的模式

```typescript
const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

useEffect(() => {
  // 只在进行中状态时启动轮询
  if (detail?.status !== 'pending' && detail?.status !== 'running') {
    return;
  }

  pollingTimerRef.current = setInterval(() => {
    fetchDetail(Number(recordId));
  }, 5000);

  return () => {
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
    }
  };
}, [detail?.status, recordId]);
```

**备选方案**:
- SWR `refreshInterval`: 需要引入新依赖，当前项目未使用 SWR
- React Query `refetchInterval`: 同上，需要引入新依赖

**理由**: 保持与现有代码库一致，无需引入新依赖。

### Decision 3: 状态检查逻辑

**选择**: 在 `useEffect` 依赖中包含 `detail?.status`

当 `fetchDetail` 返回新状态后，`detail.status` 变化会触发 `useEffect` 重新执行：
- 如果新状态仍是 `pending`/`running`，继续轮询
- 如果新状态是终态，`useEffect` 提前返回，不启动新定时器

**理由**: 利用 React 的响应式机制自动处理状态转换，无需手动判断。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 用户打开多个详情页标签，造成 API 压力 | 5 秒间隔已足够保守；可考虑未来添加 `visibilitychange` 监听，页面不可见时暂停轮询 |
| 网络请求失败时持续重试 | 当前 `fetchDetail` 已有 try/finally，失败不会阻塞下次轮询；可考虑添加连续失败计数器 |
| 定时器未正确清理导致内存泄漏 | 使用 `useEffect` cleanup 函数确保清理 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-26
```

## Capability Deltas

### job-record-auto-refresh

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

## Work Checklist

## 1. 添加轮询逻辑

- [x] 1.1 在 `page.tsx` 中添加 `pollingTimerRef` 引用
- [x] 1.2 添加轮询 `useEffect`，当 `detail?.status` 为 `pending` 或 `running` 时启动 5 秒间隔轮询
- [x] 1.3 在 `useEffect` cleanup 中清理定时器

## 2. 验证

- [x] 2.1 手动测试：打开进行中的任务详情页，确认每 5 秒刷新一次
- [x] 2.2 手动测试：等待任务完成，确认轮询自动停止
- [x] 2.3 手动测试：点击返回按钮，确认无控制台错误（定时器已清理）
- [x] 2.4 运行 `pnpm lint && pnpm type-check` 确保无类型错误
