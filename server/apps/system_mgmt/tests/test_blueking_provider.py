from apps.system_mgmt.providers.builtin.blueking import PROVIDER_MANIFEST
from apps.system_mgmt.providers.builtin.blueking.adapters.client import (
    ALL_DEPARTMENT_ID,
    LIST_DEPARTMENTS_PATH,
    LIST_USERS_PATH,
    LOGIN_GET_USER_PATH,
    RETRIEVE_USER_PATH,
)


def test_blueking_manifest_only_declares_login_auth_and_user_sync():
    assert PROVIDER_MANIFEST.key == "blueking"
    assert {capability.key for capability in PROVIDER_MANIFEST.capabilities} == {"login_auth", "user_sync"}
    assert "im_notification" not in {capability.key for capability in PROVIDER_MANIFEST.capabilities}
    assert "im_group" not in {capability.key for capability in PROVIDER_MANIFEST.capabilities}


def test_blueking_app_token_is_secret_and_base_fields_reset_login_and_sync():
    fields = {field.key: field for group in PROVIDER_MANIFEST.instance_templates["base_connection"].groups for field in group.fields}

    assert set(fields) == {"bk_url", "app_id", "app_token"}
    assert "bk_username" not in fields
    assert fields["app_token"].secret is True
    assert fields["app_token"].field_type == "password"
    assert fields["app_token"].mask_strategy == "full"
    for field in fields.values():
        assert field.reset_capabilities == ["login_auth", "user_sync"]


def test_blueking_login_auth_locks_username_mapping_and_exposes_unmatched_action():
    template = PROVIDER_MANIFEST.business_templates["login_auth_form"]
    field_keys = {field.key for group in template.groups for field in group.fields}

    assert template.available_external_fields == ["username"]
    assert template.default_external_match_field == "username"
    assert template.identity_fields == ["username"]
    assert "unmatched_user_action" in field_keys
    assert "default_group_name" not in field_keys


def test_blueking_user_sync_form_matches_wecom_pull_settings():
    fields = {field.key: field for group in PROVIDER_MANIFEST.business_templates["user_sync_form"].groups for field in group.fields}

    assert fields["root_department_id"].required is True
    assert fields["root_department_id"].input_mode == "department_select"
    assert fields["include_child_departments"].field_type == "boolean"
    assert fields["include_child_departments"].default is True


def test_blueking_does_not_expose_esb_paths_as_form_fields():
    instance_keys = {field.key for group in PROVIDER_MANIFEST.instance_templates["base_connection"].groups for field in group.fields}
    capability_keys = {field.key for capability in PROVIDER_MANIFEST.capabilities for field in capability.connection_template}

    assert instance_keys.isdisjoint({"login_auth_user_info_url", "user_sync_departments_url", "user_sync_users_url"})
    assert not capability_keys
    assert ALL_DEPARTMENT_ID == "bk_all"
    assert LOGIN_GET_USER_PATH == "/api/c/compapi/v2/bk_login/get_user/"
    assert RETRIEVE_USER_PATH == "/api/c/compapi/v2/usermanage/retrieve_user/"
    assert LIST_DEPARTMENTS_PATH == "/api/c/compapi/v2/usermanage/list_departments/"
    assert LIST_USERS_PATH == "/api/c/compapi/v2/usermanage/list_users/"
