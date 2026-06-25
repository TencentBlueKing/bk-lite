from types import SimpleNamespace

from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.models import (
    Group,
    IntegrationInstanceStatusChoices,
    UserSyncRun,
    UserSyncSource,
)
from apps.system_mgmt.services import user_sync_service
from apps.system_mgmt.services.user_sync_service import (
    get_user_sync_root_department_input_mode,
    is_root_group_name_reserved,
)


class UserSyncRunSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = UserSyncRun
        fields = "__all__"


class UserSyncSourceSerializer(UsernameSerializer):
    integration_instance_name = serializers.SerializerMethodField()
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = UserSyncSource
        fields = "__all__"

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""

    def get_latest_run(self, obj):
        latest_run = getattr(obj, "_prefetched_latest_run", None)
        if latest_run is None:
            latest_run = obj.runs.order_by("-started_at", "-id").first()
        return UserSyncRunSerializer(latest_run).data if latest_run else None

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
        if raw_business_config is not None and not isinstance(raw_business_config, dict):
            raise serializers.ValidationError({"business_config": "Business config must be an object"})
        business_config = dict(getattr(self.instance, "business_config", None) or {})
        if raw_business_config:
            business_config.update(raw_business_config)

        field_mapping = attrs.get("field_mapping")
        if field_mapping is not None and not isinstance(field_mapping, dict):
            raise serializers.ValidationError({"field_mapping": "Field mapping must be an object"})

        schedule_config = attrs.get("schedule_config")
        if schedule_config is not None and not isinstance(schedule_config, dict):
            raise serializers.ValidationError({"schedule_config": "Schedule config must be an object"})

        if self.instance:
            if "integration_instance" in attrs and attrs["integration_instance"].id != self.instance.integration_instance_id:
                raise serializers.ValidationError({"integration_instance": "Integration instance cannot be changed"})
            if "root_group_name" in attrs and attrs["root_group_name"] != self.instance.root_group_name:
                raise serializers.ValidationError({"root_group_name": "Root group name cannot be changed"})

        root_department_id = str(business_config.get("root_department_id") or "")
        if not root_department_id:
            raise serializers.ValidationError({"business_config": "Root department is required"})

        input_mode = get_user_sync_root_department_input_mode(integration_instance.provider_key)
        if input_mode == "manual_input":
            business_config.pop("department_id_type", None)
            business_config["root_department_id"] = root_department_id
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
                root_department_id,
                department_result.payload,
            )
            valid_department_ids = user_sync_service.flatten_department_ids(department_result.payload.get("items") or [])
            valid_department_ids.add(str(department_result.payload.get("all_department_id") or ""))
            if normalized_root_department_id not in valid_department_ids:
                raise serializers.ValidationError({"business_config": "Selected root department is invalid"})
            business_config["root_department_id"] = normalized_root_department_id

        attrs["business_config"] = business_config
        return attrs

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
        if instance.enabled and schedule_config.get("enabled") and schedule_config.get("sync_time"):
            instance.create_sync_periodic_task()
        else:
            instance.delete_sync_periodic_task()
