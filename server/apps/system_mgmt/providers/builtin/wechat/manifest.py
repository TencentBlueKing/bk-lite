from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "wechat",
        "base_connection_adapter_key": "wechat.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.WechatBaseConnectionAdapter",
        "name": "WeChat",
        "description": "Built-in WeChat integration provider for login auth.",
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "App credentials",
                        "fields": [
                            {
                                "key": "app_id",
                                "label": "App ID",
                                "field_type": "string",
                                "required": True,
                                "reset_capabilities": ["login_auth"],
                            },
                            {
                                "key": "app_secret",
                                "label": "App Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "reset_capabilities": ["login_auth"],
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
                            {"key": "unmatched_user_action", "label": "Unmatched user action", "field_type": "select", "required": True},
                            {"key": "default_group_name", "label": "Default user group name", "field_type": "string", "required": False},
                        ],
                    }
                ],
                "available_external_fields": ["openid", "unionid"],
                "default_external_match_field": "openid",
            }
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "WeChat login authentication capability.",
                "adapter_key": "wechat.login_auth",
                "adapter_path": "adapters.login_auth.WechatLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "Authorization URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.weixin.qq.com/connect/qrconnect",
                    },
                    {
                        "key": "login_auth_access_token_url",
                        "label": "Access token URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://api.weixin.qq.com/sns/oauth2/access_token",
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "User info URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://api.weixin.qq.com/sns/userinfo",
                    },
                ],
                "business_template": "login_auth_form",
            }
        ],
    }
)
