# 集成中心 Teams 通知渠道

Status: implemented

## Completion Evidence

- 2026-09-08：`teams` pack 仅企业 overlay；社区 builtin 不含该 key。adapter 对 `requests` 打桩覆盖分页/`nextLink`、超页失败、Guest 过滤、双收件人 1:1 发送、第二人失败 `partial_success`、ROPC 失败码与摘要、应用令牌不能单独通过能力测试、代理与 URL 覆盖。
- 2026-09-09：委托 `username`/`password` 从基础连接挪到 `im_notification.connection_template`；基础连接只保留 Entra 应用与代理。manifest 断言与「无委托账号时能力测试失败」覆盖该分组。
- 定向 pytest：社区 `test_provider_loader.py` / `test_im_notification_manifest.py` / `test_provider_loader_base_connection.py`；企业 `apps/system_mgmt/enterprise/tests/test_teams_*.py`。
- 前端：集成中心/登录认证/用户同步直接用 provider key 作为 iconfont 名，不再维护图标解析 helper；pack 中英文文案由企业 yaml 路径的 presentation 契约覆盖。

## Problem Statement

客户在企业 Microsoft 365 / Teams 里办公，需要把 BK-Lite 的告警与系统通知发到员工的 Teams 私聊。集成中心已有飞书、企微通知渠道，但没有 Teams。WeOps 虽能用委托账号发 1:1，那是另一套插件和 CMSI，不能原样搬进 BK-Lite。个人免费 Teams 与工作租户不通，本需求只覆盖企业工作账号。

## Solution

管理员在集成中心创建一个内置 Teams 实例，只启用 IM 通知能力。基础连接填写 Entra 应用凭证以及可选出站代理；IM 通知能力填写专用委托工作账号（可 ROPC、通常需排除 MFA）。连接测试分两步：基础连接验证应用令牌，能力测试再验证委托用户令牌。管理员再在 IM 通知渠道里选该实例、同步映射、向已映射用户发文本。发送时由委托账号与每个收件人各建一条 1:1 私聊并逐条投递，与现有通知渠道的部分成功语义一致。平台只出站访问 Entra 和 Graph，不要求 Bot、应用包或公网入站。

## User Stories

1. As a 系统管理员, I want 在集成中心创建仅含通知能力的 Teams 实例，基础连接保存 Entra 应用、IM 通知保存委托账号, so that 不必上架 Teams 应用或暴露公网 Bot 入口也能对接企业租户。
2. As a 系统管理员, I want 基础连接测试失败时能区分缺配置、网络/代理、应用认证失败和委托账号 MFA/ROPC 被拒, so that 知道是改应用权限还是给委托账号开例外，而不是看到一句「Teams 失败」。
3. As a 系统管理员, I want 在 IM 通知渠道选择已就绪的 Teams 实例并同步外部用户, so that 能按邮箱或 Graph 用户 id 把平台用户映射到本租户工作账号。
4. As a 系统管理员, I want 向一个或多个已映射用户发送标题加正文的文本通知, so that 每人在 Teams 里收到来自委托账号的一条私聊，而不是一个群。
5. As a 操作人员, I want 部分收件人失败时仍看到成功数和失败明细, so that 未映射或 Graph 拒绝的用户不会被邮箱/手机号兜底发出去。
6. As a 安全与合规相关的实现约束受众, I want 日志和接口回显不出现客户端密钥、用户密码、access token 或带凭据的 URL, so that 生产日志可开给运维看。

## Implementation Decisions

- 新增 **BK-Lite 企业版** provider，键为 `teams`。只声明 `im_notification` 与基础连接，不声明 `login_auth`、`user_sync`、`im_group`。包放在 `enterprise/server/apps/system_mgmt/enterprise/providers/builtin/teams/`，由社区 loader 在企业 overlay 存在时额外扫描；社区 `providers/builtin/` 不含 `teams`。pack 必须满足现有必填文件（含厂商 client 与 base_connection）。
- 对象仅限全球云 Microsoft 365 工作租户。默认 token 主机为 `login.microsoftonline.com`，Graph 为 `graph.microsoft.com`。允许管理员覆盖完整 HTTP(S) URL（与企微私有化地址同一模式），但不为一等中国区 21Vianet 做探测或文案。个人 Microsoft 账号、来宾、仅外部访问/联邦存在的用户不在 `list_external_users` 与发送范围内。
- 基础连接字段：`tenant_id`、`client_id`、`client_secret`（密钥，加密存储、回显脱敏）、可选 `proxy_url`（仅 HTTP/HTTPS，禁止 SOCKS）。IM 通知能力连接字段：委托 `username`（UPN）、`password`（密钥）。变更这些字段时将 `im_notification` 重置为待验证。能力级另保留可覆盖的 Graph/token URL，默认官方地址见下表；未填则用常量，不得把 WeOps 插件里的几十个 URL 做成必填项。
- 令牌：应用令牌使用 `client_credentials`，scope 为 Graph `.default`。委托令牌使用 `grant_type=password`（ROPC），同一 client 与 secret。应用令牌可按不可逆缓存键做进程内短缓存，临近过期或认证失败刷新。用户令牌缓存不得以明文密码入键。缓存与日志不得含 token、secret、密码。
- `list_external_users`：应用令牌分页拉取 Graph 用户（跟随 `@odata.nextLink`，必须有页数上限，超限失败而不是截断当成功）。只保留有 `id` 且可视为本租户成员的用户（排除 Guest）。对外字段至少包含 `id`、`name`（displayName）、`mail`、`userPrincipalName`、`mobile`。无邮箱的用户仍可出现在列表中，匹配是否成功交给渠道配置。
- 通知业务模板：`identity_fields` 与 `receivable_fields` 仅为 `id`；`matchable_fields` 为 `id`、`mail`、`userPrincipalName`；默认外部匹配字段 `mail`，默认接收字段 `id`。映射、同步 run、定时任务、先同步再发送，全部走现有 IM 通知服务，不新建 Teams 专用表。
- `send_message`：对每个 `receive_ids` 项（Graph 用户 id）独立处理。用应用令牌创建或取得委托用户与该 id 的 `oneOnOne` chat，再用委托用户令牌向该 chat 发一条文本消息。标题与正文按现有通知服务合成纯文本（与企微/飞书相同拼接），不做 Adaptive Card、Tab 深链或 HTML 卡片。多人即多次 1:1。单人失败记入 `failures` 并继续；有成功有失败则 `partial_success`。未映射用户由通知服务拦截，adapter 不按邮箱/手机号改投。
- 连接测试：基础连接必须成功取得应用令牌。能力测试必须再成功取得委托用户令牌；只测应用令牌算未就绪。ROPC 因 MFA、无密码、联邦或 `invalid_grant` 失败时使用稳定 `provider.auth_failed`（或已有认证失败码），摘要可行动且不含 Microsoft 原始 error_description 全文、不含密码。
- 外呼 URL 只接受 HTTP/HTTPS。代理仅作用于 BK-Lite 发出的 token 与 Graph 请求。日志用稳定模板和惰性参数；一个失败只在 adapter/runtime 约定的一层打 traceback；不得记录 Authorization 头、密码、token、完整用户列表或响应正文。
- 前端：集成中心创建/详情按 manifest 自动只出现基础连接与 IM 通知 Tab（现有「有 capability_status 才出 Tab」即可）。补 provider 显示名、描述、中英文 pack 文案；图标用 provider key。不改登录页，不增加 Teams Bot 渠道类型。社区 loader 注册表断言覆盖社区四包；企业 overlay 测试断言纳入 `teams`。
- 不移植 WeOps 的 JWT 免登、Excel 导入用户管理、CMSI `send_teams_weops`、未验签解码。参考其 Graph 建 chat + ROPC 发消息的协议顺序，但错误处理、分页上限、日志与部分成功必须对齐 BK-Lite 企微/飞书通知，而不是 WeOps 循环里覆盖成功 payload 的行为。

默认官方 URL（管理员可整段覆盖）：

| 用途 | 默认 |
|---|---|
| 应用/用户令牌 | `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token` |
| 用户列表 | `https://graph.microsoft.com/v1.0/users` |
| 按 id 取用户 | `https://graph.microsoft.com/v1.0/users/{userid}` |
| 创建会话 | `https://graph.microsoft.com/v1.0/chats` |
| 发消息 | `https://graph.microsoft.com/v1.0/chats/{chat_id}/messages` |
| scope | `https://graph.microsoft.com/.default` |

`{tenant_id}`、`{userid}`、`{chat_id}` 由运行时替换，不在表单里让管理员拼路径。

## Testing Decisions

- 只测对外行为：manifest 能力集合、敏感字段、`list_external_users` payload、发送的 Graph 调用顺序与部分成功、连接测试在缺字段/应用令牌失败/ROPC MFA 类失败下的 code 与摘要、日志模板不含凭据哨兵。不测 Graph SDK 内部、不测真实 Azure。
- 最高接缝：Teams 通知 adapter（对 `requests` 打桩）+ 现有 IM 通知服务在「假 adapter 结果」上的映射/未映射/发送（若已有飞书/企微服务测试可复用同一服务用例模式，不必为 Teams 复制渠道状态机）。Manifest/loader 先验见现有 `test_provider_loader`、`test_im_notification_manifest`、企微 adapter 服务测试。
- 必须覆盖：分页 `nextLink` 收齐；超页上限失败；Guest 不进入 `external_users`；`send_message` 对两个 receive_id 创建两次 oneOnOne 并两次发消息；第二人失败时 `partial_success` 且第一人已发送；ROPC 失败时能力测试失败且不把密码写入 summary；应用令牌成功不能单独让能力测试通过；代理传入 token 与 Graph 请求；覆盖 URL 被使用而默认主机不被调用。
- 改日志须同时锁模板、独立参数、格式化结果、单一 traceback 所有权、凭据哨兵不出现，并保持原返回值与错误码。
- 前端若只加图标键和文案，用现有集成中心/文案契约测试或最小静态断言即可，不要求浏览器测真实 Microsoft。

## Out of Scope

- `login_auth`、`user_sync`、`im_group`。
- Teams Tab SSO、在 Teams 里打开 BK-Lite、应用包上架、Azure Bot、Messaging endpoint。
- Adaptive Card、深链、富文本/文件。
- 群聊或频道一次广播。
- 个人免费 Teams、来宾、外部联邦用户作为收件人。
- 中国区 21Vianet 作为一等环境（允许 URL 覆盖但不做专项验收）。
- 把 WeOps/CMSI 通道迁入本产品。
- 为 Teams 新增独立通知渠道类型或绕过 IMNotificationChannel。

## Further Notes

产品决策见 `docs/design/product-decisions/system-mgmt-teams-provider.md`。WeOps 对照仓库仅作协议参考，实现以本 spec 与现有企微/飞书通知 adapter 为模板。Entra 应用需管理员同意 Graph 委托权限（至少含创建 chat、发消息、读用户）；应用权限用于列表用户与建 chat。委托账号必须是本租户已许可 Teams 的工作用户。实现 agent 应更新企业 overlay 的 loader 扫描与内置 key 集合断言，并补中英文 pack 语言文件。社区注册表断言保持四包（ad/feishu/wechat/wecom）。
