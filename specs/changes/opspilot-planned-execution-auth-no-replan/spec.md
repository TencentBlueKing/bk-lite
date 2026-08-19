# OpsPilot 分步执行：凭据/权限失败不重规划

Status: implemented

## Problem Statement

K8S 等业务工具返回 401、403 或 kubeconfig 加载失败时，分步执行仍把它当成可恢复失败：步内改参再试，外层最多重规划两次。凭据来自技能配置，再规划同类工具结果不变，只会空烧 token。

## Solution

工具与技能脚本失败走同一套分型。凭据（401）、权限（403）、连接配置/解密失败、以及实现异常不再重规划，清空后续步骤并直接告诉用户。超时、5xx、资源不存在、查询参数缺失（如 namespace）、脚本不存在/参数错误等仍可改命令或重规划。

## User Stories

1. As a 运维人员, I want 集群凭据错误时立即看到要改 kubeconfig/token, so that 不会空等两轮无效重规划。
2. As a 运维人员, I want RBAC 403 时看到权限不足而不是再跑后续诊断步, so that 不会用同一身份反复打集群。
3. As a 运维人员, I want Pod 不存在或瞬时连接失败仍可换步骤继续, so that 可恢复失败不被误杀。

## Implementation Decisions

- 在规划器旁增加失败分型：authn / authz / config / internal / other。扫包拒绝、技能成功/改命令提示仍不算失败；技能脚本失败正文（即使带 `[OPSPILOT_SKILL_RESULT]`）按同一套规则分型。
- 分步循环在重规划前拦截不可恢复失败：结束当前步、清空后续步、不发 replanning。技能步与业务工具步共用该收口。
- 技能守卫：凭据/配置/实现异常第一次 execute 即收工具；超时等仍允许改参再 execute 一次。
- 步内已有给用户的正文时沿用跳过总结轮，避免复述。
- 步内提示收紧为 401/配置失败/实现异常不改参；403 仅允许换 namespace、实例或查询范围一次。不按工具名特判。
- 连接参数只拦 host/url required、CredentialValidationError；不拦 namespace 等查询参数。
- 实现异常只认 AttributeError/TypeError/ImportError 等解释器错误与 Traceback，不把所有 status=error 当代码缺陷。

## Testing Decisions

- `test_deepagent_runtime_policy.py`：分型与不可重规划判定（含技能脚本 401 / timeout）；技能守卫第一次凭据失败即停。
- `test_deepagent_engine_service.py`：工具与技能步 401/403 不二次规划且不跑后续步；Pod 不存在 JSON error 仍重规划。
- `test_execute_result_log_summary.py`：凭据失败提示禁止重试；普通脚本失败仍最多改参一次。

## Out of Scope

- 不改 K8S 客户端与凭据注入。
- 不把「Pod 不存在」改为禁止重规划。

## Further Notes

- 失败分型抽到无 langchain 依赖的 `tool_failure` 模块，业务工具与技能脚本共用；规划器再导出原符号。
- 工具抛异常时由 `ToolExceptionAsResultMiddleware` 写成 ToolMessage，保证前端收到 TOOL_CALL_RESULT；步骤 end 带 `failed_*` + `error`，UI 显示失败而非绿色「已完成」。
