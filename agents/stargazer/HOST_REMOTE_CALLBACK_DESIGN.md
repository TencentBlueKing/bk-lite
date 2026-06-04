# Host Remote Callback Flow

## Target flow

```text
Telegraf
  -> /api/monitor/host/metrics
  -> ARQ collect_task(monitor_type=host)
  -> submit ansible adhoc with callback subject
  -> ansible callback -> service.nats_server.handle_host_remote_callback
  -> persist raw callback + enqueue processing worker
  -> ARQ process_host_remote_callback_task
  -> HostCollector.process_adhoc_result
  -> publish_metrics_to_nats
```

## Runtime phases

1. **submit**
   - `tasks.handlers.monitor_handler.collect_host_metrics_task`
   - stores callback context in Redis
   - submits remote execution to ansible
   - returns `defer_running_clear=True`

2. **callback receive**
   - `service.nats_server.handle_host_remote_callback`
   - validates `task_id`
   - stores raw callback payload in Redis context
   - clears `task:running:{task_id}`
   - enqueues `process_host_remote_callback_task`

3. **callback process**
   - `tasks.handlers.host_remote_handler.process_host_remote_callback_task`
   - reads stored callback payload/context
   - transforms callback payload to Prometheus metrics
   - publishes metrics to NATS
   - updates Redis delivery status
   - clears callback context after successful publish

4. **sweeper / retry**
   - `core.host_remote_runtime.sweep_host_remote_callback_contexts`
   - marks callback timeout for overdue `waiting_callback`
   - re-enqueues `publish_pending`
   - re-enqueues stale `processing`

## Redis callback context schema

```json
{
  "task_id": "collect_host_xxx",
  "ctx": {},
  "params": {},
  "status": {
    "execution": "waiting_callback|execution_finished",
    "delivery": "not_ready|processing|published|delivery_failed"
  },
  "raw_callback": {},
  "callback_received_at": 0,
  "process_enqueued_at": 0,
  "process_started_at": 0,
  "process_completed_at": 0,
  "processing_job_id": "process_host_remote_callback:<task_id>",
  "publish_attempts": 0,
  "last_retry_at": 0,
  "next_retry_at": 0,
  "published_at": 0,
  "last_error": "",
  "created_at": 0,
  "updated_at": 0
}
```

## Cleanup semantics

- `task:running:{task_id}` is cleared when callback is safely persisted.
- callback context is retained while processing/publish is pending.
- callback context is removed only after successful publish.
- failed publish keeps callback context for retry/inspection.

## Retry / timeout policy

- `HOST_REMOTE_CALLBACK_DEADLINE_SECONDS` controls callback timeout detection.
- `HOST_REMOTE_PUBLISH_RETRY_BACKOFFS` controls publish retry backoff sequence.
- retryable publish failures move delivery state to `publish_pending`.
- non-retryable failures end as `delivery_failed`.

## Route separation

- remote host collection must use `/api/monitor/host/metrics`
- `/api/collect/collect_info` now rejects `model_id=host` with an explicit route hint

## Runtime validation

- startup warns when `NATS_SERVERS` is set but `NATS_URLS` is empty
- startup warns when `NATS_URLS` and `NATS_SERVERS` diverge
- startup warns when callback deadline is not aligned with worker timeout

## Current implementation notes

- host remote callback processing is decoupled from callback receive.
- callback receive stays lightweight and no longer publishes metrics directly.
- processing worker is registered in `core.worker.WorkerSettings`.
