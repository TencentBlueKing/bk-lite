# -- coding: utf-8 --
# @File: field_group.py
# @Time: 2026/1/4
# @Author: windyzhao

from rest_framework import serializers

from apps.cmdb.models.field_group import FieldGroup


class FieldGroupSerializer(serializers.ModelSerializer):
    """字段分组序列化器"""

    class Meta:
        model = FieldGroup
        fields = (
            "id",
            "model_id",
            "group_name",
            "order",
            "is_collapsed",
            "description",
            "attr_orders",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class FieldGroupCreateSerializer(serializers.Serializer):
    """创建分组序列化器"""

    group_name = serializers.CharField(
        required=True,
        max_length=200,
        error_messages={
            "required": "分组名称不能为空",
            "blank": "分组名称不能为空",
            "max_length": "分组名称不能超过200个字符",
        },
    )
    description = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )
    is_collapsed = serializers.BooleanField(required=False, default=False)


class FieldGroupUpdateSerializer(serializers.Serializer):
    """更新分组序列化器"""

    group_name = serializers.CharField(
        required=True,
        max_length=200,
        error_messages={
            "required": "分组名称不能为空",
            "blank": "分组名称不能为空",
            "max_length": "分组名称不能超过200个字符",
        },
    )
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )
    is_collapsed = serializers.BooleanField(required=False)


class FieldGroupMoveSerializer(serializers.Serializer):
    """移动分组序列化器"""

    direction = serializers.ChoiceField(
        choices=["up", "down"],
        required=True,
        error_messages={
            "required": "移动方向不能为空",
            "invalid_choice": "移动方向必须为up或down",
        },
    )


class BatchUpdateAttrGroupSerializer(serializers.Serializer):
    """批量更新字段分组序列化器"""

    updates = serializers.ListField(
        child=serializers.DictField(),
        required=True,
        min_length=1,
        error_messages={
            "required": "更新列表不能为空",
            "min_length": "至少需要更新一个字段",
        },
    )

    def validate_updates(self, value):
        """校验更新列表格式"""
        for item in value:
            if "attr_id" not in item:
                raise serializers.ValidationError("每个更新项必须包含attr_id")
            if "group_name" not in item:
                raise serializers.ValidationError("每个更新项必须包含group_name")
        return value
