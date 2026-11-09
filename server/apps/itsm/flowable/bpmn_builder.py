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


def build_bpmn(payload: dict, process_id: str = "itsm_process") -> str:
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
    defaults = {}
    for node in document.nodes:
        _append_node(process, node)
        if node.type == "exclusive":
            default_edge = next((edge for edge in document.edges if edge.from_ == node.id and edge.default), None)
            if default_edge:
                defaults[node.id] = f"flow_{node.id}_{default_edge.to}"
    for node_id, flow_id in defaults.items():
        process.find(f"{{{BPMN}}}exclusiveGateway[@id='{node_id}']").set("default", flow_id)
    for edge in document.edges:
        attrs = {"id": f"flow_{edge.from_}_{edge.to}", "sourceRef": edge.from_, "targetRef": edge.to}
        flow = ET.SubElement(process, f"{{{BPMN}}}sequenceFlow", attrs)
        if edge.condition and not edge.default:
            expression = ET.SubElement(flow, f"{{{BPMN}}}conditionExpression", {f"{{{XSI}}}type": "tFormalExpression"})
            expression.text = to_juel(edge.condition)
    return ET.tostring(definitions, encoding="unicode")


def _append_node(process, node):
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
    if node.type in {"cc", "auto"}:
        topic = "itsm.notify" if node.type == "cc" else "itsm.auto"
        task = ET.SubElement(
            process,
            f"{{{BPMN}}}serviceTask",
            {"id": node.id, "name": node.name or node.id, f"{{{FLOWABLE}}}type": "external-worker", f"{{{FLOWABLE}}}topic": topic},
        )
        _extension(task, node)
        return
    assignee = "${initiator}" if node.type == "submit" else f"${{itsm_assignee_{node.id}}}"
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
