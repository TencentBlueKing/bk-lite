# 模块 ARD：Operation Analysis（运营分析）

> 路径 `server/apps/operation_analysis` ｜ API 前缀 `api/v1/operation_analysis/`

## 1. 职责【已实现/已存在】
统一可视化层：聚合外部 REST/NATS 数据源，组织仪表盘、拓扑、架构图，支持配置导入导出。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Directory | `models/models.py` | 层级目录（最多 3 级） |
| Dashboard / Topology / Architecture | `models/models.py` | 仪表盘/拓扑/架构图（filters、view_sets JSON） |
| NameSpace | `models/datasource_models.py` | NATS 连接配置（域/账号/密码加密/TLS） |
| DataSourceAPIModel / DataSourceTag | `models/datasource_models.py` | 外部 REST API 数据源、标签 |

## 3. 接口【已实现/已存在】
`data_source`/`dashboard`/`directory`/`topology`/`architecture`/`namespace`/`tag`/`import_export`；开放端点 `open_api/import_export`。

## 4. 依赖与通信【已实现/已存在】
- NATS：`nats/nats.py` 暴露 `get_operation_analysis_module_data`/`_list`（仅暴露自身数据源模块）；`common/get_nats_source_data.py:GetNatsData.get_data()` 为**通用数据源取数器**，按 `path` 参数动态调用任意已注册 NATS 函数。
  - 更正：operation_analysis 代码中**未硬编码调用** alerts 的 `get_alert_*`；这些是 alerts 独立的 NATS 端点，理论上可被配置为数据源调用，但非内置依赖（证据：operation_analysis 全模块无 `get_alert_`/`alerts.` 引用）。
- 服务：`services/directory_service.py`（目录树）、`services/node_tree.py`、`services/import_export/*`（YAML 导入导出）。
- 依赖 `apps.core` 装饰器/视图工具；RPC 经 `OperationAnalysisRpc`（独立 server/namespace，`apps/rpc/base.py`）。

## 5. 风险 / 待确认
- 数据源为外部 REST/NATS，运营分析本身不落原始数据；数据一致性与缓存策略【待确认】。
- `tasks.py` 当前为空（无后台任务）【已实现】。

## 6. 证据来源
`server/apps/operation_analysis/{urls.py,models/*,nats/nats.py,common/get_nats_source_data.py,services/*}`、`apps/rpc/base.py:OperationAnalysisRpc`。
