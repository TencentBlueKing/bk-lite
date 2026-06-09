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
