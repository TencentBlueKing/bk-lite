# OpsPilot 分步执行：工具结果压缩与 K8s 反查硬校验

Status: implemented

## Problem Statement

真机日志（Unhealthy / `server-5b8fb979d7-csdcc`，2026-08-06 14:13）显示：
- 规划已正确把 `resolve_k8s_target_from_alert` 作为第一步；
- 第 2 步 `diagnose_kubernetes_pod_issues` 仍因 `8259 > 8192` 溢出；
- 溢出后续跑已生效，但后续步 prompt 再次爬回 ~8K，最终总结几乎无输出。

根因是步内/步间仍携带完整工具结果，8K 窗口无法消化。

## Solution

1. 分步执行每次模型调用前截断过长 ToolMessage（及过长 AI 文本）。
2. 每步结束后用「用户原问 + 已完成步骤摘要」替换完整工具历史，再进入下一步。
3. 规划器 `_normalize` 硬校验：若计划含需 namespace 的诊断类工具，且可用反查工具存在，则强制第一步包含反查工具（导读不够时兜底）。

## Testing Decisions

- `test_deepagent_runtime_policy.py`：截断辅助函数、规划硬校验改写。
- `test_deepagent_engine_service.py`：步成功后进入下一步的消息不含巨型 tool 结果；硬校验注入第一步。

## Further Notes

- 对照日志：`logs/bk-lite/opspilot.log`（call_index 4–5 diagnose 溢出，6–9 续跑）。
