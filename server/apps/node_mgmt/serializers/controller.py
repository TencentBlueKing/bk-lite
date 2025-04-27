from rest_framework import serializers

from apps.node_mgmt.models import Controller


class ControllerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Controller
        fields = ['id', 'name', 'os', 'description']
