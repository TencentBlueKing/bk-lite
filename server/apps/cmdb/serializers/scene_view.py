from rest_framework import serializers

from apps.cmdb.models.scene_view import SceneView
from apps.cmdb.services.scene_view import can_edit_scene


class SceneViewSerializer(serializers.ModelSerializer):
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = SceneView
        fields = [
            "id",
            "name",
            "visibility",
            "organization",
            "model_ids",
            "tags",
            "tag_match",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "can_edit",
        ]
        read_only_fields = [
            "id",
            "organization",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "can_edit",
        ]

    def get_can_edit(self, obj) -> bool:
        request = self.context.get("request")
        if not request:
            return False
        return can_edit_scene(request.user, obj)

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("名称不能为空")
        return name

    def validate_visibility(self, value):
        allowed = {
            SceneView.Visibility.PERSONAL,
            SceneView.Visibility.ORGANIZATION,
            SceneView.Visibility.GLOBAL,
        }
        if value not in allowed:
            raise serializers.ValidationError("可见范围无效")
        if value != SceneView.Visibility.PERSONAL and not self.context.get("request"):
            raise serializers.ValidationError("当前仅支持个人视图")
        return value

    def validate_tag_match(self, value):
        allowed = {SceneView.TagMatch.AND, SceneView.TagMatch.OR}
        if value not in allowed:
            raise serializers.ValidationError("标签匹配仅支持 and 或 or")
        return value

    def validate_model_ids(self, value):
        if not isinstance(value, list) or not [item for item in value if str(item).strip()]:
            raise serializers.ValidationError("至少选择一个模型")
        return [str(item).strip() for item in value if str(item).strip()]

    def validate_tags(self, value):
        if not isinstance(value, list) or not [item for item in value if str(item).strip()]:
            raise serializers.ValidationError("至少选择一个标签")
        return [str(item).strip() for item in value if str(item).strip()]
