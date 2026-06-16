# 模块 ARD：基础设施依赖与部署形态

> 路径 `server/config/components/*`、`deploy/*`、各 `Makefile`/`Dockerfile`

## 1. 基础设施依赖【已实现/已存在】
| 服务 | 用途 | 配置 |
|------|------|------|
| PostgreSQL（默认） / MySQL / 达梦 / GaussDB / GoldenDB / OceanBase | 主数据库（`DB_ENGINE` 选择，国产库自定义 backend + 补丁） | `database.py` |
| ⚠️ **MySQL 分支疑似缺陷** | `DB_ENGINE=mysql` 时 `ENGINE` 实际指向 `cw_cornerstone.db.dameng.backend`（达梦后端），MySQL 可能无法正常工作 | `database.py:24-38`（需人工确认是否有意为之） |
| Redis（可选，默认 LocMem） | 缓存 | `cache.py`（`REDIS_CACHE_URL`） |
| RabbitMQ | Celery broker（默认 `amqp://admin:password@rabbitmq.lite/`） | `celery.py` |
| NATS | RPC / pub-sub / 权限同步（namespace `bklite`，JetStream 默认关闭） | `nats.py` |
| MinIO / S3 | 对象存储（多 bucket） | `minio.py` |
| VictoriaMetrics | 指标时序 | `monitor/utils/victoriametrics_api.py` |
| VictoriaLogs | 日志（`VICTORIALOGS_*`） | `log/constants/victoriametrics.py` |
| Neo4j / FalkorDB | CMDB 图谱 | `cmdb/graph/*` |
| pgvector | opspilot 向量 | opspilot |
| Elasticsearch | opspilot metis 工具 | opspilot/metis |
| MLflow | 模型注册（`MLFLOW_TRACKER_URL`） | `mlflow.py` |
| Kubernetes | 采集 DaemonSet、opspilot bot 部署 | `deploy/*`、opspilot |

## 2. 运行进程【已实现/已存在】
- 后端：Uvicorn ASGI **:8011（`make dev` 开发）**；Celery worker+Beat（`make celery`，Beat 用 `DatabaseScheduler`，周期任务存 `django_celery_beat` 表）；NATS 监听（`make start-nats`）。
  - ⚠️ 生产 web Dockerfile 配置 `NEXTAPI_URL=http://bklite-server:8000`，与开发端口 :8011 不一致，部署时需统一后端容器端口（`web/Dockerfile`）。
- 前端：web :3000、mobile :3001。
- agents：stargazer :8083、nats-executor、ansible-executor。
- 算法：BentoML :3000。

## 3. 容器与编排【已实现/已存在 + 待确认】
- web 多阶段 Dockerfile（`NEXTAPI_URL=http://bklite-server:8000`）。【已实现】
- `deploy/dist/bk-lite-kubernetes-collector/`：K8s 采集 DaemonSet（cadvisor、telegraf 等）。【已实现】
- **完整平台 K8s 编排（各 app/agent/中间件）位置缺失**。【待确认】

## 4. 配置约定【已实现/已存在】
- app 自动注册进 INSTALLED_APPS（`base`/`core`/`rpc` 常驻，其余受 `INSTALL_APPS` 控制）。
- URL 自动路由 `api/v1/<app>/`（`server/urls.py`）。
- split_settings：`config/components/*.py`。
- 关键环境变量：`DB_*`、`INSTALL_APPS`、`NEXTAPI_URL`、`NATS_*`、`MINIO_*`、`CELERY_BROKER_URL`、`MLFLOW_TRACKER_URL`、`VICTORIALOGS_*`；模板 `server/envs/.env.example`、`server/support-files/env/*.example`。

## 5. 风险 / 待确认
- 完整部署清单与编排（除采集器外）【待确认】。
- 默认凭据（RabbitMQ `admin:password`、MinIO 无默认）需生产加固【已实现风险】。
- JetStream 生产启用与否影响 job 日志/安装【已实现风险】。

## 6. 证据来源
`server/config/components/{base,database,cache,celery,nats,minio,mlflow,log,locale,drf,enterprise,extra}.py`、`server/Makefile`、`web/{Dockerfile,.env.example}`、`deploy/dist/bk-lite-kubernetes-collector/*`。
