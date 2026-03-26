from rest_framework import serializers


class LogTopStatsSerializer(serializers.Serializer):
    query = serializers.CharField(required=False, allow_blank=True, default="*")
    start_time = serializers.CharField(required=False, allow_blank=True, default="")
    end_time = serializers.CharField(required=False, allow_blank=True, default="")
    attr = serializers.RegexField(
        regex=r"^[A-Za-z_][A-Za-z0-9_.]*$",
        max_length=200,
        error_messages={"invalid": "attr 参数格式非法"},
    )
    top_num = serializers.IntegerField(min_value=1, max_value=100, default=5)
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        default=list,
    )
