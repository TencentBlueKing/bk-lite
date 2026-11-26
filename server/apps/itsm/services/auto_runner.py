import requests

from apps.core.logger import itsm_logger as logger
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.itsm.models import DataTable, DataTableRow


def run_auto_action(ticket, kind: str, config: dict, operator: str) -> tuple[str, dict]:
    """执行自动节点。作业和编排只在配置完整时调用；失败只记错误类型。"""
    config = config or {}
    if kind == "integration":
        from apps.itsm.services.integrations import run_for_ticket

        return run_for_ticket(ticket, config, operator)
    if kind == "table" and config.get("table_key"):
        table = DataTable.objects.filter(domain=ticket.domain, key=config["table_key"]).first()
        if table is None:
            return "skipped", {"reason": "数据表不存在"}
        DataTableRow.objects.create(
            table=table,
            domain=ticket.domain,
            data=config.get("data") or {"ticket": ticket.sn},
            created_by=operator,
            updated_by=operator,
        )
        return "done", {"table": table.key}
    if kind == "http":
        return _run_http(config)
    if kind == "job":
        return _run_job(config, ticket)
    if kind == "workflow":
        return _run_workflow(config, operator)
    if kind == "cmdb":
        return _run_cmdb(config)
    return "skipped", {"reason": "未配置可执行动作"}


def _run_http(config: dict) -> tuple[str, dict]:
    url = str(config.get("url") or "")
    try:
        SSRFValidator().validate_url(url)
        response = requests.request(str(config.get("method") or "GET"), url, timeout=3, allow_redirects=False)
    except (SSRFError, requests.RequestException) as exc:
        logger.warning("自动节点 HTTP 失败 error_type=%s", type(exc).__name__)
        return "failed", {"error_type": type(exc).__name__}
    return ("done" if 200 <= response.status_code < 300 else "failed"), {"status_code": response.status_code}


def _run_job(config: dict, ticket=None) -> tuple[str, dict]:
    from apps.job_mgmt.nats_api import job_script_execute

    payload = {
        "name": config.get("name") or (f"ITSM {ticket.sn}" if ticket is not None else "ITSM"),
        "target_source": config.get("target_source") or "manual",
        "target_list": config.get("target_list") or [],
        "script_type": config.get("script_type") or "shell",
        "script_content": config.get("script_content") or "echo itsm",
        "team": config.get("team") or [],
        "callback_type": config.get("callback_type") or "nats",
        "callback_subject": config.get("callback_subject") or "bklite.itsm_job_result",
    }
    if not payload["target_list"] or not payload["team"]:
        return "skipped", {"reason": "作业缺少目标或组织"}
    try:
        result = job_script_execute(payload)
    except Exception as exc:
        logger.warning("自动节点作业失败 error_type=%s", type(exc).__name__)
        return "failed", {"error_type": type(exc).__name__}
    if not isinstance(result, dict) or not result.get("result"):
        return "failed", {"message": str((result or {}).get("message") or "作业未执行")}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return "done", {"task_id": data.get("task_id")}


def _run_workflow(config: dict, operator: str) -> tuple[str, dict]:
    from apps.workflow.models import Workflow
    from apps.workflow.services.conductor import ConductorUnavailable
    from apps.workflow.services.runtime import start_execution

    workflow = Workflow.objects.filter(id=config.get("workflow_id")).first()
    if workflow is None:
        return "skipped", {"reason": "编排流程不存在"}
    try:
        execution = start_execution(
            workflow,
            inputs=config.get("inputs") or {},
            started_by=operator,
            domain="domain.com",
            trigger_type="ITSM",
        )
    except ConductorUnavailable as exc:
        logger.warning("自动节点编排不可用 error_type=%s", type(exc).__name__)
        return "failed", {"error_type": type(exc).__name__}
    except Exception as exc:
        logger.warning("自动节点编排失败 error_type=%s", type(exc).__name__)
        return "failed", {"error_type": type(exc).__name__}
    return "done", {"execution_id": execution.id}


def _run_cmdb(config: dict) -> tuple[str, dict]:
    from apps.rpc.cmdb import CMDB

    try:
        data = CMDB(is_local_client=True).search_instances(**config)
    except Exception as exc:
        logger.warning("自动节点 CMDB 失败 error_type=%s", type(exc).__name__)
        return "failed", {"error_type": type(exc).__name__}
    return "done", {"found": bool(data)}
