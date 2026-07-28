# 企业微信 Provider 变更规格

## 目标

在集成中心新增内置企业微信 provider，沿用现有 provider manifest、adapter 和
IntegrationInstance 运行时模型，首期提供以下三个能力：

- 用户同步
- Web 端企业微信扫码登录
- 企业微信自建应用的单用户 IM 通知

同一个企业微信集成实例的三个能力默认共享基础连接配置，并允许将企业微信官方
接口域名替换为私有化部署地址。

## 已确认的产品决定

### 登录形态

首期只支持用户从 BK-Lite Web 登录页主动发起的企业微信扫码 OAuth：

1. BK-Lite 创建登录请求并生成带签名 `state` 的企业微信扫码授权地址。
2. 用户扫码并确认授权。
3. 企业微信携带授权 `code` 回调 BK-Lite 现有统一后端回调地址。
4. 后端使用 `code` 获取企业微信用户身份，按登录认证绑定配置匹配平台用户。
5. 前端沿用现有登录结果轮询和会话同步链路，成功后进入原 `callbackUrl`。

首期不实现以下形态：

- 从企业微信工作台点击应用进入 BK-Lite 的应用免登。
- 外部身份平台主动携带凭证跳转 BK-Lite 的通用 SSO。
- 企业微信回调后固定重定向首页。扫码登录仍应保留并校验 BK-Lite 原始
  `callbackUrl`，没有合法目标时才回到首页。

### 用户匹配与创建

- 推荐部署顺序是先执行企业微信用户同步，再启用扫码登录。
- 登录认证默认只允许匹配已经存在的平台用户，未匹配用户拒绝登录。
- 企业微信登录认证仅允许匹配已同步的平台用户；未匹配用户始终拒绝登录，
  不允许通过登录绑定的“未匹配时创建用户”策略创建账号。该策略仅适用于微信
  provider。
- 管理员仍可在系统管理的用户管理入口显式创建平台用户；这属于后台用户管理，
  不属于外部登录认证的自动创建语义。
- 企业微信 `userid` 是首期稳定的外部身份标识。用户同步、登录认证和 IM 通知应
  对该标识使用一致的归一化字段，避免混用 openid、unionid 或手机号作为主身份。

### 公共连接配置

一个企业微信 IntegrationInstance 共享以下基础配置：

- `corp_id`：企业 ID。
- `corp_secret`：自建应用 Secret，敏感字段，加密存储并掩码回显。
- `agent_id`：自建应用 AgentId。
- `access_token_url`：访问令牌地址，默认
  `https://qyapi.weixin.qq.com/cgi-bin/gettoken`，被三个能力共用。
- `proxy_url`：可选的网络代理地址，默认空，仅允许 HTTP/HTTPS，不支持 SOCKS。
  当配置时，BK-Lite 后端访问该实例的 `requests` 调用会传入该代理；
  `build_login_url` 不发 HTTP 请求因此不受影响。

三个能力不得分别重复保存 CorpId、Secret、AgentId 和访问令牌地址。能力配置只
保存该能力独有的业务接口地址，基础配置变更后沿用集成中心现有语义，将受影响能力
重置为待验证。`access_token_url` 与 `proxy_url` 变更重置全部三个能力。

私有化场景由管理员直接填写实际接口地址，adapter 不再拼接「基础 URL + 接口
路径」。每个能力独立配置需要的接口 URL，未配置时回退到对应官方默认常量。
URL 只接受 HTTP/HTTPS，日志不得记录 Secret、access token、OAuth code 或完整
含敏感查询参数的 URL。

## 能力契约

### 用户同步

企业微信用户同步沿用项目现有的同步源、同步策略、组织创建、用户创建/更新/禁用、
执行记录和定时任务语义，不另建企业微信专属同步模型。

#### 配置

- 支持选择或填写同步根部门。
- 支持是否递归包含子部门；默认包含。
- 企业微信返回的部门转换为通用 `group_list`。
- 企业微信返回的成员转换为通用 `user_list`。
- 外部成员主标识取 `userid`，并归一化为 provider 对外统一使用的用户标识字段。
- 姓名、邮箱、手机号和部门关系在企业微信授权范围内按现有字段映射机制提供。

#### 验收场景

- **WHEN** 实例凭据有效且根部门可访问
- **THEN** 连接测试成功，并能列出可选部门。

- **WHEN** 执行同步
- **THEN** adapter 拉取根部门范围内的部门和成员，返回通用同步 payload。
- **AND** 通用同步服务按项目已有语义创建或更新用户与组织。

- **WHEN** 同一成员因属于多个部门被重复返回
- **THEN** 以 `userid` 去重并保留完整部门关系。

- **WHEN** 企业微信分页返回数据
- **THEN** adapter 拉取全部页后再完成同步，不静默丢失后续页。

### Web 扫码登录

企业微信登录 adapter 接入现有 `start_login_auth -> callback -> poll status ->
session sync` 统一链路，不新增 NextAuth provider，不复用旧个人微信登录流程。

#### 配置

- 集成详情页展示现有统一后端 OAuth 回调地址，供管理员配置到企业微信应用。
- 登录绑定允许选择企业微信外部字段与平台字段的匹配关系。
- 默认外部匹配字段为企业微信 `userid`，默认未匹配处理为拒绝登录。

#### 验收场景

- **WHEN** 用户在 BK-Lite 登录页选择企业微信扫码登录
- **THEN** 后端生成使用实例 `corp_id`、`agent_id`、回调地址和签名 `state` 的扫码
  授权地址。

- **WHEN** 企业微信以合法 `code` 和 `state` 回调
- **THEN** 后端校验并消费登录请求，获取企业微信 `userid`，匹配平台用户并完成
  现有会话同步流程。
- **AND** 登录完成后回到登录发起时的合法 `callbackUrl`，缺省时进入首页。

- **WHEN** 用户不存在且绑定策略为拒绝
- **THEN** 登录失败并返回可理解的未匹配提示，不创建平台用户。

- **WHEN** `state` 无效、过期或已消费，或 `code` 无效
- **THEN** 登录失败，不能建立会话，错误信息不得泄露外部凭据。

### IM 应用通知

首期通知使用企业微信自建应用消息接口向用户发送文本消息，不等同于群机器人
Webhook，也不复用现有 `wecom_bot` 渠道。

#### 配置

- 外部用户目录来自企业微信通讯录。
- 首期接收标识只使用企业微信 `userid`。
- 平台用户与企业微信用户的映射、映射同步记录、定时同步和状态机沿用现有
  IMNotificationChannel 语义。
- 首期消息类型只支持文本；标题和正文按现有通知服务输入合成为可读文本。

#### 验收场景

- **WHEN** 同步通知用户映射
- **THEN** 系统按配置匹配平台用户，并将对应企业微信 `userid` 保存为接收标识。

- **WHEN** 向一个或多个已映射用户发送通知
- **THEN** adapter 使用共享 AgentId 和 access token 逐个发送应用文本消息。
- **AND** 返回成功数和失败明细，部分失败沿用现有 partial success 语义。

- **WHEN** 用户没有有效映射
- **THEN** 通知服务报告未映射用户，不使用手机号、邮箱或其他标识隐式兜底发送。

## 外部 API 与私有化边界

adapter 直接读取实例配置中的实际接口 URL；不再使用 `api_base_url` +
`api_path` 拼接的私有化基址模型。每个能力按需配置独立的完整接口 URL：

| 用途 | 默认官方 URL |
|---|---|
| 获取 access token | `https://qyapi.weixin.qq.com/cgi-bin/gettoken`（基础连接） |
| 扫码授权 | `https://open.work.weixin.qq.com/wwopen/sso/qrConnect`（login_auth） |
| OAuth code 换取用户身份 | `https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo`（login_auth） |
| 部门列表 | `https://qyapi.weixin.qq.com/cgi-bin/department/list`（user_sync） |
| 成员列表 | `https://qyapi.weixin.qq.com/cgi-bin/user/list`（user_sync / im_notification） |
| 发送应用消息 | `https://qyapi.weixin.qq.com/cgi-bin/message/send`（im_notification） |

私有化场景由管理员直接将上述地址替换为私有化部署的实际接口地址。Adapter 不对
私有化路径做猜测兼容；测试需证明每条外呼都尊重配置值。`build_login_url` 只
构造给浏览器打开的扫码 URL，不产生后端 HTTP 请求，因此也不受 `proxy_url`
影响。

access token 可按 `(access_token_url, corp_id, corp_secret)` 的不可逆缓存键进行
进程内缓存，并在临近过期或认证失败时刷新。缓存、异常和日志不得暴露 token
或 Secret。

## 实现切片

1. 新增企业微信 manifest、loader 注册和三类 adapter 骨架，先以 manifest/loader
   测试锁定公共配置、能力声明、敏感字段和私有化地址。
2. 实现 access token、分页通讯录和用户同步，以 adapter 单测及同步服务集成测试
   锁定 `userid` 去重、组织关系和失败语义。
3. 实现扫码 OAuth，并通过登录认证服务测试覆盖授权地址、回调、state、防重放、
   用户匹配及 callbackUrl。
4. 实现 IM 用户映射和应用文本消息发送，覆盖多接收人、未映射和部分失败。
5. 补齐集成中心中英文文案、provider 图标和登录页入口，并运行 system_mgmt
   provider、同步、登录认证、IM 通知及相关前端新鲜验证。

## 非目标

- 企业微信工作台应用免登。
- 通用外部 SSO 协议或 SSO 路由改造。
- 群机器人 Webhook、群聊通知或已有企业微信机器人渠道迁移。
- 卡片、Markdown、图片、文件等富消息。
- OAuth 回调时由企业微信 adapter 即时创建用户。
- 多套凭据分别服务三个能力。
