# ARCHITECTURE.md

> BK-Lite 系统架构总览 —— 面向人与 Agent 的「先读这里」入口。
> 本文只描述**结构与边界**;命令与工作流见 [AGENTS.md](AGENTS.md),设计原则见 [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md)。

## 1. 一句话定位

AI-first 的轻量运维平台:Django 后端 + Next.js 多端前端 + 分布式采集 Agent + BentoML 算法服务,以 NATS / Celery 做异步与分布式协同。

## 2. 顶层模块边界

| 模块 | 路径 | 技术栈 | 职责 | 对外端口 |
|------|------|--------|------|---------|
| Server | `server/` | Python 3.12 / Django 4.2 / Uvicorn(ASGI) / Celery / DRF | 业务后端、API、调度、权限 | 8001 |
| Web | `web/` | Next.js 16 / React 19 / TS / Ant Design / Tailwind | 主控制台 | 3000 |
| Mobile | `mobile/` | Next.js 15 / Tauri 2(Rust) | 移动端 / 桌面端 | 3001 |
| WebChat | `webchat/` | npm monorepo(core/ui/demo) | 嵌入式对话组件库 | — |
| Stargazer | `agents/stargazer/` | Python 3.12 / Sanic | 云资源采集代理 | 8083 |
| Algorithms | `algorithms/` | Python / BentoML / MLflow | 异常/时序/日志/文本/图像/目标检测 | 3000(各服务) |
| Collector | `deploy/dist/bk-lite-kubernetes-collector/` | K8s manifest | 指标/日志采集器 | — |

> 模块优先级与默认工作目录规则见 [AGENTS.md](AGENTS.md#仓库目录默认优先级)。

## 3. Server 内部架构(核心)

### 3.1 配置:split_settings
- 配置拆分在 `server/config/components/*.py`(base / app / database / cache / celery / nats / minio / mlflow ...)。
- 改配置去 `components/`,不要塞进单一 settings。

### 3.2 应用自动发现
- `server/apps/` 下的 app 自动注册进 `INSTALLED_APPS`(`base` / `core` / `rpc` 恒定加载),由 `INSTALL_APPS` 环境变量裁剪。
- URL 自动路由:`server/urls.py` 遍历 `apps.*`,凡含 `urls.py` 即注册到 `api/v1/<app_name>/`。

### 3.3 业务 App 清单(`server/apps/`,15 个)

| App | 领域 |
|-----|------|
| `base` | 认证 / 用户(自定义 `base.User`) |
| `core` | Celery / 中间件 / 公共工具 |
| `system_mgmt` | 系统管理、认证源、权限 |
| `console_mgmt` | 控制台聚合 |
| `cmdb` | 配置管理(图数据用 **FalkorDB**,非 Neo4j) |
| `monitor` | 监控对象 / 指标 / 仪表盘 |
| `alerts` | 告警生命周期 / 通知闭环 |
| `log` | 日志检索与权限链 |
| `node_mgmt` | 节点 / Agent 管理 |
| `job_mgmt` | 作业调度 |
| `mlops` | 模型训练 / 部署对接 |
| `opspilot` | AI 助手(LangChain / LangGraph) |
| `operation_analysis` | 运营分析 |
| `rpc` | 跨服务调用 |

### 3.4 横切关注点
- **多数据库**:PostgreSQL(默认)/ MySQL / SQLite / Dameng / GaussDB / GoldenDB / OceanBase,由 `DB_ENGINE` 选择。
- **认证**:Session / API Secret / 标准多后端;Web 经 `/api/proxy/...` 转发,统一 `bklite_token` cookie(见 [CLAUDE.md](CLAUDE.md) 登录学习项)。
- **异步与分布式**:Celery + Beat 调度,NATS 做分布式消息(`make start-nats`)。
- **对象存储**:MinIO(S3 兼容,`django_minio_backend`)。
- **图存储**:FalkorDB(CMDB),**禁止 Neo4j 语法**。

## 4. 关键数据流(跨模块)

```
采集端                     传输/异步              后端                     前端
Stargazer / K8s Collector ──NATS──▶ server(node_mgmt/monitor) ──DRF──▶ web/mobile
                                         │
                          Celery+Beat ───┤ 告警检测/通知闭环(alerts)
                                         │
                          MLflow ◀───────┤ mlops ──HTTP──▶ algorithms(BentoML)
                                         │
                          opspilot(LangGraph)─▶ webchat 组件
```

## 5. 部署形态

- 各模块独立 Docker 镜像(`*/support-files/release/Dockerfile`);Web 为多模块镜像(system-manager / console / node-manager / cmdb / monitor / opspilot)。
- K8s 部署模板在 `deploy/`。
- 启动编排见 `server/support-files/release/startup.sh`(migrate / createcachetable / collectstatic / supervisord)。

## 6. 延伸阅读

- 运行/构建/回滚:[AGENTS.md](AGENTS.md)
- 设计信条:[docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md)
- 前端规范:[FRONTEND.md](FRONTEND.md) · [web/DESIGN.md](web/DESIGN.md)
- 安全 / 可靠性:[SECURITY.md](SECURITY.md) · [RELIABILITY.md](RELIABILITY.md)
- 数据库 schema(生成式):[docs/generated/db-schema.md](docs/generated/db-schema.md)

> TODO: 补充各 app 之间的同步/异步调用矩阵(确认位置:`server/apps/*/tasks.py`、`server/apps/rpc/`)。
