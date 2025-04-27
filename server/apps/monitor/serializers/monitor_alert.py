from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorAlert


class MonitorAlertSerializer(serializers.ModelSerializer):

    class Meta:
        model = MonitorAlert
        fields = '__all__'
