from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "wecom",
        "name": "WeCom",
        "description": "Built-in WeCom integration provider.",
        "instance_templates": {
            "base_connection": {
                "title": "基础连接",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "应用凭证",
                        "fields": [
                            {
                                "key": "corp_id",
                                "label": "企业 ID",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "ww1234567890abcdef",
                                "help_text": "企业微信管理后台 → 我的企业 → 企业信息 → 企业 ID",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                            {
                                "key": "corp_secret",
                                "label": "应用 Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "placeholder": "如无需变更可留空",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                            {
                                "key": "agent_id",
                                "label": "应用 AgentId",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "1000002",
                                "help_text": "企业微信管理后台 → 应用管理 → 自建应用 → AgentId",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                        ],
                    },
                    {
                        "key": "endpoints",
                        "title": "公共接口",
                        "fields": [
                            {
                                "key": "access_token_url",
                                "label": "访问令牌地址",
                                "field_type": "string",
                                "required": False,
                                "default": "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                            {
                                "key": "proxy_url",
                                "label": "网络代理地址",
                                "field_type": "string",
                                "required": False,
                                "placeholder": "http://127.0.0.1:8080",
                                "help_text": (
                                    "可选。BK-Lite 后端访问该企业微信实例的 HTTP(S) 网络代理；"
                                    "留空表示直接连接。仅支持 HTTP/HTTPS，不支持 SOCKS。"
                                ),
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
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
                        ],
                    }
                ],
                "available_external_fields": ["userid"],
                "default_external_match_field": "userid",
                "identity_fields": ["userid"],
            },
            "user_sync_form": {
                "title": "用户同步配置",
                "groups": [
                    {
                        "key": "pull",
                        "title": "拉取配置",
                        "fields": [
                            {
                                "key": "root_department_id",
                                "label": "根部门 ID",
                                "field_type": "string",
                                "required": True,
                                "input_mode": "department_select",
                            },
                            {
                                "key": "include_child_departments",
                                "label": "递归包含子部门",
                                "field_type": "boolean",
                                "required": False,
                                "default": True,
                                "help_text": "默认递归同步根部门及全部子部门成员；关闭后只同步该部门直属成员。",
                            },
                        ],
                    }
                ],
                "available_external_fields": ["userid", "name", "email", "mobile", "department_ids"],
            },
            "im_notification_form": {
                "title": "IM 通知配置",
                "groups": [
                    {
                        "key": "send",
                        "title": "发送配置",
                        "fields": [
                            {"key": "mapping_strategy", "label": "映射策略", "field_type": "select", "required": True},
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
                "adapter_path": "apps.system_mgmt.providers.adapters.wecom.WeComLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "扫码授权地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.work.weixin.qq.com/wwopen/sso/qrConnect",
                        "reset_capabilities": ["login_auth"],
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "用户身份地址",
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
                "adapter_path": "apps.system_mgmt.providers.adapters.wecom.WeComUserSyncAdapter",
                "connection_template": [
                    {
                        "key": "user_sync_departments_url",
                        "label": "部门地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/department/list",
                        "reset_capabilities": ["user_sync"],
                    },
                    {
                        "key": "user_sync_users_url",
                        "label": "成员地址",
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
                "adapter_path": "apps.system_mgmt.providers.adapters.wecom.WeComIMNotificationAdapter",
                "connection_template": [
                    {
                        "key": "im_notification_users_url",
                        "label": "成员地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/user/list",
                        "reset_capabilities": ["im_notification"],
                    },
                    {
                        "key": "im_notification_send_message_url",
                        "label": "应用消息地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                        "reset_capabilities": ["im_notification"],
                    },
                ],
                "business_template": "im_notification_form",
            },
        ],
    }
)
