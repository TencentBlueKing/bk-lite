# Stargazer 主机采集 150 目标 Mock 压测报告

日期：2026-08-07  
分支：`codex-stargazer-stateless-async-collection`  
测试：`tests/test_collection_end_to_end.py::test_host_150_target_timeout_load_through_http_redis_runtime_and_nats`

## 1. 结论

完整 HTTP → Redis → Runtime → 有界目标窗口 → CredentialPolicy → Host CredentialAttempt（mock）→ NATS Publisher 链路跑通。
150 个目标全部发布结果；活跃 run/target/worker 结束后归零。**测试通过（1 passed）。**

| 指标 | 值 |
| --- | ---: |
| 墙钟耗时 | **5.177 s** |
| 进程 CPU | 0.366 s（约单核 7.07%） |
| 峰值插件并发 IO | **150**（目标数 ≤ 窗口 200，一批打满） |
| 事件循环 lag max | **0.085 s**（p99 0.024 s） |
| 发布结果数 | 150 |
| 插件超时数 | 150（预期：全部 mock 打满 5s 外层超时） |
| 凭据错配 | 0 |
| 结束后残留 | 无 |

本测凭据全部 mock（username/password 仅环境变量/测试默认值注入），**不连真实 SSH/Responder**。
`TargetPolicy` 使用测试注入的 `ReachablePreflight`，避免把本机 NATS Responder 不可用误判为采集失败。
报告证明的是 **host 模型在有界并发 + 5s Attempt 超时**下的调度/资源占用；不证明 10.10.41.0–149 真实主机可达。

## 2. 场景参数

| 参数 | 值 |
| --- | --- |
| 目标范围 | `10.10.41.0`–`.149`（150） |
| 协议语义 | host SSH/Job CredentialAttempt（mock） |
| 凭据 | 1 张共享 mock（username/password=`***`，port=22） |
| 目标并发 | 200 |
| 外层 connect/plugin 超时 | 5 s / 5 s |
| Mock 行为 | `asyncio.sleep(60)`，由外层 `plugin_timeout` 取消 |
| 运行 deadline | 20 s |
| HTTP 入口 | `GET /collect/collect_info`（`model_id=host`, `executor_type=job`） |

## 3. 资源与时延

| 指标 | 值 |
| --- | ---: |
| wall_seconds | 5.177 |
| cpu_seconds | 0.366 |
| process_cpu_percent_of_one_core | 7.07 |
| process_max_rss_bytes | 67567616 |
| process_max_rss_delta_bytes | 1507328 |
| python_traced_peak_bytes | 1064919 |
| redis_used_memory_bytes | 1148928 |
| redis_used_memory_delta_bytes | 0 |
| redis_used_memory_peak_bytes | 1279328 |
| peak_asyncio_tasks | 154 |
| peak_plugin_io | 150 |
| event_loop_lag_max_seconds | 0.085476 |
| event_loop_lag_p95_seconds | 0.002587 |
| event_loop_lag_p99_seconds | 0.024045 |
| event_loop_lag_samples | 423 |
| published_results | 150 |
| plugin_timeout_total | 150 |
| credential_mismatch_attempts | 0 |
| active_runs_after_completion | 0 |
| active_targets_after_completion | 0 |
| target_worker_tasks_after_completion | 0 |

### 墙钟解读

- 150 目标、窗口 200 → **一批**完成；墙钟 ≈ 外层 5s 超时 + 调度开销（~5.2s）。
- 事件循环 lag max **<0.1s**，说明 150 并发 mock Attempt 未拖死循环。
- CPU 占用低（~7% 单核），符合「等待超时」型负载。

## 4. 与设计对照

| 设计点 | 观察 |
| --- | --- |
| 有界并发 200 | peak_plugin_io=150（受目标数限制） |
| 单目标即推 | published_results=150 |
| 凭据串行尝试（每目标 1 张） | credential_mismatch_attempts=0；plugin_timeout_total=150 |
| 事件循环不被阻塞 | lag max≈0.085s |
| 结束后无残留 | active_runs/targets/workers=0 |
| 秘密不入库 | username/password 报告为 `***` |

## 5. 与 SNMP 256 压测对照

| 项 | Host 150 mock（本次） | SNMP 256 mixed（同日） |
| --- | --- | --- |
| 墙钟 | ~5.2s（一批） | ~10.2s（两批 mock + 真实） |
| 峰值并发 | 150 | 200 |
| 真实设备 | 无（全 mock） | 3 通 / 1 不通 |
| lag max | 0.085s | 0.084s |

## 6. 复现命令

```bash
cd agents/stargazer
export STARGAZER_HOST_TEST_PREFIX=10.10.41
export STARGAZER_HOST_TEST_COUNT=150
# 可选覆盖 mock 凭据（勿提交）
# export STARGAZER_HOST_TEST_USERNAME=...
# export STARGAZER_HOST_TEST_PASSWORD=...

.venv/bin/pytest -q -o addopts='' -s \
  tests/test_collection_end_to_end.py::test_host_150_target_timeout_load_through_http_redis_runtime_and_nats
```

## 7. 原始 JSON（脱敏）

```json
{
  "active_runs_after_completion": 0,
  "active_targets_after_completion": 0,
  "cpu_seconds": 0.366,
  "credential_mismatch_attempts": 0,
  "credentials": 1,
  "event_loop_lag_max_seconds": 0.085476,
  "event_loop_lag_p95_seconds": 0.002587,
  "event_loop_lag_p99_seconds": 0.024045,
  "event_loop_lag_samples": 423,
  "expected_failed_targets": 150,
  "expected_succeeded_targets": 0,
  "password": "***",
  "peak_asyncio_tasks": 154,
  "peak_plugin_io": 150,
  "plugin_timeout_total": 150,
  "port": 22,
  "process_cpu_percent_of_one_core": 7.07,
  "process_max_rss_bytes": 67567616,
  "process_max_rss_delta_bytes": 1507328,
  "protocol": "host-ssh-job-mock",
  "published_results": 150,
  "python_traced_peak_bytes": 1064919,
  "redis_used_memory_bytes": 1148928,
  "redis_used_memory_delta_bytes": 0,
  "redis_used_memory_peak_bytes": 1279328,
  "target_concurrency": 200,
  "target_range": "10.10.41.0-149",
  "target_worker_tasks_after_completion": 0,
  "targets": 150,
  "timeout_seconds": 5,
  "username": "***",
  "wall_seconds": 5.177
}
```
