from rest_framework import serializers

from apps.log.services.syslog_source_device import PAGE_SIZE_MAX


class SyslogSourceDeviceQuerySerializer(serializers.Serializer):
    cloud_region_id = serializers.CharField(required=False, allow_blank=True, default="")
    source_ip = serializers.CharField(required=False, allow_blank=True, default="")
    hostname = serializers.CharField(required=False, allow_blank=True, default="")
    keyword = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=PAGE_SIZE_MAX, default=20)

    def validate_status(self, value: str) -> str:
        if value in ("", None):
            return ""
        if value not in {"active", "silent"}:
            raise serializers.ValidationError("status must be active or silent")
        return value
