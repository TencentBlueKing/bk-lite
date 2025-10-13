from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import App


class AppSerializer(serializers.ModelSerializer):
    description_cn = serializers.SerializerMethodField()

    class Meta:
        model = App
        fields = "__all__"

    def __init__(self, instance=None, data=empty, **kwargs):
        super(AppSerializer, self).__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") or "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)

    def get_description_cn(self, obj):
        # 如果是内置模块，翻译name
        if obj.is_build_in:
            return self.loader.get(f"app.{obj.name}") or obj.description
            # 否则返回原始name
        return obj.description

    def to_representation(self, instance):
        # 获取标准的序列化表示
        data = super().to_representation(instance)
        # 当是GET请求时，将name替换为已翻译的name
        if self.context.get("request") and self.context["request"].method == "GET":
            data["description"] = data["description_cn"]
        # 删除辅助字段，避免在响应中包含
        if "description_cn" in data:
            del data["description_cn"]
        return data

    def create(self, validated_data):
        validated_data["is_build_in"] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("is_build_in", None)
        return super().update(instance, validated_data)
