from rest_framework import serializers

from apps.log.constants.victoriametrics import VictoriaLogsConstants


class LogFieldValuesSerializer(serializers.Serializer):
    filed = serializers.RegexField(
        regex=r"^[A-Za-z_][A-Za-z0-9_.]*$",
        max_length=200,
        error_messages={"invalid": "filed 参数格式非法"},
    )
    start_time = serializers.CharField(required=False, allow_blank=True, default="")
    end_time = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(
        min_value=1,
        max_value=VictoriaLogsConstants.FIELD_VALUES_LIMIT_MAX,
        default=100,
    )


class LogSearchSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, allow_blank=False)
    start_time = serializers.CharField(required=False, allow_blank=True, default="")
    end_time = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(
        min_value=1,
        max_value=VictoriaLogsConstants.QUERY_LIMIT_MAX,
        default=10,
    )
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
        error_messages={"required": "缺少日志分组", "empty": "缺少日志分组"},
    )


class LogHitsSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, allow_blank=False)
    start_time = serializers.CharField(required=False, allow_blank=True, default="")
    end_time = serializers.CharField(required=False, allow_blank=True, default="")
    field = serializers.RegexField(
        regex=r"^[A-Za-z_][A-Za-z0-9_.]*$",
        max_length=200,
        error_messages={"invalid": "field 参数格式非法"},
    )
    fields_limit = serializers.IntegerField(
        min_value=1,
        max_value=VictoriaLogsConstants.HITS_FIELDS_LIMIT_MAX,
        default=5,
    )
    step = serializers.CharField(required=False, allow_blank=True, default="5m")
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
        error_messages={"required": "缺少日志分组", "empty": "缺少日志分组"},
    )


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
        required=True,
        allow_empty=False,
        error_messages={"required": "缺少日志分组", "empty": "缺少日志分组"},
    )
