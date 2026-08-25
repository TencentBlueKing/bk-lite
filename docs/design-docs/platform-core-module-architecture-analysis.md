# 平台基础能力模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/base/`、`server/apps/core/`、`server/apps/rpc/`、`server/apps/console_mgmt/`、`server/nats_client/`，以及它们与 SystemMgmt、对象存储、NATS 和外部 HTTP 的直接边界。
> 分析方式：按“身份进入—授权上下文—本地/OpenAPI/RPC 调用—外部副作用—结果与错误返回”完整平台 Interface 分析，不按公共工具文件或单个 tech-debt 拆分。

## 1. 结论摘要

这五个目录共同构成后端平台 Interface：`base` 保存 Django 用户投影与 API Secret，`core` 处理认证、授权、团队数据范围、OpenAPI、公共字段和网络访问，`rpc` 与 `nats_client` 提供进程内/NATS 调用适配，`console_mgmt` 暴露当前用户和控制台入口。它们虽只有约 16,322 行生产 Python，却位于所有业务模块的扇出中心；公共语义一旦含糊，影响会同时扩散到安全、事务、并发和扩展能力。

当前实现已有值得保留的基础：API Secret 使用随机值并保存 SHA-256 摘要；权限缓存用 `permission_version` 代际阻止旧快照重新生效；团队 scope 校验能拒绝失效或未授权组织；OpenAPI 为显式注册且拒绝未知身份字段；安全请求在跨域重定向时剥离认证头；NATS listener 已有有界队列、pending 限制、ack progress、背压拒绝和优雅退出。

但平台层仍有三项必须优先处理的结构风险：

- **认证回调允许调用方指定任意外部 origin**，代码明确承认可跳转到攻击者同路径钓鱼页；这是开放重定向与身份流程边界问题，不能只依赖 OAuth Provider 白名单和 Cookie 不跨域来兜底。
- **`S3JSONField` 把对象存储上传/下载藏在 ORM 字段读写中**：属性访问会发网络请求，`save()` 提交数据库前先上传，失败被折叠为 `None`，全量序列化/解压进入内存，且 `queryset.update`/bulk 语义不成立。
- **SSRF 校验与实际连接分两次解析 DNS**，校验后的 hostname 被 `requests` 再解析；DNS rebinding 可穿过检查，同时公共出口没有统一响应字节、流式读取和总 deadline 预算。

目标不是立刻拆出“基础平台微服务”，而是在当前 Django 进程内建立少而深的五个边界：`AuthorizedActorContext`、`CapabilityRegistry + InvocationEnvelope`、`InvocationCoordinator`、`EgressGateway` 和 `ArtifactReferencePort`。HTTP、OpenAPI、NATS、Celery 与管理命令只做 Adapter，不再各自重新推导身份、权限、团队范围、超时和错误语义。

## 2. 模块规模与职责边界

本次统计生产 Python 约 16,322 行（排除 migrations/tests）。规模最大的文件包括 `core/views/index_view.py`（约 1,150 行）、`core/utils/viewset_utils.py`（约 694 行）、`core/backends.py`（约 496 行）、`core/fields/s3_json_field.py`（约 495 行）、`rpc/system_mgmt.py`（约 457 行）、`core/utils/permission_cache.py`（约 442 行）、`nats_client/clients.py`（约 434 行）和 `console_mgmt/views.py`（约 414 行）。大文件是职责堆叠的信号，但不是单独拆文件的理由。

| 能力域 | 当前实现 | 应拥有的事实/契约 |
|---|---|---|
| 身份认证 | AuthMiddleware、AuthBackend、APISecretAuthBackend、OpenAPI identity | credential 验证结果、subject、credential type、auth revision |
| 授权上下文 | mutable `request.user` 属性、cookie、decorator、ViewSet scope | action、permission revision、current team、data team ids、delegation |
| 能力调用 | `AppClient` 动态 import、OpenAPI dispatcher、`RpcClient`/NATS | versioned capability、同一输入/输出 schema、deadline、request/idempotency id |
| 运行控制 | 固定 OpenAPI 线程池、NATS 全局 worker queue | query/command 分类、并发舱壁、取消/未知结果语义、背压预算 |
| 网络出口 | SSRFValidator + SafeRequests | 一次解析并绑定连接、redirect policy、响应字节与总 deadline |
| 大对象引用 | `S3JSONField` descriptor + model signal | 显式 artifact reference、digest、提交 intent、流式读写、GC |
| 用户投影 | `base.User` 与 `system_mgmt.User` 双模型 | SystemMgmt 主事实 + 有 revision 的登录投影 |

平台基础模块的 Interface 应尽量小：调用方只声明“谁、以什么凭据、在什么团队范围、执行哪个能力、预算是多少”，而不需要知道角色名映射、NATS subject 拼法、线程池取消限制或对象存储路径约定。

## 3. 现状架构图

- [平台基础能力现状架构（Archify HTML）](./platform-core-current.architecture.html)
- [平台基础能力现状架构规格](./platform-core-current.architecture.json)
- [平台基础能力现状架构静态图](./platform-core-current.architecture.light.png)

当前路径可概括为：

```text
HTTP / OpenAPI / 内部 Python 调用 / NATS
            ↓
多套认证身份形状 + cookie/current_team + 多处 app 名推导
            ↓
View/Decorator/OpenAPI dispatcher/AppClient/RpcClient
            ↓
Django ORM / SystemMgmt RPC / NATS / S3 / 外部 HTTP
```

问题不在入口多，而在同一应用用例经不同入口调用时会获得不同的身份形状、序列化、超时、错误与取消语义；本地调用成功不等于远程调用契约成立。

## 4. 应保留并深化的设计

### 4.1 权限代际与 fail-closed 是正确基础

API Secret 认证会同时检查本地用户 active 和 SystemMgmt 用户未禁用，并在权限计算异常时清空权限拒绝访问，见 [backends.py:82](../../server/apps/core/backends.py#L82)；权限缓存 key 包含 `permission_version`，读取与写入后再次检查代际，见 [backends.py:132](../../server/apps/core/backends.py#L132)。这比单纯 TTL 更可靠，应把代际加入统一 actor context，并让所有 Adapter 共享，而不是各自复制缓存和用户属性。

### 4.2 OpenAPI 的显式暴露、schema 拒绝和身份注入方向正确

OpenAPI 只有显式注册能力可被调用，注册阶段要求声明权限所属 app；dispatcher 在 schema 校验后才从认证结果注入用户与授权团队，客户端不能混入身份字段，见 [dispatcher.py:41](../../server/apps/core/openapi/dispatcher.py#L41)。后续应把这套 allowlist 发展为统一 CapabilityRegistry，使本地和 NATS 也执行同一 schema/identity contract。

### 4.3 NATS 的有界队列和 JetStream 进度心跳应保留

listener 使用有界 `asyncio.Queue` 与固定 worker 数，核心订阅设置 pending message/byte limit，队列满时显式拒绝；JetStream 长任务发送 in-progress 并在成功后 ack，退出前 drain 已接收任务，见 [nats_listener.py:118](../../server/nats_client/management/commands/nats_listener.py#L118)、[nats_listener.py:235](../../server/nats_client/management/commands/nats_listener.py#L235)。这些是可靠运行的良好底座，目标设计是在其上增加能力分舱和协议预算，不应退回无界 task-per-message。

### 4.4 SafeRequests 的逐跳校验与跨域凭据剥离可继续深化

SafeRequests 禁用 requests 自动重定向，每一跳重新验证，并在跨 origin 时移除 Authorization、Cookie、Host 和 Proxy-Authorization，见 [safe_requests.py:150](../../server/apps/core/utils/safe_requests.py#L150)。目标 EgressGateway 应复用这些策略，再补齐 DNS 绑定、peer 校验、响应上限和 deadline。

## 5. 身份、登录与授权上下文

### P0：登录认证回调允许任意外部 origin

`validate_redirect_origin()` 仅检查 URL 有合法 scheme/hostname 且无 path/query/fragment，见 [login_auth_request_service.py:105](../../server/apps/core/services/login_auth_request_service.py#L105)；注释明确说明攻击者可以在相同结果路径搭建钓鱼页，随后 `get_login_auth_callback_uri()` 直接把该 origin 拼成 OAuth callback，见 [login_auth_request_service.py:137](../../server/apps/core/services/login_auth_request_service.py#L137)。Cookie 不跨域只能证明 session token 未直接泄露，不能消除登录链被用于可信跳转、品牌仿冒、用户误输凭据和 Provider 配置漂移的风险。

短期必须由部署配置/集成绑定维护可审计的 public origin allowlist，输入 origin 规范化后做精确 `(scheme, host, port)` 匹配；Provider callback 使用服务端固定 public base URL。登录完成后的页面只接受相对 continuation id，由服务端映射到已登记路径，不能继续接受调用方绝对 URL。

### P1：同一请求的身份、权限和团队范围被分散推导

普通 token 经 `AuthMiddleware` 每次调用 `auth.authenticate()` 后又执行 `auth.login()` 并维护 Session，见 [auth_middleware.py:99](../../server/apps/core/middlewares/auth_middleware.py#L99)；API Secret backend 则给 `base.User` 动态挂载 `roles`、`permission`、`group_list` 和 team scope，OpenAPI 再构造独立 `CallerIdentity`。随后 ViewSet 从 cookie 解析 current team，并按类 module path 推导 app，见 [viewset_utils.py:63](../../server/apps/core/utils/viewset_utils.py#L63)。行动权限与对象数据范围不是同一个必经校验，新增 endpoint 容易只加 decorator 而漏掉 scope。

建立不可变 `AuthorizedActorContext`：

```text
subject + domain + credential_type + auth_revision
+ action/capability_id + permission_revision
+ current_team + data_team_ids + include_children/delegation
+ request_id + deadline + audit attributes
```

所有 HTTP/OpenAPI/NATS 入口只构造一次 context，应用用例必须显式接收它；scope 解析失败、权限代际变化或目标组织失效都 fail-closed。普通 Bearer token 保持无状态，不应在每次 API 请求建立/轮换浏览器 Session；只有交互式登录完成时显式创建 Session。

### P1：用户主事实与登录投影混在两个模型中

SystemMgmt User 拥有组织、角色和禁用事实，认证却会 `get_or_create` 并更新 `base.User`，见 [backends.py:435](../../server/apps/core/backends.py#L435)；API Secret 路径又同时查询两个模型。开发者无法仅从类型判断字段是主事实、缓存还是请求期属性。

明确 SystemMgmt 是身份与授权主事实；`base.User` 仅作为 Django 兼容登录投影，保存 `source_revision/synced_at`，不独立拥有授权规则。actor context 从版本化快照构建，动态属性不得作为跨任务或 RPC 契约。

### P1：app/capability 命名靠多份映射与 module path 推断

`AuthBackend`、`HasPermission` 和 permission utils 各自维护 `system_mgmt → system-manager`、`patch_mgmt → patch` 等映射；例如 [backends.py:387](../../server/apps/core/backends.py#L387) 与 [api_permission.py:92](../../server/apps/core/decorators/api_permission.py#L92)。新增/重命名模块时，角色、菜单、OpenAPI 和对象权限可能出现不同 app key。

使用稳定 `capability_id`/`permission_namespace` 注册表；路由、模块名和展示名只是 adapter metadata，禁止从 Python module path 猜授权 namespace。注册启动时检查重复、未知 permission 与缺失 scope policy。

## 6. 请求与 RPC 数据流

- [平台请求与 RPC 数据流（Archify HTML）](./platform-core-request-rpc.dataflow.html)
- [平台请求与 RPC 数据流规格](./platform-core-request-rpc.dataflow.json)
- [平台请求与 RPC 数据流静态图](./platform-core-request-rpc.dataflow.light.png)

### P1：本地、OpenAPI 与 NATS 是三套调用语义

`AppClient.run()` 根据字符串动态 import 并直接调用 Python 函数，返回任意 Python 类型或原始异常，见 [rpc/base.py:42](../../server/apps/rpc/base.py#L42)；`RpcClient.run()` 则拼 NATS method 字符串、JSON 序列化并转换异常，见 [rpc/base.py:11](../../server/apps/rpc/base.py#L11)；OpenAPI 又单独执行 serializer、身份注入、线程池与 envelope。相同 facade 通过 `is_local_client` 切换时，调用方实际面对不同 schema、错误、deadline、身份和幂等性。

建立 `CapabilityRegistry`，每个能力注册稳定 id/version、request/response schema、query/command 类型、scope policy、cost class 和 handler。`LocalInvoker` 与 `NatsInvoker` 都消费同一 `InvocationEnvelope` 并返回同一 `ResultEnvelope`；本地模式也必须经过序列化契约测试，不能成为绕过协议的快捷路径。

### P1：NATS 每次请求新建连接，sync wrapper 每次新建事件循环

`RpcClient` 每次 `run/request` 都用 `asyncio.run()`，见 [rpc/base.py:19](../../server/apps/rpc/base.py#L19)；`nats_client.request()` 每次创建 Client、连接、请求后关闭，见 [clients.py:169](../../server/nats_client/clients.py#L169)。高频跨模块调用会反复付出 DNS/TCP/TLS/认证和连接回收成本，在已有事件循环中调用 sync facade 还会直接失败。

实现进程级 `NatsConnectionManager`：按 server/credential profile 复用异步连接，支持 reconnect、health、drain 和 multiplexing；应用层优先 async，sync facade 只允许在明确的同步边缘使用。连接池不是业务重试器，request deadline、重试和幂等仍由 InvocationCoordinator 统一控制。

### P1：OpenAPI 超时不等于执行取消

dispatcher 使用全局固定线程池，`future.result(timeout)` 超时后调用 `future.cancel()`，见 [dispatcher.py:31](../../server/apps/core/openapi/dispatcher.py#L31)、[dispatcher.py:95](../../server/apps/core/openapi/dispatcher.py#L95)。Python 运行中的线程不会因此停止：调用方收到 TIMEOUT 时，数据库或外部副作用仍可能随后提交；多个慢调用还会占满全部 worker，让无关能力排队。

能力必须先分类：query 接收可传播的 deadline/cancellation token，并在 DB/HTTP/循环边界主动检查；command 先持久创建带 idempotency key 和 fencing token 的 `OperationRun`，返回 `202 + operation_id`，由协调器执行并可查询结果。超时只能表达“结果未知/仍在运行”，不能伪装成已取消。

### P1：NATS 协议缺少版本、调用者、deadline 和稳定错误码

当前请求主体主要是 args/kwargs JSON，subject 由 namespace 与方法名拼接；listener 的失败响应仍序列化 `jsonpickle.encode(error)`，见 [nats_listener.py:272](../../server/nats_client/management/commands/nats_listener.py#L272)。客户端虽已不反序列化 Python 对象，只从旧结构读取字符串，但服务端仍可能把异常属性、敏感上下文和超大对象写入消息。

定义 v2 envelope：`protocol_version、capability_id/version、request_id、idempotency_key、actor_context、deadline_at、trace_context、payload`；错误仅返回 allowlist `code、message、retryable、safe_details、operation_id`，禁止 exception pickle。为 payload、result 和 error 分别设置字节上限；敏感字段按 schema 分类和脱敏，不依赖异常字符串清洗。

### P1：所有 NATS handler 共享一条队列和同一 worker 池

当前有界队列解决了无限积压，但所有 core/JetStream subject 最终进入同一 `_message_queue`，worker 也不区分短查询与长命令，见 [nats_listener.py:118](../../server/nats_client/management/commands/nats_listener.py#L118)。少数慢 handler 会造成队头阻塞，身份/查询类调用与批量任务互相饥饿。

在保留总背压的前提下按能力 cost class 建立舱壁：例如 `auth/control/query/command/bulk` 分别拥有 inflight、queue、deadline、payload/result bytes 和公平调度额度；registry 声明预算，listener 启动时校验。JetStream durable、重试与 ack policy 也应由 capability metadata 明确，而不是一个布尔 `js`。

## 7. 公共网络与大对象边界

### P0：SSRF 检查与连接之间存在 DNS TOCTOU

SSRFValidator 先解析 hostname 并检查所有地址，随后返回仍含 hostname 的 URL；SafeRequests 再把 URL 交给 `requests.request()`，见 [safe_requests.py:187](../../server/apps/core/utils/safe_requests.py#L187)，redirect 也重复相同流程，见 [safe_requests.py:212](../../server/apps/core/utils/safe_requests.py#L212)。校验与连接发生两次 DNS 解析，攻击者可通过 rebinding 在两者之间切换到 loopback、link-local、内网或 metadata 地址。

建立唯一 `EgressGateway`：解析一次并筛选地址，连接绑定获批 IP，同时保留原 Host/SNI 并核对实际 peer；每次 redirect 重复同一流程。统一限制 connect/read/total deadline、redirect 次数、响应字节、解压后字节和流式 chunk；allowlist 记录 owner、用途、协议、端口和有效期。所有 webhook、模型服务、探测和下载不得绕过该端口。

### P0：`S3JSONField` 把网络和外部一致性隐藏为 ORM 语义

字段通过 descriptor 拦截属性访问，见 [s3_json_field.py:101](../../server/apps/core/fields/s3_json_field.py#L101)；第一次读取会同步下载完整对象、解压和 JSON parse，任何错误都返回 `None`，见 [s3_json_field.py:285](../../server/apps/core/fields/s3_json_field.py#L285)。模型 `pre_save` 在数据库提交前全量 `json.dumps`、gzip 并上传，见 [s3_json_field.py:126](../../server/apps/core/fields/s3_json_field.py#L126)、[s3_json_field.py:216](../../server/apps/core/fields/s3_json_field.py#L216)：数据库回滚会留下新孤儿对象，属性访问可能形成隐藏 N+1，内存占用等于 JSON、编码和压缩副本总和。`get_prep_value()` 对 dict/list 返回 `None`，意味着 queryset update/bulk 路径无法遵守字段承诺，见 [s3_json_field.py:338](../../server/apps/core/fields/s3_json_field.py#L338)。

立即冻结新用法。新增显式 `ArtifactReferencePort`：数据库只保存 `artifact_id/key、content_digest、media_type、compressed_size、logical_size、state`；应用服务显式 `stage → persist reference → finalize`，失败有 intent/GC 对账；读取显式 `load/stream`，区分 absent、unavailable、corrupt 和 budget exceeded。现有 APM/MLOps 字段按写路径迁移，最后删除 descriptor，不能再用“访问一个 model 属性”隐藏网络。

## 8. 代码结构：按用例与端口组织，而不是按适配技术堆叠

`core/views/index_view.py` 同时承载登录、OTP、微信、SSO、客户端配置与菜单等多类流程，`console_mgmt/views.py` 又处理当前用户、密码、邮箱、通知等相邻能力；`rpc/*.py` 按远端 app 聚合大量字符串方法转发。当前结构让一个身份用例横跨 middleware/backend/view/rpc/system_mgmt，而一个外部调用同时依赖隐含的 NATS 和本地分支知识。

建议结构：

```text
platform_core/
  identity/       credential validators, AuthorizedActorContext builder
  authorization/ capability policy, team scope, permission revision
  invocation/    registry, envelopes, coordinator, OperationRun
  egress/        DNS-bound HTTP gateway, redirect and response budgets
  artifacts/     reference port, write intent, reader, reconciler/GC
  adapters/
    django_http/ openapi/ nats/ celery/ management_command/
  projections/   Django user/session and compatibility read models
```

这不是要求一次移动全部目录。先让新 use case 依赖这些稳定 Interface，再按 capability 逐步把现有 backend/decorator/view/client 变成薄 Adapter。业务规则仍归 SystemMgmt 或对应业务模块，platform core 只拥有跨入口协议与执行约束。

## 9. 不合理设计要素与优先级

| 优先级 | 设计要素 | 影响 | 优化方向 |
|---|---|---|---|
| P0 | 登录 callback 接受任意合法外部 origin | 开放重定向、钓鱼与 Provider 配置漂移 | server-owned origin allowlist + 固定 callback base + relative continuation |
| P0 | SSRF 校验后由 HTTP client 再次解析 hostname | DNS rebinding 可绕过内网/metadata 阻断 | EgressGateway：pin resolved IP、peer verify、逐跳重验 |
| P0 | S3JSONField 把网络 I/O 藏在字段访问和 model save | 隐藏 N+1、内存放大、回滚孤儿、bulk 语义失真 | 冻结新用法，ArtifactReferencePort + intent + stream + GC |
| P1 | 身份、行动权限和团队数据范围分散推导 | 新入口易漏 scope，不同凭据行为漂移 | immutable AuthorizedActorContext，所有 use case 必需 |
| P1 | `base.User` 与 SystemMgmt User 双事实 | 禁用/角色/组织状态不一致，类型语义含糊 | SystemMgmt 主事实 + 带 revision 的 Django projection |
| P1 | app 名靠多份 map 与 module path 推断 | 重命名和新增模块造成静默授权错误 | stable capability/permission namespace registry |
| P1 | 本地/OpenAPI/NATS 三套调用契约 | 测试通过但远程失败，错误/身份/超时不一致 | CapabilityRegistry + shared Invocation/Result envelope |
| P1 | 每次 RPC 新建事件循环和 NATS 连接 | 高频延迟、连接风暴、async 环境不可用 | process-level async connection manager + edge sync facade |
| P1 | OpenAPI `future.cancel()` 被当作硬取消 | 超时后副作用继续、结果未知、线程池耗尽 | query cooperative deadline；command OperationRun/202/fencing |
| P1 | NATS 异常仍发送 jsonpickle，协议无版本/调用者/预算 | 信息泄露、消息膨胀、演进与审计困难 | v2 typed envelope + structured safe error + byte limits |
| P1 | 所有 NATS handler 共用一个 queue/pool | 慢任务队头阻塞，关键查询被批量任务拖垮 | cost-class bulkheads + fair scheduling + per-capability budgets |
| P1 | token API 每请求执行 `auth.login` | session 写放大，状态式/无状态认证耦合 | bearer context stateless；interactive login 单独建 session |
| P2 | API Secret 仍保留历史明文查询 fallback | 迁移完成后长期扩大密钥暴露面 | 核实迁移覆盖后删除 plaintext shadow path |
| P2 | 身份/控制台用例散落在巨型 View 与 RPC facade | 修改需跨技术层，测试组合膨胀 | application use cases + thin adapters，按能力渐进迁移 |

## 10. 分阶段优化路线

### 短期：0—2 个迭代

1. 修复 login callback：部署级精确 origin allowlist、固定 Provider callback、相对 continuation；增加恶意 origin/默认端口/Unicode hostname/代理 header 测试；
2. 建立 EgressGateway 最小版本，完成 DNS pin/peer verify、redirect 逐跳校验、响应/解压字节和总 deadline；将公共 SafeRequests 调用迁入；
3. 冻结 `S3JSONField` 新增使用，记录现有字段清单；为读写增加显式错误、对象字节/解压字节预算和 orphan 扫描；
4. 移除 NATS 新错误中的 `pickled_exc`，定义稳定错误码/retryable/safe details，限制 payload/result/error 大小；
5. 让 NATS client 复用进程连接并支持 drain/reconnect；监控连接数、请求 latency、queue wait 和 timeout unknown outcome；
6. 建立最小 `AuthorizedActorContext`，先覆盖 OpenAPI 与一个高风险业务能力，验证 HTTP/NATS identity/scope 等价；
7. 将 OpenAPI command 从线程池“超时取消”改为 OperationRun 或明确禁止副作用能力同步暴露。

### 中期：2—5 个迭代

1. 建立 CapabilityRegistry 与 v2 InvocationEnvelope，迁移本地/NATS/OpenAPI 三种 Adapter；
2. action permission、team scope 和 permission revision 合并为一个必经授权决策，并在跨进程时签名/校验 actor context；
3. NATS listener 按 capability cost class 分舱，落地公平调度、inflight、deadline、消息字节和 result budget；
4. 建立 ArtifactReferencePort、write intent、内容 digest 与 GC，迁移 APM/MLOps 的 S3JSONField；
5. 明确 SystemMgmt identity 主事实和 base.User 投影同步协议，移除请求期动态用户属性对业务用例的依赖；
6. 拆分身份、会话、OTP、SSO、当前用户等 application use case，让 View/中间件只做协议转换。

### 长期：5 个迭代以后

1. 所有入口共享 capability contract tests，确保 local/HTTP/NATS/Celery 的 schema、授权、错误、deadline 和幂等语义一致；
2. 以 OperationRun 统一长命令的状态、attempt、fencing、取消、重试和审计，业务模块只提供 handler 与补偿策略；
3. 形成统一的 egress、artifact 与 invocation 容量面板，按团队/能力分配连接、线程、队列、字节和 deadline 预算；
4. 只有当某个协调器需要独立扩缩容、隔离故障或独立发布时，再拆物理服务；先稳定协议与事实模型。

## 11. 目标架构图

- [平台基础能力目标架构（Archify HTML）](./platform-core-target.architecture.html)
- [平台基础能力目标架构规格](./platform-core-target.architecture.json)
- [平台基础能力目标架构静态图](./platform-core-target.architecture.light.png)

目标结构的关键不是新增更多公共类，而是形成五条不可绕过的路径：

```text
Adapter → AuthorizedActorContext → CapabilityRegistry/Policy
        → InvocationCoordinator → Domain Use Case
        → explicit Egress / Artifact / Messaging ports
```

业务模块不再直接拼角色 app 名、NATS subject、对象 key 或外部 URL；平台层也不拥有业务状态机，只统一身份、协议、执行与资源预算。

## 12. 开发同学后续必须注意

1. 新 HTTP/NATS/Celery/管理命令入口必须调用同一应用用例，并证明 actor、scope、schema、错误和幂等语义等价；
2. 不要从 module path、URL 前缀或展示名称推导授权 namespace，必须注册稳定 capability id；
3. 行动权限与数据范围必须在同一授权上下文内完成，禁止“decorator 已鉴权”后默认查询全集；
4. timeout 只表示调用方停止等待，不代表线程、消息或外部系统已取消；有副作用的命令必须有 operation id、idempotency key 和 fencing；
5. 不得在 model property、field descriptor、serializer property 或 signal 中隐藏对象存储/HTTP/NATS 网络调用；
6. 所有外部 URL 必须经统一 EgressGateway，禁止先校验 hostname 再让 client 自行重解析；
7. NATS handler 必须声明 query/command、消息/结果字节、deadline、重试和 JetStream ack 语义；禁止返回 Python exception pickle；
8. 新的大 JSON/模型/报告制品只能保存显式 artifact reference；写入需可对账，读取需有流式与解压预算；
9. token/API Secret 请求保持无状态，不能为每次 API 调用制造 Session 写；浏览器 Session 只在交互式登录边界创建；
10. 公共抽象进入 `core` 前必须证明至少有两个真实调用方和稳定共同语义；不能为了复用几行代码把业务规则吸入平台层。
