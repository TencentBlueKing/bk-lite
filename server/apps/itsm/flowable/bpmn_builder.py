import json
from xml.etree import ElementTree as ET

from apps.itsm.flowable.design_schema import DesignDocument
from apps.itsm.flowable.expressions import to_juel
from apps.itsm.flowable.validator import validate_design

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
FLOWABLE = "http://flowable.org/bpmn"
ITSM = "http://bk-lite/itsm"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


class BpmnBuildError(ValueError):
    pass


def _with_pre_approve(payload: dict) -> dict:
    settings = payload.get("settings") or {}
    if not settings.get("pre_approve"):
        return payload
    nodes = [dict(node) for node in payload.get("nodes") or []]
    if any(node.get("id") == "pre_approve" for node in nodes):
        return payload
    edges = []
    for edge in payload.get("edges") or []:
        if edge.get("from") == "start":
            edges.append({"from": "start", "to": "pre_approve"})
            edges.append({"from": "pre_approve", "to": edge.get("to")})
        else:
            edges.append(dict(edge))
    nodes.append({"id": "pre_approve", "type": "approval", "name": "预审批", "assignee": {"source": "users", "value": ["admin"]}, "fallback": "admin"})
    copied = dict(payload)
    copied["nodes"] = nodes
    copied["edges"] = edges
    return copied


def _merge_parallel_forks(payload: dict) -> dict:
    """并行分叉如果有多条入线，Flowable 会把它当成汇聚一直等待。先用排他网关收口。"""
    nodes = [dict(node) for node in payload.get("nodes") or []]
    edges = [dict(edge) for edge in payload.get("edges") or []]
    ids = {node.get("id") for node in nodes}
    extra_nodes = []
    rewritten = list(edges)
    for node in nodes:
        if node.get("type") not in {"parallel", "parallel_condition", "converge"}:
            continue
        incoming = [edge for edge in rewritten if edge.get("to") == node.get("id")]
        outgoing = [edge for edge in rewritten if edge.get("from") == node.get("id")]
        if len(incoming) <= 1 or len(outgoing) <= 1:
            continue
        merge_id = f"{node['id']}__merge"
        if merge_id in ids:
            continue
        ids.add(merge_id)
        extra_nodes.append({"id": merge_id, "type": "exclusive", "name": "汇合"})
        for edge in rewritten:
            if edge.get("to") == node["id"]:
                edge["to"] = merge_id
        rewritten.append({"from": merge_id, "to": node["id"], "default": True})
    if not extra_nodes:
        return payload
    copied = dict(payload)
    copied["nodes"] = nodes + extra_nodes
    copied["edges"] = rewritten
    return copied


def build_bpmn(payload: dict, process_id: str = "itsm_process") -> str:
    payload = _merge_parallel_forks(_with_pre_approve(payload))
    errors = validate_design(payload)
    if errors:
        raise BpmnBuildError("；".join(errors))
    document = DesignDocument.model_validate(payload)
    ET.register_namespace("", BPMN)
    ET.register_namespace("flowable", FLOWABLE)
    ET.register_namespace("itsm", ITSM)
    ET.register_namespace("xsi", XSI)
    definitions = ET.Element(f"{{{BPMN}}}definitions", {"targetNamespace": ITSM})
    process = ET.SubElement(definitions, f"{{{BPMN}}}process", {"id": process_id, "isExecutable": "true"})
    for node in document.nodes:
        _append_node(process, node)
    for index, edge in enumerate(document.edges):
        if edge.default:
            gateway = process.find(f"{{{BPMN}}}exclusiveGateway[@id='{edge.from_}']")
            if gateway is not None:
                gateway.set("default", f"flow_{index}_{edge.from_}_{edge.to}")
    for index, edge in enumerate(document.edges):
        attrs = {"id": f"flow_{index}_{edge.from_}_{edge.to}", "sourceRef": edge.from_, "targetRef": edge.to}
        flow = ET.SubElement(process, f"{{{BPMN}}}sequenceFlow", attrs)
        if edge.condition and not edge.default:
            expression = ET.SubElement(flow, f"{{{BPMN}}}conditionExpression", {f"{{{XSI}}}type": "tFormalExpression"})
            expression.text = to_juel(edge.condition)
    return ET.tostring(definitions, encoding="unicode")


_NODE_ALIAS = {
    "manual": "handle",
    "decision": "auto",
    "notice": "cc",
    "branch": "exclusive",
    "branch_condition": "exclusive",
    "parallel_condition": "parallel",
    "converge": "parallel",
    "manual_trigger": "auto",
    "rule_trigger": "auto",
    "auto_dispatch": "auto",
    "subprocess": "call",
    "subprocess_submit": "call",
    "subprocess_handle": "handle",
    "knowledge": "auto",
}


def _append_node(process, node):
    node.type = _NODE_ALIAS.get(node.type, node.type)
    if node.type == "start":
        ET.SubElement(process, f"{{{BPMN}}}startEvent", {"id": node.id, "name": node.name or "开始"})
        return
    if node.type == "end":
        ET.SubElement(process, f"{{{BPMN}}}endEvent", {"id": node.id, "name": node.name or "结束"})
        return
    if node.type == "exclusive":
        ET.SubElement(process, f"{{{BPMN}}}exclusiveGateway", {"id": node.id})
        return
    if node.type == "parallel":
        ET.SubElement(process, f"{{{BPMN}}}parallelGateway", {"id": node.id})
        return
    if node.type == "call":
        called = str((node.auto or {}).get("process_key") or node.name or node.id)
        ET.SubElement(
            process,
            f"{{{BPMN}}}callActivity",
            {"id": node.id, "name": node.name or node.id, "calledElement": called, f"{{{FLOWABLE}}}inheritVariables": "true"},
        )
        return
    if node.type in {"cc", "auto"}:
        topic = "itsm.notify" if node.type == "cc" else "itsm.auto"
        task = ET.SubElement(
            process,
            f"{{{BPMN}}}serviceTask",
            {"id": node.id, "name": node.name or node.id, f"{{{FLOWABLE}}}type": "external-worker", f"{{{FLOWABLE}}}topic": topic},
        )
        _extension(task, node)
        return
    if node.type == "submit":
        assignee = "${execution.getVariable('initiator') != null ? execution.getVariable('initiator') : 'admin'}"
    else:
        fallback = node.fallback or "admin"
        key = f"itsm_assignee_{node.id}"
        assignee = "${" + f"execution.getVariable('{key}') != null ? execution.getVariable('{key}') : '{fallback}'" + "}"
    task = ET.SubElement(
        process,
        f"{{{BPMN}}}userTask",
        {"id": node.id, "name": node.name or node.id, f"{{{FLOWABLE}}}assignee": assignee},
    )
    _extension(task, node)
    mode = (node.multi or {}).get("mode")
    if mode in {"any", "all", "serial"}:
        task.attrib.pop(f"{{{FLOWABLE}}}assignee", None)
        multi = ET.SubElement(
            task,
            f"{{{BPMN}}}multiInstanceLoopCharacteristics",
            {
                "isSequential": "true" if mode == "serial" else "false",
                f"{{{FLOWABLE}}}collection": f"itsm_assignees_{node.id}",
                f"{{{FLOWABLE}}}elementVariable": "assignee",
            },
        )
        condition = ET.SubElement(multi, f"{{{BPMN}}}completionCondition")
        condition.text = "${nrOfCompletedInstances >= 1}" if mode == "any" else "${nrOfCompletedInstances == nrOfInstances}"
        task.set(f"{{{FLOWABLE}}}assignee", "${assignee}")


def _extension(task, node):
    extension = ET.SubElement(task, f"{{{BPMN}}}extensionElements")
    payload = ET.SubElement(extension, f"{{{ITSM}}}config")
    payload.text = json.dumps(node.model_dump(), ensure_ascii=False)
