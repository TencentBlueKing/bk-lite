from apps.system_mgmt.providers.manifests.feishu import PROVIDER_MANIFEST


def test_feishu_im_notification_manifest_declares_field_semantics():
    template = PROVIDER_MANIFEST.business_templates["im_notification_form"]

    assert template.available_external_fields == ["user_id", "open_id", "name", "email", "mobile"]
    assert template.matchable_fields == ["email", "mobile", "user_id", "open_id"]
    assert template.receivable_fields == ["user_id", "open_id"]
    assert template.identity_fields == ["user_id", "open_id"]
    assert template.default_external_match_field == "email"
    assert template.default_external_receive_field == "user_id"
