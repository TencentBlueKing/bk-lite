"""按台核对 VMware 交付回执，作业受理后继续等待 Flowable 下次领取。"""

import base64
import ipaddress
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.itsm.models import AutoExecution, Ticket
from apps.itsm.services.service_assignment import handler_group_members
from apps.itsm.services.vmware_catalog import load_delivery

SCRIPT = Path(__file__).resolve().parents[1] / "support-files/vmware/provision_vm.py"


def submit_vm(ticket, operator, plan, request, generation):
    from apps.job_mgmt.nats_api import _run_script_execute

    payload = base64.urlsafe_b64encode(json.dumps(request).encode()).decode("ascii")
    response = _run_script_execute(
        {
            "name": f"VMware 交付 {request['delivery_id']}",
            "target_source": "manual",
            "target_list": [{"target_id": plan["target_id"]}],
            "script_type": "python",
            "script_content": SCRIPT.read_text(encoding="utf-8"),
            "params": [{"name": "payload", "value": payload}],
            "timeout": 1200,
            "team": [plan["team_id"]],
            "idempotency_key": f"{request['delivery_id']}-{generation}",
        },
        trusted_actor={"user": operator, "domain": ticket.domain},
    )
    if not response.get("result") or not (response.get("data") or {}).get("task_id"):
        raise ValueError("作业平台未确认受理，请核对执行机和作业调度记录")
    return response["data"]["task_id"]


def read_receipt(job_id, team, delivery_id):
    from apps.job_mgmt.nats_api import job_detail_query

    response = job_detail_query({"task_id": job_id, "team": [team]})
    if not response.get("result"):
        raise ConnectionError("暂时无法核对作业状态")
    data = response["data"]
    if data["status"] in {"pending", "running", "cancelling"}:
        return None
    if data["status"] != "success":
        raise ValueError(f"作业 {job_id} 状态为 {data['status']}，请核对该台虚拟机")
    rows = data.get("execution_results") or []
    try:
        if len(rows) != 1:
            raise ValueError()
        receipt = json.loads(rows[0]["stdout"].strip().splitlines()[-1])
        if receipt["delivery_id"] != delivery_id or receipt["status"] != "success" or not receipt["vm_uuid"] or not receipt["vm_id"]:
            raise ValueError()
        ipaddress.ip_address(receipt["ip"])
        return {key: receipt[key] for key in ("hostname", "ip", "vm_id", "vm_uuid", "task_id")}
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ValueError(f"作业 {job_id} 缺少匹配本台 VM 的交付回执") from exc


MACHINE_FIELDS = ("template_id", "network_id", "disk_policy_id", "cpu", "memory_gib", "data_disk_gib")


def _machine_rows(plan):
    if "machines" in plan:
        return plan["machines"]
    return [{key: plan[key] for key in MACHINE_FIELDS} for _ in range(plan["quantity"])]


def advance(ticket, profile, state, plan):
    approved = ticket.logs.filter(task__node_id="approve", action__in=["approve", "reject", "return"]).order_by("-id").first()
    if not approved or approved.action != "approve":
        raise ValueError("尚无有效的运维审批记录")
    machines = _machine_rows(plan)
    if profile == "demo":
        return True, [
            f"第 {i} 台（模拟）：demo-{ticket.pk}-{i}，示例 IP 192.0.2.{i}，{row['cpu']} vCPU / {row['memory_gib']} GiB，数据盘 {row['data_disk_gib']} GiB"
            for i, row in enumerate(machines, 1)
        ]
    if ticket.is_test:
        raise ValueError("测试工单仅可使用模拟交付环境")
    if approved.operator not in handler_group_members(ticket.service.handler_group_id, ticket.domain):
        raise PermissionError("当前运维审批人不在服务处理组内，请核对审批授权")
    lines, complete = [], True
    for index, row in enumerate(machines, 1):
        delivery_id = f"itsm-{ticket.pk}-{index}"
        item = state.setdefault("machines", {}).setdefault(delivery_id, {})
        request = {key: row[key] for key in MACHINE_FIELDS}
        request.update(delivery_id=delivery_id, profile=profile, vc_host=plan["vc_host"])
        if item.setdefault("request", request) != request:
            raise ValueError("交付参数与已记录的创建请求不一致")
        if not item.get("job"):
            item["job"] = submit_vm(ticket, approved.operator, plan, request, item.get("generation", 1))
        if not item.get("receipt") and item.get("failed_job") != item["job"]:
            try:
                item["receipt"] = read_receipt(item["job"], plan["team_id"], delivery_id)
            except ValueError as exc:
                item.update(failed_job=item["job"], error=str(exc))
        if item.get("failed_job") == item["job"]:
            lines.append(f"第 {index} 台 · {item['error']}")
            continue
        receipt = item.get("receipt")
        prefix = f"第 {index} 台 · 作业 {item['job']}"
        if receipt:
            lines.append(f"{prefix} · {receipt['hostname']} · {receipt['ip']} · {receipt['vm_id']} · UUID {receipt['vm_uuid']}")
        else:
            lines.append(f"{prefix} · 等待创建和来宾初始化")
            complete = False
    return complete, lines


def process_delivery(ticket, execution, profile):
    state = execution.detail.get("delivery", {})
    # 作业系统须能先提交自己的执行记录，Worker 才能按 ID 读取。
    try:
        plan = load_delivery(profile, ticket)
        previous = state.get("plan", plan)
        if "quantity" in previous and "machines" in plan:
            previous = {**{k: v for k, v in previous.items() if k not in (*MACHINE_FIELDS, "quantity")}, "machines": _machine_rows(previous)}
        if previous != plan:
            raise ValueError("已批准的交付配置发生变化，请核对原作业")
        state["plan"] = plan
        owned = AutoExecution.objects.filter(pk=execution.pk, status="running", detail__attempt=execution.detail["attempt"])
        if not owned.update(detail={**execution.detail, "delivery": state}):
            return
        done, lines = advance(ticket, profile, state, plan)
        errors = [
            item.get("error", "") for item in state.get("machines", {}).values() if item.get("failed_job") == item.get("job") and item.get("job")
        ]
        status, reason = ("failed" if errors else "executed", "；".join(errors)) if done else ("awaiting_job", "")
    except ConnectionError:
        status, reason, lines = "awaiting_job", "等待作业平台返回状态", []
    except Exception as exc:  # noqa: BLE001 -- 外部平台异常须记录为可核对的流程状态。
        status = "failed"
        reason = str(exc) if isinstance(exc, (ValueError, PermissionError)) else f"请核对交付记录（{type(exc).__name__}）"
        lines = []
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        active = AutoExecution.objects.filter(pk=execution.pk, status="running", detail__attempt=execution.detail["attempt"])
        detail = {**execution.detail, "delivery": state, "reason": reason, "retryable": status == "failed"}
        if not active.update(status=status, detail=detail, updated_at=timezone.now()):
            return
        if lines:
            ticket.form_data = {**ticket.form_data, "delivery_result": "\n".join(lines)}
            ticket.save(update_fields=["form_data", "updated_at"])
        execution.status, execution.detail = status, detail
