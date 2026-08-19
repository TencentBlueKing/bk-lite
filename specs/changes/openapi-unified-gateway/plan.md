# OpenAPI 统一网关 · 实施计划

行为契约见 [spec.md](spec.md)，完整设计见 [design.md](design.md)。本计划按四个里程碑推进，每个里程碑可独立合并、可独立验证；M1 完成前不对外发布任何路由。

## 前置确认（开工前拍板，来自 design.md 第 7 章）

| # | 事项 | 缺省建议 |
| --- | --- | --- |
| 1 | 双租户测试 CI 门禁的投入（测试基建 + 首批清单） | 确认投入，helper 随 M1 交付 |
| 2 | ITSM 身份传递模式 | 信任头模式（用户体系已打通 + 网络封锁可落实时） |
| 3 | JWT 浏览器直调的 CORS 域清单与「禁纯 Cookie」约束 | 接受；CORS 来源从注册表派生 |
| 4 | 流量隔离拆分阈值与观测指标 | openapi QPS 与 worker 占用比，阈值实施前定数 |
| 5 | KV 写入渠道收口（管理员 / wxc），自注册列二期 | 确认 |

## M1 · 契约骨架与内部暴露（server，纯代码）

**范围**：`server/apps/core/openapi/` 新包——`envelope.py`（统一响应 / 错误码枚举 / 共享错误序列化器）、`decorators.py` + `registry.py`（`@openapi_expose`、fail-closed 校验、service 名注册表、`dispatch` 分支模型）、`auth.py`（双凭据形态路由，复用 `APISecretAuthBackend` / `system_mgmt` JWT 逻辑 / `permission_cache` 版本围栏）、`dispatcher.py`（权限位 → schema 校验 → 注入 → 强制超时 → envelope 包装 → 审计日志）、`serializers.py`（共享分页基类）、`testing.py`（双租户 helper）、invoke 端点与 `/openapi/v1/_me`、core urls 挂载。

**试点**：patch_mgmt（全集式）与 cmdb（锚点式）各暴露一个查询函数，含暴露专用 serializer、双租户测试、组织口径的对外文档注释。锚点式注入负载键名先按 design.md 3.3.2 对照现有代码（`user` / `domain` / `team` / `include_children`）逐 app 核对后定稿——评审已确认 alerts 等应用读取字段超出三个基础键，核对范围至少覆盖 monitor / alerts / log / job_mgmt / node_mgmt / operation_analysis。

**明确不做**：KV / 渲染器 / ForwardAuth / 外部服务，一概不进 M1。

**验收**：spec.md「验证」节中装饰器 fail-closed、双租户、身份注入、错误契约、`_me`、认证缓存各条全部通过；`server` 现有测试基线不回归。

**风险**：认证缓存与 `permission_cache` 的集成边界（版本围栏 key 结构复用 vs 新 key 空间）需在实现首日给出小型设计备忘，避免临场发挥。

## M2 · 外部服务注册链路（server + NATS KV）

**范围**：`renderer.py`（条目校验：JSON schema / `schema_version` / `gateway_versions` / `token_ref` 与 `shared_secret_ref` 可解析性 / `base_url` 允许清单；渲染 Traefik 动态配置含中间件映射层）、渲染端点（供 `providers.http`）、ForwardAuth 认证视图（复用 M1 认证函数与错误序列化器，`required_roles` 检查含空数组语义测试）、KV bucket 初始化（部署侧幂等创建，遵循启动硬约束：bucket 创建失败不得阻断 server 启动，渲染端点降级返回最后成功配置或空配置 + 告警）。

**验收**：spec.md「验证」节 KV 注册五类条目行为（生效 / 四类坏条目跳过 / 下线延迟）全部通过；ForwardAuth 与 invoke 路径 401 响应体逐字段同构测试通过。

## M3 · 文档聚合与治理门禁

**范围**：`/openapi/v1/_docs` 聚合端点（内部注册表 + 外部 `doc_url` 链接）；审计日志字段补齐（凭据类型、返回量级）；CI 接入双租户测试门禁（无测试不合并）；CODEOWNERS 覆盖 `apps/core/openapi/` 与全部 `@openapi_expose` 变更；首批暴露命名评审流程落地（API 设计责任人对 schema 字段名把关）。

**验收**：`_docs` 返回机器可读接口清单；故意提交一个无双租户测试的暴露函数，CI 拒绝合并。

## M4 · 部署联调与 ITSM 试点（跨仓库）

**范围**（WeOpsX 仓库 + wxc，本仓库仅配合联调）：Traefik 静态配置（`/openapi/v1/*` 入口、清头 / 限流中间件链、`providers.http` 指向渲染端点、`errors` 中间件输出同构 JSON、429 带 `Retry-After`）；wxc 子命令 `openapi validate` / `openapi status` / 注册收尾直连探测；ITSM 以信任头模式试点接入（KV 条目 + `X-BK-Gateway-Auth` 共享密钥 + 网络封锁 + 直连探测验收），ITSM 侧按 design.md 3.5.5 实现身份处理中间件。

**验收**：design.md 2.3 三条端到端链路在联调环境全部走通（API 令牌调内部、JWT 调内部、任一凭据经网关调 ITSM）；伪造头穿透测试与直连探测告警各演练一次。

## 里程碑依赖与并行度

M1 是唯一硬前置；M2 依赖 M1 的认证函数与错误序列化器；M3 可与 M2 并行（依赖 M1 注册表）；M4 的 Traefik / wxc 配置编写可与 M2 并行起草，联调依赖 M2 完成。

## 全程红线（实现期检查项）

- 遵循 `specs/capabilities/backend-engineering.md`：权限 fail-closed、分页强制上界、不信任消息体身份字段、错误结构统一、serializer 显式列字段、进程级缓存必须有失效机制、日志用 `apps.core.logger`。
- 遵循启动硬约束（`docs/operations/server-startup-dependencies.md`）：KV bucket、渲染端点、NATS 相关初始化全部不得阻断 server 启动，失败走告警 + 运行期补偿。
- 对外契约以 design.md 第 8 章冻结清单为准：实现与清单冲突时先回文档评审，不得在代码里就地改契约。
- 不变更数据库表结构（无 migration）；webhookd 与存量 open_api 不动。
