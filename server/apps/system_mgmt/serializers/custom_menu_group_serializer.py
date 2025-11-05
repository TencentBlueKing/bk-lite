from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import CustomMenuGroup


class CustomMenuGroupSerializer(UsernameSerializer):
    """自定义菜单组序列化器"""

    class Meta:
        model = CustomMenuGroup
        fields = "__all__"
        read_only_fields = ["id", "is_build_in"]

    def validate(self, attrs):
        """数据校验"""
        app = attrs.get("app")
        display_name = attrs.get("display_name")
        is_enabled = attrs.get("is_enabled", False)

        # 检查唯一性（同一个 app 下，display_name 不能重复）
        instance_id = self.instance.id if self.instance else None
        queryset = CustomMenuGroup.objects.filter(app=app, display_name=display_name)
        if instance_id:
            queryset = queryset.exclude(id=instance_id)

        if queryset.exists():
            raise serializers.ValidationError(f"应用 {app} 下已存在相同显示名称的菜单组")

        # 如果要启用，检查是否已有启用的菜单组
        if is_enabled:
            existing_enabled = CustomMenuGroup.objects.filter(app=app, is_enabled=True)
            if instance_id:
                existing_enabled = existing_enabled.exclude(id=instance_id)

            if existing_enabled.exists():
                raise serializers.ValidationError(f"应用 {app} 已有启用的菜单组，每个应用只能启用一个菜单组")

        return attrs


class CustomMenuGroupListSerializer(UsernameSerializer):
    """自定义菜单组列表序列化器（包含菜单数量统计）"""

    menu_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomMenuGroup
        fields = "__all__"

    def get_menu_count(self, obj):
        """获取菜单数量（一级菜单数量）"""
        menus = obj.menus if isinstance(obj.menus, list) else []
        return len(menus)
