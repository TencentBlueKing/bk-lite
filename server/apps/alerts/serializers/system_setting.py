# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.sys_setting import SystemSetting


class SystemSettingModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = "__all__"
        extra_kwargs = {}
