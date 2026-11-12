from rest_framework import serializers

from apps.itsm.models import Service, ServiceCatalog, Workflow


class ServiceCatalogSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = ServiceCatalog
        fields = ["id", "name", "parent_id", "order"]
        read_only_fields = ["id"]


class ServiceSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    version_id = serializers.IntegerField(source="workflow.current_version_id", read_only=True)
    catalog_id = serializers.IntegerField(allow_null=True, required=False)
    workflow_id = serializers.IntegerField(required=False)

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
        ]
        read_only_fields = ["id", "workflow_name", "version_id"]

    def validate(self, attrs):
        creating = self.instance is None
        if creating and not attrs.get("name"):
            raise serializers.ValidationError("请填写服务名称并选择流程")
        workflow_id = attrs.get("workflow_id")
        if creating and not workflow_id:
            raise serializers.ValidationError("请填写服务名称并选择流程")
        if workflow_id:
            workflow = Workflow.objects.filter(id=workflow_id).first()
            if workflow is None:
                raise serializers.ValidationError("流程不存在")
            if creating and workflow.current_version_id is None:
                raise serializers.ValidationError("流程还没有发布版本")
            attrs["workflow"] = workflow
        return attrs
