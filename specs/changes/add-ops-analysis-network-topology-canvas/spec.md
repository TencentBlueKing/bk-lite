# 网络拓扑大屏 (network_topology) - 运营分析新增画布

Status: done

## Migration Context

- Legacy source: `openspec/changes/add-ops-analysis-network-topology-canvas/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

运营分析已经支持 dashboard、topology、architecture、screen、report 五种内置画布，但**网络拓扑大屏**作为运维最常见的"网络全貌"展示形态，目前缺失。当前拓扑画布（`topology`）是面向应用层关系图设计的（无网络设备语义、无运行态聚合、无 WeOps 凭据承载），无法承载"网络设备 + 指标阈值 + 实时端口状态"这一网络运维核心场景。

WeOps 平台已上线 `/open_api/bklite/network_topology/*` 一组 OpenAPI（`commo-weops/weops/apps/bklite_network_topology/`），提供：

- 设备/接口/链路资源查询（节点/连线数据源）
- 批量指标查询（`batch_metric_values`）
- 批量接口状态查询（`batch_interface_status`）
- 拓扑数据源插件实例/模板查询

但当前 BK-Lite 端没有任何能消费这些 API 的入口。本次变更在运营分析中新增一个**独立的"网络拓扑大屏"画布**，让用户能在运营分析菜单下创建画布，配置 WeOps 服务地址 + Token，把节点/连线/端口对/指标/阈值结构保存到画布，运行时从 WeOps 拉取指标值和端口状态，按"最深阈值命中"聚合节点外层颜色，按"oper_status down-only"聚合连线状态，最终展示一个"会动"的网络拓扑大屏。

## What Changes

- **新增** `NetworkTopology` 模型：扁平 schema 单行承载画布与 WeOps 凭据。`base_url`（URLField）+ `token`（Fernet 加密持久化）+ `view_sets`（JSON: nodes/links/port_pairs/metrics/thresholds）+ `last_runtime_cache`（60s TTL 缓存）。
- **删除** 5 张冗余的旧 P0 之前的独立表（Node/Link/LinkInterface/NodeMetric/MetricThreshold）以及中间表 `NetworkTopologyWeOpsConnection`（凭据现已嵌入主表）。
- **新增** 应用层 JSON 校验器：对 `view_sets` 做节点唯一性、端口对 ≥1（非草稿）、引用完整性、级联删除等校验。
- **新增** WeOps OpenAPI 适配器（`WeOpsTopologyAdapter`）：8 个端点 + 16 种 error_code 映射 + 401/403 → `weops_token_invalid` 归一。
- **新增** 运行时聚合服务（`NetworkTopologyRuntimeService`）：节点颜色按 `(metric_field, result_table_id)` 匹配，最深阈值命中优先；连线状态 down→critical/全 up→normal/否则 unknown；60s TTL 缓存 stale fallback。
- **新增** `NetworkTopologyViewSet`：标准 CRUD + `test_connection` + `runtime` + `put_config` + `remove_node` 4 个 action。Token 仅 `write_only`，列表/详情 API 仅返回 `token_set: bool`。
- **新增** 8 端点 URL：`/api/network_topology/`、`/api/network_topology/test_connection/`、`/api/network_topology/<id>/runtime/`、`/api/network_topology/<id>/config/`、`/api/network_topology/<id>/config/nodes/<node_id>/` 等。
- **未触动** 已有 `topology` 画布（`apps/operation_analysis/views/view.py` 中的 `TopologyModelViewSet` 等），按定开隔离约束，运营分析是单独的 module，network_topology 是该 module 下独立业务。

## Capabilities

### New Capabilities
- `ops-analysis-network-topology-canvas`: 网络拓扑大屏的画布定义、运行态聚合、WeOps 凭据承载与缓存策略。

### Modified Capabilities
无（不修改任何现有 capability）

## Impact

- **新增** schema：单张主表 `operation_analysis_network_topology`（`0016_network_topology` 直接创建 P0 扁平 schema）。
- **数据库**：由于迁移尚未进入共享环境，`0016_network_topology` 直接落最终结构：`base_url`/`token` 位于主表，画布配置使用 `view_sets`，不再保留旧 `NetworkTopologyWeOpsConnection` 与 `weops_connection_id` 兼容迁移。
- **业务隔离**：`NetworkTopology` 模型类不进入 `CANVAS_TYPE_REGISTRY`（5 个 first-class 不含它），独立 URL 路由、独立序列化流程。
- **前端**：在 `web/src/app/ops-analysis/(pages)/view/networkTopology/` 下消费本后端 API（前端由独立 worker 负责）。
- **依赖**：`cryptography==45.0.0`（Fernet token 加密，依赖已在 `server/pyproject.toml`）。
- **测试**：新增 4 个测试文件，90 个用例，全部通过。

## Non-Goals

- 不在本变更中实现 WeOps 端（`commo-weops/weops/apps/bklite_network_topology/`）—— 已在 WeOps 主仓就位。
- 不修改 `apps/operation_analysis/services/canvas/registry.py` 把 `NetworkTopology` 加进 first-class registry（保持 5 个不变）。
- 不实现画布导出/导入（沿用 `import_export` 通用入口，本变更不深耕）。
- 不做 WeOps 凭据轮换/多凭据切换（单画布单 Token）。
- 不在第一版支持画布之间复用节点（每个画布独立维护 view_sets）。

## Implementation Decisions

> 本文档对应 proposal.md 中的 `ops-analysis-network-topology-canvas` capability。

## 1. 背景

运营分析是 BK-Lite 的"控制台"模块，提供 dashboard / topology / architecture / screen / report 五种内置画布。本变更在该模块下新增**第六种画布** —— `network_topology`（网络拓扑大屏），专门面向网络设备运维场景，承载"节点 + 端口 + 指标阈值 + 实时运行态"。

P0 之前 BK-Lite 曾有过 5 张独立表（Node/Link/LinkInterface/NodeMetric/MetricThreshold）+ 1 张中间表（NetworkTopologyWeOpsConnection），schema 复杂且难以对接 WeOps 现有 OpenAPI。本变更**完全扁平化**：

- 节点/连线/端口对/指标/阈值全部进 `view_sets` JSON 字段；
- WeOps 凭据（base_url + token）从中间表内嵌到主表；
- 应用层做 JSON 校验 + 应用层级联。

## 2. 画布模型

### 2.1 NetworkTopology 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BigAutoField | PK |
| `name` | CharField(128, unique) | 画布名称 |
| `desc` | TextField | 描述 |
| `directory` | FK(Directory) | 所属目录 |
| `base_url` | URLField(512) | WeOps 服务地址（保存时自动去尾斜杠、强 http(s) scheme） |
| `token` | CharField(1024, encrypted) | WeOps Token（Fernet 加密，write_only） |
| `refresh_interval` | PositiveIntegerField | 刷新周期（秒），默认 60 |
| `status` | CharField(32) | `draft` / `published` |
| `view_sets` | JSONField | 画布内容（节点/连线/端口对/指标/阈值） |
| `last_runtime_cache` | JSONField | 60s TTL 缓存（`_generated_at` 时间戳） |
| `is_build_in` / `build_in_key` | 标准字段 | 内置标识 |
| `created_*` / `updated_*` | 标准字段 | 时间与维护者 |

### 2.2 节点结构

```json
{
  "id": "node-1",
  "bk_obj_id": "bk_switch",
  "bk_inst_id": 10001,
  "bk_inst_name": "core-switch-01",
  "ip_addr": "10.0.0.1",
  "network_collect_task_id": 12,
  "network_collect_instance_id": 345,
  "plugin_group_id": 3,
  "plugin_template_id": "cisco_c9300",
  "position": {"x": 200, "y": 120},
  "style": {},
  "metrics": [
    {
      "metric_field": "ifHCInOctets",
      "result_table_id": "snmp_network",
      "display_name": "入口流量",
      "unit": "bps",
      "dimensions": {},
      "thresholds": [
        {"value": 0, "color": "#22c55e"},
        {"value": 8000000000, "color": "#f59e0b"},
        {"value": 9000000000, "color": "#dc2626"}
      ]
    }
  ]
}
```

### 2.3 连线结构

```json
{
  "id": "link-1",
  "source_node_id": "node-1",
  "target_node_id": "node-2",
  "is_draft": false,
  "port_pairs": [
    {
      "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001, "interface_name": "GigE0/1"},
      "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002, "interface_name": "GigE0/1"}
    }
  ],
  "style": {}
}
```

`is_draft=true` 的连线允许 `port_pairs=[]`（用户拖拽过程中未选端口），其他情况必须至少 1 对端口。

## 3. JSON Schema 校验（应用层）

`NetworkTopology.clean_view_sets()` 与 `apps.operation_analysis.services.network_topology.canvas_config._validate_payload()` 实施以下规则：

### 3.1 节点校验
- `id` 必填、字符串
- `id` 在画布内唯一
- `bk_obj_id` + `bk_inst_id` 必填（引用完整性）
- 同一 `(bk_obj_id, bk_inst_id)` 资产对在画布内不能重复
- `metrics` 数组（可空）；每个 metric 必须有 `metric_field` + `result_table_id`；`thresholds` 数组（可空），每个 threshold 必须有 `value` + `color`

### 3.2 连线校验
- `source_node_id` + `target_node_id` 必须在画布中
- 非草稿连线 `port_pairs` 数量 ≥ 1
- 每个 port_pair 必须有 `source_interface.bk_inst_id` + `target_interface.bk_inst_id`

### 3.3 错误抛出
抛 `django.core.exceptions.ValidationError`，detail 形如 `{"nodes": [...], "links": [...]}`。view 层做 DRF ValidationError 转换返回 400。

## 4. Serializer 行为

`NetworkTopologySerializer`：

- `token`: `write_only=True`，**任何** GET 接口都不返回明文
- `token_set`: `SerializerMethodField` —— DB 有 token 时返回 `True`，前端根据这个值决定是否显示"重新配置 Token"按钮
- `view_sets`: `JSONField` 写入时通过 canvas_config.replace 走应用层校验
- `create()`: 调 `full_clean()` 触发 `clean_view_sets()`；注入 `request.user.username` 到 `created_by` / `updated_by`
- `update()`: 同样调 `full_clean()` + 更新 `updated_by`
- `validate_token()`: 拒绝占位符（`******` 等），长度 < 4 拒绝，自动 Fernet 加密

**Token 加密**：`_fernet_key()` 从 `settings.SECRET_KEY` 用 SHA-256 派生一个 32 字节 base64-url-safe key → Fernet 实例。同一 SECRET_KEY 跨进程产出相同密文；DB 中只存 `gAAAAA...` 形式的密文。

## 5. WeOps 适配器

`WeOpsTopologyAdapter`（`apps.operation_analysis.services.network_topology.weops_adapter`）封装以下 8 个端点（来自 `commo-weops/weops/apps/bklite_network_topology/urls.py`）：

| 方法 | 端点 | 用途 |
|------|------|------|
| `test_connection` | `POST /open_api/bklite/network_topology/test_connection/` | 校验 Token（`adapter.test_connection()` 内部调一个轻量接口） |
| `list_nodes` | `GET /open_api/bklite/network_topology/nodes/?page=1&page_size=1000` | 全量拉节点（page_size=1000 一次性拉完） |
| `get_node` | `GET /open_api/bklite/network_topology/nodes/{node_ref}/` | 单节点详情 |
| `list_interfaces` | `GET /open_api/bklite/network_topology/nodes/{node_ref}/interfaces/` | 节点接口 |
| `list_topology_sources` | `GET /open_api/bklite/network_topology/topology_sources/` | 拓扑数据源实例/模板 |
| `get_metric_value` | `POST /open_api/bklite/network_topology/metric_value/` | 单条指标 |
| `batch_metric_values` | `POST /open_api/bklite/network_topology/batch_metric_values/` | 批量指标 |
| `batch_interface_status` | `POST /open_api/bklite/network_topology/batch_interface_status/` | 批量接口状态（含 `node_interface_summary`） |

### 5.1 响应处理

- 顶层响应统一剥 `{result, data}` 信封：成功 `data` 直接返回；失败抛 `WeOpsTopologyAdapterError`
- 401 / 403 → 抛 `WeOpsTopologyAdapterError(code="weops_token_invalid", status_code=401/403)`
- 节点引用 (`node_ref`) 通过 `encode_node_ref({"bk_obj_id": ..., "bk_inst_id": ...})` 走 URL-safe base64

### 5.2 16 种 error_code 映射

`_ITEM_ERROR_MAP` 把 WeOps 数据项内嵌的 `error_code` 字符串映射到内部 `NetworkTopologyErrorType` 枚举：

- `source_not_found` / `node_mismatch` / `source_inactive` —— 数据源问题
- `template_mismatch` / `template_not_found` —— 模板问题
- `node_ref_invalid` —— 节点引用问题
- `metric_not_found` / `metric_query_failed` / `metric_no_data` —— 指标三类
- `interface_relation_query_failed` / `interface_query_failed` / `interface_not_found` —— 接口三类
- `status_metric_not_found` / `status_query_failed` / `status_no_data` —— 状态三类
- 未知 code → `NetworkTopologyErrorType.UNKNOWN`

## 6. ViewSet 端点

`NetworkTopologyViewSet`（`apps/operation_analysis/views/network_topology_view.py`）：

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/network_topology/` | 列表（token 不返回） |
| POST | `/api/network_topology/` | 创建（必填 token；自动 Fernet 加密） |
| GET | `/api/network_topology/<id>/` | 详情（token 不返回） |
| PUT | `/api/network_topology/<id>/` | 更新（token 留空则不变） |
| DELETE | `/api/network_topology/<id>/` | 删除 |
| POST | `/api/network_topology/test_connection/` | 验证 WeOps Token（不持久化） |
| GET | `/api/network_topology/<id>/runtime/` | 拉取运行态聚合结果（带 60s stale fallback） |
| PUT | `/api/network_topology/<id>/config/` | 替换 `view_sets` JSON（应用层校验） |
| DELETE | `/api/network_topology/<id>/config/nodes/<node_id>/` | 级联删除节点 + 引用它的连线 |

### 6.1 CustomRenderer 适配

项目用 `config/drf/renderers.py` 的 `CustomRenderer` 把响应包成 `{result, code, message, data}`，错误时 `data: data.get("data")`。我们的：

- 成功响应 body 直接是 `{"nodes": [...], "links": [...], "errors": []}`（render 自动包成 `data: {...}`）
- 错误响应 body 是 `{"data": {"code": "...", "message": "...", "stale": False}}`（避免 `data.get("data")` 返回 None）
- 运行时 stale fallback body 是 `{"nodes": [...], "links": [...], "stale": true, "errors": [{"code": "...", "message": "..."}]}`

### 6.2 错误映射（Django ValidationError → DRF）

`canvas_config.replace()` / `cascade_remove_*` 抛 `django.core.exceptions.ValidationError`，DRF 默认不识别。view 层 `_coerce_validation_error()` 转成 `rest_framework.exceptions.ValidationError`，让 `custom_exception_handler` 返回 400。

## 7. 运行态聚合

`NetworkTopologyRuntimeService.build_runtime(topology, adapter)` 是核心入口，返回 `{result: True, data: {nodes, links, errors}}`。

### 7.1 节点颜色聚合

`resolve_node_outer_color(metrics, runtime_metrics)`：

1. 遍历 `metrics`，按 `(metric_field, result_table_id)` 找到对应 `runtime_metrics` 项
2. 对每个 metric 调 `resolve_active_threshold(metric, runtime)`，返回 `{level, color}` 或 `None`
3. 取最深 level（threshold 数组索引越大 = 用户定义的"最严重"级别）；同 level 按 metric 在画布中的位置优先
4. 全部无数据 → 返回 `None`（前端用 `NODE_OUTER_COLOR_UNKNOWN = "#64748b"` 兜底）

`resolve_active_threshold`：

- NaN / None / 字符串值 → `None`
- thresholds 按 `value` 升序：第一个 `value <= 当前值` 的为命中
- 比所有阈值都小 → 用最小阈值的 `color`（baseline）

### 7.2 连线状态聚合

`resolve_link_status(interface_items)`（`oper_status_down_only`）：

- 任何 `oper_status == "down"` → `{"status": "critical", "reason": "interface_down"}`
- 全部 `oper_status == "up"` 且 `status == "ok"` → `{"status": "normal", "reason": "all_interface_up"}`
- 否则（含 `unknown` / `testing` / 缺数据 / 报错）→ `{"status": "unknown", "reason": "interface_unknown"}`
- 无接口项 → `{"status": "unknown", "reason": "no_interface"}`

### 7.3 缓存策略

`NetworkTopologyRuntimeService.CACHE_TTL_SECONDS = 60`（与画布 `refresh_interval` 默认值对齐）：

- `cache_payload(data)`：附加 `_generated_at = timezone.now().isoformat()`
- `fresh_cached_payload(topology)`：从 `last_runtime_cache` 读出；超过 TTL 或无时间戳 → 返回 `{}`
- view `runtime` action：
  1. `build_runtime()` 成功 → 写新缓存，返回 `data`
  2. 失败 + 有 fresh cache → 返回 `cached` + `stale: true` + `errors: [{code, message}]`
  3. 失败 + 无 fresh cache → 走 `_adapter_error_response` 返回 502

## 8. 迁移

### 8.1 0016 - 扁平 P0 schema

新建 `operation_analysis_network_topology` 表，字段如 §2.1 所列。**不在**这张表上建 `weops_connection_id` FK —— 凭据直接放主表。

### 8.2 0017 - 数据迁移

```python
migrate_schema(apps, schema_editor):
    # 1. 加 base_url / token / view_sets 列（如果不存在）
    # 2. 把 view_config 重命名为 view_sets
    # 3. 从 operation_analysis_network_topology_weops_connection 拉 base_url/token
    # 4. UPDATE nt SET base_url = wc.base_url, token = wc.token WHERE nt.weops_connection_id = wc.id
    # 5. 设默认 '' 防 NULL
    # 6. SET NOT NULL
    # 7. DROP COLUMN weops_connection_id
```

幂等：检测列存在后再操作；旧表不存在（测试库新装）也不报错。

## 9. 已知决策与 trade-off

### 9.1 为什么不用 `topology/` 现有代码

按 CLAUDE.md 团队定开隔离约束，`apps/operation_analysis/services/topology/` 等是已有定开代码，本变更**不引用** 任何 `topology` 业务代码，新建独立的 `services/network_topology/` 子包。

### 9.2 为什么用 Django ValidationError 而不是 DRF

测试断言 `pytest.raises(DjangoValidationError)` + `exc.value.message_dict`，统一在 view 层做 DRF 转换。

### 9.3 registry 不含 network_topology

`test_canvas_registry_contains_all_first_class_canvas_types` 测试硬编码 5 个 first-class canvas。`network_topology` 走独立 URL 路由（`/api/network_topology/`），不进 `CANVAS_TYPE_REGISTRY`。

### 9.4 不做 WeOps 凭据轮换

单画布单 Token；不实现多凭据切换、不实现 API Key 轮换。后续可加独立 capability。

## 10. 测试覆盖

4 个测试文件，90 用例：

| 文件 | 用例数 | 覆盖范围 |
|------|--------|---------|
| `test_network_topology_models.py` | 18 | Token 加密、URL 规范化、view_sets 校验（节点唯一性、端口对、引用完整性、级联） |
| `test_network_topology_runtime.py` | 22 | 节点颜色聚合（基线、平局、NaN、无数据）、连线状态聚合、缓存 TTL、`build_runtime` 端到端 |
| `test_network_topology_weops_adapter.py` | 37 | 16 种 error_code 映射、URL 编码、HTTP 错误归一、401/403 → `weops_token_invalid` |
| `test_network_topology_api.py` | 13 | CRUD + test_connection + runtime + put_config + delete_node（含 stale fallback） |

`make test` 跑网络拓扑相关：**90/90 通过**。

## Capability Deltas

### ops-analysis-network-topology-canvas

> 本 capability 的验收场景。所有场景均已在 `server/apps/operation_analysis/tests/test_network_topology_*.py` 中以测试用例形式实现并通过。

## ADDED Requirements

### Requirement: 网络拓扑画布模型（扁平 schema）

系统 MUST 在运营分析模块下提供 `NetworkTopology` 模型，承载网络拓扑大屏配置。模型 MUST 满足：

#### Scenario: 单表承载画布与 WeOps 凭据

- **WHEN** 用户创建一个网络拓扑大屏
- **THEN** 系统在 `operation_analysis_network_topology` 表中创建一行
- **AND** 该行的 `base_url` / `token` / `view_sets` 全部直接存储在该行上
- **AND** 不存在 `weops_connection_id` 等外键指向单独的凭据表

#### Scenario: Token Fernet 加密持久化

- **WHEN** 用户提交创建画布请求，明文 `token="plain-token"`
- **THEN** DB 列 `token` 存储的不是明文（以 `gAAAAA` 开头）
- **AND** 模型方法 `topology.decrypt_token()` 还原明文
- **AND** `topology.token_set()` 返回 `True`

#### Scenario: base_url 规范化

- **WHEN** 用户提交 `base_url="https://weops.example.com/api///"`
- **THEN** DB 存储为 `https://weops.example.com/api`（去尾斜杠）
- **WHEN** 用户提交 `base_url="weops.example.com"`（无 scheme）
- **THEN** 校验失败，返回 400
- **WHEN** 用户提交 `base_url="ftp://weops"`
- **THEN** 校验失败，返回 400

#### Scenario: 占位符 token 拒绝

- **WHEN** 用户提交 `token="******"`
- **THEN** 校验失败，返回 400（"Token 不允许使用占位符"）

### Requirement: view_sets JSON 应用层校验

系统 MUST 对 `view_sets` JSON 实施应用层结构校验，校验失败时返回 400，错误 detail 形如 `{"nodes": [...], "links": [...]}`。

#### Scenario: 节点 id 唯一性

- **WHEN** `view_sets` 包含两个 `id` 相同的节点
- **THEN** 校验失败，detail 中 `nodes` 包含 "节点 id 'node-1' 重复"

#### Scenario: 节点资产对 (bk_obj_id, bk_inst_id) 唯一性

- **WHEN** 画布包含两个节点 `(bk_switch, 10001)` 和 `(bk_switch, 10001)`（不同 id 但同资产）
- **THEN** 校验失败，detail 包含 "与画布中已有节点 (bk_switch, 10001) 重复"

#### Scenario: 连线引用完整性

- **WHEN** 画布中有连线引用 `target_node_id="ghost-node"`，但 `ghost-node` 不在画布
- **THEN** 校验失败，detail 包含 "连线 link-1 的 target_node_id 'ghost-node' 不在画布中"

#### Scenario: 非草稿连线必须有端口对

- **WHEN** `is_draft=false` 的连线 `port_pairs=[]`
- **THEN** 校验失败，detail 包含 "连线 link-1 至少需要 1 对端口"
- **WHEN** `is_draft=true` 的连线 `port_pairs=[]`
- **THEN** 校验通过

#### Scenario: 端口对 bk_inst_id 必填

- **WHEN** port_pair 缺 `source_interface.bk_inst_id`
- **THEN** 校验失败，detail 包含 "缺少源接口 bk_inst_id"

#### Scenario: 指标必填字段

- **WHEN** metric 缺 `metric_field` 或 `result_table_id`
- **THEN** 校验失败，detail 包含 "缺少 metric_field" / "缺少 result_table_id"

#### Scenario: 阈值必填字段

- **WHEN** threshold 缺 `value` 或 `color`
- **THEN** 校验失败，detail 包含 "缺少 value" / "缺少 color"

### Requirement: 应用层级联删除

系统 MUST 在应用层（非 DB FK）实施级联删除：删除一个节点时引用它的所有连线同步删除。

#### Scenario: 删除节点时级联删除引用它的连线

- **WHEN** 画布有 `node-1`、`node-2`，连线 `link-1` 引用两者
- **AND** 用户调用 `DELETE /api/network_topology/<id>/config/nodes/node-1/`
- **THEN** 节点 `node-1` 被删除
- **AND** 连线 `link-1` 也被删除（因为它引用了 `node-1`）
- **AND** 画布中剩下 `node-2`，无连线

#### Scenario: 删除不存在的节点是幂等 no-op

- **WHEN** 用户调用删除节点 API，节点 id 不存在
- **THEN** 不抛错，返回 200，view_sets 不变

### Requirement: Token API 可见性

系统 MUST 在 GET 接口中**永不**返回明文 token，只返回 `token_set: bool`。

#### Scenario: 创建后 token_set 标志

- **WHEN** 用户 POST 创建画布 body 包含明文 token
- **THEN** 响应 201
- **AND** 响应 `data.token_set == true`
- **AND** 响应 `data` 中不包含 `token` 字段
- **AND** 响应原文（`json.dumps(payload)`）不包含明文 token

#### Scenario: 详情接口不暴露 token

- **WHEN** 用户 GET `/api/network_topology/<id>/`
- **THEN** 响应 `data.token_set == true`
- **AND** 响应 `data` 中不包含 `token` 字段
- **AND** 响应原文不包含 DB 中密文 token

### Requirement: test_connection 端点

系统 MUST 提供 `POST /api/network_topology/test_connection/` 端点用于验证 WeOps 凭据，**不**持久化凭据。

#### Scenario: 凭据有效返回 200

- **WHEN** 用户 POST 端点，body 包含合法 base_url + token
- **THEN** 响应 200
- **AND** 响应 `data == {"status": "ok"}`
- **AND** DB 中无任何新行

#### Scenario: 凭据无效返回 403 + weops_token_invalid

- **WHEN** 用户 POST 端点，token 已失效
- **THEN** 响应 403
- **AND** 响应顶层 `code == "40300"`
- **AND** 响应 `data.code == "weops_token_invalid"`

#### Scenario: base_url 格式错误返回 400

- **WHEN** 用户 POST 端点，base_url 缺 scheme
- **THEN** 响应 400

### Requirement: runtime 端点 + 缓存 stale fallback

系统 MUST 提供 `GET /api/network_topology/<id>/runtime/` 端点拉取运行态聚合结果。

#### Scenario: 拉取 fresh 成功

- **WHEN** WeOps 可用
- **THEN** 响应 200
- **AND** 响应 `data.nodes` 是按最深阈值命中颜色聚合的节点列表
- **AND** 响应 `data.links` 是按 `oper_status_down_only` 聚合的连线状态
- **AND** 响应 `data.stale == false`（或缺失）

#### Scenario: WeOps 不可用时 stale fallback

- **WHEN** WeOps 抛 `weops_unavailable`
- **AND** 画布有 fresh 缓存（60s TTL 内）
- **THEN** 响应 200
- **AND** 响应 `data.stale == true`
- **AND** 响应 `data` 是上次缓存内容
- **AND** 响应 `data.errors[0].code == "weops_unavailable"`

#### Scenario: WeOps 不可用且无缓存返回 502

- **WHEN** WeOps 抛 `weops_unavailable`
- **AND** 画布无 fresh 缓存（TTL 过期或从未缓存）
- **THEN** 响应 502
- **AND** 响应 `result == false`
- **AND** 响应 `data.stale == false`
- **AND** 响应 `data` 不包含 `nodes` 字段

#### Scenario: Token 失效时也走 stale fallback

- **WHEN** WeOps 抛 `weops_token_invalid` (401/403)
- **AND** 画布有 fresh 缓存
- **THEN** 响应 200
- **AND** 响应 `data.stale == true`
- **AND** 响应 `data.errors[0].code == "weops_token_invalid"`

### Requirement: 节点颜色聚合

系统 MUST 按"最深阈值命中"为节点外层颜色排序，平局按画布中 metric 位置优先。

#### Scenario: 单 metric 基线（value 低于所有阈值）

- **WHEN** metric 只有一个 threshold `[{value: 0, color: "#22c55e"}]`
- **AND** runtime value = -1
- **THEN** 节点外层颜色为 `#22c55e`（baseline）

#### Scenario: 多 metric 平局

- **WHEN** 节点有两个 metric，都命中各自的第一个 threshold（level=0）
- **THEN** 取画布中位置靠前的 metric 的 color

#### Scenario: 全部无数据

- **WHEN** 节点 metrics 全部无 runtime value
- **THEN** `resolve_node_outer_color` 返回 `None`
- **AND** 前端用 `NODE_OUTER_COLOR_UNKNOWN = "#64748b"` 兜底

#### Scenario: NaN / 字符串值

- **WHEN** runtime value 是 `NaN` 或字符串
- **THEN** 该 metric 不参与聚合

### Requirement: 连线状态聚合 (oper_status_down_only)

#### Scenario: 任一 down → critical

- **WHEN** link 的任一接口 `oper_status == "down"`
- **THEN** 状态 = `"critical"`，原因 = `"interface_down"`

#### Scenario: 全部 up 且 status=ok → normal

- **WHEN** 所有接口 `oper_status == "up"` 且 `status == "ok"`
- **THEN** 状态 = `"normal"`，原因 = `"all_interface_up"`

#### Scenario: 含 testing / unknown / 缺数据

- **WHEN** 接口有 `unknown` / `testing` 状态或缺数据
- **THEN** 状态 = `"unknown"`，原因 = `"interface_unknown"`（不降到 critical）

#### Scenario: 无接口项

- **WHEN** link 没有任何接口 runtime 项
- **THEN** 状态 = `"unknown"`，原因 = `"no_interface"`

### Requirement: WeOps 适配器

#### Scenario: 16 种 error_code 全部映射

- **WHEN** WeOps 在 `data.items[].error_code` 中返回已知 code（如 `metric_not_found`、`status_query_failed` 等）
- **THEN** 适配器把它映射到对应的 `NetworkTopologyErrorType` 枚举值
- **WHEN** 返回未知 code
- **THEN** 映射到 `NetworkTopologyErrorType.UNKNOWN`

#### Scenario: 401/403 → weops_token_invalid

- **WHEN** WeOps 响应 HTTP 401 或 403
- **THEN** 适配器抛 `WeOpsTopologyAdapterError(code="weops_token_invalid", status_code=401/403)`

#### Scenario: node_ref URL 编码

- **WHEN** 调用 `adapter.get_node({"bk_obj_id": "bk_switch", "bk_inst_id": 10001})`
- **THEN** URL 路径中 `node_ref` 是 base64-url-safe 编码的字符串

#### Scenario: 全量拉 nodes 用 page_size=1000

- **WHEN** 调用 `adapter.list_nodes()`
- **THEN** HTTP 请求 query 包含 `page_size=1000`

### Requirement: 视图层错误转换

#### Scenario: view_sets 校验失败返回 400

- **WHEN** `PUT /config/` body 包含非法 view_sets
- **THEN** 响应 400
- **AND** 响应 message 或 data 中包含具体错误描述（如 "ghost"、"端口" 等关键词）

## Work Checklist

> 本文件由实现过程中按 TDD 节奏逐步完成；以下编号与设计文档（design.md）章节对应。
> Worker A（后端）/ Worker B（前端）可并行执行；本任务清单只覆盖 Worker A。

## 1. 前置

- [x] 1.1 读 `proposal.md` / `design.md` / `tasks.md` / `specs/.../spec.md` 吃透需求
- [x] 1.2 读 WeOps 实际代码：`commo-weops/weops/apps/bklite_network_topology/{urls,views,services}.py`，确认端点路径、响应信封、字段名

## 2. 后端模型重构

- [x] 2.1 删除 5 张独立表（Node / Link / LinkInterface / NodeMetric / MetricThreshold）的模型类 + 旧迁移
- [x] 2.2 删除 `NetworkTopologyWeOpsConnection` 模型
- [x] 2.3 `NetworkTopology.view_config` → `view_sets` 重命名
- [x] 2.4 `NetworkTopology` 新增 `base_url` (URLField, 512) 和 `token` (CharField, 1024, Fernet 加密存储)
- [x] 2.5 保留 `last_runtime_cache` JSONField
- [x] 2.6 迁移整理：由于未进入共享环境，`0016_network_topology.py` 直接创建最终扁平 schema，无需旧 FK 数据迁移

## 3. view_sets JSON Schema 与应用层校验

- [x] 3.1 `canvas_config._validate_payload()`：节点唯一性、端口对 ≥1、引用完整性
- [x] 3.2 `canvas_config.cascade_remove_node()` / `cascade_remove_link()`：应用层级联
- [x] 3.3 `NetworkTopology.clean_view_sets()` 模型方法做同样校验（DRF 不通时也走通）
- [x] 3.4 抛 `django.core.exceptions.ValidationError`，detail 形如 `{"nodes": [...], "links": [...]}`

## 4. Serializer 重写

- [x] 4.1 `NetworkTopologySerializer` 以 `view_sets` 为核心
- [x] 4.2 列表 / 详情 API 不返回明文 `token`，改返回 `token_set: bool`（`SerializerMethodField`）
- [x] 4.3 `view_sets` JSON schema 校验（写入时）
- [x] 4.4 Token 加密：`cryptography.Fernet` + SECRET_KEY 派生 key，写入前自动加密
- [x] 4.5 Token 拒绝占位符（`******`）、长度 < 4 拒绝
- [x] 4.6 `create()` / `update()` 注入 `request.user.username` 到 `created_by` / `updated_by`，调 `full_clean()`

## 5. Service 重写

- [x] 5.1 `apps.operation_analysis.services.network_topology.runtime.NetworkTopologyRuntimeService` 处理 view_sets 读写 + runtime 聚合
- [x] 5.2 `weops_adapter.WeOpsTopologyAdapter` 封装 8 个 WeOps 端点（严格按 design.md §5 字段名）
- [x] 5.3 `resolve_node_outer_color()` 工具：按 `(metric_field, result_table_id)` 匹配，最深阈值命中优先，平局按画布中位置优先
- [x] 5.4 `resolve_link_status()` 工具：`oper_status_down_only` 聚合
- [x] 5.5 运行态缓存 + stale 处理（60s TTL）

## 6. View 重写

- [x] 6.1 `NetworkTopologyViewSet`（`apps/operation_analysis/views/network_topology_view.py`）
- [x] 6.2 标准 CRUD（`list` / `create` / `retrieve` / `update` / `destroy`）
- [x] 6.3 `POST /api/network_topology/test_connection/` 端点（不持久化）
- [x] 6.4 详情 API 返回 `token_set: bool` 不返回明文
- [x] 6.5 错误映射：401/403 → `weops_token_invalid`，其他 4xx/5xx 透传
- [x] 6.6 `GET /api/network_topology/<id>/runtime/` 拉运行态聚合（stale fallback）
- [x] 6.7 `PUT /api/network_topology/<id>/config/` 替换 view_sets JSON
- [x] 6.8 `DELETE /api/network_topology/<id>/config/nodes/<node_id>/` 级联删节点
- [x] 6.9 URL 注册：`apps/operation_analysis/urls.py` 添加 `router.register(r"api/network_topology", ...)`

## 7. 前端

> Worker B 独立任务，不在本清单。

## 8. 跨 worker 协调

- [x] 8.1 后端交付时已确定的接口契约（与 Worker B 对齐）
  - `POST /api/network_topology/` body / response
  - `GET /api/network_topology/<id>/` response（含 `token_set`）
  - `POST /api/network_topology/test_connection/` body / response
  - `GET /api/network_topology/<id>/runtime/` response
  - `PUT /api/network_topology/<id>/config/` body / response
  - `DELETE /api/network_topology/<id>/config/nodes/<node_id>/` response

## 9. 集成与端到端验证

- [x] 9.1 `cd server && uv run python -m pytest apps/operation_analysis/tests/test_network_topology_*.py --no-cov` 90/90 通过
- [x] 9.2 `cd server && uv run python manage.py makemigrations operation_analysis --dry-run --check` 无 pending
- [x] 9.3 干净库 `manage.py migrate` 跑通
- [x] 9.4 cmdb 网络拓扑测试 6/6 通过（确保未破坏跨模块引用）
- [x] 9.5 operation_analysis 整套 334/335 通过（唯一失败是预存 import_export_schema 版本问题，与本任务无关）

## 10. WeOps Adapter 后端

- [x] 10.1 16 种 error_code 全部映射到 `NetworkTopologyErrorType` 枚举
- [x] 10.2 `encode_node_ref()` URL-safe base64 编码节点引用
- [x] 10.3 大 `page_size=1000` 拉全部 nodes
- [x] 10.4 单元测试覆盖 37 用例

## 11. 测试

- [x] 11.1 view_sets JSON 校验测试（18 用例）
- [x] 11.2 节点外层颜色聚合测试（边界场景：基线、平局、无数据、NaN、字符串值）
- [x] 11.3 连线状态聚合测试（down、up、unknown、testing、缺数据）
- [x] 11.4 运行态刷新测试（fresh、stale fallback、token invalid stale fallback、cache 过期）
- [x] 11.5 WeOps adapter 单元测试（37 用例）
- [x] 11.6 真实跑一遍，`make test` 90/90 通过

## 12. 完成标准

- [x] 所有 task 列表项完成
- [x] `cd server && make test` 中网络拓扑相关 90/90 通过
- [x] 迁移文件 0016/0017 就位（干净库能跑通）
- [x] OpenSpec 场景均有测试覆盖
- [x] 无 TODO/FIXME/占位
- [x] 未引用 `topology/` 业务代码

## 13. 后续（P1+，本变更不实现）

- 多凭据 / 凭据轮换
- 画布导入/导出网络拓扑专用模板
- 前端实时刷新（依赖前端 worker）
- 节点搜索 / 资产引用 CMDB 实时同步
- 历史快照（回放某时刻画布运行态）
