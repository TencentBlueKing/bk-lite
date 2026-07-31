# APM MVP Phase 0 差距审计

> 审计基线：`codex/apm-notification-design@a2c80bdaf`
>
> 审计日期：2026-07-31
>
> 契约关系：本文只保存基线事实与运行证据；目标行为、实施顺序和验收口径以同目录 `spec.md` 为唯一规范。代码变化后不通过修改历史结论掩盖基线差距，而是在实施记录中逐项关闭。

## 1. 证据范围与判定规则

Phase 0 逐项检查了以下事实入口：

- `server/apps/apm` 的模型、迁移、序列化、API、领域服务、生产适配器、运行期任务和测试；
- `web/src/app/apm` 的全部生产路由、API hook、表单、按钮、跳转、错误态和类型；
- `deploy/apm` 的 Nginx、Collector、VictoriaTraces、VictoriaMetrics、健康检查和容器契约；
- `server/support-files/system_mgmt/menus/apm.json` 的菜单与权限；
- 当前本地 Server/Web/APM 容器、HTTP 路由、Django migration state 和新鲜自动化测试。

状态定义：

| 状态 | 含义 |
| --- | --- |
| 已真实完成 | 生产代码存在，页面或 API 可操作，并有与风险相称的新鲜运行证据 |
| 只有展示壳或 mock | 路由可打开或有演示内容，但用户不能通过真实 API 完成行为，或关键链路只由内存/Mock 证明 |
| 部分完成有缺陷 | 主体存在，但遗漏了契约要求的操作、安全边界、错误语义或真实环境证明 |
| 完全缺失 | 没有可用实现或公开入口 |

文件存在、路由返回 200、单元测试使用 fake adapter 成功，均不能单独判定为“已真实完成”。

## 2. Slice 差距矩阵

| Slice | 状态 | 已有事实 | 关键缺口与证据 |
| --- | --- | --- | --- |
| Slice 1：骨架与契约 | 部分完成有缺陷 | `server/apps/apm`、8 个生产页面、3 个 APM migration、菜单/权限、四个深模块接口已经存在；APM 聚焦测试 84 项通过 | 架构边界测试只搜索 `apps.alerts`，未覆盖 Monitor、Log、System Management 内部依赖；列表 API 缺统一分页上限；接入向导未消费已有控制面 API |
| Slice 2：真实数据面 | 部分完成有缺陷 | `deploy/apm/otel/collector.yaml` 在采样前生成全量 span metrics，尾采样后写 VictoriaTraces；Nginx HTTP 入口调用机器鉴权并覆盖受信来源；`/telegraf/api` 路由未被修改 | 外部只暴露 OTLP/HTTP 4318，OTLP/gRPC 4317 没有等价的边缘鉴权入口；当前 compose 项目的 Collector 因绑定到已删除 worktree 配置而 unhealthy，尚无本分支隔离项目的真实 SDK 上报证据；Token 片段只存在服务方法，没有 API/UI 闭环 |
| Slice 3：目录与 RED | 部分完成有缺陷 | 运行期 Celery 对账、服务/实例模型与组织、归档/解档 API、VictoriaMetrics 适配器、服务/实例列表页存在 | 缺少 `service.instance.id` 时 `DjangoTelemetryCatalogService.discover` 同时放弃服务创建，违反“可见服务、不造假实例”；页面没有组织调整、手动归档/解档；RED 只有窗口标量，没有时间序列和 Top endpoint；真实 VictoriaMetrics 落库/查询未验收 |
| Slice 4：Trace 诊断 | 部分完成有缺陷 | Trace 搜索/详情 API、受控查询参数、组织过滤、不可枚举 404、属性脱敏、瀑布详情页和服务到 Trace 跳转存在 | 仅由 adapter mock/fixture 证明；没有本分支真实 OTLP → VictoriaTraces → 页面证据；数据面健康无法在 UI 区分 Collector、TraceStore、MetricStore；页面操作与响应大小还需浏览器全链验证 |
| Slice 5：基础告警 | 部分完成有缺陷 | 三类阈值策略 CRUD、启停、测试查询、运行期评估、APM 自有 Event/Alert/PolicyState、幂等 event key 已实现；策略页有真实 API | 通知仍是 NATS `receive_alert_events` 专用；没有逐渠道目标、普通通知、人类可读 payload、有限重试终态和人工重投；事件页只读；未用真实 VictoriaMetrics 触发/恢复 |
| Slice 5.1：通知渠道契约修正 | 完全缺失 | 规格已有目标设计 | System Management 目录没有 `delivery_mode`、`recipient_mode`、availability；投递没有统一 `code/retryable`；APM 仍使用 `SystemMgmtNatsAlertPublisher`、全局 `notice_type_ids/notice_users`，前端仍写“告警中心 NATS 渠道” |

## 3. 控制面 API 差距矩阵

| API | 状态 | 证据与缺口 |
| --- | --- | --- |
| `GET /api/v1/apm/ingest-sources/` | 部分完成有缺陷 | 后端按当前组织过滤；Web hook 可读，但生产页面未展示接入源管理表 |
| `POST /api/v1/apm/ingest-sources/` | 部分完成有缺陷 | `ApmIngestSourceViewSet.create` 创建源并仅在响应返回明文 Token，权限测试通过；生产页面没有表单和调用 |
| `GET /api/v1/apm/ingest-sources/{id}/` | 部分完成有缺陷 | 后端存在并受组织过滤；Web 无详情/管理入口 |
| `POST /api/v1/apm/ingest-sources/{id}/rotate/` | 部分完成有缺陷 | 后端立即替换摘要且只回传一次明文；Web 无轮换确认、复制与旧 Token 失效操作 |
| `POST /api/v1/apm/ingest-sources/{id}/disable/` | 部分完成有缺陷 | 后端存在；Web 无禁用确认/状态反馈；缺真实入口拒绝验证 |
| `PUT /api/v1/apm/ingest-sources/{id}/organizations/` | 部分完成有缺陷 | 后端有可分配组织校验；Web 无组织编辑 |
| 接入片段 API | 完全缺失 | `DjangoIngestSourceService.render_snippet` 及单测存在，但没有公开 action；页面只有硬编码接入类型卡片 |
| `GET /api/v1/apm/instances/` | 部分完成有缺陷 | 后端按组织/环境/状态过滤，页面真实读取；无分页、无接入源筛选和身份缺失诊断入口 |
| `GET /api/v1/apm/instances/{id}/` | 部分完成有缺陷 | 后端存在；页面没有实例详情路由或操作抽屉 |
| `PUT /instances/{id}/organizations/` | 部分完成有缺陷 | 后端存在；Web 无操作 |
| `POST /instances/{id}/archive/`、`restore/` | 部分完成有缺陷 | 后端存在；Web 无操作 |
| `GET /api/v1/apm/services/` | 部分完成有缺陷 | 后端按组织和环境过滤，页面真实读取；环境视图由前端展开实例推导，缺分页和服务级诊断状态 |
| `GET /api/v1/apm/services/{id}/` | 部分完成有缺陷 | 后端和详情页存在；页面仅展示摘要卡片 |
| `PUT /services/{id}/organizations/` | 部分完成有缺陷 | 后端存在；Web 无操作 |
| `POST /services/{id}/archive/`、`restore/` | 部分完成有缺陷 | 后端存在；Web 无操作 |
| `GET /services/{id}/metrics/` | 部分完成有缺陷 | 真实 VictoriaMetrics adapter 和 503 映射存在，窗口有界；响应只有 rate/error/p95/p99 标量，缺趋势与 Top endpoint |
| `GET /api/v1/apm/traces/` | 部分完成有缺陷 | 条件、时间窗、游标、limit、组织过滤和 503 存在；未以真实 VictoriaTraces 验证 |
| `GET /api/v1/apm/traces/{trace_id}/` | 部分完成有缺陷 | 组织鉴权、不可枚举 404、脱敏和 span 截断存在；未以真实存储和浏览器验证 |
| `GET /api/v1/apm/health/` | 部分完成有缺陷 | 只返回目录对账 cache；没有 Collector、VictoriaTraces、VictoriaMetrics、评估和通知投递的分项状态 |
| `GET /api/v1/apm/machine-auth/` | 部分完成有缺陷 | 无/错/禁用/旧 Token 返回 401，DB 不可用返回 503；只接入 HTTP edge，未覆盖外部 gRPC |
| `GET/POST /api/v1/apm/policies/` | 部分完成有缺陷 | 组织边界、CRUD 和页面表单存在；DTO 是旧通知字段且渠道限制为告警中心 NATS |
| `GET/PATCH/DELETE /policies/{id}/` | 部分完成有缺陷 | 后端和 Web 编辑/删除存在；缺逐渠道目标与兼容迁移 |
| `POST /policies/{id}/enable/`、`disable/` | 部分完成有缺陷 | 后端权限和 Web switch 调用真实 API，聚焦代码测试通过；缺带真实策略对象的浏览器操作与重启状态验证 |
| `POST /policies/{id}/test-query/` | 部分完成有缺陷 | 后端调用 MetricStore、页面可操作并区分 503；尚无真实指标数据验证 |
| `GET /api/v1/apm/events/` | 部分完成有缺陷 | 读取 APM 自有事件并按组织过滤；无分页/详情/关联 Trace，尚无真实触发恢复证据 |
| `GET /api/v1/apm/notification-channels/` | 只有展示壳或 mock | API 和 UI 存在，但公开的只是 `receive_alert_events` NATS 目录，不是通用渠道能力 |
| outbox 查询/人工重投 API | 完全缺失 | 模型与任务只有 pending/delivered；无终止失败、错误审计或人工重投 |

## 4. 生产路由差距矩阵

所有下列路由在当前本地 Web 上返回 HTTP 200；这只证明路由可达。浏览器实查 `/apm/integration/add` 和 `/apm/policies` 后按可操作性判定如下。

| 路由 | 状态 | 用户可完成的真实行为与缺口 |
| --- | --- | --- |
| `/apm/integration/add` | 只有展示壳或 mock | `integration/add/page.tsx` 只有硬编码语言/基础设施卡片和跳转按钮；不能选组织、创建源、查看一次性 Token、复制片段、轮换或禁用 |
| `/apm/integration/instances` | 部分完成有缺陷 | 可真实查询/过滤实例；不能打开详情、编辑组织、归档/解档、查看接入源或身份诊断 |
| `/apm/services` | 部分完成有缺陷 | 可真实查询服务/环境视图并跳详情；不能编辑组织、归档/解档，状态仅基于目录字段 |
| `/apm/services/[serviceId]` | 部分完成有缺陷 | 可查详情、RED 标量并携带条件跳 Trace；缺趋势图、Top endpoint、管理操作和完整降级诊断 |
| `/apm/traces` | 部分完成有缺陷 | 有真实筛选、搜索、分页游标和错误态；没有真实 VictoriaTraces 数据证明 |
| `/apm/traces/[traceId]` | 部分完成有缺陷 | 有瀑布/属性详情和错误态；没有真实 Trace 端到端证明 |
| `/apm/policies` | 部分完成有缺陷 | CRUD、编辑、删除、启停和测试查询调用真实 API；通知表单/文案是 NATS 告警中心旧模型 |
| `/apm/events` | 部分完成有缺陷 | 可真实查询/过滤 APM 事件；缺真实策略触发/恢复、通知状态和人工补偿入口 |

`web/src/app/apm` 未发现生产代码 import Storybook story/fixture；当前问题是功能缺失和硬编码展示内容，不是 fixture 直接泄漏。旧 Storybook 仍有“不签发 Token”的过期口径，实施时必须同步清理或隔离，不能反向覆盖本规格。

## 5. 验收场景基线矩阵

下表编号对应 `spec.md` 的“必须覆盖的验收场景”。

| 场景 | 状态 | 基线证据/缺口 |
| --- | --- | --- |
| 1 | 部分完成有缺陷 | 配置测试证明 `/telegraf/api` 未重叠，HTTP OTLP 独立；外部 gRPC 未鉴权暴露，未真实双协议上报 |
| 2 | 部分完成有缺陷 | 机器鉴权单测覆盖无效/禁用/轮换；Collector 配置测试覆盖保留字段覆盖；没有页面一次性 Token 与真实边缘验证 |
| 3 | 部分完成有缺陷 | ORM 对账测试覆盖多实例/单服务；没有真实三个 SDK 实例链路 |
| 4 | 部分完成有缺陷 | 归档/解档领域测试存在；Web 无操作，未真实重建 Pod 验证 |
| 5 | 部分完成有缺陷 | 组织继承/自定义领域测试存在；Web 无组织管理 |
| 6 | 部分完成有缺陷 | 服务/实例组织隔离 API 测试存在；未用真实 Trace 与 UI 证明 |
| 7 | 部分完成有缺陷 | 后端环境过滤测试存在；“全部环境”由页面推导，未真实数据证明 |
| 8 | 部分完成有缺陷 | Collector 静态配置测试存在；未对 VictoriaMetrics/Traces 实际数量和采样结果取证 |
| 9 | 部分完成有缺陷 | adapter query 单测覆盖 histogram quantile/有限维度；缺真实 RED 趋势与 endpoint 数据 |
| 10 | 部分完成有缺陷 | Trace/指标配置允许缺 instance；目录实现错误地连服务也不创建，且无 UI 诊断 |
| 11 | 部分完成有缺陷 | API 单测覆盖组织、不枚举和脱敏；缺真实存储/浏览器验证 |
| 12 | 部分完成有缺陷 | 评估幂等与存储失败测试存在；通知没有有限重试终态和人工重投 |
| 13 | 部分完成有缺陷 | 启动边界静态测试存在；当前 Collector unhealthy；未验证 Alerts 未安装、responder 缺失和重启恢复 |
| 14 | 部分完成有缺陷 | Trace/RED API 区分 503/空数据且查询有界；目录列表、事件和通知审计缺分页/响应上限，UI 健康维度不足 |
| 15 | 部分完成有缺陷 | 生产页面未 import story，菜单/动态路由测试通过；接入页仍是死页面，主要操作/中英文/错态未完整覆盖 |
| 16 | 完全缺失 | 只能选择告警中心 NATS，不能多渠道独立投递 |
| 17 | 部分完成有缺陷 | 当前生产代码未发现跨 App 模型 import；自动化只检查 Alerts 字符串，未验证 Alerts 完全缺失时运行 |
| 18 | 完全缺失 | 通用渠道目录、失效终态、有限重试均未实现 |
| 19 | 完全缺失 | 前端仍使用“告警中心 NATS 渠道”和全局接收人字段 |

## 6. 数据面、部署与本地运行证据

### 6.1 已确认配置事实

- `deploy/apm/nginx/apm.conf.template` 对外暴露 OTLP/HTTP，调用 `/api/v1/apm/machine-auth/`，移除外部内部身份 Header，并将认证结果写入 Collector 请求。
- `deploy/apm/otel/collector.yaml` 在 tail sampling 前运行 spanmetrics，限定维度、队列和批处理，删除请求/响应正文与敏感属性，Trace 写 VictoriaTraces、指标写 VictoriaMetrics。
- `deploy/apm/compose.yaml` 将 VictoriaTraces、Collector、edge 独立于 Server；VictoriaMetrics 可复用外部地址，standalone profile 可本地启动；未修改 `/telegraf/api`。
- Server 的目录对账和策略评估由 Celery beat 在运行期触发；`batch_init` 未调用 APM 外部依赖。

### 6.2 新鲜命令结果

| 命令/检查 | 原始结论 |
| --- | --- |
| `NEXTAPI_INSTALL_APP=apm pnpm type-check` | exit 0 |
| `NEXTAPI_INSTALL_APP=apm pnpm test:apm-dynamic-route-permission` | `APM dynamic route permission checks passed` |
| `NEXTAPI_INSTALL_APP=apm pnpm test:apm-menu-route` | `APM menu route checks passed` |
| `INSTALL_APPS=system_mgmt,alerts,apm ... SECRET_KEY=test-secret uv run pytest apps/apm/tests -q --nomigrations --create-db` | `84 passed in 45.05s`；证明当前代码行为，不证明 migration 链 |
| `ENABLE_CELERY=True ... uv run python manage.py makemigrations --check --dry-run` | `No changes detected` |
| 使用正常 migration 运行 APM tests | 数据库 setup 阶段 `29 passed, 55 errors`，被仓库既有非 APM migration state 错误 `NewSessionEventRelation has no field named 'event'` 阻断；最终验收必须在真实 PostgreSQL/完整 App 集合重做，不能以 `--nomigrations` 替代 |
| `docker compose -f deploy/apm/compose.yaml config --quiet` | exit 0 |
| `RUN_APM_CONTAINER_CONTRACT` 未设置的容器契约测试 | 默认 skip，不能算通过 |
| 本地 HTTP | `/apm/{integration/add,integration/instances,services,traces,events,policies}` 均 200；`/api/v1/apm/health/` 未登录返回 401；edge `/healthz` 与 VictoriaTraces `/health` 返回 200 |

当前机器已有同项目名但来自其他 worktree 的 APM compose：edge/VictoriaTraces healthy，Collector unhealthy。Collector 主日志曾报告 ready，但 healthcheck 持续失败，容器 bind mount 指向已经删除的 worktree 路径。该状态说明复用同名本地项目会制造假阳性/假阴性；实施验收必须使用唯一 compose project 名、当前绝对路径和新卷启动，不停止或修改其他 worktree 的容器。

## 7. 已确认冲突与推荐决定

没有发现需要用户选择的权限、数据身份或外部部署边界冲突；以下均按主规格的安全边界直接决定：

1. **缺实例身份的目录行为冲突**：现有测试把“不创建任何目录行”当作正确行为，规格要求“创建/更新逻辑服务但不创建伪实例”。以规格为准，修改实现与测试。
2. **gRPC 边界缺口**：不把 Collector 内部 4317 直接暴露。由 edge 增加 HTTP/2 gRPC listener，复用机器鉴权、内部 Header 清理和受信来源注入；认证不可用时 fail closed。
3. **一次性 Token 与片段生成**：创建/轮换响应只返回一次明文；片段生成 API 接收当前浏览器内存中的 Token 与受限模板参数，验证 Token 后即时渲染，不持久化、不记录日志。关闭弹窗/刷新即无法再次取回，只能轮换。
4. **服务 RED**：扩展既有 metrics action，返回同一有界窗口的 summary、timeseries 和 Top endpoint，避免再暴露 PromQL；现有标量字段保留一轮兼容。
5. **通知兼容**：新增逐渠道目标与 outbox 状态，旧策略通知字段仅作为滚动升级读兼容；新写入只走目标表。System Management 公开契约先向后兼容扩展，再切 APM 后端/前端。
6. **健康与启动**：健康 API 只报告运行期组件状态，不将任何外部探测加入 `batch_init` 或 Server 启动门禁。
7. **迁移基线异常**：不修改与 APM 无关的历史业务迁移来掩盖错误；最终在项目支持的 PostgreSQL 初始化路径上验证。若仍失败，单独报告仓库基线阻断和原始日志。

## 8. Phase 0 关闭条件

Phase 0 在以下条件同时满足后关闭：

- 本差距矩阵与 `spec.md` 的目标范围、纵向实施切片、完整测试矩阵互相一致；
- 每个已有 API、生产路由和 19 条验收场景都有明确基线状态；
- 安全/权限/部署冲突有唯一推荐决定，且没有被通知子项取代主目标；
- 文档单独提交，随后按“接入闭环优先”的切片开始编码。
