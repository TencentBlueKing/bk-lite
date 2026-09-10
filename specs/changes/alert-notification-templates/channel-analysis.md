# 系统管理通知渠道探索与模板方案校准

状态：探索结论已落实到第一版实现；待部署与真实渠道验收。

关联：[实施方案](./spec.md)、[测试计划](./test-plan.md)。

## 1. 结论

系统管理通知渠道是告警中心及其他业务模块共用的底层投递能力。
当前告警中心使用的 `send_msg_with_channel` 接收已生成的标题和正文，不查询通知模板、
不理解告警变量，也不要求调用方按固定业务字段组织通知内容。

因此自定义模板主要是补齐告警中心的内容生成能力，不能把告警规则、模板 ID、富化变量或
模板权限逻辑下沉到系统管理渠道，也不能给全部业务的渠道正文增加告警专属校验。

“没有业务模板限制”不等于所有发送路径都透明：当前 Adapter 有固定消息外壳、自动追加
接收人、NATS 入参约束；另一个 `dispatch_notification` 入口还有内容转义和长度限制。
这些差异必须以具体调用链区分。

## 2. 实际调用链

```text
分派/提醒/升级/恢复/未分派兜底
  → Alerts 生成 title/content
  → AlertOutbox / AlertNotificationDelivery
  → tasks.sync_notify
  → common.notify.Notify.notify
  → Alerts.SystemMgmtUtils.send_msg_with_channel
  → RPC.SystemMgmt.send_msg_with_channel
  → SystemMgmt NATS handler: send_msg_with_channel
  → channel_utils 的各渠道函数
  → SMTP / 平台 HTTP / NATS
```

当前模板正文写死的位置是 Alerts 的 `NotifyParamsFormat`，不是 SystemMgmt 的邮件或
机器人发送函数。模板渲染完成后仍沿用上述链路。

代码入口：

- `server/apps/alerts/common/notify/base.py`
- `server/apps/alerts/common/notify/notify.py`
- `server/apps/alerts/utils/system_mgmt_util.py`
- `server/apps/rpc/system_mgmt.py`
- `server/apps/system_mgmt/nats/channels.py`
- `server/apps/system_mgmt/utils/channel_utils.py`

## 3. 渠道配置页面实际提供什么

`web/src/app/system-manager/(pages)/channel/page.tsx` 展示邮件、群聊小助手、NATS、IM 通知入口。

其中群聊小助手是统一配置入口；`components/channel/channelModal.tsx` 可切换：

- 企业微信机器人 `enterprise_wechat_bot`
- 飞书机器人 `feishu_bot`
- 钉钉机器人 `dingtalk_bot`
- 其他 `custom_webhook`

邮件配置 SMTP、认证、TLS、发件人等连接参数。机器人配置地址与签名。
自定义 Webhook 额外提供 request_method、headers、body_template。

这些表单定义投递连接和外部请求协议，不是定义“生产故障告警应该显示哪些字段”。
`Channel.config` 是 JSON；当前 `ChannelSerializer` 没有通用业务正文模板校验器，
其专门配置校验主要包括组织、加密字段和 NATS 模式等。

前端存在 `ChannelTemplate` 类型和 `getChannelTemp()` 对 `/system_mgmt/channel_template/` 的
请求定义，后端也留有 `TemplateFilter` 类。但已检查的主线 `system_mgmt/urls.py` 没有注册
channel_template 路由，当前 Channel 模型也没有对应的业务模板模型；不能凭残留名称判断
“系统管理已有一套可以直接复用的通知模板管理”。企业扩展如以后引入同名路由需另行核对。

IM 通知是另一套 `IMNotificationChannel`、账号映射和 provider Adapter 能力。
当前上述告警中心 `Notify` 链路不经它，不能把它与 Channel 的企业微信机器人混在一起接入。

## 4. 各 Adapter 对内容的处理

| 渠道 | 当前处理 | 对模板的实际含义 |
|---|---|---|
| 邮件 | `MIMEText(content, "html", "utf-8")`，独立 Subject，支持附件参数 | 调用方可以提供已生成 HTML；函数没有业务版式白名单或模板求值 |
| 企业微信机器人 | `{msgtype: "markdown", markdown: {content}}` | 正文是 Markdown；外壳由 Adapter 决定，不是 arbitrary payload |
| 钉钉机器人 | `{msgtype: "markdown", markdown: {title, text: content}}` | 标题和 Markdown 正文分别传入 |
| 飞书机器人 | 固定 interactive card，header title + Markdown element | 可定制该标题和正文；当前函数不能透传任意 card JSON |
| 自定义 Webhook | JSON 解析 body_template 后递归替换 `{{content}}`；非 JSON 则字符串替换发送 | 业务内容和传输请求体是两层；正文字符串可包含 Markdown/HTML/JSON 文本 |
| 普通 NATS message 路径 | 规范化 message/team/user_ids；再按渠道 namespace/method 发送 | 不能从 RPC 注释里的“原样”推断 handler 接受任意对象 |
| NATS 事件副本/企业扩展 | 单独协议和认证/模式处理 | 必须独立看契约，不沿用普通消息模板的假设 |

### 4.1 自动追加接收人

当前企微/飞书会追加换行和 `To: @...`，钉钉/Webhook 会追加 `<br>To: @...`。
因此它们不保证输入 content 与发出的正文完全相等。

为实现用户完整控制通知正文，已新增通用可选 `append_receivers`，默认 true；自定义
告警通知显式传 false。该参数只是展示选项，底层不依据模板 ID 判断何时关闭。
实际接收人仍通过 receivers 传入，不得通过清空 receivers 来隐藏正文中的人名。

### 4.2 Webhook 的两层模板示例

告警中心负责生成内容：

```text
### 【严重】生产数据库连接数过高
告警对象：prod-mysql-01
```

系统管理的渠道负责外部请求体：

```json
{
  "msgtype": "markdown",
  "markdown": {"content": "{{content}}"}
}
```

渠道只替换 `{{content}}`，不继续解析其中的 `{{ alert.title }}` 或富化路径。
如果请求体是 `{"data":"{{content}}"}`，而 content 是 `{"a":1}` 字符串，最终 data
仍为字符串，不应声称现有机制能把它自动转换成任意 JSON 对象。

实施方案中的“文本通知正文”表示通用字符串插槽，不表示必须禁止 Markdown/HTML 排版。
其预览默认展示准确的渲染后源码；已知目标格式时可以辅助预览，不根据 body_template
猜测或擅自变更外部协议。

## 5. 两个发送入口不能混用

### 5.1 当前告警中心入口：send_msg_with_channel

- 接收已生成 title/content/receivers，邮件保留 HTML，机器人保留正文 Markdown。
- 没有业务模板查询或告警变量求值。
- 仍有渠道存在性、接收人解析、NATS 协议、出站地址等检查；不能据此宣称完全没有约束。

### 5.2 另一入口：dispatch_notification

`server/apps/system_mgmt/nats/channels.py` 中已有公开通知投递能力，APM 及 Monitor 的
部分链路在使用。

它检查 delivery_key、组织、接收人和消息长度；当前 title 最长 512 字符、body 最长
20,000 字符。这些是该 Interface 的字符限制，不是所有渠道的统一字节限制。

对于 HTML/Markdown 渠道，它调用 `_escape_notification_rich_text`：先 HTML escape，
再转义 Markdown 保留字符。这条接口按普通字段文本处理正文。直接传 `<table>...` 或
`**严重**`，会破坏调用方原本想表达的富格式。

现有回归证据：
`server/apps/system_mgmt/tests/test_nats_api_handlers_service.py`
中的 `test_public_notification_dispatch_escapes_rich_text_before_transport`。

**本次不把 Alerts 自定义模板切换到 dispatch_notification，也不删除它的转义来迁就模板。**
若将来统一入口，需要显式区分“普通文本”和“已渲染富格式”的契约，验证所有既有调用方；
那属于另外一项协议演进。

## 6. 查询与试发也要区分

- SystemMgmt 已有 `search_channel_list_scoped`、`list_notification_channels_scoped` 等
  授权查询接口；其中公开 capability 当前返回 delivery_mode/recipient_mode 等，不包含
  完整编辑器格式、模板变量或 HTML 支持表。
- Alerts 当前 `get_channel_list` 直接查询非 NATS Channel 并合并 OpsPilot 渠道，不能因为
  底层管理页面已经做过权限过滤，就认定 Alerts 的候选查询也已继承该过滤。
- 新模板候选与绑定应接入经过校验的渠道摘要查询，不读取或回传渠道凭据；保留 Alerts
  “非 NATS + OpsPilot 托管 NATS”的产品范围，不把事件副本通道错误列为通知模板目标。
- SystemMgmt 的 `ChannelViewSet.test_send` 使用服务端固定测试内容，支持测试未保存的
  连接配置，目的是验证渠道连通性，不是预览或试发用户写的告警模板。
- 告警模板试发由 Alerts 校验当前编辑内容、真实告警的团队可见性和渠道授权，再通过已保存的
  channel ID 调用通用发送能力；因此新建模板和未保存的编辑内容也能试发，但不创建临时模板。
  Alerts 不读取 SMTP、Webhook 等原始配置，也不复用 SystemMgmt 的固定内容 `test_send`。

## 7. 已落实的实现边界

1. 系统管理继续只负责连接、渠道 Adapter、协议和投递结果；不新增告警模板 CRUD、告警
   字段名单、模板 revision 或场景判断。
2. 模板存储、绑定、上下文、变量求值、版本快照、预览和业务回退均在 Alerts。
3. 保持现有 `send_msg_with_channel` 调用链，不因统一命名替换成语义不同的接口。
4. 系统管理的必要内容行为改动收敛为向后兼容的接收人追加选项；告警渠道查询按当前组织
   筛选，并单独并入 OpsPilot 托管 NATS。业务模板渲染通过底层 Adapter 的测试替身验证。
5. 已发送内容不能再次整体 escape 或按固定模板重排；变量值和用户写的格式标记分开处理。
6. HTML 白名单、动态属性和长度上界已经作为 Alerts 编辑/渲染安全策略实现，**不是系统
   管理已有的模板限制**。这些限制没有推广到共享 sender，也不追溯拒绝其他业务现有内容。
7. 模板内容定制的排版自由度以“保留业务用户写的格式”为目标；预览隔离与变量安全并不
   等于必须重排所有 HTML。资源/协议限制与浏览器预览限制需分别呈现，不擅自声称平台不支持。
8. 第一版已经接入自动分派、提醒、升级和恢复；未分派汇总继续沿用既有固定内容。
