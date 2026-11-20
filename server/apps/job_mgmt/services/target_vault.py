"""Job 目标消费主机凭据的身份与组织边界。"""

from apps.core.utils.team_utils import get_current_team
from apps.job_mgmt.constants import CredentialSource, OSType, TargetSource
from apps.job_mgmt.models import Target
from apps.job_mgmt.utils.team_authz import normalize_team
from apps.system_mgmt.models import User
from apps.system_mgmt.services.credential_scope import is_current_team_authorized
from apps.system_mgmt.services.credential_service import CredentialServiceError, describe_host_credentials, resolve_job_host_fields


def credential_actor(username, domain, current_team):
    if not username or not domain or not str(current_team).isdecimal() or int(current_team) <= 0:
        return {}
    return {"username": username, "domain": domain, "current_team": int(current_team)}


def request_credential_actor(request):
    user = getattr(request, "user", None)
    return credential_actor(getattr(user, "username", None), getattr(user, "domain", None), get_current_team(request))


def _live_actor(actor):
    from apps.system_mgmt.nats.users import _is_persisted_superuser

    if not actor or not actor.get("username") or not actor.get("domain"):
        raise ValueError("缺少可信的作业凭据消费身份")
    user = User.objects.filter(username=actor["username"], domain=actor["domain"], disabled=False).first()
    if user is None:
        raise ValueError("凭据使用者已不可用")
    return {"current_team": actor.get("current_team"), "group_list": user.group_list, "is_superuser": _is_persisted_superuser(user)}


def describe_target_credentials(credential_ids, actor):
    """对一页目标批量回显，仅返回当前操作者可见的无密元数据。"""
    if not credential_ids:
        return {}
    return describe_host_credentials(credential_ids, _live_actor(actor))


def describe_target_credential(credential_id, os_type, actor):
    item = describe_target_credentials([credential_id], actor).get(credential_id)
    if not item:
        raise ValueError("凭据不存在或当前组织无权使用")
    if item["type"] != _host_type(os_type):
        raise ValueError("凭据类型与目标操作系统不匹配")
    return item


def _host_type(os_type):
    if os_type == OSType.LINUX:
        return "ssh"
    if os_type == OSType.WINDOWS:
        return "winrm"
    raise ValueError("目标操作系统不支持仓库凭据")


def uses_vault_targets(source, target_list):
    if source != TargetSource.MANUAL:
        return False
    ids = [row.get("target_id") for row in (target_list or []) if isinstance(row, dict) and str(row.get("target_id")).isdecimal()]
    return Target.objects.filter(pk__in=ids, credential_source=CredentialSource.CREDENTIAL).exists()


def resolve_target_fields(target, *, execution=None, actor=None):
    if target.credential_source != CredentialSource.CREDENTIAL or not target.credential_id:
        raise ValueError("目标未绑定仓库凭据")
    if execution is not None and execution.enforce_scheduled_team_boundary:
        teams = execution.team
        if not isinstance(teams, list) or len(teams) != 1 or not str(teams[0]).isdecimal():
            raise ValueError("定时作业缺少唯一的任务团队")
        team = int(teams[0])
    else:
        scope = _live_actor(execution.credential_actor if execution is not None else actor)
        team = scope["current_team"]
        if not is_current_team_authorized(team, scope["group_list"], scope["is_superuser"]):
            raise ValueError("无权在当前组织使用凭据")
    if execution is not None and team not in normalize_team(target.team):
        raise ValueError("执行目标不属于凭据消费组织")
    expected_type = _host_type(target.os_type)
    try:
        return resolve_job_host_fields(target.credential_id, expected_type, team)
    except CredentialServiceError as exc:
        if exc.code == "disabled":
            raise ValueError("目标绑定的凭据已停用") from None
        if exc.code == "type_mismatch":
            raise ValueError("凭据类型与目标操作系统不匹配") from None
        raise ValueError("凭据不存在或当前组织无权使用") from None
    except Exception:
        # 密码解密和类型校验异常可能携带原始输入。执行结果只保留固定文案。
        raise ValueError("目标凭据字段无法解析") from None
