# OpsPilot bklite 域内 App LLM 工具补充与验证

Status: implemented

## Completion Evidence

- 2026-09-11：技能 **376**「LLM Tools E2E」（`http://localhost:3001/opspilot/skill/detail/settings?id=376`）真实对话，四包均打到 NATS 并返回业务数据。缺对话、工具层单测或 NATS handler 单测任一项都不算收口。
  - **告警**：问未处理告警 → `alerts_list_alerts` 返回 `ALERT-LLM-E2E`（critical / web-1 / unassigned）。再问详情与关联事件 → 标题 LLM e2e cpu high，事件 `EVENT-LLM-E2E`。
  - **日志**：列分组并搜 timeout → `default`、`llm-e2e`，命中 nginx/postgres timeout（VictoriaLogs `:9428`）。`log_search_raw` 搜 timeout → **8** 条。
  - **监控**：`monitor_list_objects` 工具层瘦身后列对象类型 → 94 类。问 web-1 最近 CPU 且省略 start/end → `monitor_list_object_instances` 命中 web-1，`monitor_query_metric_data` 返回 **18.5% → 23.5% → 28.5% → 29.5%**（工具层默认近 1 小时并把秒/毫秒/ISO 归一成毫秒）。
  - **CMDB**：列模型 → `llm_e2e_host`；创建 `web-llm-e2e` 成功，UUID `32e9cf14-207d-48ba-82b7-e8192fe82ce0`。再改 `inst_name` 为 `web-llm-e2e-renamed`、查询确认、`cmdb_delete_instance` 删除，三步均 `success=true`。
- 图库：远端 FalkorDB TCP 通但当前 `.env` 口令认证失败；本机无 Docker/Podman。本地 Neo4j 4.4（`:7687`）作 GraphClient 回落。`search_models_for_llm` 查出后再进程内 `_llm_has_model_view` 过滤。Cypher 成员列表：有 `FALKORDB_HOST` 才用 `typeof`，否则 Neo4j 用 `CASE WHEN n.field IS NULL THEN [] ELSE n.field END`。`Neo4jClient.set_entity_properties` 补 `attrs=None`，与 FalkorDB 客户端签名对齐（未改 InstanceManage 权限逻辑）。
- 单测（`--nomigrations --create-db --no-cov`）：四包工具+handler 此前约 **165 passed**。本轮增量：`test_monitor_tools.py` **63 passed**；`test_format_type.py` + `test_neo4j_client.py`（含 `attrs` 签名）**52 passed**。

## Problem Statement

OpsPilot 的技能可以挂 LLM 工具做 function calling，但面向 bklite 平台自身四个核心 app 的工具覆盖不全、通道不统一：

- **监控中心**：已有 7 个只读查询工具（`metis/llm/tools/monitor/`），走 NATS RPC + `caller_identity`，但没有按用户场景做过够用性评估，端到端验证缺失。
- **告警中心（alerts app）**：没有专用工具，只能通过 monitor 工具查「监控策略产生的告警」，统一告警中心的数据查不到。
- **日志中心**：完全没有工具。
- **CMDB**：约 20 个增删改查工具代码已写完（`metis/llm/tools/cmdb/`），但直接 import `InstanceManage` / `ModelManage`（同进程 service），且在 `tools_loader.py` 中注释关闭，未启用。

## Solution

补齐四个 app 的 LLM 工具并逐一验证，**所有工具统一通过 NATS RPC 调用目标 app，禁止直接 import 其他 app 的模块**：

1. **监控中心**：以用户场景清单评估现有 7 个工具的够用性，缺则补；补齐单测与端到端验证。
2. **告警中心**：新建只读查询工具包（告警列表 / 详情 / 关联事件），alerts app 侧按需补 NATS handler。
3. **日志中心**：新建工具包——结构化查询工具打底（数据流/时间范围/关键词/条数上限等结构化入参，查询语句由工具内部拼装）+ 一个接受原生查询语句的「高级查询」工具。
4. **CMDB**：现有工具从直接 import 改造为 NATS 调用后启用；增删改查全量放开；CMDB NATS handler 能力缺口（如拓扑、全文检索、模型属性查询）按需补齐，并确保 handler 侧有身份透传与权限校验。

注册方式统一照 monitor 模式：`TOOL_MODULES`（`tools_loader.py`）+ `services/builtin_tools.py` 内置分类，log / alerts / cmdb 各建一个分类，与 monitor 并列，不依赖 `parse_tools_yml` 管理命令同步。

## User Stories

1. As a 运维人员, I want 在对话中问「XX 实例最近的 CPU 使用率」并得到真实监控数据, so that 不用切到监控中心页面手查。
2. As a 值班人员, I want 问「现在有哪些未处理的告警」并看到统一告警中心的列表与详情, so that 快速掌握值班态势。
3. As a 排障人员, I want 用自然语言让智能体按时间范围和关键词搜日志，必要时写原生查询语句, so that 缩短故障定位路径。
4. As a 资产管理员, I want 通过对话完成 CMDB 资产的增删改查, so that 常规资产维护不必进 CMDB 页面。
5. As a 平台管理员, I want 所有工具都带调用者身份并在服务端做权限校验, so that LLM 工具不会成为越权通道。

## Implementation Decisions

### 统一约束

- **通道**：工具 → `apps/rpc/*` RPC 客户端 → 目标 app NATS handler。禁止工具直接 import monitor / log / alerts / cmdb 的 service 或 model。
- **身份与权限**：沿用 monitor 模式，`configurable.caller_identity`（username / domain / team_id / include_children）由 `services/caller_identity.py` 捕获并透传到 NATS 参数；无身份则工具拒绝执行。权限判定在目标 app 的 NATS handler 侧完成（服务端兜底），handler 缺权限校验的必须补上。
- **注册**：新工具模块加入 `tools_loader.TOOL_MODULES`；`services/builtin_tools.py` 增加 log / alerts / cmdb 内置分类，用户在技能配置中直接勾选。
- **够用性基准**：以「典型用户问答场景清单」为准，不追求覆盖后端能力全集。每个模块开工时先起草场景清单并经用户确认，场景映射不到工具的即为补充项。

### 监控中心（第 1 批，先行跑通方法论）

- 现有 7 个工具（`monitor_list_objects` / `monitor_list_object_instances` / `monitor_list_object_metrics` / `monitor_list_instance_metrics` / `monitor_query_metric_data` / `monitor_list_active_alerts` / `monitor_query_alert_segments`）为基础，按场景清单评估缺口。
- 本批同时固化「场景清单 → 够用评估 → 单测 → 端到端验证」的方法论，供后三批复制。

### CMDB（第 2 批）

- `metis/llm/tools/cmdb/` 现有工具逐个改造：service 直调 → `apps/rpc/cmdb.py` RPC 调用；`cmdb/nats/nats.py` 已有 `search_instances` / `list_instances` / `search_models` / `create_instance` / `update_instance` / `delete_instance` 等 handler，能力不足的（拓扑、全文检索、模型属性等）在 cmdb app 侧补 handler。
- **增删改查全量放开**：查询、创建、更新、删除工具都默认可勾选；安全完全依赖服务端权限校验（操作人身份透传，按 CMDB 权限规则判定），不在工具层做额外限制。
- 改造完成后解除 `tools_loader.py` 中的注释，正式注册。

### 告警中心（第 3 批）

- **只读**：告警列表（按状态 / 级别 / 时间等过滤）、告警详情、告警关联事件。不做认领 / 分派 / 关闭等处置操作（本期明确排除）。
- alerts app 现有 NATS handler 偏运营统计（`get_alert_*` 趋势/分布类），列表/详情/事件类查询按需新增 handler，业务逻辑可参照 `open_api/services.py` 的 `AlertsOpenAPIService`，但暴露通道是 NATS。

### 日志中心（第 4 批）

- 结构化查询工具：入参为数据流/分组、时间范围、关键词、条数上限等结构化字段，工具内部拼装查询语句；复用 `log/nats/log.py` 的 `log_search` / `log_hits` 等 handler，必要时补参数。
- 高级查询工具：接受原生查询语句字符串，供复杂场景使用；服务端仍按调用者身份做访问范围过滤。

### 交付批次

监控 → CMDB → 告警 → 日志，一个模块一批交付（工具代码 + 单测 + 端到端验证 + 场景清单核销），逐批确认后再进下一批。

## Testing Decisions

每个工具两层单测 + 一层端到端，全部通过才算验证完成：

1. **工具层单测**：mock NATS RPC 边界，验证参数拼装、`caller_identity` 透传、无身份拒绝、异常与空结果处理。参照 `tests/test_monitor_tools.py` 模式。
2. **NATS handler 层单测**：sqlite 下真实执行 handler，锁定契约（入参 / 返回结构 / 按身份的权限过滤）。CMDB 写操作 handler 必须覆盖越权拒绝用例。
3. **真实 LLM 端到端**：本地环境（opspilot 模型已配好）建技能挂工具，发起真实会话逐工具验证。数据准备：
   - 数据库表类（告警、CMDB 实例、监控对象/实例元数据）直接造假数据；
   - 监控指标查询用本地已有的 VictoriaMetrics，数据不够再补造；
   - 日志查询起 VictoriaLogs 容器，通过 API 灌假日志。
   - LLM API key 只存在于本地环境配置，不进仓库。

## Out of Scope

- 告警中心的处置操作工具（认领 / 分派 / 关闭）。
- 通过 OpenAPI 网关或 HTTP 暴露这些工具（仅 NATS）。
- 工具层的额外写操作防护（确认机制、删除拦截等）——安全由服务端权限校验兜底。
- MCP 协议形态的工具暴露（沿用 langchain `StructuredTool` 内置工具形态）。
- 后端能力全集的工具化（只按场景清单补齐）。
