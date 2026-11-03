# ITSM 通知渠道目录补齐 IM 应用通知

## 行为

- `GET system-mgmt/notification-channels` 返回调用身份组织范围内的全部 `Channel` 和 `IMNotificationChannel`，统一分页；不按类型、启用状态或同步状态隐藏实例。本次不增加过滤参数，保留原组织权限边界。
- 不返回渠道配置、应用凭据或用户映射内容。`availability` 表示 `available`、`disabled`、`unavailable`、`pending_sync`、`needs_resync` 等状态。内部 NATS 渠道可列出，但为 `unsupported`，不开放外部投递。
- IM 渠道的 `channel_type` 为 `im_notification`，`recipient_mode` 为 `system_user`。两张表各自拥有主键，以 `(channel_type, id)` 标识渠道。
- `POST system-mgmt/notification-channels/send` 新增可选 `channel_type`。旧渠道省略时保持原行为；IM 必须传 `im_notification`。发送前沿用渠道组织与接收人组织校验，再复用现有 IM 用户映射和发送服务。未同步、停用、能力不可用等错误继续由既有服务返回。
- ITSM 仅消费 `notification-channels` 和 `notification-channels/send`，本变更不包含 ITSM Apps 适配，也不要求客户端调用 IM 管理接口。

## 发布与回滚

本变更为待评审草稿，不可直接发布。当前 ITSM 按渠道 ID 标识实例，发送时不传 `channel_type`；本草稿新增的 IM 路由依赖该字段，因此仍需在 BK-Lite 侧解决统一目录身份及既有发送契约兼容问题，再完成 ITSM 实际链路验证。无需迁移数据库，不自动修改现有通知配置。

## 验证

覆盖双组织隔离、全部渠道类型、未就绪/停用可见、混合分页、同号渠道发送路由、真实用户映射至外部运行服务、不可用渠道拒绝、旧渠道发送及接口 schema。
本地测试隔离第三方发送，不代表飞书真实送达；实际验证仍需解除飞书 IP 白名单阻塞并成功同步用户映射。
