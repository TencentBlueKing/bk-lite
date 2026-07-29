from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.system_mgmt.models import Group, LoginModule
from apps.system_mgmt.tasks import sync_user_and_group_by_login_module


class LoginModuleSerializer(serializers.ModelSerializer):
    # 自定义 name 字段，用于展示时可能的翻译
    display_name = serializers.SerializerMethodField()
    # app_secret 仅接受写入，不在 API 响应中返回，避免密文暴露给前端
    app_secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    class Meta:
        model = LoginModule
        fields = (
            "id",
            "name",
            "source_type",
            "app_id",
            "app_secret",
            "other_config",
            "enabled",
            "is_build_in",
            "display_name",
        )

    def get_display_name(self, obj):
        # 如果是内置模块，翻译name
        if obj.is_build_in:
            return _(obj.name)
        # 否则返回原始name
        return obj.name

    def to_representation(self, instance):
        # 获取标准的序列化表示
        data = super().to_representation(instance)
        # 当是GET请求时，将name替换为已翻译的name
        if self.context.get("request") and self.context["request"].method == "GET":
            data["name"] = data["display_name"]
        # 删除辅助字段，避免在响应中包含
        if "display_name" in data:
            del data["display_name"]
        return data

    def create(self, validated_data):
        source_type = validated_data.get("source_type")
        if source_type == "bk_login":
            Group.objects.get_or_create(parent_id=0, name=validated_data["other_config"].get("root_group", "蓝鲸"))
        instance = super().create(validated_data)
        if source_type == "bk_lite":
            try:
                instance.create_sync_periodic_task()
                sync_user_and_group_by_login_module.delay(instance.id)
            except Exception:
                pass
        return instance

    def update(self, instance, validated_data):
        # 未输入新密钥时保留现值；前端编辑表单会将空值视为“不更换密钥”
        if validated_data.get("app_secret") in (None, ""):
            validated_data.pop("app_secret", None)
        instance = super().update(instance, validated_data)
        if instance.source_type == "bk_lite":
            try:
                instance.create_sync_periodic_task()
            except Exception:
                pass
        return instance
