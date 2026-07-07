"""序列化器共用校验函数。

抽取 Target / ScheduledTask 序列化器中重复出现的字段校验，
避免散落在多个 :meth:`validate` 中难以维护。
"""

from rest_framework import serializers

from apps.job_mgmt.constants import CredentialSource, JobType, OSType, ScheduleType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import Target
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings
from apps.job_mgmt.services.script_params_service import ScriptParamsService


def validate_manual_credentials(attrs: dict, *, require_cloud_region: bool = False) -> dict:
    """校验目标的手动凭据字段（Linux SSH / Windows WinRM）。

    覆盖 :class:`TargetSerializer` 与 :class:`TargetTestConnectionSerializer` 中
    重复出现的 ~30 行凭据校验逻辑。

    Args:
        attrs: 序列化器 ``validate`` 收到的属性字典。
        require_cloud_region: 是否要求 ``cloud_region_id`` 必填。
            ``TargetSerializer`` 中需为 ``True``；
            ``TargetTestConnectionSerializer`` 的字段定义已强制 required=True，传 ``False`` 即可。

    Returns:
        校验通过的 ``attrs``（原样返回，方便链式调用）。

    Raises:
        serializers.ValidationError: 任一必填项缺失。
    """
    os_type = attrs.get("os_type", OSType.LINUX)
    credential_source = attrs.get("credential_source", CredentialSource.MANUAL)

    if credential_source == CredentialSource.MANUAL:
        if os_type == OSType.LINUX:
            if not attrs.get("ssh_user"):
                raise serializers.ValidationError({"ssh_user": "Linux目标必须提供SSH用户名"})
            ssh_credential_type = attrs.get("ssh_credential_type", SSHCredentialType.PASSWORD)
            if ssh_credential_type == SSHCredentialType.PASSWORD:
                if not attrs.get("ssh_password"):
                    raise serializers.ValidationError({"ssh_password": "密码认证方式必须提供SSH密码"})
            else:
                if not attrs.get("ssh_key_file"):
                    raise serializers.ValidationError({"ssh_key_file": "密钥认证方式必须上传SSH密钥文件"})
        else:
            if not attrs.get("winrm_user"):
                raise serializers.ValidationError({"winrm_user": "Windows目标必须提供WinRM用户名"})
            if not attrs.get("winrm_password"):
                raise serializers.ValidationError({"winrm_password": "Windows目标必须提供WinRM密码"})
    elif credential_source == CredentialSource.CREDENTIAL:
        if not attrs.get("credential_id"):
            raise serializers.ValidationError({"credential_id": "凭据管理方式必须选择凭据"})

    if require_cloud_region and not attrs.get("cloud_region_id"):
        raise serializers.ValidationError({"cloud_region_id": "云区域必填"})

    return attrs


def validate_scheduled_task_payload(attrs: dict, *, instance=None) -> dict:
    """校验定时任务 create / update 共用的字段约束。

    覆盖 :class:`ScheduledTaskCreateSerializer` 与 :class:`ScheduledTaskUpdateSerializer`
    中重复出现的 ~50 行调度类型 / 作业类型 / 目标列表 / 参数格式校验。

    Args:
        attrs: 序列化器 ``validate`` 收到的属性字典。
        instance: 更新场景下传入当前 :class:`ScheduledTask` 实例；
            未在 ``attrs`` 中提供的字段会回退到 ``instance`` 上对应属性。
            创建场景传 ``None``，所有字段均必须出现在 ``attrs`` 中。
    """

    def _resolve(key):
        if key in attrs:
            return attrs[key]
        return getattr(instance, key, None) if instance is not None else None

    schedule_type = _resolve("schedule_type")
    job_type = _resolve("job_type")

    # 调度类型校验
    if schedule_type == ScheduleType.CRON:
        if not _resolve("cron_expression"):
            raise serializers.ValidationError({"cron_expression": "周期执行时必须指定Cron表达式"})
    elif schedule_type == ScheduleType.ONCE:
        if not _resolve("scheduled_time"):
            raise serializers.ValidationError({"scheduled_time": "单次执行时必须指定计划执行时间"})

    # 作业类型校验
    if job_type == JobType.SCRIPT:
        if not _resolve("script") and not _resolve("script_content"):
            raise serializers.ValidationError({"script": "脚本执行时必须指定脚本或脚本内容"})
        if _resolve("script_content") and not _resolve("script_type"):
            raise serializers.ValidationError({"script_type": "使用脚本内容时必须指定脚本类型"})
    elif job_type == JobType.FILE_DISTRIBUTION:
        if not _resolve("files"):
            raise serializers.ValidationError({"files": "文件分发时必须指定文件列表"})
        if not _resolve("target_path"):
            raise serializers.ValidationError({"target_path": "文件分发时必须指定目标路径"})
    elif job_type == JobType.PLAYBOOK:
        if not _resolve("playbook"):
            raise serializers.ValidationError({"playbook": "Playbook执行时必须指定Playbook"})

    # 目标列表校验（仅 manual 来源需要验证 target_id 存在）
    target_list = attrs.get("target_list")
    if target_list is not None and _resolve("target_source") == TargetSource.MANUAL:
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if target_ids:
            existing_count = Target.objects.filter(id__in=target_ids).count()
            if existing_count != len(target_ids):
                raise serializers.ValidationError({"target_list": "部分目标不存在"})

    # 参数格式校验
    params = attrs.get("params")
    if params:
        ScriptParamsService.validate_params_format(params)

    # 脚本内容入库前规范化换行符（CRLF/CR → LF；bat/powershell 保留原样）。
    # 仅在 attrs 显式提供 script_content 时处理；update 场景下未传则保留 instance 原值，
    # 由 worker 兜底执行规范化。script_type 走 _resolve 取值，避免 PATCH 只改 content 时
    # 误把 PowerShell 脚本里的 CRLF 当作 Unix 转 LF。
    if "script_content" in attrs and attrs["script_content"]:
        resolved_script_type = _resolve("script_type") or ""
        attrs["script_content"] = normalize_script_line_endings(attrs["script_content"], resolved_script_type)

    return attrs
