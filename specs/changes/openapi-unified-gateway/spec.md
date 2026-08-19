# OpenAPI 统一网关

完整设计依据见同目录 [design.md](design.md)（v2.2，已完成产品 / 开发 / 架构 / 外部契约四视角评审）；本文件按仓库变更规范提炼行为契约、接缝与验证，实施排期见 [plan.md](plan.md)。

## 目标

将对外 API 收口至 `/openapi/v1/{service}/*` 单一入口，实现统一认证、审计与限流：内部应用以 `@openapi_expose` 装饰器声明暴露并在 server 进程内本地调用；外部服务（ITSM 等）经 NATS KV 注册后由 Traefik 直接反向代理。不引入新进程、不变更数据库表结构。

## 行为契约

### 入口与版本

- 对外入口统一为 `/openapi/v1/{service}/*`；`v1` 为网关契约大版本，破坏性变更必须以新版本段发布。
- `service` 名为一级注册实体，与内部 Django 应用名解耦；命名规则 `^[a-z][a-z0-9-]{0,31}$`，下划线开头为网关保留命名空间（`_me`、`_docs`），注册与渲染层拒绝冲突命名。

### 认证与身份注入

- 认证按凭据形态路由：64 字符十六进制 → API 令牌（`UserAPISecret` 哈希查表）；三段式 → JWT（复用 `_verify_token` 逻辑）。仅接受显式 `Authorization` 头，不接受 Cookie。判别演进规则：已注册前缀优先于形态，新增凭据类型必须带前缀。
- 内部路径由 middleware 认证（不挂 ForwardAuth）；外部服务路径经 Traefik ForwardAuth 回调 server 认证视图。两路复用同一认证函数与同一错误序列化器。
- 认证缓存复用 `permission_cache` 版本围栏机制；如叠加进程内快缓存，TTL ≤ 60 秒且认证失败不缓存；凭据吊销最长延迟等于 TTL 并对外声明。
- 身份注入遵循不变式：身份（user / 授权组织集合）必来自认证结果，选择（组织锚点、业务组织参数）可来自客户端但必被校验或被现有权限逻辑自然约束；请求体中的身份字段一律丢弃。
- 注入形状按装饰器 `inject` 声明适配：`team_list`（全集式，注入授权组织 id 集合）与 `user_info`（锚点式，注入 `{user, domain}`，键名以现有代码为准）。两种协议的组织可见范围口径差异（全集式不级联、锚点式函数内级联，且锚点必须为直属组织）必须写入各函数对外文档。

### 内部暴露（fail-closed）

- 未声明 `@openapi_expose` 的函数一律不可经网关调用；装饰器缺 schema、缺 `inject`、身份参数缺失且未声明 `team_free=True`、path 未显式声明，任一情形拒绝注册（启动即报错）。
- `team_free` 仅限无组织维度数据的公共元信息接口，须附「响应不含组织字段」断言测试并经 CODEOWNERS 安全评审。
- schema 即契约：暴露必须使用暴露专用 serializer（禁复用内部业务 serializer、禁 `fields = "__all__"`），经显式「schema 字段 → 函数形参」映射解耦；已发布 schema 只增不删不改名，破坏性变更以新 path 发布。
- 分发器对每次调用施加强制超时；分页遵循统一规范（`page` 1-based、`page_size` 默认 20 / 上限 500 / 越限钳制、响应 `data: {count, items}`）。
- 注册表内部模型含 `dispatch` 字段（首版仅 `"local"`），分发器核心逻辑对其分支，为边缘通道保留扩展点。

### 外部服务注册

- 注册表为 NATS JetStream KV bucket `openapi_registry`，条目含 `schema_version`（首版 1）与可选 `gateway_versions`（缺省挂载全部活跃网关版本）；渲染器对未知字段忽略、对未知版本 / 未知枚举整条跳过并告警。
- 渲染器校验涵盖：JSON schema、`token_ref` / `shared_secret_ref` 引用可解析性、`base_url` 落在部署侧允许清单内；任一失败该条目跳过（fail-closed），不影响其余条目。
- server 暴露渲染端点供 Traefik `providers.http` 周期拉取；条目写入后秒级生效，无须发版或重启。
- `required_roles: []` 语义冻结为「放行任意已认证身份」，以单元测试锁定。
- 首期仅管理员或 wxc 可写 KV；注册流程以「Traefik 之外网络位置的直连探测」收尾，可达即告警。

### 响应与错误契约

- 内部代理调用统一 envelope：成功 `{"result": true, "data": ...}`；失败 `{"result": false, "code": "<枚举>", "message": "..."}`。外部透传服务的响应显式声明为透传、不在承诺内。
- 机器可读错误码枚举与状态码映射一次定死（`AUTH_INVALID`/`PERM_MISSING`/`ROLE_REQUIRED`/`TEAM_OUT_OF_SCOPE`/`SCHEMA_INVALID`/`NOT_FOUND`/`RATE_LIMITED`/`UPSTREAM_UNREACHABLE`/`INTERNAL_ERROR`）。
- 同一状态码跨组件响应体同构：ForwardAuth 视图与分发器共用错误序列化器；Traefik 原生错误经 `errors` 中间件替换为同构 JSON；429 携带 `Retry-After`。
- 404 对无权限调用方与不存在路径返回一致，不泄漏资源存在性；未捕获异常映射 500，堆栈仅入日志。

### 安全红线

1. Traefik 中间件链第一步清除入站 `X-BK-*` 前缀族头；`X-On-Behalf-Of` 仅服务账号场景接受、仅入审计并标注「自报未验证」。
2. server 认证函数在内部路径下永远从凭据重新推导身份，不信任任何入站头、不假设流量必经 Traefik。
3. 外部服务注册即封锁直连，以注册流程末尾自动直连探测验收。
4. 双租户测试为暴露准入条件：每个暴露函数附双租户测试（读隔离 + 写归属断言），CI 无测试不合并。

## 接缝

- `server/apps/core/openapi/`（新包）：
  - `decorators.py`：`@openapi_expose` 与注册表收集；
  - `registry.py`：service 名注册表、path → 函数映射、`dispatch` 分支模型；
  - `auth.py`：双凭据认证函数（复用 `APISecretAuthBackend` 与 `system_mgmt` JWT 验证逻辑、`permission_cache` 版本围栏）；
  - `dispatcher.py`：invoke 分发（权限位 → schema 校验 → 注入 → 强制超时本地调用 → envelope 包装）；
  - `envelope.py`：统一响应 / 错误码枚举 / 共享错误序列化器；
  - `renderer.py`：KV 条目校验与 Traefik 动态配置渲染；
  - `views.py`：invoke 端点、ForwardAuth 认证视图、`/openapi/v1/_me`、`/openapi/v1/_docs`、渲染端点；
  - `testing.py`：双租户测试 helper（`assert_tenant_isolated` 等）；
  - `serializers.py`：共享分页 serializer 基类。
- `server/apps/core/urls.py`：挂载 `/openapi/v1/` 路由。
- 日志统一 `from apps.core.logger import core_logger as logger`。
- NATS JetStream：新增 KV bucket `openapi_registry`（部署初始化创建）。
- 首批暴露试点：`apps/patch_mgmt`（全集式）与 `apps/cmdb` 各一个查询函数，配套暴露专用 serializer 与双租户测试。
- 跨仓库依赖（不在本仓库实现，见 plan.md）：WeOpsX 侧 Traefik 静态配置（入口路由、中间件链、`providers.http`、`errors` 中间件）；wxc 子命令 `openapi validate` / `openapi status` / 注册收尾直连探测。

## 验证

- 未打装饰器的 nats_api 函数经 `/openapi/v1/*` 调用返回 404；装饰器缺 schema / inject / 身份参数时 server 启动报错。
- 双租户测试：组织 A 令牌不可读组织 B 数据、不可写组织 B 对象（403/404）；`team_free` 函数响应经断言不含组织字段。
- 携带伪造 `X-BK-User` / `X-BK-Team` / `X-BK-Gateway-Auth` 头的请求：经 Traefik 后到达后端时头已被清除；绕过 Traefik 直连 server invoke 端点时身份仍从凭据推导，伪造头不生效。
- 请求体携带 `team` / `user` 等身份字段被丢弃，注入值以认证结果为准（全集式）；锚点式传非直属组织 id 返回空结果集且不越权。
- 错误契约：401/403/400/404/500 响应体符合统一 envelope 且 `code` 枚举正确；ForwardAuth 路径与 invoke 路径的 401 响应体逐字段同构；429 含 `Retry-After`；分页越限被钳制而非报错。
- KV 注册：写入合法条目后路由在一个拉取周期内生效；坏 JSON、未知 `schema_version`、`token_ref` 不可解析、`base_url` 超允许清单四类条目均被跳过并产生告警日志，其余条目不受影响；`enabled: false` 后路由在一个拉取周期内下线。
- `required_roles: []` 放行任意已认证身份的语义有专项单元测试。
- `/openapi/v1/_me` 返回结构含 `user` / `domain` / `credential_type` / `groups`（对象数组）/ `anchor_scopes` / `roles` / `services`（含 internal / external 标注），套统一 envelope。
- 认证缓存：删除 API 令牌 / JWT 进黑名单后，超过声明 TTL 的请求返回 401；认证失败结果不进缓存。
- 凭据吊销、限流、慢函数强制超时、审计日志字段（user、team、path、耗时、状态码、凭据类型、返回量级）各有对应测试或可观测证据。
