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
        ("error.builtin_entry_immutable", {"label": "10.0.0.0/8"}, "内置条目不可修改或删除: 10.0.0.0/8", "Built-in entries cannot be modified or deleted: 10.0.0.0/8"),
        ("error.opspilot_channel_readonly", {}, "OpsPilot 工作流自动创建的通道不可编辑或删除", "Channels created by an OpsPilot workflow cannot be edited or deleted"),
        ("error.email_recipient_missing_or_unknown", {}, "用户邮箱为空或用户不存在", "The user has no email address or does not exist"),
        ("error.current_team_archived_or_missing", {}, "current_team 对应组织已归档或不存在", "The current organization is archived or does not exist"),
        ("error.channel_id_not_found", {}, "传入的channel_id无法匹配到channel", "No channel matches the given channel_id"),
        ("channel.opspilot_nats_trigger_description", {}, "OpsPilot 工作流自动创建的 NATS 触发通道", "NATS trigger channel created by an OpsPilot workflow"),
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
    assert localized_channel_description(OPSPILOT_NATS_DESCRIPTION_MARKER, "en") == (
        "NATS trigger channel created by an OpsPilot workflow"
    )
    assert localized_channel_description("OpsPilot 工作流自动创建的 NATS 触发通道", "zh-Hans") == (
        "OpsPilot 工作流自动创建的 NATS 触发通道"
    )
    assert localized_channel_description("manual description", "en") == "manual description"
