"""作业执行序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import JobExecution, JobExecutionTarget, Playbook, Script


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
    trigger_source_display = serializers.CharField(source="get_trigger_source_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = JobExecution
        fields = [
            "id",
            "name",
            "job_type",
            "job_type_display",
            "trigger_source",
            "trigger_source_display",
            "status",
            "status_display",
            "total_count",
            "success_count",
            "failed_count",
            "started_at",
            "finished_at",
            "executor_user",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class JobExecutionDetailSerializer(serializers.ModelSerializer):
    """作业执行详情序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    trigger_source_display = serializers.CharField(source="get_trigger_source_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)
    execution_targets = JobExecutionTargetSerializer(many=True, read_only=True)
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
            "trigger_source",
            "trigger_source_display",
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
            "executor_user",
            "team",
            "execution_targets",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields


class QuickExecuteSerializer(serializers.Serializer):
    """快速执行序列化器（统一入口）

    支持三种执行模式：
    1. 作业模版 - 脚本库：指定 script_id
    2. 作业模版 - Playbook：指定 playbook_id
    3. 临时输入：指定 script_type + script_content

    按原型设计：
    - 作业名称（必填）
    - 目标主机（必填）
    - 内容来源：作业模版 | 临时输入
    - 执行参数：模版模式为 dict，临时输入模式为字符串
    - 超时时间（默认 600 秒）
    """

    name = serializers.CharField(max_length=256, help_text="作业名称")
    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标主机ID列表")

    # 作业模版模式 - 脚本库
    script_id = serializers.IntegerField(required=False, help_text="脚本ID（作业模版-脚本库）")

    # 作业模版模式 - Playbook
    playbook_id = serializers.IntegerField(required=False, help_text="Playbook ID（作业模版-Playbook）")

    # 临时输入模式
    script_type = serializers.ChoiceField(choices=["shell", "bash", "python", "powershell", "bat"], required=False, help_text="脚本类型（临时输入模式必填）")
    script_content = serializers.CharField(required=False, help_text="脚本内容（临时输入模式）")

    # 执行参数（新格式）
    # [{"key": "param1", "value": "value1", "is_modified": True}, ...]
    params = serializers.ListField(child=serializers.DictField(), required=False, default=list, help_text="执行参数列表，格式: [{key, value, is_modified}]")

    # 超时时间
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400, help_text="超时时间（秒）")

    # 团队
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")

    def validate(self, attrs):
        """验证执行模式，确保三选一"""
        script_id = attrs.get("script_id")
        playbook_id = attrs.get("playbook_id")
        script_content = attrs.get("script_content")

        # 统计提供了几种模式
        modes = [bool(script_id), bool(playbook_id), bool(script_content)]
        mode_count = sum(modes)

        if mode_count == 0:
            raise serializers.ValidationError({"script_id": "必须提供 script_id、playbook_id 或 script_content 其中之一"})

        if mode_count > 1:
            raise serializers.ValidationError({"script_id": "script_id、playbook_id、script_content 只能提供其中之一"})

        # 验证临时输入模式必须指定脚本类型
        if script_content and not attrs.get("script_type"):
            raise serializers.ValidationError({"script_type": "临时输入模式必须指定脚本类型"})

        # 验证脚本存在
        if script_id:
            if not Script.objects.filter(id=script_id).exists():
                raise serializers.ValidationError({"script_id": "脚本不存在"})

        # 验证 Playbook 存在
        if playbook_id:
            if not Playbook.objects.filter(id=playbook_id).exists():
                raise serializers.ValidationError({"playbook_id": "Playbook不存在"})

        # 验证 params 格式
        params = attrs.get("params", [])
        if params:
            from apps.job_mgmt.services.script_params_service import ScriptParamsService

            ScriptParamsService.validate_params_format(params)

        return attrs


class FileDistributionSerializer(serializers.Serializer):
    """文件分发序列化器

    使用 multipart/form-data 上传文件，后端自动处理文件存储到 MinIO。

    请求体 (multipart/form-data):
    {
        "name": "部署配置文件",
        "files": [<文件1>, <文件2>, ...],  // 多文件上传
        "target_ids": [1, 2, 3],
        "target_path": "/etc/nginx/",
        "overwrite_strategy": "overwrite",  // overwrite 或 skip
        "timeout": 600,
        "team": [1]
    }
    """

    name = serializers.CharField(max_length=256, help_text="作业名称")
    files = serializers.ListField(child=serializers.FileField(), min_length=1, help_text="文件列表（支持多文件上传）")
    target_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标ID列表")
    target_path = serializers.CharField(max_length=512, help_text="目标路径")
    overwrite_strategy = serializers.ChoiceField(choices=["overwrite", "skip"], default="overwrite", help_text="覆盖策略：overwrite=覆盖已存在文件, skip=跳过已存在文件")
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400, help_text="超时时间（秒）")
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")

    def validate_files(self, value):
        """验证文件"""
        max_size = 500 * 1024 * 1024  # 500MB
        for file in value:
            if file.size > max_size:
                raise serializers.ValidationError(f"文件 {file.name} 超过 500MB 限制")
        return value
