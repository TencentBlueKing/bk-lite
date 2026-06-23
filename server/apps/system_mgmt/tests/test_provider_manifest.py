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
