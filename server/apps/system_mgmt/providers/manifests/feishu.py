from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "feishu",
        "name": "Feishu",
        "description": "Built-in Feishu integration provider for Phase 1.",
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
                                "placeholder": "cli_xxx",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                            {
                                "key": "app_secret",
                                "label": "App Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification"],
                            },
                        ],
                    },
                    {
                        "key": "endpoints",
                        "title": "公共接口",
                        "fields": [
                            {
                                "key": "tenant_access_token_url",
                                "label": "租户访问令牌地址",
                                "field_type": "string",
                                "required": False,
                                "default": "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                            },
                        ],
                    },
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
                            {
                                "key": "unmatched_user_action",
                                "label": "未匹配用户处理方式",
                                "field_type": "select",
                                "required": True,
                            },
                            {
                                "key": "default_group_name",
                                "label": "默认用户组名称",
                                "field_type": "string",
                                "required": False,
                            },
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "open_id", "name", "email", "mobile"],
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
                            },
                            {
                                "key": "department_id_type",
                                "label": "部门 ID 类型",
                                "field_type": "select",
                                "required": True,
                                "default": "open_department_id",
                                "options": [
                                    {"value": "open_department_id", "label": "open_department_id"},
                                    {"value": "department_id", "label": "department_id"},
                                ],
                            },
                            {
                                "key": "user_id_type",
                                "label": "用户 ID 类型",
                                "field_type": "select",
                                "required": True,
                                "default": "open_id",
                                "options": [
                                    {"value": "open_id", "label": "open_id"},
                                    {"value": "union_id", "label": "union_id"},
                                    {"value": "user_id", "label": "user_id"},
                                ],
                            },
                            {
                                "key": "fetch_child",
                                "label": "递归拉取子部门",
                                "field_type": "boolean",
                                "required": False,
                                "default": True,
                            },
                            {
                                "key": "status",
                                "label": "用户状态筛选",
                                "field_type": "select",
                                "required": True,
                                "default": "active",
                                "options": [
                                    {"value": "active", "label": "在职"},
                                    {"value": "all", "label": "全部"},
                                ],
                            },
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "open_id", "name", "email", "mobile", "department_ids"],
            },
            "im_notification_form": {
                "title": "IM 通知配置",
                "groups": [
                    {
                        "key": "send",
                        "title": "发送配置",
                        "fields": [
                            {
                                "key": "mapping_strategy",
                                "label": "映射策略",
                                "field_type": "select",
                                "required": True,
                            },
                            {"key": "message_type", "label": "消息类型", "field_type": "select", "required": True},
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "open_id", "name", "email", "mobile"],
                "matchable_fields": ["email", "mobile", "user_id", "open_id"],
                "receivable_fields": ["user_id", "open_id"],
                "identity_fields": ["user_id", "open_id"],
                "default_external_match_field": "email",
                "default_external_receive_field": "user_id",
            },
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "Feishu login authentication capability.",
                "adapter_key": "feishu.login_auth",
                "adapter_path": "apps.system_mgmt.providers.adapters.feishu.FeishuLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "授权地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
                    },
                    {
                        "key": "login_auth_access_token_url",
                        "label": "访问令牌地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/authen/v1/access_token",
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "用户信息地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/authen/v1/user_info",
                    },
                ],
                "business_template": "login_auth_form",
            },
            {
                "key": "user_sync",
                "name": "User Sync",
                "description": "Feishu user synchronization capability.",
                "adapter_key": "feishu.user_sync",
                "adapter_path": "apps.system_mgmt.providers.adapters.feishu.FeishuUserSyncAdapter",
                "connection_template": [
                    {
                        "key": "user_sync_departments_url",
                        "label": "部门接口地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children",
                    },
                    {
                        "key": "user_sync_users_url",
                        "label": "用户接口地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/users",
                    },
                ],
                "business_template": "user_sync_form",
            },
            {
                "key": "im_notification",
                "name": "IM Notification",
                "description": "Feishu per-user IM notification capability.",
                "adapter_key": "feishu.im_notification",
                "adapter_path": "apps.system_mgmt.providers.adapters.feishu.FeishuIMNotificationAdapter",
                "connection_template": [
                    {
                        "key": "im_notification_users_url",
                        "label": "用户接口地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/users",
                    },
                    {
                        "key": "im_notification_send_message_url",
                        "label": "发送消息接口地址",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/im/v1/messages",
                    },
                ],
                "business_template": "im_notification_form",
            },
        ],
    }
)
