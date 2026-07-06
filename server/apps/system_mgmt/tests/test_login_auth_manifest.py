from apps.system_mgmt.providers.manifests.feishu import PROVIDER_MANIFEST as FEISHU_PROVIDER_MANIFEST
from apps.system_mgmt.providers.manifests.wechat import PROVIDER_MANIFEST as WECHAT_PROVIDER_MANIFEST


def test_feishu_login_auth_manifest_declares_recommended_external_field():
    template = FEISHU_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    assert template.available_external_fields == ["user_id", "open_id", "name", "email", "mobile"]
    assert template.default_external_match_field == "user_id"


def test_wechat_login_auth_manifest_declares_recommended_external_field():
    template = WECHAT_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    assert template.available_external_fields == ["openid", "unionid"]
    assert template.default_external_match_field == "openid"
