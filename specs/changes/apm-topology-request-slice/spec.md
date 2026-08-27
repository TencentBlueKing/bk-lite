# APM 服务拓扑按请求切片

Status: implemented

## Completion Evidence

- 拓扑服务构图改为 `TopologyStore.sample_traces` 的有界 Trace 样本；图、节点 RED、边 P95/错误率和样本 Trace 同源。Adapter 用模板化 LogsQL，禁止用户粘贴 TraceQL。
- 切片字段复用调用链探索：`status` / `span_name` / `min_duration_ms` / `environment`。`status=error` 后图中不含仅正常请求才有的边；操作名切片只保留命中该操作的路径。
- 边样本 Trace 带 caller 与 callee 身份。截断时 `truncated=true`。单个 Trace 拉取失败记 WARNING 并省略，不让整张图失败。
- 拓扑页增加请求状态 / 操作名 / 耗时下限与「清空切片」；「只看异常」仍是节点健康度的客户端过滤，不触发重新取数。
- 测试：`apps/apm/tests/test_topology_service.py` 切片与边 RED 用例；`test_victoriatraces_adapter.py` 的 `sample_traces` 模板查询；`topology-canvas.test.tsx`；`apm-service-workflow-test.ts` 通过。sqlite 下原有 `test_topology_api_*` 仍因无关迁移无法建库。

## Problem Statement

服务拓扑已经能在图上看出谁慢、谁错，并停在图上看样本 Trace。但它仍是「时间窗内谁调用了谁」的全图。不能把图收成「这次出错的请求怎么走」或「这条结账接口怎么走」。边也仍然只有调用量，点边时的样本 Trace 不是这条边上的调用，只是被调用方服务的最近 Trace。

## Solution

用同一套有界 Trace 样本构图，而不是 Jaeger `dependencies` 的 callCount。拓扑页增加与调用链探索一致的请求切片：错误状态、操作名、耗时下限。过滤后整张图、节点 RED、边 P95/错误率和样本 Trace 都只来自命中的 Trace。不开放用户粘贴 TraceQL。

## User Stories

1. As an APM 使用者, I want 把拓扑收成「仅错误请求」或某一操作名的调用图, so that 我看到的是这次故障/这条接口怎么走，而不是组织里所有调用。
2. As an APM 使用者, I want 边上看到真实 P95 和错误率, so that 我能判断瓶颈在哪一段调用，而不是只有谁连着谁。
3. As an APM 使用者, I want 点边后看到的样本 Trace 属于这条调用关系, so that 打开瀑布图时能看到这对 caller→callee，而不是被调用方的任意最近请求。
4. As an APM 使用者, I want 切片条件带到「更多调用链」, so that 离开拓扑后仍在查同一批请求。
5. As an APM 使用者, I want 清空切片后回到时间窗内的全图, so that 我可以在全貌和这次故障之间切换。

## Implementation Decisions

- 拓扑构图离开 VictoriaTraces Jaeger `/select/jaeger/api/dependencies`。领域层只提交类型化拓扑查询 DTO；Adapter 内部可用模板化查询，禁止把用户输入当 TraceQL/LogsQL 透传。
- 图、节点量和边量都来自同一有界 Trace 样本。时间窗仍最长 7 天，组织内仍最多 30 个拓扑目标。样本不足时 `truncated=true`，调用量不代表全量。
- 请求切片复用调用链探索已有字段，不新增任意属性：`status`（全部 / 错误 / 正常）、`span_name`（操作名）、可选 `min_duration_ms`。环境筛选保持现有行为。拓扑上的「只看异常」仍按节点错误率健康度过滤，不等于「仅错误请求」。
- 有切片时，节点 P95 / 错误率 / 吞吐、边 P95 / 错误率 / 调用量、调查栏样本 Trace 都只统计命中切片的样本。无切片时走同一聚合路径，不再叠一份未过滤的服务级 RED。
- 边身份是 caller 服务 → callee 服务（跨服务父子 Span）。边健康度与节点相同：错误率 `>=5%` 严重、`>=1%` 警告、有样本且更低为正常、无样本或聚合失败为未知。边契约用可空的 `p95_ms`、`error_rate` 和真实 `error_calls`；界面不再展示始终为 0 的平均耗时。
- 点边加载最多 5 条同时包含该 caller 与 callee 的样本 Trace。点节点仍加载该服务的样本 Trace。两者都遵守当前切片。「更多调用链」带上同一组过滤参数。
- 单个 Trace 拉取或聚合失败不得让整张图失败；截断与省略记入 `diagnostics`。不提高 30 个目标上限，不做 Gateway 折叠，不开放自定义时间或超过 7 天的窗口。

## Testing Decisions

测试外部行为，不锁 Adapter 内部查询语句。

- 拓扑服务：无切片时边带 P95/错误率；`status=error` 后图中不含正常请求才有的边；操作名切片只保留命中该操作的路径；边样本 Trace 必须同时包含 caller 与 callee。
- 聚合失败或空样本时图仍返回，节点/边健康度为未知，`data_state` 诚实。
- 歧义服务名省略、组织可见性、7 天窗口上限保持现有契约。
- 页面：切片控件改变图与调查栏；清空切片恢复全图；「只看异常」与「仅错误请求」可同时存在且语义不同；「更多调用链」URL 含相同过滤。

先验：`test_topology_service.py`、`topology-canvas.test.tsx`、`apm-service-workflow-test.ts`。

## Out of Scope

- 任意 span 属性、用户、高基数字段或用户粘贴 TraceQL。
- Gateway/Sidecar 折叠、Entry Service、自定义时间、60 天窗口、提高 30 个目标上限。
- 用未过滤的服务级 RED 覆盖切片后的节点指标。

## Further Notes

本切片接在 `apm-topology-investigation` 之后。对照的是 Honeycomb Filter Traces 的「先切片再看图」，不是把调用链探索做成拓扑。
