import json
from pathlib import Path

from apps.itsm.flowable.bpmn_builder import build_bpmn

APPENDIX_B = {
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "submit", "type": "submit", "name": "提单", "field_perm": {"*": "editable"}},
        {
            "id": "approve_1",
            "type": "approval",
            "name": "部门审批",
            "assignee": {"source": "variable", "value": "initiator_leader"},
            "multi": {"mode": "any"},
            "fallback": "admin",
            "field_perm": {"priority": "editable", "*": "readonly"},
        },
        {"id": "gw_1", "type": "exclusive"},
        {"id": "auto_1", "type": "auto", "name": "初始化主机", "auto": {"kind": "job"}},
        {"id": "handle_1", "type": "handle", "name": "运维处理", "assignee": {"source": "handler_group", "value": 3}, "fallback": "admin"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "submit"},
        {"from": "submit", "to": "approve_1"},
        {"from": "approve_1", "to": "gw_1"},
        {"from": "gw_1", "to": "auto_1", "condition": {"logic": "and", "items": [{"field": "out_approve_1_result", "op": "=", "value": "approve"}]}},
        {"from": "gw_1", "to": "end", "default": True},
        {"from": "auto_1", "to": "handle_1"},
        {"from": "handle_1", "to": "end"},
    ],
    "settings": {"form_id": 7},
}


def test_appendix_b_contains_flowable_mapping():
    xml = build_bpmn(APPENDIX_B, "itsm_demo")
    assert 'id="approve_1"' in xml
    assert "itsm_assignees_approve_1" in xml
    assert "nrOfCompletedInstances &gt;= 1" in xml or "nrOfCompletedInstances >= 1" in xml
    assert "out_approve_1_result == 'approve'" in xml
    assert 'topic="itsm.auto"' in xml or "itsm.auto" in xml
    assert "${initiator}" in xml
    Path("/tmp/itsm-appendix-b.bpmn").write_text(xml, encoding="utf-8")
    json.dumps(APPENDIX_B)
