# 系统架构

> 只记录稳定边界。版本、依赖和端口以各模块的 manifest、Makefile 与部署配置为准；业务规则以 capability spec 为准。

## 顶层边界

| 模块 | 职责 | 主要事实源 |
|---|---|---|
| `server/` | Django API、权限、业务状态、Celery 调度、NATS 消费 | `server/pyproject.toml`、`server/apps/`、`server/config/components/` |
| `web/` | Next.js 主控制台 | `web/package.json`、`web/src/app/` |
| `mobile/` | Next.js + Tauri 客户端 | `mobile/package.json`、`mobile/src-tauri/` |
| `webchat/` | 嵌入式对话组件 monorepo | `webchat/package.json`、`webchat/packages/` |
| `agents/stargazer/` | 云与基础设施采集代理 | `agents/stargazer/pyproject.toml`、`agents/stargazer/plugins/` |
| `algorithms/` | 独立算法服务 | 各服务的 `pyproject.toml`、Makefile |
| `deploy/` | Docker/Kubernetes 交付资产 | `deploy/` 与各模块 `support-files/` |

## 依赖方向

```text
采集端 -> NATS/HTTP -> server -> Web/Mobile
                         |
                         +-> Celery/Beat
                         +-> PostgreSQL/兼容数据库
                         +-> Redis/MinIO/图存储等外部依赖
                         +-> algorithms / external integrations
```

- `server/apps/` 是业务域边界；跨域交互优先通过 service/RPC/任务接口，不直接耦合内部模型。
- Django 配置按 `server/config/components/` 拆分；新增配置进入对应组件。
- Web API 访问走现有代理和鉴权层；不要从浏览器绕过平台边界直连内部依赖。
- 非关键外部资源不得进入阻断启动的必经路径，详见 [可靠性红线](platform-reliability.md)。
- 数据库访问必须遵守 [安全红线](platform-security.md) 与后端编码规范。

## 继续阅读

- [开发与运行](../../DEVELOP.md)
- [后端工程规格](backend-engineering.md)
- [前端工程规格](frontend-engineering.md)
- [工程质量规格](engineering-quality.md)

具体调用关系、表结构、函数签名和测试断言以当前代码为准，不在本文件复制。
