# BK-Lite OpenAPI 统一网关设计文档

| 项目 | 内容 |
| --- | --- |
| 文档状态 | 修订稿（已完成产品 / 开发 / 架构 / 外部契约四视角评审，v2.x 为按评审意见修订后的版本） |
| 版本 | v2.2 |
| 日期 | 2026-08-17 |
| 适用仓库 | bk-lite（server / deploy）、WeOpsX（部署编排） |

---

## 1. 背景与目标

### 1.1 背景

BK-Lite 当前对外开放 API 的现状存在以下问题：

1. **对外 API 暴露面分散**：`open_api` 路由散落在 cmdb、monitor、node_mgmt、alerts、log、job_mgmt、operation_analysis 等 7 个以上 Django 应用中，各自定义路由与鉴权，平台缺乏统一视图。
2. **认证方式不统一**：各应用的开放接口分别处理凭据校验，无统一的令牌规范与审计口径。
3. **外部集成缺乏收口**：ITSM 等旁挂系统需要与平台互调时，只能各自开设入口，认证、限流、审计均无法统一管理。

### 1.2 目标

1. 将对外 API 收口至单一入口 `/openapi/v1/{service}/*`，实现统一认证、统一审计、统一限流。
2. 内部应用以声明式方式（装饰器）控制暴露面，默认全部关闭。
3. 外部服务（如 ITSM）以注册方式接入，注册后秒级生效，接入无须编写代码。
4. 支持双凭据：API 令牌（机器对机器）与平台登录态 JWT（浏览器及同步代用户场景），全部复用平台现有认证机制。

### 1.3 非目标

以下内容明确不在本期范围内：

- API 令牌的过期、轮转与作用域（scope）机制；
- 接口级细粒度授权（外部服务仅提供服务级粗粒度授权）；
- 外部服务自注册；
- 远端（边缘 Zone）能力的网关暴露；
- 对外 API 流量与 Web UI 流量的进程级隔离（首期以限流兜底，预留部署形态拆分方案）；
- 平台主动发起的出站调用与 webhook 推送（沿用现有告警 / 通知分发机制，不经本网关）。

### 1.4 设计约束

1. **不引入新进程**：不新增任何常驻服务或中间件，复用 Traefik 与 server。
2. **不变更数据库表结构**：全程无 migration，注册数据存放于 NATS JetStream KV。
3. **复用现有机制**：认证、权限、组织模型、配置分发均使用平台既有实现。

---

## 2. 总体设计

### 2.1 架构概览

```
客户端（第三方系统 / 浏览器前端 / ITSM 后端）
    │  Authorization: Bearer <API 令牌 | JWT>
    ▼
Traefik  /openapi/v1/{service}/*
    │  中间件链：① 清除入站 X-BK-* 头 → ② 限流 → ③ ForwardAuth（仅外部服务路由）
    ├─ service = 外部服务（ITSM 等）
    │      └→ 直接反向代理（stripPrefix，注入身份头）→ ITSM
    └─ service = 内部应用
           └→ server · OpenAPI 接入模块
                ├─ 认证函数：双凭据形态路由（middleware 与 ForwardAuth view 同源）
                ├─ invoke 分发器：注册表查找 → 权限位 → schema 校验 → 身份注入 → 本地调用
                └─ KV 渲染器：读取 openapi_registry → 输出 Traefik 动态配置（providers.http）

NATS JetStream KV（bucket: openapi_registry）：外部服务注册表
```

要点：

1. **数据面（业务请求转发路径）不经过 NATS**。server 为 Django 单体，各应用的函数与 `nats_listener` 均在 server 代码库内，内部调用为进程内本地函数调用；NATS 仅承担外部服务注册表（KV）与预留的远端通道。
2. **外部服务流量不经过 server**。Traefik 原生反向代理承担外部服务转发，server 仅通过 ForwardAuth 参与认证。

### 2.2 组件职责

| 组件 | 职责 | 性质 |
| --- | --- | --- |
| Traefik | 统一入口、清除伪造头、限流、外部服务反向代理、ForwardAuth 编排 | 现有组件，新增配置 |
| server · 认证函数 | 双凭据校验与用户态构建，供 middleware 与 ForwardAuth view 共用 | 新增代码 |
| server · invoke 分发器 | 内部暴露函数的路由、校验、身份注入、调用与错误映射 | 新增代码 |
| server · KV 渲染器 | 将 KV 注册表渲染为 Traefik 动态配置 | 新增代码 |
| NATS JetStream KV | 外部服务注册表存储 | 现有设施，新增 bucket |
| webhookd | 维持运维脚本执行器定位，不参与网关数据面 | 不变更 |

### 2.3 核心调用链路

本节以三条端到端链路串联后文各机制，建议先读本节再进入第 3 章。三条链路覆盖全部调用场景：链路一与链路二为调用**内部应用**的两种凭据形态，链路三为经网关调用**外部服务**。

#### 链路一：API 令牌调用内部应用（机器对机器）

适用：第三方系统、脚本、CI；ITSM 异步节点使用服务账号令牌时同样走本链路（额外携带 `X-On-Behalf-Of` 头，仅记录审计）。

```
客户端 ──①──▶ Traefik ──②──▶ server 接入模块 ──③④⑤──▶ 暴露函数 ──⑥──▶ 原路返回
```

| 步骤 | 组件 | 动作 | 失败出口 |
| --- | --- | --- | --- |
| 前置 | 系统管理 | 用户在「API 密钥」页生成令牌，绑定「用户 × 组织」 | — |
| ① | 客户端 | 携带 `Authorization: Bearer <64 字符令牌>` 请求 `/openapi/v1/patch-mgmt/module-data` | — |
| ② | Traefik | 命中 `/openapi/*` 静态路由：清除入站 `X-BK-*` 头 → 限流检查 → 转发 server 统一 invoke 端点（内部路由不挂 ForwardAuth） | 超限 429 |
| ③ | server · 认证函数 | 凭据形态识别：64 字符十六进制 → API 令牌分支 → `UserAPISecret` 哈希查表并填充权限，结果做进程内短 TTL 缓存 | 无效 401 |
| ④ | server · invoke 分发器 | 注册表查 path → 权限位检查 → schema 校验 | 404 / 403 / 400 |
| ⑤ | server · invoke 分发器 | 按装饰器 `inject` 注入（本例 `team_list`）：`team = [令牌绑定组织]`，请求体中身份字段丢弃 | — |
| ⑥ | 暴露函数 | 进程内本地调用，函数按注入集合过滤数据；分发器包装响应并记结构化审计日志 | 软错误 400/403，异常 500 |

#### 链路二：平台登录态（JWT）调用内部应用

适用：平台或 ITSM 前端在浏览器中直调；ITSM 后端在用户**同步**操作中透传该用户 JWT。示例为 cmdb 资产查询（锚点式注入，呼应 3.3.3）。

```
浏览器 / ITSM ──①──▶ Traefik ──②──▶ server 接入模块 ──③④⑤──▶ cmdb 函数 ──⑥──▶ 原路返回
```

| 步骤 | 组件 | 动作 | 失败出口 |
| --- | --- | --- | --- |
| ① | 客户端 | 用户已登录平台（ITSM 与平台同栈单点登录时，ITSM 会话即持有平台 JWT）；将 JWT 显式放入 `Authorization` 头（不使用 Cookie）请求 `/openapi/v1/cmdb/...`，请求参数中携带组织锚点 | — |
| ② | Traefik | 同链路一步骤 ② | 超限 429 |
| ③ | server · 认证函数 | 凭据形态识别：三段式 → JWT 分支 → `_verify_token`（验签、jti 黑名单、过期）→ `build_user_authorization_context` 得到 `group_list` 等用户态 | 无效 / 过期 401 |
| ④ | server · invoke 分发器 | 同链路一步骤 ④ | 404 / 403 / 400 |
| ⑤ | server · invoke 分发器 | 本例 `inject="user_info"`（锚点式）：仅注入认证身份 `{username, domain}`；组织锚点为业务参数原样传递 | — |
| ⑥ | cmdb 函数 | 自查 `group_list` → 以锚点做子树级联展开 → 与资产 `organization` 数组求交，叠加实例级权限规则；锚点选错仅返回空结果集 | 软错误 400/403，异常 500 |

附注：JWT 存在会话有效期，ITSM **异步**场景禁止存储用户 JWT，应改走链路一的服务账号方式（见 3.2.2 配套约束）。

#### 链路三：经网关调用外部服务（ITSM 作为被调方）

适用：任意持合法凭据的调用方访问已注册的外部服务。

```
客户端 ──①──▶ Traefik ──②(ForwardAuth)──▶ server 认证视图
                 │◀──③ 200 + 身份头 ────────┘
                 └──④──▶ ITSM ──⑤──▶ 原路返回
```

| 步骤 | 组件 | 动作 | 失败出口 |
| --- | --- | --- | --- |
| 前置 | 管理员 / wxc | 向 KV bucket `openapi_registry` 写入 itsm 条目 → server 渲染器输出动态配置 → Traefik `providers.http` 秒级加载；部署侧同步封锁 ITSM 直连端口 | — |
| ① | 客户端 | 携带任一合法凭据请求 `/openapi/v1/itsm/tickets/create` | — |
| ② | Traefik | 命中 KV 渲染出的 itsm 路由：清除入站 `X-BK-*` 头 → 限流 → ForwardAuth 回调 server 认证视图 | 超限 429 |
| ③ | server · 认证视图 | 与链路一 / 二同一认证函数（双凭据），另按注册条目 `required_roles` 做服务级授权；通过则返回 200 并携带 `X-BK-User` / `X-BK-Team` 响应头 | 401 / 403（请求在 Traefik 层被拒） |
| ④ | Traefik | 注入身份头（`service-token` 模式再注入外部服务令牌）→ stripPrefix → 反向代理至 ITSM | ITSM 不可达 502 |
| ⑤ | ITSM | 信任网关注入的身份头处理业务（网络上仅 Traefik 可达 ITSM）；响应原路返回，Traefik accesslog 记审计 | — |

---

## 3. 详细设计

### 3.1 统一入口与路由

- 入口前缀：`/openapi/v1/{service}/*`。**`v1` 为契约大版本段**：新增字段、新增接口不升版；破坏性变更（响应结构、错误码语义、注入协议变化）必须以新版本段发布，旧版本按公告周期弃用。版本段是最重要的对外契约止损阀，发布后不可移除。
- **service 名为一级注册实体，与内部 Django 应用名解耦**：server 内维护「service 名 → 处理方（内部应用 / 外部注册条目）」映射，内部应用改名、拆分、合并不改变对外 URL。service 命名规则为 `^[a-z][a-z0-9-]{0,31}$`；下划线开头（`_me`、`_docs` 等）为网关保留命名空间，注册与渲染层拒绝该形态的 service 名。
- 内部应用路由为静态配置：`/openapi/v1/*` 默认转发至 server 统一 invoke 端点，service 级识别由 server 内注册表完成。
- 外部服务路由为动态配置：由 KV 渲染器生成，Traefik 通过 `providers.http` 周期拉取（秒级生效，无须重启）。平台日志组件 system-vector 已采用同一模式从 server 拉取配置，该链路有现成先例。
- 中间件链顺序固定：清除入站 `X-BK-*` 头 → 限流（按 service 配置）→ ForwardAuth（仅外部服务路由挂载；内部路由由 server 自行认证，减少一次回调往返）。

### 3.2 认证设计

#### 3.2.1 双凭据形态路由

认证函数按凭据形态直接分流，不做顺序尝试：

| 凭据形态 | 判别特征 | 验证逻辑（均为现有实现） |
| --- | --- | --- |
| API 令牌 | 64 字符十六进制字符串（256 bit 随机数） | `UserAPISecret` 哈希查表（`APISecretAuthBackend`） |
| JWT 登录态 | 三段式 `xxx.yyy.zzz` | `_verify_token`：SECRET_KEY 验签、jti 黑名单、过期校验 |

认证函数是唯一实现，被两处共用：内部路径的 Django middleware 与外部路径的 ForwardAuth view。

**凭据判别演进规则（冻结项）**：判别优先级为「已注册前缀 > 形态」。64 字符十六进制与三段式 JWT 是仅有的两种无前缀历史形态，其判别归属永久保留；未来任何新增凭据类型（如 OAuth2 access token）必须携带可判别前缀（如 `bkoa_`），不得再依赖形态推断。

**认证缓存**：复用平台现有 `permission_cache` 的版本围栏机制（缓存 key 内嵌 `UserPermissionVersion`，撤权 / 吊销先推进版本号，缓存随之整体失效），不引入独立语义的新 TTL 层；如叠加进程内快缓存，TTL 上限 60 秒，并对外明示「凭据吊销最长延迟 = TTL」；认证失败结果不缓存。

#### 3.2.2 调用场景与凭据矩阵

| 调用方 | 凭据 | 授权注入 |
| --- | --- | --- |
| 第三方系统 / 脚本 / CI | API 令牌 | 注入令牌绑定的组织（单元素集合，刻意收窄） |
| 浏览器（平台 / ITSM 前端） | JWT（显式 Authorization 头） | 注入用户全部授权组织（`group_list`）或认证身份（按 inject 形状，见 3.3.2） |
| ITSM 后端 · 同步代用户调用 | 透传用户 JWT | 同上 |
| ITSM 后端 · 异步节点 | 服务账号 API 令牌 | 注入服务账号绑定的组织；真实用户经 `X-On-Behalf-Of` 头仅记录审计 |

配套约束：

1. JWT 路径仅接受显式 `Authorization` 头，不接受纯 Cookie（规避 CSRF）；CORS 允许来源从外部服务注册条目派生（随注册链路走，不维护需改代码的独立白名单）。
2. 禁止 ITSM 持久化存储用户 JWT；异步场景一律使用服务账号令牌（写入集成规范）。
3. 审计日志记录凭据类型；限流键按凭据主体（令牌 / 用户）区分，429 响应携带 `Retry-After` 头。
4. `X-On-Behalf-Of` 头仅在服务账号令牌场景下被接受，其余场景在网关层丢弃；其值不参与任何鉴权判定，审计记录中标注为「自报、未经验证」，不与服务端验证过的身份混排。

#### 3.2.3 凭据发放（现有功能）

API 令牌由系统管理「API 密钥」页面自助生成（`UserAPISecretViewSet`）：令牌为 64 字符随机十六进制串，仅生成时展示一次，数据库中存储其 SHA-256 哈希；令牌与「用户 × 组织」绑定，同一用户在每个组织下至多一把。

### 3.3 身份注入模型

#### 3.3.1 统一不变式

**身份（username / 授权组织集合）必须来自服务端认证结果；选择（组织锚点、业务组织参数）可以来自客户端，但必须被校验或被现有权限逻辑自然约束。** 客户端请求体中的身份字段一律丢弃。

#### 3.3.2 两种注入形状

现有 `nats_api`（NATS 接口层）函数存在两种组织参数协议，按函数期待的组织参数形状命名：接收授权组织全集的称「全集式」，接收单一组织锚点的称「锚点式」。装饰器通过 `inject` 声明形状，分发器按声明组装，现有函数无须改造：

| 协议 | inject 取值 | 函数期待 | 网关注入 | 信任模型 | 现有代表 |
| --- | --- | --- | --- | --- | --- |
| 全集式 | `team_list` | `team=[授权组织 id 集合]` | API 令牌 → 绑定组织单元素集合；JWT → `group_list` | 函数信任注入集合，校验业务组织参数属于该集合 | patch_mgmt |
| 锚点式 | `user_info` | `user_info={user, domain, team: 锚点, include_children}`（键名以现有代码为准：标识字段为 `user`，非 `username`） | 仅注入认证身份；组织锚点与 `include_children` 为业务参数（API 令牌默认锚定其绑定组织） | 函数仅信任身份，自查 `group_list` 并做级联展开；锚点选错仅返回空结果集，不构成越权 | cmdb |

两点必须说明的口径差异（评审阶段经代码核对确认）：

1. **组织可见范围口径**：全集式现有实现（patch_mgmt）注入后做精确成员校验、**不做级联展开**；锚点式（cmdb）在函数内**自行级联展开子组织**。同一用户经两类接口可见的组织范围可能不同，这是历史实现差异而非有意的权限模型。首批暴露时须在各函数文档中写明其口径；若两种口径均有业务需要，应在 `inject` 中拆分为显式取值（如 `team_list` 与 `team_list_cascaded`），不得靠协议选择隐式决定可见范围。
2. **锚点必须是调用者的直属组织**：现有级联展开实现要求锚点 ∈ 用户直属 `group_list`；传入真实存在但非直属的子组织 id（如直属「华南」的用户直接锚定「广州」）会静默返回空结果而非报错。该规则必须写入对外 API 文档并在 `_me` 响应中可被发现（见 3.6）。

#### 3.3.3 数据域过滤示例（cmdb 资产查询）

以组织树 `1 总公司（├ 2 华南（├ 4 广州 └ 5 深圳）└ 3 华北）`、用户为华南成员为例，参与判定的三个组织列表：

1. 用户 `group_list = [2]`：User 模型字段，仅含直接所属组织；
2. `authorized_team_ids = [2, 4, 5]`：查询时以组织锚点做子树级联展开（`GroupUtils.get_user_authorized_child_groups`）；
3. 资产 `organization = [4]`：实例属性，整数数组，一个资产可挂多个组织。

可见性判定为 **② ∩ ③ ≠ ∅**，其后叠加实例级数据权限规则（`PermissionManage` 将组织到实例白名单、creator 例外编译进图查询条件）。写入侧对称校验：资产 `organization` ⊆ 允许范围。上述逻辑全部为 cmdb 现有实现，经网关暴露时直接继承。

### 3.4 内部暴露：`@openapi_expose` 装饰器契约

#### 3.4.1 示例

```python
@nats_client.register
@openapi_expose(
    path="patch-mgmt/module-data",
    method="GET",
    schema=ModuleDataQuerySerializer,   # 必填，fail-closed
    permission="patch_mgmt-View",       # 缺省时仅要求认证
    inject="team_list",                 # 全集式；cmdb 锚点式取 "user_info"
)
def get_patch_mgmt_module_data(module, child_module, page, page_size,
                               group_id, *, team=None):
    ...
```

#### 3.4.2 不满足即拒绝注册的硬性要求

1. 参数与返回值必须可用 JSON 表达；
2. 必须声明输入 schema（serializer），schema 之外的字段一律拒绝；
3. 必须声明 `inject` 形状（`team_list` / `user_info`）；对应身份参数缺失且未显式声明 `team_free=True` 时拒绝注册。**`team_free` 的治理规则**：仅适用于不含任何组织维度数据的公共元信息接口；声明该标记的函数仍须提供「响应不含组织相关字段」的轻量断言测试，并经 CODEOWNERS 安全评审签字，审计日志对此类调用打标；
4. `path` 显式声明，不跟随函数名，避免内部重构破坏外部契约；
5. **schema 即契约**：每个暴露函数必须使用暴露专用 serializer（禁止直接复用内部业务 serializer），归属 openapi 契约目录、变更走契约评审；分发器采用显式「schema 字段 → 函数形参」映射（缺省同名，可经 `param_map` 覆盖），内部重命名形参只改映射、不破坏外部契约；
6. **schema 演进规则**：已发布函数的请求 schema 只能新增可选字段，响应只能新增字段；改名、收紧、删除已有字段属破坏性变更，必须以新 path（或新版本段）发布。「暴露 schema 变更」纳入 CODEOWNERS 强制评审范围；
7. 注册表内部模型含 `dispatch` 字段（首版仅 `"local"` 一个取值），invoke 分发器核心逻辑对该字段分支，为二期远端（边缘 Zone）通道保留真实的扩展点，避免「本地调用」被硬编码进调用路径；
8. 首批暴露须过「命名评审」关卡：由 API 设计责任人统一 schema 字段命名（组织概念全平台收敛为同一字段名），不把内部 NATS 字段名直接透传为外部契约。

#### 3.4.3 执行与错误约定

1. 暴露函数在 Django Web 进程的 worker 内同步执行：必须短耗时、强制分页；长任务拆分为「提交任务」与「查询结果」两个接口；
2. 装饰器声明 `method` 表达读写语义，只读函数不得有副作用；
3. 错误由分发器统一映射：业务软错误（`{"result": false}`）映射为 400 / 403；未捕获异常映射为 500，堆栈仅写入服务端日志；
4. 可选声明 `permission` 权限位。实现说明：现有 `HasPermission` 为 Django view 装饰器，不能直接套用于 invoke 路径；分发器复用其同款权限数据模型（应用映射表、权限字符串解析、用户权限字典查表）自行实现等价判断，与页面权限保持同一模型；
5. 分发器对每次调用施加**强制超时**（不依赖 API 作者自觉遵守「短耗时」约定），超时即中断并返回错误，避免单个慢请求的尾延迟传导至共享 worker 池。

#### 3.4.4 首批暴露原则

首批清单从现有「查询类、已接收 team 参数、已实现分页」的函数中选取；不符合契约的函数须先改造后暴露。

### 3.5 外部服务注册：NATS KV

#### 3.5.1 注册条目模型

Bucket 为 `openapi_registry`，key 为服务名。示例：

```json
{
  "schema_version": 1,
  "gateway_versions": ["v1"],
  "type": "http",
  "base_url": "http://itsm-svc:8000",
  "strip_prefix": true,
  "paths": ["/tickets/*", "/approvals/*"],
  "auth_mode": "trusted-header",
  "shared_secret_ref": "env:ITSM_GW_SHARED_SECRET",
  "token_ref": "env:ITSM_SERVICE_TOKEN",
  "required_roles": [],
  "rate_limit": { "average": 50, "burst": 100 },
  "doc_url": "http://itsm-svc:8000/swagger.json",
  "enabled": true
}
```

条目演进规则（冻结项）：`schema_version` 首版固定为 1，缺失时按 1 处理；渲染器对**未知字段忽略**（前向兼容）、对**未知版本或已知版本内的未知枚举值整条跳过并告警**（fail-closed）。`auth_mode`、`type` 为封闭枚举。

**注册条目与 URL 版本段的关系**：`/openapi/v1/` 中的版本段是**网关契约版本**（认证方式、头格式、错误体、注册语义的大版本），不是外部服务自身的 API 版本——后者由外部服务在其上游路径中自行管理（`base_url` / `paths` 可指向其任意版本，如 `/api/v2/`）。可选字段 `gateway_versions` 声明该条目挂载的网关版本，**缺省为挂载全部活跃版本**，渲染器将条目渲染到每个所列版本的前缀下（`/openapi/{version}/{service}/*`）。该缺省语义与「未知字段忽略」规则自洽：不认识此字段的旧渲染器的行为恰好等于缺省行为。网关未来发布 v2 时，透传型外部服务的条目通常无须变更（版本差异仅体现为网关注入行为的差异），过渡期可用该字段把个别服务限定在单一版本。

- `paths` 支持接口级白名单，省略时该前缀下全部路径均被反向代理；
- `auth_mode` 支持信任头模式（`trusted-header`）与服务账号模式（`service-token`），两种模式定义见 3.5.4；
- `shared_secret_ref` 为信任头模式下网关与外部服务间共享密钥的引用（按服务隔离，非全局共享），转发时以 `X-BK-Gateway-Auth` 头注入（属 `X-BK-` 保留前缀族，天然受入站清除规则保护）；
- `token_ref` 为外部服务令牌的引用地址（环境变量或 secret），不存明文；
- `required_roles` 提供服务级粗粒度授权，认证视图从 `X-Forwarded-Uri` 解析 service 后检查；**空数组语义冻结为「放行任意已认证身份」**，并以单元测试锁定，防止重构反转；
- `rate_limit` 默认按调用方凭据主体分桶（防单一调用方耗尽配额），如需保护下游总容量的服务级聚合限流须显式声明；
- 渲染器内部维护「KV 字段 → Traefik 参数」的显式映射层，KV 字段名不与 Traefik 中间件参数名耦合，Traefik 侧变化只改映射、不改已落地条目。

#### 3.5.2 生效链路

管理员或 wxc（平台统一部署命令行工具）写入 KV → server KV 渲染器读取并校验 → Traefik `providers.http` 周期拉取 → 路由秒级生效。

#### 3.5.3 五条纪律

1. **渲染器必须校验并容错**：schema 校验不通过的条目跳过并记录告警，不得影响其余条目渲染；**`token_ref` / `shared_secret_ref` 的引用可解析性纳入校验范围**，解析失败同样跳过并告警（fail-closed），不得静默降级为无凭据转发；
2. **密钥不得以明文写入 KV**：`token_ref` 仅存引用（环境变量 / secret），渲染时解引用；
3. **写入权限收口**：首期仅管理员或 wxc 可写；外部服务自注册须按 `$KV.openapi_registry.*` 配置 subject 前缀权限，列为二期；
4. **`base_url` 目标允许清单**：渲染器校验 `base_url` 必须落在部署侧预定义的内部服务命名空间 / 域名后缀内，超范围条目跳过并告警——防止一条 KV 写入即把任意内网地址（数据库、元数据端点）挂到认证反代之后（SSRF 面收敛）；
5. **注册流程以直连探测收尾**：ITSM 等外部服务注册完成后，由 wxc 自动从 Traefik 之外的网络位置探测其端口是否仍可直达，可达即告警（红线 3 的自动化验证）；同时 wxc 提供 `validate`（写前 dry-run 校验）与 `status`（列出各条目生效 / 告警状态）子命令，交付工程师无须查看 server 日志即可自助确认注册结果。

#### 3.5.4 身份传递模式

- **信任头模式**：ITSM 信任网关注入的 `X-BK-User` / `X-BK-Team` 头。前提：ITSM 与平台用户体系已打通；部署侧保证 ITSM 端口仅 Traefik 可达（compose 网络隔离 / NetworkPolicy），并以网关与 ITSM 间共享密钥头兜底。
- **服务账号模式**：注册条目引用 ITSM 颁发的服务令牌，转发时注入；ITSM 侧见到服务账号身份，真实用户仅入审计。适用于用户体系未打通的场景。

#### 3.5.5 外部服务侧身份处理演示

本节为外部服务（以 ITSM 为例）开发者的对接指引，演示信任头模式下如何消费网关注入的身份信息。

**外部服务收到的请求**（原始请求为 `POST /openapi/v1/itsm/tickets/create`，经 stripPrefix 与身份注入后）：

```http
POST /tickets/create HTTP/1.1
Host: itsm-svc:8000
Content-Type: application/json
X-BK-Gateway-Auth: <shared_secret_ref 解引用后的共享密钥>
X-BK-User: zhangsan@domain.com
X-BK-Team: 2
X-On-Behalf-Of: lisi@domain.com        # 仅服务账号场景存在

{"title": "交换机故障", ...}
```

`X-BK-Team` 的口径：API 令牌 → 绑定组织（单值）；JWT → 用户**直属组织**列表（逗号分隔，不做级联展开，子组织可见性由外部服务自身权限模型决定）。

**外部服务侧处理五步**（伪代码）：

```python
def gateway_identity_middleware(request):
    # 1. 共享密钥校验——唯一的信任根，常数时间比较；缺失或不符一律拒绝，
    #    即使来源 IP 看似可信（IP 不是信任依据）
    if not hmac.compare_digest(
        request.headers.get("X-BK-Gateway-Auth", ""), GW_SHARED_SECRET
    ):
        return reject_401()

    # 2. 解析身份：X-BK-User 形如 user@domain，缺失即 400
    user_id = request.headers["X-BK-User"]
    teams = [int(t) for t in request.headers.get("X-BK-Team", "").split(",") if t]

    # 3. 映射本地用户：与平台同用户体系时直接查询；
    #    查不到按集成策略处理（首次自动创建影子账号，或直接拒绝）
    local_user = resolve_or_provision(user_id)

    # 4. 组织授权：以 teams 为本次请求的数据域边界，接入 ITSM 自身权限模型
    request.ctx = Context(user=local_user, teams=teams)

    # 5. 审计：X-On-Behalf-Of 仅记录并标注「自报、未经验证」，不参与鉴权
    audit_log(actor=user_id,
              on_behalf_of=request.headers.get("X-On-Behalf-Of"),
              on_behalf_verified=False)
```

**三条禁令**：

1. 不得信任任何未通过 `X-BK-Gateway-Auth` 校验的 `X-BK-*` 头；
2. 不得将 `X-BK-*` 头透传给外部服务自身的更下游系统（防止信任链被隐式延长）；
3. 不得以来源 IP 白名单代替密钥校验（网络拓扑一变即失效）。

**服务账号模式的差异**：请求额外携带 `Authorization: Bearer <ITSM 颁发的服务令牌>`，外部服务按自身令牌体系认证该服务账号并以其权限确定数据域；`X-BK-User` 与 `X-On-Behalf-Of` 仅作审计参考，处理步骤中第 1、2、5 步保留，第 3、4 步替换为服务账号自身的会话逻辑。

### 3.6 内省与文档端点

提供 `GET /openapi/v1/_me`，返回调用方认证上下文，响应结构为字段级冻结项、承诺仅增量演进（只增不删不改名）：

```json
{
  "result": true,
  "data": {
    "user": "zhangsan",
    "domain": "domain.com",
    "credential_type": "api_token",
    "groups": [ { "id": 2, "name": "华南" } ],
    "anchor_scopes": [ { "anchor": 2, "cascaded_group_ids": [2, 4, 5] } ],
    "roles": ["opspilot--admin"],
    "services": [ { "name": "cmdb", "kind": "internal" }, { "name": "itsm", "kind": "external" } ]
  }
}
```

- `groups` 为**直属组织**（含 id 与名称，免第三方二次查询）；`anchor_scopes` 给出锚定每个直属组织后级联可见的完整组织集合——配合 3.3.2 的「锚点必须为直属组织」规则，第三方可自助判断锚点合法性与可见范围，避免对合法但非直属的组织 id 反复得到空结果而无从排查；
- `services` 标注各 service 属「内部代理调用」（响应遵循 3.8 统一契约）还是「外部透传」（响应格式由被代理系统决定，网关仅保证认证与限流统一）；
- 文档聚合预留 `/openapi/v1/_docs`：基于装饰器注册表汇总内部接口清单与各自 JSON Schema（外部服务附 `doc_url` 链接），作为第三方的机器可读接口目录，最小可行版本随首批暴露一并交付。

### 3.7 错误码

| 状态码 | 含义 | 产生组件 |
| --- | --- | --- |
| 401 | 凭据无效或缺失 | server 认证（两路同源） |
| 403 | 权限位 / required_roles 不通过；组织参数越出授权集合 | invoke 分发器 / 认证 view / 暴露函数 |
| 404 | path 不在注册表 | invoke 分发器 |
| 400 | schema 校验失败 | invoke 分发器 |
| 429 | 触发限流 | Traefik |
| 500 | 暴露函数未捕获异常（堆栈仅入日志） | invoke 分发器 |
| 502 | 外部服务不可达 | Traefik |

同一状态码在不同组件产生时，响应体必须同构（见 3.8）：ForwardAuth 认证视图与 invoke 分发器复用同一错误序列化器；Traefik 原生错误（429 / 502 / 未匹配路由）经 `errors` 中间件替换为同构 JSON。404 的存在性语义：对无权限调用方与不存在的 path 返回一致（不泄漏资源存在性）。

### 3.8 对外契约规范

本节各项均为**发布后不可变更**的对外契约，与 3.7 一并构成响应层契约。

1. **统一响应 envelope**（仅覆盖内部代理调用；外部透传服务的响应显式声明为透传、不在承诺内）：
   - 成功：`{"result": true, "data": ...}`
   - 失败：`{"result": false, "code": "<机器可读错误码>", "message": "<人类可读描述>"}`
2. **机器可读错误码枚举**（与 HTTP 状态码映射一次定死）：`AUTH_INVALID`(401)、`PERM_MISSING`(403)、`ROLE_REQUIRED`(403)、`TEAM_OUT_OF_SCOPE`(403)、`SCHEMA_INVALID`(400)、`NOT_FOUND`(404)、`RATE_LIMITED`(429)、`UPSTREAM_UNREACHABLE`(502)、`INTERNAL_ERROR`(500)。403 的三种语义经 `code` 区分，第三方可编程处理。
3. **分页规范**：参数名统一为 `page`（1-based）与 `page_size`；`page_size` 默认 20、硬上限 500，越限取钳制值；分页响应固定为 `data: {"count": <总数>, "items": [...]}`。符合本规范列入 3.4.2 注册硬性要求，首批函数以共享分页 serializer 基类改造。
4. **参数位置规则**：GET 参数一律走 query string（数组编码为逗号分隔）；POST / PUT / DELETE 参数一律走 `application/json` 请求体；混用即返回 `SCHEMA_INVALID`。
5. **身份头值格式**：`X-BK-User` 传 ASCII 安全的稳定标识（`user@domain`），显示名不进头；`X-BK-Team` 为逗号分隔十进制组织 id；`X-On-Behalf-Of` 与 `X-BK-User` 同格式。`X-BK-` 声明为网关保留头前缀。

四条红线，缺一不可。前三条为机制，第四条为对「机制被正确使用」的行为验证。

1. **中间件链第一步清除入站 `X-BK-*` 前缀族头。** ForwardAuth 仅注入认证服务的响应头，不清除客户端伪造的同名头；不显式清除，信任头模式即成提权通道。`X-On-Behalf-Of` 按 3.2.2 配套约束第 4 条处理（仅服务账号场景接受、仅入审计并标注自报）。
2. **身份上下文只能服务端注入。** 遵循 3.3.1 不变式；请求体中的身份字段一律丢弃。**纵深防御**：server 认证函数在内部路径下永远从凭据重新推导身份，不信任任何入站头、不假设流量必经 Traefik（server 端口在内网仍可能被直接访问）；部署侧条件允许时将 server 端口纳入与红线 3 对等的网络收口。
3. **外部服务注册即封锁直连，且封锁必须可验证。**外部服务端口若可绕过 Traefik 直达，统一认证、审计、限流即告失效。「KV 注册」与「网络封锁」在部署侧绑定为同一动作，并以注册流程末尾的自动直连探测（3.5.3 第 5 条）验收，不依赖 runbook 自觉。
4. **双租户测试是暴露的准入条件。** 「函数接收 team 却未使用」表现为静默越权：请求返回 200，数据跨租户泄漏。签名检查无法验证行为，因此每个暴露函数必须附带双租户测试（两个组织身份分别调用，断言读隔离与写归属），CI 中无测试不予合并；辅以数据域 helper 使用约定（违规可检索）、CODEOWNERS 强制评审、审计量级告警。彻底根除依赖数据层强制（行级安全或 scoped manager），列为长期方向。

---

## 5. 运维与部署

1. **Traefik 配置**：入口路由、中间件链、`providers.http` 指向 server 渲染端点，均为静态配置，随 wxc 分发。
2. **KV bucket**：`openapi_registry` 随部署初始化创建；写入渠道见 3.5.3。
3. **审计日志**：invoke 分发器输出结构化访问日志（user、team、path、耗时、状态码、凭据类型、返回量级）；Traefik accesslog 覆盖外部服务路径。
4. **流量隔离**：首期对外 API 与 Web UI 同进程，Traefik 限流 + invoke 分发器强制超时（3.4.3 第 5 条）双重兜底；约定观测指标（openapi QPS、worker 占用比）与具体拆分阈值，达标后以同镜像单独副本组承接 `/openapi/v1/*`（部署形态调整，无须改代码）。
5. **可用性依赖声明**：ForwardAuth 逐请求回调 server，server 不可用时内部调用与外部服务代理**同时不可用**——「数据面不经过 server」不等于可用性解耦；紧急场景运维手册保留手动切换 Traefik 静态配置的旁路。Traefik `providers.http` 拉取失败时保留最后一次已知配置，此行为是本设计的依赖项；KV 条目禁用的生效延迟为一个拉取周期，注销外部服务的操作顺序为「先 `enabled: false`、确认路由下线，再解除网络封锁」。

---

## 6. 限制与演进

| 限制 | 说明 | 演进方向 |
| --- | --- | --- |
| API 令牌无过期 / 轮转 / scope | 令牌永久有效，仅可删除重建；一把令牌等于该用户在该组织的全部权限 | 二期增加过期与最后使用时间（涉及表变更，需另行评审）。本期止损：客户交付资料明确写出「令牌无过期、建议定期删除重建轮转」；「API 密钥」页面基于审计日志弱提示最近认证时间（不动表） |
| 外部服务授权粒度粗 | 仅 `required_roles` 服务级检查 | 二期评估接口级授权。本期交付规范：为每个外部集成方创建仅挂载所需权限的专属角色与账号，用该账号生成 API 令牌，禁止复用内部员工高权限账号令牌 |
| 外部服务不可自注册 | 仅管理员 / wxc 写 KV | 二期按 subject 前缀授权开放 |
| 远端能力不经网关 | 注册表预留远端 subject 字段，分发器首期仅本地调用 | 二期打通边缘 Zone 通道 |
| 静默越权为残余风险 | 四层防御为缓解而非根除 | 长期推进数据层强制 |

---

## 7. 待决策事项

1. 双租户测试作为暴露准入的 CI 门禁，是否确认投入（一次性测试基建 + 首批函数清单）；
2. ITSM 身份传递采用信任头模式还是服务账号模式；
3. JWT 浏览器直调的 CORS 域清单与「禁纯 Cookie」约束是否接受；
4. 流量隔离的拆分阈值与观测指标；
5. KV 写入渠道收口（仅管理员 / wxc）是否确认，自注册是否明确列为二期。

---

## 8. 对外契约冻结清单

以下各项为**发布前必须一次定死、发布后不可再变更**的对外契约面（汇总自四视角评审的 freeze list，正文已逐项落实定义）：

1. URL 前缀 `/openapi/v1/{service}/*`，含版本段语义与升版 / 弃用策略（3.1）；
2. service 命名规则 `^[a-z][a-z0-9-]{0,31}$`、service 名与内部应用名解耦的注册表、下划线保留命名空间（3.1）；
3. 双凭据判别规则（64 字符十六进制 / 三段式 JWT 为仅有的无前缀形态）及「已注册前缀 > 形态」演进规则；仅认显式 `Authorization` 头、不认 Cookie（3.2.1、3.2.2）；
4. 统一响应 envelope 结构，及「外部透传服务响应不在承诺内」的边界声明（3.8）；
5. 机器可读错误码枚举与 HTTP 状态码映射；跨组件同构错误体；429 携带 `Retry-After`（3.7、3.8）；
6. 404 / 403 的存在性语义：无权限调用方不可探知资源存在（3.7）；
7. 身份头族：`X-BK-` 保留前缀；`X-BK-User`（`user@domain`，ASCII）、`X-BK-Team`（逗号分隔整数 id）、`X-On-Behalf-Of`（同 `X-BK-User` 格式，仅服务账号场景接受、仅入审计）（3.8、3.2.2）；
8. 「入站 `X-BK-*` 前缀族必须在网关第一跳清除」规则本身（第 4 章红线 1）；
9. 每个已发布函数的 `path` 与暴露专用 serializer 的字段名 / 类型；schema 只增不删不改名的演进纪律（3.4.2）；
10. 两种注入协议的字段名与口径（`team_list` / `user_info={user, domain, team, include_children}`）、「客户端身份字段一律丢弃」不变式（3.3）；
11. 分页规范：`page`（1-based）/ `page_size`（默认 20、上限 500、越限钳制）、响应 `data: {count, items}`（3.8）；
12. 参数位置规则：GET 走 query（数组逗号分隔），POST / PUT / DELETE 走 JSON 请求体（3.8）；
13. `openapi_registry` 条目 schema：`schema_version=1`、字段清单、`required_roles: []` = 放行任意已认证身份、未知字段忽略 / 未知枚举跳过的演进规则、`gateway_versions` 缺省挂载全部活跃网关版本的语义（3.5.1）；
14. 网关与外部服务间共享密钥头 `X-BK-Gateway-Auth` 的名称与校验方式（按服务隔离）（3.5.1、3.5.5）；
15. `/openapi/v1/_me` 字段级结构（additive-only 演进）；`/_docs` 一旦上线其响应结构同样冻结（3.6）；
16. 认证缓存的「凭据吊销最长延迟 = TTL」安全语义（3.2.1）。

---

## 附录 A：设计依据（代码核对清单）

| 结论 | 依据 |
| --- | --- |
| API 令牌模型与管理页现成 | `server/apps/base/models/user.py`（UserAPISecret）、`server/apps/base/user_api_secret_mgmt/` |
| API 令牌认证后端现成 | `server/apps/core/backends.py`（APISecretAuthBackend） |
| JWT 验证与用户态构建现成 | `server/apps/system_mgmt/nats/auth.py`、`common.py`（_verify_token、build_user_authorization_context） |
| NATS RPC 注册机制 | `server/nats_client/registry.py`（subject 为 `{namespace}.{function}`） |
| 全集式 team 协议范例 | `server/apps/patch_mgmt/nats_api.py` |
| 锚点式 user_info 协议与实例权限 | `server/apps/cmdb/nats/nats.py`、`services/instance.py` |
| 组织子树级联展开 | `server/apps/system_mgmt/utils/group_utils.py` |
| webhookd 不适合作为数据面 | `agents/webhookd/Dockerfile`（fork-per-request 机制与镜像内容） |
| 配置拉取模式先例 | system-vector HTTP provider |

## 附录 B：典型调用示例

```bash
# 1. API 令牌调用内部应用
curl -H "Authorization: Bearer <64 位 API 令牌>" \
  "https://bklite.example.com/openapi/v1/patch-mgmt/module-data?module=patch_target&page=1&page_size=50"

# 2. 浏览器 JWT 调用（ITSM 前端）—— 查询类接口按 3.8 参数位置规则以 POST + JSON 体提交
curl -X POST -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" \
  "https://bklite.example.com/openapi/v1/cmdb/instance/list" \
  -d '{"model_id": "host", "team": 2, "page": 1, "page_size": 20}'

# 3. 查询自身认证上下文
curl -H "Authorization: Bearer <凭据>" \
  "https://bklite.example.com/openapi/v1/_me"
```
