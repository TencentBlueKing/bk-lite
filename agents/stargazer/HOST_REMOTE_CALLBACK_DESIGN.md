# Host Remote callback（无状态运行时）

Host 监控与配置采集共用 `CollectionRuntime`。目标通过 TCP 预检并完成凭据选择后，
`MonitorCollectionPlugin` 向 Remote Node 提交任务并返回 `Deferred`，不占用目标并发等待回调。

```text
HTTP X-Task-ID
  -> CollectionRuntime / RunLease(fence)
  -> TargetCollection(host + credential)
  -> HostCollector.submit_collection(callback identity)
  -> Redis callback context
  -> NATS callback
  -> validate parent task + target + fence
  -> Sanic local callback task
  -> publish metrics / retry state
```

每个目标的 callback task ID 由父任务、插件、目标和 fencing token 确定性摘要得到，因此一个
多目标运行不会互相覆盖 callback 上下文。Redis 上下文保存：

- callback task ID 与父 `collection_task_id`；
- 目标、插件、owner 和 fencing token；
- Remote 原始结果、执行/发布状态、重试次数和截止时间；
- 发布所需的非秘密参数。

回调必须同时匹配父任务 ID、目标和 fencing token，校验失败时不会登记 payload 或启动处理。
重复或待重试处理由进程内有名 Task 登记表去重；callback sweeper 在 Sanic 运行期扫描 Redis
短期状态并重新触发发布。该 Task 登记表只管理生命周期，不是持久队列。

Pod 退出时 callback Task 会被取消，Redis 上下文保留到 TTL；NATS 重投或 sweeper 可在新 Pod
继续处理。发布成功后删除上下文。Redis 或 NATS 故障不会通过延长启动等待、无限重试或恢复
ARQ Worker 来掩盖。
