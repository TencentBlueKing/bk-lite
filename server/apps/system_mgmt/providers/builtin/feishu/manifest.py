from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "feishu",
        "base_connection_adapter_key": "feishu.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.FeishuBaseConnectionAdapter",
        "name": "Feishu",
        "description": "Built-in Feishu integration provider for Phase 1.",
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
                                "placeholder": "cli_xxx",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                            {
                                "key": "app_secret",
                                "label": "App Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "reset_capabilities": ["login_auth", "user_sync", "im_notification", "im_group"],
                            },
                        ],
                    },
                    {
                        "key": "endpoints",
                        "title": "Public endpoints",
                        "fields": [
                            {
                                "key": "tenant_access_token_url",
                                "label": "Tenant access token URL",
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
                            {
                                "key": "default_group_name",
                                "label": "Default user group name",
                                "field_type": "string",
                                "required": False,
                            },
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "open_id", "name", "email", "mobile"],
                "default_external_match_field": "user_id",
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
                                "key": "department_id_type",
                                "label": "Department ID type",
                                "field_type": "select",
                                "required": True,
                                "default": "department_id",
                                "options": [
                                    {"value": "department_id", "label": "department_id"},
                                    {"value": "open_department_id", "label": "open_department_id"}, 
                                ],
                            },
                            {
                                "key": "user_id_type",
                                "label": "User ID type",
                                "field_type": "select",
                                "required": True,
                                "default": "user_id",
                                "options": [
                                    {"value": "user_id", "label": "user_id"},
                                    {"value": "open_id", "label": "open_id"},
                                    {"value": "union_id", "label": "union_id"},
                                ],
                            },
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "open_id", "name", "email", "mobile", "department_ids"],
            },
            "im_notification_form": {
                "title": "IM notification",
                "groups": [
                    {
                        "key": "send",
                        "title": "Send settings",
                        "fields": [
                            {
                                "key": "mapping_strategy",
                                "label": "Mapping strategy",
                                "field_type": "select",
                                "required": True,
                            },
                            {"key": "message_type", "label": "Message type", "field_type": "select", "required": True},
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
                "adapter_path": "adapters.login_auth.FeishuLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "login_auth_authorize_url",
                        "label": "Authorization URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
                    },
                    {
                        "key": "login_auth_access_token_url",
                        "label": "Access token URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/authen/v1/access_token",
                    },
                    {
                        "key": "login_auth_user_info_url",
                        "label": "User info URL",
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
                "adapter_path": "adapters.user_sync.FeishuUserSyncAdapter",
                "connection_template": [
                    {
                        "key": "user_sync_scopes_url",
                        "label": "Authorized scopes URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/scopes",
                    },
                    {
                        "key": "user_sync_departments_batch_url",
                        "label": "Department batch query URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/departments/batch",
                    },
                    {
                        "key": "user_sync_departments_url",
                        "label": "Department URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children",
                    },
                    {
                        "key": "user_sync_users_url",
                        "label": "User URL",
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
                "adapter_path": "adapters.im_notification.FeishuIMNotificationAdapter",
                "connection_template": [
                    {
                        "key": "im_notification_users_url",
                        "label": "User URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/contact/v3/users",
                    },
                    {
                        "key": "im_notification_send_message_url",
                        "label": "Send message URL",
                        "field_type": "string",
                        "required": False,
                        "default": "https://open.feishu.cn/open-apis/im/v1/messages",
                    },
                ],
                "business_template": "im_notification_form",
            },
            {
                "key": "im_group",
                "name": "IM Group",
                "description": "Feishu group collaboration capability.",
                "adapter_key": "feishu.im_group",
                "adapter_path": "adapters.im_group.FeishuIMGroupAdapter",
                "connection_template": [],
            },
        ],
    }
)
