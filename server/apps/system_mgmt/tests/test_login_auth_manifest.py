from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST as AD_PROVIDER_MANIFEST
from apps.system_mgmt.providers.manifests.feishu import PROVIDER_MANIFEST as FEISHU_PROVIDER_MANIFEST
from apps.system_mgmt.providers.manifests.wechat import PROVIDER_MANIFEST as WECHAT_PROVIDER_MANIFEST
from apps.system_mgmt.providers.manifests.wecom import PROVIDER_MANIFEST as WECOM_PROVIDER_MANIFEST
def test_ad_external_field_manifests_expose_both_phone_variants():
    """AD 表单暴露两个可映射的手机号字段。"""
    login_template = AD_PROVIDER_MANIFEST.business_templates["login_auth_form"]
    sync_template = AD_PROVIDER_MANIFEST.business_templates["user_sync_form"]

    for template in (login_template, sync_template):
        assert "telephoneNumber" in template.available_external_fields
        assert "mobile" in template.available_external_fields
        assert "mobilePhone" in template.available_external_fields


def test_feishu_login_auth_manifest_declares_recommended_external_field():
    template = FEISHU_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    assert template.available_external_fields == ["user_id", "open_id", "name", "email", "mobile"]
    assert template.default_external_match_field == "user_id"


def test_feishu_user_sync_manifest_declares_scopes_and_department_batch_endpoints():
    capability = FEISHU_PROVIDER_MANIFEST.get_capability("user_sync")
    defaults = {field.key: field.default for field in capability.connection_template}

    assert defaults["user_sync_scopes_url"] == "https://open.feishu.cn/open-apis/contact/v3/scopes"
    assert defaults["user_sync_departments_batch_url"] == "https://open.feishu.cn/open-apis/contact/v3/departments/batch"


def test_wechat_login_auth_manifest_declares_recommended_external_field():
    template = WECHAT_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    assert template.available_external_fields == ["openid", "unionid"]
    assert template.default_external_match_field == "openid"


def test_wecom_manifest_declares_shared_credentials_and_three_capabilities():
    groups = WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
    template = WECOM_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    field_keys = [field.key for group in groups for field in group.fields]
    assert field_keys == [
        "corp_id", "corp_secret", "agent_id", "access_token_url", "proxy_url",
    ]
    assert {capability.key for capability in WECOM_PROVIDER_MANIFEST.capabilities} == {
        "login_auth", "user_sync", "im_notification"
    }
    assert template.available_external_fields == ["userid"]
    assert template.default_external_match_field == "userid"


def test_wecom_manifest_does_not_expose_api_base_url_or_sso_base_url():
    credentials = {
        field.key for field in WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups[0].fields
    }
    capability_field_keys = {
        capability.key: {field.key for field in capability.connection_template}
        for capability in WECOM_PROVIDER_MANIFEST.capabilities
    }

    assert "api_base_url" not in credentials
    assert "sso_base_url" not in credentials
    for capability_key, keys in capability_field_keys.items():
        assert "access_token_url" not in keys, capability_key
        assert not any(key.endswith("_access_token_url") for key in keys), capability_key


def test_wecom_login_auth_manifest_limits_external_fields_to_userid():
    template = WECOM_PROVIDER_MANIFEST.business_templates["login_auth_form"]

    assert template.available_external_fields == ["userid"]
    assert template.default_external_match_field == "userid"
    assert template.identity_fields == ["userid"]


def test_wecom_login_auth_manifest_does_not_allow_unmatched_user_creation():
    template = WECOM_PROVIDER_MANIFEST.business_templates["login_auth_form"]
    field_keys = {
        field.key
        for group in template.groups
        for field in group.fields
    }

    assert "unmatched_user_action" not in field_keys
    assert "default_group_name" not in field_keys


def test_wecom_base_connection_fields_reset_affected_capabilities():
    fields = {
        field.key: field
        for group in WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
        for field in group.fields
    }

    assert fields["corp_id"].reset_capabilities == ["login_auth", "user_sync", "im_notification"]
    assert fields["corp_secret"].reset_capabilities == ["login_auth", "user_sync", "im_notification"]
    assert fields["agent_id"].reset_capabilities == ["login_auth", "user_sync", "im_notification"]
    assert fields["access_token_url"].reset_capabilities == ["login_auth", "user_sync", "im_notification"]
    assert fields["proxy_url"].reset_capabilities == ["login_auth", "user_sync", "im_notification"]


def test_wecom_capability_fields_reset_only_their_capability():
    for capability_key, expected_fields in {
        "login_auth": ["login_auth_authorize_url", "login_auth_user_info_url"],
        "user_sync": ["user_sync_departments_url", "user_sync_users_url"],
        "im_notification": ["im_notification_users_url", "im_notification_send_message_url"],
    }.items():
        capability = WECOM_PROVIDER_MANIFEST.get_capability(capability_key)
        field_keys = {field.key: field for field in capability.connection_template}
        for field_key in expected_fields:
            assert field_keys[field_key].reset_capabilities == [capability_key], (
                capability_key,
                field_key,
                field_keys[field_key].reset_capabilities,
            )


def test_wecom_user_sync_manifest_exposes_recursive_toggle():
    fields = {
        field.key: field
        for group in WECOM_PROVIDER_MANIFEST.business_templates["user_sync_form"].groups
        for field in group.fields
    }

    include_child = fields["include_child_departments"]
    assert include_child.field_type == "boolean"
    assert include_child.default is True
    assert "递归" in include_child.label


def test_wecom_connection_templates_prefill_official_endpoints():
    expected_defaults = {
        ("base_connection", "access_token_url"): "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        ("login_auth", "login_auth_authorize_url"): "https://open.work.weixin.qq.com/wwopen/sso/qrConnect",
        ("login_auth", "login_auth_user_info_url"): "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
        ("user_sync", "user_sync_departments_url"): "https://qyapi.weixin.qq.com/cgi-bin/department/list",
        ("user_sync", "user_sync_users_url"): "https://qyapi.weixin.qq.com/cgi-bin/user/list",
        ("im_notification", "im_notification_users_url"): "https://qyapi.weixin.qq.com/cgi-bin/user/list",
        ("im_notification", "im_notification_send_message_url"): "https://qyapi.weixin.qq.com/cgi-bin/message/send",
    }

    for location, field_key, expected in (
        (location, field_key, expected_defaults[(location, field_key)])
        for location, field_key in expected_defaults
    ):
        if location == "base_connection":
            field = next(
                item
                for group in WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
                for item in group.fields
                if item.key == field_key
            )
        else:
            capability = WECOM_PROVIDER_MANIFEST.get_capability(location)
            field = next(
                item for item in capability.connection_template if item.key == field_key
            )
        assert field.default == expected, (location, field_key, field.default, expected)


def test_wecom_endpoint_field_labels_do_not_include_full_address():
    base_fields = {
        field.key: field
        for group in WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
        for field in group.fields
    }
    for field_key in ("access_token_url", "proxy_url"):
        assert "完整地址" not in base_fields[field_key].label, field_key

    for capability_key in ("login_auth", "user_sync", "im_notification"):
        capability = WECOM_PROVIDER_MANIFEST.get_capability(capability_key)
        for field in capability.connection_template:
            assert "完整地址" not in field.label, (capability_key, field.key, field.label)


def test_wecom_base_connection_groups_credentials_and_endpoints_separately():
    groups = WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
    group_keys = {group.key for group in groups}
    assert "credentials" in group_keys
    assert "endpoints" in group_keys

    credentials_group = next(group for group in groups if group.key == "credentials")
    endpoints_group = next(group for group in groups if group.key == "endpoints")
    assert "应用凭证" in credentials_group.title
    assert "公共接口" in endpoints_group.title

    credentials_keys = {field.key for field in credentials_group.fields}
    endpoints_keys = {field.key for field in endpoints_group.fields}
    assert {"corp_id", "corp_secret", "agent_id"} <= credentials_keys
    assert {"access_token_url", "proxy_url"} <= endpoints_keys
    assert credentials_keys.isdisjoint(endpoints_keys)


def test_wecom_credential_fields_carry_placeholders_or_help_text():
    credentials_group = next(
        group for group in WECOM_PROVIDER_MANIFEST.instance_templates["base_connection"].groups
        if group.key == "credentials"
    )
    fields = {field.key: field for field in credentials_group.fields}
    assert fields["corp_id"].placeholder == "ww1234567890abcdef"
    assert fields["corp_id"].help_text == "企业微信管理后台 → 我的企业 → 企业信息 → 企业 ID"
    assert fields["corp_secret"].placeholder == "如无需变更可留空"
    assert fields["agent_id"].placeholder == "1000002"
    assert fields["agent_id"].help_text == "企业微信管理后台 → 应用管理 → 自建应用 → AgentId"
