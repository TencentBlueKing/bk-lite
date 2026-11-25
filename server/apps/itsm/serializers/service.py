from rest_framework import serializers

from apps.itsm.models import Service, ServiceCatalog, Workflow
from apps.itsm.services.service_assignment import (
    LEGACY_PRESET_MESSAGE,
    handler_group_members,
    has_legacy_preset_handlers,
    has_open_group_tickets,
    requires_handler_group,
)


class ServiceCatalogSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = ServiceCatalog
        fields = ["id", "name", "parent_id", "order"]
        read_only_fields = ["id"]

    def validate_parent_id(self, value):
        if value and not ServiceCatalog.objects.filter(id=value, domain=self.context.get("domain", "")).exists():
            raise serializers.ValidationError("父目录不存在")
        seen = {self.instance.id} if self.instance else set()
        parent = value
        while parent:
            if parent in seen:
                raise serializers.ValidationError("目录不能循环嵌套")
            seen.add(parent)
            parent = ServiceCatalog.objects.filter(id=parent, domain=self.context.get("domain", "")).values_list("parent_id", flat=True).first()
        return value


class ServiceSerializer(serializers.ModelSerializer):
    handler_group = serializers.IntegerField(source="handler_group_id", min_value=1, required=False, allow_null=True)
    requires_handler_group = serializers.SerializerMethodField()

    def get_requires_handler_group(self, service):
        if "group_workflows" in self.context:
            return service.workflow_id in self.context["group_workflows"]
        version = service.workflow.current_version
        return bool(version and requires_handler_group(version.design))

    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    version_id = serializers.IntegerField(source="workflow.current_version_id", read_only=True)
    catalog_id = serializers.IntegerField(allow_null=True, required=False)
    workflow_id = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "catalog_id",
            "workflow_id",
            "workflow_name",
            "version_id",
            "description",
            "is_hot",
            "is_enabled",
            "handler_group",
            "requires_handler_group",
            "visibility",
            "visible_users",
            "visible_groups",
        ]
        read_only_fields = ["id", "workflow_name", "version_id"]

    def validate(self, attrs):
        from apps.itsm.models import HandlerGroup
        from apps.system_mgmt.models import User

        domain = self.context.get("domain", "")
        for field, model, lookup in [("visible_users", User, "username"), ("visible_groups", HandlerGroup, "id")]:
            if field in attrs:
                values = attrs[field]
                if not isinstance(values, list) or len(values) > 500 or any(isinstance(v, (dict, list, bool)) for v in values):
                    raise serializers.ValidationError({field: "请选择有效的用户或组"})
                try:
                    found = model.objects.filter(domain=domain, **{lookup + "__in": values}).count()
                    valid = len(set(values)) == found
                except (ValueError, TypeError):
                    valid = False
                if not valid:
                    raise serializers.ValidationError({field: "用户或组不存在于当前域"})
        creating = self.instance is None
        if creating and not attrs.get("name"):
            raise serializers.ValidationError("请填写服务名称并选择流程")
        if attrs.get("catalog_id"):
            if not ServiceCatalog.objects.filter(id=attrs["catalog_id"], domain=self.context.get("domain", "")).exists():
                raise serializers.ValidationError("目录不存在")
        workflow_id = attrs.get("workflow_id")
        if creating and not workflow_id:
            raise serializers.ValidationError("请填写服务名称并选择流程")
        if workflow_id:
            workflow = Workflow.objects.filter(id=workflow_id, domain=self.context.get("domain", "")).first()
            if workflow is None:
                raise serializers.ValidationError("流程不存在")
            if creating and workflow.current_version_id is None:
                raise serializers.ValidationError("流程还没有发布版本")
            attrs["workflow"] = workflow
        workflow = attrs.get("workflow") or (self.instance.workflow if self.instance else None)
        version = workflow.current_version if workflow else None
        enabled = attrs.get("is_enabled", self.instance.is_enabled if self.instance else True)
        group_id = attrs.get("handler_group_id", self.instance.handler_group_id if self.instance else None)
        if self.instance and (workflow.pk != self.instance.workflow_id or (self.instance.handler_group_id and group_id is None)):
            if has_open_group_tickets(self.instance):
                raise serializers.ValidationError("服务有依赖处理组的在办工单，请保留当前流程和处理组绑定")
        if enabled and (version is None or not version.is_published):
            raise serializers.ValidationError("请先发布服务流程，再启用服务")
        if enabled and version and has_legacy_preset_handlers(version):
            raise serializers.ValidationError(LEGACY_PRESET_MESSAGE)
        if (enabled and version and requires_handler_group(version.design)) or attrs.get("handler_group_id") is not None:
            if not group_id or not handler_group_members(group_id, domain):
                raise serializers.ValidationError({"handler_group": "请选择本域包含有效成员的处理组"})
        return attrs


class PortalServiceSerializer(ServiceSerializer):
    class Meta(ServiceSerializer.Meta):
        fields = ["id", "name", "catalog_id", "workflow_id", "workflow_name", "version_id", "description", "is_hot", "is_enabled"]
