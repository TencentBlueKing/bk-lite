# 系统管理 Teams 集成产品决策记忆

- 最近更新：2026-09-09
- 当前规格：`specs/changes/teams-im-notification-provider/spec.md`

## 产品定位

在系统管理集成中心新增 **BK-Lite 企业版** Microsoft Teams provider，复用现有
`IntegrationInstance` 与 IM 通知渠道，而不是平移 WeOps IM 插件或 CMSI 通道。
对象是 **Microsoft 365 工作租户中的企业 Teams**（Entra 工作/学校账号），不含个人免费 Teams。
社区版 builtin 不含该 provider。

## 已确认范围

- 首期只交付 `im_notification`：集成实例、连接测试、外部用户同步映射、按已映射用户发送。
- 发送形态对齐 WeOps 通知：一个委托工作账号对多个收件人分别建立 1:1 私聊（多次一对一，不是群发）。
- 登录认证、用户同步、`im_group` 拉群、Bot、Tab SSO 均不在首期。

## 已确认设计决策

- 「在 Teams 里打开 BK-Lite」属于单点登录 / Tab 免登，与 `login_auth` 授权码回调不是同一条链路；首期不做，也不因通知去上架 Teams 应用包。
- 首期通知走 Graph + 委托账号 ROPC（与 WeOps `send_teams_weops` 同类），BK-Lite 只需出站访问 Entra / Graph；不要求 Bot Messaging endpoint。
- 收件人必须是本租户工作账户（Graph 用户对象 id）。个人 Teams 账号、未入目录的外部联邦用户不在首期接收范围内。
- 外部稳定身份与接收标识使用 Graph 用户 `id`；邮箱可用于匹配，不作为主键。
- 仅声明 `im_notification` capability（形态对齐微信「只做 login_auth」的单能力 pack），不预留未实现的登录/同步/建群开关。
- Entra 应用（租户 ID、客户端 ID、客户端密钥）放在基础连接；委托工作账号 UPN 与密码放在 IM 应用通知连接配置。应用令牌仍用于拉用户和建 chat，委托账号只用于发消息。

## 明确后置

- Teams 客户端内嵌控制台、Tab SSO、从 Teams 应用入口免登。
- Azure Bot、应用包上架、公网 Messaging endpoint。
- `login_auth`、`user_sync`、`im_group`。
- Adaptive Card、Tab 深链、中国区 21Vianet。
- 个人免费 Teams、来宾/外部访问用户作为通知对象。

## 仍待确认

- 无（首期能力边界已确认）。连接测试是否必须用 ROPC 真换用户令牌（而不只测 client_credentials）可在实现规格里写死为必须，不必再开产品选择题。

## 已替代决策

- 2026-08-27 曾把登录页 Entra 授权码列为已确认首期范围；2026-09-08 收窄为仅通知渠道，登录整段后置。
- 通知通道曾在 Bot 与 ROPC 之间待确认；2026-09-08 按实施成本与 WeOps 对照，首期定为 ROPC + 多次 1:1。

## 决策来源

- 2026-08-27：用户确认 Teams 内打开 BK-Lite 不在范围内。
- 2026-09-02：对照 WeOps 后确认 ROPC 比 Bot 更适合内网出站；Bot 需入站入口。
- 2026-09-08：用户确认要做 Teams provider，首期只做通知渠道，且对象为企业版 Teams。
- 2026-09-09：用户确认只把委托 UPN/密码挪到 IM 应用通知 Tab，Entra 三项留在基础连接。
