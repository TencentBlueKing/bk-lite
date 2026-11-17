# APM 首页与服务列表按服务分组读取聚合库

Status: done

来源：2026-11-11 对 APM / RUM 聚合架构的复核。`observability-aggregate-hardening` 的 Out of Scope 里留下的
P2「Server 按服务批量查询聚合库（去掉首页 40 个目标的限制）」由本变更承接，并补上首页数字口径和页面提示。

## Problem Statement

聚合起点覆盖查询窗口后，APM 首页和服务列表已经改读聚合库，但仍然沿用为 VictoriaTraces 设计的「逐服务查询」：

1. **首页一次打开发出约 400 次 PromQL。** 首页先把可见服务截到 40 个「服务 × 环境」目标，再用 8 个线程逐个调用单服务 RED。
   聚合路径下每个有请求的目标要查 6 次即时查询和 4 次区间查询。服务列表的批量接口同样逐个查询，前端每批 40 个。
2. **首页 KPI 和健康分布只统计前 40 个目标。** 第 41 个之后的服务不计入请求量、错误量，也不进入健康分布和 Top 列表。
3. **首页 KPI 的 p95 不是真的 p95。** 现在是把各服务的 p95 按请求量加权平均，趋势小图则是各服务 p95 的算术平均。
4. **聚合数字偏少时页面无从得知。** 聚合消费者积压超过 5 分钟的 Span 被记为晚到，不进入 RED；某个服务入口组合超过
   `APM_AGG_CARDINALITY_LIMIT` 后，多出的入口进入溢出序列，也不计入该服务。两者都只有运维告警，页面上看到的是「流量下降」。

## Solution

- 聚合起点覆盖窗口时，首页和服务列表批量接口改为**按服务分组的少量查询**：用 `job`（「命名空间/服务名」）的精确正则把
  查询收窄到已授权的服务，按 `service_namespace`、`service_name`、`deployment_environment` 分组返回，在 Server 里拆回各目标。
- 首页在聚合路径下覆盖**全部可见服务**，KPI 的请求量、错误量由各目标求和，p95 和 p95 趋势由合并后的直方图桶计算。
- 首页显示窗口级提示：晚到 Span 数、入口组合超限的服务数。服务列表在入口超限的服务上打标记。
- 窗口早于聚合起点、聚合库未配置或未记录起点时，首页与批量接口**完全保持现状**（逐目标读 VictoriaTraces、40 个上限）。

## User Stories

1. 作为运维，我打开 APM 首页任意时间窗，聚合覆盖时页面只发出与服务数无关的少量聚合查询，打开速度不随服务数增长。
2. 作为运维，聚合覆盖时，首页 KPI、健康分布和 Top 列表统计全部可见服务，不止前 40 个。
3. 作为运维，首页 KPI 的 p95 及其趋势是全部入口请求合在一起的分位数。
4. 作为运维，窗口内有晚到 Span 未计入时，首页告诉我「这段时间有 N 个晚到 Span 没有计入请求数」，我不会误以为流量下降。
5. 作为运维，某个服务的入口组合超过上限时，首页提示超限服务数，服务列表在该服务上标出「入口超限」。
6. 作为运维，服务列表每批 RED 在聚合覆盖时只发出一组分组查询，批内单服务不可见时仍单独显示不可见，聚合库故障时整批降级。
7. 作为租户用户，分组查询只会返回我有权看到的服务，其他服务的数字不会出现在页面或接口里。

## Implementation Decisions

### 分组读取模块（聚合 RED 适配器）

- 在现有聚合 RED 适配器里新增分组读取，路由器（`ApmAggregateRedRouter`）对外新增一个方法，入参是已授权服务列表
  （命名空间、服务名，均为数据库原值）、窗口起止、是否需要首页总览和总览点数；返回 `None` 表示未覆盖或聚合库未配置，
  调用方走原有逐目标路径。覆盖判断与单服务完全一致（聚合可用、已记录起点、窗口起点不早于起点）。版本、实例、慢请求、
  Apdex 不进入分组读取。
- 返回结构放在服务契约模块，形状如下（字段名可微调，语义不变）：

  ```python
  @dataclass(frozen=True)
  class GroupedRedOverview:
      request_rate: float | None          # 全部目标请求数 / 窗口秒数
      error_request_rate: float | None    # 全部目标错误数 / 窗口秒数
      p95_ms: float | None                # 合并直方图桶后的分位数
      request_trend: tuple[float | None, ...]
      error_trend: tuple[float | None, ...]
      p95_trend: tuple[float | None, ...]
      late_spans: int | None              # 窗口内晚到 Span 数；无样本为 None

  @dataclass(frozen=True)
  class GroupedRed:
      # 键：(namespace, name) 为数据库原值；environment 为序列上的原始标签值（空环境写作 unknown）
      by_target: dict[tuple[str, str, str], ServiceRed]
      truncated_services: frozenset[tuple[str, str]]     # 窗口内出现溢出序列的 (namespace, name)，数据库原值
      overview: GroupedRedOverview | None
  ```

- 调用方注入的 RED 存储没有分组读取方法时（例如现有测试桩），按「未覆盖」处理，走逐目标路径。

- **选择器**：`job=~"<alt>"`，`<alt>` 是已授权服务 `job` 值的精确正则并集，`job` 值为
  `f"{namespace or 'unknown'}/{name or 'unknown'}"`，与采集端把空命名空间写成 `unknown` 的规则一致。RED 相关序列另加
  `service_name!=""`，把没有服务名的溢出序列排除在请求数之外。晚到计数没有 `service_name`，只用 `job` 收窄。
- **正则转义**：只转义 RE2 元字符 `\ . + * ? ( ) | [ ] { } ^ $`，再做 PromQL 字符串转义。不要用 Python `re.escape`：
  它会转义空格等字符，RE2 不接受这些转义。正则转义函数放在聚合 PromQL 客户端模块，与现有标签转义函数并列。
- **分块**：按服务切块，每块生成的任一 PromQL 不超过 12 KiB，保证低于 VictoriaMetrics 默认 `-search.maxQueryLen`（16 KiB）。
  每块独立查询，结果在 Server 合并；各块的 `job` 集合互不相交，求和不会重复。
- **每块查询**（窗口值为对齐后的整窗秒数，结束时间沿用现有对齐规则）：
  - 按目标分组的即时查询 6 条：请求数、错误数（`status_code="STATUS_CODE_ERROR"`）、耗时总和、耗时计数、p95、p99。
    p95、p99 用 `histogram_quantile(φ, sum by (le, service_namespace, service_name, deployment_environment) (increase(...)))`，每个目标一条结果。
  - 溢出 1 条：`sum by (job) (increase(apm_calls_total{job=~"<alt>", otel_metric_overflow="true"}[w])) > 0`。
  - 仅在需要总览时：全局桶 `sum by (le) (increase(apm_duration_milliseconds_bucket{...}[w]))` 1 条；晚到
    `sum(increase(apm_aggregate_late_spans_total{job=~"<alt>"}[w]))` 1 条；趋势区间查询 3 条（请求数、错误数、`sum by (le)` 桶）。
    趋势步长取 `max(APM 刷出秒数, ceil(窗口秒数 / 点数))`，区间从「起点 + 一个步长」到对齐后的结束时间（与 RUM 目录相同），
    结果按点数重采样。
- **结果映射**：只接受 `(service_namespace, service_name)` 标签能映射回已授权服务的序列（服务按
  `(namespace or "unknown", name)` 建索引，与单服务路径的精确匹配一致）；映射不上的序列（包括其他租户的同名序列）直接丢弃。
  环境保留原始标签值：批量接口用 `environment or "unknown"` 查找；首页把 `unknown` 显示回空环境，与现在按实例环境展示一致。
  目标没有请求时不出现在 `by_target` 中，调用方按无数据处理，不当 0。
- **总览求和按序列去重**：总览的请求数、错误数和桶按「通过授权映射的序列」各计一次，不按数据库服务累加。
  空命名空间与名为 `unknown` 的命名空间可能对应同一条序列，按服务累加会重复计数。
  `ServiceRed` 字段与单服务聚合路径一致：`request_rate`、`error_rate`、`p95_ms`、`p99_ms`、`request_count`、`error_count`、
  `avg_ms`，`max_ms` 为空，`timeseries`、`top_endpoints` 为空。
- **总览分位数**：在 Server 用纯函数从合并后的桶计算，语义与 Prometheus `histogram_quantile` 一致：按 `le` 升序；总数
  （`+Inf` 桶）为 0 返回 `None`；落在 `+Inf` 桶时返回最大有限上界；第一个桶下界为 0；桶内线性插值；累计值非单调时取前缀最大值。
- **失败语义**：任一查询失败，整次分组读取抛出与单服务一致的 `TelemetryStoreUnavailable` / `TelemetryQueryTooLarge`，
  不回退扫明细。新代码不记录 PromQL 表达式、服务列表或响应正文。

### 聚合 PromQL 客户端

- 即时查询和区间查询改用 POST 表单提交（VictoriaMetrics 的 `/api/v1/query`、`/api/v1/query_range` 支持），其余行为不变：
  基础认证、超时、`allow_redirects=False`、2 MiB 响应上限、错误阶段名。APM、RUM 和起点探测共用这个客户端，一并生效。

### 首页

- 首页服务先取全部可见服务的（id、命名空间、服务名、`last_seen_at`、`archived_at`），调用分组读取（需要总览，点数取当前窗口的
  小图点数）。拿到结果时：
  - 目标 = 分组结果里出现的全部「服务 × 环境」；在窗口内没有结果的服务按现有规则记为「未知」健康档，不进入 Top 列表。
  - KPI：请求量、错误请求量、p95 和三条小图都取总览；应用数、服务数、活动告警数仍查数据库，计算方式不变。
  - 健康分布、错误率 Top、p95 Top 用全部目标，排序和条数规则不变。
  - 响应新增顶层字段 `aggregate_notice`：`{"late_spans": int | null, "truncated_service_count": int}`。
    走逐目标路径时为 `null`。
- 分组读取返回 `None` 时，现有逐目标路径（40 个上限、线程池、加权 p95）一字不改。
- 分组读取失败时，与现在的存储错误一样：KPI 的 RED 数字为空，健康、Top 区块标为失败，`aggregate_notice` 为 `null`。

### 服务列表批量接口

- `include_breakdown=false` 且分组读取覆盖时，一批目标走一次分组读取（不需要总览）。每项载荷与现在相同，另加
  `entry_truncated: bool`。不可见服务仍返回 `not_found`，服务名为空仍返回 `invalid_query`，与单服务校验一致；
  聚合失败时每个可见项返回与现在相同的遥测错误载荷。
- `include_breakdown=true`（应用观测卡片的趋势）、未覆盖、未配置时，保持现有逐目标路径，`entry_truncated` 为 `false`。
- 单批上限 40 和前端按 40 分批都不改，以保留「一批失败只标记该批」的行为。

### 前端

- 类型：`ApmDashboard` 增加可选 `aggregate_notice`；批量项增加可选 `entry_truncated`。
- 首页：`aggregate_notice` 存在且晚到数大于 0 或超限服务数大于 0 时，在 KPI 行上方显示一条 Ant Design `Alert`（`type="info"`、
  `showIcon`），按条件拼两句：「这段时间有 {count} 个晚到 Span 没有计入请求数」「{count} 个服务的入口组合超过上限，多出的入口没有计入该服务」。
- 服务列表：任一指标项 `entry_truncated` 为真时，在该服务（服务视角的行、应用视角下对应的服务）上显示 Ant Design `Tag`
  「入口超限」，颜色用语义 token，悬停说明「入口组合超过上限，多出的入口没有计入该服务」。
- 文案走现有 `t(key, fallback)`，中英文都补到 APM 的 locales。布局遵守 `AGENTS.md` 的 Web UI 硬约束，不新增 SCSS。

### 文档与长期规范

- 聚合库运维规则：写明 Server 批量读取用 `job` 精确收窄到已授权服务，同时要求 `service_name` 非空，溢出序列仍不计入任何
  服务的 RED，按服务和环境分组的口径不变；Server 用 POST 查询，单条查询低于 16 KiB，不要把 `-search.maxQueryLen` 调小。
  `deploy/apm/README.md` 里「Server 查询仍按服务名和环境，不改成按 `job`」一句同步改成同样的表述。
- APM 功能清单的「首页总览」「RED 指标」两行：聚合覆盖时首页统计全部可见服务，KPI p95 是合并直方图的分位数，首页有晚到
  与入口超限提示，服务列表有入口超限标记；回退到明细时仍是前 40 个目标。

## Testing Decisions

- 只测外部行为：分组读取的返回值与生成的查询形状、首页与批量接口的响应、页面渲染。不测内部私有函数的调用顺序，
  总览分位数的纯函数除外。
- **分组读取**（先例：`apps/apm/tests/test_aggregate_red.py` 的伪造客户端，记录表达式并按表达式返回结果）：
  - 一块时查询数固定：不带总览 7 条，带总览 12 条，与服务数无关。
  - `job` 正则精确：服务名含 `.`、`+`、`"`、`\`、空格、中文时，表达式合法且只命中原值；空命名空间生成 `unknown/<name>`。
  - RED 查询都带 `service_name!=""`；晚到查询不带。
  - 伪造客户端返回未授权服务、其他命名空间同名服务、溢出序列时，这些序列不出现在结果里，也不进入总览。
  - 空环境目标在批量接口按 `unknown` 标签取到数据；名为 `unknown` 的真实环境同样取到数据。
  - 2000 个长服务名时切成多块，每条表达式都小于 16384 字节，跨块求和、合并桶后的总览与单块一致。
  - 未配置、未记录起点、窗口早于起点返回 `None`；任一查询失败抛 `TelemetryStoreUnavailable`，响应过大抛 `TelemetryQueryTooLarge`。
  - 总览分位数纯函数：桶内插值、全部落在 `+Inf`、空桶、第一桶下界为 0、累计非单调。
- **首页服务**（先例：`apps/apm/tests/test_dashboard_service.py`）：60 个可见服务、聚合覆盖时 KPI、健康、Top 覆盖全部服务，
  且不再调用单服务 RED；KPI p95 等于合并桶分位数，不是加权平均；`aggregate_notice` 数值正确；未覆盖时现有测试全部保持通过
  （仍不超过 40 次单服务调用）；分组读取失败时区块降级、通知为空。
- **批量接口**（先例：`test_aggregate_red.py` 里 `apm_api_client` + `monkeypatch` 的接口测试）：覆盖时一批只触发一次分组读取；
  `entry_truncated` 正确；租户外服务仍是 `not_found`；聚合失败时每项是遥测错误；`include_breakdown=true` 仍走逐目标路径。
- **客户端**（先例：`apps/core/tests/test_aggregate_promql_client.py` 和 `test_aggregate_origin_probe.py` 的伪造会话）：
  改为断言 POST 表单、认证、超时、响应上限与错误阶段名不变。
- **采集端契约**：`deploy/apm/tests/test_aggregate_contract.py` 增加一个空命名空间的入口 Span，断言其 `job` 为 `unknown/<name>`，
  并断言晚到计数序列带 `job`。有 Docker 时跑 `make -C deploy/apm contract`；没有 Docker 时在完成证据里写明未跑。
- **前端**（先例：`web/src/app/apm/home/__tests__/page.test.tsx`、`web/src/app/apm/services/__tests__/page.test.tsx`）：
  首页在有通知时渲染提示、为空或为 0 时不渲染；服务列表在 `entry_truncated` 时渲染标记。
- 验证命令：
  - Server：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/apm/tests apps/core/tests apps/rum/tests --no-cov`。
    改代码前先在同一命令上记录基线失败，完成后对照，不新增失败。
  - 采集端：`make -C deploy/apm test validate`，按上条决定是否跑 `contract`。
  - Web：`cd web && pnpm lint`、`pnpm type-check`、`pnpm test:apm-home-workflow`、`pnpm test:apm-service-workflow`、`pnpm test:apm-i18n`。
    `pnpm lint` 若有既有基线错误，只确认本次改动的文件不新增错误。
- 不连接本机正在用的 8428、9428、10428，不操作用户正在运行的 `bk-lite-apm-*`、`bklite-dev-*` 容器。

## Out of Scope

- 回退到 VictoriaTraces 时的 40 个上限、加权 p95 和截断提示。
- 应用观测卡片（`include_breakdown=true`）的分组读取；服务详情页的晚到与超限提示。
- 告警策略、慢请求、Apdex、延迟 SLO 读聚合库；可用性 SLO 的读取方式。
- RUM 网关、路由准入、Redis、聚合库部署与容量。平台 Redis 是否会淘汰 `ops:rum:v2:*` 由运维确认，不在本变更改代码。
- 起点探测、窗口整段回退规则、刷出间隔、单节点、不去重等已确认决策。

## Further Notes

- 依赖 `observability-aggregate-metrics` 与 `observability-aggregate-hardening`（均已完成并合入）。聚合库尚未在生产部署，
  本变更在聚合库上线、起点记录后才生效。
- 执行顺序：
  1. 客户端改 POST，加正则转义；分组读取与总览分位数；对应测试。
  2. 首页与批量接口接入分组读取，新增 `aggregate_notice`、`entry_truncated`；对应测试。
  3. 前端提示与标记、locales、前端测试。
  4. 采集端契约断言；运维规则、`deploy/apm/README.md`、APM 功能清单。
- 每一步完成后用中文提交一次；完成后把本文件 `Status` 改为 `done`，并在文末追加 `## Completion evidence`，
  写明各验证命令的结果和基线对照。

## Completion evidence

本机 `server/.env` 的 `INSTALL_APPS` 不含 cmdb，pytest-dotenv 会让 Django 在收集阶段失败。下面的 Server 结果都额外加了空的 `INSTALL_APPS=`，让 dotenv 不再覆盖，从而加载全部应用。规格原文那条命令不加这个变量时，基线和完成后都是退出码 1、0 个用例：`AutoRelationPending` 没有 `app_label` 且不在 `INSTALLED_APPS`。

- Server 基线（`INSTALL_APPS=` + 规格中的 sqlite 变量，`uv run pytest apps/apm/tests apps/core/tests apps/rum/tests --no-cov`）：36 failed，2511 passed，21 skipped，132.43s。
- Server 完成后同一命令：36 failed，2536 passed，21 skipped，130.56s。失败名单与基线相同，没有新增失败；多出的 25 个通过来自本变更的新测试。日志里另有 `tests/test_application.py` 和 `dev/test_embedded.py` 的嵌套 FAILED 行，不在这 36 条里。
- `make -C deploy/apm test`：三个 Go 包测试通过。
- `make -C deploy/apm validate`：第一次在构建采集镜像时因 Alpine 仓库 TLS 失败；重试构建成功后，compose 配置和四份采集配置校验通过，退出码 0。
- `make -C deploy/apm contract`：5 passed，1 failed，225.31s。失败的是 `test_data_plane_contract.py` 的 Django 启动，原因与上面的 `INSTALL_APPS` 相同，用例体没有跑到。五个聚合契约用例通过，包含空命名空间 `job=unknown/blank-ns` 和晚到计数带 `job`。使用独立 Compose project 和随机端口，没有连接 8428、9428、10428。
- `cd web && pnpm lint`：退出码 0。102 条既有 warning、0 error，本次改动的 APM 文件没有新增问题。
- `cd web && pnpm type-check`：退出码 0。
- `pnpm test:apm-home-workflow`：11 passed。
- `pnpm test:apm-service-workflow`：114 passed。
- `pnpm test:apm-i18n`：失败，报错都在既有文件（`duration-share-bar.tsx`、告警详情、策略编辑器、调用链详情），本次改动的文件不在错误列表里。
