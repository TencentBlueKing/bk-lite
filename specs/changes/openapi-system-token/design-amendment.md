# design.md 修订稿

> 目标文件：`specs/changes/openapi-unified-gateway/design.md`。

## v2.4（Scope = 网关接口名单 / 全部）

产品对齐见同目录 `spec.md`。本版改写 v2.3 已合入、尚未对外发布的鉴权口径：钥匙 Scope
从权限位求交改为接口名单。冻结清单第 18 条必须改写（v2.3 尚未发货，不构成已发布契约回滚）。

### 3.2.2 凭据矩阵两行

| 调用方 | 凭据 | 授权注入 |
| --- | --- | --- |
| 第三方系统（ITSM 异步节点等） | **系统 Token**（`bksys_` 前缀） | 注入经校验的业务主体；人的权限 = 该用户在该组织的现场权限；钥匙 Scope 只限制能碰哪些路由；超管在人的权限层仍直通，不在名单则仍 403 |
| 人（脚本 / 调试） | 个人 API 令牌 | 注入令牌绑定的用户与组织；Scope 语义与系统 Token 相同 |

配套约束 6 改为：不再因为钥匙有 Scope 把 `is_superuser` 打成假；名单外路由对人（含超管）一律
`403 SCOPE_DENIED`；人的权限位不足仍为 `403 PERM_MISSING`；权限缓存仍只存原始权限，禁止写回钥匙名单。

### 3.2.3 凭据发放

Scope 词表改为文档同源的网关路由：内部 `METHOD service/sub_path`，外部 `EXTERNAL {service}`
（与前缀转发同粒度）。形状为 `{mode: all}` 或 `{mode: allowlist, endpoints: [...]}`。
新建必须显式二选一。存量空 / 旧权限位 JSON 迁成 `mode=all`。

### 3.2.4 第五步

第 5 步只推导现场权限，不再 ∩ 钥匙。名单检查下移到 invoke 分发器（已知 endpoint 之后）
以及个人钥匙的 `_auth`（`EXTERNAL {service}`）。系统 Token 经 forward-auth 仍先于名单 /
`required_roles` 返回 `403 ROLE_REQUIRED`。`_me` / `_docs` 不进名单。

### 3.7 映射表该行

「端点不在钥匙名单内」→ `SCOPE_DENIED` 403；「人的权限位不满足已声明 permission」→ `PERM_MISSING` 403。
删除「未声明 permission 对带 Scope 凭据 fail-closed」。未声明 permission 走网关默认：
名单通过后不查菜单权限。

### 冻结清单第 18 条

改为：「有效权限分层 = 钥匙名单（或全部）决定能否碰该路由，人的现场权限决定
`_check_permission`；超管在人的权限层直通；不在名单则超管也 403；名单不落权限缓存」。
五步认人顺序与失败子串不变。

---

# v2.2 → v2.3（已过评审，已合入）

> 评审记录：2026-09-16 安全/架构与契约/产品双视角评审，结论「修改后合入」；本版已吸收全部
> 评审意见，随评审通过合入正文并升版 v2.3。
>
> additive 声明的准确范围：**冻结清单（第 8 章）既有条目无一改动或收紧**；第 1.3 非目标与
> 1.4 设计约束属 v1 落地时的范围声明（非冻结契约），本修订对其显式改写（见第〇节），
> 使正文不自相矛盾。

## 〇、1.3 非目标 / 1.4 设计约束（范围声明更新）

- 1.3 非目标中「API 令牌的过期、轮转与作用域（scope）机制」条目追加标注：
  > v2.3 起由 `specs/changes/openapi-system-token` 变更引入，不再是非目标。
- 1.4 设计约束 2「不变更数据库表结构：全程无 migration」追加标注：
  > 该约束描述 v1 网关自身落地；v2.3 系统 Token 变更引入 `SystemAPIToken` 新表与
  > `UserAPISecret` 加列/删约束迁移，网关核心（注册表存 KV、不落库）不变。

## 一、3.2.1 凭据判别（追加一种已注册前缀）

在双凭据判别规则之后追加：

> 已注册前缀 `bksys_`：`bksys_` + 64 字符十六进制 → **系统 Token**，走系统凭据认证
> （`SystemAPIToken` 哈希查表 + 业务主体头校验，见 3.2.4）。本条目是「已注册前缀 > 形态」
> 演进规则的首次行使，且前缀判别必须**先于**形态匹配执行（`JWT_RE` 字符集含下划线，
> 畸形串 `bksys_a.b.c` 可匹配 JWT 形态）；无前缀形态的判别语义不变。

## 二、3.2.2 调用场景与凭据矩阵（追加两行）

| 调用方 | 凭据 | 授权注入 |
| --- | --- | --- |
| 第三方系统（ITSM 异步节点等） | **系统 Token**（`bksys_` 前缀） | 注入经校验的业务主体：`X-Bklite-Acting-User` / `X-Bklite-Acting-Team` 传入的用户与组织，有效权限 = 该用户在该组织的权限 ∩ 令牌 scope；`is_superuser` 强制为假 |
| 人（脚本 / 调试） | 个人 API 令牌（64hex，补过期 / scope / 多把） | 语义不变：注入令牌绑定的用户与组织；非空 scope 时同样取交集 |

配套约束追加：

5. 系统 Token 的业务主体头 `X-Bklite-Acting-*` **不是认证身份**而是受校验的业务参数：
   网关必须依次校验令牌有效、头齐全、用户存在且可用、用户属于该组织（**直属组织精确
   交集，无祖先/子孙级联**，口径同 3.3.2「锚点必须是直属组织」；用户只属父组织而传子
   组织 id 即拒绝），全部通过后才以该用户为主语构造认证上下文；任何一步失败即按 3.7
   映射拒绝，**不存在回落到系统自身假用户的路径**。该头对个人令牌与 JWT 一律忽略；
   `X-Bklite-Acting-User` 值按 `rsplit("@", 1)` 解析（username 合法字符含 `@`）。
6. 传入用户为超管时，其「在该组织的权限」取全集，故有效权限 = scope 本身；
   `is_superuser` 仍强制为假（含权限缓存读出的快照），超管身份不带来任何 scope 外能力。
   有效权限交集只在认证上下文构造期内存中计算，**不得写回权限缓存**（缓存键
   `username:domain:version:team` 与个人令牌共用，写回即静默削权同一用户的个人令牌）。
7. ITSM 异步节点场景由「服务账号 API 令牌 + `X-On-Behalf-Of` 自报审计」（3.2.2 第 4 条）
   **升级为系统 Token + 受校验主体**；原机制不删除、语义不变，仅在集成规范中标注为
   deprecated，存量集成迁移完成后再议下线。
8. 限流键口径（限流机制仍属已知边界未实现）：系统 Token 的凭据主体为 `system_id`
   （按系统分桶），非 acting user。
9. 已论证的用户枚举面：持有效系统 Token 者可经 401/403 差异区分用户存在性与组织成员
   关系。接受理由：系统 Token 仅由管理员发给受管系统，且集成方需区分这些错误做流程
   提示；匿名调用方无此探测面。404 存在性语义（冻结第 6 条）不变。

## 三、3.2.3 凭据发放（追加一段）

> 系统 Token 由系统管理「系统凭据」页发放（独立权限位，仅管理员）：登记 `system_id`
> （命名规则同 service 段）与 scope（词表复用 `permission_app` → 权限名集合，与
> `@openapi_expose` 的 `permission` / `permission_app` 同一命名空间），令牌为
> `bksys_` + 64hex，仅生成时展示一次，库存 SHA-256 哈希，记录 `created_by`；同一
> `system_id` 允许多把并存以支持轮转，吊销即时生效；发放与吊销写系统管理操作日志。
>
> 个人令牌解除「一用户一组织一把」限制，支持多把并存，新增 `name` / `expires_at` /
> `scope`（均可空，空值行为与存量一致）。过期与吊销校验位于 `find_by_api_secret`
> 模型层查表咽喉，覆盖网关之外的既有直查路径（opspilot OpenAI 兼容令牌、嵌入式渠道）；
> scope 仅在网关 invoke 路径生效，非网关入口按其自身鉴权模型（边界写入密钥页文案）。

## 四、3.3 身份注入（追加一条不变式说明）

> 系统 Token 路径下，「身份只能来自服务端认证结果」不变式的口径为：`X-Bklite-Acting-*`
> 头是**主体选择输入**，经 3.2.4 五步校验后成为服务端认证结果的一部分；下游注入
> （`team_list` / `team_list_with_user` / `user_info`）与审计使用的均为校验后的主体，
> 协议形状与字段名不变。`inject='user_info'` 的锚点收窄规则从「API 令牌 → 绑定组织」
> 扩展为「API 令牌 → 绑定组织；系统 Token → 传入组织」。

## 五、3.7 错误码（不新增枚举，登记映射与传播协议）

复用既有枚举，追加映射说明：

| 场景 | code / 状态码 | message 稳定子串 |
| --- | --- | --- |
| 系统 Token 无效、过期、禁用 | `AUTH_INVALID` 401 | `invalid system token` |
| 主体头缺失或格式非法 | `AUTH_INVALID` 401 | `acting headers required` |
| 传入用户不存在或被禁用 | `AUTH_INVALID` 401 | `acting user not found or disabled` |
| 传入用户不属于传入组织（直属口径） | `TEAM_OUT_OF_SCOPE` 403 | — |
| 端点不在钥匙名单内 | `SCOPE_DENIED` 403 | `endpoint not in token scope` |
| 人的权限位不满足已声明 `permission` | `PERM_MISSING` 403 | `permission denied` |
| 系统 Token 经 forward-auth 调外部服务（本期不放行，先于 `required_roles` 评估） | `ROLE_REQUIRED` 403 | — |

> 传播协议：认证层失败异常携带错误码（现有实现将 `AuthenticationFailed` 一律映射
> `AUTH_INVALID` 401，须扩展），views 层按码映射状态；message 不属冻结契约，但上表
> 子串承诺稳定，供集成方编程排障。
>
> 与冻结第 13 条的关系：「`required_roles: []` = 放行任意已认证身份」语义定义于既有
> 凭据类型（api_token / JWT）；系统 Token 在 `required_roles` 评估之前即被凭据类型闸门
> 拒绝，不构成对该条的收紧，锁定该语义的既有单测不得反转。

## 六、3.6 `_me`（additive 扩展）

> 系统 Token 调 `_me` 同样走五步校验，无「仅凭令牌返回系统自身信息」旁路；校验通过后
> `user` / `domain` / `groups` 为 acting 主体口径，`credential_type` 新增枚举值
> `system_token`，响应新增字段 `caller_system`（additive；其余凭据类型不返回或为 null）。
> 既有字段结构不变，符合字段级 additive-only 规则。

## 七、第 8 章冻结清单（追加三条，编号 17–19；既有 1–16 条不动）

17. 系统 Token 凭据前缀 `bksys_`（前缀 + 64hex 形态，判别先于形态匹配）；业务主体头
    `X-Bklite-Acting-User`（`user@domain`，同 `X-BK-User` 值格式，`rsplit("@", 1)` 解析）
    与 `X-Bklite-Acting-Team`（十进制组织 id）的名称、格式与「仅系统 Token 场景消费、
    其余凭据类型忽略」的语义。**该头不属于 `X-BK-` 保留前缀族，禁止被任何前缀清除规则
    波及**（内部路由不清除；外部服务路由由注入中间件清除后转发，防上游误消费）。
18. 系统 Token 校验顺序与失败语义（3.2.4 五步 → 3.7 映射表，含 message 稳定子串）；
    鉴权分层为「钥匙名单（或全部）决定能否碰该路由，人的现场权限决定 `_check_permission`；
    超管在人的权限层直通；不在名单则超管也 `403 SCOPE_DENIED`；名单不落权限缓存」。
19. 审计访问日志 `caller=<system_id>` 字段（非系统 Token 场景为 `-`）；`_me` 的
    `credential_type=system_token` 枚举值与 `caller_system` 字段。

## 八、能力规范同步（实现后执行，不在本修订稿内）

`specs/capabilities/openapi-gateway.md` 第 6 章已知边界两行待实现落地后更新：

- 「API 令牌永不过期、无 scope、无轮转；权限等于生成账号的全部权限」→
  「个人令牌支持可选过期与 scope、多把并存；存量令牌（空过期 / 空 scope）行为不变」。
- 「接口级授权……超管身份均直接绕过」→ 补注「系统 Token 例外：超管不直通，受 scope
  交集约束」。
