from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "blueking",
        "base_connection_adapter_key": "blueking.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.BlueKingBaseConnectionAdapter",
        "name": "BlueKing",
        "description": "Built-in BlueKing integration provider.",
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "App credentials",
                        "fields": [
                            {
                                "key": "bk_url",
                                "label": "BlueKing URL",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "https://bk.example.com",
                                "help_text": "BlueKing platform address, including scheme and host.",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "app_id",
                                "label": "App ID",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "bk_lite",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "app_token",
                                "label": "App Token",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "placeholder": "Leave blank if unchanged",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                        ],
                    }
                ],
            }
        },
        "business_templates": {
            "login_auth_form": {
                "title": "Login authentication",
                "groups": [
                    {
                        "key": "mapping",
                        "title": "Field mapping",
                        "fields": [
                            {"key": "display_name", "label": "Display name", "field_type": "string", "required": True},
                            {"key": "icon", "label": "Icon", "field_type": "string", "required": False},
                            {"key": "description", "label": "Description", "field_type": "string", "required": False},
                            {"key": "external_field", "label": "External field", "field_type": "string", "required": True},
                            {"key": "platform_field", "label": "Platform field", "field_type": "select", "required": True},
                            {
                                "key": "unmatched_user_action",
                                "label": "Unmatched user action",
                                "field_type": "select",
                                "required": True,
                            },
                        ],
                    }
                ],
                "available_external_fields": ["username"],
                "default_external_match_field": "username",
                "identity_fields": ["username"],
            },
            "user_sync_form": {
                "title": "User sync",
                "groups": [
                    {
                        "key": "pull",
                        "title": "Pull settings",
                        "fields": [
                            {
                                "key": "root_department_id",
                                "label": "Root department ID",
                                "field_type": "string",
                                "required": True,
                                "input_mode": "department_select",
                            },
                            {
                                "key": "include_child_departments",
                                "label": "Include child departments",
                                "field_type": "boolean",
                                "required": False,
                                "default": True,
                                "help_text": (
                                    "By default, sync members of the root department and all child departments. "
                                    "Turn this off to sync only direct members of that department."
                                ),
                            },
                        ],
                    }
                ],
                "available_external_fields": ["username", "display_name", "email", "mobile", "department_ids"],
            },
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "BlueKing cookie login.",
                "adapter_key": "blueking.login_auth",
                "adapter_path": "adapters.login_auth.BlueKingLoginAuthAdapter",
                "connection_template": [],
                "business_template": "login_auth_form",
            },
            {
                "key": "user_sync",
                "name": "User Sync",
                "description": "BlueKing user synchronization.",
                "adapter_key": "blueking.user_sync",
                "adapter_path": "adapters.user_sync.BlueKingUserSyncAdapter",
                "connection_template": [],
                "business_template": "user_sync_form",
            },
        ],
    }
)
