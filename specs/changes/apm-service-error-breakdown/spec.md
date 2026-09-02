# APM 服务详情错误 Tab：入口计数 + 全量归因

Status: implemented

## Completion Evidence

- `TelemetryStore.service_error_breakdown` 已落地；`VictoriaTracesTelemetryStore` 用入口 RED 计数 + `stats by (kind, exception/error.type/status_message/http, exception.message)` 归因，样例查询按 coalesce 优先级互斥过滤；内存适配器同步实现。
- `GET /api/v1/apm/services/{id}/error-breakdown/` 已注册，拒绝未知参数；组织过滤复用服务 detail。
- 服务详情错误 Tab 改为四区块（错误率与趋势、失败端点、错误原因、最近失败样本），不再调用 `/apm/issues/`。
- 删除 Issue 未归因合并；探索页 Issue 投影其余行为不变。
- 测试：`test_error_breakdown_api.py`、`test_victoriatraces_adapter.py::test_error_breakdown_*`、`test_memory_adapters.py::test_memory_store_error_breakdown_*`、`web/src/app/apm/services/[serviceId]/__tests__/page.test.tsx`；`web/scripts/apm-service-workflow-test.ts` 通过。

## Problem Statement

服务详情错误 Tab 顶部显示全窗口径的「本窗 1,787 次入口请求 · 226 次失败 · 错误率 12.6%」，下方却是最近 50 条失败入口 Span 逐条拉 Trace 后聚出的 Issue 卡（「50 次 · 占失败样本 100%」）。两套口径并排，用户必然把卡片当成对 226 次失败的拆分，追问为何数字对不上。

更根本的问题是归因看错了层：错误率按入口 Span（SERVER / CONSUMER）计数是正确的，但异常信息不在入口 Span 上。本机 VictoriaTraces 实测 `demo-storefront` 近 1 小时：入口 Error Span 874 条全部是笼统的 `server_error`，真正的原因 `payment_declined`（586）与 `downstream_error`（289）挂在 CLIENT Span 上。把 Issue 收成入口口径后，页面只剩一张 `SpanError / OTel Span status=Error` 卡，等于没有解释。

同时，逐条 `get_trace` 归类是 N+1，页面慢且脆弱；拉不到 Trace 时的「未归因合并」把「不知道」伪装成「都是同一种错」。

## Solution

错误 Tab 拆成四个各自单一口径的区块，全部由存储侧聚合得到，不再逐条拉 Trace：

1. **错误率与趋势**：本窗入口请求 / 失败次数 / 错误率 + 错误率趋势小图（复用现有 RED 聚合）。
2. **失败端点**：按失败次数降序的入口端点列表，各端点失败次数合计等于顶部失败次数（精确，入口口径）。
3. **错误原因**：该服务本窗全部 Error Span（含 CLIENT / INTERNAL 等子 Span）按归因键聚合的 Top 类型，标注发生位置（入口 / 调下游 / 内部）与最近样例链，并说明「按错误类型统计，一次失败请求可能对应多个错误」。
4. **最近失败样本**：最近 N 条入口失败 Span，点端点行可过滤，点样本进入 Trace 详情；区块底部保留「在错误分析中打开」。

计数用入口、归因看全部 Error Span，两者分区标注、不互相对账。删除样本占比、`N 条 Trace` 标签、卡片内展开堆栈与未归因合并逻辑。

## User Stories

1. As an APM 使用者, I want 错误 Tab 顶部的请求数、失败数、错误率与头部 RED 卡完全一致并附趋势, so that 我先知道多严重、从何时开始。
2. As an APM 使用者, I want 看到哪些入口端点在失败、各失败多少次且合计等于总失败数, so that 我能判断是单个端点还是全面性故障。
3. As an APM 使用者, I want 看到本服务真实的错误原因类型（如 `payment_declined`、`downstream_error`）及发生位置, so that 我不用在一堆 `SpanError` 里猜原因。
4. As an APM 使用者, I want 每个错误原因带最近几条样例链、最近失败样本可按端点过滤并直接点进 Trace, so that 定位到原因后能立刻看堆栈与路径。
5. As an APM 使用者, I want 当本窗没有失败请求时看到明确的「无失败」空态、数据面不可用时看到降级提示, so that 空页面不会被误读成「没错」或「坏了」。
6. As a 平台工程师, I want 错误 Tab 的所有数字来自受控 LogsQL 模板下的存储侧聚合、按组织可见范围过滤, so that 不出现 N+1、不透传查询语言、不越权。

## Implementation Decisions

### 口径

- **计数口径**：入口 Span = kind ∈ {SERVER, CONSUMER}，status = ERROR。与现有 RED / SLO 的 `_deduped_entry_query` 语义一致，包括 `RED_EXACT_DEDUP_WINDOW` 内按 (trace_id, span_id) 去重、超窗改流式近似的规则，保证失败端点合计 = RED `error_count`。
- **归因口径**：该服务、该环境、本窗内 **全部** status = ERROR 的 Span，不限 kind。下游失败体现在本服务 CLIENT / PRODUCER Span 上，归为「调下游」；下游服务自身的异常留给下游服务页面。
- 两个口径的数字不要求相等，UI 用区块标题与说明文字区分，不再出现「占失败样本 %」。

### 归因键（已在本机 VT 验证字段可 `stats by`）

按优先级取第一个非空值作为 `error_type`：

1. `event:event_attr:exception.type:0`（OTel exception 事件，仅未捕获异常有）
2. `span_attr:error.type`（OTel 语义约定）
3. `status_message`（OTel 状态描述）
4. `span_attr:http.response.status_code`（仅 5xx，展示为 `HTTP 502`）
5. 兜底常量「未携带错误信息」

副标题取 `event:event_attr:exception.message:0`，缺失则取 `status_message`（与 `error_type` 相同时省略）。

聚合方式：适配器一条 `stats by (kind, <上述四个字段>)` 拿到有界分组（分组上限由适配器常量控制，建议 200），在服务层做 coalesce、按 `error_type` 合并、排序、截取 Top N（建议 10）。不在 LogsQL 里做条件表达式。字段名含冒号与点，须用反引号包裹，与现有 `_SERVICE_FIELD` 写法一致。

### 新契约与适配器

- 新增 `ServiceErrorBreakdownQuery`：`service_namespace`、`service_name`、`environment`、`started_at`、`ended_at`、`sample_limit`。
- 新增 `ServiceErrorBreakdown`：
  - `request_count`、`error_count`、`error_rate`（与 `service_red` 同一算法；可直接复用 `service_red` 不带 breakdown 的结果）
  - `failed_endpoints`: 列表项 `endpoint`、`error_count`、`request_count`、`error_rate`，按 `error_count` 降序，上限与 `MAX_TOP_ENDPOINTS` 同级但独立常量，另返回 `other_error_count` 装未进榜的余量，保证合计可核对
  - `error_types`: 列表项 `error_type`、`message`、`count`、`location` ∈ {`entry`, `downstream`, `internal`}、`last_seen_at`、`sample_traces`（最多 3 条：`trace_id`、`span_id`、`endpoint`、`started_at`）
  - `recent_failures`: 最近 `sample_limit` 条入口失败 Span，复用 `SpanSummary`
  - `data_state`：复用 `MetricDataState`，无入口请求时为 `NO_DATA`，此时其余字段为空
- `TelemetryStore` 协议新增 `service_error_breakdown`；`VictoriaTracesTelemetryStore` 与内存适配器均实现。查询服务层做时间窗校验，沿用 `service_red` 的窗上限。
- `error_types` 每组的最近样例：优先用 LogsQL 行级聚合（如 `row_max` 按 `_time` 取 `trace_id`/`span_id`/`name`）一次拿到最近一条；若需 3 条，对 Top N 每组追加一条 `limit 3` 的行查询，N 有界，可接受。不得对样本逐条调用 `get_trace`。
- 现有 `top_endpoints` 契约不改；`service_red` 不改。

### API

- 新增 `GET /api/v1/apm/services/{id}/error-breakdown/`，挂在服务 ViewSet 的 detail action 上，权限 `services-View`，通过 `get_object()` 复用组织可见范围过滤；参数 `environment`（必填）、`started_at`、`ended_at`、`sample_limit`（1–50，默认 20），拒绝未知参数。
- 错误语义与 `metrics` action 一致：参数非法 400 `invalid_query`；VT 不可用 503 `telemetry_unavailable`。
- 属于内部页面 API，不经 OpenAPI 网关对外暴露。
- 现有 `GET /apm/issues/` 与 `entry_only` 参数保留给探索页，不删除。

### 移除

- 服务详情页不再调用 `/apm/issues/`。
- 删除 Issue 服务中的「未归因合并」（`_merge_unattributed`）及其测试；它是为入口口径只剩 `SpanError` 打的补丁，根因消除后不再需要。探索页 Issue 投影其余行为不变。
- 删除前端 Issue 列表组件的 `sampleShare` 能力与对应 i18n 键；`errorRateReconcile`、`openErrorExplore` 文案按新布局调整或复用。

### 前端布局（服务详情 · 错误 Tab）

- 顶部一行：`本窗 {requests} 次入口请求 · {errors} 次失败 · 错误率 {rate}`，右侧错误率趋势小图（来自现有 RED `timeseries`）。
- 区块「失败端点」：表格列 端点 / 失败次数 / 请求次数 / 错误率；有 `other_error_count` 时末行显示「其他 N 次」；点击行把端点写入样本区过滤条件。
- 区块「错误原因」：表格列 类型（副标题为 message）/ 次数 / 发生位置 / 最近一次 / 样例链（最多 3 个可点击 Trace 链接）；区块标题旁说明「按错误类型统计，一次失败请求可能对应多个错误」。
- 区块「最近失败样本」：复用调用链 Tab 的行样式，列 端点 / HTTP / 耗时 / 时间；标题写「最近 N 条」；支持按端点过滤；底部「在错误分析中打开」链接保留现有 service / environment / window 参数。
- 状态：`NO_DATA` 显示「本窗无入口请求」；`error_count = 0` 显示「本窗无失败请求」且隐藏三个列表区块；503 显示数据面不可用降级。
- 样式遵守 Web UI 硬约束：Tailwind `className`、语义 token、复用 Ant Design Table / Tag / Typography；不新增 SCSS Module。
- Tab 标题保持「错误」，无计数。

### 位置映射

`location` 由 Span kind 推导：SERVER / CONSUMER → `entry`；CLIENT / PRODUCER → `downstream`；INTERNAL / UNSPECIFIED → `internal`。UI 文案：入口 / 调下游 / 内部。

## Testing Decisions

- 只测外部行为：API 响应结构与数字、适配器发出的 LogsQL 字符串与解析结果、页面渲染出的文字与链接；不测私有函数。
- **VT 适配器**（prior art：`test_victoriatraces_adapter.py` 的 `service_red` / `search_spans` 用例，用假 session 断言 query 参数）：
  - 归因键 coalesce 优先级：exception.type > error.type > status_message > HTTP 5xx > 兜底。
  - 同 `error_type` 不同 kind 的分组正确合并，`location` 取占比最高的 kind。
  - 失败端点使用与 RED 相同的入口 + 去重模板；断言 `failed_endpoints` 合计 + `other_error_count` = `error_count`。
  - 字段名带反引号；值经 `_logsql_string` 转义。
  - 无入口请求返回 `NO_DATA` 且列表为空；上游 5xx 抛 `TelemetryStoreUnavailable`。
- **内存适配器**（prior art：`test_memory_adapters.py`、`test_span_api.py::test_memory_span_store_filters_entry_kinds`）：同一套输入得到与 VT 语义一致的结果。
- **API**（prior art：`test_red_api.py` 用 `apm_api_client` + mocker 替换 store）：
  - 正常返回全部字段；`environment` 缺失 400；未知参数 400；VT 不可用 503。
  - 组织不可见的服务 404（复用现有服务 detail 的组织过滤测试模式）。
- **Issue 服务**：删除未归因合并的测试；保留「缺 `get_trace` 仍投影为 `SpanError`」的既有行为测试。
- **前端**（prior art：`services/[serviceId]/__tests__/page.test.tsx` mock `useApmApi`；`web/scripts/apm-service-workflow-test.ts`）：
  - 切到错误 Tab 调用 `error-breakdown` 而非 `getIssues`；不再渲染「占失败样本」。
  - 三个区块渲染对应数字与文案；`error_count = 0` 只显示无失败空态；样例链链接指向 Trace 详情。
  - 点击端点行后样本区只显示该端点。
- **本机验证**：`demo-storefront` / `local` / 1h 预期：失败端点为 `POST /api/checkout` 与 `GET /api/products` 且合计 = 顶部失败数；错误原因出现 `payment_declined`（调下游）、`downstream_error`（调下游）、`server_error`（入口）、偶发 `BrokenPipeError`（入口）；页面不再出现 `SpanError`。

## Out of Scope

- 探索 · 错误分析页：仍按 Issue fingerprint 翻页，不改口径。
- Issue 持久化、全窗精确 fingerprint 去重、生命周期、认领、激增 / 回归。
- 按错误类型过滤样本（第一期用每类型自带的样例链替代）。
- 拓扑节点错误率口径、错误率公式、RED / SLO 契约。
- 对外 OpenAPI 暴露。

## Further Notes

- 本机 VictoriaTraces 字段事实（2026-09-02 验证）：exception 事件已列化为 `event:event_attr:exception.type:0` / `.message:0` / `.stacktrace:0`；`span_attr:error.type` 与 `status_message` 在全部 Error Span 上都有值；未见第二个 exception 事件（`:1`）。实施时以当前 VT 为准，若字段缺失走 coalesce 兜底即可，不需分支逻辑。
- 与错误率不同源是刻意决定，不是遗漏；实施时不要为了让「错误原因」合计等于失败数而把范围收回入口。
- 完成后更新 `docs/design/product-decisions/apm-service-error-tab.md` 的「已确认设计决策」与 `specs/capabilities/apm-function-list.md` 的错误聚合行，并将本 spec 置为 `implemented` 附完成证据。
