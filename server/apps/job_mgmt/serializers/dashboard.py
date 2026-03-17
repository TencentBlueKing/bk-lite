"""Dashboard序列化器"""

from rest_framework import serializers


class DashboardStatsSerializer(serializers.Serializer):
    """Dashboard统计数据序列化器"""

    # 目标统计
    target_total = serializers.IntegerField(help_text="目标总数")
    target_online = serializers.IntegerField(help_text="在线目标数")
    target_offline = serializers.IntegerField(help_text="离线目标数")

    # 脚本统计
    script_total = serializers.IntegerField(help_text="脚本总数")
    playbook_total = serializers.IntegerField(help_text="Playbook总数")

    # 执行统计
    execution_total = serializers.IntegerField(help_text="执行记录总数")
    execution_success = serializers.IntegerField(help_text="执行成功数")
    execution_failed = serializers.IntegerField(help_text="执行失败数")
    execution_running = serializers.IntegerField(help_text="执行中数量")

    # 定时任务统计
    scheduled_task_total = serializers.IntegerField(help_text="定时任务总数")
    scheduled_task_enabled = serializers.IntegerField(help_text="启用的定时任务数")


class DashboardTrendSerializer(serializers.Serializer):
    """Dashboard趋势数据序列化器"""

    date = serializers.DateField(help_text="日期")
    execution_count = serializers.IntegerField(help_text="执行次数")
    success_count = serializers.IntegerField(help_text="成功次数")
    failed_count = serializers.IntegerField(help_text="失败次数")


class DashboardRecentExecutionSerializer(serializers.Serializer):
    """Dashboard最近执行记录序列化器"""

    id = serializers.IntegerField(help_text="执行记录ID")
    name = serializers.CharField(help_text="作业名称")
    job_type = serializers.CharField(help_text="作业类型")
    job_type_display = serializers.CharField(help_text="作业类型显示名称")
    status = serializers.CharField(help_text="执行状态")
    status_display = serializers.CharField(help_text="执行状态显示名称")
    created_by = serializers.CharField(help_text="创建人")
    created_at = serializers.DateTimeField(help_text="创建时间")
