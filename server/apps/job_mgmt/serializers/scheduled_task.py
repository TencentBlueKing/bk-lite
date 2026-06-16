"""定时任务序列化器"""

from django.db import transaction
from rest_framework import serializers

from apps.job_mgmt.constants import TargetSource
from apps.job_mgmt.models import ScheduledTask
from apps.job_mgmt.serializers.validators import validate_scheduled_task_payload
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService


class ScheduledTaskListSerializer(serializers.ModelSerializer):
    """定时任务列表序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    schedule_type_display = serializers.CharField(source="get_schedule_type_display", read_only=True)
    target_count = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledTask
        fields = [
            "id",
            "name",
            "description",
            "job_type",
            "job_type_display",
            "schedule_type",
            "schedule_type_display",
            "cron_expression",
            "scheduled_time",
            "is_enabled",
            "concurrency_policy",
            "last_run_at",
            "run_count",
            "target_count",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_target_count(self, obj):
        target_list = obj.target_list or []
        return len(target_list)


class ScheduledTaskDetailSerializer(serializers.ModelSerializer):
    """定时任务详情序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    schedule_type_display = serializers.CharField(source="get_schedule_type_display", read_only=True)
    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)
    script_name = serializers.CharField(source="script.name", read_only=True, default=None)
    playbook_name = serializers.CharField(source="playbook.name", read_only=True, default=None)

    class Meta:
        model = ScheduledTask
        fields = [
            "id",
            "name",
            "description",
            "job_type",
            "job_type_display",
            "schedule_type",
            "schedule_type_display",
            "cron_expression",
            "scheduled_time",
            "script",
            "script_name",
            "playbook",
            "playbook_name",
            "target_source",
            "target_list",
            "params",
            "script_type",
            "script_type_display",
            "script_content",
            "files",
            "target_path",
            "timeout",
            "is_enabled",
            "concurrency_policy",
            "periodic_task_id",
            "last_run_at",
            "run_count",
            "team",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields


class ScheduledTaskCreateSerializer(serializers.ModelSerializer):
    """定时任务创建序列化器"""

    target_source = serializers.ChoiceField(
        choices=[TargetSource.NODE_MGMT, TargetSource.MANUAL, TargetSource.SYNC],
        help_text="目标来源: node_mgmt=节点管理, manual=手动添加, sync=同步",
    )
    target_list = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        write_only=True,
        help_text="目标列表: node_mgmt时为[{node_id, name, ip, os, cloud_region_id}], manual时为[{target_id, name, ip}]",
    )
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表，用于高危规则匹配")

    class Meta:
        model = ScheduledTask
        fields = [
            "name",
            "description",
            "job_type",
            "schedule_type",
            "cron_expression",
            "scheduled_time",
            "script",
            "playbook",
            "target_source",
            "target_list",
            "params",
            "script_type",
            "script_content",
            "files",
            "target_path",
            "timeout",
            "is_enabled",
            "concurrency_policy",
            "team",
        ]

    def validate(self, attrs):
        """验证定时任务配置（共用校验见 :mod:`serializers.validators`）"""
        return validate_scheduled_task_payload(attrs, instance=None)

    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user:
            validated_data["created_by"] = request.user.username
            validated_data["updated_by"] = request.user.username

        with transaction.atomic():
            instance = ScheduledTask.objects.create(**validated_data)

            # 创建 celery-beat PeriodicTask
            periodic_task = ScheduledTaskService.create_periodic_task(instance)
            if periodic_task:
                instance.periodic_task_id = periodic_task.id
                instance.save(update_fields=["periodic_task_id"])
            else:
                # PeriodicTask 创建失败，回滚整个事务
                raise serializers.ValidationError({"non_field_errors": ["创建定时调度任务失败，请检查 Cron 表达式或计划执行时间"]})

        return instance


class ScheduledTaskUpdateSerializer(serializers.ModelSerializer):
    """定时任务更新序列化器"""

    target_source = serializers.ChoiceField(
        choices=[TargetSource.NODE_MGMT, TargetSource.MANUAL, TargetSource.SYNC],
        required=False,
        help_text="目标来源: node_mgmt=节点管理, manual=手动添加, sync=同步",
    )
    target_list = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True,
        help_text="目标列表: node_mgmt时为[{node_id, name, ip, os, cloud_region_id}], manual时为[{target_id, name, ip}]",
    )
    team = serializers.ListField(child=serializers.IntegerField(), required=False, help_text="团队ID列表，用于高危规则匹配")

    class Meta:
        model = ScheduledTask
        fields = [
            "name",
            "description",
            "job_type",
            "schedule_type",
            "cron_expression",
            "scheduled_time",
            "script",
            "playbook",
            "target_source",
            "target_list",
            "params",
            "script_type",
            "script_content",
            "files",
            "target_path",
            "timeout",
            "is_enabled",
            "concurrency_policy",
            "team",
        ]

    def validate(self, attrs):
        """验证定时任务配置（共用校验见 :mod:`serializers.validators`）"""
        return validate_scheduled_task_payload(attrs, instance=self.instance)

    def update(self, instance, validated_data):
        request = self.context.get("request")

        if request and request.user:
            validated_data["updated_by"] = request.user.username

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # 更新 celery-beat PeriodicTask
            periodic_task = ScheduledTaskService.update_periodic_task(instance)
            if periodic_task:
                instance.periodic_task_id = periodic_task.id
                instance.save(update_fields=["periodic_task_id"])
            elif instance.is_enabled:
                # 启用状态下 PeriodicTask 更新失败，回滚
                raise serializers.ValidationError({"non_field_errors": ["更新定时调度任务失败，请检查配置"]})

        return instance


class ScheduledTaskToggleSerializer(serializers.Serializer):
    """定时任务启用/禁用序列化器"""

    is_enabled = serializers.BooleanField(help_text="是否启用")


class ScheduledTaskBatchDeleteSerializer(serializers.Serializer):
    """定时任务批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="定时任务ID列表")
