from apps.system_mgmt.providers.schemas import ProviderManifest

PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "example_channel_template",
        "name": "Example Channel",
        "description": "Example notification channel pack. It does not deliver messages.",
        "instance_templates": {
            "connection": {
                "title": "Connection",
                "groups": [
                    {
                        "key": "main",
                        "title": "Main",
                        "fields": [
                            {
                                "key": "endpoint",
                                "label": "Endpoint",
                                "field_type": "string",
                                "required": True,
                            },
                            {
                                "key": "api_secret",
                                "label": "API Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                            },
                            {
                                "key": "template_id",
                                "label": "Template ID",
                                "field_type": "string",
                                "required": True,
                            },
                        ],
                    }
                ],
            }
        },
        "capabilities": [
            {
                "key": "notification_channel",
                "name": "Notify",
                "adapter_key": "example_channel_template.send",
                "adapter_path": "adapters.send.ExampleChannelSendAdapter",
                "delivery": "template",
                "parameter_mode": "named",
            }
        ],
    }
)
