# OpenAPI 对外凭据分类：系统 Token 与个人 Token

Status: ready

背景与分析结论：现有 `UserAPISecret` 绑定「用户 × 组织」、永不过期、无 scope，ITSM 等第三方
系统只能拿集成账号（`itsm_openapi` 影子账号）的个人令牌调 CMDB / 告警 / 作业，导致业务创建人
与鉴权主体都是假用户，`X-On-Behalf-Of` 仅自报审计不参与鉴权，员工离职或改角色时集成随之漂移。
本变更把对外凭据拆成两类，网关继续只收 `Authorization: Bearer`，按凭据类型注入不同主语。
对 `openapi-unified-gateway/design.md` 的修订见同目录
[design-amendment.md](design-amendment.md)。

> 评审记录：v2.3 已完成安全/架构与契约/产品双视角文档评审（2026-09-16）并合入 design.md。
> 本版（v2.4）替换 Scope 语义：钥匙不再与权限位求交，只限制「能碰哪些网关接口 / 外部服务前缀」；
> 人的权限仍按现场角色做原来的 `_check_permission`。冻结清单第 18 条同步改写。

## 目标

1. **系统 Token**（发给第三方系统）：令牌内只含系统 ID 与 Scope（接口名单或全部），不编用户、
   不编组织；调用时由第三方以请求头传入用户与组织。网关认人后带出该用户在该组织的现场权限；
   钥匙名单只决定这把凭据能不能碰该路由。业务创建人落真实用户，审计另记 `caller=<系统ID>`。
2. **个人 Token**（发给人）：保持「令牌内身份即主体」，补齐过期时间、Scope、多把并存与按把吊销；
   请求中的任何身份传入字段一律忽略。个人与系统钥匙的 Scope 语义相同。

## 行为契约

### 凭据形态与判别

- 系统 Token 形态为 `bksys_` 前缀 + 64 字符十六进制随机串；按已冻结的判别演进规则
  （已注册前缀 > 形态）在 `authenticate_request` 中**先于形态匹配**识别。前缀先行不是风格
  而是必要：`JWT_RE` 字符集含下划线，畸形串 `bksys_a.b.c` 可匹配 JWT 形态。
- 个人 Token 维持 64 字符十六进制（无前缀），存量令牌不换发。
- 两类凭据数据库中均只存 SHA-256 哈希，明文仅生成时展示一次。

### Scope：网关接口名单与全部

Scope 只限制这把凭据能访问哪些 OpenAPI 网关路由。它不是权限位词表，不与人的菜单权限求交。

新建必须显式二选一，空名单不能保存：

- **全部**（`mode=all`）：运行时通配。当前及以后新注册的内部接口、以及文档目录中的外部服务前缀，
  在钥匙层都放行。不是创建时把当天目录勾满。
- **勾选**（`mode=allowlist`）：只放行名单；以后新接口 / 新外部服务不会自动进入。

目录与接口文档同源：管理页读控制台 `GET /system_mgmt/openapi_docs/`（与文档页同一
`build_docs_catalog()`），不拿钥匙去调网关 `_docs`。JWT 无钥匙 Scope，不进名单检查。

存储形状：

```json
{ "mode": "all" }
{ "mode": "allowlist", "endpoints": ["GET cmdb/classifications", "EXTERNAL itsm"] }
```

存储键不存展示 URL（`/openapi/v1/...`）：

- 内部接口：`{METHOD} {service}/{sub_path}`，方法大写，path 与注册表 `Endpoint.path` 一致。
- 外部服务：`EXTERNAL {service}`。网关对外部本就是按 `/openapi/v1/{service}/*` 前缀统一转发，
  勾选粒度与转发粒度相同，不展开对方 OpenAPI 里的单条 API。

写接口校验：必须是上列两种形状之一；`allowlist` 的 `endpoints` 至少一条；键格式合法。
**不**要求键当时一定存在于目录（避免保存与注册表强耦合）。运行时对不上的键等于没勾。
写路径拒绝旧权限位 JSON（`{permission_app: [权限, ...]}`）。

存量迁移（复用已有 `base.0012` / `system_mgmt.0050`，不要再新建 0013/0051）：

- `null`、`{}`、以及旧权限位 JSON（无 `mode` 字段的对象）一律写成 `{ "mode": "all" }`。
  旧权限位无法无损翻译成接口名单；本功能尚未发货，直接迁成全部。
- 系统钥匙新表无生产存量；若有未提交试写的权限位 JSON，同样迁成全部。

### 系统 Token：登记与发放

- 新模型 `SystemAPIToken`（`system_mgmt`）：`system_id`（标识，如 `itsm`，命名规则同 service 段
  `^[a-z][a-z0-9-]{0,31}$`）、`name`（用途备注）、`secret_hash`、`scope`、`enabled`、
  `expires_at`（可空 = 不过期）、`created_by` / `created_by_domain`。
- 同一 `system_id` 允许多把令牌并存（轮转期新旧并行）；吊销 = 删行或 `enabled=false`，
  即时生效（认证每请求按哈希查库）。
- 发放、吊销走系统管理页面，权限位独立于个人「API 密钥」页（系统级凭据仅管理员可见）；
  **发放与吊销动作写系统管理操作日志**（记录操作人、system_id、动作，不记录令牌值）。
- `system_id` 与 NATS KV `openapi_registry` 条目名是两个正交概念（调用方凭据 vs 被代理服务），
  不合并存储；ITSM 这类双重身份的系统建议两处同名以便审计串联。

### 系统 Token：主体传入与校验（顺序固定，任一步失败即终止）

调用方以请求头传入业务主体（非认证身份）：

- `X-Bklite-Acting-User: <user>@<domain>`（值格式同已冻结的 `X-BK-User`；username 合法字符
  含 `@`，解析一律按 `rsplit("@", 1)` 取最后一个 `@` 分割）
- `X-Bklite-Acting-Team: <十进制组织 id>`

网关校验五步：

1. 令牌哈希命中、系统 `enabled`、未过期 → 否则 `401 AUTH_INVALID`，message 固定含
   `invalid system token`；
2. 两个头齐全且格式合法 → 否则 `401 AUTH_INVALID`，message 固定含
   `acting headers required`（**不存在任何回落到系统假用户的路径**）；
3. 用户存在且可用（`base.User.is_active` 且 `system_mgmt.User` 未禁用，与个人令牌路径同款
   检查）→ 否则 `401 AUTH_INVALID`，message 固定含 `acting user not found or disabled`；
4. 组织成员校验：传入组织必须是该用户的**直属组织**（`system_mgmt.User.group_list` 精确
   交集，无祖先/子孙级联，口径同 design.md 3.3.2「锚点必须是直属组织」；复用
   `APISecretAuthBackend._get_user_all_roles` 中 `requested_group_ids & system_group_ids`
   逻辑）→ 否则 `403 TEAM_OUT_OF_SCOPE`。用户只属父组织而传子组织 id 同样 403——这与
   个人令牌路径「交集为空后静默退化到仅个人角色」是**有意差异**（系统对系统集成要求显式失败，
   不接受静默降权）；ITSM 侧注意：工单挂子组织而发起人只属父组织时调用必失败，需在集成
   规范中写明。
5. 以「该用户 × 该组织」跑既有权限推导（`_populate_user_permissions`，复用其缓存与
   `permission_version` 围栏），得到**现场权限**，不再与钥匙 Scope 求交。产出
   `CallerIdentity(user=<传入用户>, team_ids=[<传入组织>], credential_type="system_token",
   permission=<现场权限>, is_superuser=<该用户是否超管>, caller_system=<system_id>,
   token_scope=<钥匙 Scope>)`。

**错误传播协议（接缝改造）**：现有 `authenticate_request` 唯一失败通道 `AuthenticationFailed`
在 views 层被一律映射为 `401 AUTH_INVALID`，第 4 步的 403 无法穿出。认证层异常须携带错误码
（扩展 `AuthenticationFailed` 增加 `code` 属性或新增异常类型），views 层按码映射状态；
message 文案上表已给出稳定可判别子串，供 ITSM 侧编程排障（认证五步仍复用既有枚举；名单失败
additive 为 `SCOPE_DENIED`。message 不属冻结契约但承诺子串稳定）。

**超管口径**：不再因为钥匙有 Scope 把 `is_superuser` 强制打成假。超管在人的权限层仍直通
`_check_permission`。不在钥匙名单内的路由，人即使是超管也 `403 SCOPE_DENIED`。
权限缓存键为 `username:domain:version:team`，缓存值必须恒为**原始权限**，禁止把钥匙名单
写回缓存。

**用户枚举面（已论证接受）**：持有效系统 Token 者可经 401/403 差异区分「用户不存在」
「非组织成员」「成员但无权限」。接受理由：系统 Token 仅由管理员发给受管第三方系统，且
ITSM 需要区分这些错误做流程提示（发起人离职 / 组织不符 / 权限不足的用户可见文案不同）；
边界：无令牌或令牌无效时探测不可行，枚举面不对匿名调用方开放。此取舍不适用于 404
存在性语义（冻结第 6 条），后者不变。

### 系统 Token：鉴权与注入

内部调用链 ③认人 → ④查路由 / 名单 / 人的权限位 / schema → ⑤注入 → ⑥调函数。

- 名单检查发生在 `dispatch`（注册表已命中 endpoint 之后），**不要**塞进 `authenticate_request`。
  JWT 跳过名单。`mode=all` 跳过名单。`mode=allowlist` 必须命中
  `"{METHOD} {endpoint.path}"`，否则 `403 SCOPE_DENIED`（`endpoint not in token scope`）。
- 名单通过后再做原来的 `_check_permission`（required ∩ 人的 granted；超管直通）。
  端点未声明 `permission` 时走网关默认：不做菜单权限校验，名单通过即继续（不补权限位，
  也不再因「带 Scope」对无 permission 端点 fail-closed）。
- 身份注入零改动：`team_list` / `team_list_with_user` / `user_info` 按现有协议注入，
  `user_info.user` 即传入用户，业务创建人自动落真实用户。
- `inject='user_info'` 锚点式端点：锚点强制取传入组织（同个人令牌「锚点强制取绑定组织」的
  既有收窄逻辑，扩展 credential_type 判断即可），客户端 `team` 参数被覆盖。
- forward-auth 路径（`/_auth`，外部服务代理）：**本期对系统 Token 返回 `403 ROLE_REQUIRED`**，
  在名单与 `required_roles` 评估之前由凭据类型闸门拒绝。系统钥匙勾选里可以出现外部服务
  （与文档同源），运行时仍被该闸门挡住；不构成对冻结第 13 条的收紧。个人钥匙：`mode=all`
  或名单含 `EXTERNAL {service}` 后再走 `required_roles`；未勾中该服务 → `403 SCOPE_DENIED`。
- `_me`、`_docs` 不进勾选、不做名单检查，认证通过即开放。`_auth` 本身也不作为可勾选项
  （它是转发回调，不是文档目录里的接口）。
- **外部服务路由透传收口**：`X-Bklite-Acting-*` 头须加入外部服务注入中间件的清除清单
  （与 `Authorization` 清除同点），防止上游外部服务误消费未经其校验的主体头；
  内部端点路由不清除（server 认证分支消费）。

### `_me` 内省端点（冻结契约 additive 扩展）

- 系统 Token 调 `_me` 同样走五步校验：缺 acting 头或用户/成员校验失败时与业务调用同语义
  失败（401/403），**不存在**「仅凭令牌返回系统自身信息」的旁路。
- 校验通过后响应：`user` / `domain` / `groups` 为 acting 主体口径（单组织），
  `credential_type` 取新枚举值 `system_token`，新增字段 `caller_system=<system_id>`
  （additive；其余凭据类型不返回或为 null），`roles` 为 acting 用户在该组织的角色。
- 符合 `_me` 字段级 additive-only 冻结规则：只增枚举值与新字段，不改既有字段。

### 系统 Token：审计与限流口径

- 访问日志稳定模板字段为 `user domain credential token_id token_name team caller
  method path status duration_ms size request_sha256`。`token_id` / `token_name` 为命中的
  密钥行（空名称与 JWT / 认证失败为 `-`）；`caller` 仅系统 Token 为 `system_id`，其余为
  `-`。惰性参数；名称只记转义/截断后的日志副本；不记录令牌明文、哈希或头原值以外的 payload。
- `X-On-Behalf-Of` 既有语义不变（api_token 场景回显、仅审计、标注自报）；系统 Token 场景
  该头被忽略——主体已由 `X-Bklite-Acting-*` 经校验承载，不需要自报通道。
- 限流键口径登记（限流机制本身未实现，属既有已知边界）：系统 Token 场景的凭据主体为
  `system_id`（按系统分桶，防单一集成方耗尽配额），非 acting user。

### 个人 Token：补齐

- `UserAPISecret` 去掉 `unique_together(username, domain, team)`，同一用户同一组织允许多把；
  迁移只删约束，存量行不动。
- 加列：`name`（用途备注）、`expires_at`（可空；空 = 不过期，存量行为不变）、`scope`
  （JSON；存量空 / 旧权限位迁成 `mode=all`，见上节）。新建与更新必须显式二选一，与系统钥匙相同。
- **过期与吊销校验下沉到 `UserAPISecret.find_by_api_secret` 模型层咽喉**：过期行在查表层
  即不可命中，从而覆盖全部认证入口——除 `APISecretAuthBackend` 外，opspilot 存在两条
  **直查该模型**的认证路径（`opspilot/views/chat_flow.py` 的 OpenAI 兼容令牌校验、
  `opspilot/services/skill_channel_chat_service.py` 的嵌入式渠道 `Api-Authorization`），
  且 `caller_identity.py` 把 `UserAPISecret` 实例直接视为已校验身份；校验只放认证后端
  会给这些路径留永久有效的绕过口。
- **Scope 的约束边界**：名单只在网关 invoke / 个人钥匙的 `_auth` 生效；opspilot 渠道等
  非网关入口不消费 Scope。此边界写入密钥管理页文案与 onboarding 文档。过期与吊销则全局生效
  （查表层）。
- 过期令牌认证返回 `401 AUTH_INVALID`；吊销按行删，即时生效。
- 请求中的 `X-Bklite-Acting-*` 头对个人令牌与 JWT 一律忽略（不参与鉴权、不进审计主体），
  身份只来自令牌。
- 系统管理「API 密钥」页：密钥列表 + 新建（名称必填且同组织唯一 / 过期档位 / Scope 二选一）+
  按把吊销；列表 / 详情能区分「全部」与具体接口；改 Scope 立即生效、不换发明文。
  创建弹窗顶部「全部」；未选则按服务勾内部接口与外部服务前缀；未选全部且零条不能提交。

### 集成规范（写入文档，不做代码强制）

- 禁止把超管或员工个人 Token 配给 ITSM worker 等系统集成；异步节点一律使用系统 Token 并
  传入工单发起人与组织。
- ITSM 侧需处理 401/403：发起人离职、被禁用或移出组织时调用会被拒绝，这是期望行为（身份
  不再漂移），需在流程侧提示而非静默重试；按本文固定 message 子串区分场景。
- 原「服务账号 API 令牌 + `X-On-Behalf-Of` 自报审计」机制标注 deprecated：共存期行为不变
  （api_token 场景网关继续回显该头），存量集成迁移到系统 Token 后再议下线；同一集成方
  不得混用两种机制调用同一业务流。

## 明确不做

- 不做「只绑组织、没有主语」的万能钥匙。
- 不信任客户端自报身份（含既有 `X-On-Behalf-Of`）而免除存在性与组织成员校验。
- 不做系统级组织白名单（连预留字段也不加；有真实需求时加列成本很低，符合仓库
  「拒绝预防性过度设计」约束）。
- 不改 `X-On-Behalf-Of` 已冻结语义，不动既有 64hex / JWT 判别分支。
- 本期不开放系统 Token 经 forward-auth 调用外部服务。
- 不做存量个人令牌强制过期 / 强制换发（过渡策略另行产品决策）。
- Scope 不下探非网关入口（opspilot 渠道等按其自身鉴权模型，见上文边界声明）。
- 不为未声明 `permission` 的内部暴露接口补权限位；维持网关默认（无权限位则不查菜单）。
- 不把外部服务展开成对方的单条 API；勾选与转发都停在 service 前缀。

## 接缝

- 认证函数：`bksys_` 前缀判别 + 系统 Token 五步认人（第 5 步只推导现场权限，不再 ∩ Scope）；
  身份对象携带钥匙 Scope 供后续名单检查；认证异常携带错误码。
- invoke 分发器：命中 endpoint 后先查钥匙名单，再按人的 `permission` / `permission_app`
  做原来的权限判定，再 schema；注入与本地调用不变。
- `_auth`：系统 Token 仍先于名单 / `required_roles` 拒绝；个人钥匙按 `EXTERNAL {service}`
  或 `mode=all` 查名单后再走 `required_roles`。
- `_me` / `_docs`：认证通过即开放，不查名单。
- 系统凭据与个人密钥的写接口：Scope JSON 形状校验；名称必填且唯一。
- 存量 `scope` 列：空 / 旧权限位 JSON 迁成 `mode=all`。
- 管理页：权限树改为文档同源的接口 / 服务勾选；「全部」与名单二选一。
- 测试 helper `create_system_tenant`：默认 Scope 改为 `mode=all` 或显式 allowlist。
- 文档（实现后同步）：onboarding、capability 第 6 章已知边界、接口文档页认证说明。

## 验证

对应需求验收四条 + 安全红线：

- 个人 Token 调 CMDB：创建人、组织、权限均来自令牌；请求体/请求头携带任何身份传入字段
  （含 `X-Bklite-Acting-*`）不改变主体。
- **存量令牌回归**：空过期 + 迁成 `mode=all` 的个人令牌，人的权限层与迁前空 scope 一致
  （含未声明 permission 的端点可调、超管仍直通、`_me` 既有字段不变）。
- 系统 Token + 张三 + 组织：`user_info` 注入与写归属为张三；名单外的路由即使张三本人拥有
  权限位也 `403 SCOPE_DENIED`；名单内但张三无权限位的声明-permission 端点 `403 PERM_MISSING`。
- 张三不属于传入组织 → `403 TEAM_OUT_OF_SCOPE`（含「只属父组织传子组织」案例）；不传
  用户/组织头、用户不存在、用户被禁用 → `401 AUTH_INVALID` 且 message 含对应稳定子串；
  断言响应中无任何系统假用户回落。
- 超管张三经系统 Token：名单内端点可用（超管在权限位层直通）；名单外 `403 SCOPE_DENIED`；缓存快照里的
  `is_superuser: true` 不得被钥匙强制打假。
- **缓存不污染**：系统 Token 调用后，同键权限缓存值仍为原始权限；随后同一用户的个人令牌
  调用权限不受影响。
- 未声明 `permission` 的内部端点：在名单内（或 `mode=all`）时按网关默认放行；不在名单则 `403 SCOPE_DENIED`。
- 系统 Token 过期 / `enabled=false` / 删行 → `401 AUTH_INVALID`，即时生效。
- forward-auth：系统 Token 调外部服务路径 → `403 ROLE_REQUIRED`（在名单与 `required_roles`
  评估前）；个人 `mode=all` 或名单含该服务时再走 `required_roles`；`required_roles: []` 对
  JWT 放行的既有锁定单测不变。
- 外部服务路由：`X-Bklite-Acting-*` 不透传上游。
- `_me` / `_docs`：只受认证约束，不受钥匙名单约束。
- 个人 Token：同一用户同组织建两把，各自可用；吊销其一另一把不受影响；过期令牌经**网关**
  与 **opspilot 直查路径**均不可用；`allowlist` 个人令牌只放行名单内路由。
- 写接口：空 Scope / 空 allowlist / 旧权限位 JSON 创建或更新均 400；`mode=all` 与非空
  allowlist 可保存；PATCH Scope 不换发明文。
- 双租户测试：系统 Token 场景以两个组织的目标用户分别调用，断言读隔离与写归属，并登记
  覆盖表。
- 审计：访问日志含 `caller=<system_id>`，模板与惰性参数有行为回归测试；日志不含令牌值与头
  原值以外的 payload；系统 Token 发放/吊销产生操作日志。
- 权限缓存：改张三角色后（`permission_version` 递增）系统 Token 的人的权限在缓存围栏语义内
  更新，与个人令牌路径一致。
- 验收第 4 条（跨仓库验收信号，不在本仓库 CI）：ITSM 切换系统 Token 后，网关审计日志
  `caller=itsm` 且业务创建人为工单发起人；`itsm_openapi` 账号可被禁用而集成不受影响。
