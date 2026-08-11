# Stargazer SNMP 256 混合真实链路压测报告

日期：2026-08-07  
分支：`codex-stargazer-stateless-async-collection`  
测试：`tests/test_collection_end_to_end.py::test_snmp_mixed_real_targets_and_mock_subnet_through_full_runtime`  
对照：`snmp-256-mixed-real-load-test-report-2026-08-06.md`（上次 4 真实全超时）

## 1. 结论

完整 HTTP → Redis → Runtime → 有界目标窗口 → CredentialPolicy → 插件 → NATS Publisher 链路跑通。
256 个目标全部发布结果；活跃 run/target/worker 结束后归零。**测试通过（1 passed）。**

| 指标 | 本次（2026-08-07） | 上次（2026-08-06） |
| --- | ---: | ---: |
| 墙钟耗时 | **10.221 s** | 27.124 s |
| 进程 CPU | 2.749 s（约单核 26.89%） | 4.346 s（16.02%） |
| 峰值插件并发 IO | 200 | 200 |
| 事件循环 lag max | **0.084 s** | 0.154 s |
| 真实目标成功 | **3 / 4** | 0 / 4 |
| 发布结果数 | 256 | 256 |
| 结束后残留 | 无 | 无 |

真实设备：

- `10.10.69.245` / `.247` / `.248`：**成功**（系统 + 接口 walk）
- `10.10.69.246`：**失败**（SNMP 无响应超时）——与单独连通性探测一致，属设备/路径问题，非框架调度错误

community 仅经环境变量 `STARGAZER_SNMP_REAL_TARGETS_JSON` 注入，**未写入仓库或本报告明文**。

## 2. 场景参数

| 参数 | 值 |
| --- | --- |
| 目标前缀 | `10.10.69.0`–`.255`（256） |
| 真实目标数 | 4（`.245` `.246` `.247` `.248`） |
| Mock 目标数 | 252（插件内 `asyncio.sleep(5)` 模拟无响应） |
| 凭据 | 4 张真实目标绑定 + 1 张 mock 共享；community=`***` |
| `.247` 超时 | timeout=20, retries=3 |
| `.245` / `.248` / `.246` | 插件默认 timeout/retries（未在 JSON 强制覆盖时走 `SnmpFacts` 默认） |
| 目标并发 | 200 |
| 外层安全超时 | 30 s |
| Mock 等待 | 5 s |
| 运行 deadline | 40 s |

## 3. 资源与时延

| 指标 | 值 |
| --- | ---: |
| wall_seconds | 10.221 |
| cpu_seconds | 2.749 |
| process_cpu_percent_of_one_core | 26.89 |
| process_max_rss_bytes | 111755264 |
| process_max_rss_delta_bytes | 40632320 |
| python_traced_peak_bytes | 14915084 |
| redis_used_memory_bytes | 1149632 |
| redis_used_memory_delta_bytes | 22160 |
| redis_used_memory_peak_bytes | 1215008 |
| peak_asyncio_tasks | 204 |
| peak_plugin_io | 200 |
| event_loop_lag_max_seconds | 0.08371 |
| event_loop_lag_p95_seconds | 0.011531 |
| event_loop_lag_p99_seconds | 0.036014 |
| event_loop_lag_samples | 775 |
| published_results | 256 |
| mock_calls | 252 |
| credential_mismatch_attempts | 0 |
| active_runs_after_completion | 0 |
| active_targets_after_completion | 0 |
| target_worker_tasks_after_completion | 0 |

### 墙钟解读

- Mock 侧：252 目标、窗口 200 → 约两批 5s；但真实目标与首批并行，真实侧亚秒～数秒完成。
- 本次墙钟 **~10.2s**（上次 ~27s 因 4 真实也打满超时，整体被拉长）。
- 事件循环 lag max **<0.1s**，说明 200 并发下循环未被 SNMP `to_thread` / mock sleep 拖死。

## 4. 真实目标结果（脱敏）

| host | success | system | interfaces | elapsed_seconds | error_code |
| --- | --- | ---: | ---: | ---: | --- |
| `10.10.69.245` | true | 1 | 13 | 1.919 | — |
| `10.10.69.246` | false | 0 | 0 | 4.424 | snmp_collection_failed |
| `10.10.69.247` | true | 1 | 30 | 2.928 | — |
| `10.10.69.248` | true | 1 | 15 | 1.851 | — |

汇总：`real_succeeded=3`，`real_failed=1`。

## 5. 与设计对照

| 设计点 | 观察 |
| --- | --- |
| 有界并发 200 | peak_plugin_io=200 |
| 单目标即推 | published_results=256 |
| 目标绑定凭据 | credential_mismatch_attempts=0 |
| 事件循环不被阻塞 | lag max≈0.084s |
| 结束后无残留 | active_runs/targets/workers=0 |
| 失败等下周期（非断点续跑） | 本测不验证续跑；结束后可再次 submit |
| 秘密不入库 | communities 报告为 `***` |

## 6. 与 2026-08-06 对照结论

| 项 | 2026-08-06 | 2026-08-07 |
| --- | --- | --- |
| 框架调度/发布 | 通 | 通 |
| 真实设备可达性 | 4 台全超时 | **3 通 1 不通（.246）** |
| 墙钟 | ~27s（真实也超时） | **~10s** |
| 证明范围 | 仅调度 | **调度 + 3 台设备兼容** |

`.246` 需单独查 community/ACL/网络路径；不要据此判框架失败。

## 7. 复现命令

```bash
cd agents/stargazer
export STARGAZER_SNMP_TEST_PREFIX=10.10.69
export STARGAZER_SNMP_REAL_TARGETS_JSON='[...]'  # 含 host/version/community/snmp_port，勿提交

.venv/bin/pytest -q -o addopts='' -s \
  tests/test_collection_end_to_end.py::test_snmp_mixed_real_targets_and_mock_subnet_through_full_runtime
```

## 8. 原始 JSON（脱敏）

```json
{
  "active_runs_after_completion": 0,
  "active_targets_after_completion": 0,
  "communities": "***",
  "cpu_seconds": 2.749,
  "credential_mismatch_attempts": 0,
  "credentials": 4,
  "event_loop_lag_max_seconds": 0.08371,
  "event_loop_lag_p95_seconds": 0.011531,
  "event_loop_lag_p99_seconds": 0.036014,
  "event_loop_lag_samples": 775,
  "mock_calls": 252,
  "mock_targets": 252,
  "mock_timeout_seconds": 5,
  "peak_asyncio_tasks": 204,
  "peak_plugin_io": 200,
  "process_cpu_percent_of_one_core": 26.89,
  "process_max_rss_bytes": 111755264,
  "process_max_rss_delta_bytes": 40632320,
  "published_results": 256,
  "python_traced_peak_bytes": 14915084,
  "real_failed": 1,
  "real_succeeded": 3,
  "real_targets": 4,
  "redis_used_memory_bytes": 1149632,
  "redis_used_memory_delta_bytes": 22160,
  "redis_used_memory_peak_bytes": 1215008,
  "runtime_safety_timeout_seconds": 30,
  "target_concurrency": 200,
  "target_worker_tasks_after_completion": 0,
  "targets": 256,
  "wall_seconds": 10.221,
  "real_results": {
    "10.10.69.245": {
      "elapsed_seconds": 1.919,
      "error_code": "",
      "interface_records": 13,
      "success": true,
      "system_records": 1
    },
    "10.10.69.246": {
      "elapsed_seconds": 4.424,
      "error_code": "snmp_collection_failed",
      "interface_records": 0,
      "success": false,
      "system_records": 0
    },
    "10.10.69.247": {
      "elapsed_seconds": 2.928,
      "error_code": "",
      "interface_records": 30,
      "success": true,
      "system_records": 1
    },
    "10.10.69.248": {
      "elapsed_seconds": 1.851,
      "error_code": "",
      "interface_records": 15,
      "success": true,
      "system_records": 1
    }
  }
}
```
