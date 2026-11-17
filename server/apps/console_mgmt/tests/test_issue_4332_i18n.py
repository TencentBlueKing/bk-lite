from apps.console_mgmt.i18n import console_message
from apps.core.utils.loader import LanguageLoader


KEYS = (
    "error.verification_code_expired",
    "error.email_code_rate_limit",
    "error.please_provide_token",
    "error.use_current_user_apps",
    "error.use_configure_user_apps",
    "error.delete_user_apps_unsupported",
    "error.use_rpc_create_notification",
    "error.full_update_unsupported",
    "error.use_mark_as_read",
    "error.notification_deleted",
    "error.notification_marked_read",
    "error.notification_marked_count",
    "error.notification_id_list_invalid",
)


def test_console_messages_exist_in_both_locales():
    en = LanguageLoader(app="console_mgmt", default_lang="en")
    zh = LanguageLoader(app="console_mgmt", default_lang="zh-Hans")
    for key in KEYS:
        assert isinstance(en.get(key), str) and en.get(key), key
        assert isinstance(zh.get(key), str) and zh.get(key), key
        assert en.get(key) != zh.get(key)


def test_marked_count_follows_locale():
    english = type("Req", (), {"user": type("User", (), {"locale": "en"})()})()
    chinese = type("Req", (), {"user": type("User", (), {"locale": "zh-Hans"})()})()
    assert console_message(english, "error.notification_marked_count", "已标记 {count} 条通知为已读", count=2) == "Marked 2 notifications as read"
    assert console_message(chinese, "error.notification_marked_count", "已标记 {count} 条通知为已读", count=2) == "已标记 2 条通知为已读"
