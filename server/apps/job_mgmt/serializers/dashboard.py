"""Dashboard序列化器"""

from rest_framework import serializers


class DashboardTrendSerializer(serializers.Serializer):
    """Dashboard趋势数据序列化器"""

    date = serializers.DateField(help_text="日期")
    execution_count = serializers.IntegerField(help_text="执行次数")
    success_count = serializers.IntegerField(help_text="成功次数")
    failed_count = serializers.IntegerField(help_text="失败次数")
