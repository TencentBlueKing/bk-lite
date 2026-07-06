from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "wechat",
        "name": "WeChat",
        "description": "Built-in WeChat integration provider for login auth.",
        "instance_templates": {
            "base_connection": {
                "title": "基础连接",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "应用凭证",
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
                "title": "登录认证配置",
                "groups": [
                    {
                        "key": "mapping",
                        "title": "字段映射",
                        "fields": [
                            {"key": "display_name", "label": "显示名称", "field_type": "string", "required": True},
                            {"key": "icon", "label": "图标", "field_type": "string", "required": False},
                            {"key": "description", "label": "描述", "field_type": "string", "required": False},
                            {"key": "external_field", "label": "外部字段", "field_type": "string", "required": True},
                            {"key": "platform_field", "label": "平台字段", "field_type": "select", "required": True},
                            {"key": "unmatched_user_action", "label": "未匹配用户处理方式", "field_type": "select", "required": True},
                            {"key": "default_group_name", "label": "默认用户组名称", "field_type": "string", "required": False},
                        ],
                    }
                ],
                "available_external_fields": ["open_id", "unionid", "nickname"],
                "default_external_match_field": "open_id",
            }
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "WeChat login authentication capability.",
                "adapter_key": "wechat.login_auth",
                "adapter_path": "apps.system_mgmt.providers.adapters.wechat.WechatLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "授权地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.weixin.qq.com/connect/qrconnect",
                    },
                    {
                        "key": "login_auth_access_token_url",
                        "label": "访问令牌地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://api.weixin.qq.com/sns/oauth2/access_token",
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "用户信息地址",
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
