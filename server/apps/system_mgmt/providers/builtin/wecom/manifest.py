from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "wecom",
        "base_connection_adapter_key": "wecom.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.WeComBaseConnectionAdapter",
        "name": "WeCom",
        "description": "Built-in WeCom integration provider.",
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "App credentials",
                        "fields": [
                            {
                                "key": "corp_id",
                                "label": "Corp ID",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "ww1234567890abcdef",
                                "help_text": "WeCom Admin → My Company → Company Information → Corp ID",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                            {
                                "key": "corp_secret",
                                "label": "App Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "placeholder": "Leave blank if unchanged",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                            {
                                "key": "agent_id",
                                "label": "Agent ID",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "1000002",
                                "help_text": "WeCom Admin → App Management → Self-built App → AgentId",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                        ],
                    },
                    {
                        "key": "endpoints",
                        "title": "Public endpoints",
                        "fields": [
                            {
                                "key": "access_token_url",
                                "label": "Access token URL",
                                "field_type": "string",
                                "required": False,
                                "default": "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                            {
                                "key": "proxy_url",
                                "label": "Proxy URL",
                                "field_type": "string",
                                "required": False,
                                "placeholder": "http://127.0.0.1:8080",
                                "help_text": (
                                    "Optional. HTTP(S) proxy used by the BK-Lite backend to reach this WeCom instance. "
                                    "Leave blank to connect directly. HTTP/HTTPS only; SOCKS is not supported."
                                ),
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
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
                        ],
                    }
                ],
                "available_external_fields": ["userid"],
                "default_external_match_field": "userid",
                "identity_fields": ["userid"],
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
                                "help_text": "By default, sync members of the root department and all child departments. Turn this off to sync only direct members of that department.",
                            },
                        ],
                    }
                ],
                "available_external_fields": ["userid", "name", "email", "mobile", "department_ids"],
            },
            "im_notification_form": {
                "title": "IM notification",
                "groups": [
                    {
                        "key": "send",
                        "title": "Send settings",
                        "fields": [
                            {"key": "mapping_strategy", "label": "Mapping strategy", "field_type": "select", "required": True},
                        ],
                    }
                ],
                "available_external_fields": ["userid", "name", "email", "mobile"],
                "matchable_fields": ["userid"],
                "receivable_fields": ["userid"],
                "identity_fields": ["userid"],
                "default_external_match_field": "userid",
                "default_external_receive_field": "userid",
            },
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "WeCom QR login.",
                "adapter_key": "wecom.login_auth",
                "adapter_path": "adapters.login_auth.WeComLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "QR authorization URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.work.weixin.qq.com/wwopen/sso/qrConnect",
                        "reset_capabilities": ["login_auth"],
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "User identity URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
                        "reset_capabilities": ["login_auth"],
                    },
                ],
                "business_template": "login_auth_form",
            },
            {
                "key": "user_sync",
                "name": "User Sync",
                "description": "WeCom user synchronization.",
                "adapter_key": "wecom.user_sync",
                "adapter_path": "adapters.user_sync.WeComUserSyncAdapter",
                "connection_template": [
                    {
                        "key": "user_sync_departments_url",
                        "label": "Department URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/department/list",
                        "reset_capabilities": ["user_sync"],
                    },
                    {
                        "key": "user_sync_users_url",
                        "label": "Member URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/user/list",
                        "reset_capabilities": ["user_sync"],
                    },
                ],
                "business_template": "user_sync_form",
            },
            {
                "key": "im_notification",
                "name": "IM Notification",
                "description": "WeCom application notification.",
                "adapter_key": "wecom.im_notification",
                "adapter_path": "adapters.im_notification.WeComIMNotificationAdapter",
                "connection_template": [
                    {
                        "key": "im_notification_users_url",
                        "label": "Member URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/user/list",
                        "reset_capabilities": ["im_notification"],
                    },
                    {
                        "key": "im_notification_send_message_url",
                        "label": "App message URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                        "reset_capabilities": ["im_notification"],
                    },
                ],
                "business_template": "im_notification_form",
            },
            {
                "key": "im_group",
                "name": "IM Group",
                "description": "WeCom internal application chat capability.",
                "adapter_key": "wecom.im_group",
                "adapter_path": "adapters.im_group.WeComIMGroupAdapter",
                "connection_template": [],
            },
        ],
    }
)
