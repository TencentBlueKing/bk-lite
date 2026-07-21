# 网络拓扑大屏 (network_topology) - 运营分析新增画布

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
