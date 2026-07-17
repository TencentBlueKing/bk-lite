from types import SimpleNamespace
from copy import deepcopy

from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.providers import RuntimeApplicationService, get_provider_registry
from apps.system_mgmt.models import (
    Group,
    IntegrationInstanceStatusChoices,
    UserSyncRun,
    UserSyncSource,
)
from apps.system_mgmt.services import user_sync_service
from apps.system_mgmt.services.capability_contract_service import (
    CapabilityContractError,
    validate_user_sync_contract,
    validate_user_sync_schedule_config,
)
from apps.system_mgmt.services.user_sync_service import (
    get_user_sync_root_department_input_mode,
    get_user_sync_root_scope_field,
    is_root_group_name_reserved,
)
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


PASSWORD_INIT_MODES = {"none", "uniform", "random"}


def validate_platform_config(platform_config, existing_platform_config=None):
    if platform_config is None:
        return None
    if not isinstance(platform_config, dict):
        raise serializers.ValidationError({"platform_config": "Platform config must be an object"})

    normalized_config = deepcopy(platform_config)
    password_init = normalized_config.get("password_init")
    if password_init is None:
        return normalized_config
    if not isinstance(password_init, dict):
        raise serializers.ValidationError({"platform_config": "password_init must be an object"})

    mode = password_init.get("mode")
    if mode is None:
        return normalized_config
    if mode not in PASSWORD_INIT_MODES:
        raise serializers.ValidationError({"platform_config": f"Unsupported password_init mode: {mode}"})
    if mode == "none":
        password_init.pop("uniform_password", None)
        password_init.pop("uniform_password_configured", None)
        return normalized_config

    if not password_init.get("email_channel_id"):
        raise serializers.ValidationError({"platform_config": "email_channel_id is required for password_init"})
    if mode != "uniform":
        password_init.pop("uniform_password", None)
        password_init.pop("uniform_password_configured", None)
        return normalized_config

    raw_password = password_init.get("uniform_password")
    previous_password = (
        ((existing_platform_config or {}).get("password_init") or {}).get("uniform_password")
    )
    password_init.pop("uniform_password_configured", None)
    if not raw_password:
        if previous_password:
            password_init["uniform_password"] = previous_password
            return normalized_config
        raise serializers.ValidationError({"platform_config": "uniform_password is required for password_init"})

    is_valid, error_message = PasswordValidator.validate_password(raw_password)
    if not is_valid:
        raise serializers.ValidationError({"platform_config": error_message or "密码强度不够"})
    password_init["uniform_password"] = encrypt_for_vault(raw_password)
    return normalized_config


class UserSyncRunSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = UserSyncRun
        fields = "__all__"


class UserSyncSourceSerializer(UsernameSerializer):
    integration_instance_name = serializers.SerializerMethodField()
    latest_run = serializers.SerializerMethodField()
    root_scope_field = serializers.SerializerMethodField()

    class Meta:
        model = UserSyncSource
        fields = "__all__"

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""

    def get_latest_run(self, obj):
        latest_run = getattr(obj, "_prefetched_latest_run", None)
        if isinstance(latest_run, list):
            latest_run = latest_run[0] if latest_run else None
        if latest_run is None:
            latest_run = obj.runs.order_by("-started_at", "-id").first()
        return UserSyncRunSerializer(latest_run).data if latest_run else None

    def get_root_scope_field(self, obj):
        provider_key = obj.integration_instance.provider_key if obj.integration_instance_id else ""
        return get_user_sync_root_scope_field(provider_key)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        platform_config = deepcopy(data.get("platform_config") or {})
        password_init = platform_config.get("password_init")
        if isinstance(password_init, dict) and password_init.get("mode") == "uniform":
            password_init["uniform_password_configured"] = bool(password_init.pop("uniform_password", None))
        data["platform_config"] = platform_config
        return data

    def validate(self, attrs):
        integration_instance = attrs.get("integration_instance") or getattr(self.instance, "integration_instance", None)
        if integration_instance is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance is required"})
        if (
            not integration_instance.enabled
            or integration_instance.status != IntegrationInstanceStatusChoices.READY
            or integration_instance.capability_status.get("user_sync") != IntegrationInstanceStatusChoices.READY
        ):
            raise serializers.ValidationError({"integration_instance": "Integration instance user_sync capability is not ready"})

        root_group_name = attrs.get("root_group_name") or getattr(self.instance, "root_group_name", "")
        if not root_group_name:
            raise serializers.ValidationError({"root_group_name": "Root group name is required"})

        current_source_id = getattr(self.instance, "id", None)
        if is_root_group_name_reserved(root_group_name, current_source_id=current_source_id):
            raise serializers.ValidationError({"root_group_name": "Root group name is already used by another sync source"})

        existing_root_group = Group.objects.filter(parent_id=0, name=root_group_name).first()
        if existing_root_group:
            if current_source_id is None:
                raise serializers.ValidationError({"root_group_name": "Root group name is already used by another sync source"})
            if existing_root_group.sync_source_id not in (None, current_source_id):
                raise serializers.ValidationError({"root_group_name": "Root group name is already used by another sync source"})

        raw_business_config = attrs.get("business_config")
        business_config = dict(getattr(self.instance, "business_config", None) or {})
        if raw_business_config:
            business_config.update(raw_business_config)

        if "platform_config" in attrs:
            attrs["platform_config"] = validate_platform_config(
                attrs["platform_config"],
                getattr(self.instance, "platform_config", None),
            )

        field_mapping = attrs.get("field_mapping")
        if self.instance is None or "field_mapping" in attrs:
            username_mapping = (
                str(field_mapping.get("username") or "").strip() if isinstance(field_mapping, dict) else ""
            )
            if not username_mapping:
                raise serializers.ValidationError(
                    {"field_mapping": {"username": "Username mapping is required"}}
                )
        manifest = get_provider_registry().get(integration_instance.provider_key)
        if manifest is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance provider manifest is missing"})
        input_mode = get_user_sync_root_department_input_mode(integration_instance.provider_key)
        if input_mode == "manual_input":
            business_config.pop("department_id_type", None)
        if integration_instance.provider_key == "feishu":
            # Feishu fetch_child is now an implementation default, not user configuration.
            business_config.pop("fetch_child", None)
        try:
            validate_user_sync_contract(
                manifest,
                business_config=business_config,
                field_mapping=field_mapping,
                schedule_config=attrs.get("schedule_config"),
            )
        except CapabilityContractError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

        if self.instance:
            if "integration_instance" in attrs and attrs["integration_instance"].id != self.instance.integration_instance_id:
                raise serializers.ValidationError({"integration_instance": "Integration instance cannot be changed"})
            if "root_group_name" in attrs and attrs["root_group_name"] != self.instance.root_group_name:
                raise serializers.ValidationError({"root_group_name": "Root group name cannot be changed"})

        root_scope_field = get_user_sync_root_scope_field(integration_instance.provider_key)
        root_scope_value = str(business_config.get(root_scope_field) or "")
        if not root_scope_value:
            raise serializers.ValidationError({"business_config": "Root department is required"})

        if input_mode == "manual_input":
            business_config.pop("department_id_type", None)
            business_config[root_scope_field] = root_scope_value
        else:
            runtime_service = RuntimeApplicationService()
            department_result = runtime_service.execute(
                provider_key=integration_instance.provider_key,
                capability_key="user_sync",
                operation="list_departments",
                config=integration_instance.get_runtime_config(),
                source=SimpleNamespace(name=getattr(self.instance, "name", ""), business_config=business_config),
                business_config=business_config,
            )
            if not department_result.success:
                raise serializers.ValidationError({"business_config": department_result.summary})

            normalized_root_department_id = user_sync_service.normalize_root_department_selection(
                root_scope_value,
                department_result.payload,
            )
            valid_department_ids = user_sync_service.flatten_department_ids(department_result.payload.get("items") or [])
            valid_department_ids.add(str(department_result.payload.get("all_department_id") or ""))
            if normalized_root_department_id not in valid_department_ids:
                raise serializers.ValidationError({"business_config": "Selected root department is invalid"})
            business_config[root_scope_field] = normalized_root_department_id

        attrs["business_config"] = business_config
        return attrs

    def _validate_schedule_config(self, schedule_config):
        try:
            validate_user_sync_schedule_config(schedule_config, field="schedule_config")
        except CapabilityContractError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._sync_periodic_task(instance)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._sync_periodic_task(instance)
        return instance

    def _sync_periodic_task(self, instance: UserSyncSource):
        schedule_config = instance.schedule_config or {}
        if instance.enabled and schedule_config.get("mode") not in (None, "disabled"):
            instance.create_sync_periodic_task()
        else:
            instance.delete_sync_periodic_task()
