"""作业执行序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import JobExecution, Playbook, Script


class JobExecutionListSerializer(serializers.ModelSerializer):
    """作业执行列表序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    trigger_source_display = serializers.CharField(source="get_trigger_source_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    duration = serializers.SerializerMethodField(help_text="耗时（秒）")

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
            "duration",
            "executor_user",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_duration(self, obj) -> int | None:
        """计算耗时（秒）"""
        if obj.started_at and obj.finished_at:
            return int((obj.finished_at - obj.started_at).total_seconds())
        return None


class JobExecutionDetailSerializer(serializers.ModelSerializer):
    """作业执行详情序列化器"""

    job_type_display = serializers.CharField(source="get_job_type_display", read_only=True)
    trigger_source_display = serializers.CharField(source="get_trigger_source_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)
    duration = serializers.SerializerMethodField(help_text="耗时（秒）")

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
            "duration",
            "total_count",
            "success_count",
            "failed_count",
            "executor_user",
            "team",
            "target_source",
            "target_list",
            "execution_results",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields

    def get_duration(self, obj) -> int | None:
        """计算耗时（秒）"""
        if obj.started_at and obj.finished_at:
            return int((obj.finished_at - obj.started_at).total_seconds())
        return None


class QuickExecuteSerializer(serializers.Serializer):
    """快速执行序列化器（统一入口）

    支持三种执行模式：
    1. 作业模版 - 脚本库：指定 script_id
    2. 作业模版 - Playbook：指定 playbook_id
    3. 临时输入：指定 script_type + script_content

    按原型设计：
    - 作业名称（必填）
    - 目标来源和目标列表（必填）
    - 内容来源：作业模版 | 临时输入
    - 执行参数：模版模式为 dict，临时输入模式为字符串
    - 超时时间（默认 600 秒）
    """

    name = serializers.CharField(max_length=256, help_text="作业名称")
    target_source = serializers.ChoiceField(choices=["node_mgmt", "manual", "sync"], help_text="目标来源: node_mgmt=节点管理, manual=手动添加, sync=同步")
    target_list = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        help_text="目标列表: node_mgmt时为[{node_id, name, ip, os, cloud_region_id}], manual时为[{target_id, name, ip}]",
    )

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

    使用 JSON 请求体，传入已上传文件的 ID 列表进行分发。

    请求体 (application/json):
    {
        "name": "部署配置文件",
        "file_ids": [1, 2, 3],
        "target_source": "node_mgmt",
        "target_list": [{"node_id": "xxx", "name": "xxx", "ip": "1.2.3.4", ...}],
        "target_path": "/etc/nginx/",
        "overwrite_strategy": "overwrite",
        "timeout": 600,
        "team": [1]
    }
    """

    name = serializers.CharField(max_length=256, help_text="作业名称")
    file_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="已上传文件ID列表")
    target_source = serializers.ChoiceField(choices=["node_mgmt", "manual", "sync"], help_text="目标来源: node_mgmt=节点管理, manual=手动添加, sync=同步")
    target_list = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        help_text="目标列表: node_mgmt时为[{node_id, name, ip, os, cloud_region_id}], manual时为[{target_id, name, ip}]",
    )
    target_path = serializers.CharField(max_length=512, help_text="目标路径")
    overwrite_strategy = serializers.ChoiceField(choices=["overwrite", "skip"], default="overwrite", help_text="覆盖策略：overwrite=覆盖已存在文件, skip=跳过已存在文件")
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400, help_text="超时时间（秒）")
    team = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, help_text="团队ID列表")
