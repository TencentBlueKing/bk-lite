# NATS 通道「支持通知人」配置契约

## 字段

NATS 通道的 `Channel.config` 可包含 `supports_notify_person` 布尔字段：

- `true`：调用方组装内容时应带通知人。
- `false`：调用方可以不带通知人。
- 缺少该 key 按 `false` 处理。

该字段只存在于 NATS 通道配置。系统管理保存配置原值，不为 API 直创且缺少 key 的通道自动补 `true`；NATS 新增表单默认显式保存 `true`，编辑缺少 key 时展示并保存为 `false`。

## 列表投影

以下列表接口仅对 `channel_type=nats` 投影 `supports_notify_person`：

- `search_channel_list`
- `search_channel_list_scoped`
- `search_opspilot_nats_channels`

严格只有 JSON 布尔值 `true` 投影为 `true`；缺 key 或其他值均为 `false`。非 NATS 列表项不返回该字段。列表仍不返回完整 `Channel.config`，也不会泄露其中的其他配置。

## 责任边界

系统管理只提供配置和列表投影，不做发送强校验，不改 `send_msg_with_channel`、`dispatch_notification` 或 `_notification_channel_capabilities`。监控、告警、日志及其他业务模块自行决定是否按该字段组装通知人。

本期不改告警中心识别、监控/告警/日志页面或存量配置迁移。
