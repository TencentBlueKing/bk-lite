from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace


class MemorySpaceSerializer(TeamSerializer, AuthSerializer):
    permission_key = "memory"
    memory_count = serializers.SerializerMethodField()

    class Meta:
        model = MemorySpace
        fields = "__all__"

    def get_memory_count(self, instance: MemorySpace):
        return instance.memories.count()


class MemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Memory
        fields = "__all__"
        read_only_fields = ("owner_username", "owner_domain")
