from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace


class MemorySpaceSerializer(TeamSerializer, AuthSerializer):
    permission_key = "memory"
    memory_count = serializers.SerializerMethodField()
    masked_storage_config = serializers.SerializerMethodField()

    class Meta:
        model = MemorySpace
        fields = "__all__"
        extra_kwargs = {
            "storage_config": {"write_only": True},  # 原始配置仅用于写入
        }

    def get_memory_count(self, instance: MemorySpace):
        return instance.memories.count()

    def get_masked_storage_config(self, instance: MemorySpace):
        """返回脱敏后的配置"""
        return instance.get_masked_config()

    def validate(self, attrs):
        """校验更新时不允许切换存储类型"""
        if self.instance:  # 更新操作
            new_storage_type = attrs.get("storage_type")
            if new_storage_type and new_storage_type != self.instance.storage_type:
                raise serializers.ValidationError({"storage_type": "不允许切换存储类型，请创建新的记忆空间"})
        return attrs

    def to_representation(self, instance):
        """自定义输出，用脱敏配置替换原始配置"""
        data = super().to_representation(instance)
        # 移除 write_only 的 storage_config，添加脱敏版本
        data.pop("storage_config", None)
        data["storage_config"] = self.get_masked_storage_config(instance)
        return data


class WorkflowMemorySpaceOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemorySpace
        fields = ("id", "name", "scope", "default_model")


class MemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Memory
        fields = "__all__"
        read_only_fields = ("owner_username", "owner_domain")
