import pytest

from apps.system_mgmt.utils.i18n import system_mgmt_message


@pytest.mark.parametrize(
    "key, values, zh_text, en_text",
    [
        ("error.initial_password_mode_invalid", {"mode": "weekly"}, "初始密码模式不合法: weekly", "Invalid initial password mode: weekly"),
        ("error.password_policy_invalid", {}, "密码策略配置无效", "Password policy configuration is invalid"),
        ("error.initial_password_reset_required", {}, "请重新设置初始密码", "Set the initial password again"),
        ("error.initial_password_required", {}, "请设置初始密码", "Set an initial password"),
        ("error.otp_whitelist_must_be_user_ids", {}, "OTP 白名单必须是用户 ID 列表", "OTP allowlist must be a list of user IDs"),
        ("error.no_permission_access_team", {}, "无权访问该团队数据", "You do not have permission to access this organization's data"),
        ("error.im_group_channel_unavailable", {}, "IM 群协作渠道不存在或已禁用", "IM collaboration channel does not exist or is disabled"),
        ("error.im_group_channel_not_ready", {}, "IM 群协作渠道尚未就绪", "IM collaboration channel is not ready"),
        ("error.im_group_provider_unsupported", {}, "当前 IM 平台不支持群协作", "This IM platform does not support group collaboration"),
        ("error.im_group_instance_not_ready", {}, "IM 群协作集成实例尚未就绪", "IM collaboration integration instance is not ready"),
        ("error.im_group_capability_not_ready", {}, "IM 群协作能力尚未就绪", "IM collaboration capability is not ready"),
        (
            "error.builtin_entry_immutable",
            {"label": "10.0.0.0/8"},
            "内置条目不可修改或删除: 10.0.0.0/8",
            "Built-in entries cannot be modified or deleted: 10.0.0.0/8",
        ),
        (
            "error.forbidden_network_supernet",
            {},
            "禁止添加 0.0.0.0/0 或 ::/0（等于关闭全部防护）",
            "Adding 0.0.0.0/0 or ::/0 is forbidden because it disables all protection",
        ),
        ("error.opspilot_channel_readonly", {}, "OpsPilot 工作流自动创建的通道不可编辑或删除", "Channels created by an OpsPilot workflow cannot be edited or deleted"),
        ("error.email_recipient_missing_or_unknown", {}, "用户邮箱为空或用户不存在", "The user has no email address or does not exist"),
        ("error.password_strength_insufficient", {}, "密码强度不够", "Password does not meet the strength requirements"),
        (
            "error.user_sync_scope_unavailable",
            {},
            "当前同步范围已不可用，请重新选择部门",
            "The current sync scope is no longer available. Select the department again.",
        ),
        ("error.initial_password_email_delivery_failed", {}, "邮件发送失败", "Failed to send the email"),
        ("email.password_expiring_subject", {}, "密码即将过期提醒", "Your password will expire soon"),
        (
            "email.password_expiring_body",
            {"name": "Ada", "days": 3},
            "<p>尊敬的 Ada：</p><p>您的密码将在 <b>3</b> 天后过期，请尽快修改密码。</p>",
            "<p>Hello Ada,</p><p>Your password will expire in <b>3</b> day(s). Please change it soon.</p>",
        ),
        ("email.password_expired_subject", {}, "密码已过期提醒", "Your password has expired"),
        (
            "email.password_expired_body",
            {"name": "Ada"},
            "<p>尊敬的 Ada：</p><p>您的密码已过期，请立即修改密码。</p>",
            "<p>Hello Ada,</p><p>Your password has expired. Please change it now.</p>",
        ),
        ("error.current_team_archived_or_missing", {}, "current_team 对应组织已归档或不存在", "The current organization is archived or does not exist"),
        ("error.channel_id_not_found", {}, "传入的channel_id无法匹配到channel", "No channel matches the given channel_id"),
        ("error.notification_provider_unavailable", {}, "通知传输暂不可用。", "Notification transport is temporarily unavailable."),
        ("error.notification_invalid_provider_response", {}, "通知渠道返回格式无效。", "The notification channel returned an invalid response."),
        ("error.alert_copy_partial_accepted", {}, "告警中心仅接受了部分事件副本。", "The alert center accepted only some event copies."),
        ("error.notification_delivery_failed", {}, "通知渠道投递失败。", "Notification channel delivery failed."),
        ("error.alert_copy_rejected", {}, "告警中心未接受事件副本。", "The alert center did not accept the event copy."),
        (
            "error.vault_secret_key_not_configured",
            {},
            "SECRET_KEY 未配置,无法加解密 vault",
            "SECRET_KEY is not configured; cannot encrypt or decrypt the vault",
        ),
        ("channel.opspilot_nats_trigger_description", {}, "OpsPilot 工作流自动创建的 NATS 触发通道", "NATS trigger channel created by an OpsPilot workflow"),
        (
            "channel.send_parameter.channel_id",
            {"channel_id": 7, "channel_name": "邮箱A"},
            "固定填写 7，对应渠道「邮箱A」。",
            'Always set this to 7, for the "邮箱A" channel.',
        ),
        (
            "channel.send_parameter.channel_type",
            {"channel_type": "email"},
            "固定填写 email。",
            "Always set this to email.",
        ),
        (
            "channel.send_parameter.channel_type_im",
            {},
            "固定填写 im_notification，用来和同号的普通渠道区分。",
            "Always set this to im_notification, to distinguish it from a regular channel with the same ID.",
        ),
        ("channel.send_parameter.title_email", {}, "邮件主题。可以留空。", "Email subject. Can be left empty."),
        (
            "channel.send_parameter.title_enterprise_wechat",
            {},
            "企微应用消息不使用标题，传空字符串即可。",
            "Enterprise WeChat app messages do not use a title; pass an empty string.",
        ),
        (
            "channel.send_parameter.title_enterprise_wechat_bot",
            {},
            "企微机器人只发送正文，标题不会出现在消息里，传空字符串即可。",
            "Enterprise WeChat bots send only the body; the title does not appear in the message. Pass an empty string.",
        ),
        (
            "channel.send_parameter.title_feishu_bot",
            {},
            "飞书卡片标题。留空时渠道侧显示为「通知」。",
            'Feishu card title. If left empty, the channel displays "通知".',
        ),
        (
            "channel.send_parameter.title_dingtalk_bot",
            {},
            "钉钉 markdown 标题。留空时渠道侧显示为「通知」。",
            'DingTalk markdown title. If left empty, the channel displays "通知".',
        ),
        (
            "channel.send_parameter.title_custom_webhook",
            {},
            "自定义 Webhook 不使用标题，传空字符串即可。",
            "Custom webhooks do not use a title; pass an empty string.",
        ),
        (
            "channel.send_parameter.title_im_notification",
            {},
            "IM 应用通知标题。可以留空。最长 512 个字符。",
            "IM app notification title. Can be left empty. Maximum 512 characters.",
        ),
        (
            "channel.send_parameter.title_default",
            {},
            "标题。可以留空。最长 512 个字符。",
            "Title. Can be left empty. Maximum 512 characters.",
        ),
        (
            "channel.send_parameter.content_email",
            {},
            "邮件正文。按 HTML 发送，不会转义标签，换行也不会改成换行标签。",
            "Email body, sent as HTML. Tags are not escaped, and line breaks are not converted to line-break tags.",
        ),
        ("channel.send_parameter.content_enterprise_wechat", {}, "企微应用文本消息正文。", "Enterprise WeChat app text message body."),
        (
            "channel.send_parameter.content_enterprise_wechat_bot",
            {},
            "企微机器人 markdown 正文。接收人名会追加在正文后面。",
            "Enterprise WeChat bot markdown body. Recipient names are appended to the body.",
        ),
        (
            "channel.send_parameter.content_feishu_bot",
            {},
            "飞书卡片 markdown 正文。接收人名会追加在正文后面。",
            "Feishu card markdown body. Recipient names are appended to the body.",
        ),
        (
            "channel.send_parameter.content_dingtalk_bot",
            {},
            "钉钉 markdown 正文。接收人名会追加在正文后面。",
            "DingTalk markdown body. Recipient names are appended to the body.",
        ),
        (
            "channel.send_parameter.content_custom_webhook",
            {},
            "通知正文，会替换该渠道模板中的 {{content}}。接收人名会追加在正文后面。",
            "Notification body; it replaces {{content}} in the channel template. Recipient names are appended to the body.",
        ),
        (
            "channel.send_parameter.content_im_notification",
            {},
            "IM 应用通知正文，不能为空。最长 20000 个字符。",
            "IM app notification body. Required. Maximum 20,000 characters.",
        ),
        (
            "channel.send_parameter.content_default",
            {},
            "通知正文，不能为空。最长 20000 个字符。",
            "Notification body. Required. Maximum 20,000 characters.",
        ),
        (
            "channel.send_parameter.receivers_system_user",
            {},
            "平台用户 ID 字符串，取自 GET /openapi/v1/system-mgmt/users 返回的 id，且必须属于当前组织。不要传用户名。1 到 100 个，不能重复。",
            (
                "Platform user ID strings from the id field returned by GET /openapi/v1/system-mgmt/users. "
                "They must belong to the current organization. Do not pass usernames. 1 to 100 items, no duplicates."
            ),
        ),
        (
            "channel.send_parameter.receivers_free_text",
            {},
            "渠道侧接收人名，原样附在消息里，不是平台用户 ID。1 到 100 个，每个最长 150 个字符，不能重复。",
            (
                "Channel-side recipient names, attached to the message as-is; not platform user IDs. "
                "1 to 100 items, each at most 150 characters, no duplicates."
            ),
        ),
        ("channel.send_parameter.receivers_default", {}, "接收人列表。", "Recipient list."),
        (
            "export.too_many_rows",
            {"limit": 10000, "count": 10001},
            "导出行数超过上限 10000（当前 10001 行）。请缩小筛选条件，或使用 selected_ids 导出已选记录。",
            "Export exceeds the limit of 10000 rows (current count is 10001). Narrow the filters, or export the selected rows with selected_ids.",
        ),
        ("export.login_log_sheet", {}, "用户登录日志", "User login logs"),
        ("export.operation_log_filename", {}, "用户操作日志", "user_operation_logs"),
    ],
)
def test_system_mgmt_user_visible_messages_follow_locale(key, values, zh_text, en_text):
    chinese = system_mgmt_message("zh-Hans", key, **values)
    english = system_mgmt_message("en", key, **values)
    assert chinese == zh_text
    assert english == en_text
    assert chinese != english


def test_opspilot_channel_description_stays_language_neutral_until_read():
    from apps.system_mgmt.utils.i18n import OPSPILOT_NATS_DESCRIPTION_MARKER, localized_channel_description

    assert OPSPILOT_NATS_DESCRIPTION_MARKER == "opspilot_nats_trigger"
    assert localized_channel_description(OPSPILOT_NATS_DESCRIPTION_MARKER, "en") == ("NATS trigger channel created by an OpsPilot workflow")
    assert localized_channel_description("OpsPilot 工作流自动创建的 NATS 触发通道", "zh-Hans") == ("OpsPilot 工作流自动创建的 NATS 触发通道")
    assert localized_channel_description("manual description", "en") == "manual description"
