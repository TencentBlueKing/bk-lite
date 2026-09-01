from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "ad",
        "base_connection_adapter_key": "ad.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.ADBaseConnectionAdapter",
        "name": "Active Directory",
        "description": "Built-in Active Directory integration provider for login auth and user sync.",
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "connection",
                        "title": "Connection",
                        "fields": [
                            {
                                "key": "connection_url",
                                "label": "Server IP",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "127.0.0.1",
                                "help_text": "Enter the server IP only. Protocol and default port are filled in automatically based on SSL settings.",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "ssl_encryption",
                                "label": "SSL encryption",
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
                                "label": "Timeout",
                                "field_type": "number",
                                "required": True,
                                "default": 10,
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "bind_dn",
                                "label": "Bind account",
                                "field_type": "string",
                                "required": True,
                                "placeholder": "administrator",
                                "help_text": "Prefer a UPN (for example administrator@corp.example.com) or a full DN (for example CN=svc_ad,OU=Service,DC=corp,DC=example,DC=com). Avoid relying on a bare username for domain resolution.",
                                "reset_capabilities": ["login_auth", "user_sync"],
                            },
                            {
                                "key": "bind_password",
                                "label": "Bind password",
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
                "available_external_fields": [
                    "sAMAccountName",
                    "userPrincipalName",
                    "displayName",
                    "mail",
                    "telephoneNumber",
                    "mobile",
                    "mobilePhone",
                    "distinguishedName",
                ],
                "default_external_match_field": "sAMAccountName",
            },
            "user_sync_form": {
                "title": "User sync",
                "groups": [
                    {
                        "key": "scope",
                        "title": "Sync scope",
                        "fields": [
                            {
                                "key": "root_dns",
                                "label": "Sync pull DNs",
                                "field_type": "textarea",
                                "required": True,
                                "placeholder": "OU=BizA,DC=example,DC=com\nOU=BizC,DC=example,DC=com",
                                "help_text": (
                                    "One complete DN per line. "
                                    "With one DN, child organizations attach under this sync source's root group. "
                                    "With multiple OUs, each appears as its own organization under that root."
                                ),
                                "input_mode": "manual_input",
                            },
                            {
                                "key": "user_object_class",
                                "label": "User object class",
                                "field_type": "string",
                                "required": False,
                                "default": "user",
                                "placeholder": "user",
                                "help_text": "Object class for user accounts in AD/LDAP. The common value is user; keep the default unless you need a different class.",
                            },
                            {
                                "key": "user_filter",
                                "label": "User object filter",
                                "field_type": "textarea",
                                "required": False,
                                "default": "(&(objectCategory=Person)(sAMAccountName=*))",
                                "placeholder": "(&(objectCategory=Person)(sAMAccountName=*))",
                                "help_text": "Extra filter on user accounts that decides who is pulled. Keep the default unless you need a different filter.",
                            },
                            {
                                "key": "organization_object_class",
                                "label": "Organization object class",
                                "field_type": "string",
                                "required": False,
                                "default": "organizationalUnit",
                                "placeholder": "organizationalUnit",
                                "help_text": "Object class for organization/department entries in AD/LDAP. The AD default is organizationalUnit; keep it unless you need a different class.",
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
                    "mobile",
                    "mobilePhone",
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
                "adapter_path": "adapters.login_auth.ADLoginAuthAdapter",
                "connection_template": [
                    {
                        "key": "base_dn",
                        "label": "Login search Base DN",
                        "field_type": "string",
                        "required": True,
                        "placeholder": "DC=example,DC=com",
                        "help_text": (
                            "LDAP search root used during login. This is not the same as sync pull DNs (root_dns): "
                            "root_dns limits what is synced, base_dn limits where login search looks."
                        ),
                    },
                    {
                        "key": "login_auth_identity_field",
                        "label": "Login account type",
                        "field_type": "select",
                        "required": True,
                        "default": "sAMAccountName",
                        "options": [
                            {"value": "sAMAccountName", "label": "Username (sAMAccountName)"},
                            {"value": "userPrincipalName", "label": "Email account (userPrincipalName)"},
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
                "adapter_path": "adapters.user_sync.ADUserSyncAdapter",
                "connection_template": [],
                "business_template": "user_sync_form",
            },
        ],
    }
)
