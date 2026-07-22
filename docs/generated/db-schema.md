# 数据库 Schema(生成式文档)

> ⚠️ **本文应由命令再生成,不要手工逐表维护**。下面给出再生成方式与当前 app 索引。
> Schema 真相源是各 app 的 `server/apps/<app>/models.py` 与 Django 迁移。

## 如何再生成

本仓库暂无现成 schema 导出命令(已登记技术债 #5)。推荐两种方式择一,产物覆盖本文「## Schema」一节:

```bash
cd server
# 方式 A:导出每个 app 的建表 SQL(按当前 DB_ENGINE 方言)
uv run python manage.py sqlmigrate <app> <migration_name>

# 方式 B:可视化 ER(需先装 django-extensions + graphviz)
uv run python manage.py graph_models -a -o ../docs/generated/db-schema.png
```

> 选定方案后,建议在 `server/` 下加一个 `make db-schema` 目标固化命令,并把本文「Schema」段改为脚本输出。

## App → 数据模型索引(指针,非全量字段)

| App | models 位置 | 领域 |
|-----|------------|------|
| `base` | `server/apps/base/models.py` | 用户 / 认证(自定义 `base.User`) |
| `system_mgmt` | `server/apps/system_mgmt/` | 系统管理 / 认证源 / 权限 |
| `cmdb` | `server/apps/cmdb/` | 配置项(图存储用 **FalkorDB**,非关系库) |
| `monitor` | `server/apps/monitor/` | 监控对象 / 指标 / 仪表盘 |
| `alerts` | `server/apps/alerts/` | 告警 / 通知生命周期 |
| `log` | `server/apps/log/` | 日志检索 / 权限链 |
| `node_mgmt` | `server/apps/node_mgmt/` | 节点 / Agent |
| `job_mgmt` | `server/apps/job_mgmt/` | 作业调度 |
| `mlops` | `server/apps/mlops/` | 模型训练 / 部署 |
| `opspilot` | `server/apps/opspilot/` | AI 助手 |
| `operation_analysis` | `server/apps/operation_analysis/` | 运营分析 |
| `console_mgmt` | `server/apps/console_mgmt/` | 控制台聚合 |
| `core` / `rpc` | `server/apps/{core,rpc}/` | 基础设施 / 跨服务 |

> 注:`cmdb` 的图数据存 FalkorDB,关系型 schema 不覆盖其图模型;图查询禁用 Neo4j 语法。
> 多数据库说明见 [系统架构](../engineering/architecture.md)；`DB_ENGINE` 影响导出的 SQL 方言。

## Schema

<!-- 此段由再生成命令覆盖。当前为占位。 -->
> TODO: 运行再生成命令后填充实际表结构。确认位置:`server/apps/*/models.py` + `server/apps/*/migrations/`。
