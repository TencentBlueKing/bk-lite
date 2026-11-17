from apps.patch_mgmt.utils.i18n import patch_message


def test_confirmed_patch_messages_follow_locale():
    english = type("Req", (), {"user": type("User", (), {"locale": "en"})()})()
    chinese = type("Req", (), {"user": type("User", (), {"locale": "zh-Hans"})()})()
    assert patch_message(english, "error.offline_catalog_required", "启用离线目录前请先上传离线目录") == "Upload an offline catalog before enabling it"
    assert patch_message(chinese, "error.linux_metadata_missing", "Linux 补丁元数据缺少：{fields}", fields="包名") == "Linux 补丁元数据缺少：包名"
    assert patch_message(english, "error.notification_rule_invalid", "第 {index} 条通知规则格式非法", index=2) == "Notification rule 2 has an invalid format"
