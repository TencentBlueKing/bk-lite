import pytest

from apps.itsm.services.workflow.assignee import AssigneeBlocked, AssigneeResolver

GROUPS = {3: {"members": ["u1", "u2"], "leaders": ["lead"]}}
ORG = {"g9": ["org-user"]}


def resolver(**kwargs):
    return AssigneeResolver(groups=GROUPS, org_users=ORG, pending_counts={"u1": 4, "u2": 1}, **kwargs)


def test_five_sources():
    ctx = {"initiator": "me", "initiator_leader": ["boss"], "form": {"owner": ["form-user"]}, "node_assignees": {"approve_1": ["prev"]}}
    engine = resolver()
    assert engine.resolve({"assignee": {"source": "users", "value": ["a"]}}, ctx) == ["a"]
    assert engine.resolve({"assignee": {"source": "handler_group", "value": 3}}, ctx) == ["u1", "u2"]
    assert engine.resolve({"assignee": {"source": "org", "value": "g9"}}, ctx) == ["org-user"]
    assert engine.resolve({"assignee": {"source": "variable", "value": "initiator"}}, ctx) == ["me"]
    assert engine.resolve({"assignee": {"source": "variable", "value": "form.owner"}}, ctx) == ["form-user"]


def test_three_fallbacks():
    engine = resolver()
    assert engine.resolve({"fallback": "skip", "assignee": {"source": "users", "value": []}}, {}) == []
    assert engine.resolve({"fallback": "admin", "assignee": {"source": "users", "value": []}}, {}) == ["admin"]
    with pytest.raises(AssigneeBlocked):
        engine.resolve({"fallback": "block", "assignee": {"source": "users", "value": []}}, {})


def test_least_pending():
    chosen = resolver().resolve({"assignee": {"source": "handler_group", "value": 3}, "multi": {"balance": "least_pending"}}, {})
    assert chosen == ["u2"]


def test_manual_node_writes_assignee_variable():
    from apps.itsm.services.ticket.service import TicketService

    version = type(
        "Version",
        (),
        {
            "design": {
                "nodes": [
                    {"id": "sec", "type": "manual", "assignee": {"source": "users", "value": ["bob"]}, "fallback": "admin"},
                ]
            }
        },
    )()
    variables = TicketService(None)._assignee_variables(version, "admin", {})
    assert variables["itsm_assignee_sec"] == "bob"
