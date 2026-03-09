"""定时任务序列化器"""

from rest_framework import serializers

from apps.job_mgmt.constants import JobType, ScheduleType
from apps.job_mgmt.models import ScheduledTask, Target
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
        return obj.targets.count()


class ScheduledTaskDetailSerializer(serializers.ModelSerializer):
    """定时任务详情序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    schedule_type_display = serializers.CharField(source="get_schedule_type_display", read_only=True)
    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)
    script_name = serializers.CharField(source="script.name", read_only=True, default=None)
    playbook_name = serializers.CharField(source="playbook.name", read_only=True, default=None)
    target_ids = serializers.PrimaryKeyRelatedField(source="targets", many=True, read_only=True)

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
            "target_ids",
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

    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, write_only=True, help_text="目标ID列表")

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
            "target_ids",
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
        """验证定时任务配置"""
        job_type = attrs.get("job_type")
        schedule_type = attrs.get("schedule_type")

        # 调度类型验证
        if schedule_type == ScheduleType.CRON:
            if not attrs.get("cron_expression"):
                raise serializers.ValidationError({"cron_expression": "周期执行时必须指定Cron表达式"})
        elif schedule_type == ScheduleType.ONCE:
            if not attrs.get("scheduled_time"):
                raise serializers.ValidationError({"scheduled_time": "单次执行时必须指定计划执行时间"})

        # 作业类型验证
        if job_type == JobType.SCRIPT:
            script = attrs.get("script")
            script_content = attrs.get("script_content")
            if not script and not script_content:
                raise serializers.ValidationError({"script": "脚本执行时必须指定脚本或脚本内容"})
            if script_content and not attrs.get("script_type"):
                raise serializers.ValidationError({"script_type": "使用脚本内容时必须指定脚本类型"})
        elif job_type == JobType.FILE_DISTRIBUTION:
            if not attrs.get("files"):
                raise serializers.ValidationError({"files": "文件分发时必须指定文件列表"})
            if not attrs.get("target_path"):
                raise serializers.ValidationError({"target_path": "文件分发时必须指定目标路径"})
        elif job_type == JobType.PLAYBOOK:
            if not attrs.get("playbook"):
                raise serializers.ValidationError({"playbook": "Playbook执行时必须指定Playbook"})

        # 验证目标
        target_ids = attrs.get("target_ids", [])
        targets = Target.objects.filter(id__in=target_ids)
        if targets.count() != len(target_ids):
            raise serializers.ValidationError({"target_ids": "部分目标不存在"})

        # 验证 params 格式
        params = attrs.get("params")
        if params:
            from apps.job_mgmt.services.script_params_service import ScriptParamsService

            ScriptParamsService.validate_params_format(params)

        return attrs

    def create(self, validated_data):
        target_ids = validated_data.pop("target_ids", [])
        request = self.context.get("request")

        if request and request.user:
            validated_data["created_by"] = request.user.username
            validated_data["updated_by"] = request.user.username

        instance = ScheduledTask.objects.create(**validated_data)
        instance.targets.set(target_ids)

        # 创建 celery-beat PeriodicTask
        periodic_task = ScheduledTaskService.create_periodic_task(instance)
        if periodic_task:
            instance.periodic_task_id = periodic_task.id
            instance.save(update_fields=["periodic_task_id"])

        return instance


class ScheduledTaskUpdateSerializer(serializers.ModelSerializer):
    """定时任务更新序列化器"""

    target_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True, help_text="目标ID列表")

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
            "target_ids",
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
        """验证定时任务配置"""
        instance = self.instance
        job_type = attrs.get("job_type", instance.job_type if instance else None)
        schedule_type = attrs.get("schedule_type", instance.schedule_type if instance else None)

        # 调度类型验证
        if schedule_type == ScheduleType.CRON:
            cron_expression = attrs.get("cron_expression", instance.cron_expression if instance else "")
            if not cron_expression:
                raise serializers.ValidationError({"cron_expression": "周期执行时必须指定Cron表达式"})
        elif schedule_type == ScheduleType.ONCE:
            scheduled_time = attrs.get("scheduled_time", instance.scheduled_time if instance else None)
            if not scheduled_time:
                raise serializers.ValidationError({"scheduled_time": "单次执行时必须指定计划执行时间"})

        # 作业类型验证
        if job_type == JobType.SCRIPT:
            script = attrs.get("script", instance.script if instance else None)
            script_content = attrs.get("script_content", instance.script_content if instance else None)
            if not script and not script_content:
                raise serializers.ValidationError({"script": "脚本执行时必须指定脚本或脚本内容"})
            script_type = attrs.get("script_type", instance.script_type if instance else None)
            if script_content and not script_type:
                raise serializers.ValidationError({"script_type": "使用脚本内容时必须指定脚本类型"})
        elif job_type == JobType.FILE_DISTRIBUTION:
            files = attrs.get("files", instance.files if instance else None)
            target_path = attrs.get("target_path", instance.target_path if instance else None)
            if not files:
                raise serializers.ValidationError({"files": "文件分发时必须指定文件列表"})
            if not target_path:
                raise serializers.ValidationError({"target_path": "文件分发时必须指定目标路径"})
        elif job_type == JobType.PLAYBOOK:
            playbook = attrs.get("playbook", instance.playbook if instance else None)
            if not playbook:
                raise serializers.ValidationError({"playbook": "Playbook执行时必须指定Playbook"})
        # 验证目标
        target_ids = attrs.get("target_ids")
        if target_ids is not None:
            targets = Target.objects.filter(id__in=target_ids)
            if targets.count() != len(target_ids):
                raise serializers.ValidationError({"target_ids": "部分目标不存在"})

        # 验证 params 格式
        params = attrs.get("params")
        if params:
            from apps.job_mgmt.services.script_params_service import ScriptParamsService

            ScriptParamsService.validate_params_format(params)

        return attrs

    def update(self, instance, validated_data):
        target_ids = validated_data.pop("target_ids", None)
        request = self.context.get("request")

        if request and request.user:
            validated_data["updated_by"] = request.user.username

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if target_ids is not None:
            instance.targets.set(target_ids)

        # 更新 celery-beat PeriodicTask
        periodic_task = ScheduledTaskService.update_periodic_task(instance)
        if periodic_task:
            instance.periodic_task_id = periodic_task.id
            instance.save(update_fields=["periodic_task_id"])

        return instance


class ScheduledTaskToggleSerializer(serializers.Serializer):
    """定时任务启用/禁用序列化器"""

    is_enabled = serializers.BooleanField(help_text="是否启用")


class ScheduledTaskBatchDeleteSerializer(serializers.Serializer):
    """定时任务批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="定时任务ID列表")
