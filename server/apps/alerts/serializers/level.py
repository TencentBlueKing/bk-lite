# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.models import Level


class LevelModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = '__all__'
