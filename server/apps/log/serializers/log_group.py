import uuid
from rest_framework import serializers
from apps.log.models.log_group import LogGroup, LogGroupOrganization, SearchCondition


class LogGroupSerializer(serializers.ModelSerializer):
    # 使用 ListField 处理输入，SerializerMethodField 处理输出
    organizations = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="关联的组织ID列表"
    )

    # ID字段改为可选，支持自动生成UUID
    id = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=200,
        help_text="日志分组ID，如不提供将自动生成UUID"
    )

    class Meta:
        model = LogGroup
        fields = ["id", "name", "description", "rule", "created_by", "created_at", "organizations"]
        read_only_fields = ["created_by", "created_at"]

    def to_representation(self, instance):
        """自定义输出格式，在输出时获取组织信息"""
        data = super().to_representation(instance)
        # 获取关联的组织ID列表
        data['organizations'] = list(
            LogGroupOrganization.objects.filter(log_group=instance)
            .values_list('organization', flat=True)
        )
        return data

    def create(self, validated_data):
        # 如果没有提供ID，自动生成UUID
        if 'id' not in validated_data or not validated_data['id']:
            validated_data['id'] = str(uuid.uuid4())

        organizations = validated_data.pop('organizations', [])
        log_group = super().create(validated_data)

        # 创建组织关联
        if organizations:
            LogGroupOrganization.objects.bulk_create(
                [LogGroupOrganization(log_group=log_group, organization=org_id)
                 for org_id in organizations],
                ignore_conflicts=True
            )

        return log_group

    def update(self, instance, validated_data):
        # 在更新时，移除ID字段，防止主键被修改
        validated_data.pop('id', None)
        organizations = validated_data.pop('organizations', None)
        log_group = super().update(instance, validated_data)

        # 更新组织关联
        if organizations is not None:
            LogGroupOrganization.objects.filter(log_group=log_group).delete()
            LogGroupOrganization.objects.bulk_create(
                [LogGroupOrganization(log_group=log_group, organization=org_id)
                 for org_id in organizations],
                ignore_conflicts=True
            )

        return log_group

    def validate_organizations(self, value):
        """验证组织ID列表"""
        if not isinstance(value, list):
            raise serializers.ValidationError("必须是一个列表")

        if not all(isinstance(org_id, int) for org_id in value):
            raise serializers.ValidationError("列表中的元素必须是整数")

        return value


class SearchConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchCondition
        fields = [
            "id", "name", "condition", "organization",
            "created_by", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "organization", "created_by", "created_at", "updated_at"]

    def validate_condition(self, value):
        """验证搜索条件配置"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("搜索条件配置必须是字典格式")
        
        # 验证必要字段
        if 'query' not in value:
            raise serializers.ValidationError("搜索条件配置中必须包含query字段")
        
        if 'log_groups' not in value:
            raise serializers.ValidationError("搜索条件配置中必须包含log_groups字段")
        
        # 验证日志分组是否存在
        log_groups = value.get('log_groups', [])
        if not isinstance(log_groups, list):
            raise serializers.ValidationError("log_groups必须是列表格式")
        
        if log_groups:
            existing_groups = LogGroup.objects.filter(id__in=log_groups).values_list('id', flat=True)
            invalid_groups = set(log_groups) - set(existing_groups)
            if invalid_groups:
                raise serializers.ValidationError(f"以下日志分组不存在: {', '.join(invalid_groups)}")
        
        return value
