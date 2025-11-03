from rest_framework import serializers

from apps.system_mgmt.models import Group


class GroupSerializer(serializers.ModelSerializer):
    roles = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Group
        fields = "__all__"
