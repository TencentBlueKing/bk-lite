"""将已审批节点按配置交给作业平台，按真实执行记录推进 Flowable。"""

import unicodedata

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.base.models import User
from apps.core.backends import APISecretAuthBackend
from apps.itsm.models import AutoExecution, Ticket
from apps.itsm.services.notify.recipients import active_users
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution, Script, Target
from apps.job_mgmt.services.execution_service import ExecutionAuthorizationError, ExecutionService
from apps.job_mgmt.services.execution_timeout_service import ExecutionTimeoutService
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.job_mgmt.services.target_vault import credential_actor
from apps.job_mgmt.services.template_revision import payload_hash, script_payload
from apps.job_mgmt.utils.team_authz import normalize_team
from apps.system_mgmt.services.credential_scope import is_current_team_authorized


def template_resources(domain, team_id, script_id, target_id, *, lock=False):
    scripts = Script.objects.select_for_update() if lock else Script.objects
    targets = Target.objects.select_for_update() if lock else Target.objects
    script = scripts.filter(domain=domain, pk=script_id).first()
    if not script or team_id not in normalize_team(script.team):
        raise PermissionError("作业模板不存在或不属于当前组织")
    target = targets.filter(domain=domain, pk=target_id, team_memberships__team_id=team_id).first()
    if not target:
        raise PermissionError("执行目标不存在或不属于当前组织")
    return script, target


def require_job_permission(operator, domain, team_id):
    if not active_users(domain).filter(username=operator).exists():
        raise PermissionError("流程发布人已停用或失效")
    user = User.objects.filter(username=operator, domain=domain, is_active=True).first()
    if user:
        user._api_secret_team_scope = True
        user._api_secret_team = team_id
        APISecretAuthBackend()._populate_user_permissions(user, team_id)
    if not user or not is_current_team_authorized(team_id, user.group_list, user.is_superuser):
        raise PermissionError("流程发布人无权在工单所属组织执行作业")
    if not user.is_superuser and "quick_exec-Add" not in user.permission.get("job", ()):
        raise PermissionError("流程发布人缺少作业平台快速执行权限")


def _parameter_value(reference, row, sources, name):
    if isinstance(reference, str):
        reference = {"source": "item", "key": reference}
    if not isinstance(reference, dict) or not isinstance(reference.get("key"), str):
        raise ValueError(f"参数「{name}」映射格式有误")
    source, key = reference.get("source"), reference["key"]
    if source == "literal":
        return key
    if source == "item" and not key and row is not None:
        return row
    if source not in ("item", "form", "system", "output"):
        raise ValueError(f"参数「{name}」来源有误")
    values = row if source == "item" else sources.get(source)
    if not isinstance(values, dict) or key not in values:
        raise ValueError(f"未找到参数「{name}」引用的字段")
    return values[key]


def row_parameters(definitions, mapping, row, sources=None):
    if not isinstance(mapping, dict):
        raise ValueError("作业参数映射格式有误")
    params = []
    for definition in definitions:
        name = definition.get("name") or definition.get("key")
        if not name or definition.get("is_encrypted"):
            raise ValueError("请选择参数具名且不含加密参数的作业模板")
        reference = mapping.get(name)
        value = _parameter_value(reference, row, sources or {}, name) if reference is not None else ""
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"参数「{name}」需要单个文本或数值")
        value = "" if value is None else str(value)
        # 作业平台会将 argv 转交远端脚本包装器，保留标点但不接受多行、控制字符或模板指令。
        if (
            len(value) > 512
            or any(unicodedata.category(char) in {"Cc", "Zl", "Zp"} for char in value)
            or any(token in value for token in ("{{", "{%", "{#"))
        ):
            raise ValueError(f"参数「{name}」仅支持 512 字以内的单行内容，不支持模板指令或控制字符")
        params.append({"name": name, "value": value, "is_modified": reference is not None})
    if mapping.keys() - {p["name"] for p in params}:
        raise ValueError("参数映射与作业模板定义不一致")
    return params


def _authorized_resources(ticket, config):
    if ticket.is_test:
        raise ValueError("测试工单不能执行真实作业")
    teams = normalize_team(ticket.team)
    if len(teams) != 1:
        raise ValueError("工单须归属唯一执行组织")
    team = next(iter(teams))
    nodes = ticket.workflow_version.design.get("nodes", [])
    approval_ids = [node["id"] for node in nodes if node.get("type") == "approval"]
    approval = (
        ticket.logs.filter(
            task__node_id__in=approval_ids, task__process_instance_id=ticket.process_instance_id, action__in=["approve", "reject", "return"]
        )
        .order_by("-id")
        .first()
    )
    if not approval or approval.action != "approve":
        raise PermissionError("当前流程缺少有效审批记录")
    binding = config.get("binding") or {}
    if not ticket.workflow_version.is_published or binding.get("team_id") != team or not binding.get("operator"):
        raise PermissionError("当前流程版本缺少本组织的作业发布授权")
    operator = binding["operator"]
    require_job_permission(operator, ticket.domain, team)
    script, target = template_resources(ticket.domain, team, config.get("script_id"), config.get("target_id"), lock=True)
    if payload_hash(script_payload(script)) != binding.get("script_hash"):
        raise PermissionError("作业模板已变更，请核对模板并重新发布流程")
    if script.script_type not in ({"powershell"} if target.os_type == "windows" else {"shell", "python"}):
        raise ValueError("作业脚本类型与目标操作系统不匹配")
    return team, operator, script, target


def _prepare_plan(ticket, config, script):
    mode = config.get("mode", "each" if config.get("table_key") else "once")
    if mode not in ("once", "each"):
        raise ValueError("未知的作业执行方式")
    form = ticket.form_data
    output_keys = {
        node["auto"]["result_field"]
        for node in ticket.workflow_version.design.get("nodes", [])
        if (node.get("auto") or {}).get("kind") == "integration" and node["auto"].get("result_field")
    }
    sources = {
        "form": form,
        "output": {key: form[key] for key in output_keys if key in form},
        "system": {"id": ticket.pk, "sn": ticket.sn, "creator": ticket.creator, "title": ticket.title},
    }
    items = [None]
    if mode == "each":
        collection = config.get("collection", f"form.{config.get('table_key', '')}")
        source, _, key = collection.partition(".") if isinstance(collection, str) else ("", "", "")
        items = sources[source].get(key) if source in {"form", "output"} else None
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("批量作业需要包含 1 至 100 项的集合")
    batch_size = config.get("batch_size") if mode == "each" else 1
    dispatch_mode = config.get("dispatch_mode", "batch" if batch_size else "parallel")
    if dispatch_mode not in {"batch", "parallel"} or (dispatch_mode == "parallel" and config.get("batch_size") is not None):
        raise ValueError("并发执行不能配置每批项数")
    if dispatch_mode == "batch" and batch_size is None:
        raise ValueError("分批执行需要设置每批项数")
    if batch_size is None:
        batch_size = len(items)
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("每批数量须为 1 至 100 的整数")
    pending = []
    for item in items:
        params = row_parameters(script.params, config.get("params", {}), item, sources)
        resolved = ScriptParamsService.resolve_params(params, script=script)
        if script.script_type == "powershell" and any(c in str(p["value"]) for p in resolved for c in "‘’‚‛"):
            raise ValueError("PowerShell 作业参数不支持弯单引号")
        pending.append(params)
    return {"mode": mode, "dispatch_mode": dispatch_mode, "total": len(items), "batch_size": batch_size, "rows": [], "pending_params": pending}


def _submit_batch(ticket, execution, config, progress):
    team, operator, script, target = _authorized_resources(ticket, config)
    if not progress.get("pending_params"):
        progress = _prepare_plan(ticket, config, script)
    pending = progress["pending_params"]
    rows = list(progress["rows"])
    batch_size = progress["batch_size"]
    for params in pending[:batch_size]:
        index = len(rows) + 1
        prefix = f"{ticket.sn} · 第 {index} 项" if progress["mode"] == "each" else ticket.sn
        data = {
            "name": f"{prefix} · {script.name}"[:128],
            "target_source": "manual",
            "target_list": [{"target_id": target.pk}],
            "script_id": script.pk,
            "params": params,
        }
        job = ExecutionService.prepare_quick_execution(
            data=data,
            team=[team],
            authorized_team_ids={team},
            username=operator,
            credential_actor=credential_actor(operator, ticket.domain, team),
            timeout_explicit=False,
            client_request_id=f"itsm-template-{execution.pk}-{index}",
        )
        # 同事务持久化等待期限，进程若在提交后、派发前退出也会由作业平台收敛。
        ExecutionTimeoutService.arm_pending(job.pk)
        transaction.on_commit(lambda job=job: ExecutionService._dispatch_or_raise(job), robust=True)
        rows.append({"row": index, "job_id": job.pk, "status": job.status})
    return {**progress, "rows": rows, "pending_params": pending[batch_size:]}


def _poll_rows(ticket, rows):
    jobs = dict(JobExecution.objects.filter(domain=ticket.domain, pk__in=[r["job_id"] for r in rows]).values_list("pk", "status"))
    for row in rows:
        if row["job_id"] not in jobs:
            raise ValueError(f"第 {row['row']} 项的作业记录已不存在，请核对作业历史")
        row["status"] = jobs[row["job_id"]]
    if any(r["status"] not in ExecutionStatus.TERMINAL_STATES for r in rows):
        return "awaiting_job", ""
    failures = [str(r["row"]) for r in rows if r["status"] != ExecutionStatus.SUCCESS]
    return ("failed", f"第 {', '.join(failures)} 项作业未成功，请查看作业记录") if failures else ("executed", "")


@transaction.atomic
def process_template(ticket, execution, config):
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    active = AutoExecution.objects.select_for_update().filter(pk=execution.pk, status="running", detail__attempt=execution.detail["attempt"]).first()
    if not active:
        return
    progress = active.detail.get("job_template", {})
    rows = progress.get("rows", [])
    try:
        if ticket.process_instance_id != active.detail["process_id"] or (
            ticket.status_id and ticket.status.key in {"finished", "cancelled", "terminated"}
        ):
            raise ValueError("工单流程已结束或切换")
        if ticket.status_id and ticket.status.key == "suspended":
            status, reason = "awaiting_job", "等待工单恢复"
        else:
            status, reason = _poll_rows(ticket, rows) if rows else ("executed", "")
            if status == "executed" and (not rows or progress.get("pending_params")):
                # 同一事务保存派发凭据与下一批参数，上一批全部成功才可领取下一批。
                with transaction.atomic():
                    progress = _submit_batch(ticket, active, config, progress)
                status = "awaiting_job"
    except (PermissionError, ValueError, ExecutionAuthorizationError) as exc:
        status, reason = "failed", str(exc)
    except ValidationError:
        status, reason = "failed", "作业参数未通过模板的必填或选项校验"
    active.detail = {
        **active.detail,
        "job_template": progress or {"rows": []},
        "reason": reason,
        "retryable": status == "failed" and not progress.get("rows"),
    }
    active.status = status
    active.save(update_fields=["status", "detail", "updated_at"])
    execution.status, execution.detail = status, active.detail
