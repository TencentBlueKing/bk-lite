import pytest

from apps.system_mgmt.providers.schemas import ProviderManifest


def test_provider_manifest_public_dict_includes_connection_template():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo",
            "name": "Demo",
            "description": "demo provider",
            "instance_templates": {
                "base_connection": {
                    "title": "Base",
                    "groups": [
                        {
                            "key": "base",
                            "title": "Base Fields",
                            "fields": [{"key": "app_id", "label": "App ID", "required": True}],
                        }
                    ],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "connection_template": [
                        {"key": "user_sync_api_url", "label": "User Sync API URL", "required": True},
                    ],
                    "business_template": "",
                }
            ],
        }
    )

    public_dict = manifest.to_public_dict()

    assert public_dict["instance_template"] == [
        {
            "key": "app_id",
            "label": "App ID",
            "field_type": "string",
            "required": True,
            "secret": False,
            "write_only": False,
            "mask_strategy": "full",
            "default": None,
            "placeholder": "",
            "help_text": "",
            "options": [],
            "reset_capabilities": [],
            "input_mode": None,
        }
    ]
    assert public_dict["capabilities"][0]["connection_template"] == [
        {
            "key": "user_sync_api_url",
            "label": "User Sync API URL",
            "field_type": "string",
            "required": True,
            "secret": False,
            "write_only": False,
            "mask_strategy": "full",
            "default": None,
            "placeholder": "",
            "help_text": "",
            "options": [],
            "reset_capabilities": [],
            "input_mode": None,
        }
    ]


def test_provider_manifest_rejects_duplicate_connection_field_keys():
    with pytest.raises(ValueError, match="Duplicate config field keys"):
        ProviderManifest.model_validate(
            {
                "key": "demo",
                "name": "Demo",
                "instance_templates": {
                    "base_connection": {
                        "title": "Base",
                        "groups": [
                            {
                                "key": "base",
                                "title": "Base Fields",
                                "fields": [{"key": "shared_url", "label": "Shared URL"}],
                            }
                        ],
                    }
                },
                "capabilities": [
                    {
                        "key": "user_sync",
                        "name": "User Sync",
                        "adapter_key": "demo.user_sync",
                        "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                        "connection_template": [
                            {"key": "shared_url", "label": "User Sync URL"},
                        ],
                    }
                ],
            }
        )


def test_provider_manifest_public_dict_includes_business_templates():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo",
            "name": "Demo",
            "instance_templates": {"base_connection": {"title": "Base", "groups": []}},
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [{"key": "root_department_id", "label": "根部门 ID", "required": True}],
                        }
                    ],
                    "available_external_fields": ["user_id", "name"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )

    public_dict = manifest.to_public_dict()
    assert public_dict["business_templates"]["user_sync_form"]["available_external_fields"] == ["user_id", "name"]
    assert public_dict["capabilities"][0]["business_template"] == "user_sync_form"


def test_provider_manifest_rejects_dangling_business_template():
    with pytest.raises(ValueError, match="references unknown business_template"):
        ProviderManifest.model_validate(
            {
                "key": "demo",
                "name": "Demo",
                "business_templates": {},
                "capabilities": [
                    {
                        "key": "user_sync",
                        "name": "User Sync",
                        "adapter_key": "demo.user_sync",
                        "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                        "business_template": "nonexistent_key",
                    }
                ],
            }
        )


def test_business_template_rejects_duplicate_field_keys_across_groups():
    with pytest.raises(ValueError, match="Duplicate field key"):
        ProviderManifest.model_validate(
            {
                "key": "demo",
                "name": "Demo",
                "business_templates": {
                    "form": {
                        "title": "Form",
                        "groups": [
                            {
                                "key": "group_a",
                                "title": "Group A",
                                "fields": [{"key": "shared_key", "label": "Field A"}],
                            },
                            {
                                "key": "group_b",
                                "title": "Group B",
                                "fields": [{"key": "shared_key", "label": "Field B"}],
                            },
                        ],
                    }
                },
                "capabilities": [],
            }
        )


def test_template_field_manifest_supports_input_mode():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo",
            "name": "Demo",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )

    public_dict = manifest.to_public_dict()
    root_field = public_dict["business_templates"]["user_sync_form"]["groups"][0]["fields"][0]
    assert root_field["input_mode"] == "manual_input"


def test_ad_manifest_declares_login_auth_and_user_sync():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    assert PROVIDER_MANIFEST.key == "ad"
    assert [cap.key for cap in PROVIDER_MANIFEST.capabilities] == ["login_auth", "user_sync"]


def test_ad_user_sync_root_dn_is_manual_input():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    template = PROVIDER_MANIFEST.business_templates["user_sync_form"]
    root_field = next(field for group in template.groups for field in group.fields if field.key == "root_dn")

    assert root_field.input_mode == "manual_input"


def test_ad_base_connection_uses_directory_boundary_wording():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    template = PROVIDER_MANIFEST.instance_templates["base_connection"]
    base_dn_field = next(field for group in template.groups for field in group.fields if field.key == "base_dn")

    assert base_dn_field.label == "目录访问边界"
    assert "访问边界" in str(base_dn_field.help_text or "")


def test_ad_user_sync_manifest_exposes_directory_query_parameters():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    template = PROVIDER_MANIFEST.business_templates["user_sync_form"]
    field_map = {field.key: field for group in template.groups for field in group.fields}

    assert list(field_map) == ["root_dn", "user_object_class", "user_filter", "organization_object_class"]
    assert field_map["user_object_class"].default == "user"
    assert field_map["user_filter"].default == "(&(objectCategory=Person)(sAMAccountName=*))"
    assert field_map["organization_object_class"].default == "organizationalUnit"
