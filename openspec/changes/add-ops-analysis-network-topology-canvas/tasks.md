# 网络拓扑大屏 - 任务清单

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
