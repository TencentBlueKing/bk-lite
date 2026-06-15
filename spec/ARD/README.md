# BK-Lite 架构设计文档（ARD）

> 本目录由**代码反向分析**生成，所有结论均以仓库内的代码、配置、目录结构、接口定义、依赖关系、脚本与测试为依据。
> 文档采用三级证据标记：
> - **【已实现/已存在】** —— 代码中可直接定位的事实
> - **【推断】** —— 由代码可合理推断，但缺乏直接证据
> - **【待确认】** —— 架构文档通常应有、但代码中暂未发现明确依据，需人工确认

## 目录结构

| 文档 | 内容 |
|------|------|
| [00-总体架构ARD.md](00-总体架构ARD.md) | 系统级架构文档（12 节）+ 4 张 mermaid 架构图 |
| [modules/cmdb.md](modules/cmdb.md) | 配置管理 / 资产采集 |
| [modules/monitor.md](modules/monitor.md) | 监控告警策略 / 指标采集 |
| [modules/alerts.md](modules/alerts.md) | 统一告警 / 富化 / 降噪 / 通知 |
| [modules/log.md](modules/log.md) | 日志采集 / 查询 / 日志告警 |
| [modules/operation_analysis.md](modules/operation_analysis.md) | 运营分析 / 仪表盘 / 拓扑 |
| [modules/node_mgmt.md](modules/node_mgmt.md) | 节点 / 控制器 / 采集器管理 |
| [modules/job_mgmt.md](modules/job_mgmt.md) | 作业执行 / 脚本 / playbook |
| [modules/mlops.md](modules/mlops.md) | 机器学习生命周期 |
| [modules/opspilot.md](modules/opspilot.md) | AI 助手 / RAG / 知识库 |
| [modules/system_mgmt.md](modules/system_mgmt.md) | 认证 / 用户 / 角色 / 权限 |
| [modules/console_mgmt.md](modules/console_mgmt.md) | 控制台 / 通知 |
| [modules/base_core_rpc.md](modules/base_core_rpc.md) | 公共基座：base / core / rpc |
| [modules/frontend.md](modules/frontend.md) | web / mobile 前端 |
| [modules/agents.md](modules/agents.md) | 分布式 agents（stargazer 等） |
| [modules/algorithms.md](modules/algorithms.md) | BentoML 算法服务 |
| [modules/infra-deployment.md](modules/infra-deployment.md) | 基础设施依赖与部署形态 |

## 维护说明
- 生成日期：2026-06-15
- 生成方式：基于 `master`/`rogerly` 分支代码静态分析
- 重新生成：分析 `server/apps/*`、`web/src/app`、`agents/*`、`algorithms/*`、`server/config/components/*`、`deploy/*`

## 校验状态（三轮双向校验，2026-06-15）
已完成三轮"ARD↔代码"双向校验并修正，主要更正：
1. **nats-executor 主题模式**：实为 `{action}.{location}.{id}`（如 `local.execute.{id}`、`ssh.execute.{id}`），原文方向写反，已改。
2. **MySQL 引擎缺陷**：`DB_ENGINE=mysql` 实际指向达梦 backend（`database.py:31`），已记入风险。
3. **opspilot 外部依赖**：`METIS_SERVER_URL`/`MUNCHKIN_BASE_URL`/`CONVERSATION_MQ_*` 仅在 config.py 定义、代码未引用（占位）；RAG 走本地 pgvector；K8s 经运行时 `kubeconfig_data` 而非 `KUBE_CONFIG_FILE`。
4. **operation_analysis**：为通用 NATS 数据源取数器，未硬编码调用 alerts 统计。
5. **完整性补充**：alerts 漏列 6 个 Celery 任务、log `AlertSnapshot`/补偿任务、node_mgmt/cmdb/opspilot/mlops 漏列模型，均已补。
6. **前端**：web 实为 11 产品模块 + `(core)`/`api`/`no-permission`；鉴权由 axios 拦截器注入（代理透明）。
7. **细节**：后端端口 dev:8011 vs 生产 Docker:8000；认证后端顺序 AuthBackend→APISecretAuthBackend→ModelBackend；仅 object_detection 有 bentofile.yaml。

最终一致性：第三轮抽检 37 项中 36 项通过，余 1 项（alerts webhook 路径含额外 `api/` 段）已修正。
