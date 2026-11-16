from apps.itsm.flowable.validator import validate_design


def design(perm):
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "handle", "type": "handle", "assignee": {"source": "users", "value": ["alice"]}, "field_perm": perm},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "handle"}, {"from": "handle", "to": "end"}],
        "settings": {"fields": ["title", "result"]},
    }


def test_unknown_field_permission_rejected():
    assert validate_design(design({"result": "anything"}))


def test_node_required_permission_accepted():
    assert not validate_design(design({"title": "read", "result": "required"}))
