# 模块 ARD：基础设施依赖与部署形态

> 路径 `server/config/components/*`、`deploy/*`、各 `Makefile`/`Dockerfile`

## 1. 基础设施依赖【已实现/已存在】
| 服务 | 用途 | 配置 |
|------|------|------|
| PostgreSQL（默认） / MySQL / 达梦 / GaussDB / GoldenDB / OceanBase | 主数据库（`DB_ENGINE` 选择，国产库自定义 backend + 补丁） | `database.py` |
| MySQL（`DB_ENGINE=mysql`）【已实现】 | `ENGINE=cw_cornerstone.db.mysql.backend`，分支内 `import pymysql` 并 `pymysql.install_as_MySQLdb()` 注册为 MySQLdb 驱动 | `database.py:24-38` |
| Redis / LocMem | 缓存：`REDIS_CACHE_URL` 非空时 `default`=Redis，否则=LocMem；另预置 `db`(DatabaseCache)/`dummy` 命名别名 | `cache.py:6-25` |
| RabbitMQ | Celery broker（默认 `amqp://admin:password@rabbitmq.lite/`） | `celery.py` |
| NATS | RPC / pub-sub / 权限同步（namespace `bklite`，JetStream 默认关闭）；支持 TLS（`_create_ssl_context()`）与 user/password/token 认证、重连参数【已实现】 | `nats.py:10-72` |
| MinIO / S3 | 对象存储；private buckets：`rewind-private`、`munchkin-private`、`log-alert-raw-data`、`monitor-alert-raw-data`、`job-mgmt-private`、`cmdb-config-file`；public buckets：`rewind-public`、`munchkin-public`【已实现】 | `minio.py:19-27` |
| VictoriaMetrics | 指标时序 | `monitor/utils/victoriametrics_api.py` |
| VictoriaLogs | 日志（`VICTORIALOGS_*`） | `log/constants/victoriametrics.py` |
| Neo4j / FalkorDB | CMDB 图谱 | `cmdb/graph/*` |
| pgvector | opspilot 向量 | opspilot |
| Elasticsearch | opspilot metis 工具 | opspilot/metis |
| MLflow | 模型注册（`MLFLOW_TRACKER_URL`） | `mlflow.py` |
| Kubernetes | 采集 DaemonSet、opspilot bot 部署 | `deploy/*`、opspilot |

## 2. 运行进程【已实现/已存在】
- 后端：Uvicorn ASGI **:8011（`make dev` 开发）**；Celery worker+Beat（`make celery`，Beat 用 `DatabaseScheduler`，周期任务存 `django_celery_beat` 表）；NATS 监听（`make start-nats`）。
  - Celery 由 `ENABLE_CELERY` 环境变量开关（默认 `False`）：仅当为 `true` 时才把 `django_celery_beat`、`django_celery_results` 装入 `INSTALLED_APPS`，并遍历各 app 的 `<app>.config.CELERY_BEAT_SCHEDULE` 聚合为 `CELERY_BEAT_SCHEDULE`。关键默认值：`CELERY_WORKER_CONCURRENCY=2`、`CELERY_MAX_TASKS_PER_CHILD=5`（worker 执行 5 个任务后自销毁释放内存）、`CELERY_RESULT_BACKEND` 取自 env（`celery.py:9-43`）。【已实现】
  - ⚠️ 生产 web Dockerfile 配置 `NEXTAPI_URL=http://bklite-server:8000`，与开发端口 :8011 不一致，部署时需统一后端容器端口（`web/Dockerfile`）。
- 前端：web :3000、mobile :3001。
- agents：stargazer :8083、nats-executor、ansible-executor。
- 算法：BentoML :3000。

## 3. 容器与编排【已实现/已存在 + 待确认】
- web 多阶段 Dockerfile（`NEXTAPI_URL=http://bklite-server:8000`）。【已实现】
- `deploy/dist/bk-lite-kubernetes-collector/` 含两套采集 manifest（均部署于命名空间 `bk-lite-collector`）：【已实现】
  - `bk-lite-metric-collector.yaml`：指标采集（cadvisor `0.56.2`、telegraf `1.29.5`、kube-state-metrics、vmagent remoteWrite）。
  - `bk-lite-log-collector.yaml`：日志采集 vector `0.39.0` DaemonSet，挂载 `/var/log`、`/var/lib/docker/containers`、`/proc`、`/sys` 与 `nats-ca-cert`，经 `kubernetes_logs` 源采集后以 TLS+user/password 写入 NATS（subject `vector`）。（DaemonSet 与挂载 `bk-lite-log-collector.yaml:9-78`；source/sink `bk-lite-log-collector.yaml:146-224`）
- **完整平台 K8s 编排（各 app/agent/中间件）位置缺失**。【待确认】

## 4. 配置约定【已实现/已存在】
- app 自动注册进 INSTALLED_APPS（`base`/`core`/`rpc` 常驻，其余受 `INSTALL_APPS` 控制）。
- URL 自动路由 `api/v1/<app>/`（`server/urls.py`）。
- split_settings：`config/components/*.py`。
- 关键环境变量：`DB_*`、`INSTALL_APPS`、`NEXTAPI_URL`、`NATS_*`、`MINIO_*`、`CELERY_BROKER_URL`、`MLFLOW_TRACKER_URL`、`VICTORIALOGS_*`；模板 `server/envs/.env.example`、`server/support-files/env/*.example`。
- NATS 连接环境变量（`nats.py:10-72`）【已实现】：
  - TLS：`NATS_TLS_ENABLED`（默认 `false`）、`NATS_TLS_INSECURE`（跳过证书验证，默认 `false`）、`NATS_TLS_CA_FILE`（自定义 CA）、`NATS_TLS_HOSTNAME`（强制校验主机名）、`NATS_TLS_CERT_FILE`/`NATS_TLS_KEY_FILE`（客户端证书）。
  - 认证：`NATS_USER`/`NATS_PASSWORD`、`NATS_TOKEN`。
  - 重连：`NATS_RECONNECT_WAIT`（默认 `2` 秒）、`NATS_MAX_RECONNECT`（默认 `60` 次）。

## 5. 风险 / 待确认
- 完整部署清单与编排（除采集器外）【待确认】。
- MinIO 内置默认凭据已移除（BL-NEW-006）：`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` 默认空字符串，仅从 env 读取，未配置即因凭据无效连接失败，不再以众所周知的默认账户访问对象存储（`minio.py:11-15`）。【已实现】
- 默认凭据风险聚焦 RabbitMQ：`CELERY_BROKER_URL` 默认 `amqp://admin:password@rabbitmq.lite/`，生产需加固（`celery.py:13`）。【已实现风险】
- JetStream 生产启用与否影响 job 日志/安装【已实现风险】。

## 6. 证据来源
`server/config/components/{app,base,database,cache,celery,nats,minio,mlflow,log,locale,drf,enterprise,extra}.py`、`server/Makefile`、`web/{Dockerfile,.env.example}`、`deploy/dist/bk-lite-kubernetes-collector/{bk-lite-metric-collector.yaml,bk-lite-log-collector.yaml}`。
