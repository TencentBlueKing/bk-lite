# APM 受控 Spans 检索

Status: implemented

## Completion Evidence

- `TelemetryStore.search_spans` + `SpanSearchQuery` / `SpanSummary` / `SpanPage` 已落地；`VictoriaTracesTelemetryStore` 用受控 LogsQL 查 `/select/logsql/query`。
- `GET /api/v1/apm/spans/` 已注册，拒绝未知参数；组织过滤复用 Trace 访问解析。
- Trace Jaeger 搜索可选 `span_name` / status / 耗时过滤已对齐。
- 调用链页开放 Spans|Traces，去掉「数据能力就绪后开放」；详情支持 `?span_id=`。
- 测试：`apps/apm/tests/test_span_api.py`、`test_victoriatraces_adapter.py::test_search_spans_*`；`web/scripts/apm-explore-workflow-test.ts` 通过。
- 本机 lab：`weops-lite-probe`/`lab` 返回 `GET /lab/health` Span；`status=error` 为空；未知参数 400。

## Problem Statement

调用链页保留了 `Spans | Traces` 切换，但 Spans 视角被禁用并提示「数据能力就绪后开放」。现有 Trace 搜索走 Jaeger `/select/jaeger/api/traces`，返回整条 Trace 而非「一行一个 Span」。探索 PRD 中的任意属性检索、分面与实时尾随超出当前交付边界；同时契约禁止向领域层透传 LogsQL/TraceQL。

## Solution

在 `TelemetryStore` 增加类型化 `search_spans`，由 `VictoriaTracesTelemetryStore` 用受控 LogsQL 模板查询 `/select/logsql/query`，暴露 `GET /api/v1/apm/spans/`，并打开前端 Spans 视角。不开放任意属性过滤，不引入 Span Metrics / VM。

## User Stories

1. As an APM 使用者, I want 按服务、环境、操作名、状态、kind 与耗时区间检索 Span 列表, so that 我能直接定位单次操作再跳进所属 Trace。
2. As an APM 使用者, I want 在调用链页切换 Spans / Traces, so that 同一套筛选条件下可用 Span 行或 Trace 行查看结果。
3. As a 平台工程师, I want 查询仍经类型化 DTO 与 Adapter 模板, so that 用户无法粘贴 LogsQL/TraceQL，且时间窗与结果上限可控。

## Implementation Decisions

### 受控查询字段

- 必填：`service_name`、`environment`、时间窗（与 Trace 搜索同一服务窗上限：QueryService 7d；Adapter 硬上限 35d）。
- 可选：`service_namespace`、`instance_id`、`span_name`（精确匹配 `name`）、`status`∈`ok|error`（映射 `status_code` 1/2）、`kind`∈`internal|server|client|producer|consumer`（映射 OTel kind 数字）、`min_duration_ms`、`max_duration_ms`、`cursor`、`limit`（1–100）。
- 拒绝未知 query 参数；禁止用户提交 LogsQL/TraceQL/URL。

### 存储与 Adapter

- 使用 `/select/logsql/query` 返回 Span 行；字段沿用现有 VT 模型：`trace_id`、`span_id`、`name`、`kind`、`status_code`、`duration`（ns）、`start_time_unix_nano`、资源属性、`span_attr:http.request.method` / `span_attr:http.response.status_code`（若存在）。
- 值一律经 `_logsql_string` 转义；结果按时间倒序 + `span_id` 稳定排序；cursor 复用既有时间编码。
- 合法无样本返回空 `items`；上游失败返回 `telemetry_unavailable`，不伪装空数据。

### API 与授权

- `GET /api/v1/apm/spans/` 返回 `{items, next_cursor}`；`SpanSummary` 含跳转 Trace 所需身份字段。
- 列表结果按当前组织可见服务/实例过滤，复用 Trace 访问解析语义。
- 顺手扩展 Trace Jaeger 搜索可选 `span_name` / 耗时 / error 过滤，使 Traces 视角筛选可对齐；仍返回 Trace 行。

### 前端

- 启用 Spans 切换；去掉「数据能力就绪后开放」文案。
- Spans 表格列：服务 / 资源 / HTTP / 耗时 / 时间；点行进入 `/apm/traces/{traceId}?span_id=...`。

### 明确不做

- 任意 Span/资源属性过滤、正则任意字段、用户粘贴查询语言。
- Issue 聚类、火焰图、实时尾随、结构特征检索、Span Metrics。

## Acceptance Criteria

1. `GET /api/v1/apm/spans/` 在 lab 探针数据下能返回 `weops-lite-probe` / `lab` 的 Span（如 `GET /lab/health`）。
2. 非法参数 / 超窗 / 超限返回 400；VT 不可用返回 503。
3. 调用链页可切换 Spans，列表可点进 Trace 详情并选中对应 span。
4. `status=error` 对健康探针返回空列表；未知参数被拒绝。
5. 单测覆盖 Adapter 模板转义、memory store、API 组织过滤与校验。
