# BK-Lite 产品技术架构

> BK-Lite（蓝鲸轻量版）是腾讯蓝鲸生态的轻量级 IT 运维平台，以 AI 原生、轻量部署、渐进式体验为核心设计目标。

---

## 1. 整体架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Web 控制台（前端）                            │
│   Next.js 16 + React 19 + TypeScript + Ant Design 5                  │
│                                                                       │
│  系统管理  CMDB  节点管理  监控  日志  告警  运营分析  OpsPilot(AI)    │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ HTTP/REST API
┌──────────────────────────────────▼───────────────────────────────────┐
│                          后端服务层                                    │
│   Python 3.12 + Django 4.2 + Django REST Framework                   │
│   Uvicorn（ASGI 服务器）+ Celery（异步任务队列）                       │
│                                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │系统管理  │ │  CMDB    │ │ 节点管理 │ │  监控    │ │   日志    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │  告警    │ │ 运营分析 │ │OpsPilot  │ │  MLOps   │ │  Console  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ NATS 消息总线
           ┌───────────────────────┼─────────────────────────┐
           │                       │                         │
┌──────────▼────────┐  ┌───────────▼──────────┐  ┌──────────▼────────┐
│   数据存储层       │  │     中间件层           │  │   采集 Agent 层   │
│                    │  │                       │  │                   │
│  PostgreSQL/MySQL  │  │  Redis（缓存/队列）    │  │  Stargazer Agent  │
│  VictoriaMetrics   │  │  NATS（消息总线）      │  │  Vector           │
│  VictoriaLogs      │  │  MinIO（对象存储）     │  │  Filebeat         │
│  FalkorDB/Neo4j    │  │  Celery（任务调度）    │  │  Packetbeat       │
│  DuckDB（分析）    │  │                       │  │  Auditbeat        │
└────────────────────┘  └───────────────────────┘  └───────────────────┘
```

---

## 2. 模块说明

### 2.1 前端（`web/`）

| 技术栈 | 版本 | 说明 |
|--------|------|------|
| Next.js | 16.x | React 全栈框架，支持 SSR/SSG |
| React | 19.x | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Ant Design | 5.x | 企业级 UI 组件库 |
| @antv/g6 | 5.x | 图可视化（拓扑图、CMDB 关系图） |
| @xyflow/react | 12.x | 流程图编辑器 |
| next-auth | 4.x | 身份认证 |
| axios | 1.x | HTTP 请求客户端 |
| dayjs | 1.x | 日期时间处理 |

**功能模块**：

| 模块路径 | 功能 |
|----------|------|
| `app/system-manager` | 系统管理（用户、角色、权限、认证源） |
| `app/cmdb` | 配置管理数据库（资产管理、关系图） |
| `app/node-manager` | 节点管理（Agent 部署与管理） |
| `app/monitor` | 监控管理（指标、告警策略、仪表盘） |
| `app/log` | 日志管理（采集、检索、分析、告警） |
| `app/alarm` | 告警中心（统一告警汇聚） |
| `app/ops-analysis` | 运营分析（仪表盘、架构图） |
| `app/opspilot` | AI 运维助手（OpsPilot） |
| `app/ops-console` | 运维控制台 |

### 2.2 后端（`server/`）

**运行时**：Python 3.12 + Django 4.2 + Uvicorn（ASGI）

**核心框架依赖**：

| 依赖 | 版本 | 用途 |
|------|------|------|
| Django | 4.2 | Web 框架与 ORM |
| djangorestframework | 3.15 | REST API 框架 |
| celery | 5.4 | 异步任务队列 |
| django-celery-beat | 2.6 | 定时任务调度 |
| uvicorn | 0.32 | ASGI 服务器 |
| nats-py | 2.9 | NATS 消息总线客户端 |
| redis | 5.0 | Redis 客户端 |
| psycopg2-binary | 2.9 | PostgreSQL 驱动 |
| pydantic | 2.5+ | 数据校验 |
| httpx | 0.28 | 异步 HTTP 客户端 |
| pandas | 2.2+ | 数据分析 |
| duckdb | 1.1 | 嵌入式分析数据库 |
| minio | 7.1 | 对象存储客户端 |
| kubernetes | 29.0+ | K8s API 客户端 |
| loguru | 0.7 | 结构化日志 |

**应用模块**（`server/apps/`）：

| 模块 | 功能 |
|------|------|
| `system_mgmt` | 用户认证、组织管理、权限控制、SSO 接入 |
| `cmdb` | 配置管理数据库（模型、实例、关系图），支持 FalkorDB/Neo4j 图数据库 |
| `node_mgmt` | 节点管理，Agent 生命周期管理 |
| `monitor` | 监控指标采集与存储（VictoriaMetrics），告警策略执行 |
| `log` | 日志采集配置、VictoriaLogs 日志存储与检索，日志告警策略 |
| `alerts` | 统一告警中心，多渠道通知 |
| `operation_analysis` | 运营分析仪表盘，架构图（基于 Isoflow） |
| `opspilot` | AI 运维助手，集成大语言模型 |
| `mlops` | 机器学习运维，算法模型管理 |
| `console_mgmt` | 运维控制台 |
| `core` | 公共基础库（认证、权限、模型基类） |
| `rpc` | RPC 服务（NATS-based） |
| `base` | 基础配置与工具 |

### 2.3 采集 Agent 层

#### Stargazer（`agents/stargazer/`）

云资源与基础设施指标采集 Agent，基于 Sanic 框架（Python 3.12）：

| 技术栈 | 版本 | 用途 |
|--------|------|------|
| Sanic | 24.6 | 高性能异步 Web 框架 |
| NATS-py | 2.10 | 与 BK-Lite 服务通信 |
| prometheus_client | 0.21 | Prometheus 指标暴露 |
| arq | 0.26+ | Redis 异步任务队列 |
| boto3 | 1.35+ | AWS/S3 云资源采集 |
| influxdb-client | 1.49+ | InfluxDB 指标采集 |

支持采集来源：云厂商（阿里云、腾讯云、AWS）、数据库（MySQL、PostgreSQL、Oracle、SQL Server）、中间件（Redis）、K8s 集群、SSH 主机等。

#### 日志采集探针

| 探针 | 框架 | 主要用途 |
|------|------|----------|
| Vector | Rust 原生高性能 | 通用日志采集、Docker/K8s 日志、应用日志 |
| Filebeat | Go | 应用结构化日志（Nginx/Apache/MySQL 等） |
| Packetbeat | Go | 网络流量协议分析 |
| Auditbeat | Go | 文件完整性监控、系统审计 |
| Winlogbeat | Go | Windows 事件日志 |
| Snmptrapd | C | 网络设备 SNMP Trap 采集 |

### 2.4 数据存储层

| 存储组件 | 用途 |
|----------|------|
| **PostgreSQL / MySQL** | 主数据库，存储系统元数据（用户、配置、策略等） |
| **VictoriaMetrics** | 时序指标数据库，存储监控指标数据 |
| **VictoriaLogs** | 高性能日志数据库，存储所有日志数据 |
| **Redis** | 缓存、Celery 消息代理、会话存储 |
| **MinIO** | 对象存储（文件上传、大文件存储） |
| **FalkorDB / Neo4j** | 图数据库（CMDB 资产关系图，可选） |
| **DuckDB** | 嵌入式分析数据库（运营分析场景） |

### 2.5 消息总线（NATS）

NATS 是 BK-Lite 内部各组件通信的核心消息总线：

- **SSO 认证**：通过 NATS 实现统一身份认证接入（`login` / `sync_data` 接口）
- **Agent 通信**：Stargazer / 日志采集探针通过 NATS 上报数据
- **RPC 调用**：模块间服务调用（如节点管理下发命令）
- **事件通知**：告警事件异步推送

### 2.6 算法服务（`algorithms/`）

独立部署的机器学习算法服务，基于 BentoML + uv 管理，提供：

- 日志/文本分类
- 时序异常检测
- 图像/目标检测

---

## 3. 关键数据流

### 3.1 监控指标数据流

```
主机/容器/云资源
      │
Stargazer Agent 采集
      │ NATS
BK-Lite Server 接收
      │
VictoriaMetrics 存储
      │
监控仪表盘 / 告警策略（Celery 定时执行）
      │
告警通知（企业微信/邮件/钉钉）
```

### 3.2 日志数据流

```
操作系统/应用/容器/网络设备
      │
采集探针（Vector/Filebeat/Packetbeat 等）
      │ NATS
BK-Lite Server 接收（日志分组规则匹配）
      │
VictoriaLogs 存储
      │
日志检索 / 日志分析仪表盘
      │ Celery 告警策略执行
告警通知
```

### 3.3 用户请求流

```
浏览器
  │ HTTPS
Next.js 前端（next-auth 身份验证）
  │ HTTP/REST API
Django 后端（JWT 鉴权 + RBAC 权限）
  │
业务逻辑处理
  │
VictoriaMetrics / VictoriaLogs / PostgreSQL
```

---

## 4. 部署要求

### 4.1 最低资源要求

| 组件 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| BK-Lite Server | 2 核 | 4 GB | 20 GB |
| VictoriaLogs | 2 核 | 4 GB | 按日志量 |
| VictoriaMetrics | 2 核 | 4 GB | 按指标量 |
| Redis | 1 核 | 1 GB | 5 GB |
| PostgreSQL | 2 核 | 2 GB | 20 GB |
| NATS | 1 核 | 512 MB | 5 GB |

### 4.2 支持的部署方式

- **Docker Compose**：单机部署，适合开发/测试环境
- **Kubernetes**：生产级部署，支持高可用
- **裸金属**：直接在操作系统上部署各组件

---

## 5. 安全架构

| 安全特性 | 实现方式 |
|----------|----------|
| 身份认证 | JWT Token + next-auth，支持 SSO（NATS）接入 |
| 权限控制 | RBAC（基于角色的访问控制），组织级权限隔离 |
| 传输加密 | HTTPS/TLS（Web），NATS TLS（组件通信） |
| 数据隔离 | 多租户日志分组隔离，按组织过滤数据 |
| 操作审计 | Auditbeat 文件完整性监控，Django 操作日志 |
| 双因素认证 | 支持 TOTP（pyotp），QR Code 绑定 |
| 密码安全 | pycryptodome 加密存储 |

---

## 6. 扩展能力

### 6.1 移动端（`mobile/`）

基于 Next.js 15 + Tauri 2 构建，提供：
- 跨平台桌面应用（Windows/macOS/Linux）
- Android 移动端应用（APK/AAB）
- 与主控制台共享 API 服务

### 6.2 WebChat 组件（`webchat/`）

可嵌入第三方网站的聊天组件，支持 OpsPilot AI 对话能力：
- `@bk-lite/webchat-core`：核心逻辑
- `@bk-lite/webchat-ui`：UI 组件
- `@bk-lite/webchat-demo`：演示应用

### 6.3 OpenAPI

所有模块提供 RESTful API，支持第三方系统集成，详见 [API 文档](api_doc.md)。

---

## 7. 相关文档

- [设计理念](design.md)
- [日志管理白皮书](log_whitepaper.md)
- [项目结构说明](code_framework.md)
- [数据库设计](../db/README.md)
- [安装部署指南](installation.md)
- [API 文档](api_doc.md)
