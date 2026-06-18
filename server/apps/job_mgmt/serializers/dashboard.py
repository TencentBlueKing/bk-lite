"""Dashboard序列化器"""

from rest_framework import serializers


class DashboardTrendSerializer(serializers.Serializer):
    """Dashboard趋势数据序列化器"""

    date = serializers.DateField(help_text="日期")
    execution_count = serializers.IntegerField(help_text="执行次数")
    success_count = serializers.IntegerField(help_text="成功次数")
    failed_count = serializers.IntegerField(help_text="失败次数")
    cancelled_count = serializers.IntegerField(help_text="取消次数")
    avg_duration_seconds = serializers.FloatField(help_text="当日平均执行时长（秒）")


class DashboardStatsSerializer(serializers.Serializer):
    """Dashboard统计数据序列化器（资产与执行计数）"""

    target_total = serializers.IntegerField(help_text="目标总数")
    script_total = serializers.IntegerField(help_text="脚本总数")
    playbook_total = serializers.IntegerField(help_text="Playbook总数")
    execution_total = serializers.IntegerField(help_text="执行记录总数")
    execution_success = serializers.IntegerField(help_text="执行成功数")
    execution_failed = serializers.IntegerField(help_text="执行失败数")
    execution_running = serializers.IntegerField(help_text="执行中数量")
    execution_pending = serializers.IntegerField(help_text="等待中数量")
    scheduled_task_total = serializers.IntegerField(help_text="定时任务总数")
    scheduled_task_enabled = serializers.IntegerField(help_text="启用的定时任务数")
    avg_duration_seconds = serializers.FloatField(help_text="平均执行时长（秒，基于已完成执行）")
