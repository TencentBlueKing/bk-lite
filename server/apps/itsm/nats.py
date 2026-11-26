import nats_client


@nats_client.register
def itsm_create_ticket(workflow_key, title, creator="alert"):
    """告警或其他模块按流程标识创建工单。"""
    from apps.itsm.models import Workflow
    from apps.itsm.views.tickets import _service

    workflow = Workflow.objects.select_related("current_version").get(key=workflow_key)
    if workflow.current_version_id is None:
        raise ValueError("流程未发布")
    ticket = _service().create(workflow.current_version, {"title": title}, creator)
    return {"id": ticket.id, "sn": ticket.sn}
