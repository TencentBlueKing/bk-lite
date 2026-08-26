# OpenAPI 统一网关 / 对外暴露规范

> 对外 API 的唯一入口是 `/openapi/v1/{service}/*`。本文是**改动网关或暴露接口前的预防性规范**，
> 每条给 **✅ 正确姿势** 与 **❌ 反模式**。
> 与[后端编码规范](backend-engineering.md)、[平台安全](platform-security.md)配套。
> 用法：新增 / 修改对外接口、改 `server/apps/core/openapi/`、或接入外部服务前，对照本文。
> 操作手册见 `docs/openapi-gateway/onboarding.md`；契约冻结清单见
> `specs/changes/openapi-unified-gateway/design.md` 第 8 章。

## 0. 一句话边界

网关负责**认证、审计、路由**；**不负责**接口级授权、调用超时、内部接口限流。
数据可见范围由被暴露函数自身的组织过滤逻辑负责——网关保证身份不可伪造，**保证不了函数用了这个身份**。

## 1. 对外契约（发布后不可变，改动前先回文档评审）

- ✅ **新增对外能力一律走网关**：内部函数用 `@openapi_expose`，外部服务写 NATS KV 注册表。
  - ❌ 在 app 里新增散落的 `open_api` view / 新开对外端口——绕过统一认证与审计，且不受契约约束。
- ✅ **`path`、暴露 serializer 的字段名与类型、错误码语义、身份头格式**一经发布即冻结；
  请求 schema 只能新增可选字段，响应只能新增字段。
  - ❌ 改名 / 收紧 / 删除已发布字段，或复用旧 `path` 承载新语义——破坏性变更必须以**新 path 或新版本段**发布。
- ✅ **内部实现可自由重构**：函数名、形参名、内部 serializer 与调用链，通过暴露专用 serializer 与
  `param_map` 与契约解耦。
- ✅ 新增错误码只能追加（additive），不得复用或改变既有 code 的语义。

## 2. 内部接口暴露（`@openapi_expose`）

- ✅ **默认全关、显式 opt-in**：未声明装饰器的函数不可经网关调用（404）。
- ✅ **暴露专用 serializer**（`apps/<app>/openapi_serializers.py`），继承
  `OpenAPIRequestSerializer` / `PaginatedRequestSerializer`。
  - ❌ 复用内部业务 serializer——内部迭代改字段会静默破坏对外契约；❌ `fields = "__all__"`。
- ✅ **service 段命名 `^[a-z][a-z0-9-]{0,31}$`**：应用目录名含下划线时须转写（`patch_mgmt` → `patch-mgmt`）。
- ✅ **`inject` 按函数已有的组织参数协议选**：`team_list`（函数收授权组织集合，不级联）、
  `team_list_with_user`（同样注入组织集合，并额外注入只含可信 `user`/`domain` 的 `user_info`，用于持久化审计）或
  `user_info`（函数自查 `group_list` 并级联；serializer 必须声明字面名 `team` 的锚点字段，
  `team`/`include_children` 会被抽取合并进 `user_info`，不再作为独立参数下传）。
- ✅ **多分支函数只暴露已做组织过滤的分支**：用 `ChoiceField` 的 `choices` 收窄，其余分支自然 400。
  - ❌ 直接暴露含无过滤分支的函数——该分支即为跨租户泄漏通道。
- ✅ **`permission` 与 `permission_app` 成对声明**；`permission_app` 取该应用菜单定义的
  `client_id`（`server/support-files/system_mgmt/menus/<app>.json`），**多数与目录名不同**
  （`patch_mgmt`→`patch`、`alerts`→`alarm`、`system_mgmt`→`system-manager`、`node_mgmt`→`node`、
  `job_mgmt`→`job`、`console_mgmt`→`ops-console`、`operation_analysis`→`ops-analysis`）。
  - ❌ 用应用目录名当 `permission_app`——取值错误**不会报错**，且超管直通导致管理员账号测不出，
    只在非超管调用时表现为全量 403。声明 permission 后**必须用非超管账号实测一次**。
- ✅ **`team_free` 仅限无组织维度的公共元信息接口**，须附「响应不含组织字段」断言测试并经安全评审。

### 启动期 fail-closed（契约错误阻断启动，属预期行为）

缺 schema、缺 `inject`、身份参数缺失、`path` 非法、service 名违规、重复注册、
`inject='user_info'` 但 serializer 未声明 `team`、声明 `permission` 却漏 `permission_app`
—— 均在 `AppConfig.ready` 阶段抛 `ImproperlyConfigured`。

- ✅ 契约类校验**继续走 fail-closed 阻断启动**：契约错误是代码缺陷。
  - ❌ 为了「让服务先起来」把这类校验降级为告警——错误会伪装成运行时 500/403，排查成本极高。
- ⚠️ 注册时**不校验** serializer 字段名与函数形参是否匹配，错配在真实调用时抛 `TypeError`
  并被兜底成 500；首次暴露后必须真实调用一次。

## 3. 身份注入不变式（安全红线）

- ✅ **身份只能来自服务端认证结果**（username / 授权组织集合），客户端请求中的身份字段一律丢弃。
- ✅ **选择可以来自客户端**（组织锚点、业务 group 参数），但必须被校验或被函数内既有权限逻辑自然约束。
- ✅ **认证永远从凭据重新推导**，不信任任何入站头、不假设流量必经 Traefik（server 端口在内网仍可达）。
  - ❌ 依据 `X-BK-*` 头判定身份——这些头由网关注入，server 侧只作为审计信息。
- ✅ 组织越权返回 `403 TEAM_OUT_OF_SCOPE`，与普通业务拒绝（400）区分。

## 4. 双租户测试是暴露的准入条件（CI 门禁）

- ✅ 每个暴露端点必须有双租户测试（两个组织身份分别调用，断言读隔离与写归属），
  并登记到 `server/apps/core/openapi/tests/tenant_coverage.py`。
  - ❌ 只测「能调通」——签名合规却 `objects.all()` 的函数会安静跨租户泄漏，请求返回 200 无报错，
    静态检查与类型系统都发现不了。
- ✅ 端点下线时同步清理登记项（`test_governance.py` 会因陈旧登记失败）。
- ⚠️ 现有 `testing.py` 只提供 API 令牌身份 helper；锚点式端点的 JWT 路径需自行构造
  （参考 `test_gateway.py::make_jwt_tenant`），否则测不到「客户端指定锚点」这条关键路径。

## 5. 外部服务注册与部署侧红线

- ✅ **注册条目只存引用不存明文**：`shared_secret_ref` / `token_ref` 用 `env:VAR` 形式。
  - ❌ 把密钥明文写进 KV 条目——KV 无加密语义，读权限即等于拿到凭据。
- ✅ **`base_url` 允许清单 fail-closed**：未配置 `OPENAPI_BASEURL_ALLOWLIST` 即拒绝一切外部条目；
  后缀匹配须落在**点边界**（`itsm-svc` 不得放行 `evil-itsm-svc`）。
- ✅ **注册即封锁直连**：外部服务端口若可绕过 Traefik 直达，统一认证 / 审计 / 限流即成摆设；
  用 `wxc openapi register --probe host:port` 复测验收。
- ✅ **Traefik 中间件链第一跳清除入站 `X-BK-*` 头**；`trusted-header` 模式同时清空转发给上游的
  `Authorization`（否则上游可拿调用方平台令牌冒充其回调平台）。
- ✅ **`_provider` / `_auth` 不得暴露到公网入口**：前者渲染结果内含下游明文密钥，二者的消费方
  只有 Traefik 自身（走 compose 内网直连）。
- ✅ **渲染动态配置时空小节必须省略**：Traefik 解码器拒绝空 map（`routers cannot be a
  standalone element`）并会**整份丢弃**配置，连带合法中间件一起失效；未注册外部服务是常态。
- ✅ 渲染器对坏条目**逐条跳过并告警**，不因单条失败拖垮整份配置。

## 6. 已知边界（新增能力前先确认是否仍然成立）

| 边界 | 现状 |
| --- | --- |
| 调用超时 | `OPENAPI_INVOKE_TIMEOUT` 未接入配置，网关不会中断慢接口 |
| 接口级授权 | 无。仅服务级 `required_roles` 与内部端点权限位，且**超管身份均直接绕过** |
| API 令牌 | 永不过期、无 scope、无轮转；权限等于生成账号的全部权限 |
| HA | 注册表（NATS KV）不随主备切换复制，须主备两端各注册 |
| 多 worker | `_me` / `_docs` / `_auth` 的外部服务数据以进程内快照为基础，读侧距上次 KV 对账超过 TTL（`OPENAPI_REGISTRY_CACHE_TTL`，默认 10 秒，0 为每次同步回源）时触发对账，滞后 ≤ TTL + 一次对账耗时。温快照按 stale-while-revalidate 执行：过期读立即返回现有快照、后台线程回源，请求线程不等待 NATS（仅进程冷启动首次对账与 TTL=0 同步，且受 KV 读取整体硬预算约束）；KV 不可达时降级最近快照，故障不被读流量放大。仍不能作为可用性判据：实际可调还取决于 Traefik 已拉取路由 |
| 存量 open_api | 与网关并存，逐步收编；新增能力不得再走存量路径 |

## 7. 改动网关自身代码时

- ✅ 改 `server/apps/core/openapi/` 前先读 `design.md` 第 8 章冻结清单；**实现与清单冲突时先回文档评审**，
  不得在代码里就地改契约。
- ✅ 涉及 Traefik 渲染输出的改动，必须在真实环境验证 Traefik **确实接受**该配置——
  单元测试只能验证结构，验证不了解码器是否接受（空 map 缺陷即由此漏网）。
- ✅ 部署侧（`bklite-website` 仓库）与 server 侧的契约变更需同步：入口路由、中间件链、
  `providers.http`、令牌 env 落盘（`.env` 是 compose 的插值源，只写 `common.env` 会在重启后失效）。
