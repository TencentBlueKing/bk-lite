from apps.system_mgmt.models import IntegrationInstanceStatusChoices


USER_SYNC_PLATFORM_FIELDS = {"username", "display_name", "email", "phone"}
SCHEDULE_SYNC_TIME_ERROR = "Schedule sync_time must be HH:mm"


class CapabilityContractError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _business_template_fields(template) -> set[str]:
    if template is None:
        return set()
    return {field.key for group in template.groups for field in group.fields}


def validate_integration_capability_state(manifest, capability_status=None, capability_enabled=None) -> dict[str, str]:
    allowed_capabilities = {capability.key for capability in manifest.capabilities}
    errors = {}

    if capability_status is not None:
        if not isinstance(capability_status, dict):
            errors["capability_status"] = "Capability status must be an object"
        else:
            invalid_status_keys = set(capability_status.keys()) - allowed_capabilities
            valid_status_values = {choice.value for choice in IntegrationInstanceStatusChoices}
            invalid_status_values = {
                key: value for key, value in capability_status.items() if value not in valid_status_values
            }
            if invalid_status_keys:
                errors["capability_status"] = f"Invalid capability keys: {', '.join(sorted(invalid_status_keys))}"
            elif invalid_status_values:
                errors["capability_status"] = (
                    f"Invalid capability status values: {', '.join(sorted(invalid_status_values.keys()))}"
                )

    if capability_enabled is not None:
        if not isinstance(capability_enabled, dict):
            errors["capability_enabled"] = "Capability enabled must be an object"
        else:
            invalid_enabled_keys = set(capability_enabled.keys()) - allowed_capabilities
            invalid_enabled_values = {
                key: value for key, value in capability_enabled.items() if not isinstance(value, bool)
            }
            if invalid_enabled_keys:
                errors["capability_enabled"] = f"Invalid capability keys: {', '.join(sorted(invalid_enabled_keys))}"
            elif invalid_enabled_values:
                errors["capability_enabled"] = (
                    f"Capability enabled values must be booleans: {', '.join(sorted(invalid_enabled_values.keys()))}"
                )

    return errors


def validate_user_sync_contract(manifest, business_config=None, field_mapping=None, schedule_config=None):
    _validate_object("business_config", business_config, required=False)
    _validate_object("field_mapping", field_mapping, required=False)
    validate_schedule_config(schedule_config, field="schedule_config")

    template_key = (manifest.get_capability("user_sync").business_template if manifest.get_capability("user_sync") else "")
    template = manifest.business_templates.get(template_key) if template_key else None

    if business_config is not None and template is not None:
        allowed_business_fields = _business_template_fields(template)
        invalid_business_fields = set(business_config.keys()) - allowed_business_fields
        if invalid_business_fields:
            raise CapabilityContractError(
                "business_config",
                f"Unsupported user_sync business config fields: {', '.join(sorted(invalid_business_fields))}",
            )

    if field_mapping is None:
        return

    invalid_platform_fields = set(field_mapping.keys()) - USER_SYNC_PLATFORM_FIELDS
    if invalid_platform_fields:
        raise CapabilityContractError(
            "field_mapping",
            f"Unsupported user_sync platform fields: {', '.join(sorted(invalid_platform_fields))}",
        )

    allowed_external_fields = set(template.available_external_fields if template else [])
    invalid_external_fields = {
        value for value in field_mapping.values() if value and value not in allowed_external_fields
    }
    if invalid_external_fields:
        raise CapabilityContractError(
            "field_mapping",
            f"Unsupported user_sync external fields: {', '.join(sorted(invalid_external_fields))}",
        )


def validate_im_notification_contract(manifest, external_match_field: str, external_receive_field: str, schedule_config=None):
    validate_schedule_config(schedule_config, field="schedule_config")
    template_key = (
        manifest.get_capability("im_notification").business_template
        if manifest.get_capability("im_notification")
        else ""
    )
    template = manifest.business_templates.get(template_key) if template_key else None
    if template is None:
        raise CapabilityContractError("integration_instance", "Integration instance im_notification template is missing")

    if external_match_field not in template.matchable_fields:
        raise CapabilityContractError(
            "external_match_field",
            "External match field is not supported by the provider manifest",
        )
    if external_receive_field not in template.receivable_fields:
        raise CapabilityContractError(
            "external_receive_field",
            "External receive field is not supported by the provider manifest",
        )


def validate_schedule_config(schedule_config, *, field: str):
    if schedule_config is None:
        return
    if not isinstance(schedule_config, dict):
        raise CapabilityContractError(field, "Schedule config must be an object")

    enabled = schedule_config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise CapabilityContractError(field, "Schedule enabled must be a boolean")
    if not enabled:
        return

    sync_time = schedule_config.get("sync_time")
    if not isinstance(sync_time, str):
        raise CapabilityContractError(field, SCHEDULE_SYNC_TIME_ERROR)
    parts = sync_time.split(":")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        raise CapabilityContractError(field, SCHEDULE_SYNC_TIME_ERROR)
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        raise CapabilityContractError(field, SCHEDULE_SYNC_TIME_ERROR) from None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise CapabilityContractError(field, SCHEDULE_SYNC_TIME_ERROR)


def _validate_object(field: str, value, *, required: bool):
    if value is None and not required:
        return
    if not isinstance(value, dict):
        raise CapabilityContractError(field, f"{field.replace('_', ' ').title()} must be an object")
