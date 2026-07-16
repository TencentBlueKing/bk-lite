# 网络拓扑大屏 - 设计文档

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
