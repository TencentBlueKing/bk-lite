from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "example_integration",
        "name": "Example Integration",
        "description": "Example integration pack. It does not call an external service.",
        "base_connection_adapter_key": "example_integration.base_connection",
        "base_connection_adapter_path": "adapters.base_connection.ExampleBaseConnectionAdapter",
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "Credentials",
                        "fields": [
                            {
                                "key": "endpoint",
                                "label": "Endpoint",
                                "field_type": "string",
                                "required": True,
                            },
                            {
                                "key": "client_secret",
                                "label": "Client Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "reset_capabilities": ["login_auth"],
                            },
                        ],
                    }
                ],
            }
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "Example login authentication capability.",
                "adapter_key": "example_integration.login_auth",
                "adapter_path": "adapters.login_auth.ExampleLoginAuthAdapter",
            }
        ],
    }
)
