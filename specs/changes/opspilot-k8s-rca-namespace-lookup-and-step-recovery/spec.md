# OpsPilot K8s RCA：缺 namespace 反查与步骤恢复

Status: implemented

## Problem Statement

K8S RCA 在告警仅有 resource_name、无 namespace 时，模型未反查命名空间就输出「待确认项」；`diagnose` 返回 JSON `{"error":...}` 不触发重规划；某步上下文溢出后会清空后续步骤（计划 4 步只跑 3 步）。

## Solution

1. `resolve_k8s_target_from_alert` 在缺 namespace 时调用全 ns Pod/Events 反查。
2. `_step_failure` 识别 JSON error 软失败并触发重规划。
3. 上下文溢出时压缩历史、跳过当前步并继续后续步骤（不带着全量工具目录重规划）。
4. 规划器目录增加缺 namespace 反查能力导读。

## Testing Decisions

- `test_kubernetes_data_collection_tools.py`：namespace 反查与多候选。
- `test_deepagent_runtime_policy.py`：JSON 失败识别、规划导读。
- `test_deepagent_engine_service.py`：溢出后续跑、JSON error replan。

## Further Notes

- 完成证据：上述单测通过；对照日志场景（Unhealthy / server-5b8fb979d7-csdcc / 8K overflow）。
