from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "ad",
        "name": "Active Directory",
        "description": "Built-in Active Directory integration provider for login auth and user sync.",
        "instance_templates": {
            "base_connection": {
                "title": "基础连接",
                "groups": [
                    {
                        "key": "connection",
                        "title": "连接配置",
                        "fields": [
                            {
                                "key": "connection_url",
                                "label": "服务器 IP",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "127.0.0.1",
                                "help_text": "仅填写服务器 IP 地址，协议和默认端口由系统按 SSL 配置自动补全。",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "ssl_encryption",
                                "label": "SSL加密方式",
                                "field_type": "select",
                                "required": True,
                                "default": "none",
                                "options": [
                                    {"value": "none", "label": "None"},
                                    {"value": "ssl", "label": "SSL"},
                                ],
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "timeout",
                                "label": "超时时间",
                                "field_type": "number",
                                "required": True,
                                "default": 10,
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "bind_dn",
                                "label": "连接账号",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "administrator",
                                "help_text": "建议填写 UPN（如 administrator@corp.example.com）或完整 DN（如 CN=svc_ad,OU=Service,DC=corp,DC=example,DC=com），避免依赖裸用户名的域解析。",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "bind_password",
                                "label": "连接密码",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "mask_strategy": "full",
                                "reset_capabilities": ["login_auth", "user_sync"],
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
                "available_external_fields": [
                    "sAMAccountName",
                    "userPrincipalName",
                    "displayName",
                    "mail",
                    "telephoneNumber",
                    "distinguishedName",
                ],
                "default_external_match_field": "sAMAccountName",
            },
            "user_sync_form": {
                "title": "用户同步配置",
                "groups": [
                    {
                        "key": "scope",
                        "title": "同步范围",
                        "fields": [
                            {
                                "key": "root_dn",
                                "label": "同步起始目录",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "OU=Users,DC=example,DC=com",
                                "input_mode": "manual_input",
                            },
                            {
                                "key": "user_object_class",
                                "label": "用户对象类",
                                "field_type": "string",
                                "required": False,
                                "default": "user",
                                "placeholder": "user",
                                "help_text": "指定 AD/LDAP 中用户账号的类别，常用user类型，若无需要，保持默认即可。",
                            },
                            {
                                "key": "user_filter",
                                "label": "用户对象过滤",
                                "field_type": "textarea",
                                "required": False,
                                "default": "(&(objectCategory=Person)(sAMAccountName=*))",
                                "placeholder": "(&(objectCategory=Person)(sAMAccountName=*))",
                                "help_text": "在用户账号基础上，再加一层筛选，决定具体拉哪些人，若无需要，保持默认即可。",
                            },
                            {
                                "key": "organization_object_class",
                                "label": "组织架构类",
                                "field_type": "string",
                                "required": False,
                                "default": "organizationalUnit",
                                "placeholder": "organizationalUnit",
                                "help_text": "指定 AD/LDAP 中用来表示组织架构/部门的对象类，AD系统中默认值为organizationalUnit，若无需要，保持默认即可。",
                            },
                        ],
                    }
                ],
                "available_external_fields": [
                    "sAMAccountName",
                    "userPrincipalName",
                    "displayName",
                    "mail",
                    "telephoneNumber",
                    "distinguishedName",
                    "department_ids",
                ],
            },
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "Active Directory login authentication capability.",
                "adapter_key": "ad.login_auth",
                "adapter_path": "apps.system_mgmt.providers.adapters.ad.ADLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "base_dn",
                        "label": "登录搜索 Base DN",
                        "field_type": "string",
                        "required": True,
                        "placeholder": "DC=example,DC=com",
                        "help_text": (
                            "登录认证时 LDAP 搜索的根目录，决定可在哪个 OU/子树范围内查找登录用户。"
                            "与「同步起始目录 (root_dn)」是不同字段：root_dn 限制同步范围，base_dn 限制登录搜索范围。"
                        ),
                    },
                    {
                        "key": "login_auth_identity_field",
                        "label": "登录账号类型",
                        "field_type": "select",
                        "required": True,
                        "default": "sAMAccountName",
                        "options": [
                            {"value": "sAMAccountName", "label": "用户名（sAMAccountName）"},
                            {"value": "userPrincipalName", "label": "邮箱账号（userPrincipalName）"},
                        ],
                    }
                ],
                "business_template": "login_auth_form",
            },
            {
                "key": "user_sync",
                "name": "User Sync",
                "description": "Active Directory user synchronization capability.",
                "adapter_key": "ad.user_sync",
                "adapter_path": "apps.system_mgmt.providers.adapters.ad.ADUserSyncAdapter",
                "connection_template": [],
                "business_template": "user_sync_form",
            },
        ],
    }
)
