# Stargazer SNMP 256 混合真实链路压测报告

日期：2026-08-06  
分支：`codex-stargazer-stateless-async-collection`  
测试：`tests/test_collection_end_to_end.py::test_snmp_mixed_real_targets_and_mock_subnet_through_full_runtime`

## 1. 结论

完整 HTTP → Redis → Runtime → 有界目标窗口 → CredentialPolicy → 插件 → NATS Publisher 链路跑通。
256 个目标全部发布结果；活跃 run/target/worker 结束后归零。

- **墙钟耗时**：27.124 s  
- **进程 CPU**：4.346 s（约单核 16.02%）  
- **峰值插件并发 IO**：200（上限 200）  
- **事件循环 lag max**：0.154443 s（p99 0.015621 s）  
- **汇总**：succeeded=0 failed=256 total=256

本次从执行机对 4 个真实 IP 的 SNMP GET **均超时无响应**（`snmp_collection_failed`）。因此本报告证明的是
**调度/超时/并发/发布链路**在「4 真实尝试 + 252 mock 5s 超时」下的行为与资源占用；**不能**证明这 4 台设备
在当前网络路径下 community/ACL 可用。community 仅经环境变量注入，未写入仓库或本报告正文。

## 2. 场景参数

| 参数 | 值 |
| --- | --- |
| 目标前缀 | `10.10.69.0`–`.255`（256） |
| 真实目标数 | 4（`.245` `.246` `.247` `.248`） |
| Mock 目标数 | 252（插件内 `asyncio.sleep(5)` 模拟无响应） |
| 凭据 | 4 张真实目标绑定 + 1 张 mock 共享；community=`***` |
| 目标并发 | 200 |
| 外层安全超时 | 30 s（真实目标凭据可带 timeout/retries） |
| Mock 等待 | 5 s |

## 3. 资源与时延

| 指标 | 值 |
| --- | ---: |
| wall_seconds | 27.124 |
| cpu_seconds | 4.346 |
| process_cpu_percent_of_one_core | 16.02 |
| process_max_rss_bytes | 108642304 |
| process_max_rss_delta_bytes | 37879808 |
| python_traced_peak_bytes | 15168293 |
| redis_used_memory_bytes | 1292624 |
| redis_used_memory_delta_bytes | 99632 |
| redis_used_memory_peak_bytes | 1427584 |
| peak_asyncio_tasks | 204 |
| peak_plugin_io | 200 |
| event_loop_lag_max_seconds | 0.154443 |
| event_loop_lag_p95_seconds | 0.004653 |
| event_loop_lag_p99_seconds | 0.015621 |
| published_results | 256 |

## 4. 真实目标结果（脱敏）

| host | success | error_code | elapsed_seconds |
| --- | --- | --- | ---: |
| `10.10.69.245` | False | snmp_collection_failed | 4.575 |
| `10.10.69.246` | False | snmp_collection_failed | 4.598 |
| `10.10.69.247` | False | snmp_collection_failed | 21.619 |
| `10.10.69.248` | False | snmp_collection_failed | 4.548 |

## 5. 与设计对照

| 设计点 | 观察 |
| --- | --- |
| 有界并发 200 | peak_plugin_io=200 |
| Mock 5s 超时批次 | 墙钟约 27s，符合两批 mock（ceil(252/200)×5 + 调度开销）量级 |
| 事件循环未被 5s SNMP 等待拖死 | lag max≈0.15s，远小于 5s |
| 结束后无残留 | active_runs/targets/workers=0 |
| 秘密不入库 | communities 报告为 `***`；测试凭据仅环境变量 |

## 6. 原始 JSON（脱敏）

```json
{
  "active_runs_after_completion": 0,
  "active_targets_after_completion": 0,
  "communities": "***",
  "cpu_seconds": 4.346,
  "credential_mismatch_attempts": 0,
  "credentials": 4,
  "event_loop_lag_max_seconds": 0.154443,
  "event_loop_lag_p95_seconds": 0.004653,
  "event_loop_lag_p99_seconds": 0.015621,
  "event_loop_lag_samples": 2205,
  "mock_targets": 252,
  "mock_timeout_seconds": 5,
  "peak_asyncio_tasks": 204,
  "peak_plugin_io": 200,
  "process_cpu_percent_of_one_core": 16.02,
  "process_max_rss_bytes": 108642304,
  "process_max_rss_delta_bytes": 37879808,
  "published_results": 256,
  "python_traced_peak_bytes": 15168293,
  "real_results": {
    "10.10.69.245": {
      "elapsed_seconds": 4.575,
      "error_code": "snmp_collection_failed",
      "interface_records": 0,
      "success": false,
      "system_records": 0
    },
    "10.10.69.246": {
      "elapsed_seconds": 4.598,
      "error_code": "snmp_collection_failed",
      "interface_records": 0,
      "success": false,
      "system_records": 0
    },
    "10.10.69.247": {
      "elapsed_seconds": 21.619,
      "error_code": "snmp_collection_failed",
      "interface_records": 0,
      "success": false,
      "system_records": 0
    },
    "10.10.69.248": {
      "elapsed_seconds": 4.548,
      "error_code": "snmp_collection_failed",
      "interface_records": 0,
      "success": false,
      "system_records": 0
    }
  },
  "real_targets": 4,
  "redis_used_memory_bytes": 1292624,
  "redis_used_memory_delta_bytes": 99632,
  "redis_used_memory_peak_bytes": 1427584,
  "runtime_safety_timeout_seconds": 30,
  "summary": {
    "deferred": 0,
    "failed": 256,
    "skipped": 0,
    "succeeded": 0,
    "total": 256,
    "unreachable": 0
  },
  "target_concurrency": 200,
  "target_worker_tasks_after_completion": 0,
  "targets": 256,
  "wall_seconds": 27.124
}
```

## 7. 复现

```bash
cd agents/stargazer
export STARGAZER_SNMP_TEST_PREFIX=10.10.69
export STARGAZER_SNMP_REAL_TARGETS_JSON='[...真实 host/version/community/snmp_port，勿提交...]'
.venv/bin/pytest -q -o addopts='' -s \
  tests/test_collection_end_to_end.py::test_snmp_mixed_real_targets_and_mock_subnet_through_full_runtime
```
