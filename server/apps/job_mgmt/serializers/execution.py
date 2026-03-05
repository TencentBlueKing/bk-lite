"""作业执行序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import JobExecution, JobExecutionTarget


class JobExecutionTargetSerializer(serializers.ModelSerializer):
    """作业执行目标序列化器"""

    target_name = serializers.CharField(source="target.name", read_only=True)
    target_ip = serializers.CharField(source="target.ip", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = JobExecutionTarget
        fields = [
            "id",
            "target",
            "target_name",
            "target_ip",
            "status",
            "status_display",
            "stdout",
            "stderr",
            "exit_code",
            "started_at",
            "finished_at",
            "error_message",
        ]
        read_only_fields = ["id", "started_at", "finished_at"]


class JobExecutionListSerializer(serializers.ModelSerializer):
    """作业执行列表序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = JobExecution
        fields = [
            "id",
            "name",
            "job_type",
            "job_type_display",
            "status",
            "status_display",
            "total_count",
            "success_count",
            "failed_count",
            "started_at",
            "finished_at",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class JobExecutionDetailSerializer(serializers.ModelSerializer):
    """作业执行详情序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)
    execution_targets = JobExecutionTargetSerializer(many=True, read_only=True)

    class Meta:
        model = JobExecution
        fields = [
            "id",
            "name",
            "job_type",
            "job_type_display",
            "status",
            "status_display",
            "script",
            "playbook",
            "params",
            "script_type",
            "script_type_display",
            "script_content",
            "files",
            "target_path",
            "timeout",
            "started_at",
            "finished_at",
            "total_count",
            "success_count",
            "failed_count",
            "team",
            "execution_targets",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields


class QuickExecuteSerializer(serializers.Serializer):
    """快速执行序列化器（脚本执行）"""

    name = serializers.CharField(max_length=256, required=False, help_text="作业名称，不填则自动生成")
    script_id = serializers.IntegerField(required=False, help_text="脚本ID，与script_content二选一")
    script_type = serializers.ChoiceField(
        choices=["shell", "bash", "python", "powershell", "bat"], required=False, help_text="脚本类型，使用script_content时必填"
    )
    script_content = serializers.CharField(required=False, help_text="脚本内容，与script_id二选一")
    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标ID列表")
    params = serializers.DictField(required=False, default=dict, help_text="执行参数")
    timeout = serializers.IntegerField(required=False, default=60, min_value=1, max_value=86400, help_text="超时时间（秒）")
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")

    def validate(self, attrs):
        """验证脚本来源"""
        script_id = attrs.get("script_id")
        script_content = attrs.get("script_content")

        if not script_id and not script_content:
            raise serializers.ValidationError({"script_id": "script_id 和 script_content 必须提供其一"})

        if script_content and not attrs.get("script_type"):
            raise serializers.ValidationError({"script_type": "使用 script_content 时必须指定 script_type"})

        return attrs


class FileDistributionSerializer(serializers.Serializer):
    """文件分发序列化器"""

    name = serializers.CharField(max_length=256, required=False, help_text="作业名称，不填则自动生成")
    files = serializers.ListField(child=serializers.DictField(), min_length=1, help_text="文件列表，每项包含 name, file_key, bucket_name, size")
    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标ID列表")
    target_path = serializers.CharField(max_length=512, help_text="目标路径")
    timeout = serializers.IntegerField(required=False, default=300, min_value=1, max_value=86400, help_text="超时时间（秒）")
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")

    def validate_files(self, value):
        """验证文件列表格式"""
        required_keys = {"name", "file_key", "bucket_name"}
        for i, file_item in enumerate(value):
            missing_keys = required_keys - set(file_item.keys())
            if missing_keys:
                raise serializers.ValidationError(f"第 {i + 1} 个文件缺少字段: {missing_keys}")
        return value


class PlaybookExecuteSerializer(serializers.Serializer):
    """Playbook执行序列化器"""

    name = serializers.CharField(max_length=256, required=False, help_text="作业名称，不填则自动生成")
    playbook_id = serializers.IntegerField(help_text="Playbook ID")
    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标ID列表")
    params = serializers.DictField(required=False, default=dict, help_text="执行参数（extra_vars）")
    timeout = serializers.IntegerField(required=False, default=300, min_value=1, max_value=86400, help_text="超时时间（秒）")
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")
