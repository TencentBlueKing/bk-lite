# Host Remote callback（无状态运行时）

Host 监控与配置采集共用 `CollectionRuntime`。目标通过 TCP 预检并完成凭据选择后，
`MonitorCollectionPlugin` 向 Remote Node 提交任务并返回 `Deferred`，不占用目标并发等待回调。

```text
HTTP X-Task-ID
  -> CollectionRuntime / RunLease(fence + attempt_id + owner)
  -> TargetCollection(host + credential)
  -> HostCollector.submit_collection(v2 callback.context + one-time token)
  -> Redis callback context + latest-run tombstone + current-generation pointer
  -> NATS callback
  -> validate token + task + target + fence + attempt + owner + caller
  -> Sanic local callback task
  -> publish metrics / retry state
```

启用 v2 后，每个目标的 callback task ID 由父任务、插件、目标、fencing token 和真实 `attempt_id`
确定性摘要得到，因此一个多目标运行或新一轮租约不会互相覆盖 callback 上下文。Redis 上下文
通过 Lua 在仍持有当前 run 的前提下，同时写入有界 TTL 的 parent-task generation 指针并原子保留
首次 callback context；同 task 重投复用原 token，身份冲突时在提交 Executor 前失败关闭。薄 run
租约可在返回 `Deferred` 后删除，generation 指针继续覆盖 callback 生命周期；每次 run acquire 还会
在同一 Lua 中推进有界保留的 latest-run tombstone，因此新 attempt 即使在创建首个 callback context
前结束，旧回调也不会重新变为有效。上下文保存：

- callback task ID 与父 `collection_task_id`；
- v2 协议版本与 token 摘要；token 由独立环境密钥和不可变执行身份确定性 HMAC 派生，不写 Redis；
- 目标、插件、owner、fencing token、真实 `attempt_id` 和 Executor caller；
- Remote 原始结果、执行/发布状态、重试次数和截止时间；
- 发布所需的非秘密参数。

回调必须同时匹配一次性 token、父任务 ID、目标、fencing token、`attempt_id`、owner 和 caller；
随后通过单个 Lua 快照读取 generation、latest-run tombstone 与 active run：run 已因同一 Deferred
完成而删除时仍核对 latest-run；若 run 存在则三者都必须与回调的 fence、attempt、owner 一致。
callback payload 的首次落库会在另一个 Lua 中再次原子核对这三层身份，关闭“校验返回后新 run
acquire”的竞态。任一校验失败时不会登记 payload、清 running 标记或启动处理。Executor 只在
加密的 `callback_secret` 中持久化 token，查询态、JetStream 重试消息与 DLQ 使用遮蔽值；Redis
始终只保存 token 摘要，首次合法 callback 落库时也会从 raw payload 中剥离 token。

提交被明确拒绝时不立即删除共享 callback context：并发重投可能已经被 Executor 接受，删除会让
合法回调永久失去凭据。该短期状态继续受默认 1 小时 TTL 和 300 秒 pre-accept sweeper 约束，
不会无限保留。
重复或待重试处理由进程内有名 Task 登记表去重；callback sweeper 在 Sanic 运行期扫描 Redis
短期状态并重新触发发布。该 Task 登记表只管理生命周期，不是持久队列。

Pod 退出时 callback Task 会被取消，Redis 上下文保留到 TTL；NATS 重投或 sweeper 可在新 Pod
继续处理。发布成功后删除上下文。Redis 或 NATS 故障不会通过延长启动等待、无限重试或恢复
ARQ Worker 来掩盖。

滚动升级期间 `HOST_REMOTE_CALLBACK_V2_ENABLED` 默认关闭，继续签发旧 `remote-` 任务；先滚动升级
Executor 并确认旧版本、旧 context 与 callback retry 清零，再配置至少 32 字符的独立
`HOST_REMOTE_CALLBACK_TOKEN_SECRET` 并启用 v2。新 handler 仅对旧前缀、无 v2 标记且未超过
context TTL/deadline 的在途记录保留兼容。`HOST_REMOTE_CALLBACK_LEGACY_MAX_AGE_SECONDS` 默认等于
context TTL，可在排空后设为 0。回滚前先关闭 v2 新签发，并排空 v2 context、执行任务与 Executor
retry；若不能排空，必须保留能处理 v2 的 Stargazer handler，不能直接回退到 fixed-base handler。

当前 v2 token 能阻断只知道或猜到 task ID 的盲伪造，但不是最终 NATS 信任根。默认管理员仍可
订阅任务请求并观察 token；完整关闭该风险仍需为 Stargazer/Executor 建立独立服务身份与最小
subject ACL，或采用预置独立私钥的 Executor 签名。该治理完成前 Issue #4280 保持开放。
