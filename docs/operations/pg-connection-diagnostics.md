# PG 连接不回落：临时诊断日志

## 启用与撤回

此功能只观测 ASGI Web 进程，不改变连接关闭策略、事务、SQL 或响应协议。
默认关闭。需要包含 `apps/core/db_diagnostics.py` 的后端版本。

1. 在实际运行后端的环境中设置 `DB_CONNECTION_DIAGNOSTICS=true`，按正常发布流程重启对应 Web 进程。
2. 保持 `LOG_LEVEL=INFO`，采集 `app` logger 的现有输出。默认在控制台；启用
   `LOG_FILE_OUTPUT=true` 时同时进入现有应用日志文件。无需打开 `django.db.backends` 的 SQL DEBUG。
3. 先在测试环境验证，再在批准的诊断窗口重现一次。采集所有相关容器/worker 的日志，保留容器身份、镜像提交、时间与时区。
4. 同时由 DBA 采集 PG 会话的 `pid`、`backend_start`、`state`、`state_change`、
   `xact_start`、`wait_event_type`、`wait_event`、`client_addr`、`application_name`。
   不需要导出 SQL 正文、凭据或业务 payload。记录触发前、请求停止后及几分钟后的快照。
5. 结束后移除 `DB_CONNECTION_DIAGNOSTICS` 或设置为 `false`，再按发布流程重启。

启用时每个请求有开始/结束日志，每条被观测连接有建连/请求结束快照；单请求最多保留
64 条连接观测，超过时 `dropped_connections` 计数。不会为历史连接建立全局保活表。
这不是常驻监控：请求洪流会增加日志与取调用栈的开销，应限制诊断时长并使用已有日志轮转/容量告警。

## 如何关联

从 PG 残留会话的 `pid` 查 `pg_pid`，再以 `request_id` 查整条请求：

```bash
rg 'event=db_connection_.*pg_pid=12345( |$)' backend.log
rg 'request_id=<上一步的请求ID>' backend.log
```

- `pg_pid`：驱动已知的 PG 后端 PID，读取它不会增加 SQL。需结合数据库实例、时间和
  `backend_start`，避免重启/PID 复用误关联。此关联面向直连 PG，不能直接套用事务池代理。
- `worker_pid` / `owner_thread`：应用进程和建连线程；不是 PG 进程/线程。跨容器还需日志采集器的容器身份。
- `connection_id`：本次连接观测 ID；同一连接在别的请求被再次观察会有新的 ID。
- `request_id`：服务端生成，不信任客户端传入值；同时设置到 request，方便关联现有鉴权失败日志。
- `callsite`：有限的文件名、行号和函数名，用于定位谁触发了建连，不包含源代码、locals 或 SQL。
- `route`：Django 已匹配的静态路由模板；不记录实际 URL、查询参数、header、cookie 或请求/响应正文。
  鉴权提前返回、读请求体失败等场景可能是 `-`，可通过 request_id 对照现有鉴权日志。
  `path_hash` 是实际 path 的单向指纹，仅帮助判断同一路径，不能还原 URL。

## 判读表

| 日志现象 | 结论与下一步 |
| --- | --- |
| 有 `db_request_begin` / `db_connection_observed`，没有对应 `db_request_end` | 请求可能仍在执行、等待或流式输出；也可能进程退出、日志丢失。结合 worker 存活、请求耗时和 PG 等待事件，不先认定泄漏。 |
| `state=open cleanup_seen=False`，请求已经结束 | 该被观测连接当时仍开着，建连线程没有被本诊断观察到 `request_finished`。重点检查旁路线程与响应生成前取消；用 callsite 定位调用方。它不是“从未调用任何清理函数”的证明。 |
| `failed_stage=application error_type=CancelledError response_closed=False` | 响应生成前取消；不属于只修补 `send_response` 异常的覆盖范围，应对照该请求的连接快照继续定位。 |
| `failed_stage=send_response`、`cleanup_fallback=True` | 发送阶段异常/取消触发定向补清理；看 `cleanup_state`、`state` 是否关闭，而非只看抛出的异常。 |
| `failed_stage=response_close` | 最后一个响应 body 的 send 已返回，失败发生于后续清理阶段；结合 `asgi_cleanup_failed`。这不保证客户端实际收到完整响应。 |
| `cleanup_seen=True cleanup_state=open conn_max_age=60` 等非零策略 | 清理信号到了，但健康持久连接可能按配置保留；需要看剩余生命周期和后续请求，不能直接当泄漏。 |
| `cleanup_seen=True cleanup_state=open conn_max_age=0` | 异常线索；检查 `in_atomic`、`autocommit`、自定义连接后端、信号顺序，以及清理异常。 |
| `state=closed` 或 `cleanup_state=closed` | 本地驱动/包装器在对应观测点已关闭/解绑。再对照 PG 会话是否消失；本地状态不是 PG 服务端确认。 |
| `state=wrapper_gone_unknown` / `replaced_unknown` | 弱引用目标已释放或 wrapper 换过驱动，不能断言旧会话仍开着或已关闭；结合 `cleanup_state` 和 PG 快照。 |
| `origin=unscoped_created request_id=-` | 此建连没有请求 ContextVar，常见于原生线程池/后台线程；按 worker、线程、callsite 排查，不伪造请求关联。 |
| `event=db_diagnostic_failed` 或 `dropped_connections>0` | 证据不完整，不能用“缺少日志”证明清理未执行。诊断异常只告警类型，不改变业务结果。 |

`cleanup_seen` 仅表示该线程执行到了诊断的 `request_finished` receiver（注册在 Django
默认连接清理 receiver 之后）；`cleanup_state` 是当时的本地快照。
`response_closed=True` 也不保证所有信号 receiver 成功，因为 Django 会先置 closed 再发信号。
`outcome=returned` 只表示 ASGI 正常返回，HTTP 是否成功仍看 `status_code`。

## 覆盖边界

- 不全局 patch `SyncToAsync`，不包装数据库 `close`，不查询 `pg_stat_activity`，不执行探活 SQL。
- 观测新建连接，以及请求开始线程中已有的连接。旁路线程里**复用且本次没有重新建连**的连接
  不一定被捕获；原生线程池未传播上下文时也不能自动关联请求。
- ASGI 入口注册的信号可看到同进程未关联请求的建连；不覆盖独立 Celery/NATS/管理命令进程。
- 请求结束快照不是持续追踪；请求派生且未等待的后台任务可能在快照后继续建连或关闭连接。
- 不记录每条 SQL，因此能定位请求、建连调用点及清理阶段，不能仅凭这些日志确定慢 SQL/锁等待详情。
- 先以 PG 快照确认“旧 PID 持续存在”，再结合日志确认生命周期；不要只比较总连接数，正常新请求也会补充连接。
